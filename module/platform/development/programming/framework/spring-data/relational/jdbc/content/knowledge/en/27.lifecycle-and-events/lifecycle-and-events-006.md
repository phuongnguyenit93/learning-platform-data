# Distinguishing EntityCallback from ApplicationEvent and Execution Order

Spring Data JDBC provides two mechanisms to hook into an aggregate's lifecycle: **EntityCallback** and **lifecycle ApplicationEvent**. Both can be invoked at milestones such as before saving or after reading data, yet their purposes and mechanics differ.

- **EntityCallback** is a hook sitting directly inside the aggregate-processing pipeline. A callback can return the same entity or a modified instance. Spring Data invokes callbacks sequentially at defined checkpoints.
- **ApplicationEvent** is a notification published inside the Spring ApplicationContext. Listeners receive information about a lifecycle event; the event mechanism fits logging, auditing, metrics, or notifying other components.

In Spring Data JDBC, a lifecycle event is a type of `ApplicationEvent` emitted by Spring Data. An EntityCallback and its corresponding event usually appear at the same checkpoint, with the event published before the callback. When you need to modify an entity in a controlled way, Spring recommends callbacks. When you need to notify listeners, use events.

This lesson explains their differences, available callbacks and events, save/load/delete pipelines, event-versus-callback ordering, bean registration, transaction boundaries, and cases that do not trigger lifecycle hooks.

## 1. Two mechanisms serving two purposes

### EntityCallback

`EntityCallback<T>` is Spring Data's abstraction for an extension point in the entity-processing flow. Each callback interface binds to a domain type via generic type `T`.

For example, `BeforeConvertCallback<Order>` only handles aggregates of type `Order`. The callback method receives the entity and returns a possibly modified entity:

~~~java
public interface BeforeConvertCallback<T> extends EntityCallback<T> {
    T onBeforeConvert(T aggregate);
}
~~~

The return value is used by Spring Data in the next step. Therefore, callbacks work with both mutable and immutable entities.

### ApplicationEvent

Spring Data JDBC publishes lifecycle events, such as `BeforeSaveEvent<Order>`. Listeners subscribe to events in the ApplicationContext:

~~~java
@EventListener
public void onBeforeSave(BeforeSaveEvent<Order> event) {
    log.info("Saving order {}", event.getEntity().getId());
}
~~~

An event is a notification about a lifecycle milestone. Listeners can read the entity and attached aggregate change information, but events have no contract to return a replacement instance to the persistence pipeline.

### Quick comparison

| Criterion | EntityCallback | ApplicationEvent |
| --- | --- | --- |
| Primary purpose | Intervene in the entity-processing pipeline | Notify that an event has occurred/is occurring |
| Processing result | Returns a possibly modified entity | Does not return an entity to the pipeline |
| Ordering | Sequential at checkpoint; orderable via `@Order`/`Ordered` | Depends on ApplicationEventMulticaster and listener configuration |
| Immutable entities | Well supported because a new instance can be returned | No mechanism to return a new instance to Spring Data |
| Scope | Callbacks are filtered by generic domain type | Listeners are selected by event type |
| Registration | `EntityCallback` bean in ApplicationContext | `ApplicationListener` or `@EventListener` |
| Use cases | Normalization, populating data, pre-persistence checks | Logging, auditing, metrics, notifying other components |

Do not treat these two mechanisms as two names for the same API. Callbacks participate in the entity-processing flow; events serve in-application communication and observation.

## 2. Lifecycle callbacks in Spring Data JDBC

Imperative callbacks in Spring Data JDBC belong to the package:

~~~java
import org.springframework.data.relational.core.mapping.event.*;
~~~

Common interfaces:

| Callback | Timing | Purpose |
| --- | --- | --- |
| `BeforeConvertCallback<T>` | Before the aggregate is converted into a database change plan | Modify domain data before creating SQL operations; suitable for programmatic ID assignment |
| `BeforeSaveCallback<T>` | After `AggregateChange` is created, before running SQL | Intervene at the write-preparation stage |
| `AfterSaveCallback<T>` | After the SQL statements saving the aggregate have run | Process the instance after persistence |
| `AfterConvertCallback<T>` | After the aggregate is built from database data | Enrich or adjust the instance after reading |
| `BeforeDeleteCallback<T>` | Before deleting the aggregate | Intervene in the delete operation |
| `AfterDeleteCallback<T>` | After deleting the aggregate | Process after deletion |

Examples of main signatures:

~~~java
public interface BeforeConvertCallback<T> extends EntityCallback<T> {
    T onBeforeConvert(T aggregate);
}

public interface BeforeSaveCallback<T> extends EntityCallback<T> {
    T onBeforeSave(
        T aggregate,
        MutableAggregateChange<T> aggregateChange
    );
}

public interface AfterSaveCallback<T> extends EntityCallback<T> {
    T onAfterSave(T aggregate);
}

public interface AfterConvertCallback<T> extends EntityCallback<T> {
    T onAfterConvert(T aggregate);
}

public interface BeforeDeleteCallback<T> extends EntityCallback<T> {
    T onBeforeDelete(
        T aggregate,
        MutableAggregateChange<T> aggregateChange
    );
}

public interface AfterDeleteCallback<T> extends EntityCallback<T> {
    T onAfterDelete(T aggregate);
}
~~~

These callbacks apply to the **aggregate root**. If you need to handle a child entity belonging to the aggregate, access it through the aggregate root in the corresponding callback. Spring Data JDBC does not automatically invoke a separate callback for each child object in a collection.

## 3. Corresponding lifecycle ApplicationEvents

Spring Data JDBC publishes the following events:

| Event | Publish timing |
| --- | --- |
| `BeforeConvertEvent<T>` | Before the aggregate is converted into an SQL plan, after Spring Data has decided insert or update |
| `BeforeSaveEvent<T>` | Before applying changes to the database, after `AggregateChange` is created |
| `AfterSaveEvent<T>` | After the aggregate has been saved via SQL statements |
| `AfterConvertEvent<T>` | After the aggregate has been created from `ResultSet` and properties have been populated |
| `BeforeDeleteEvent<T>` | Before deleting the aggregate root |
| `AfterDeleteEvent<T>` | After deleting the aggregate root |

These events reside in the package:

~~~java
import org.springframework.data.relational.core.mapping.event.*;
~~~

They are Spring event classes that can be received via `ApplicationListener` or `@EventListener`.

Example registering an event listener:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.data.relational.core.mapping.event.AfterSaveEvent;

@Component
public class OrderLifecycleListener {

    @EventListener
    public void onAfterSave(AfterSaveEvent<Order> event) {
        Order savedOrder = event.getEntity();

        log.info(
            "Order {} was persisted",
            savedOrder.getId()
        );
    }
}
~~~

If you want a more explicit listener, you can implement `ApplicationListener<BeforeSaveEvent<Order>>`. Using a concrete generic type helps Spring filter the exact domain event to handle.

## 4. Execution order when saving an aggregate

This is the most important part of the lesson. When a repository or template saves an aggregate, Spring Data JDBC goes through several stages. At each checkpoint, there is a corresponding lifecycle event and callback.

~~~mermaid
flowchart TD
    A["Start aggregate save"] --> B["Determine new or existing entity"]
    B --> C["BeforeConvertEvent"]
    C --> D["BeforeConvertCallback"]
    D --> E["Create AggregateChange / DbAction"]
    E --> F["BeforeSaveEvent"]
    F --> G["BeforeSaveCallback"]
    G --> H["Execute SQL"]
    H --> I["AfterSaveEvent"]
    I --> J["AfterSaveCallback"]
    J --> K["Return result from save operation"]
~~~

Under Spring Data Commons mechanics, store-specific ApplicationEvents are published before the corresponding EntityCallbacks are invoked. Therefore, in the default synchronous event configuration, the order at each checkpoint is:

1. Publish the event.
2. Invoke the corresponding callback.
3. Proceed to the next processing step.

### 4.1. Determining insert or update

Spring Data JDBC determines whether an aggregate is new or existing before calling `BeforeConvertCallback`. This decision governs the subsequent persistence plan.

This means `BeforeConvertCallback` can assign an ID to a new aggregate, but is not the place to arbitrarily change the already-determined newness state.

### 4.2. BeforeConvertEvent and BeforeConvertCallback

After deciding insert/update, Spring Data publishes `BeforeConvertEvent` and then calls `BeforeConvertCallback`.

This checkpoint is suitable for:

- Normalizing domain data before mapping.
- Programmatically assigning an ID to a new aggregate.
- Generating a slug or business code to be stored in the database.
- Populating timestamps or metadata that belong in persisted data.

For example, using a callback to normalize an order code:

~~~java
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class NormalizeOrderCodeCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order) {
        String normalized = order.getCode().trim().toUpperCase();

        order.setCode(normalized);

        return order;
    }
}
~~~

The example uses a mutable entity for illustration. If the entity is immutable, construct and return a new instance instead of mutating the current object.

### 4.3. Creating AggregateChange

After `BeforeConvertCallback`, Spring Data JDBC converts the aggregate into `AggregateChange`. This structure holds the `DbAction`s to execute, such as insert, update, and delete for the root and child entities.

At this stage, Spring Data has already determined how to execute the operations and whether the ID is supplied by the aggregate or generated by the database.

### 4.4. BeforeSaveEvent and BeforeSaveCallback

After creating `AggregateChange`, Spring Data publishes `BeforeSaveEvent` and then calls `BeforeSaveCallback`. SQL has not run yet at this point.

This callback receives both the aggregate and `MutableAggregateChange`. It can return the entity and intervene in the change plan.

Do not use `BeforeSaveCallback` to generate an ID for a new aggregate. The ID strategy decision was already made when creating the aggregate change. If you need to assign an ID before persistence, use `BeforeConvertCallback`.

### 4.5. SQL and AfterSaveEvent/AfterSaveCallback

After the pre-save callback, Spring Data executes the SQL statements in `AggregateChange`. Once the save operation finishes, Spring Data publishes `AfterSaveEvent` and then calls `AfterSaveCallback`.

This is a suitable checkpoint for observing the persistence result or adjusting the instance returned by the pipeline. However, "SQL has run" does not mean "the transaction has committed". If a service has a wrapping transaction, commit may happen after the repository method returns.

## 5. Order when reading and deleting aggregates

### 5.1. When reading

When Spring Data JDBC reads data and builds an aggregate:

~~~text
Run SELECT
    ↓
Read ResultSet
    ↓
Build aggregate root and properties
    ↓
AfterConvertEvent
    ↓
AfterConvertCallback
    ↓
Return aggregate to caller
~~~

`AfterConvertCallback` fits when you need to enrich a computed value or adjust the instance after mapping. Be careful about modifying data in a read callback: the same database row may be read across different use cases, so callbacks should behave consistently without side effects.

### 5.2. When deleting

Conceptual aggregate deletion flow:

~~~text
Start aggregate delete
    ↓
BeforeDeleteEvent
    ↓
BeforeDeleteCallback
    ↓
Execute SQL deleting root and child entities
    ↓
AfterDeleteEvent
    ↓
AfterDeleteCallback
~~~

One notable limitation: `BeforeDeleteCallback` and `AfterDeleteCallback` are only invoked when the delete method receives an **aggregate instance** as an argument. Delete-by-ID or argumentless delete operations do not trigger these two callbacks.

Example:

~~~java
repository.delete(order);       // Can trigger delete callbacks
repository.deleteById(orderId);  // Does not trigger delete callbacks
~~~

If logic must run in a delete callback, use a delete operation that accepts an aggregate instance. For delete by ID, an application service can load the aggregate first and then delete that object, if cost and business requirements allow.

## 6. Registering EntityCallback

Spring Data picks up callback beans registered in the `ApplicationContext`. You can use `@Component` or declare with `@Bean`.

Component example:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(100)
public class OrderTimestampCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order) {
        if (order.getCreatedAt() == null) {
            order.setCreatedAt(Instant.now());
        }

        return order;
    }
}
~~~

Bean registration example:

~~~java
@Configuration
public class OrderCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Order> orderCodeCallback() {
        return order -> {
            order.setCode(order.getCode().trim());
            return order;
        };
    }
}
~~~

In real systems, if a callback needs testable time, inject a `Clock` instead of calling `Instant.now()` directly. That lets tests control time values.

### 6.1. Callbacks by domain type

The generic type `Order` tells Spring Data which type the callback applies to. A callback can handle the declared type and compatible subtypes.

If a class implements multiple callback interfaces, it can handle multiple checkpoints in the same bean:

~~~java
@Component
public class OrderCallbacks
        implements BeforeConvertCallback<Order>,
                   AfterConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order) {
        // Prepare data before persistence.
        return order;
    }

    @Override
    public Order onAfterConvert(Order order) {
        // Enrich data after reading.
        return order;
    }
}
~~~

### 6.2. Ordering multiple callbacks

When there are multiple callbacks of the same type for a domain type, you can specify order with `@Order` or by implementing `Ordered`.

~~~java
@Component
@Order(10)
class FirstOrderCallback implements BeforeConvertCallback<Order> {
    @Override
    public Order onBeforeConvert(Order order) {
        order.setCode(order.getCode().trim());
        return order;
    }
}

@Component
@Order(20)
class SecondOrderCallback implements BeforeConvertCallback<Order> {
    @Override
    public Order onBeforeConvert(Order order) {
        order.setCode(order.getCode().toUpperCase());
        return order;
    }
}
~~~

Lower order values are called first. The next callback receives the result returned by the previous callback. In the example, the second callback receives the trimmed order.

Callbacks without explicit ordering may be called after ordered callbacks. Lambda callbacks do not expose generic type metadata the way class callbacks do, so use class/enum callbacks when effective and clear type filtering is needed.

## 7. Registering ApplicationEvent listeners

There are two common ways to receive lifecycle events.

### 7.1. Using @EventListener

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.data.relational.core.mapping.event.BeforeSaveEvent;
import org.springframework.data.relational.core.mapping.event.AfterSaveEvent;

@Component
public class OrderEventListener {

    @EventListener
    public void onBeforeSave(BeforeSaveEvent<Order> event) {
        log.info("About to save order {}", event.getEntity().getId());
    }

    @EventListener
    public void onAfterSave(AfterSaveEvent<Order> event) {
        log.info("Saved order {}", event.getEntity().getId());
    }
}
~~~

### 7.2. Using ApplicationListener

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;
import org.springframework.data.relational.core.mapping.event.AfterSaveEvent;

@Component
public class OrderSavedListener
        implements ApplicationListener<AfterSaveEvent<Order>> {

    @Override
    public void onApplicationEvent(AfterSaveEvent<Order> event) {
        Order order = event.getEntity();

        log.info("Order {} was persisted", order.getId());
    }
}
~~~

Using `@EventListener` fits when one class handles multiple event types. Using `ApplicationListener<E>` fits when you want a bean with an explicit listener contract for a single event type.

### 7.3. Events are only published for the aggregate root

Spring Data JDBC only emits lifecycle events for the aggregate root. An `OrderLine` inside `Order` does not emit its own `BeforeSaveEvent<OrderLine>` or separate callbacks. If you need to log or inspect order lines, read the collection from `event.getEntity()` on the root.

## 8. Custom ApplicationEvents and @TransactionalEventListener

Not every event in an application is a Spring Data lifecycle event. An application can publish its own business event via `ApplicationEventPublisher`.

For example, after creating an order, the service publishes `OrderPlacedEvent`:

~~~java
public record OrderPlacedEvent(Long orderId) {
}
~~~

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public Long placeOrder(Order order) {
        Order saved = orders.save(order);

        events.publishEvent(
            new OrderPlacedEvent(saved.getId())
        );

        return saved.getId();
    }
}
~~~

If a listener sends notifications to external systems, synchronous event publishing alone is not enough to guarantee the transaction has committed. Use `@TransactionalEventListener` to bind the listener to a transaction phase:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderPlaced(OrderPlacedEvent event) {
        notificationService.notifyOrderPlaced(event.orderId());
    }
}
~~~

By default, `@TransactionalEventListener` uses the `AFTER_COMMIT` phase. The listener only runs after the transaction commits successfully. Other phases include `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.

You can use `@TransactionalEventListener` with Spring Data JDBC lifecycle events because they are also ApplicationEvents. However, with dedicated business events like `OrderPlacedEvent`, application code depends less on persistence details.

If there is no active transaction, transactional listeners are not invoked by default. You can enable `fallbackExecution = true` if business requirements dictate the listener still runs without a transaction, though semantics should be considered carefully.

`AFTER_COMMIT` helps avoid sending notifications when a transaction rolls back. It is not a durable queue: if the process stops after commit but before the listener completes, the notification can still be lost. For reliable event delivery requirements, consider a Transactional Outbox or a durable message delivery mechanism.

## 9. Callback ordering and event ordering are not the same

Two kinds of ordering must be distinguished:

### Ordering between events and callbacks at the same checkpoint

Spring Data Commons specifies that store-specific ApplicationEvents are published before invoking the corresponding EntityCallbacks.

In the default synchronous event setup, for example at the pre-save checkpoint:

~~~text
BeforeSaveEvent is published
        ↓
ApplicationEvent listener is invoked
        ↓
BeforeSaveCallback is invoked
        ↓
SQL is executed
~~~

This is the pipeline order when event listeners process synchronously. If ApplicationEventMulticaster is configured with a TaskExecutor or a listener runs with `@Async`, event processing may occur on another thread and is no longer guaranteed to finish before the callback.

Therefore, do not put entity-modification logic that must complete into an asynchronous event listener.

### Ordering among multiple EntityCallbacks

Use `@Order` or `Ordered` to determine which callback runs first. Callbacks run sequentially; the instance returned by an earlier callback is the input to the next callback.

### Ordering among multiple ApplicationEvent listeners

Spring's event infrastructure can order listeners using `@Order`. However, listener ordering does not change the event's position in the persistence pipeline. If listeners are asynchronous, do not rely on completion order for correctness.

Do not use `@Order` to try coordinating an event listener and an EntityCallback as if they were in the same callback list. The two mechanisms have separate dispatching rules.

## 10. Synchronous and asynchronous

### EntityCallback

Spring Data JDBC's EntityCallback is an imperative callback invoked sequentially in the aggregate processing pipeline. It does not use `ApplicationEventMulticaster` to dispatch callbacks.

This lets Spring Data control checkpoints and pass callback return values to the next step.

### ApplicationEvent

Spring ApplicationEvents are dispatched through `ApplicationEventMulticaster`. The default configuration usually invokes listeners synchronously on the event-publishing thread. If a TaskExecutor is configured or `@Async` is used, listeners can run on a different thread.

| Characteristic | Callback | Synchronous event listener | Asynchronous event listener |
| --- | --- | --- | --- |
| Same thread as pipeline | Yes | Yes by default | Not necessarily |
| Completes before next step | Yes | Yes in synchronous setup | Not guaranteed |
| Returns modified entity to pipeline | Yes | No | No |
| Exceptions propagate directly through pipeline | Yes | Can propagate through publisher | Not propagated directly to caller in normal async flow |
| Suitable for modifying entities | Yes | Not recommended | No |
| Suitable for background work | No | Can slow down caller | Yes, if asynchronicity is acceptable |

Do not configure lifecycle events asynchronously if listeners must complete before the aggregate is persisted. Use callbacks for modifications that belong in the pipeline.

## 11. Trigger scope and skipped cases

Lifecycle callbacks and events are not invoked for every SQL statement an application executes.

### 11.1. Aggregate root only

Spring Data JDBC events and callbacks fire only for the aggregate root. Child entities are handled in the context of the root containing them.

### 11.2. Derived queries and annotated queries

Save/delete-related callbacks are not invoked for derived query operations or annotated queries that execute directly. Spring Data JDBC has no efficient way to determine all aggregates affected by such a query.

For example, a bulk update statement with `@Modifying` does not go through the same `save(aggregate)` pipeline:

~~~java
@Modifying
@Query("UPDATE purchase_orders SET status = :status WHERE id = :id")
int updateStatus(Long id, String status);
~~~

Do not assume `BeforeSaveCallback` or `AfterSaveCallback` will run for each aggregate updated by the SQL above. If the business requires auditing or notifications, perform them explicitly in the service/query workflow.

### 11.3. Deleting by ID

As noted, `BeforeDeleteCallback` and `AfterDeleteCallback` are only invoked when the delete method receives an aggregate instance. `deleteById` and instance-less deletes do not trigger those callbacks.

### 11.4. Custom RowMapper

If a query uses a custom `RowMapper`, `ResultSetExtractor`, or custom mapping, Spring Data JDBC cannot automatically apply full callbacks/events as it does with default mapping. Custom-mapped queries must handle hooks themselves if the use case requires them.

## 12. Choosing a mechanism by need

| Need | Should use |
| --- | --- |
| Normalize data before saving | `BeforeConvertCallback` |
| Programmatically assign ID to a new aggregate | `BeforeConvertCallback` |
| Intervene in `AggregateChange` before SQL runs | `BeforeSaveCallback` |
| Enrich data after aggregate is read | `AfterConvertCallback` |
| Log when aggregate is about to be saved | `BeforeSaveEvent` listener |
| Log after aggregate save SQL has run | `AfterSaveEvent` listener |
| Log when aggregate is deleted | `BeforeDeleteEvent` / `AfterDeleteEvent` |
| Send notification only after transaction commit | Application event + `@TransactionalEventListener(AFTER_COMMIT)` |
| Handle logic requiring a new immutable instance | EntityCallback |
| Emit business events between modules | Custom ApplicationEvent |

A practical rule of thumb:

- If processing output must affect the object being persisted or returned, use EntityCallback.
- If you only need to notify other components that a milestone occurred, use ApplicationEvent.
- If side effects depend on transaction commit, use a transactional event listener.
- If durable event delivery is required, use an outbox or suitable messaging infrastructure.

## 13. Testing execution order

You can write tests that record callback and event execution order using a shared list. Illustrative example:

~~~java
@Component
public class OrderBeforeConvertCallback
        implements BeforeConvertCallback<Order> {

    private final List<String> trace;

    public OrderBeforeConvertCallback(List<String> trace) {
        this.trace = trace;
    }

    @Override
    public Order onBeforeConvert(Order order) {
        trace.add("before-convert-callback");
        return order;
    }
}
~~~

Event listener:

~~~java
@Component
public class OrderBeforeConvertListener {

    private final List<String> trace;

    public OrderBeforeConvertListener(List<String> trace) {
        this.trace = trace;
    }

    @EventListener
    public void onBeforeConvert(BeforeConvertEvent<Order> event) {
        trace.add("before-convert-event");
    }
}
~~~

In the test configuration, provide a shared collection and invoke the repository in an appropriate test transaction. With the default synchronous event listener, the expected order at this checkpoint is:

~~~text
before-convert-event
before-convert-callback
~~~

This test illustrates the principle. With a real Spring context, ensure both beans receive the exact same trace instance and the event multicaster is not configured asynchronously.

To verify the full save pipeline, register additional listeners/callbacks for `BeforeSave` and `AfterSave`, then assert the order of corresponding checkpoints. Do not test the completion order of asynchronous event listeners using a simple sequential assertion; use a latch or dedicated test synchronization mechanism.

### Scenarios worth integration testing

1. BeforeConvert callback modifies the entity and that value is saved to the database.
2. Immutable entity is replaced by the instance returned from the callback.
3. BeforeSaveCallback is called after AggregateChange is created.
4. AfterConvertCallback is called when the repository reads the aggregate.
5. Event listener receives the right aggregate root type.
6. Events and callbacks run in order when the event multicaster is synchronous.
7. Transaction rollback does not trigger `AFTER_COMMIT` listeners.
8. `deleteById` does not invoke delete callbacks.
9. Modifying queries do not trigger save/delete callbacks.

## 14. Common mistakes

| Mistake | Cause | Solution |
| --- | --- | --- |
| Modifying entity in an event listener yet data does not change as expected | Events are notifications with no contract to return a new entity | Use EntityCallback |
| Callback does not run | Bean is not registered in ApplicationContext or generic type does not match | Register `@Component`/`@Bean` and check domain type |
| Assigning ID in BeforeSaveCallback yet insert does not use the ID | AggregateChange and ID strategy were already decided earlier | Assign ID in `BeforeConvertCallback` |
| Later callback does not see earlier callback's changes | Earlier callback did not return the modified instance | Return the right instance or a new instance |
| Event listener runs after callback even though event is published first | Event multicaster or listener is asynchronous | Use callbacks for logic needing deterministic ordering |
| Sending email despite transaction rollback | Standard listeners run before commit | Use `@TransactionalEventListener(AFTER_COMMIT)` |
| Callback does not run when using `@Modifying` | Query runs directly without going through the aggregate lifecycle | Invoke business logic in the service or handle audits/events explicitly |
| Delete callback does not run when calling deleteById | Callbacks require an aggregate instance as an argument | Load the aggregate and call `delete(entity)` if callbacks are needed |
| Callback runs for root yet does not run for child | Lifecycle hooks apply only to the aggregate root | Process children through the root |
| Unstable callback order | Missing order declaration when multiple callbacks exist | Use `@Order` or `Ordered` |
| Async event listener loses transaction context | Listener runs on a different thread | Use a transactional listener or pass event data explicitly |

## 15. Practice exercises

### Exercise 1 — Compare the two mechanisms

Create a `BeforeConvertCallback<Order>` and a `BeforeConvertEvent<Order>` listener. Record execution order when saving an aggregate. Explain why the callback is more suitable if you need to modify the object before persistence.

### Exercise 2 — Immutable entity

Convert `Order` to a record. Write a callback creating a new record with an updated `updatedAt` field. Verify the value returned by the callback is used in the pipeline.

### Exercise 3 — Callback ordering

Create two `BeforeConvertCallback`s with `@Order(10)` and `@Order(20)`. Have the second callback rely on the first callback's output. Observe the order and final value.

### Exercise 4 — Save lifecycle

Register listeners for `BeforeConvertEvent`, `BeforeSaveEvent`, and `AfterSaveEvent`. Log the time each event is received and compare with the corresponding callbacks.

### Exercise 5 — Transaction commit

Publish a custom `OrderPlacedEvent` inside a `@Transactional` method. Write a standard listener and a `@TransactionalEventListener(AFTER_COMMIT)` listener. Trigger a rollback scenario to compare.

### Exercise 6 — Delete callbacks

Try `repository.delete(order)` and `repository.deleteById(id)`. Observe which callbacks are invoked. Explain the difference based on callbacks requiring an aggregate instance.

### Exercise 7 — Modifying query

Write a `@Modifying @Query` method to update order status. Confirm save callbacks do not run automatically and decide where to place auditing/notifications.

### Exercise 8 — Async event

Configure an asynchronous event listener. Observe that the event may complete after the callback or after the save method returns. Explain why entity-modification logic belongs in EntityCallback.

## 16. Official references

- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html): lifecycle events, supported callbacks, and ordering of persist/load/delete stages.
- [Spring Data Commons — Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html): how to implement, register, and order EntityCallbacks; ordering relationship between events and callbacks.
- [Spring Data Relational — BeforeConvertCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeConvertCallback.html): callback timing and why to use it for assigning IDs.
- [Spring Data Relational — BeforeSaveCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html): callback after AggregateChange is created.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): using `@TransactionalEventListener` to handle events by transaction phase.
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): event publish/subscribe mechanism in ApplicationContext and synchronous/asynchronous execution.

EntityCallback and ApplicationEvent both participate in Spring Data JDBC's lifecycle yet have distinct responsibilities. Callbacks are ordered extension points that return an entity for the pipeline to keep processing; events are notifications for listeners. Understanding the event-before-callback order at each checkpoint, where AggregateChange is built, when SQL executes, and transaction boundaries helps place the right logic in the right spot and avoid relying on uncommitted side effects.
