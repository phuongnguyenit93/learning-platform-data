# SpEL in @EventListener condition

Spring Framework allows using the Spring Expression Language (SpEL) in the **condition** attribute of the **@EventListener** annotation. The condition is evaluated when a matching event is published to the listener. Only when the result is Boolean true is the listener method invoked.

This feature is useful when many events share the same type but only some events need to trigger a specific handler. For example, a listener only handles orders whose total exceeds a threshold, only receives notifications belonging to a certain channel, or only runs when a feature is enabled.

The condition is a SpEL expression, so it can read event properties, method parameters, variables in the evaluation context, and beans resolved by Spring. Keep conditions concise, easy to test, and avoid calling methods with side effects while filtering events.

## 1. @EventListener and the condition attribute

### 1.1. Basic listener declaration

A method marked with @EventListener is registered by Spring as an event listener:

~~~java
@Component
public class OrderEventListener {

    @EventListener
    public void handleOrderPlaced(OrderPlacedEvent event) {
        // Handle event
    }
}
~~~

When the application publishes an event of a matching type, Spring invokes the listener method via the event multicaster mechanism.

Events can be published via ApplicationEventPublisher:

~~~java
@Component
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void placeOrder(OrderPlacedEvent event) {
        publisher.publishEvent(event);
    }
}
~~~

An event can be a class extending ApplicationEvent or a plain object published as a payload event. Spring supports publishing object events starting from modern versions of the framework.

### 1.2. Adding a condition

The condition attribute accepts a SpEL expression string:

~~~java
@EventListener(condition = "#a0.total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
    // Only handle orders with total >= 100
}
~~~

When an event matching the method parameter type is published:

1. Spring determines that the listener can receive the event.
2. The condition expression is evaluated in the listener's context.
3. If the result is true, the method is invoked.
4. If the result is false, the method is skipped for that event.

The condition only decides whether the specific listener method is called. It does not cancel the event, prevent other listeners from receiving the event, or change the fact that the event has already been published.

### 1.3. Default condition

If no condition is declared, the listener has no additional SpEL filter:

~~~java
@EventListener
public void handleAllOrders(OrderPlacedEvent event) {
}
~~~

The default condition can be understood as having no expression-based filtering condition. When filtering is needed, add the condition directly to the annotation instead of creating multiple identical if-branches at the start of the method.

## 2. Accessing the event and method arguments

### 2.1. Using #a0 and #p0

In a condition, listener method arguments can be accessed by index:

~~~java
@EventListener(condition = "#a0.total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
}
~~~

**#a0** references the first argument. **#p0** is a compatible syntax for the same parameter position.

For listeners receiving a single event argument, #a0 is usually a clear and reliable way to access the payload the method will receive.

### 2.2. Using #root.args

The event listener's evaluation context provides arguments as an array via the root object:

~~~java
@EventListener(condition = "#root.args[0].total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
}
~~~

**args** can be used instead of **#root.args** in the appropriate expression context:

~~~java
@EventListener(condition = "args[0].total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
}
~~~

Writing #a0 is shorter for the first parameter; #root.args is useful when you want to explicitly show access to the argument list.

### 2.3. Using parameter names

Spring can allow accessing arguments by parameter name if parameter name metadata is retained and ParameterNameDiscoverer can determine that name:

~~~java
@EventListener(condition = "#orderEvent.total >= 100")
public void handleLargeOrder(OrderPlacedEvent orderEvent) {
}
~~~

For reliable parameter name discovery, configure the build to retain parameter name metadata, such as the Java compiler **-parameters** option. Discovery capability also depends on the Spring version and how the class was compiled.

If unsure whether parameter names are retained, use #a0 or #p0 to avoid making the condition depend on compilation metadata.

### 2.4. #root.event and event

The event expression context also provides the current event via the root object:

~~~java
#root.event
~~~

Event properties can be used through the root event if the event type and accessor permit. Meanwhile:

- **#root.event** references the event currently being processed.
- **#root.args** are the resolved arguments for the listener method.
- **#a0** or **#p0** references the first argument.
- **#root** is the root object for condition evaluation.

With payload events passed into a method parameter, using #a0 or the parameter name usually keeps the expression closely aligned with the exact object the method receives. When needing to access Spring event metadata, check the actual type of the event provided in the context.

## 3. Writing conditions based on event properties

### 3.1. Filtering by status

Suppose the event has JavaBean getters:

~~~java
public class OrderPlacedEvent {

    private final String orderId;
    private final String status;
    private final BigDecimal total;

    public OrderPlacedEvent(
            String orderId,
            String status,
            BigDecimal total) {
        this.orderId = orderId;
        this.status = status;
        this.total = total;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

The listener only receives paid orders:

~~~java
@EventListener(condition = "#a0.status == 'PAID'")
public void handlePaidOrder(OrderPlacedEvent event) {
    // Handle paid order
}
~~~

SpEL accesses the status property via a property accessor, usually based on the getStatus() getter.

### 3.2. Combining multiple conditions

AND, OR, and comparison operators can be combined:

~~~java
@EventListener(
    condition = "#a0.status == 'PAID' && #a0.total >= 100"
)
public void handleQualifiedOrder(OrderPlacedEvent event) {
}
~~~

The listener only runs when both status and total satisfy the conditions.

Example using OR:

~~~java
@EventListener(
    condition = "#a0.status == 'PAID' || #a0.status == 'SETTLED'"
)
public void handleCompletedOrder(OrderPlacedEvent event) {
}
~~~

When an expression has multiple logic groups, use parentheses and line breaks to clearly reflect the business structure.

### 3.3. Filtering by string

Channel codes, event types, or status names can be compared:

~~~java
@EventListener(condition = "#a0.channel == 'WEB'")
public void handleWebOrder(OrderPlacedEvent event) {
}
~~~

String equality comparison is case-sensitive. If the domain requires case-insensitivity, normalize the data before publishing or use an appropriate comparison method while guarding against null.

Example:

~~~java
@EventListener(
    condition = "#a0.channel != null && #a0.channel.equalsIgnoreCase('web')"
)
public void handleWebOrder(OrderPlacedEvent event) {
}
~~~

Do not put a long normalization chain inside multiple annotations. If the rule is reused, normalize the event where it is created or extract a clearly named predicate.

### 3.4. Filtering by numeric values

SpEL supports numeric comparisons:

~~~java
@EventListener(condition = "#a0.total > 1000")
public void handleHighValueOrder(OrderPlacedEvent event) {
}
~~~

When total is BigDecimal, test the expression with the actual type and the Spring version in use. Avoid converting money amounts to double just for comparison if the business domain requires decimal precision.

Thresholds should come from configuration or validated data if they need to vary by environment. Do not hard-code different thresholds across listeners when they represent the same business policy.

## 4. Handling null in conditions

### 4.1. Checking for null before deep access

If an event may contain a null field, place a null guard first:

~~~java
@EventListener(
    condition = "#a0.customer != null && #a0.customer.active"
)
public void handleActiveCustomerOrder(OrderPlacedEvent event) {
}
~~~

The AND operator uses short-circuit evaluation. If customer is null, the side accessing active is not evaluated.

### 4.2. Using safe navigation

Safe navigation can be used on a property path when supported by the Spring version:

~~~java
@EventListener(
    condition = "#a0.customer?.active == true"
)
public void handleActiveCustomerOrder(OrderPlacedEvent event) {
}
~~~

Safe navigation handles a null receiver at the position with ?. It does not handle misspelled property names, nonexistent methods, or exceptions thrown by invoked code.

### 4.3. Nullable Boolean values

If a property is a Boolean wrapper rather than a primitive boolean, the value may be null. Write the condition explicitly:

~~~java
@EventListener(condition = "#a0.enabled == true")
public void handleEnabledEvent(MyEvent event) {
}
~~~

This approach only accepts cases where enabled is true. Both null and false do not satisfy the condition.

Do not use simple negation without defining the meaning of null. For example, enabled != true can include both false and null; that may not match the business rule.

### 4.4. Condition is not validation

If an event is missing required data, a condition returning false only causes the listener to be skipped. It does not automatically report a validation error to the event publisher.

Validate events before publishing or in the application service. Conditions are suitable for selecting listeners by policy, and should not be used as the sole mechanism to ensure valid data.

## 5. Using beans in conditions

### 5.1. Referencing a Spring bean

Event listener conditions are evaluated in a context that supports Spring bean resolution. Beans can be referenced using the **@beanName** syntax:

~~~java
@EventListener(
    condition = "@featureFlags.isEnabled('order-alerts') && #a0.total > 0"
)
public void handleOrderAlert(OrderPlacedEvent event) {
}
~~~

This example checks a feature flag and then checks the event's total. The bean must be registered in the ApplicationContext and have an appropriate method.

### 5.2. Using a bean as a policy

If rules are complex, the decision part can be placed in a policy bean:

~~~java
@Component
public class OrderEventPolicy {

    public boolean shouldNotify(OrderPlacedEvent event) {
        return event.getTotal() != null
                && event.getTotal().compareTo(new BigDecimal("100")) >= 0;
    }
}
~~~

Listener:

~~~java
@EventListener(
    condition = "@orderEventPolicy.shouldNotify(#a0)"
)
public void notifyQualifiedOrder(OrderPlacedEvent event) {
}
~~~

This keeps the annotation shorter and allows the policy to be tested directly with unit tests.

### 5.3. Keep methods in conditions free of side effects

A condition may be evaluated before the listener method runs. If a method called inside the condition sends an email, writes to a database, or mutates state, that action still happens even if the rest of the condition causes the listener to be skipped.

Therefore, methods used in conditions should be pure predicates or read-only, low-cost, and deterministic. Keep business actions inside the listener method after the condition allows processing.

### 5.4. Do not overuse bean references

Do not call multiple services in a long condition. Doing so makes deciding whether the listener runs depend on many components and hard to diagnose when errors occur.

If a lot of data is needed, compute it before publishing the event or package the required data into the event. Use a policy bean when a rule has distinct meaning and needs to be shared.

## 6. Combining multiple listeners with different conditions

One event can be dispatched to multiple listeners. Each listener has its own condition:

~~~java
@Component
public class OrderEventListeners {

    @EventListener(condition = "#a0.total >= 1000")
    public void handleHighValueOrder(OrderPlacedEvent event) {
        // Handle high-value order
    }

    @EventListener(condition = "#a0.channel == 'WEB'")
    public void handleWebOrder(OrderPlacedEvent event) {
        // Handle order from web channel
    }

    @EventListener(condition = "#a0.status == 'CANCELLED'")
    public void handleCancelledOrder(OrderPlacedEvent event) {
        // Handle cancelled order
    }
}
~~~

When an event is published:

- The first listener only runs if total reaches the threshold.
- The second listener only runs if channel is WEB.
- The third listener only runs if status is CANCELLED.

One event can satisfy multiple conditions and trigger multiple listeners. One listener's condition does not exclude the event from other listeners.

If listeners need a specific processing order, look into ordering mechanisms such as @Order and ensure that order matches requirements. Do not rely on method declaration order in source code to infer listener order.

## 7. Conditions with event payloads and event types

### 7.1. Event as a plain object

Spring allows publishing a plain object:

~~~java
publisher.publishEvent(
        new OrderPlacedEvent("O-100", "PAID", new BigDecimal("150"))
);
~~~

The listener receives the event payload according to the parameter type:

~~~java
@EventListener(condition = "#a0.status == 'PAID'")
public void handlePaidOrder(OrderPlacedEvent event) {
}
~~~

Using a method argument to access payload data keeps the expression aligned with the listener signature.

### 7.2. Filtering by event type

Determining whether a listener receives an event is primarily based on the parameter type and Spring's event resolution rules. Condition is an additional filtering step after the listener is considered a match for the event.

Do not use condition as a substitute for event type design. If two groups of events have different structures or meanings, create separate event classes to make system routing clearer.

### 7.3. Generic events

For generic events, Spring supports type resolution in some cases via ResolvableType and the listener parameter type. However, generic types at runtime can be affected by type erasure and how the event is created.

If a listener depends on a specific payload type, test event type resolution in the actual application. Conditions should only inspect content after the listener has received the right event type.

## 8. Conditions and asynchronous processing

### 8.1. Combining with @Async

A listener can be annotated with @Async if the application enables async support:

~~~java
@Async
@EventListener(condition = "#a0.total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
    // Handle asynchronously
}
~~~

The condition remains the criterion deciding whether the listener is invoked. Running the method asynchronously does not turn the condition into a retry or error-handling mechanism.

Configure an appropriate executor, queue limits, and task rejection policy. Do not assume an async event listener guarantees durable event processing after the application stops.

### 8.2. Exceptions in async listeners

With asynchronous listeners, exceptions thrown inside the method are usually not propagated back to the thread that published the event. Configure error handling for the executor or AsyncUncaughtExceptionHandler as needed.

Errors when evaluating the condition are a different stage from errors inside the async method. Observe logs and test both cases, especially when the condition calls a policy bean.

### 8.3. When durable processing is needed

@EventListener is an in-memory event mechanism within a Spring application. If business requirements require guaranteed delivery across restarts, retries, deduplication, or distributed processing, use a suitable message broker or transactional outbox. The condition in the annotation only filters listener invocation within the current event flow.

## 9. Conditions and listener return values

An @EventListener method can return an object instead of void. Spring can publish the return value as a new event according to the rules of the event listener adapter.

The condition decides whether the method is called. If the condition is false, the method does not run and there is no return value from that invocation to publish further.

If the method returns a collection or array, the framework can publish the elements as separate events according to supported semantics. Check the documentation of the Spring version in use if relying on this behavior.

Do not use condition as a global filter for subsequently published events. It only applies to the listener method carrying that annotation.

## 10. Testing @EventListener conditions

### 10.1. Testing with ApplicationContext

A test context can be created to publish events and verify that the listener is called only when the condition is true.

Example listener:

~~~java
@Component
public class OrderEventListener {

    private final List<String> handled = new ArrayList<>();

    @EventListener(condition = "#a0.total >= 100")
    public void handle(OrderPlacedEvent event) {
        handled.add(event.getOrderId());
    }

    public List<String> getHandled() {
        return handled;
    }
}
~~~

The test can publish an event below the threshold and an event meeting the threshold:

~~~java
publisher.publishEvent(
        new OrderPlacedEvent("O-LOW", "PAID", new BigDecimal("50"))
);

publisher.publishEvent(
        new OrderPlacedEvent("O-HIGH", "PAID", new BigDecimal("150"))
);
~~~

After the events are processed synchronously, only O-HIGH is recorded.

With an async context, wait or synchronize the test with the executor rather than assuming the listener finishes immediately after publishEvent.

### 10.2. Cases to test

Should include:

- Condition true: listener is called.
- Condition false: listener is skipped.
- Value exactly at the comparison threshold.
- Null property and null Boolean wrapper.
- Strings differing in letter case.
- Expressions using #a0, #p0, and parameter names.
- Policy bean present and working properly.
- Bean or method in the condition throws an exception.
- Multiple listeners with independent conditions.
- Event not matching the parameter type.
- Async listener and error-handling policy.
- Listener returning a follow-up event if the application uses this capability.

Do not only check the invocation count. Verify which exact event was handled to catch miswritten conditions or wrong parameters.

### 10.3. Testing policies separately

If a condition calls a policy bean, test the policy as a regular Java class:

~~~java
assertTrue(policy.shouldNotify(highValueOrder));
assertFalse(policy.shouldNotify(lowValueOrder));
~~~

Then have a small integration test confirming the annotation calls the right policy and Spring evaluates the condition as expected.

This separation prevents bugs in business logic from being confused with event listener configuration or SpEL errors.

## 11. Common mistakes

| Symptom | Possible cause | How to handle |
|---|---|---|
| Listener does not run | Condition returns false or event does not match type | Check event type and condition value |
| Parameter name not found | Parameter name metadata not retained | Use #a0/#p0 or enable -parameters |
| Error accessing property | Wrong getter/property name or null receiver | Check event model and add null guard |
| Condition does not return a valid Boolean | Expression returns another type or cannot be converted | Write a clear Boolean expression |
| Bean reference is not resolved | Bean not registered or wrong name | Check ApplicationContext and bean name |
| Condition calls service too slowly | Predicate performs queries or I/O | Precompute data or use a lightweight policy |
| Multiple listeners run together | One event satisfies multiple conditions | Design independent, clearly targeted conditions |
| Async listener completes late | Executor processes on another thread | Synchronize tests and configure executor |
| Event skipped without validation error | Condition only filters listeners | Validate events before publishing |
| Condition error treated as false | Exception caught too broadly at an outer layer | Classify evaluation errors and log appropriately |

Do not catch every exception during condition evaluation and return false. That approach can cause events to be silently skipped when an expression is wrong, a bean fails, or data has an invalid structure.

## 12. Principles for designing maintainable conditions

A good condition should be short, have a clear Boolean result, and only read necessary data.

- Use #a0 or #p0 when reliable access to the event argument is needed.
- Use parameter names when the build retains metadata and those names make the expression easier to understand.
- Use #root.event or #root.args when needing to explicitly express the event context structure.
- Place null guards before deep access.
- Use a policy bean for long or reusable rules.
- Keep methods called from conditions pure, lightweight, and free of side effects.
- Do not use conditions as a substitute for validation, authorization, or durable messaging.
- Test true, false, null, resolution errors, and multiple listeners receiving the same event.

If a condition becomes a long expression with multiple service calls, move the decision logic to a clearly named policy. The annotation should only concisely express the criteria under which the listener is allowed to handle the event.

## 13. Summary

The **condition** attribute of **@EventListener** allows using SpEL to decide whether a listener method is called for a matching event.

- **#a0** and **#p0** access the first argument; **#root.args** accesses the argument list.
- **#root.event** references the current event in the event expression context.
- Parameter names can be used if metadata is retained and Spring can discover the names.
- Properties, logical operators, null checks, and policy beans can be combined.
- A false condition only skips that listener; other listeners can still receive the event.
- Conditions do not replace validation, authorization, retries, or durable delivery guarantees.
- With async listeners, configure an executor and separate exception handling.
- Keep conditions short, read-only, and easy to test.

Use conditions when filtering events based on already available data. For complex business rules, place the logic in a Java policy/service and have the condition call a lightweight, clearly named predicate.