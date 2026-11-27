# Callback Scope on Aggregate Root and Handling Child Components

In **Spring Data Relational JDBC (Spring Data JDBC)**, entity callbacks and lifecycle events are emitted per **aggregate root**. When Spring Data JDBC saves, loads, or deletes an aggregate, the callback receives the root object representing the whole aggregate. Child objects such as OrderLine or Address stored in separate tables still belong to the same aggregate, yet do not receive an independent callback invocation per object.

This has direct implications when an application wants to normalize data, assign audit timestamps, validate state, or record actions on child components. To process a child entity, a callback must go through the aggregate root containing it, then invoke behavior on the root or iterate over the child collection. You cannot register a callback for a child type and expect Spring Data JDBC to automatically invoke that callback each time a child is inserted/updated/deleted while saving the aggregate.

## 1. Aggregate root and child components

Suppose an order consists of an Order root and a list of OrderLine items:

~~~text
Order (aggregate root)
├── id
├── status
├── createdAt
└── lines
    ├── OrderLine
    │   ├── sku
    │   └── quantity
    └── OrderLine
        ├── sku
        └── quantity
~~~

Order is the entry point of the aggregate. OrderLine may be stored in a separate table, yet the lifecycle of the lines is managed through Order. When calling a repository to save Order, Spring Data JDBC generates the necessary SQL operations for the root and child components.

~~~mermaid
flowchart TB
    Repo["OrderRepository.save(order)"]
    Callback["BeforeConvertCallback<Order>"]
    Root["Aggregate root: Order"]
    Child["Order.lines<br/>OrderLine objects"]
    Mapping["Spring Data JDBC<br/>aggregate mapping"]
    SQL["SQL actions for root<br/>and owned children"]
    DB[("Database")]
    After["AfterSaveCallback<Order>"]
    Repo --> Callback --> Root
    Root --> Child
    Root --> Mapping
    Child --> Mapping
    Mapping --> SQL --> DB --> After
~~~

The callback has generic type `BeforeConvertCallback<Order>`. When the callback receives Order, it can read and modify data in the lines list through the aggregate's API. Spring Data JDBC does not automatically invoke an additional `BeforeConvertCallback<OrderLine>` for each element.

## 2. Which callbacks and events are supported?

Spring Data JDBC provides callbacks at key milestones of the aggregate lifecycle:

| Operation | Callback | Timing |
|---|---|---|
| Save | `BeforeConvertCallback<T>` | After determining insert/update, before building the SQL plan |
| Save | `BeforeSaveCallback<T>` | After the aggregate has been converted into AggregateChange, before running SQL |
| Save | `AfterSaveCallback<T>` | After the SQL operations saving the aggregate have run |
| Read | `AfterConvertCallback<T>` | After the aggregate has been built from ResultSet and properties have been mapped |
| Delete | `BeforeDeleteCallback<T>` | Before deleting the aggregate |
| Delete | `AfterDeleteCallback<T>` | After deleting the aggregate |

The callbacks above receive the aggregate root. Corresponding lifecycle events are also emitted for the root, including `BeforeConvertEvent`, `BeforeSaveEvent`, `AfterSaveEvent`, `AfterConvertEvent`, `BeforeDeleteEvent`, and `AfterDeleteEvent`.

In modern versions, the post-mapping read callback is `AfterConvertCallback`. Some older versions had `AfterLoadCallback` or `AfterLoadEvent` which have been replaced/deprecated; use the API appropriate for your project's Spring Data Relational version.

## 3. Callback scope: root is invoked, children are not invoked separately

Suppose an aggregate has one Order and three OrderLines:

~~~text
Order #501
  lines:
    OrderLine #1
    OrderLine #2
    OrderLine #3
~~~

When saving the aggregate, the callback receives one Order object:

~~~java
public class OrderBeforeConvertCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order) {
        // Invoked once for the aggregate root Order.
        // order.getLines() can be accessed here.
        return order;
    }
}
~~~

The callback is not invoked three additional times for the OrderLines. This remains true even though each OrderLine is written as a row in the `order_lines` table.

| Component | Separate callback during Order save? | Can be processed via root callback? |
|---|---:|---:|
| Order root | Yes | Yes |
| OrderLine belonging to Order | No | Yes |
| Address embedded in Order | No | Yes |
| Customer as another aggregate, referenced only by ID | No in Order callback | Not part of Order's object graph; must be handled separately |

Important distinction: a root callback can traverse child objects that actually live inside the aggregate object graph. It does not automatically load another aggregate referenced by a scalar ID.

## 4. Aggregate structure with a child collection

Example Order entity:

~~~java
package com.example.sales.order;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_orders")
public class Order {

    @Id
    private Long id;

    private String status;
    private Instant updatedAt;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();

    protected Order() {
    }

    public Order(List<OrderLine> lines) {
        this.status = "DRAFT";
        this.lines.addAll(lines);
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }

    public void prepareForPersistence(Instant now) {
        this.updatedAt = now;
        lines.forEach(line -> line.prepareForPersistence(now));
    }
}
~~~

Child entity:

~~~java
package com.example.sales.order;

import java.time.Instant;

public class OrderLine {

    private String sku;
    private int quantity;
    private Instant updatedAt;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void prepareForPersistence(Instant now) {
        this.updatedAt = now;
    }
}
~~~

The `Order.prepareForPersistence` method is behavior of the aggregate root. It updates metadata on the root and invokes the corresponding behavior on each line. The callback only needs to call one method on Order; the root coordinates its child components itself.

## 5. Processing root and children in BeforeConvertCallback

`BeforeConvertCallback` is the right hook when you want to modify the aggregate before Spring Data JDBC converts it into a plan of database operations. Therefore, if you need to normalize or update data on children before saving, do it at this stage.

~~~java
package com.example.sales.order;

import java.time.Clock;

import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderBeforeConvertCallback
        implements BeforeConvertCallback<Order> {

    private final Clock clock;

    public OrderBeforeConvertCallback(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Order onBeforeConvert(Order aggregate) {
        aggregate.prepareForPersistence(clock.instant());
        return aggregate;
    }
}
~~~

When the repository saves Order:

1. Spring Data JDBC determines whether the aggregate is new or existing.
2. The callback receives the Order root.
3. The callback calls `prepareForPersistence`, updating `updatedAt` on the root and all existing OrderLines in the aggregate.
4. Spring Data JDBC converts the prepared aggregate into write operations.
5. SQL for root and children is executed.

Do not create a `BeforeConvertCallback<OrderLine>` to process each line. Keep line-lifecycle logic inside OrderLine and have Order invoke that logic.

### Why use Clock instead of calling Instant.now() directly?

Injecting `Clock` lets tests control time:

~~~java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
~~~

Tests can supply a fixed Clock to verify timestamps on root and children without depending on execution timing.

## 6. BeforeSaveCallback occurs after the aggregate has been converted

The save flow has two pre-SQL hooks, yet they occur at different times:

~~~mermaid
flowchart TD
    A["Determine new or existing aggregate"]
    B["BeforeConvertCallback"]
    C["Create AggregateChange / DbAction"]
    D["BeforeSaveCallback"]
    E["Execute SQL"]
    F["AfterSaveCallback"]
    A --> B --> C --> D --> E --> F
~~~

`BeforeConvertCallback` runs before creating AggregateChange. This is the right place to modify the entity and children before the framework decides the write operations.

`BeforeSaveCallback` runs after the aggregate has been converted into `MutableAggregateChange`. This callback receives both the aggregate root and the change plan:

~~~java
import org.springframework.data.relational.core.mapping.event.BeforeSaveCallback;
import org.springframework.data.relational.core.conversion.MutableAggregateChange;
import org.springframework.stereotype.Component;

@Component
public class OrderBeforeSaveCallback
        implements BeforeSaveCallback<Order> {

    @Override
    public Order onBeforeSave(
            Order aggregate,
            MutableAggregateChange<Order> aggregateChange) {

        // Can inspect the aggregate or adjust AggregateChange
        // for advanced persistence cases.
        return aggregate;
    }
}
~~~

At this stage, the insert/update decision and DbActions have already been created. Modifying properties on root/child objects here is not a reliable way to change data already placed into the change plan. If the goal is to normalize the entity or update child fields, do it in `BeforeConvertCallback`. Only use `MutableAggregateChange` when you genuinely need to intervene in the persistence plan and understand the API of your version.

One important case: if you want to assign an ID manually for a new aggregate, do it in `BeforeConvertCallback`. By the time `BeforeSaveCallback` runs, the decision of whether the ID is sent to the database or generated by the database has already been made.

## 7. AfterSaveCallback also receives only the aggregate root

After the SQL statements saving the aggregate have executed, Spring Data JDBC invokes `AfterSaveCallback` with the root:

~~~java
import org.springframework.data.relational.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderAfterSaveCallback
        implements AfterSaveCallback<Order> {

    @Override
    public Order onAfterSave(Order aggregate) {
        // Can observe the root after the save operation.
        // aggregate.getLines() still provides access to the child graph.
        return aggregate;
    }
}
~~~

If you need to log the total number of order lines, the callback can use `aggregate.getLines().size()`. There is no separate AfterSave callback per OrderLine.

Do not treat `AfterSaveCallback` as a post-transaction-commit hook. The callback runs after the aggregate's SQL operations, yet the outer transaction may still be uncommitted. If the transaction later rolls back, a side effect already sent to an external system from the callback is not automatically undone.

Therefore, avoid sending emails, making HTTP calls, publishing messages directly, or performing non-rollbackable side effects in callbacks. For post-commit notifications, consider a transactional event listener or a transactional outbox.

## 8. AfterConvertCallback when an aggregate is loaded

When Spring Data JDBC reads an aggregate, the framework runs the necessary queries, maps the root and child components, and then invokes `AfterConvertCallback`:

~~~java
import org.springframework.data.relational.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderAfterConvertCallback
        implements AfterConvertCallback<Order> {

    @Override
    public Order onAfterConvert(Order aggregate) {
        // Aggregate and properties have been mapped.
        // aggregate.getLines() can be accessed.
        return aggregate;
    }
}
~~~

This callback can be used to:

- Compute a transient value from loaded properties.
- Normalize an in-memory representation if that rule is appropriate.
- Check invariants that should be detected immediately after reading.

Do not use this callback to load a Customer aggregate or call an external service for each Order. Doing so easily creates N+1 queries, network dependencies, and unpredictable read latency for a single aggregate.

If display data comes from another aggregate, let the application service/query layer coordinate explicitly. If values can be computed in SQL or belong in a read model, consider a dedicated projection/query.

## 9. Processing children in the post-read callback

Because `AfterConvertCallback<Order>` receives the constructed root, you can invoke a root method to process the lines:

~~~java
@Override
public Order onAfterConvert(Order aggregate) {
    aggregate.recalculateTransientSummary();
    return aggregate;
}
~~~

Root example:

~~~java
public void recalculateTransientSummary() {
    // Compute in-memory-only data from loaded lines.
    this.lineCount = lines.size();
}
~~~

If the summary is persistent data that must be stored, do not only compute it in AfterConvert and expect that value to automatically be written back to the database. AfterConvert happens on the read flow; updating persistent data requires a separate write use case or computing it in the database when querying.

## 10. Callbacks when deleting an aggregate

Spring Data JDBC has `BeforeDeleteCallback` and `AfterDeleteCallback`. They also work with the aggregate root:

~~~java
import org.springframework.data.relational.core.mapping.event.BeforeDeleteCallback;
import org.springframework.data.relational.core.mapping.event.AfterDeleteCallback;
import org.springframework.data.relational.core.conversion.MutableAggregateChange;
import org.springframework.stereotype.Component;

@Component
public class OrderDeleteCallback
        implements BeforeDeleteCallback<Order>, AfterDeleteCallback<Order> {

    @Override
    public Order onBeforeDelete(
            Order aggregate,
            MutableAggregateChange<Order> aggregateChange) {

        // Can inspect the root and traverse the child graph if needed.
        // Do not rely on persistent mutations on the aggregate to change
        // the already-built delete decision.
        return aggregate;
    }

    @Override
    public Order onAfterDelete(Order aggregate) {
        // Aggregate root has been deleted.
        return aggregate;
    }
}
~~~

There is an important limitation: delete callbacks are only invoked when the delete method receives an **aggregate instance** as a parameter, such as `repository.delete(order)`. Delete-by-ID or parameterless delete operations such as `deleteById(id)`/`deleteAll()` do not invoke these delete callbacks because the framework has no aggregate instance to pass to the callback.

This also means callbacks are not the place to guarantee that every delete path in the application runs the same logic. If business requirements demand pre-delete checks or auditing for every deletion path, place rules in the application service and control which write/delete paths are permitted.

## 11. Do children need their own callbacks?

No. If a child needs processing before saving, place the behavior on the child and let the root coordinate it:

~~~java
public class OrderLine {

    private String sku;
    private int quantity;
    private String normalizedSku;

    public void normalize() {
        this.normalizedSku = sku == null
            ? null
            : sku.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Root:

~~~java
public void prepareForPersistence(Instant now) {
    this.updatedAt = now;
    lines.forEach(line -> {
        line.normalize();
        line.markUpdated(now);
    });
}
~~~

Callback:

~~~java
@Override
public Order onBeforeConvert(Order aggregate) {
    aggregate.prepareForPersistence(clock.instant());
    return aggregate;
}
~~~

This design keeps responsibilities clear:

- Order decides when lines are prepared together with the aggregate.
- OrderLine knows how to normalize its own data.
- The callback connects the persistence lifecycle to aggregate behavior.

Do not put critical business logic only inside callbacks if it must run even when the domain is modified outside Spring Data JDBC. Rules that must always hold should live in domain methods/factories; callbacks are only suitable for persistence-lifecycle tasks like audit metadata or preparing save data.

## 12. How do EntityCallback and ApplicationEvent differ?

Spring Data JDBC provides both entity callbacks and lifecycle events. They have different goals:

| Criterion | EntityCallback | Lifecycle event |
|---|---|---|
| Purpose | Intervene or transform an entity during the lifecycle | Notify that a lifecycle phase has occurred |
| Can return modified entity | Yes | Events have no mechanism to return a replacement entity |
| Processing order | Along the callback pipeline; controllable via order | Depends on ApplicationEventMulticaster |
| Asynchronous processing | Spring Data JDBC synchronous callbacks run on the persistence thread | Event listeners can be configured to run async |
| Suitable for | Entity normalization, audit fields, pre-persistence checks | Logging, metrics, notifications, and event integration |
| Scope | Aggregate root | Aggregate root |

Entity callbacks are the right choice when you need to modify an object, especially immutable entities because callbacks can return a new instance. Lifecycle events fit notifications. If ApplicationEventMulticaster runs async, do not assume listeners complete before the persistence operation proceeds.

Example listener receiving a pre-save event:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.data.relational.core.mapping.event.BeforeSaveEvent;
import org.springframework.stereotype.Component;

@Component
public class OrderSaveListener
        implements ApplicationListener<BeforeSaveEvent<Order>> {

    @Override
    public void onApplicationEvent(BeforeSaveEvent<Order> event) {
        Order order = event.getEntity();
        // Observe/notify only; the event contains only the aggregate root.
    }
}
~~~

If a listener needs to run after commit, you can use `@TransactionalEventListener(phase = AFTER_COMMIT)` for business events emitted by the application. Do not confuse the AfterSave lifecycle callback with transaction commit time.

## 13. Are callbacks invoked for derived queries and @Query?

Not every SQL operation in a repository passes through the aggregate lifecycle. Spring Data JDBC cannot always determine precisely which aggregates are affected by a custom query or derived modifying query. Therefore, **save/delete-related callbacks and events are not invoked for derived query methods or methods declared with @Query** under the behavior documented by Spring Data JDBC.

Example:

~~~java
@Modifying
@Query("UPDATE sales_orders SET status = :status WHERE customer_id = :customerId")
int updateStatusForCustomer(String status, Long customerId);
~~~

This is a direct bulk update. Do not assume Spring Data JDBC will load each Order, call BeforeConvert/BeforeSave for each root, and only then run the SQL statement. Child rows are likewise not automatically routed through callbacks.

If a bulk update needs auditing/versioning/side effects:

- Place the necessary logic in SQL or an explicit application service workflow.
- Update audit columns/version inside the statement if required.
- Write outbox/audit records in the same transaction when guarantees are needed.
- Or load each aggregate and save through the repository if full domain lifecycle execution is mandatory, accepting the higher cost.

Do not rely on callbacks as a global database trigger. Write paths via JdbcTemplate, SQL scripts, stored procedures, or other applications also do not trigger Spring Data JDBC callbacks automatically.

## 14. Callback ordering and multiple callbacks of the same type

Entity callbacks are executed by Spring Data in a synchronous pipeline. If multiple beans implement the same callback for the same domain type, you can use `@Order` or `Ordered` to determine execution order:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class OrderNormalizeCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order aggregate) {
        aggregate.normalize();
        return aggregate;
    }
}
~~~

~~~java
@Component
@Order(20)
public class OrderAuditCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order aggregate) {
        aggregate.updateAuditMetadata();
        return aggregate;
    }
}
~~~

The example puts normalization before auditing. If a later callback depends on an earlier callback's output, declare explicit ordering instead of relying on bean discovery order.

Lambda callbacks do not expose generic type information as clearly as class implementations in certain callback-filtering scenarios. For callbacks intended to apply reliably to a specific domain type, class beans make code easier to read and type-resolution clearer.

## 15. Performance and responsibility boundaries

Callbacks run on the aggregate persistence path. When a query loads thousands of aggregates, read callbacks may run many times. A heavy callback can dramatically alter read latency.

Avoid the following inside callbacks:

- Making HTTP calls or accessing external services.
- Querying another repository for each child.
- Running repeated auxiliary queries to compute data obtainable in one query.
- Traversing large structures multiple times unnecessarily.
- Sending messages/emails before the transaction commits.
- Implementing business logic that other write paths bypass.

Callbacks should be short, deterministic, easy to test, and tied to a specific lifecycle checkpoint. Domain logic belongs in the aggregate; orchestration across multiple aggregates belongs in the application service.

## 16. Testing callback scope on root and children

A useful test verifies that the callback is invoked only for the root even when the aggregate has multiple children:

~~~java
@Test
void beforeConvertCallbackReceivesAggregateRoot() {
    Order order = new Order(List.of(
        new OrderLine("SKU-1", 2),
        new OrderLine("SKU-2", 3),
        new OrderLine("SKU-3", 1)
    ));

    Order result = callback.onBeforeConvert(order);

    assertThat(result).isSameAs(order);
    assertThat(result.getUpdatedAt()).isNotNull();
    assertThat(result.getLines())
        .allSatisfy(line ->
            assertThat(line.getUpdatedAt()).isNotNull()
        );
}
~~~

Beyond unit tests for callbacks, integration tests should verify:

1. Saving an Order with multiple OrderLines: the root callback runs per aggregate, not separately per line.
2. Loading Order: AfterConvertCallback receives the root already populated with the child collection.
3. Deleting by instance: BeforeDelete/AfterDelete callbacks are invoked.
4. Deleting by ID: do not expect instance-delete callbacks to be invoked.
5. Derived delete or `@Query` bulk update: do not expect save/delete lifecycle callbacks to run for each affected root.
6. Transaction rollback after save: do not treat AfterSaveCallback as proof data committed.
7. Multiple callbacks of the same type: verify order via `@Order`.

Tests should inspect both database data and callback invocation counts. Checking only that a callback ran does not prove child data was prepared or persisted properly.

## 17. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Registering a callback for a child type and expecting Spring to invoke it per child | Child callback is never called by the aggregate lifecycle | Register callbacks for the root and traverse the child graph |
| Thinking each child table row is an aggregate root | Wrong persistence scope design | Distinguish aggregate-owned children from independent aggregates |
| Modifying children in BeforeSave after the change plan was built | Changed values may not be reflected in DbActions | Modify root/children in BeforeConvert |
| Generating a new ID in BeforeSave | Insert decision and ID strategy were already decided | Generate IDs in BeforeConvert |
| Using AfterSave as an after-commit hook | Side effects may happen even if the transaction later rolls back | Use transactional events/outbox |
| Using callbacks to load other aggregates | N+1 queries and coupling between aggregates | Use application service/query layer |
| Thinking deleteById invokes BeforeDeleteCallback | Delete callbacks have no aggregate instance to receive | Use delete(instance) if callbacks are needed or handle in service |
| Relying on callbacks for bulk `@Query`/derived deletes | Affected aggregates do not go through per-root callbacks | Place logic in appropriate queries/services/outbox |
| Using async event listeners to modify entities | Changes may happen too late or not be used by persistence | Use EntityCallback to transform entities |
| Sending emails/messages inside callbacks | Side effects do not roll back with the database | Emit events after commit or use an outbox |
| Putting too much logic into callbacks | Domain is hard to run outside Spring Data JDBC | Move invariants into aggregate/domain methods |
| Callback runs auxiliary queries for each root | Load time scales with aggregate count | Compute data in queries or batch loads |

## 18. Practice exercises

1. Create an Order aggregate root with an OrderLine collection using `@MappedCollection`.
2. Write a `BeforeConvertCallback<Order>` and verify it receives the Order root.
3. On the root, write `prepareForPersistence(Instant now)` to update audit timestamps for the root and each line.
4. Save an Order with three lines; inspect timestamps of both root and children in the database.
5. Write an `AfterConvertCallback<Order>` and verify the line collection is already mapped when the callback runs.
6. Write a `BeforeSaveCallback<Order>`; observe that the callback receives `MutableAggregateChange` after the change plan is built.
7. Try placing ID assignment in BeforeConvert and compare with assigning an ID in BeforeSave.
8. Write `BeforeDeleteCallback<Order>` and `AfterDeleteCallback<Order>`; call `delete(instance)` to test.
9. Call `deleteById` and confirm instance-delete callbacks do not run.
10. Write a bulk `@Query` update and verify save/delete callbacks are not invoked for each affected Order.
11. Register two `BeforeConvertCallback`s with different `@Order` values and record execution order.
12. Write an event listener only to log the root; do not modify entities in the listener.
13. Force a transaction rollback after a save operation and demonstrate that AfterSaveCallback does not mean the transaction committed.
14. Design an outbox event written in the same transaction and published after commit.

## 19. Takeaways

Spring Data JDBC invokes lifecycle callbacks and events on the **aggregate root**. Child entities are still saved/loaded/deleted with the aggregate according to mapping, yet have no independent per-child callbacks. When child processing is needed, the root callback must traverse the object graph or call domain behavior coordinated by the root.

For saves, use BeforeConvert to prepare root and children before building the SQL plan; BeforeSave runs after AggregateChange is created; AfterSave runs after the aggregate's SQL executes. For reads, AfterConvert runs after the aggregate is built. For deletes, delete callbacks run only when deleting by aggregate instance; delete by ID or bulk queries do not provide per-root callbacks.

Use EntityCallback when you need to transform entities in an ordered pipeline. Use lifecycle events for notification/observation. Keep callbacks short and avoid external side effects outside transactions; if post-commit notifications are needed, use transactional events or an outbox.

## References

- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html)
- [Spring Data Relational — Entity Callbacks](https://docs.spring.io/spring-data/relational/reference/commons/entity-callbacks.html)
- [BeforeConvertCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeConvertCallback.html)
- [BeforeSaveCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html)
- [BeforeDeleteCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeDeleteCallback.html)
