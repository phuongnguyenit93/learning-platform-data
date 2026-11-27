# BeforeSaveCallback, AfterSaveCallback, and AggregateChange

In Spring Data JDBC, saving an aggregate is more than sending a single INSERT or UPDATE statement. Spring Data first determines whether the aggregate is new or already exists, converts the aggregate into a plan of database operations, executes that plan, and then returns the result to the caller. **BeforeSaveCallback**, **AfterSaveCallback**, and **AggregateChange** provide extension points to observe or adjust this process.

These three concepts are directly related yet have distinct roles:

- **BeforeSaveCallback** runs after Spring Data has created the change plan, but before SQL is executed.
- **AggregateChange** describes the operations needed to save or delete the entire aggregate.
- **AfterSaveCallback** runs after the aggregate's SQL operations have been executed and can return a modified instance to the caller.

These callbacks are invoked for the aggregate root on the persistence path managed by Spring Data JDBC. They do not run automatically for every SQL statement in the application; in particular, derived queries and `@Query` methods do not trigger save callbacks.

## 1. Position of callbacks in the aggregate save lifecycle

When the application calls `repository.save(aggregate)` or saves an aggregate through `JdbcAggregateTemplate`, Spring Data JDBC performs the following general flow:

1. Determine whether the aggregate is new or existing to decide INSERT or UPDATE.
2. Invoke BeforeConvertCallback and publish BeforeConvertEvent.
3. Convert the aggregate into an AggregateChange containing the DbActions to execute.
4. Invoke BeforeSaveCallback and publish BeforeSaveEvent.
5. Execute the SQL statements corresponding to the change plan.
6. Invoke AfterSaveCallback and publish AfterSaveEvent.

~~~mermaid
flowchart TD
    A[repository.save aggregate] --> B[Decide INSERT or UPDATE]
    B --> C[BeforeConvertCallback]
    C --> D[Create AggregateChange and DbAction]
    D --> E[BeforeSaveCallback]
    E --> F[Execute SQL]
    F --> G[AfterSaveCallback]
    G --> H[Return saved aggregate]
~~~

This order matters because each callback sees a different state:

- BeforeConvertCallback receives the aggregate before it is converted into an SQL plan.
- BeforeSaveCallback receives the aggregate and the already-created change plan.
- AfterSaveCallback receives the aggregate after the SQL statements have run.

If you need to assign an application-generated ID before Spring Data decides whether the ID value is sent to the database, use BeforeConvertCallback. BeforeSaveCallback runs after the insert/update decision and after the plan has been created, so it is not the right place to generate a new ID.

## 2. What is AggregateChange?

AggregateChange resides in the `org.springframework.data.relational.core.conversion` package. It represents the changes needed on an aggregate along the aggregate root boundary.

An aggregate may consist of a root and child entities mapped via `@MappedCollection`. When saving the root, Spring Data JDBC generates `DbAction`s to represent the necessary operations, such as:

- Inserting a new aggregate root.
- Updating an existing aggregate root.
- Inserting new child entities.
- Updating or deleting child entities based on collection state.
- Deleting rows belonging to the aggregate in an order consistent with dependency relationships.

AggregateChange is a persistence plan model, not a single SQL statement. A single root save can generate multiple DbActions and multiple SQL statements.

The AggregateChange API provides methods to inspect the plan:

| API | Meaning |
|---|---|
| getKind() | Type of aggregate change, e.g., save or delete |
| getEntityType() | Type of the aggregate root |
| forEachAction(consumer) | Iterate over the DbActions in the plan |

In the BeforeSave callback, the concrete parameter is `MutableAggregateChange<T>`. MutableAggregateChange extends AggregateChange and allows modifying the plan, such as adding a DbAction via `addAction(...)`. Therefore, when discussing the callback contract, distinguish the general read interface AggregateChange from the mutable type received by BeforeSaveCallback.

## 3. Aggregate root example

Suppose an application manages purchase orders:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Version Long version,
        String orderNumber,
        String status,
        BigDecimal total,
        Instant createdAt
) {}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

A save call:

~~~java
PurchaseOrder order = new PurchaseOrder(
        null,
        null,
        "PO-2026-001",
        "NEW",
        new BigDecimal("250.00"),
        Instant.now()
);

PurchaseOrder saved = repository.save(order);
~~~

Spring Data JDBC detects the new entity according to the repository's detection rules, builds a plan to insert the root, and executes SQL. After the database generates the ID, the aggregate is returned with the corresponding ID/version information according to the mapping.

Callbacks for PurchaseOrder can observe the stages of this save without rewriting the entire repository.

## 4. BeforeSaveCallback: runs after the change plan is created

BeforeSaveCallback belongs to the package:

~~~java
org.springframework.data.relational.core.mapping.event
~~~

Signature in current Spring Data Relational:

~~~java
public interface BeforeSaveCallback<T> {
    T onBeforeSave(T aggregate, MutableAggregateChange<T> aggregateChange);
}
~~~

The callback receives two arguments:

- The aggregate root being saved.
- The MutableAggregateChange containing the DbActions created for that save.

The callback can return the same aggregate or a different instance; it can also observe or adjust MutableAggregateChange before the SQL operations are executed.

Example callback logging the plan:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.relational.core.conversion.MutableAggregateChange;
import org.springframework.data.relational.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderBeforeSaveCallback
        implements BeforeSaveCallback<PurchaseOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(PurchaseOrderBeforeSaveCallback.class);

    @Override
    public PurchaseOrder onBeforeSave(
            PurchaseOrder aggregate,
            MutableAggregateChange<PurchaseOrder> aggregateChange
    ) {
        log.debug(
                "Saving aggregate type={}, kind={}",
                aggregateChange.getEntityType().getSimpleName(),
                aggregateChange.getKind()
        );

        aggregateChange.forEachAction(action ->
                log.debug(
                        "Planned database action: {}",
                        action.getClass().getSimpleName()
                )
        );

        return aggregate;
    }
}
~~~

This is a useful spot to log the persistence plan, inspect the change kind, or add a specialized DbAction when the application genuinely needs deep control over the save process.

### Why is the parameter MutableAggregateChange?

AggregateChange describes the plan and provides iteration over operations. MutableAggregateChange extends that interface with the ability to add actions. BeforeSaveCallback needs the mutable type because the callback can adjust the plan before SQL runs.

Do not modify DbActions arbitrarily. Actions may depend on IDs generated by previous actions, property paths within the aggregate, insert/delete ordering, and optimistic locking. Adding an invalid action can corrupt persistence ordering or break aggregate consistency.

If you only need to observe the plan, use `forEachAction` and do not modify it.

## 5. BeforeSaveCallback differs from BeforeConvertCallback

These two callbacks have similar names but run at two different times:

| Callback | Timing | Suitable for |
|---|---|---|
| BeforeConvertCallback | Before the aggregate is converted into a DbAction plan | Normalizing or changing aggregate data before generating SQL actions; assigning application-managed IDs |
| BeforeSaveCallback | After AggregateChange/DbActions have been created, before SQL runs | Observing or adjusting the generated persistence plan |
| AfterSaveCallback | After SQL actions have been executed | Observing save results, using populated ID/version info, producing the returned instance |

For example, if you want to assign an order number when missing:

~~~java
import java.util.UUID;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderBeforeConvertCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(PurchaseOrder aggregate) {
        if (aggregate.orderNumber() != null
                && !aggregate.orderNumber().isBlank()) {
            return aggregate;
        }

        return new PurchaseOrder(
                aggregate.id(),
                aggregate.version(),
                "PO-" + UUID.randomUUID(),
                aggregate.status(),
                aggregate.total(),
                aggregate.createdAt()
        );
    }
}
~~~

The example demonstrates modifying the aggregate before creating the save plan. For database-generated IDs, do not assign an ID yourself in this callback if the application wants Spring Data JDBC to let the database supply the ID. If the application uses client/application-generated IDs, follow the entity's ID strategy and `isNew` rules.

BeforeSaveCallback runs later. Modifying the aggregate returned from this callback is not a reliable way to alter DbActions already built from prior data. If the goal is to change persistent properties before the SQL plan is constructed, use BeforeConvertCallback.

## 6. Adjusting MutableAggregateChange

MutableAggregateChange has APIs such as `addAction(DbAction<?>)`. For concrete RootAggregateChange types, the API may also provide operations to set the root or root action. These are low-level APIs intended for cases requiring custom persistence integration.

AggregateChange allows iterating over actions:

~~~java
aggregateChange.forEachAction(action -> {
    // Observe a DbAction in the plan.
});
~~~

MutableAggregateChange allows adding an action:

~~~java
mutableAggregateChange.addAction(customDbAction);
~~~

The second snippet only shows the API shape, not a complete example of constructing a DbAction. Constructing a valid DbAction requires knowing the action type, root, property path, dependent IDs, metadata, and execution order. Do not add actions manually just to write simple audit logs when an application service or transactional outbox can express the use case more clearly.

### AggregateChange is not a business change log

The DbAction plan describes the persistence operations Spring Data JDBC needs to perform. It does not necessarily capture full business semantics such as "order was paid", "customer changed address", or "inventory was reserved".

Do not use the list of DbActions as a stable domain event to emit externally. Action structures may change when aggregate mapping, framework versions, or collection-saving strategies change. If domain events are needed, model them in business terms and publish them via an appropriate mechanism.

## 7. AfterSaveCallback: runs after SQL is executed

AfterSaveCallback belongs to the `org.springframework.data.relational.core.mapping.event` package.

Signature:

~~~java
public interface AfterSaveCallback<T> {
    T onAfterSave(T aggregate);
}
~~~

The callback receives the saved aggregate. For an insert using a generated ID, the instance passed to the after-save stage can carry the ID received from the database. If the aggregate has `@Version`, the version is also managed by Spring Data JDBC on the standard save path.

Example:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.relational.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderAfterSaveCallback
        implements AfterSaveCallback<PurchaseOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(PurchaseOrderAfterSaveCallback.class);

    @Override
    public PurchaseOrder onAfterSave(PurchaseOrder aggregate) {
        log.info(
                "Saved purchase order id={}, version={}, number={}",
                aggregate.id(),
                aggregate.version(),
                aggregate.orderNumber()
        );

        return aggregate;
    }
}
~~~

AfterSaveCallback can return the same instance or a modified instance. For immutable aggregates like records, the callback can create a new record to return to the caller. However, the save's SQL has already executed before the callback; changes in the returned instance do not automatically trigger another UPDATE to the database.

If the callback only adds computed information to the returned instance, the caller may receive that information while the database retains the data saved in the previous step. If you need to save a persistent value, modify the aggregate before saving or execute a separate persistence operation within an appropriate transaction.

## 8. AfterSave does not mean the transaction has committed

This is an important distinction:

- **AfterSaveCallback** runs after Spring Data JDBC has executed the DbActions of the save call.
- **Transaction commit** occurs when the transaction boundary completes successfully.

If save runs inside a service method annotated with `@Transactional`, AfterSaveCallback is typically invoked while the transaction is still open. The SQL statements may have executed, but not yet committed.

~~~mermaid
sequenceDiagram
    participant S as Service
    participant R as Repository
    participant C as AfterSaveCallback
    participant DB as Database
    S->>R: save(aggregate)
    R->>DB: INSERT / UPDATE / child actions
    DB-->>R: SQL completed
    R->>C: onAfterSave(aggregate)
    C-->>R: aggregate
    R-->>S: saved aggregate
    S->>S: Subsequent business steps
    S->>DB: Transaction commits when method ends
~~~

If AfterSaveCallback throws a RuntimeException within the same transaction and the exception causes the transaction to roll back, the preceding SQL changes can be rolled back. However, if the callback already sent an email, made an HTTP call, or published a message to an external broker, those external effects will not roll back automatically.

Therefore, do not treat AfterSaveCallback as a safe point for firing irreversible side effects. If work must run only after commit, use an after-commit mechanism such as `TransactionalEventListener` with phase `AFTER_COMMIT`, or a transactional outbox if high reliability between the database and message broker is required.

## 9. Callbacks apply only to the aggregate root

Spring Data JDBC organizes persistence around aggregates. Child entities in `@MappedCollection` are saved as part of the aggregate root.

Spring Data JDBC callbacks and lifecycle events are invoked for the **aggregate root**. A callback declared for a child type is not automatically invoked separately each time a child is inserted/updated/deleted while saving the root.

Example:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        @MappedCollection(idColumn = "order_id")
        List<OrderLine> lines
) {}

public record OrderLine(
        String sku,
        int quantity
) {}
~~~

When saving PurchaseOrder, the callback receives PurchaseOrder and the AggregateChange describing the save plan for the entire aggregate. Do not expect a `BeforeSaveCallback<OrderLine>` to be invoked separately for each OrderLine.

If child processing is needed, you can traverse child data through the aggregate root or inspect DbActions in AggregateChange. If a child truly requires an independent lifecycle and transaction, reconsider the aggregate boundary instead of relying on per-child callbacks.

## 10. Callbacks are not invoked for derived queries and @Query

Save/delete callbacks are integrated with the aggregate persistence process. They are not invoked for derived query methods or annotated query methods.

Example:

~~~java
@Modifying
@Query("UPDATE purchase_orders SET status = :status WHERE id = :id")
int updateStatusDirectly(Long id, String status);
~~~

The UPDATE statement above executes via a custom query method. Spring Data JDBC does not build a standard aggregate save plan for each affected root, so it cannot determine and invoke BeforeSaveCallback/AfterSaveCallback for each updated aggregate.

Similarly, a derived delete query does not mean delete callbacks are invoked for each affected aggregate.

If a use case uses `@Query` or direct SQL yet still needs auditing, domain events, or read model updates, orchestrate that explicitly in the application service/custom repository. Do not depend on callbacks that are not triggered along that query path.

## 11. Registering callbacks in the Spring ApplicationContext

Spring Data discovers EntityCallback beans in the ApplicationContext. You can register one using `@Component`:

~~~java
@Component
public class PurchaseOrderAfterSaveCallback
        implements AfterSaveCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onAfterSave(PurchaseOrder aggregate) {
        return aggregate;
    }
}
~~~

Or declare a bean using `@Bean`:

~~~java
@Configuration
public class PersistenceCallbackConfiguration {

    @Bean
    AfterSaveCallback<PurchaseOrder> purchaseOrderAfterSaveCallback() {
        return aggregate -> {
            // Short, synchronous processing.
            return aggregate;
        };
    }
}
~~~

Generic types associate the callback with the corresponding domain type. Prefer an implementation class with explicit generics if type filtering and testable behavior are needed. Lambda callbacks do not expose runtime generic type information in the same way a concrete class does, so when there are multiple domain types or callbacks, an implementation class is usually clearer.

Do not call the callback manually in a service. Let Spring Data JDBC invoke the callback at the corresponding lifecycle checkpoint.

## 12. Ordering when multiple callbacks exist

An aggregate can have multiple callbacks of the same type. The Spring Data EntityCallback API supports ordering callbacks via `Ordered` or `@Order`.

Example:

~~~java
@Component
@Order(100)
public class FirstPurchaseOrderCallback
        implements BeforeSaveCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeSave(
            PurchaseOrder aggregate,
            MutableAggregateChange<PurchaseOrder> change
    ) {
        return aggregate;
    }
}

@Component
@Order(200)
public class SecondPurchaseOrderCallback
        implements BeforeSaveCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeSave(
            PurchaseOrder aggregate,
            MutableAggregateChange<PurchaseOrder> change
    ) {
        return aggregate;
    }
}
~~~

Lower order values are processed first according to Spring's ordering rules. When multiple callbacks modify the aggregate or MutableAggregateChange, ordering becomes part of application behavior. Declare explicit ordering if one callback depends on the result of another.

Do not rely on bean registration order or component scan order if logic requires a deterministic order.

## 13. How do Callbacks and ApplicationEvents differ?

Spring Data JDBC provides both EntityCallback and lifecycle events like BeforeSaveEvent/AfterSaveEvent.

| Criterion | EntityCallback | Lifecycle event |
|---|---|---|
| Purpose | Synchronous hook to inspect/modify an entity or persistence plan | Notify that a lifecycle milestone occurred |
| Return type | Can return a modified instance | Listeners do not replace the entity via return value |
| Ordering | EntityCallback API supports ordering and guarantees ordered execution | Depends on ApplicationEventMulticaster; can be configured async |
| Immutable aggregate | Suitable because callbacks return a new instance | Event listeners are not an entity replacement mechanism |
| Usage | Data normalization, validation, or adjusting the change plan | Logging, metrics, notifications, and lifecycle observation |

Callbacks are recommended when you need to modify entities, especially immutable types. Events are suitable when you only need to notify listeners.

If ApplicationEventMulticaster is configured to use a TaskExecutor, events may be processed asynchronously and will no longer guarantee execution order like synchronous callbacks. Do not use async events to modify an entity being saved.

## 14. Callbacks and transactions

Callbacks are invoked inside Spring Data JDBC's persistence process. When a save operation runs within a Spring transaction, callbacks run on the same execution thread and before the transaction boundary ends.

Principles:

- Keep callbacks short and predictable.
- Avoid high-latency external service calls in callbacks.
- Do not manually open connections or commit transactions.
- If a callback throws an exception, let the exception be handled according to the use case's transaction policy.
- Do not treat AfterSaveCallback as an after-commit hook.
- If auditing in the same transaction is needed, write the audit via repository/JDBC inside the transaction or use an outbox.
- If post-commit notifications are needed, use `TransactionalEventListener(AFTER_COMMIT)` or an equivalent mechanism.

A callback does not start a new transaction just because it is invoked. It participates in the current persistence context. Transaction boundaries remain governed by the repository/template and application service with the transaction manager.

## 15. Limitations when using AggregateChange

AggregateChange is a persistence-internal abstraction. Although the API allows iterating over actions and MutableAggregateChange allows adding actions, it should not be viewed as an extension point replacing the whole repository.

Limitations to keep in mind:

- The plan is generated from mapping metadata and aggregate state at save time.
- A DbAction may depend on the ID of a preceding action.
- Action ordering reflects dependencies between root and child.
- Improperly altering the plan can break optimistic locking or referential integrity.
- DbAction structures are persistence details, not public domain events.
- Custom actions must be supported by the transaction and data access strategy.
- Derived queries and `@Query` do not create aggregate plans for save/delete callbacks to observe.

If you only need to add an audit record, an application service/outbox is usually clearer than adding a custom DbAction to AggregateChange. Only modify MutableAggregateChange when you thoroughly understand the API, dependencies, and action execution order.

## 16. Complete example: before- and after-save callbacks

This example combines a before-save callback to observe the plan and an after-save callback to log the saved ID/version.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.relational.core.conversion.MutableAggregateChange;
import org.springframework.data.relational.core.mapping.event.BeforeSaveCallback;
import org.springframework.data.relational.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderLifecycleCallback
        implements BeforeSaveCallback<PurchaseOrder>,
                   AfterSaveCallback<PurchaseOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(PurchaseOrderLifecycleCallback.class);

    @Override
    public PurchaseOrder onBeforeSave(
            PurchaseOrder aggregate,
            MutableAggregateChange<PurchaseOrder> change
    ) {
        log.debug(
                "Before save: type={}, kind={}",
                change.getEntityType().getSimpleName(),
                change.getKind()
        );

        change.forEachAction(action ->
                log.debug("Action: {}", action.getClass().getSimpleName())
        );

        return aggregate;
    }

    @Override
    public PurchaseOrder onAfterSave(PurchaseOrder aggregate) {
        log.info(
                "After save: id={}, version={}, orderNumber={}",
                aggregate.id(),
                aggregate.version(),
                aggregate.orderNumber()
        );

        return aggregate;
    }
}
~~~

The same bean can implement multiple callback interfaces. Spring calls each method at its corresponding checkpoint. If logic grows larger, splitting into separate beans makes responsibilities easier to test and ordering easier to manage.

## 17. Testing callbacks

Callbacks can be tested at two levels.

### Unit testing callback logic

If a callback only checks properties or processes an AggregateChange, you can invoke the method directly with a sample object and a MutableAggregateChange created for the test. Verify the return value or any added/modified actions.

Unit tests are suitable for validating small logic, but do not prove Spring Data JDBC actually registers and invokes the callback in the right lifecycle.

### Integration testing through the repository

To verify the callback is registered and runs at the right time, use a Spring context and test database:

~~~java
@SpringBootTest
class PurchaseOrderCallbackIntegrationTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Autowired
    PurchaseOrderCallbackProbe probe;

    @Test
    void invokesCallbacksWhenSavingAggregate() {
        PurchaseOrder saved = repository.save(
                new PurchaseOrder(
                        null,
                        null,
                        "PO-TEST-1",
                        "NEW",
                        new BigDecimal("10.00"),
                        Instant.now()
                )
        );

        assertNotNull(saved.id());
        assertTrue(probe.beforeSaveCalled());
        assertTrue(probe.afterSaveCalled());
    }
}
~~~

PurchaseOrderCallbackProbe is a test bean recording that callbacks ran. Real tests should reset the probe between tests to avoid shared state skewing results.

Additional cases worth testing:

- Inserting a new root and checking that the ID is present in AfterSaveCallback.
- Updating an existing root and checking version according to configuration.
- Saving a root with children and verifying the callback is invoked for the root, not each child.
- Executing a derived query or `@Query` DML and verifying save callbacks are not called.
- Throwing an exception from a callback inside a transaction and checking rollback as configured.
- Multiple callbacks with `@Order` and verifying invocation order.

## 18. Common mistakes

| Symptom | Common cause | Solution |
|---|---|---|
| BeforeSaveCallback does not see newly changed value | AggregateChange was already created before the callback | Use BeforeConvertCallback to modify the entity before conversion |
| ID is not generated as expected | Attempting to assign ID in BeforeSaveCallback after insert/update decision | Assign ID in BeforeConvertCallback or use an appropriate ID strategy |
| AfterSaveCallback does not run with `@Query` update | Query method bypasses the aggregate save lifecycle | Orchestrate side effects in a service/custom fragment |
| Child callback does not run | Callbacks are only called for the aggregate root | Handle children through the root or AggregateChange |
| Changes in AfterSaveCallback are missing in DB | SQL already executed before the callback | Modify data before save or run separate persistence |
| Email is sent even though transaction rolled back | AfterSave does not mean commit; email is an external side effect | Use an after-commit listener or transactional outbox |
| Callbacks run in the wrong order | Multiple callbacks without declared order | Use `@Order` or `Ordered` |
| Adding DbAction causes FK/ID errors | Action does not respect aggregate dependencies and ordering | Check DbAction, root, property path, and ID dependencies |
| Event listeners execute out of order | ApplicationEventMulticaster may run asynchronously | Use EntityCallback for logic requiring synchronous execution |
| Callback is not discovered | Bean is not registered in ApplicationContext or generic type does not match | Register `@Component`/`@Bean` and check domain type |
| Callback does not run in batch DML | Derived/annotated queries do not create aggregate lifecycles per row | Handle batch side effects separately and intentionally |

## 19. Process for choosing the right callback

When wanting to intervene in the save process, clarify your goal first:

1. **Need to change the aggregate before creating the SQL plan?** Use BeforeConvertCallback.
2. **Need to inspect or adjust the DbAction plan?** Use BeforeSaveCallback with MutableAggregateChange.
3. **Need to observe the aggregate after SQL ran or change the returned instance?** Use AfterSaveCallback.
4. **Need to notify another component about the lifecycle?** Consider an event listener.
5. **Need to run side effects only after commit?** Use an after-commit event or outbox, not AfterSaveCallback as an after-commit hook.
6. **Using derived queries or `@Query` DML?** Coordinate related logic yourself because save callbacks are not triggered for those methods.
7. **Need to process children?** Do so via the aggregate root and aggregate plan; do not assume per-child callbacks.

~~~mermaid
flowchart TD
    A[Need to intervene during save] --> B{Modify entity before SQL plan?}
    B -->|Yes| C[BeforeConvertCallback]
    B -->|No| D{Inspect or modify DbAction plan?}
    D -->|Yes| E[BeforeSaveCallback + MutableAggregateChange]
    D -->|No| F{Process after SQL runs?}
    F -->|Yes| G[AfterSaveCallback]
    F -->|No| H{Only notify?}
    H -->|Yes| I[Lifecycle Event]
    H -->|Need after commit| J[AFTER_COMMIT or Outbox]
~~~

## 20. Key takeaways

- Spring Data JDBC determines insert/update, calls BeforeConvert, creates AggregateChange, calls BeforeSave, executes SQL, and then calls AfterSave.
- BeforeSaveCallback receives the aggregate root and `MutableAggregateChange<T>`; MutableAggregateChange extends AggregateChange.
- AggregateChange describes the persistence plan via DbActions, iterable with `forEachAction`.
- MutableAggregateChange allows altering the plan, though adding/modifying DbActions requires understanding dependencies and execution order.
- Use BeforeConvertCallback to change aggregate data before the SQL plan is generated or to assign IDs under an application strategy.
- BeforeSaveCallback runs after the plan is built; do not use it as a shortcut to change properties prior to conversion.
- AfterSaveCallback runs after SQL has executed and can return a modified aggregate instance.
- Modifying the instance in AfterSaveCallback does not automatically write changes back with a new UPDATE statement.
- Save/delete callbacks are only invoked for the aggregate root and are not triggered by derived queries or annotated query methods.
- EntityCallback fits synchronous processing; lifecycle events fit notifications and can be processed asynchronously depending on the multicaster.
- AfterSave is not after-commit; external side effects should use after-commit listeners or a transactional outbox.
- Register callbacks in the ApplicationContext with `@Component` or `@Bean`; use `@Order`/`Ordered` when explicit ordering is needed.

BeforeSaveCallback, AfterSaveCallback, and AggregateChange allow extending Spring Data JDBC's persistence flow at meaningful milestones. Use BeforeConvert to prepare the aggregate, BeforeSave to work with the DbAction plan, and AfterSave to observe post-SQL results. By keeping aggregate root boundaries, callback lifecycles, and transaction commits clear, extensions cooperate predictably with repositories without turning callbacks into homes for full business workflows or external side effects.

## References

- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html)
- [Spring Data Relational — Entity Callbacks](https://docs.spring.io/spring-data/relational/reference/commons/entity-callbacks.html)
- [BeforeSaveCallback API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html)
- [AfterSaveCallback API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/mapping/event/AfterSaveCallback.html)
- [AggregateChange API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/conversion/AggregateChange.html)
- [MutableAggregateChange API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/conversion/MutableAggregateChange.html)
