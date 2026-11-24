# Do Not Hide Side Effects Inside Expressions

Spring Expression Language (SpEL) allows reading properties, performing calculations, calling methods, invoking functions, referencing beans, and even assigning values. Therefore, an expression can do more than produce a value: it can mutate object state, write data, or trigger external actions.

In a good design, expressions should clearly convey a declarative purpose: reading data, checking conditions, or computing a result. Actions with side effects such as saving to a database, sending emails, charging payments, publishing messages, or updating state should reside in Java services with explicit execution flows.

Do not hide side-effecting actions inside an expression that looks like a simple calculation. An expression may be evaluated multiple times, run on every element of a collection, be invoked inside an annotation, or be re-executed when an error occurs in compiled mode. If readers do not realize a method mutates state, the application can easily produce duplicate actions or become hard to trace.

## 1. What Is a Side Effect?

A computation is considered to have a side effect when, in addition to returning a result, it mutates state or creates an observable effect outside that computation.

Examples of common side effects:

- Modifying a field or property of an object.
- Writing or deleting data in a database.
- Sending an email, SMS, webhook, or message to a broker.
- Processing a payment, refund, or balance update.
- Writing files, calling APIs, or modifying external systems.
- Modifying shared state, caches, or static variables.
- Publishing events or creating audit records.

A method can return a boolean or String and still produce side effects. The return type does not tell whether a method is pure.

For example:

~~~java
boolean isEligible(Order order) {
    auditService.recordEligibilityCheck(order.getId());
    return order.getTotal().compareTo(limit) >= 0;
}
~~~

The name isEligible sounds like a read-only check, yet the method also records an audit entry. If an expression calls this method multiple times, audit records may be created multiple times.

Inspect the actual behavior of methods and getters, rather than relying only on names or return types.

## 2. Expressions Should Represent Reads and Calculations

A pure expression typically has the following traits:

- Reads data from the root object or variables.
- Performs comparisons, calculations, or transformations without altering external state.
- Returns the same result when inputs do not change.
- Does not depend on previous call order or hidden state.
- Can be re-evaluated without triggering additional actions.

For example:

~~~text
#order.total >= #minimumTotal
~~~

The expression only reads total and compares it with minimumTotal.

A calculation example:

~~~text
#order.subtotal * (1 + #taxRate)
~~~

If the properties being read do not cause side effects, the expression only produces a new value.

In contrast, the following expressions can mutate state:

~~~text
#order.status = 'APPROVED'
~~~

Or:

~~~text
@paymentService.charge(#order.account, #order.total)
~~~

These two expressions perform actions. They need to be recognized as commands or state-mutating operations, and should not be mixed into an expression meant solely for display or condition checking.

## 3. Method Invocation Can Produce Side Effects

SpEL allows invoking methods on objects:

~~~text
#order.calculateTotal()
~~~

or invoking methods on Spring beans:

~~~text
@orderService.approve(#order)
~~~

SpEL does not automatically distinguish pure methods from side-effecting methods. It calls methods according to the access capabilities configured in the EvaluationContext.

A pure method may be suitable:

~~~java
public BigDecimal calculateTax(BigDecimal subtotal, BigDecimal rate) {
    return subtotal.multiply(rate);
}
~~~

A method with side effects:

~~~java
public void approve(Order order) {
    order.setStatus(OrderStatus.APPROVED);
    orderRepository.save(order);
    eventPublisher.publishEvent(new OrderApproved(order.getId()));
}
~~~

If you need to evaluate a condition, use a read-only method such as canApprove(order). After the condition is confirmed, call approve(order) from the service or application workflow.

Do not use side-effecting methods in keys, conditions, message templates, or expressions that may be re-evaluated without the caller realizing it.

## 4. Getters Can Also Have Side Effects

Property access in SpEL typically goes through PropertyAccessor and can invoke Java getters. A getter is not guaranteed to be a pure read operation.

For example:

~~~java
public Customer getCustomer() {
    accessCounter++;
    return customerRepository.load(customerId);
}
~~~

The expression:

~~~text
#order.customer.name
~~~

can invoke getCustomer() while accessing the property. If the getter queries a repository or increments accessCounter, reading the property has already produced an effect.

Cases to watch out for:

- Getters triggering ORM lazy loading.
- Getters querying a database or calling an API.
- Getters updating a cache or internal state.
- Getters writing logs/audits per invocation.
- Getters performing expensive calculations or returning results that vary over time.

Keep getters simple and predictable. Place queries, updates, and system coordination in service methods whose names clearly express the action.

If an expression needs preloaded data, prepare a DTO or view model in Java and pass it into the EvaluationContext.

## 5. Registered Functions Are Not Automatically Pure Either

SpEL allows registering a Java Method as a function:

~~~java
context.registerFunction("normalizeCode", normalizeMethod);
~~~

Expressions call the function using the syntax:

~~~text
#normalizeCode(#rawCode)
~~~

Functions usually fit pure transformations such as string normalization, format checking, or calculations. However, registering a method as a function does not guarantee the method has no side effects.

Example of a function that should not be used in an expression that may be evaluated repeatedly:

~~~java
public static boolean sendReminder(Order order) {
    mailClient.send(order.getCustomerEmail(), "Reminder");
    return true;
}
~~~

Expression:

~~~text
#sendReminder(#order)
~~~

The function name and boolean return type do not make sending an email safe when evaluated multiple times.

Register only functions whose behavior matches the expression's purpose. When an action is needed, call a service method at a clear orchestration point.

## 6. Bean References Do Not Make Methods Safe

Bean references use the syntax:

~~~text
@beanName
~~~

For example:

~~~text
@pricingService.calculate(#order)
~~~

Spring-managed beans may hold repositories, clients, or dependencies with side effects. Calling a method via a bean reference does not change the method's semantics and does not automatically create a transaction boundary for the expression.

If the returned bean is a Spring proxy, the method invocation may pass through the proxy according to application configuration. However, SpEL does not open transactions on its own, does not guarantee safe retries, and does not manage business workflows.

Call bean methods inside expressions only when the method has appropriate behavior, typically reads or calculations. Keep writes and actions outside expressions.

## 7. Assignment Is an Explicit Side Effect

SpEL supports assignment in contexts that allow writes:

~~~text
#customer.name = 'Linh'
~~~

Or assigning a property on the root object:

~~~text
status = 'APPROVED'
~~~

Assignment mutates the evaluated object. This is a direct side effect and can affect subsequent parts of the expression or other components holding the same reference.

Some contexts restrict write capability, such as a SimpleEvaluationContext configured as read-only. However, using a read-only context does not guarantee every called method is pure; methods or getters can still produce their own side effects.

If the goal is to update an object from input data, consider doing so with Java setters or a mapper in a clearly named step. Use SpEL assignment when data binding is the intended goal and write scope is controlled.

## 8. Selection and Projection Can Invoke Logic Multiple Times

SpEL provides collection operators:

- **Selection** .?[...] filters elements by a condition.
- **Projection** .![...] transforms each element into a new result.

For example:

~~~text
#orders.?[total >= #minimumTotal]
~~~

The condition is evaluated on every element inspected.

Projection:

~~~text
#orders.![#formatter.format(#this)]
~~~

The expression inside projection is evaluated for each element.

If a method inside the condition or projection has side effects, it may be called many times:

~~~text
#orders.?[@auditService.recordAndCheck(#this)]
~~~

For a collection with N elements, the method can be called up to N times in a single evaluation. If the expression is evaluated again, the invocation count increases further.

Do not use selection/projection to send notifications, write audits, persist data, or mutate state. Use them for filtering and transforming values; perform actions in Java loops/services once elements and processing policies are clearly determined.

## 9. Short-Circuiting and Conditional Branches

Some SpEL logical operators exhibit short-circuit behavior. With and, if the left-hand side is false, the right-hand side does not need to be evaluated. With or, if the left-hand side is true, the right-hand side does not need to be evaluated. The ternary operator evaluates only the selected branch.

For example:

~~~text
#order != null and #order.total > #minimumTotal
~~~

If order is null, the right-hand side is not evaluated.

However, do not rely on short-circuiting to hide side effects in one branch:

~~~text
#shouldNotify and @notificationService.send(#order)
~~~

When shouldNotify is true, the notification method is called. When the condition changes or the expression is re-evaluated, the action may be called again.

Logical conditions should only read data. Place the action after the condition is computed in Java:

~~~java
if (expression.getValue(context, Boolean.class)) {
    notificationService.send(order);
}
~~~

This makes clear when notifications are sent and lets you apply transactions, retries, or idempotency according to application policy.

## 10. One Expression Can Be Evaluated Multiple Times

Parsing an Expression once does not mean its result is computed only once.

For example:

~~~java
Expression expression =
        parser.parseExpression("#order.total > #minimumTotal");

Boolean first = expression.getValue(context, Boolean.class);
Boolean second = expression.getValue(context, Boolean.class);
~~~

Two calls to getValue() are two separate evaluations. If the expression calls a method with side effects, that method may be called in both evaluations.

An expression may also be evaluated multiple times by:

- Multiple requests or multiple messages.
- Loops in application code.
- Framework integration points.
- Mechanisms checking conditions, keys, or metadata.
- Retry logic at the application layer.
- Rebuilding display values or logs.

Do not assume a framework evaluates an expression only once if the API contract does not promise it. Design expressions so re-evaluation does not mutate state.

## 11. Annotations and Integration Points Also Evaluate Expressions

SpEL appears in many Spring annotations and integration points, such as @Value, @Cacheable, @PreAuthorize, or other configurations.

Expressions in these locations are typically used to read parameters, build keys, determine conditions, or check permissions. If an action is embedded there, it may be executed whenever the framework evaluates the expression, which can differ from when a source-code reader expects.

Example of what not to use in a cache key:

~~~java
@Cacheable(
    cacheNames = "orders",
    key = "@auditService.recordAndReturnKey(#orderId)"
)
public Order findOrder(String orderId) {
    // ...
}
~~~

Generating a cache key could invoke an audit-writing method. Key computation should be a pure and deterministic calculation.

Similarly, expressions used in security conditions should only check permissions. Do not put updates or notification calls inside @PreAuthorize.

## 12. MIXED Compiler Mode and the Risk of Re-Running Side Effects

The SpEL compiler has modes OFF, IMMEDIATE, and MIXED. In MIXED mode, if compiled evaluation fails, SpEL may fall back to the interpreter and re-evaluate the expression.

This poses risks if the compiled expression already executed part of an action before the failure occurred.

Example expression:

~~~text
@paymentService.charge(#account, #amount) + #payload.value
~~~

Suppose the charge call already executed the transaction, and then accessing payload.value fails in compiled form. When MIXED falls back to the interpreter and re-evaluates, the charge method may be called a second time.

Therefore:

- Do not put side effects in expressions using MIXED mode.
- Prefer read-only and pure calculation expressions.
- If an action must be invoked, perform it outside the expression at a clear orchestration point.
- Do not rely on switching to IMMEDIATE as a substitute for idempotent design; errors can still happen after an action has started.
- Check the compiler configuration of the parser or integration point in use.

Compiler and fallback details depend on the Spring version. Consult the documentation for your application's version when selecting a mode.

## 13. Separate Decisions from Commands

An easy-to-understand design separates two steps:

1. **Decision:** the expression only answers whether the action should be performed.
2. **Command:** the Java service executes the action after the decision is confirmed.

For example:

~~~java
Expression canApprove =
        parser.parseExpression(
                "#order.total <= #approvalLimit"
                + " and #order.customer.active"
        );

boolean approvedByRule = Boolean.TRUE.equals(
        canApprove.getValue(context, Boolean.class)
);

if (approvedByRule) {
    approvalService.approve(order);
}
~~~

The expression only evaluates the rule. The approve service updates status, persists to the database, and publishes events according to the application's transaction or workflow.

This separation helps:

- Readers clearly see what is the condition and what is the action.
- Expression tests need no database or external systems.
- Service tests can verify transactions, events, and side effects independently.
- Rules can change without altering the command execution workflow.

## 14. Use Pure Functions and Formatters for Transformations

If logic needs to be reused across expressions, prefer pure functions or bean methods:

~~~java
public static String normalizeCode(String value) {
    return value == null ? null : value.trim().toUpperCase(Locale.ROOT);
}
~~~

Expression:

~~~text
#normalizeCode(#rawCode) == #expectedCode
~~~

A formatter can also be suitable if it only converts a value to a string:

~~~text
@priceFormatter.format(#order.total, #locale)
~~~

However, verify that the formatter does not write data or call external systems. A method named format can still have side effects if its implementation does more than expected.

Name methods to reflect actual behavior. If a method mutates state, use an action verb such as approve, send, charge, or persist and invoke it in the service layer.

## 15. Idempotency and Retry Handling for Actions

Some workflows must retry, such as sending messages or calling a payment gateway. In such cases, do not rely on SpEL expressions to manage retries.

Place idempotency in the service or integration layer:

~~~java
paymentService.charge(
        account,
        amount,
        idempotencyKey
);
~~~

The service uses the idempotency key to identify the same business request and prevent duplicate execution according to the payment provider's contract or internal state tracking.

Principles:

- Generate a stable idempotency key for the same business command.
- Persist processing status and outcome according to system policy.
- Distinguish errors before sending the request from ambiguous outcomes after sending.
- Do not automatically retry a non-idempotent operation without knowing whether the previous attempt succeeded.
- Use an outbox or reliable event-publishing mechanism when synchronizing a database and a message broker.

SpEL should decide conditions or compute required data. A dedicated service is the proper place to manage retries, transactions, and idempotency.

## 16. Side Effects and Transaction Boundaries

Calling a method on a bean from SpEL does not automatically create a transaction boundary. Transactions depend on Spring transaction configuration and how the method is invoked through a proxy.

If a bean reference returns a Spring proxy, the call may pass through the transaction interceptor as configured. However, do not assume every expression runs inside a transaction merely because the target method has @Transactional.

Check:

- Whether the resolved bean is the appropriate proxy.
- Whether the invoked method lies within the intended transaction boundary.
- Whether errors propagate so the transaction rolls back.
- Whether side effects outside the database are coordinated with the transaction.
- Whether retries could re-run an action after a transaction has committed or rolled back.

For business operations, calling services directly from an application service usually makes transaction boundaries clearer than embedding calls inside expressions.

## 17. Testing Side Effects

A test should verify not only the return value but also how many times actions were invoked.

Example with Mockito:

~~~java
@Test
void decisionExpressionDoesNotSendNotification() {
    NotificationService notificationService =
            mock(NotificationService.class);

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("order", order);
    context.setVariable("minimumTotal", new BigDecimal("100.00"));

    Expression expression = parser.parseExpression(
            "#order.total >= #minimumTotal"
    );

    Boolean result = expression.getValue(context, Boolean.class);

    assertEquals(Boolean.TRUE, result);
    verifyNoInteractions(notificationService);
}
~~~

If an expression must invoke a read-only method, you can verify that method is called the expected number of times. If an expression includes collection operations, verify that the invocation count matches the element count and number of evaluations.

For command services, test separately:

~~~java
@Test
void approvesOrderOnlyWhenRulePasses() {
    when(ruleEvaluator.canApprove(order)).thenReturn(true);

    applicationService.process(order);

    verify(approvalService, times(1)).approve(order);
}
~~~

Scenarios to test:

- Calling getValue() once and multiple times.
- Empty, single-element, and multi-element collections.
- Short-circuit conditions and ternary branches.
- Methods throwing exceptions before or after mutating state.
- Retries at the application layer.
- MIXED compiler mode if the expression is used in that mode.
- Idempotency when a command is re-sent.

Use mocks or fakes for email, payment, broker, and repository collaborators so tests never trigger real production effects.

## 18. How to Spot Hidden Side Effects

When reading an expression or a method called by an expression, ask yourself:

1. Does property access invoke a getter that queries data or mutates state?
2. Does the method write to a database, publish events, or call an API?
3. Is a registered function genuinely pure?
4. Is a bean reference calling a query method or a command method?
5. Is the expression used inside selection/projection and therefore run on many elements?
6. Could the framework evaluate the expression multiple times?
7. Could any retry or compiler fallback re-execute part of the expression?
8. Does the result depend on time, randomness, shared state, or call order?
9. If the expression fails halfway through, which actions have already occurred?
10. Can the decision and command be separated into two clear steps?

Method names, comments, or return types are not enough to conclude purity. Inspect the implementation and the dependencies the method uses.

## 19. Common Design Mistakes

- **Calling commands inside conditions:** re-evaluating the condition can repeat the action.
- **Sending emails inside projections:** each element can trigger an email.
- **Writing audits inside getters:** repeated property access can create multiple records.
- **Updating state with hidden assignments:** readers assume the expression only computes a value.
- **Using bean references to orchestrate workflows:** expressions hide transactions and action ordering.
- **Putting actions inside cache keys:** key computation can produce side effects.
- **Using a function named like a check that actually writes data:** the name misleads about behavior.
- **Relying on short-circuiting to gate commands:** changing conditions can start triggering the action.
- **Assuming parsing once means evaluating once:** every getValue() still re-executes the expression.
- **Ignoring MIXED fallback:** compiled failures can cause part of the expression to run again.
- **Lacking idempotency for retried commands:** a single request can produce multiple effects.

## 20. Quick Takeaways

- SpEL can invoke methods, functions, beans, and setters; these operations can produce side effects.
- Getters can also query databases, trigger lazy loading, or mutate state.
- Prefer pure expressions for reading data, checking conditions, and computing values.
- Do not put payments, notifications, database writes, or event publishing inside expressions used for conditions, keys, templates, or collection operations.
- Selection and projection can evaluate expressions for each element.
- A parsed Expression can be evaluated multiple times; parse once does not mean run once.
- Short-circuiting and ternaries only control which branch is evaluated, not that actions inside a branch run only once.
- Assignment in SpEL can mutate objects if the context allows writes.
- MIXED compiler mode can fall back to the interpreter after a compiled failure and cause part of an expression to be re-evaluated.
- Separate decision expressions from command services.
- Keep transactions, retries, and idempotency in the application/service layer.
- Test both return values and how many times side effects occur.

## 21. Official References

- [Spring Framework — SpEL Evaluation and EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework — Method Invocation](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework — Variables and Functions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework — Collection Selection and Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
