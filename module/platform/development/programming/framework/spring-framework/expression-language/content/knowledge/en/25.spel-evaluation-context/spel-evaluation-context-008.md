# Context Reuse and the Risk of Retained State

## Objectives

In SpEL, the **Expression** object holds the parsed expression, while **EvaluationContext** supplies the data and configuration needed to evaluate that expression. These two objects have different lifecycles and roles. A parsed Expression can be reused across many evaluations, whereas reusing a mutable EvaluationContext across requests requires careful control.

An EvaluationContext can hold a root object, variables, functions, and configuration components such as PropertyAccessor, MethodResolver, TypeConverter, TypeLocator, or BeanResolver. If an application swaps the root object or variables per request but forgets to update everything completely, data from a previous evaluation can affect the next one. If multiple threads mutate the same context concurrently, evaluations can even observe state belonging to another request.

After this lesson, you will be able to:

- Distinguish reusing an Expression from reusing an EvaluationContext.
- Identify state retained in the root object, variables, and context configuration.
- Avoid accidentally using data from a previous request in subsequent evaluations.
- Understand the risks when multiple threads update the same context.
- Create a separate EvaluationContext per request or per evaluation.
- Reuse shared configuration without sharing mutable request state.
- Write tests that detect stale state, data leakage, and concurrency bugs.

## 1. Expression and EvaluationContext have different roles

An Expression is the result of parsing a SpEL string. It represents the syntax and structure of the expression to be evaluated.

EvaluationContext provides the environment in which the expression runs, including:

- Default root object.
- Variables registered via setVariable().
- Functions registered in the context.
- PropertyAccessor and MethodResolver.
- ConstructorResolver and BeanResolver if configured.
- TypeLocator, TypeConverter, and OperatorOverloader.
- Other components that determine how expressions access or convert data.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#root.total >= #minimumTotal");
~~~

The Expression above can be retained and used for multiple evaluations. Each evaluation can supply an appropriate root object and context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable("minimumTotal", new BigDecimal("100"));

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

Key point: Expression describes what to compute; EvaluationContext provides the data and rules to compute it. Reusing an Expression does not require reusing the same EvaluationContext.

## 2. What state can be retained in a context?

An EvaluationContext is not merely a transient parameter. It can hold values and configuration across multiple getValue() calls.

### Root object

When creating a StandardEvaluationContext with a root object:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);
~~~

the context holds a reference to that object as the default root. If the application reuses the context without replacing the root object, the next expression can still read the old object.

If the root object is mutable and another part of the application modifies it, the expression will observe the new state of that exact object. Reusing a context does not create an independent copy of the root object.

### Variables

Variables registered with setVariable():

~~~java
context.setVariable("minimumTotal", new BigDecimal("100"));
context.setVariable("region", "VN");
~~~

remain in the context until they are changed or the context is no longer used. If a subsequent evaluation does not supply a new value for a variable, the old value may continue to be read.

For example, the first request sets minimumTotal to 100. The second request only updates region and forgets to update minimumTotal. The expression can still use the threshold of 100 from the previous request, even though the second request did not intend that.

### Functions and configuration

Functions registered in the context, along with configured accessors, resolvers, and converters, are also part of the evaluation environment. These are typically stable shared configuration, but if the application mutates them while evaluation is underway, behavior can become unpredictable.

Distinguish clearly:

- Fixed application configuration can be set up once and kept stable.
- Root objects, variables, and per-request data references need to be isolated per evaluation.
- Mutable objects stored inside variables can still change even if the context itself is not modified.

## 3. Distinguishing Expression reuse and context reuse

| Component | Can it be reused? | What needs to be controlled |
|---|---|---|
| Parsed Expression | Usually reusable across many evaluations | Same syntax, appropriate parser/compiler configuration |
| EvaluationContext | Reusable within a processing flow with stable state | Root object, variables, and any mutations in the context |
| Root object | Can be kept unchanged if evaluations work on the same object | Mutable state, access permissions, and object lifecycle |
| Context variables | Can be kept if values are genuinely shared | Do not let a previous request's value persist unintentionally |
| Accessor/resolver/converter | Can be used as stable configuration | Do not mutate configuration during ongoing evaluations |
| Objects referenced from variables | Depends on the object | Mutable state and sharing across requests |

A common design is to cache the Expression by expression string or rule ID, and then create a new EvaluationContext for each request. This keeps the benefit of parsing once while separating evaluation data.

Do not cache a context containing a request's root object and variables and use it as though it were an immutable Expression.

## 4. Example of stale state when reusing a context

Suppose an expression checks an order total:

~~~text
#root.total >= #minimumTotal
~~~

The application creates the context once:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

Expression expression = parser.parseExpression(
    "#root.total >= #minimumTotal");
~~~

First request:

~~~java
context.setRootObject(orderA);
context.setVariable("minimumTotal", new BigDecimal("100"));

Boolean first =
    expression.getValue(context, Boolean.class);
~~~

Next request:

~~~java
context.setRootObject(orderB);
// Forgot to update minimumTotal.

Boolean second =
    expression.getValue(context, Boolean.class);
~~~

The second evaluation can continue using minimumTotal equal to 100 from the first request. The result appears valid in terms of data type, yet is wrong according to the second request's policy.

This is a subtle bug to detect because the expression does not necessarily throw an exception. It simply uses a stale value still present in the context.

The fix is to create a new context or ensure all required variables are explicitly reset before each evaluation. Creating a new context is usually simpler and less risky.

## 5. Risks of sharing a context across multiple threads

Suppose two requests share one StandardEvaluationContext:

- Request A sets the root object to order A.
- Request B sets the root object to order B.
- Request A starts evaluating the expression.
- Request B updates variables or the root object before A finishes.

If a mutable context is updated concurrently, an evaluation can observe inconsistent state or state belonging to another request. This can lead to wrong results, non-deterministic failures, or cross-request data leakage.

Do not rely on the fact that certain internal operations may be thread-safe to conclude that the entire sequence of updating the root object, variables, and evaluating the expression is an atomic transaction. Reading and writing multiple context values must be coordinated if a single instance is shared.

Safety principles:

- Do not share the same mutable context across multiple requests if each request changes the root object or variables.
- Do not modify variables while another evaluation might be reading them.
- Do not change the root object on a context being used concurrently.
- If a context must be shared, share only stable configuration and do not modify it during evaluation.
- Prefer creating a dedicated context per request or per evaluation.

## 6. Creating a dedicated context for each evaluation

The simplest approach is to create a new context with the current request's root object and variables.

~~~java
public Boolean evaluateOrder(
        Expression expression,
        Order order,
        BigDecimal minimumTotal) {

    StandardEvaluationContext context =
        new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);

    return expression.getValue(context, Boolean.class);
}
~~~

The Expression can be parsed and stored outside the method, while the context is created fresh on every call.

Advantages:

- The root object always belongs to the current request.
- Variables from previous requests do not exist in the new context.
- No synchronization is required when changing the root object or variables across threads.
- Tests can easily build independent data for each evaluation.
- Bugs caused by stale state are easily eliminated.

The cost of creating a context is usually smaller than the cost of diagnosing a hard-to-reproduce state leakage bug. If performance optimization is required, measure with a realistic workload before choosing pooling or sharing mutable contexts.

## 7. Using a factory to hold shared configuration

Creating a new context does not mean re-registering configuration piecemeal in many places. A factory can be used to apply the same set of accessors, resolvers, converters, and functions to each context.

Example:

~~~java
public class SpelContextFactory {

    private final ConversionService conversionService;

    public SpelContextFactory(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public StandardEvaluationContext create(
            Object rootObject,
            BigDecimal minimumTotal) {

        StandardEvaluationContext context =
            new StandardEvaluationContext(rootObject);

        context.setVariable("minimumTotal", minimumTotal);
        context.setTypeConverter(
            new StandardTypeConverter(conversionService)
        );

        return context;
    }
}
~~~

The application calls the factory for each evaluation:

~~~java
StandardEvaluationContext context =
    contextFactory.create(order, minimumTotal);

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

A factory centralizes configuration, while each call still produces a separate context. If functions or PropertyAccessors need to be registered, add them in the factory so every context has consistent configuration.

Dependencies used as shared configuration should be managed with an appropriate Spring lifecycle. Do not store request data or request-specific mutable objects in shared fields of the factory.

## 8. When can the same EvaluationContext be reused?

A context can be reused when evaluations genuinely belong to the same data scope and state does not change unexpectedly.

Examples:

- A batch processing multiple expressions on the same immutable root object.
- A rule set sharing fixed configuration variables.
- A context that has been completely configured and no thread mutates its root object or variables.
- A test intentionally evaluating multiple expressions against the same fixture.

Even in these cases, clearly determine who owns the context and when it expires.

Do not reuse a context just to avoid calling `new`. If each request has a different root object, tenant, user, threshold, or access permission, a dedicated context is usually the right choice.

If a context needs to be reused in a sequential flow, include a complete preparation step before each evaluation:

1. Set the correct root object.
2. Assign all required variables.
3. Handle optional variables according to clear rules.
4. Verify accessor/resolver/converter configuration.
5. Evaluate the expression.
6. Prevent the next evaluation from inheriting unintended data.

Do not rely on "any variable not set will disappear on its own." Treat a used context as retaining state until replaced or discarded.

## 9. State can reside inside passed-in objects

Creating a new EvaluationContext does not automatically make all data independent. The root object or variables can reference a mutable object that is shared elsewhere.

Example:

~~~java
context.setVariable("policy", sharedPolicy);
~~~

If sharedPolicy is modified by another thread, the expression can see the new value even if the context did not change.

Similarly, the root object might hold mutable collections, an entity currently being updated, or a proxy accessing dynamic data.

Therefore, inspect the entire object graph passed in:

- Is the object immutable throughout the evaluation?
- Can internal collections be mutated concurrently?
- Does a variable point to an object shared across multiple tenants or requests?
- Do property getters return mutable data or load data dynamically?
- Does the expression invoke methods that mutate state?

If an expression needs a stable snapshot, create a read-only DTO or a copy of the required data before evaluation. Do not pass a high-privilege object when only a few values are needed.

## 10. Risks of stale data and cross-request leakage

Stale state does not merely cause wrong calculations. If a context retains the root object or variables of a previous request, a subsequent expression may read data belonging to another user or tenant.

Risk examples:

- The currentUser variable still points to the previous user.
- The tenantId variable was not updated, and the rule uses the old tenant.
- The root object is still the entity from the previous request.
- An optional variable was not reset, so it keeps its old value.
- A function or accessor uses a global mutable field to store request data.

This is a data isolation bug. Treat it as a request-boundary and access-control issue, not just an expression logic bug.

Risk mitigation measures:

- Create a dedicated context per request.
- Place only necessary data into the context.
- Populate the root object and variables from authenticated data.
- Avoid storing request-specific state in singletons or static fields.
- Do not share mutable contexts across tenants or users.
- Test two consecutive requests with different data.
- Test concurrent requests with separate root objects and variables.

## 11. Expression caching and context lifecycle

Parsed Expressions can be cached to avoid parsing the same string repeatedly. The cache should store expressions under a stable key such as rule ID plus version or normalized expression content.

Conceptual example:

~~~java
Expression expression = expressionCache.get(ruleId);
~~~

Then, for each evaluation create a new context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(currentOrder);

context.setVariable("minimumTotal", currentMinimum);

Boolean result = expression.getValue(context, Boolean.class);
~~~

Do not put a request's EvaluationContext into a shared cache. Contexts hold state and object references, so caching them can extend data lifetimes, retain unneeded objects, and create cross-request leakage risks.

You must also manage the Expression cache when rules change. If an expression is updated, the cache must be invalidated or versioned so old content is not continuously evaluated.

Expression caching and context creation are two independent decisions:

- Cache Expressions to reduce parsing cost.
- Create new EvaluationContexts to isolate data and state.
- Only share immutable configuration after clearly defining lifecycle and concurrency behavior.

## 12. Common errors and diagnosis

| Symptom | Possible cause | How to address |
|---|---|---|
| Result uses the previous request's threshold | Context variable was not updated | Create a new context or reset all required variables |
| Expression reads the wrong entity | Old root object remains in context | Initialize context with the current root |
| Results vary unpredictably | Multiple threads mutating context | Isolate context per request |
| Data across tenants gets mixed | Context or variable object shared in the wrong scope | Separate contexts and objects per tenant/request |
| Optional variable has an unexpected value | Old state was not cleared or replaced | Define explicit null/missing variable policy |
| Tests pass individually but fail in parallel | Shared mutable context or fixture | Create separate contexts and fixtures per test |
| Memory retains request objects longer than expected | Context cached or held in singleton field | Do not cache contexts; limit reference lifetimes |
| Inconsistent function/accessor configuration | Different places build contexts differently | Use a single context factory |
| New expression still runs old logic | Expression cache not versioned or invalidated | Manage cache by rule version |

When investigating, record the expression ID, request ID, context type, and list of provided variable names. Do not log sensitive values. Compare root types and variable data types across evaluations to identify which state was retained.

## 13. Testing stale state and isolation

An important test is evaluating twice consecutively with different data and verifying that the second result does not depend on the first evaluation's values.

Example using separate contexts:

~~~java
@Test
void createsIsolatedContextForEachEvaluation() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
        parser.parseExpression("#root.total >= #minimumTotal");

    Order firstOrder = new Order(new BigDecimal("150"));
    Order secondOrder = new Order(new BigDecimal("150"));

    StandardEvaluationContext firstContext =
        new StandardEvaluationContext(firstOrder);
    firstContext.setVariable("minimumTotal", new BigDecimal("100"));

    StandardEvaluationContext secondContext =
        new StandardEvaluationContext(secondOrder);
    secondContext.setVariable("minimumTotal", new BigDecimal("200"));

    assertEquals(Boolean.TRUE,
        expression.getValue(firstContext, Boolean.class));

    assertEquals(Boolean.FALSE,
        expression.getValue(secondContext, Boolean.class));
}
~~~

This test uses the same Expression but two independent contexts. The results differ due to each evaluation's data, not due to retained state.

Cases to include:

- Two sequential requests with different root objects.
- Two requests with different variable values.
- A second request omitting an optional variable that the first request provided.
- One evaluation throws an exception and the next evaluation still uses a clean context.
- Multiple concurrent requests with separate contexts.
- Root object or variable referencing mutable collections.
- Functions/accessors registered consistently through a factory.
- Expression cache updated when a rule changes version.
- No request objects retained in singletons or context caches.

If an application intentionally reuses a sequential context, include tests verifying that all state is replaced before each evaluation. Separate isolation tests should still be kept to prove data across requests does not mix.

## 14. Context lifecycle design workflow

When deploying SpEL in an application:

1. **Parse and manage Expressions separately.** Cache expressions by rule ID or version if needed.
2. **Identify per-evaluation data.** List the root object, variables, and referenced objects.
3. **Create separate contexts.** Use a factory to initialize the context with the current request's root object and variables.
4. **Apply shared configuration.** Register necessary accessors, resolvers, converters, and functions.
5. **Do not share mutable state.** Avoid updating the context or input objects while an evaluation is running.
6. **Evaluate and retrieve the result.** Do not retain the context in cache after completion without a clear reason.
7. **Test isolation.** Run sequentially and concurrently with different data.
8. **Track cache lifecycle.** Version Expressions and evict stale entries when rules change.

If performance is a concern, measure parse time, context creation time, and evaluation time separately. Do not optimize by sharing contexts before having measurements and tests proving state is properly isolated.

## 15. Best practices

- Reuse parsed Expressions; manage EvaluationContext according to data lifecycle.
- Create a dedicated context for each request or evaluation with different state.
- Initialize the root object from current data; do not retain the previous request's root.
- Register all required variables before each evaluation.
- Do not assume old variables disappear automatically if not re-set.
- Do not modify the root object or variables while a context is being used concurrently.
- Use a context factory to configure accessors, resolvers, converters, and functions consistently.
- Share only stable configuration; do not share mutable request state.
- Also inspect mutable objects referenced from the root or variables.
- Do not cache an EvaluationContext containing request data.
- Version or invalidate the Expression cache when rules change.
- Test stale state, request isolation, and concurrent evaluations.
- Do not log sensitive values solely to diagnose context state.

## 16. Review checklist

Before approving a SpEL reuse design, check:

- [ ] Expression and EvaluationContext have separate lifecycles.
- [ ] Expression cache does not retain a request's EvaluationContext.
- [ ] Root object belongs to the exact request or batch being processed.
- [ ] All required variables are registered before evaluation.
- [ ] Optional variables have a clear null/missing policy.
- [ ] Old state cannot affect subsequent evaluations.
- [ ] Multiple threads do not mutate a single mutable context.
- [ ] Mutable objects inside root/variables are controlled.
- [ ] Functions and accessors do not store request state in shared fields.
- [ ] Shared configuration is applied through a context factory.
- [ ] Expression cache is versioned and invalidated at the right time.
- [ ] Sequential, concurrent, and cross-request leakage tests exist.

## Conclusion

A parsed Expression can be reused for many evaluations, whereas EvaluationContext can retain the root object, variables, and configuration across calls. If a context is reused without fully replacing state, expressions can read stale data; if multiple threads update a context concurrently, data across requests can mix. A safe design typically caches Expressions separately, creates a new EvaluationContext for each request or evaluation, and uses a factory to apply shared configuration. Test stale state, mutable objects, and concurrent evaluation before optimizing context lifecycles.