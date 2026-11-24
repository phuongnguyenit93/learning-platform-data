# Shrinking the context to detect excessive access permissions

## Objectives

After this lesson, you can inspect what capabilities a SpEL EvaluationContext currently provides; narrow down the root object, property accessors, method resolvers, bean resolvers, functions, and type creation mechanisms; and use allowed/denied probes to detect excessive access permissions. You will also know when to choose SimpleEvaluationContext, when a custom context is needed, how to keep existing expressions working after narrowing permissions, and how to investigate errors without widening the context just to make tests pass.

## 1. Why shrink EvaluationContext?

EvaluationContext determines the data and mechanisms SpEL can use when evaluating an expression. Depending on configuration, an expression can read properties, call methods, reference beans, invoke functions, convert types, or instantiate objects.

An overly capable context increases the blast radius of an expression. For example, a rule only needs to read `order.total` yet is evaluated against a full domain entity, a service with data-write capabilities, a BeanResolver accessing the entire container, and the default method resolver. If an expression or template is modified unexpectedly, those extra capabilities can become pathways to unnecessary data or actions.

Shrinking the context helps answer these questions:

- Which objects and properties does the expression actually need to read?
- Does it need to call methods or only read prepared data?
- Does it need bean references or can the application pass results via variables?
- Which functions are needed, and what permissions do those functions have?
- Are type references or constructor invocations needed?
- Which operations must always be denied?
- When the model or expression changes, which tests will catch newly widened permissions?

The principle is to grant only the capabilities required for the expression's task. Unnecessary permissions should be removed directly in the context instead of relying on expression author conventions.

## 2. Inventory permissions before changing the context

First, list the operations that current expressions perform:

| Capability | Indicator in expression or context |
|---|---|
| Read root property | `name`, `order.total`, `#root.id` |
| Read variable | `#minimum`, `#customer` |
| Read variable property | `#customer.profile.name` |
| Call instance method | `#order.calculateTotal()` |
| Call registered function | `#normalize(#code)` |
| Bean reference | `@pricingService.calculate(...)` |
| Type reference | `T(java.time.LocalDate)` |
| Call constructor | `new java.math.BigDecimal(...)` |
| Assign property | `status = 'READY'` |
| Selection/projection | `#orders.?[...]`, `#orders.![...]` |

Read the expression sources and identify the root object, variables, and resolvers supplied by the application. Clearly note which capabilities are business requirements and which exist solely because the context uses a default configuration.

Do not shrink a context by randomly deleting a resolver and waiting for production errors. First determine what the expression needs, write tests for valid behavior and behavior that must be denied, and then apply the minimal configuration.

## 3. Narrow the root object first

The root object is the starting point for accessing properties without the # prefix. Passing a large entity or an object with many relationships exposes more data to the expression than necessary.

For example, instead of passing the entire User entity into the context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(userEntity);
~~~

create a dedicated read-only view object containing only the data needed by the expression:

~~~java
public record UserView(
        String displayName,
        String locale,
        boolean active) {
}
~~~

Then:

~~~java
UserView view = new UserView(
    user.getDisplayName(),
    user.getLocale(),
    user.isActive()
);

EvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

Object result = expression.getValue(context, view);
~~~

The expression only receives the properties exposed on UserView. Relationships, setters, and administrative methods on the real entity do not exist on this object.

This is a useful data boundary: if an expression only needs name and locale, there is no reason to pass password hashes, roles, tokens, internal collections, or repositories in the root object.

## 4. Pass data via variables instead of overly broad objects

Not all required data has to live on the root object. Specific values can be passed via variables:

~~~java
context.setVariable("minimumTotal", minimumTotal);
context.setVariable("featureEnabled", featureEnabled);
~~~

Expression:

~~~text
total >= #minimumTotal and #featureEnabled
~~~

This makes the inputs required by the rule explicit. If only a number or boolean is needed, pass that exact value instead of passing a service or large configuration for the expression to traverse itself.

When passing objects via variables, apply the same rule as for the root object: prefer a DTO or view containing only needed properties. Variables do not restrict permissions on their own; if a value is a service or object with sensitive methods, the expression can still use whatever capabilities the context allows.

Name variables according to their role and check their types before evaluation. Never concatenate user input directly into expression sources.

## 5. SimpleEvaluationContext for data-reading expressions

SimpleEvaluationContext is designed for cases needing a restricted set of SpEL features. For instance, when an expression only needs to read properties via data binding:

~~~java
EvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

You can evaluate an expression on the root object:

~~~java
Expression expression =
    new SpelExpressionParser().parseExpression(
        "active and locale != null"
    );

Boolean active =
    expression.getValue(context, userView, Boolean.class);
~~~

SimpleEvaluationContext does not provide all features of StandardEvaluationContext. It does not enable type references, constructor invocations, or bean references like a full context does. Method invocation is also not enabled by default; the builder can configure instance method access when the application genuinely needs it.

For property-reading expressions, this is usually the right starting point. If an additional feature is needed, enable just that capability and re-test the permission boundary after configuring.

## 6. Prefer read-only over read-write whenever possible

If an expression only serves calculation, conditions, or display, do not grant property write permissions:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Read-only mode allows reading properties via the corresponding accessor while preventing expressions from mutating properties through data binding.

If the application needs to update certain fields, consider a dedicated command or DTO, validation, and a Java service with explicit authorization. When assignment in SpEL is still needed, use a read-write context with an allowlist PropertyAccessor permitting only the exact properties that need writing.

Do not use read-write just because an existing expression has an assignment operator. First determine why the update belongs in an expression and whether a dedicated service expresses the rule more clearly.

## 7. Restrict PropertyAccessor by type and property

PropertyAccessor determines whether an expression can read or write a property on a target object. With a custom accessor, you can control both the target type and the property name.

An allowlist should explicitly define:

- Supported target types.
- Readable properties.
- Writable properties, if any.
- How missing or disallowed properties are handled.
- Data types the accessor accepts.

Example policy for a view:

| Target type | Property | Read | Write |
|---|---|---|---|
| UserView | displayName | Allowed | No |
| UserView | locale | Allowed | No |
| UserView | active | Allowed | No |
| UserEntity | passwordHash | No | No |
| UserEntity | role | No or restricted | No |

Do not use a short denylist as the default policy for large objects. When the model adds new properties, a denylist can accidentally expose new properties; an allowlist keeps deny-by-default.

If only a small set of properties needs to be read, SimpleEvaluationContext with a read-only DataBindingPropertyAccessor may suffice. If finer-grained rules are needed, use a custom PropertyAccessor and test each allowed and denied property.

## 8. Controlling method invocation

Method invocation can turn a data-reading expression into an action. A method like getDisplayName() may merely return a value, whereas methods like changeRole(), deleteAccount(), or sendPayment() can mutate state or interact with external systems.

SimpleEvaluationContext does not enable instance method invocation by default. Only call the builder's withInstanceMethods() if the expression genuinely needs to call methods on supplied objects.

If enabling method invocation, narrow the passed objects so they only have safe and necessary methods. A getter-only DTO is usually easier to control than a full entity or service.

With StandardEvaluationContext, note that the default MethodResolver may allow calling public methods on accessible objects. When using this context for untrusted expressions, configure an explicit allowlist resolver or choose an appropriately restricted context.

Do not treat a read-only property accessor as sufficient to guarantee an expression cannot mutate state. Method invocation is a separate pathway that must be controlled.

## 9. Restricting BeanResolver and bean references

The `@beanName` syntax requires a BeanResolver. If an expression only needs a few computed values, pass those values via variables instead of exposing the entire Spring container.

For example, instead of:

~~~text
@pricingService.calculate(#order)
~~~

the application can call the service in Java beforehand and then pass the resolved result:

~~~java
context.setVariable(
    "calculatedTotal",
    pricingService.calculate(order)
);
~~~

The expression only needs:

~~~text
#calculatedTotal >= #minimumTotal
~~~

This keeps the service and its dependencies outside the expression's scope.

If bean references are genuinely required, use a restricted BeanResolver that only resolves approved beans. Avoid providing a broad BeanFactory or ApplicationContext to user-editable templates. Allow only beans with necessary methods, clear contracts, and no permissions beyond the intended purpose.

Do not register beans in the context merely to avoid passing a simple variable. Every exposed bean can expand what the expression can invoke.

## 10. Register only necessary functions

Functions registered in EvaluationContext can invoke Java code via `#functionName(...)` syntax.

If an expression only needs to normalize a code, register just that function:

~~~java
context.registerFunction(
    "normalizeCode",
    TextFunctions.class.getMethod("normalizeCode", String.class)
);
~~~

Do not register an entire large utility suite if the expression only needs one function. Do not register functions that can execute commands, read secrets, write files, make network calls, or mutate data when the expression's purpose is just calculation.

Functions and variables share a namespace, so avoid naming collisions. For untrusted contexts, maintain a small function allowlist and test that names outside the list cannot be invoked.

If logic needs dependencies or transactions, keep it in a Java service. Functions are best suited for small, deterministic transformations with clear inputs and outputs.

## 11. Restricting type references and constructor invocations

StandardEvaluationContext supports type references via `T(...)` and constructor invocations via `new`. These capabilities can expand the range of classes and behaviors an expression accesses.

If an expression does not need to instantiate objects or reference classes, do not provide a broad context just for convenience. SimpleEvaluationContext omits these capabilities by design.

If genuinely required in a custom context, review TypeLocator and ConstructorResolver against an allowlist. Only permit types and constructors explicitly identified as necessary. Do not allow a broad package assuming every class in that package is safe.

You should also check constructor arguments and how many times the expression is evaluated. A constructor can allocate large objects, open resources, or perform side effects.

## 12. Controlling custom TypeConverters and PropertyAccessors

TypeConverter can convert values between types; PropertyAccessor reads or writes properties; both affect expression behavior.

Only configure custom converters when the expression needs that conversion. A broad converter can create more conversion paths than expected or accept overly permissive input formats.

With custom property accessors, avoid falling back to a broad reflective accessor if the goal is to restrict permissions. Inspect the actual accessor list in the context and confirm which accessor handles each target type.

If a custom accessor does not accept a target type, SpEL may try the next accessor. Therefore, an allowlist accessor placed before a general accessor does not automatically guarantee denial of non-listed properties if the later accessor can still read them. Design the accessor list so no unintended broad access path remains.

## 13. Building a minimal context for read-only expressions

The following example provides a dedicated root object and a read-only context:

~~~java
public record OrderView(
        String status,
        BigDecimal total,
        boolean customerActive) {
}

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "customerActive and total >= #minimumTotal"
);

SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

OrderView view = new OrderView(
    "PAID",
    new BigDecimal("125.00"),
    true
);

context.setVariable(
    "minimumTotal",
    new BigDecimal("100.00")
);

Boolean eligible =
    expression.getValue(context, view, Boolean.class);
~~~

The example illustrates the principles:

- The root object has only the three required properties.
- The context permits only read data binding.
- The threshold is passed as a variable.
- The expression needs no beans, functions, type references, or constructor invocations.

Create a separate context per processing run if variables or root objects change.

## 14. Use a dedicated context per task

Do not use one shared broad context for every expression. Different tasks may require different permission sets:

| Task | Appropriate context |
|---|---|
| Rendering a label from a DTO | Read-only data binding |
| Checking conditions on a view object | Read-only context and necessary variables |
| Computing with pure functions | Context with exact function allowlist |
| Updating a dedicated DTO | Read-write accessor with write allowlist |
| Rule needing a service call | Handle service in Java or restricted bean resolver |
| User-editable template | Restricted context, narrow root object, no excess execution rights |

Separating contexts by task prevents one expression from accidentally inheriting permissions needed only by another expression. It also makes tests easier to read because each context has a concrete contract.

Do not reuse a mutable context across different requests if variables, root objects, or access permissions may change. Sharing a broad context can cause data leaks and unpredictable behavior.

## 15. Testing for excessive permissions with negative tests

A test proving that a valid expression runs is not enough to confirm the context has been narrowed. Negative tests are needed for actions that must be denied.

For example, if an expression is only allowed to read displayName:

- Reading displayName must succeed.
- Assigning displayName must be denied.
- Calling a method that changes roles must be denied or inaccessible.
- Referencing an unprovided bean must fail.
- Disallowed type references or constructors must not execute.
- Properties outside the allowlist must be denied.

Tests can be written with JUnit:

~~~java
@Test
void readOnlyContextCanReadButCannotWrite() {
    EvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Profile profile = new Profile("An");

    Expression read =
        parser.parseExpression("displayName");

    assertEquals(
        "An",
        read.getValue(context, profile, String.class)
    );

    Expression write =
        parser.parseExpression("displayName = 'Binh'");

    assertThrows(
        EvaluationException.class,
        () -> write.getValue(context, profile)
    );
}
~~~

Exact exception types may depend on the operation and Spring version; check the project's actual exception hierarchy. What matters is that the test proves the write operation did not happen and the object retains its original value.

Negative tests should verify both the outcome and the object's state after denial.

## 16. Comparing broad context and narrowed context

One way to spot excessive permissions is to tabulate behaviors for the expression on the current context and the target context:

| Operation | Current context | Desired narrowed context |
|---|---|---|
| Read required property | Succeeds | Succeeds |
| Read sensitive property | May currently succeed | Denied or absent from root view |
| Write property | May be allowed | Denied |
| Call unnecessary method | May be allowed | Denied |
| Reference bean | May resolve | Absent or narrow allowlist |
| Call unnecessary function | May be registered | Not registered |
| Type reference/constructor | May be supported | Unsupported or explicit allowlist |

Run the same test suite on both configurations. For required operations, results must stay the same. For excessive operations, the narrowed context must deny them.

Do not use the broad context as the correctness baseline for every behavior. The goal is to preserve approved use cases and eliminate unnecessary capabilities.

## 17. Tracking permission changes when expressions or models change

Permissions can widen unintentionally when:

- The root object is changed from a DTO to a full entity.
- Method invocations are added to an expression.
- Additional beans or functions are registered.
- SimpleEvaluationContext is replaced with StandardEvaluationContext.
- A reflective accessor or broad resolver is added.
- Assignment or constructor invocation is enabled.
- Variable or property types change.

Record the list of capabilities each expression is allowed to use alongside corresponding tests. When modifying an expression or context, re-run both positive and negative tests.

If expressions are stored in a database or external configuration, attach an identifier/version to the template. When a template changes, test it against the intended context before publishing.

Do not grant extra global permissions to fix an individual expression. If an expression needs an extra capability, evaluate the need and create a dedicated context for it.

## 18. Debugging when an expression is denied

When an expression fails after shrinking the context, identify which capability is missing:

1. Does the root object have the right type and required properties?
2. Are required variables registered?
3. Does PropertyAccessor support the target type?
4. Is the expression calling a method that the context does not enable?
5. Is there a bean reference without a BeanResolver?
6. Is there an unregistered function?
7. Is there a restricted type reference or constructor?
8. Does a value need a conversion unsupported by the current converter?
9. Is this an intended access-control failure or a missing configuration?

If the denied operation is outside requirements, the test is confirming the right policy. If it is valid behavior for the use case, add only the exact needed capability and update the tests.

Do not resolve errors by switching every expression to StandardEvaluationContext or adding broad reflective resolvers. That approach can make current tests pass while reopening permissions that were intentionally removed.

## 19. Logging and observing capabilities

In development environments, you can record the context configuration and expression identifier to see which permission set an expression is evaluated with.

Log:

- Expression identifier or template version.
- EvaluationContext type in use.
- Root object type or DTO type.
- Supplied variable names, without necessarily logging values.
- Configured accessors/resolvers/functions.
- Denied operation type and related property or method.
- Exception type and cause chain.

Do not log entire objects, passwords, tokens, personal data, or sensitive variable values. Logs should help identify which capability was invoked without becoming a copy of business data.

In production, use metrics or rate-limited logs to track denial errors. A sudden spike may indicate an outdated template not yet updated, a model change, or a source attempting to use a capability outside the allowlist.

## 20. Context-shrinking checklist

Before putting an expression into use, verify:

1. Root object contains only data the expression needs.
2. Variables are explicitly registered with expected types.
3. Context is read-only if updates are unnecessary.
4. PropertyAccessor supports only approved target types and properties.
5. Method invocation is disabled if unnecessary.
6. BeanResolver is not provided if bean references are unnecessary.
7. If beans are needed, the resolver resolves only allowlisted beans.
8. Only genuinely needed functions are registered.
9. Type references and constructor invocations are not opened unless needed.
10. Converters do not accept extra formats beyond the contract.
11. No broad accessor/resolver accidentally reopens permissions.
12. Positive tests exist for necessary operations.
13. Negative tests exist for excessive operations.
14. Tests confirm objects are not mutated when operations are denied.
15. Context does not share mutable state across unrelated requests.

This checklist turns a "looks-safe context" into a testable permission contract.

## 21. Takeaways

EvaluationContext is the boundary deciding which data and capabilities SpEL is allowed to use. Start with a small root object or read-only DTO, pass needed values via variables, and choose SimpleEvaluationContext when expressions only need limited data binding.

PropertyAccessor controls property reads/writes; MethodResolver controls method calls; BeanResolver controls bean references; function registration permits invoking selected Methods; TypeLocator and ConstructorResolver govern type references and constructor invocations. Never let a general accessor or resolver accidentally reopen permissions behind an allowlist.

To detect excessive permissions, test both valid behaviors and behaviors that must be denied. Compare the current context with the narrowed context, confirm valid results remain unchanged, and verify unnecessary operations cannot execute. When an expression is denied, add only the exact required capability rather than widening the entire context.

Shrinking the context does not replace authorization in services or business validation. Actions that mutate data, permissions, or resources should still go through Java APIs with explicit contracts and controls.

## References

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [PropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html)
- [MethodResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/MethodResolver.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)