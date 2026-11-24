# Side-Effect Risks When Invoking Methods from SpEL Expressions

Spring Expression Language (SpEL) allows invoking methods on the root object, properties, or variables placed into the EvaluationContext. A method call may simply return data, yet it can also mutate state, write to a database, send messages, call an API, or perform an external operation. Because expressions can be evaluated multiple times and at different moments, methods with side effects need explicit control.

When designing expressions, treat method invocation as an action capable of executing application logic. It is necessary to define who is permitted to call, which methods are permitted, when calls occur, and how to handle partial completion.

## 1. Distinguishing read-only methods from methods with side effects

A read-only method typically returns information without altering observable system state. Examples:

    #order.items.size()
    #customer.getDisplayName()
    #pricingService.calculatePreview(#order)

Such methods are better suited for expressions used for display, conditional checks, or computing derived values, provided they genuinely do not write data or call services with side effects.

A method with side effects can change an object or external state:

    #order.approve()
    #inventoryService.reserve(#productId, #quantity)
    #notificationService.send(#recipient, 'Order confirmed')
    #repository.save(#order)

The examples above can update order status, reserve inventory, send notifications, or persist data. When such a call sits inside an expression, evaluating the expression can become an actual business action.

A method name is not enough to conclude whether it is safe. A method named `getStatus()` may still access a remote system or write business-significant logs; a method named `calculate()` may also update a cache or counter. Inspect the implementation and contract of the method.

## 2. Expressions evaluated multiple times

Parsing a SpEL string produces an Expression that can be evaluated later. Each call to `getValue(...)` evaluates the expression within the provided context. Do not assume that the result of a previous evaluation is automatically cached and reused.

Example:

    Expression expression =
            parser.parseExpression("#counterService.nextSequence()");

    Object first = expression.getValue(context);
    Object second = expression.getValue(context);

If `nextSequence()` increments a counter, two evaluations can produce two different numbers and mutate state twice. Keeping the Expression object for reuse does not turn a method with side effects into a one-time execution.

Some application flows may evaluate the same expression multiple times: when checking conditions, rendering UI, recomputing data, or handling retries. If the expression calls a data-writing method, repeated evaluations can produce duplicate updates, send multiple notifications, or consume excessive resources.

Therefore, keep query expressions side-effect-free. Perform data-writing actions through an explicit business step, where the application controls the call count and outcome.

## 3. Side effects in logical conditions

Methods can appear inside `and`, `or`, or `not` conditions:

    #account.isActive() and #auditService.recordCheck(#account.id)

Logical operators can short-circuit: if the left side of AND is false, the right side is not evaluated; similarly, if the left side of OR is true, the right side does not need evaluation. Consequently, a method with side effects on the right side may only be called in certain cases.

This makes the count and ordering of side effects depend on input data as well as condition structure. If the order of operands changes or a new condition is added, write behavior may change even though the original goal was only to adjust logic.

Do not use data-writing methods to produce side effects inside Boolean conditions. Separate checking and acting into two steps:

    Boolean allowed =
            parser.parseExpression("#account.isActive()")
                    .getValue(context, Boolean.class);

    if (Boolean.TRUE.equals(allowed)) {
        auditService.recordCheck(account.getId());
    }

In this approach, the condition only answers the question. Java controls when the audit is recorded and can explicitly check the result before performing the next action.

## 4. Side effects in arguments of another method

A method call can contain other calls inside its argument list:

    #orderService.submit(
        #order,
        #inventoryService.reserve(#order.productId, #order.quantity)
    )

Before invoking the outer method, SpEL must evaluate the arguments to be passed in. Thus, `reserve(...)` can perform side effects while preparing arguments for `submit(...)`.

If the outer method fails after the inner method has already reserved inventory, the system can end up in a partially updated state. Two methods appearing in the same expression do not automatically create a shared transaction or rollback mechanism across all external systems.

Avoid nesting data-writing methods inside arguments. Instead, orchestrate the sequence in a business service:

    Reservation reservation =
            inventoryService.reserve(productId, quantity);

    orderService.submit(order, reservation);

The service can manage transactions, handle errors, and compensate if a later step fails. SpEL should be used to pass or compute needed values, while the action sequence should be expressed in business code.

## 5. Method calls can affect external systems

Side effects are not limited to the root object. A method can:

- Insert or delete records in a database.
- Send emails, SMS, or push notifications.
- Publish messages to a queue or event bus.
- Call a REST API or payment service.
- Acquire or release resources.
- Create files, write audit logs, or update caches.
- Mutate state shared across multiple requests.

These operations can fail due to timeouts, network errors, access permissions, or incidents in the target system. A single SpEL evaluation can throw an error after a side effect has already occurred. Catching exceptions at the call site does not automatically reverse changes already accepted by an external system.

For irreversible operations such as sending notifications or publishing events, consider emission timing, retry mechanisms, and duplicate-delivery risk. If event publication must be tied to a database transaction, use an appropriate application-layer mechanism, such as a transactional outbox, instead of placing the send command directly inside an expression.

## 6. Retries, safe repeatability, and idempotency

A retried operation can be executed more than once. This often happens when a request times out or the application fails to receive confirmation from the target service even though the service processed it successfully.

If a method with side effects is called through SpEL, clarify:

- Can an evaluation be repeated within the same request?
- Does the calling layer retry upon receiving an error or timeout?
- Is the method idempotent, meaning repeated calls with the same data preserve an equivalent business outcome?
- Is an idempotency key or unique request ID needed to prevent duplicate processing?
- If a later step fails, is there a compensating action to perform?

For example, `setStatus('APPROVED')` may be safe to repeat if it only sets the same state and produces no secondary side effects. However, `incrementBalance(100)` or `sendNotification(...)` is usually unsafe to call repeatedly without deduplication mechanisms.

Idempotency must be designed in the service or target system. Caching the Expression result or expression value does not replace duplicate-processing protection at the business layer.

## 7. Controlling invocable methods via EvaluationContext

StandardEvaluationContext by default provides reflection-based method invocation via ReflectiveMethodResolver. If the root object or variables contain services with many public methods, an expression can invoke methods the use case did not intend to provide.

For expressions that only need to read data, restrict the objects placed into the context and use SimpleEvaluationContext with an appropriate configuration. SimpleEvaluationContext does not enable instance method invocation by default; if invoking instance methods is needed, the application must explicitly enable it through the builder via `withInstanceMethods()`.

Example:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withInstanceMethods()
                    .withRootObject(viewModel)
                    .build();

This configuration illustrates enabling instance method calls on a data-binding object. It does not automatically create a per-method allowlist; therefore, the object placed into the context must have an API matching the expression's trust level.

If stricter method restrictions are needed, use a custom MethodResolver or a facade exposing only permitted operations. Avoid placing repositories, payment services, notification services, or broad administrative services directly into contexts meant for user-supplied expressions.

## 8. Creating a facade with a narrow API

A safer way to organize this is to provide an intermediary object with small methods and clear contracts. For example, instead of putting the entire OrderService into the context, provide a facade with preview-only methods:

    public final class OrderExpressionView {

        private final Order order;

        public OrderExpressionView(Order order) {
            this.order = order;
        }

        public boolean isEligibleForDiscount() {
            return order.getTotal().compareTo(
                    new BigDecimal("100.00")) >= 0;
        }

        public BigDecimal getEstimatedTotal() {
            return order.getTotal();
        }
    }

The methods in the example only read data. This facade can be passed as the root object or a variable for expressions to use without opening up save, delete, or notification operations.

If an action is genuinely needed, consider creating a dedicated service with method names and parameters that clearly express the action. The Java layer must verify permissions, validate data, and manage transactions before calling. Do not use a facade with a generic method like `execute(String command)` that turns expressions into an arbitrary command executor.

## 9. Error handling and observing behavior

Method invocation can fail during resolution or execution. Common causes include:

- The target object is null.
- The method does not exist or is inaccessible.
- The number or types of arguments do not match.
- TypeConverter cannot convert an argument.
- The method throws an exception during execution.
- An external service times out or rejects the operation.

When debugging, inspect the target, method signature, runtime types of each argument, and the root exception thrown by the method. If an expression invokes methods with side effects, log the request ID, processing status, and service outcome at the business layer. Avoid logging the entire expression string if it may contain sensitive data.

For important actions, clearly distinguish states: not started, executed, failed before write, failed after the target system processed it, and unknown outcome due to timeout. These states determine whether to retry or query status before proceeding.

## 10. Testing method calls with side effects

Test argument evaluation and method invocation counts separately. Scenarios to cover:

1. Literals pass the expected values and types.
2. Properties pass the current values of objects.
3. Sub-expressions are evaluated before the outer method receives arguments.
4. Null properties are handled properly per contract.
5. Overloads are selected accurately by runtime types.
6. AND/OR conditions do not trigger unexpected side-effect method calls.
7. Evaluating the same Expression multiple times does not cause unintended duplicate updates.
8. Exceptions or timeouts are handled according to retry and compensation policies.

Mocks or spies can be used for services to verify invocation counts and actual arguments. For methods that write to a database or call external services, test transactions, idempotency, and behavior when an intermediate step in the workflow fails.

## 11. Summary

Method invocation in SpEL can execute logic and produce side effects. Literals, properties, and expressions can all serve as arguments; SpEL evaluates arguments and then resolves a matching method. An Expression evaluated multiple times can invoke a method multiple times, and short-circuiting can change whether a branch is executed. Keep query expressions side-effect-free, restrict callable methods via contexts or facades, and place data-writing actions, external service calls, retries, and transactions in controlled business services.
