# Collection traversal cost and controlling large datasets

## 1. Both selection and projection must traverse data

Spring Expression Language (SpEL) supports two important operations on collections:

- **Selection** filters elements according to a condition.
- **Projection** transforms each element into a value or another structure.

Example:

    members.?[active == true]

The selection expression retains members whose active equals true.

Projection example:

    members.![name]

The projection expression retrieves the name property of each member to create a result collection.

These two operations make expressions concise, yet they still have to process the input data. For a collection with n elements, a typical selection or projection needs to iterate over the relevant elements. Therefore, collection size and the cost of the inner expression largely determine execution time.

SpEL does not automatically turn selection into a database query. If a collection has already been loaded into memory, SpEL iterates over the data currently present in the application.

## 2. Basic complexity

Suppose the collection has n elements.

| Operation | Main work | Typical complexity |
| --- | --- | --- |
| Selection of all matching elements | Evaluates condition on each element | O(n) |
| Projection | Evaluates expression for each element | O(n) |
| Select first | Finds the first matching element | O(n) in the worst case |
| Select last | Finds the last matching element | O(n) |
| Accessing one element by List index | Accesses element by position | Usually O(1) for ArrayList; depends on collection type |

Example:

    members.?[active == true]

If the collection has 100 elements, the condition may be evaluated up to about 100 times.

If the collection has 100,000 elements, the number of checks increases accordingly. Using a shorter SpEL syntax does not reduce the number of elements that must be checked.

This is a cost model for design analysis. Actual runtime also depends on the collection type, property accessors, data types, condition contents, and the cost of methods invoked in the expression.

## 3. Cost of the selection condition

Each element examined by selection is checked using the expression inside square brackets.

Example:

    orders.?[total >= 1000]

A simple condition only reads the total property and compares it to a literal. If the collection has n orders, SpEL must evaluate the condition across those elements.

A more complex condition:

    orders.?[
        customer.account.manager.department.name == 'Sales'
    ]

may have to traverse multiple intermediate properties for each order.

If the property path has many levels, the cost of access and null checks can be higher than a condition reading a single simple field.

A condition with a method call:

    orders.?[customer.isEligible()]

can take significantly longer if isEligible performs computation or accesses a service. If that method calls a database or an external API, the cost can rise sharply because it is executed repeatedly for each element that must be checked.

Rule of thumb: keep predicates simple, predictable, and avoid I/O operations inside selection.

## 4. Cost of projection

Projection produces one result value for each source element.

Example:

    members.![name]

With n members, SpEL needs to evaluate the name expression on each member and create the corresponding result collection.

If projection performs a calculation:

    orders.![total * taxRate]

each element needs to read total, read taxRate, and compute the result.

If projection calls a method:

    members.![getDisplayName()]

the method is called for every element processed. Consider the cost of that method before using it on large collections.

Projection typically creates a result collection in memory. Therefore, beyond traversal time, the application also pays the cost of allocating and storing the resulting values.

If you only need to check a condition or get a single property, avoid creating an intermediate projection and then iterating over the result again if the goal can be expressed directly in one expression or clearer Java code.

## 5. Combining selection and projection

A common flow is filtering data and then extracting a piece of information:

    members.?[active == true].![name]

With this notation, SpEL performs two tasks:

1. Iterates over the collection to find active members.
2. Iterates over the matching elements to extract name.

If n is the number of input elements and k is the number of selected elements, the amount of processing can be pictured as n + k. Since k is at most n, overall complexity remains O(n), but there is additional cost to create both the selection collection and the projection collection.

With large data, intermediate collections can increase memory usage.

If you only need the list of names of active members, the combined expression remains easy to read. But if multiple steps, multiple conditions, or multiple transformations are needed, measure the actual cost and consider implementing it with a Java Stream or a dedicated data query.

Do not conclude that a long expression chain is always faster than an equivalent Java snippet. Compare on real data and in a real environment.

## 6. Nested selection can increase cost rapidly

Suppose each department has a list of employees. You might write:

    departments.?[
        employees.?[active == true].size() > 0
    ]

If there are d departments and each department has m employees on average, the expression may have to traverse nearly d × m employees to check the condition.

Complexity can be approximated as:

    O(d × m)

If another collection is nested further, the number of operations can continue multiplying.

Example:

    departments.?[
        teams.?[
            members.?[active == true].size() > 0
        ].size() > 0
    ]

This expression traverses multiple collection levels. With large datasets, the number of predicate evaluations can grow substantially.

Clearly identify:

- How many elements does the outer collection have?
- What is the size of the child collection inside each element?
- How many levels of selection or projection are there?
- Does the inner predicate call expensive methods or access costly properties?

If a nested expression makes traversal counts hard to estimate, split the logic into steps that can be measured and tested independently.

## 7. Select first and select last

SpEL provides specialized selection forms:

    members.^[active == true]

Selects the first matching element.

    members.$[active == true]

Selects the last matching element.

These two forms are useful when only one result is needed instead of the entire filtered collection.

Select first can stop once the first matching element is found; in the case where no element matches, it still must examine the whole collection. Select last needs to keep checking to determine the last matching element.

Therefore:

- If only the first matching element is needed, use select first instead of full selection followed by index 0.
- If the last matching element is needed, use select last instead of creating the full selection result and taking the last element.
- If all results are needed, use standard selection.

Example:

    members.^[active == true]

directly expresses the goal of getting a single first matching element.

Do not create an intermediate collection just to take one element when a SpEL operator directly expresses the intent.

## 8. Memory cost and result collections

Selection and projection can create new collections. Result size depends on the operation:

- Selection creates a result containing elements satisfying the condition.
- Projection creates a result containing values computed for each source element.
- Select first and select last only need to return a single result or null.

If selection retains k elements, additional memory is generally proportional to k. If projection creates one value per element, result memory is generally proportional to n.

When an expression performs both selection and projection, an intermediate collection and a final collection may both exist. For large datasets, consider peak memory as well as runtime.

Example:

    members.?[active == true].![name]

may create a collection containing matching members, then create a collection of names. If the number of members is large, two collections can increase memory pressure during evaluation.

If you only need to count or check existence, avoid materializing the entire result when a better-suited approach for the goal can be used.

## 9. SpEL does not replace database queries

A common design mistake is loading all data first and only then using SpEL to filter:

    allOrders.?[status == 'PAID']

If allOrders contains hundreds of thousands of orders, the application still has to:

1. Read the data from the database.
2. Create or hold the collection in memory.
3. Traverse the elements with SpEL.
4. Create the result collection.

SpEL selection does not automatically translate into SQL WHERE, does not automatically add database indexes, and does not automatically paginate data.

For large datasets, push filtering conditions down to the storage layer if business logic permits:

    SELECT *
    FROM orders
    WHERE status = 'PAID'
    LIMIT 100;

The database can leverage indexes, the query planner, and result limits. Then SpEL only processes the narrowed dataset if dynamic expressions are still needed.

Separate responsibilities:

- Database: filtering, sorting, pagination, and fetching only required fields.
- Service: authorization checks, orchestration, and applying business rules.
- SpEL: evaluating rules or expressions on an appropriately narrowed dataset.

## 10. Limiting data with pagination and query-level projection

When the full dataset is not needed, query by page:

    Page<Order> page =
        orderRepository.findByStatus(
            OrderStatus.PAID,
            PageRequest.of(0, 100)
        );

Only then apply SpEL on the page's content if needed.

Example:

    List<Order> eligible = parser
        .parseExpression("?[total >= #minimum]")
        .getValue(context, page.getContent(), List.class);

The example above is only meant to illustrate limiting the input collection. In a real application, you can filter via a repository or Java before calling SpEL, depending on the API and data type.

If only a few properties are needed, use a DTO or query projection so the database returns just the required columns instead of loading the entire entity graph.

Be careful with lazy loading: if a predicate accesses an unloaded relationship, each element may trigger an additional query. This is an N+1 query situation that can drive up cost dramatically even though the expression looks very short.

Inspect the actual SQL and query counts when selection/projection accesses ORM relationships.

## 11. Parse once, evaluate many times

Do not create a parser and re-parse the same string inside every loop iteration if the expression does not change.

Wasteful approach:

    for (Order order : orders) {
        Expression expression =
            new SpelExpressionParser()
                .parseExpression("total >= 1000");

        boolean eligible =
            expression.getValue(order, Boolean.class);
    }

Better approach:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("total >= 1000");

    for (Order order : orders) {
        boolean eligible =
            expression.getValue(order, Boolean.class);
    }

Parsing builds the expression structure. Keeping the Expression lets you reuse the parsing result and avoid repeating that work.

If the expression has variables, pass an appropriate EvaluationContext for each evaluation. Do not put one request's data into a context shared with another request without safely controlling state and concurrency.

Parse-once does not eliminate collection traversal or evaluation cost. It only avoids repeated parsing cost.

## 12. Keep predicates simple and avoid side effects

Selection and projection invoke expressions repeatedly across many elements. Therefore, predicates and projections should have clear, predictable behavior.

Prefer:

    orders.?[status == 'PAID' and total >= #minimum]

Be cautious with:

    orders.?[customer.loadLatestStatus() == 'ACTIVE']

If loadLatestStatus calls a database or API, it may be executed many times. A large collection can lead to a very large number of calls.

Do not use methods with side effects inside a predicate, such as updating state, sending messages, or writing business logs as a required part of filtering. Selection's purpose is choosing elements; it is not a side-effect orchestration mechanism.

If data must be enriched from an external source, do so in the service using appropriate batching or caching, then pass the results into the expression context.

## 13. Controlling EvaluationContext and property access

Evaluation cost also depends on how SpEL locates and reads data.

Factors that can affect it:

- PropertyAccessor must resolve properties on objects.
- MethodResolver may have to look up matching methods.
- TypeConverter may convert types during evaluation.
- Variables and functions are looked up in EvaluationContext.
- Nested properties can lead to multiple accesses per element.

For an expression evaluated many times, using an appropriate context and accessors can affect performance.

However, do not broaden access permissions just to make an expression work. For expressions supplied by users or external configuration, restrict objects, variables, property accessors, and method resolvers strictly according to business needs.

Performance optimization must preserve necessary access restrictions.

## 14. Compiler and performance optimization

SpEL has a compiler with modes such as OFF, IMMEDIATE, and MIXED. The compiler can improve speed for suitable expressions and data types.

However, not every expression can be compiled. Expressions depending on varying data types, custom accessors, or complex structures may not be suitable for the compiler.

Do not enable the compiler just because a collection is large. First identify whether the time-consuming part is:

- Repeated parsing.
- Collection traversal.
- Property or method access.
- Database queries triggered inside the predicate.
- Result collection allocation.
- Type conversion or business logic.

After measuring, test a compiler mode on a representative workload and compare results. The compiler cannot substitute for reducing input data size or eliminating repeated I/O.

## 15. Measure instead of guessing

When optimizing selection/projection, measure on data whose size and distribution are close to the real environment.

Track:

- Number of input elements.
- Number of selected elements.
- Parse time and evaluation time separately.
- Predicate time per element.
- Number of method calls or database queries.
- Extra memory caused by result collections.
- SQL query count and N+1 occurrences.
- Average latency and high percentiles under concurrency.

A small benchmark can be used to compare expressions:

    ExpressionParser parser = new SpelExpressionParser();

    Expression selection =
        parser.parseExpression("?[active == true]");

    long start = System.nanoTime();

    List<?> result = selection.getValue(
        context,
        members,
        List.class
    );

    long elapsed = System.nanoTime() - start;

    System.out.println("Matched: " + result.size());
    System.out.println("Elapsed ns: " + elapsed);

The snippet only illustrates timing a single run. For reliable benchmarks, warm up the JVM, run multiple iterations, use representative data, and avoid interference from logging or other tasks. JMH is better suited for microbenchmarks needing accurate comparison.

## 16. Checklist when handling large collections

Before using selection or projection on a large collection, check:

1. Does the input collection really need to be loaded in full?
2. Can filtering or pagination be done at the database or repository layer?
3. Does the predicate call expensive methods or trigger I/O?
4. Can the expression be parsed once and reused?
5. Is the entire result collection needed, or only the first matching element?
6. Does projection create unnecessary intermediate collections?
7. Is there nested selection/projection causing traversal counts to multiply?
8. Do ORM relationships cause N+1 queries?
9. Can only the required fields be fetched using a DTO?
10. Have time and memory been measured on representative data?

There is no single element-count threshold for every application. A collection of 10,000 elements with a simple predicate can be lighter than 100 elements where each element calls multiple external APIs.

Base decisions on per-element cost and system resource limits.

## 17. Key points to remember

- Selection and projection are in-memory collection traversal operations.
- Full selection typically has O(n) complexity; projection is also typically O(n).
- Select first can stop at the first match; in the worst case it still has to traverse the entire collection.
- Select last needs to find the last match, so it must inspect the collection.
- Predicates or projections with expensive methods multiply cost by the number of processed elements.
- Selection/projection can allocate result collections and increase memory usage.
- Nesting multiple collections can increase traversal counts by the product of the sizes of each level.
- SpEL does not automatically translate selection into SQL or paginate the database.
- Filter and limit data at the repository/database before using SpEL when appropriate.
- Parse expressions once and reuse them when the source expression does not change.
- Avoid I/O and side effects inside predicates.
- Measure time, memory, and query counts before optimizing compiler settings or expression structure.

SpEL is well suited for expressing rules and processing reasonably bounded collections. For large datasets, control input size, traversal count, per-element cost, and result collections before deciding between using an expression or pushing processing down to the query layer.
