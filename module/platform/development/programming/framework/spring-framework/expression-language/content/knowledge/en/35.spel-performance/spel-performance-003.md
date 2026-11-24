# Cost of EvaluationContext and Object Graphs in SpEL

The performance of Spring Expression Language (SpEL) depends on several steps: parsing the expression, preparing the EvaluationContext, resolving properties and methods, and executing operations on the object graph. When an expression is evaluated many times, the cost of repeatedly creating a context or re-parsing the same string can become significant. When the object graph is large or the expression traverses collections, data access and intermediate result creation typically account for most of the work.

Proper optimization requires separating these costs. Parse expressions once when possible, provide only the context capabilities needed, manage the context according to the appropriate request scope, and write expressions that only access the parts of the object graph actually required. For large collections or complex nested logic, consider moving that processing to Java.

## 1. Components That Make Up Evaluation Cost

A single SpEL evaluation can involve the following work:

1. **Parse expression:** convert the expression string into an Expression object and internal structure.
2. **Prepare EvaluationContext:** provide the root object, variables, functions, property accessors, method resolvers, type converter, bean resolver, and related strategies.
3. **Resolve property or method:** find how to read a property or invoke a method on the current object.
4. **Traverse the object graph:** follow nested properties, collection elements, or Map keys.
5. **Execute operations and conversions:** perform comparisons, calculations, or invoke converters or operators.
6. **Create results:** create intermediate Strings, collections, or objects if requested by the expression.

Not every expression performs all of these steps. For example, a comparison on a simple variable involves less work than an expression that calls a bean method, accesses multiple nested properties, and then filters a collection.

When optimizing, identify which step is taking actual time instead of just looking at the length of the expression string.

## 2. Cost of Creating and Configuring EvaluationContext

EvaluationContext provides the environment an expression uses during evaluation. It not only holds the root object, but can also hold variables, functions, property accessors, method resolvers, a bean resolver, a type locator, a type converter, and an operator overloader.

### 2.1. StandardEvaluationContext

StandardEvaluationContext provides the full set of SpEL capabilities and default reflection-based strategies. It is suitable when expressions need property access, method invocation, bean references, type references, or other extended features.

Example:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumTotal", minimumTotal);
context.setBeanResolver(new BeanFactoryResolver(beanFactory));
~~~

If every evaluation creates a new context and re-registers the same set of accessors, resolvers, or functions, the application repeats configuration work.

When configuration is stable, extract context initialization into a factory/helper to reduce duplicate code and ensure contexts are created consistently. Whether to reuse the same context instance or create a new context for each processing execution depends on mutable data and the application's concurrency scope.

### 2.2. SimpleEvaluationContext

SimpleEvaluationContext provides only a subset of SpEL features. You can choose read-only data binding, read-write data binding, or configure permitted property accessors and instance methods.

Example:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

If an expression only needs to read properties, SimpleEvaluationContext can help restrict access capabilities and reduce unnecessary configuration. However, do not assume it is always faster across all workloads. Choose the context based on required features and measure performance with real data.

SimpleEvaluationContext does not support bean references, type references, or constructor invocation. If an expression needs those features, a more suitable context must be chosen.

### 2.3. Do Not Register Unused Capabilities

Each configured resolver or accessor can affect the resolution process. Only register what the expression needs:

- Do not add a BeanResolver if the expression does not reference beans.
- Do not enable instance method invocation if the expression only reads properties.
- Do not add a custom PropertyAccessor if the default accessor already suffices.
- Do not register converters or functions just in case there is a future need.

Limiting configuration keeps the context easier to understand and reduces unnecessary processing paths.

## 3. Reusing Parsed Expressions

In a repetitive processing flow, do not parse the same expression string in every loop iteration.

Example to avoid:

~~~java
for (Order order : orders) {
    Expression expression =
            parser.parseExpression("total * #taxRate");

    BigDecimal total = expression.getValue(
            context,
            order,
            BigDecimal.class
    );
}
~~~

You can parse once and reuse:

~~~java
Expression expression =
        parser.parseExpression("total * #taxRate");

for (Order order : orders) {
    BigDecimal total = expression.getValue(
            context,
            order,
            BigDecimal.class
    );
}
~~~

The Expression retains the parsed structure. Each call to getValue() still evaluates with the passed-in context and root object, but the application does not have to repeat the string parsing step.

If an expression is used in multiple places, parsing can be placed in a registry or cache keyed by rule name.

### 3.1. Caching Expressions by Content and Parsing Configuration

An expression cache should account for factors that affect the parsing result:

- Expression content.
- Associated parser or parser configuration.
- ParserContext if the expression is a template or uses custom delimiters.
- Other parsing options of the application.

Do not use an unbounded cache for user-submitted expression strings. If input can grow continuously, the cache needs a size limit or time-to-live to avoid retaining too many Expressions in memory.

For expressions from untrusted sources, beyond cache bounds, syntax and EvaluationContext permissions also need to be restricted. Caching is not a security measure.

### 3.2. Do Not Cache Results If Input Data Changes

Reusing an Expression is different from caching evaluation results.

Example expression:

~~~text
#order.total * #taxRate
~~~

The result depends on the evaluation's order and taxRate. If results are cached without a key covering all affecting data, the application may return stale values.

Only cache results when data immutability is clearly established, the cache key covers all relevant inputs, and an appropriate expiration is set.

## 4. Create a New EvaluationContext or Reuse It?

There are two groups of data in a context:

- **Relatively stable configuration:** property accessors, method resolvers, bean resolver, type converter, and functions.
- **Per-execution data:** root object, variables such as currentUser, order, or request.

Repeated work can be reduced by grouping configuration into a factory. However, a context typically has mutable state: the root object and variables can be changed via setters.

### 4.1. Creating a Context per Request or Unit of Work

An easily controllable pattern is to parse the Expression once, then create a separate EvaluationContext for each request or unit of work:

~~~java
Expression expression =
        parser.parseExpression("total >= #minimumTotal");

StandardEvaluationContext createContext(
        Order order,
        BigDecimal minimumTotal) {

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);

    return context;
}
~~~

This keeps data from different executions isolated. It is especially useful when multiple requests run concurrently and each request has a different root object or variables.

### 4.2. When Can a Context Be Reused?

Reusing a context can be considered when:

- Access strategies do not change.
- Data in the context is not shared across independent executions.
- The root object and variables are updated in a controlled manner.
- No two concurrent threads read/write different mutable values in the same context.

Do not share a single mutable StandardEvaluationContext across multiple concurrent requests if each request needs its own root object or variables. One request can overwrite a variable while another request is evaluating, leading to wrong results.

If configuration needs to be shared, create separate contexts from a factory for each processing unit rather than sharing a single mutating instance.

## 5. Property and Method Access Cost

The expression:

~~~text
#order.customer.address.city
~~~

has multiple consecutive access steps:

1. Read order.
2. Read customer.
3. Read address.
4. Read city.

Each step requires an appropriate property access mechanism. With StandardEvaluationContext, default accessors typically use reflection to access properties. Method invocation also requires a resolver to locate the method and determine how arguments are passed.

The more access steps or method calls an expression has, the more work needs to be performed. However, depth is not the only factor: a getter can contain logic that takes far more time than property resolution itself.

### 5.1. Avoid Getters That Perform Heavy Work

A getter can query a database, call an API, perform large computations, or trigger lazy loading. SpEL calls the getter as part of property access; it does not know that the getter has a high cost.

Example:

~~~text
#order.customer.accountManager.department.name
~~~

If a getter in the chain triggers a data query, even a short expression can cause significant I/O.

Prefer passing into the context DTOs or pre-prepared objects with the values the expression needs. Do not put database queries or network calls inside getters just so an expression can read a property.

### 5.2. Avoid Calling the Same Expensive Calculation Repeatedly

If multiple parts of an expression call an expensive method, that method may be executed multiple times.

Example:

~~~text
#order.calculateShippingCost() + #order.calculateShippingCost()
~~~

If the method has no internal cache, the expression calls it twice. You can precompute it in Java and register the result:

~~~java
context.setVariable(
        "shippingCost",
        order.calculateShippingCost()
);
~~~

Expression:

~~~text
#shippingCost * 2
~~~

Only pass precomputed results into the context when semantics allow sharing a single value within that processing execution.

## 6. A Large Object Graph Does Not Mean SpEL Automatically Traverses the Entire Graph

SpEL only executes the access paths and operations requested by the expression. Having hundreds of properties or many relationships on the root object does not mean every evaluation automatically reads all of them.

Example:

~~~text
#order.customer.name
~~~

only requires following the path to customer and then name. Other branches of the object graph are not traversed simply because they exist.

Cost increases when the expression:

- Traverses many nested properties.
- Accesses large collections.
- Calls getters with side effects or data loading.
- Uses multiple nested selections/projections.
- Creates many intermediate collections or objects.

Therefore, evaluate the graph based on actual access paths, number of elements traversed, and getter behavior, rather than just looking at the total number of properties on the root object.

## 7. Selection and Projection on Collections

Selection and projection can be useful, but their cost depends on the number of elements and the complexity of the expression applied to each element.

Selection example:

~~~text
#orders.?[total >= #minimumTotal]
~~~

SpEL must evaluate the condition across the elements of the collection. With N elements and a nearly constant-cost condition, the work scales with N.

Projection:

~~~text
#orders.![total * #taxRate]
~~~

performs the transformation for each element and creates a result collection.

### 7.1. Intermediate Collections and Multiple Passes

An expression combining selection and projection:

~~~text
#orders.?[total >= #minimumTotal].![total * #taxRate]
~~~

needs to filter elements and then create the projection result. Using multiple collection operators can create intermediate collections and add memory allocation cost.

For large collections, measure both execution time and allocation volume. If logic involves multiple steps, multiple conditions, or needs data-flow optimization, Java Streams or Java loops may be easier to control.

### 7.2. Avoid Unnecessary Nested Selection

Example of a collection nested inside each other element:

~~~text
#departments.?[
    employees.?[active].size() > 0
]
~~~

If there are D departments and each department has an average of E employees, the expression may have to check a number of elements proportional to D times E.

When data is large, consider precomputing the condition state in Java or creating a DTO containing aggregated information. Do not use nested expressions to replace a query or data aggregation that can be performed more efficiently at the appropriate layer.

## 8. Lazy Loading and the N+1 Query Risk

In applications using an ORM, a getter on an association can trigger lazy loading. An expression such as:

~~~text
#orders.![customer.address.city]
~~~

may access customer and address for each order. If the associations have not been loaded, each access can issue additional queries.

This is the familiar N+1 query risk:

- One query fetches the list of orders.
- Then many queries are issued as the expression reads each order's associations.

SpEL does not batch those queries automatically. It simply invokes the property accessor or getter on the provided objects.

How to handle it:

1. Preload required data using fetch joins, entity graphs, or projections appropriate for the ORM in use.
2. Transform data needed for display into DTOs before evaluating.
3. Avoid accessing unnecessary association properties inside selection/projection.
4. Monitor SQL query counts in integration tests or a profiler.
5. Push large aggregations down to the database when that is the appropriate place to process them.

Do not optimize SpEL time alone if the primary cost comes from the database or lazy loading.

## 9. Choosing Appropriate Root Objects and Variables

The root object and variables determine what an expression can access.

An overly large root object or one containing many associations can make it easy for expressions to accidentally access unnecessary branches. A small DTO containing just the needed properties usually makes expressions easier to understand and predict.

For example, instead of passing a complex entity graph:

~~~java
context.setRootObject(orderEntity);
~~~

you can create dedicated input data:

~~~java
context.setRootObject(new OrderSummary(
        order.getId(),
        order.getCustomer().getDisplayName(),
        order.getTotal()
));
~~~

Expression:

~~~text
id + ' - ' + customerName + ' - ' + total
~~~

DTOs help bound the object graph visible to the expression and avoid unnecessary getters. The cost of creating DTOs also needs to be accounted for in benchmarks, but in return the access flow is clearer.

Variables are suitable for passing per-execution values such as threshold, locale, or feature flags. Do not put the entire application context or a service locator into a variable just so expressions can access anything arbitrarily.

## 10. Optimizing with Custom PropertyAccessors or Resolvers

If profiling shows property access cost is a bottleneck, you can consider a specialized PropertyAccessor for frequently used data types.

A custom accessor can provide a clearer way to read properties for a special domain structure. However, writing custom accessors also adds code to maintain and can alter access semantics.

Only customize when:

- Profiling identifies property resolution as a significant cost.
- The data structure has stable access rules.
- The default accessor is unsuitable or insufficiently efficient.
- Tests verify correct types, null behavior, and access errors.

Similarly, custom MethodResolvers, BeanResolvers, or TypeConverters can add processing steps. Do not add resolvers merely hoping for a speedup if no benefit has been measured.

## 11. Compiled Expressions and Context Cost

The SpEL compiler can improve execution speed for certain frequently evaluated expressions. However, the compiler does not eliminate the cost of creating an EvaluationContext, preparing variables, calling services, or loading data from the object graph.

Some expression forms currently do not support compilation, such as selection/projection, bean references, assignments, and certain cases requiring custom resolvers or a ConversionService. These expressions may still run in interpreted mode.

If considering the compiler:

- Verify that the expression falls into a supported category in the Spring version being used.
- Check that root object and property types are stable across evaluations.
- Measure parsing, context initialization, and evaluation time together.
- Avoid side effects in expressions that may fall back/retry in MIXED mode.
- Do not enable the compiler merely because an expression is long or evaluated frequently.

Compiled mode can reduce part of the interpreter cost, but it cannot fix an object graph with overly expensive getters or an expression causing N+1 queries.

## 12. Measuring Performance Properly

Do not decide on optimizations based solely on intuition or a single run. Measure components with a workload close to the real environment.

A benchmark can separate:

1. Expression parsing time.
2. EvaluationContext creation and configuration time.
3. Evaluation time with a small root object.
4. Evaluation time with a deep object graph.
5. Selection/projection time on collections of varying sizes.
6. Getter/method invocation counts and database query counts if an ORM is involved.
7. Allocation volume of intermediate collections or objects.

JMH is suitable for Java microbenchmarking. For applications with databases, proxies, or lazy loading, integration tests and a profiler are needed to measure both I/O and query counts.

In benchmarks, be sure to:

- Warm up the JVM before collecting metrics.
- Use the same input data when comparing approaches.
- Measure multiple iterations and inspect result distributions, not just a single value.
- Separate parse cost from evaluation if the goal is to measure a hot loop.
- Compare interpreted and compiled only for expressions supported by the compiler.
- Keep context configuration equivalent across options.
- Verify the returned result to avoid benchmarking a meaningless computation.

## 13. Practical Optimization Checklist

When an expression runs slowly, consider in order:

1. Parse the expression once and reuse the Expression.
2. Do not create a new context inside a loop if it can be prepared once for the processing unit.
3. Create a separate context per request or task when variables/root objects differ.
4. Only register necessary resolvers, accessors, and functions.
5. Reduce repeated property access steps.
6. Precompute expensive methods/getters and pass results via variables when appropriate.
7. Use small DTOs or projections instead of passing an overly broad entity graph.
8. Reduce nested selection/projection on large collections.
9. Check for lazy loading and N+1 queries.
10. Only write custom accessors or resolvers after profiling identifies the bottleneck.
11. Consider compiled mode when the expression is supported and data types are stable.
12. Re-measure after every change to confirm the benefit and detect costs shifting elsewhere.

## 14. Example: Parse Once, Context per Execution

The following example separates the parsed expression from each order's data:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("total >= #minimumTotal");

boolean isEligible(
        Order order,
        BigDecimal minimumTotal) {

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);

    return Boolean.TRUE.equals(
            expression.getValue(context, Boolean.class)
    );
}
~~~

In the example, the Expression is parsed once and can be reused. Each call to isEligible() creates a context with the corresponding root object and threshold.

If profiling shows context creation is a significant cost, benchmark an alternative with stable configuration and controlled mutable state. Do not switch to sharing a global context if doing so causes requests to overwrite each other's root objects or variables.

## 15. Quick Takeaways

- SpEL cost consists of parsing, creating EvaluationContext, resolving properties/methods, traversing the object graph, and creating results.
- Parse Expressions once and reuse them on hot paths.
- Create contexts per request or unit of work when root objects and variables differ.
- Do not share a mutable EvaluationContext across concurrent requests with separate data.
- Only register resolvers, accessors, functions, and converters that the expression needs.
- SimpleEvaluationContext has a smaller feature set; choose based on access requirements and measure in practice.
- SpEL only traverses access paths requested by the expression; it does not automatically scan the entire object graph.
- Deep property chains, expensive getters, and methods with side effects can slow down evaluation.
- Selection/projection traverses collections and can create intermediate collections; cost grows with the data processed.
- Getters accessing ORM associations can trigger lazy loading and N+1 queries.
- Small DTOs or projections help limit the object graph and make input data predictable.
- The compiler does not eliminate context, getter, service, or database costs.
- Use a profiler/JMH and integration tests to pinpoint bottlenecks before optimizing.

## 16. Official References

- [Spring Framework — EvaluationContext and Expression Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework — Collection Selection and Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
