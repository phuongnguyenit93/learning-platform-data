# Processing Entities After Reading or After Saving

In Spring Data R2DBC, an entity often needs processing at different points in the persistence lifecycle. After reading a row, the application may need to normalize data or populate an in-memory-only property. After saving, the application may need to mark state on the returned object or record information for the calling layer.

Spring Data provides **entity callbacks** to intervene at these milestones. Two commonly used callbacks are `AfterConvertCallback` and `AfterSaveCallback`. The post-conversion callback is invoked after row data has been mapped into a Java object; the post-save callback is invoked after saving the entity. They allow returning the processed entity to continue flowing through the reactive pipeline.

Distinguish the post-save callback from transaction commit time. A SQL statement may have executed successfully and `AfterSaveCallback` may have run, yet the enclosing transaction can still roll back later. Therefore, entity lifecycle callbacks are suited for object and mapping processing; they do not by themselves turn an external side effect into an atomic post-commit operation.

## 1. Lifecycle milestones related to reading and saving

In Spring Data Relational/R2DBC, reading and saving involve several milestones:

| Milestone | Timing | Common purpose |
|---|---|---|
| `BeforeConvertCallback` | Before the entity is converted into write data | Normalize or populate values before creating the outbound row. |
| `BeforeSaveCallback` | After creating write data, before sending the SQL command | Adjust the entity or `OutboundRow` before insert/update. |
| `AfterSaveCallback` | After the insert/update operation succeeds | Process the entity returned after saving or populate in-memory-only state. |
| `AfterConvertCallback` | After a database row is converted into an entity | Normalize a newly loaded object or compute properties not stored in the database. |

Callback names reflect their processing milestones. `AfterConvertCallback` relates to converting a data row into an entity; `AfterSaveCallback` relates to the save operation. Do not use a post-read callback to silently write data back, or use a post-save callback to replace a business workflow that must commit together with data.

## 2. AfterConvertCallback: processing entities after reading

`AfterConvertCallback<T>` is invoked after Spring Data converts a data row into an entity of type `T`. The callback receives the mapped entity, the source row, and the table name as a `SqlIdentifier`.

Common signature:

```java
public interface AfterConvertCallback<T> extends EntityCallback<T> {
    T onAfterConvert(T entity, Row row, SqlIdentifier table);
}
```

For example, the application stores a display name in the database but wants to trim whitespace before returning the object to the business layer:

```java
@Component
public class CustomerAfterConvertCallback
        implements AfterConvertCallback<Customer> {

    @Override
    public Customer onAfterConvert(
            Customer customer, Row row, SqlIdentifier table) {

        String normalized = customer.getDisplayName() == null
            ? null
            : customer.getDisplayName().trim();

        return customer.withDisplayName(normalized);
    }
}
```

`withDisplayName` in the example is a method provided by the domain class to create a new object. If the entity is mutable, the callback can update the object and return the same instance; if the entity is immutable or a record, create and return a new instance.

The callback must return the entity to be forwarded downstream. Creating a new object while still returning the old object prevents the change from taking effect for the caller.

### 2.1 Using AfterConvert for in-memory-only properties

A common use case is computing derived properties after reading. For example, `Customer` stores `firstName` and `lastName`, while `displayLabel` is solely for display:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    private String displayLabel;

    public Customer withDisplayLabel(String value) {
        this.displayLabel = value;
        return this;
    }
}
```

A callback can build the label after reading:

```java
@Component
public class CustomerLabelCallback
        implements AfterConvertCallback<Customer> {

    @Override
    public Customer onAfterConvert(
            Customer customer, Row row, SqlIdentifier table) {

        String label = Stream.of(
                customer.getFirstName(), customer.getLastName())
            .filter(Objects::nonNull)
            .collect(Collectors.joining(" "));

        return customer.withDisplayLabel(label);
    }
}
```

`@Transient` indicates the property is not persisted as a regular column. The `displayLabel` value is constructed in memory after reading; it is not data written to the database.

### 2.2 AfterConvert is not lazy loading

The post-conversion callback does not create proxies and does not automatically turn associations into lazy relationships. If data from another table is needed, the callback would have to perform an explicit operation, or better yet, the read use case should design an appropriate query/projection.

Do not use `AfterConvertCallback` to silently query a series of tables for each entity in a `Flux`. That can produce N+1 queries, increase latency, and make read costs unpredictable. If a screen requires aggregated data, consider a SQL join, projection, or dedicated query service.

## 3. AfterSaveCallback: processing entities after saving

`AfterSaveCallback<T>` is invoked after Spring Data executes the entity save operation. The callback receives the entity, the `OutboundRow` used for the write operation, and the table name.

Common signature:

```java
public interface AfterSaveCallback<T> extends EntityCallback<T> {
    T onAfterSave(T entity, OutboundRow row, SqlIdentifier table);
}
```

For example, the entity has a transient property so the calling layer knows the object just went through persistence:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;

    private String email;

    @Transient
    private boolean persistedInThisOperation;

    public Customer withPersistedInThisOperation(boolean value) {
        this.persistedInThisOperation = value;
        return this;
    }
}
```

Callback:

```java
@Component
public class CustomerAfterSaveCallback
        implements AfterSaveCallback<Customer> {

    @Override
    public Customer onAfterSave(
            Customer customer, OutboundRow row, SqlIdentifier table) {

        return customer.withPersistedInThisOperation(true);
    }
}
```

The transient value is added to the object returned after the save operation. It is not written as a database column because `@Transient` excludes the property from persistence mapping.

### 3.1 Modifying an entity in AfterSave does not automatically re-write the database

The most important point about the post-save callback is that SQL has already executed before this callback runs. If the callback changes a property mapped to a column, that change exists only in the returned object; the database does not automatically issue an extra `UPDATE` to save the new change.

For instance, if the callback changes `customer.email` after save, do not assume the email in the database also changed. To persist that change, the application must execute a separate save/update operation and carefully design transactions and potential repeated callback invocations.

Do not call the same repository's `save` again from `AfterSaveCallback` for the same entity. This can create callback loops, nested queries, or unpredictable behavior. If a second persistence step is needed, place it in the service/use case with an explicit processing flow.

### 3.2 Generated IDs and database-generated values

Database-generated IDs are part of the insert/mapping pipeline managed by Spring Data R2DBC. When you need to handle the ID value, use the entity returned from `save` or the corresponding insert API rather than guessing when the ID is populated inside a callback.

Example:

```java
return customerRepository.save(customer)
    .flatMap(saved -> auditRepository.recordCreated(saved.getId())
        .thenReturn(saved));
```

The code uses the `saved` entity returned by the repository. If a post-save callback creates a new instance, that instance must also be returned per the callback contract to continue the processing chain.

## 4. Registering entity callbacks in Spring

Spring Data discovers `EntityCallback` implementations registered as beans in the application context. You can use `@Component` or declare `@Bean` in configuration.

Example using `@Bean`:

```java
@Configuration
public class CustomerCallbackConfiguration {

    @Bean
    AfterConvertCallback<Customer> customerAfterConvertCallback() {
        return (customer, row, table) ->
            customer.withDisplayLabel(
                customer.getFirstName() + " " + customer.getLastName());
    }
}
```

With lambda-based callbacks, ensure the class/return type is explicitly typed so Spring recognizes the callback bean accurately. For complex logic or when dependencies are needed, a `@Component` class is usually easier to read and test.

Callbacks apply to their corresponding entity type. Avoid declaring a generic catch-all callback with type-agnostic logic if the operation actually applies only to one domain type.

## 5. Synchronous callbacks and reactive callbacks

Spring Data provides synchronous callbacks and reactive variants for reactive operations. Synchronous callbacks return the entity directly; reactive callbacks return a `Publisher<T>`.

Example of the reactive post-convert variant:

```java
@Component
public class CustomerReactiveAfterConvertCallback
        implements ReactiveAfterConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onAfterConvert(
            Customer customer, Row row, SqlIdentifier table) {

        return Mono.just(customer.withDisplayLabel(
            customer.getFirstName() + " " + customer.getLastName()));
    }
}
```

The example illustrates a callback returning `Publisher<Customer>`; exact imports and APIs must match your project's Spring Data Relational/R2DBC version.

With reactive callbacks:

- Do not call `block()` to obtain a result from another publisher.
- Return a publisher so Spring Data can chain it into the persistence pipeline.
- Do not call `subscribe()` inside the callback because that detaches the work from the read/save operation lifecycle.
- If the callback performs asynchronous I/O, weigh the cost and risk of generating multiple queries per entity.
- If you are only normalizing strings or computing simple properties, a synchronous callback may suffice and be clearer.

Do not use synchronous callbacks to perform blocking I/O in a reactive flow. That can block processing threads and reduce application scalability.

## 6. Execution order when multiple callbacks exist

An application can register multiple callbacks for the same entity type or callback phase. When execution order needs to be controlled, you can use `Ordered` or the `@Order` annotation via Spring's ordering mechanism.

Example:

```java
@Component
@Order(100)
public class NormalizeCustomerAfterConvert
        implements AfterConvertCallback<Customer> {
    // Normalize data first.
}

@Component
@Order(200)
public class BuildCustomerLabelAfterConvert
        implements AfterConvertCallback<Customer> {
    // Build label after normalization step.
}
```

In the example, the callback with the smaller order value takes precedence and runs first within the same sorting mechanism. Use explicit ordering when a later callback depends on an earlier callback's output. Avoid creating too many callbacks with implicit dependencies; if a workflow requires multiple coordinated steps, a dedicated callback or service can be easier to trace.

Do not assume a global order across all different callback types based solely on `@Order`. The `BeforeConvert`, `BeforeSave`, `AfterSave`, and `AfterConvert` phases have distinct positions in the persistence lifecycle.

## 7. Distinguishing EntityCallback from lifecycle events

Spring Data also provides a mechanism to emit lifecycle events through the application event publisher. Events are appropriate when an application wants to notify listeners that a lifecycle milestone occurred so they can observe or perform secondary reactions.

Key differences:

| Entity callback | Lifecycle event |
|---|---|
| Invoked as part of the mapping/persistence pipeline. | Published via the application event mechanism. |
| Can return a transformed entity for Spring Data to keep using. | Listeners do not return a replacement entity for the persistence operation. |
| Has reactive variants for reactive stores. | Dispatch behavior depends on the event publisher and application context configuration. |
| Suited for adjusting an entity or mapping data at a specific phase. | Suited for notifying/observing a lifecycle event. |

If the goal is to modify the object before the caller receives the result, entity callbacks are usually more suitable. If the goal is to notify other components that an operation occurred, events may fit better. However, a post-save lifecycle event also does not inherently mean the transaction has committed.

For side effects that must run only after commit, use an appropriate after-commit mechanism or transactional outbox; do not rely on the names `AfterSave` or `AfterSaveEvent` to infer commit timing.

## 8. AfterSave does not mean after-commit

This is the easiest pitfall when using post-save callbacks. `AfterSaveCallback` runs after saving the entity at the Spring Data layer. If that operation is inside a larger transaction, the transaction may still be uncommitted.

Example:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(Order.from(command))
        .flatMap(saved -> validateAnotherCondition(saved)
            .thenReturn(saved));
}
```

Suppose `AfterSaveCallback<Order>` ran when `orderRepository.save` completed, yet `validateAnotherCondition` subsequently emits an error. The transaction can roll back. If the callback already sent an email or published a message to a broker, that side effect is not rolled back with the database.

Therefore, do not use `AfterSaveCallback` to:

- Send irreversible emails or SMS messages.
- Publish messages to a broker assuming messages exist only when the database commits.
- Call HTTP APIs to mutate state in another service.
- Write files/object storage without compensation mechanisms.

Post-save callbacks are suitable for local object processing and metadata for the caller. For events that must be emitted durably, write an outbox row in the same transaction as the entity, then let a separate publisher send the message after commit.

## 9. Combining callbacks with auditing

Spring Data auditing can automatically manage fields such as creator, creation timestamp, updater, and update timestamp. This is pre-write processing, not a typical responsibility of `AfterSaveCallback`.

Entity example:

```java
@Table("customer")
public class Customer {
    @Id
    private Long id;

    private String email;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant modifiedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String modifiedBy;
}
```

Enabling auditing for R2DBC can use `@EnableR2dbcAuditing`:

```java
@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
```

If the current user needs to be resolved in a reactive application, configure `ReactiveAuditorAware<T>` per the API of the Spring Data version in use. Spring Data's auditing callback will populate values before saving at the appropriate lifecycle point.

Do not manually update `createdAt` in `AfterSaveCallback`, because the SQL statement just executed may already have written the old value or null. If audit fields need changing before saving, use the auditing infrastructure or a pre-save phase callback.

## 10. Callbacks and immutable entities

Immutable entities typically use constructors or records instead of setters. In this case, the callback must return a new instance with the desired values.

Illustrative example:

```java
public record Customer(
    Long id,
    String firstName,
    String lastName,
    String displayLabel
) {
    Customer withDisplayLabel(String value) {
        return new Customer(id, firstName, lastName, value);
    }
}

@Component
class CustomerAfterConvertCallback
        implements AfterConvertCallback<Customer> {

    @Override
    public Customer onAfterConvert(
            Customer customer, Row row, SqlIdentifier table) {

        return customer.withDisplayLabel(
            customer.firstName() + " " + customer.lastName());
    }
}
```

Spring Data continues using the instance returned by the callback. If the callback returns `null`, or a reactive callback emits `null`, the publisher has no valid value and the operation may fail. Always return a valid entity per the contract.

With immutable entities, callbacks must not expect editing `Row` directly to modify the already-converted object; create a new object instead. With `BeforeSaveCallback`, `OutboundRow` can be edited if the goal is changing written data, provided you understand the difference between values in the entity and values sent to the database.

## 11. Callbacks do not replace business logic in services

Callbacks suit technical logic tightly bound to the mapping/persistence lifecycle, such as format normalization, creating transient properties, or adding metadata before writing. Conditional business logic, multi-repository dependencies, or external system calls usually belong in a service/use case.

For example, do not put the entire order confirmation workflow inside `AfterSaveCallback<Order>`:

```java
// Do not let a callback execute an entire workflow.
public Order onAfterSave(Order order, OutboundRow row, SqlIdentifier table) {
    // Call inventory, payment, email, and broker from here.
    return order;
}
```

That approach hides dependencies, makes transactions hard to control, can cause repeated queries, and causes saving an entity to unexpectedly trigger an entire workflow. Let the service express the business sequence:

```java
@Transactional
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> inventoryService.reserve(order)
            .then(order.confirm())
            .flatMap(orderRepository::save));
}
```

Steps outside the database still require an outbox/saga or separate coordination mechanism if consistency across multiple resources must be guaranteed.

## 12. Performance and impact when callbacks run on many entities

Callbacks are invoked per Spring Data entity operation. A query returning thousands of entities can trigger the corresponding callback for every converted entity. Therefore:

- Avoid unnecessary heavy CPU processing in callbacks.
- Do not perform blocking I/O.
- Avoid querying repositories per entity to prevent N+1 queries.
- Avoid building large object graphs or holding auxiliary data in global caches.
- If an asynchronous service must be called, consider moving it to the service/use case or a separate post-query processing step.
- Measure callback duration on high-volume queries.

Reactive callbacks can return a publisher and avoid blocking threads when written properly, yet they can still increase I/O operation counts and overall latency. Being reactive does not make extra query cost disappear.

## 13. Callback scope across data access APIs

Callbacks are tied to Spring Data's entity mapping pipeline. When using a repository or `R2dbcEntityTemplate`, Spring Data manages entity conversion and can invoke the corresponding callbacks.

When using `DatabaseClient` to execute SQL and manually map `Row` to DTOs with a lambda, the application defines the mapping itself. Do not assume entity callbacks will run automatically on objects created by that lambda. If the same normalization logic is needed, explicitly invoke a shared mapper/helper.

Similarly, direct SQL updates/deletes do not necessarily pass through the entity read/save lifecycle like `save` or `select`. `AfterSaveCallback` is not a universal hook for every hand-written `UPDATE` statement, and `AfterConvertCallback` is not a hook for every `Row` read at the SPI level.

When using custom repositories, native queries, or low-level APIs, verify whether the execution path goes through the mapping infrastructure. If a callback is a mandatory requirement, write an integration test using the exact API employed.

## 14. Testing AfterConvertCallback and AfterSaveCallback

You can test callbacks individually with unit tests to confirm the input entity is transformed properly. Example:

```java
@Test
void trimsDisplayNameAfterConvert() {
    Customer customer = customerWithDisplayName("  Nguyen An  ");
    Row row = mock(Row.class);
    SqlIdentifier table = SqlIdentifier.unquoted("customer");

    Customer result = callback.onAfterConvert(customer, row, table);

    assertThat(result.getDisplayName()).isEqualTo("Nguyen An");
}
```

For post-save callbacks, inspect the returned object and confirm transient properties are populated as expected. If the callback returns a new instance, verify the caller receives the transformed instance.

Integration tests need to verify that callbacks are actually invoked through the application's repository/template path:

1. Save an entity and confirm `AfterSaveCallback` is invoked.
2. Read the entity via repository/template and confirm `AfterConvertCallback` is invoked.
3. Verify the returned entity contains properties updated by the callbacks.
4. Verify `@Transient` properties are not written as columns.
5. If the operation is in a transaction, intentionally emit an error after save to confirm callbacks are not mistaken for completed commits.
6. Verify callbacks do not swallow mapping or database errors.

For reactive callbacks, use `StepVerifier` to test publishers and ensure callbacks do not manually subscribe or block. Integration tests should run against the corresponding driver/database because mapping and column types can differ across database systems.

## 15. Common design mistakes

| Practice | Consequence |
|---|---|
| Modifying entity in callback without returning new instance | Caller still receives the old object; changes are lost. |
| Editing a mapped field in `AfterSaveCallback` and thinking DB changed | In-memory object diverges from persisted data. |
| Sending messages in `AfterSaveCallback` | Messages may be sent even though the transaction later rolls back. |
| Calling `save` again from a post-save callback | Can create callback loops or nested write operations. |
| Performing blocking I/O in a reactive callback | Blocks threads and reduces scalability. |
| Querying a repository per entity in `AfterConvertCallback` | Easily produces N+1 queries. |
| Using callbacks to orchestrate full business workflows | Dependencies and transaction boundaries are hidden, hard to test. |
| Assuming raw `DatabaseClient` mapping also runs entity callbacks | Callback logic may never execute on custom mapping paths. |

## 16. Choosing the right mechanism for each need

| Need | Mechanism to consider |
|---|---|
| Normalize objects after reading | `AfterConvertCallback`. |
| Compute transient properties after reading | `AfterConvertCallback` or query-layer mapper. |
| Modify data before building outbound row | `BeforeConvertCallback`. |
| Adjust outbound row before SQL | `BeforeSaveCallback`. |
| Process object after save operation | `AfterSaveCallback`. |
| Populate `createdAt`, `modifiedAt`, `createdBy`, `modifiedBy` | Spring Data auditing. |
| Notify listeners of lifecycle events | Application events if semantics and timing match. |
| Emit messages only after database commit | Transactional outbox or suitable after-commit mechanism. |
| Execute multi-step business workflows | Service/use case, transactions, and saga/outbox as needed. |

## 17. Workflow for applying callbacks in a project

When adding post-read or post-save processing, determine:

1. Does the logic belong to mapping/entity lifecycle or is it an independent business step?
2. Does the logic need to run after convert, before save, or after save?
3. Does the callback need to create a new entity or only mutate a mutable instance?
4. Is the change only for the returned object or does it need to be written back to the database?
5. Does the data access API go through Spring Data entity mapping?
6. Is the callback synchronous or reactive; is there a risk of blocking or triggering N+1 queries?
7. Does the callback have external side effects; if so, has the transaction committed yet?
8. Are there multiple callbacks in the same phase needing `Ordered`/`@Order`?
9. Is there an integration test confirming the callback runs on the right repository/template/driver?

`AfterConvertCallback` is suitable for processing entities after reading and converting from database rows. `AfterSaveCallback` is suitable for processing objects after a save operation. Both can return a transformed entity, but post-save changes do not automatically re-write the database and post-save callbacks do not mean the transaction has committed. Keeping callbacks short and focused on mapping/object lifecycle while placing multi-resource workflows and side effects in services, outboxes, or sagas makes consistency boundaries much clearer.
