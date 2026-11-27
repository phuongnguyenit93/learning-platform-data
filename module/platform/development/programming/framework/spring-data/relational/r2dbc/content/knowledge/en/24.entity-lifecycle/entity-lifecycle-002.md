# Synchronous EntityCallback and Reactive Callbacks

## 1. EntityCallback in the entity lifecycle

Spring Data R2DBC provides **EntityCallback** as an extension point for applications to intervene on an entity at specific points during save, read, or delete operations. A callback can normalize an entity, enrich metadata, validate conditions, or transform values before Spring Data maps and executes the persistence operation.

There are two types of callbacks to distinguish:

- **Synchronous callback:** receives an entity and directly returns the processed entity.
- **Reactive callback:** receives an entity and returns a Publisher containing the processed entity. The callback can compose with other reactive operations without blocking threads.

Synchronous callback example:

~~~java
@Component
class CustomerNormalizationCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer entity,
            SqlIdentifier table) {

        return new Customer(
                entity.id(),
                entity.name().trim(),
                entity.email().trim().toLowerCase(Locale.ROOT),
                entity.status()
        );
    }
}
~~~

The callback is invoked before Spring Data converts the entity into write data. Because Customer is an immutable record, the callback creates and returns a new normalized instance.

Reactive callback example:

~~~java
@Component
class CustomerPolicyCallback
        implements ReactiveBeforeConvertCallback<Customer> {

    private final CustomerPolicy policy;

    CustomerPolicyCallback(CustomerPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer entity,
            SqlIdentifier table) {

        return policy.normalize(entity);
    }
}
~~~

In the second example, CustomerPolicy returns a Publisher. Spring Data can chain this publisher into the persistence pipeline and only proceed once the callback emits the entity.

EntityCallback is not an arbitrary listener running after the database has completely finished. Callbacks are part of the entity mapping/persistence pipeline. The callback's position determines what stage the entity is in and where changes take effect.

## 2. Callback lifecycle when writing an entity

Write callbacks are typically organized around the following stages:

~~~text
Entity is passed to save operation
              |
              v
       BeforeConvertCallback
              |
              v
       Convert entity into
          OutboundRow
              |
              v
         BeforeSaveCallback
              |
              v
       Execute INSERT/UPDATE
              |
              v
          AfterSaveCallback
              |
              v
       Publisher emits entity
~~~

The callback name describes its timing in the lifecycle:

| Callback | Timing | Common purpose |
|---|---|---|
| BeforeConvertCallback | Before converting the entity into write data | Normalize or populate fields on the entity |
| BeforeSaveCallback | After preparing write data, before executing SQL | Adjust the entity or OutboundRow |
| AfterSaveCallback | After the save operation completes | Perform post-save processing based on the persistence result |

Reactive callbacks have corresponding names prefixed with **Reactive**, for example **ReactiveBeforeConvertCallback**.

The order above is a general view of the write lifecycle. Details such as generated IDs, versions, and database-generated data depend on mapping, dialect, and driver. Do not assume the input object is always mutated in place; for immutable entities, use the entity emitted by the save publisher.

### 2.1. BeforeConvertCallback

**BeforeConvertCallback<T>** is invoked before the entity is converted into the representation used to write to the database. The callback receives the entity and the table name as a **SqlIdentifier**.

This is the right place to:

- Trim or normalize strings.
- Generate slugs or simple derived values.
- Populate default values that are a persistence responsibility.
- Generate metadata that needs to be persisted alongside the entity.
- Return a new entity if the model is immutable.

Example:

~~~java
@Component
class ProductBeforeConvertCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            SqlIdentifier table) {

        String normalizedCode =
                product.code().trim().toUpperCase(Locale.ROOT);

        return new Product(
                product.id(),
                normalizedCode,
                product.name().trim(),
                product.price()
        );
    }
}
~~~

Changes are made on the entity before Spring Data creates the write data. Therefore, this is usually the clearest place to normalize domain values before persistence.

Do not use this callback to replace full request validation or complex business rules. Rules requiring clear user feedback should generally be validated in the service/domain layer before starting the write.

### 2.2. BeforeSaveCallback

**BeforeSaveCallback<T>** is invoked when Spring Data has prepared the **OutboundRow** and is about to execute the write operation. The callback receives:

- The entity being saved.
- The OutboundRow containing values mapped to columns.
- The SqlIdentifier representing the target table.

Signature example:

~~~java
@Component
class CustomerBeforeSaveCallback
        implements BeforeSaveCallback<Customer> {

    @Override
    public Customer onBeforeSave(
            Customer entity,
            OutboundRow row,
            SqlIdentifier table) {

        // Can inspect entity, table, and data in row.
        return entity;
    }
}
~~~

This callback is appropriate when you need to intervene at the row-mapping level, such as a specialized write value or metadata that depends on the generated row structure.

OutboundRow is Spring Data Relational's write-data representation. Modifying the row can cause the data sent to the database to differ from the properties on the entity. If editing the row directly, keep the row, the returned entity, and the data expected by the caller consistent. Do not arbitrarily change columns or data types without understanding the mapping and dialect.

If you only need to normalize an entity property, it is usually better to use BeforeConvertCallback to avoid maintaining two different versions of the data.

### 2.3. AfterSaveCallback

**AfterSaveCallback<T>** is invoked after the save operation has been executed. The callback receives the entity, OutboundRow, and table identifier.

Example:

~~~java
@Component
class CustomerAfterSaveCallback
        implements AfterSaveCallback<Customer> {

    @Override
    public Customer onAfterSave(
            Customer entity,
            OutboundRow row,
            SqlIdentifier table) {

        return entity;
    }
}
~~~

This callback is suitable for post-save processing that belongs in the persistence lifecycle, such as adding a derived value to the returned object or recording appropriate technical information.

Distinguish post-save callbacks from emitting external side effects. Sending an email, making an HTTP call, or publishing a message directly from AfterSaveCallback can create inconsistent state if the database rolls back or the external operation fails. For reliable event publishing requirements, consider a transactional outbox.

If AfterSaveCallback emits an error after the SQL statement has already run, rollback capability depends on whether a transaction wraps the operation. When database changes and post-save steps must be atomic together, place the entire publisher in an appropriate reactive transaction.

## 3. Callbacks when reading an entity

When reading data, Spring Data retrieves rows from the database, maps them into entities, and can then invoke the post-conversion callback:

~~~text
SELECT returns Row
       |
       v
MappingR2dbcConverter
       |
       v
Entity is created
       |
       v
AfterConvertCallback
       |
       v
Entity is emitted
~~~

**AfterConvertCallback<T>** is invoked after the row has been converted into an entity.

Example:

~~~java
@Component
class CustomerAfterConvertCallback
        implements AfterConvertCallback<Customer> {

    @Override
    public Customer onAfterConvert(
            Customer entity,
            SqlIdentifier table) {

        return new Customer(
                entity.id(),
                entity.name(),
                entity.email(),
                entity.status()
        );
    }
}
~~~

The callback can transform the entity after mapping. However, keep processing lightweight and deterministic. If each loaded row requires calling a remote service, the callback can trigger a network call per row and turn a list query into a slow chain of operations.

Especially with Flux, the post-convert callback may run for every emitted entity. Consider row count, concurrency, latency, and backpressure when adding work to this stage.

Do not confuse AfterConvertCallback with lazy loading. Spring Data R2DBC does not provide a persistence context and lazy-loading proxies like JPA. If data from another table is needed, write an appropriate query or compose publishers intentionally.

## 4. Callbacks when deleting an entity

Spring Data Relational also has callbacks for the delete lifecycle:

- **BeforeDeleteCallback<T>:** invoked before deleting an entity.
- **AfterDeleteCallback<T>:** invoked after the delete operation completes.

Before-delete callback example:

~~~java
@Component
class CustomerBeforeDeleteCallback
        implements BeforeDeleteCallback<Customer> {

    @Override
    public Customer onBeforeDelete(
            Customer entity,
            SqlIdentifier table) {

        return entity;
    }
}
~~~

The before-delete callback can validate or prepare information based on the entity and table. The after-delete callback is suitable for post-operation processing within the lifecycle scope.

Distinguish deleting a full entity from running a custom SQL DELETE via DatabaseClient. When the application sends raw SQL using DatabaseClient, there is no entity lifecycle mapping for Spring Data to automatically trigger callbacks for that statement.

Additionally, do not assume every delete by ID, Criteria, or raw SQL provides the same entity information to the callback. Identify the API being used and test callback behavior on your project's Spring Data R2DBC version.

## 5. Synchronous callbacks: returning the entity directly

Synchronous callbacks implement interfaces such as:

- **BeforeConvertCallback<T>**.
- **BeforeSaveCallback<T>**.
- **AfterSaveCallback<T>**.
- **AfterConvertCallback<T>**.
- **BeforeDeleteCallback<T>**.
- **AfterDeleteCallback<T>**.

The callback method receives an entity and returns an entity:

~~~java
public interface BeforeConvertCallback<T> {
    T onBeforeConvert(T entity, SqlIdentifier table);
}
~~~

This is an illustrative signature overview. The actual interface also extends Spring Data's callback marker interface, and package details may vary across modules/versions.

Synchronous callback implementation example:

~~~java
@Component
class NormalizeEmailCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String normalized = customer.email()
                .trim()
                .toLowerCase(Locale.ROOT);

        return customer.withEmail(normalized);
    }
}
~~~

Synchronous callbacks are suitable for fast transformations that require no I/O:

- Normalizing data.
- Assigning default values.
- Generating local metadata.
- Computing simple derived values.
- Checking technical preconditions and throwing an exception if invalid.

For mutable entities, the callback can modify the entity and return the same instance. For records or immutable classes, the callback should create a new object. In both cases, it must return the entity that the persistence pipeline should continue using.

### 5.1. Do not perform blocking I/O in synchronous callbacks

Do not call network services, read large files, or perform blocking database queries in a synchronous callback. In a reactive application, callbacks may execute on the thread processing the pipeline; a blocking operation can block the event loop or degrade throughput.

Inappropriate example:

~~~java
@Override
public Customer onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    // Not recommended: blocks the thread to call an external service.
    RiskResult result = riskClient.check(customer.email()).block();

    return customer.withRiskLevel(result.level());
}
~~~

If the work requires asynchronous I/O, use a reactive callback or move that step up to the service layer before calling the repository.

## 6. Reactive callbacks: returning a Publisher

Reactive callbacks use corresponding interfaces prefixed with **Reactive**, such as:

- **ReactiveBeforeConvertCallback<T>**.
- **ReactiveBeforeSaveCallback<T>**.
- **ReactiveAfterSaveCallback<T>**.
- **ReactiveAfterConvertCallback<T>**.
- **ReactiveBeforeDeleteCallback<T>**.
- **ReactiveAfterDeleteCallback<T>**.

Instead of returning the entity directly, the callback returns a **Publisher<T>**. In Reactor applications, **Mono<T>** can be used because Mono implements Publisher.

Signature example:

~~~java
public interface ReactiveBeforeConvertCallback<T> {
    Publisher<T> onBeforeConvert(T entity, SqlIdentifier table);
}
~~~

Reactive callback example:

~~~java
@Component
class ReactiveCustomerCallback
        implements ReactiveBeforeConvertCallback<Customer> {

    private final CustomerPolicy policy;

    ReactiveCustomerCallback(CustomerPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return policy.normalize(customer)
                .map(normalized -> normalized.withStatus(
                        normalized.status().toUpperCase(Locale.ROOT)
                ));
    }
}
~~~

CustomerPolicy.normalize() can return a Mono<Customer>. The callback returns that publisher so Spring Data can chain it into the save process. There is no need to manually subscribe or block to wait for the result.

### 6.1. Reactive callbacks can compose asynchronous operations

Example of a callback that needs to fetch metadata from a reactive source:

~~~java
@Component
class ReactiveBeforeConvertCallbackImpl
        implements ReactiveBeforeConvertCallback<Customer> {

    private final TenantPolicyRepository tenantPolicyRepository;

    ReactiveBeforeConvertCallbackImpl(
            TenantPolicyRepository tenantPolicyRepository) {
        this.tenantPolicyRepository = tenantPolicyRepository;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return tenantPolicyRepository.findPolicy(customer.tenantId())
                .map(policy -> customer.withRegion(policy.region()));
    }
}
~~~

This illustrates reactive composition capability. In practical design, consider the implications of a persistence callback calling another repository:

- It increases the number of queries per save.
- It can create an N+1 pattern when saving multiple entities.
- It extends transaction duration and holds connections longer if the operations share the same transaction.
- The secondary repository must use the right ConnectionFactory/transaction context if it needs to join the same transaction.
- Errors from the metadata source will fail the save publisher.

If fetching a policy is part of an important business rule, it is usually clearer to perform it in the service before invoking persistence. Reactive callbacks should be used when the logic truly belongs to the entity lifecycle and applies across multiple save paths.

### 6.2. Do not call subscribe() or block() in reactive callbacks

Not recommended:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    policy.normalize(customer).subscribe();
    return Mono.just(customer);
}
~~~

A manually created subscription runs independently of the publisher Spring Data is awaiting. Spring cannot guarantee that the normalize operation completes before the entity is saved, nor can it propagate errors or share the transaction of that publisher.

The right approach is to return the publisher:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    return policy.normalize(customer);
}
~~~

Similarly, do not use block() to synchronously extract a value from a publisher inside a reactive callback.

### 6.3. Callback publishers must emit an entity for the pipeline to continue

A reactive callback is expected to emit the entity to continue processing. If it returns Mono.empty(), the pipeline may complete without an entity to perform the next persistence step.

If the callback detects invalid data, emit an explicit error:

~~~java
return Mono.error(
        new IllegalArgumentException("Customer email is required")
);
~~~

If the callback does not need to modify the entity, return Mono.just(entity) or an equivalent publisher. Avoid returning empty unintentionally, as the caller may receive an empty completion without understanding why the save produced no result.

## 7. Comparing synchronous and reactive callbacks

| Criterion | Synchronous callback | Reactive callback |
|---|---|---|
| Interface | BeforeConvertCallback<T> | ReactiveBeforeConvertCallback<T> |
| Return type | T | Publisher<T> |
| Reactor example | Return entity directly | Return Mono<T> |
| Asynchronous processing | Not suitable | Can compose with Publisher |
| I/O | Only fast, non-blocking work | Can use reactive APIs |
| Error | Throw exception | Mono.error/error signal |
| Ordering | Synchronous callback completes within the call | Pipeline awaits the callback publisher |
| Best fit | Local normalization and transformations | Truly reactive work tied to the lifecycle |

Do not choose a reactive callback solely because the application uses R2DBC. If you are only trimming strings or setting defaults, a synchronous callback is more concise. Choose a reactive callback when you genuinely need to compose publishers and keep all processing non-blocking.

In applications with both imperative and reactive access paths, register callbacks appropriate for the API being used. Do not assume a synchronous callback can replace a reactive callback when asynchronous I/O is needed; verify callback registration and invocation in your Spring Data version.

## 8. Registering callbacks in the Spring ApplicationContext

Typically, callbacks are declared as Spring beans. You can use @Component:

~~~java
@Component
class ProductCallback implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            SqlIdentifier table) {
        return product;
    }
}
~~~

Or declare with @Bean:

~~~java
@Configuration
class EntityCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Product> productCallback() {
        return (product, table) -> product.withName(
                product.name().trim()
        );
    }
}
~~~

Spring Data detects callback beans by their callback interface and integrates them into lifecycle execution. Constructor injection should be used when a callback requires dependencies.

Do not instantiate callbacks with `new` inside a service and expect Spring Data to invoke them automatically. Callbacks must be registered in the application context or in the corresponding callback registry.

When using multiple persistence configurations or multiple application contexts, verify that the callback is registered in the context used by the template/repository. With multiple databases, a shared callback may be invoked across multiple persistence paths; inspect the table/entity to scope the logic if necessary.

## 9. Callback execution order

An entity may pass through multiple callbacks of the same type or multiple callbacks across different phases. Spring supports ordering via **Ordered** or the **@Order** annotation.

Example:

~~~java
@Component
@Order(10)
class TrimNameCallback implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        return customer.withName(customer.name().trim());
    }
}
~~~

~~~java
@Component
@Order(20)
class NormalizeEmailCallback implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        return customer.withEmail(
                customer.email().toLowerCase(Locale.ROOT)
        );
    }
}
~~~

Callbacks in the same phase are sorted according to the configured order; lower order values have higher priority per Spring convention. The second callback receives the entity returned by the first callback.

Ordering matters when one callback depends on another callback's result. For instance, trimming a string before checking its length or computing a hash. Keep the number of callbacks small and responsibilities clear to avoid hard-to-trace transformation chains.

Do not rely on accidental bean registration order. If logic requires a specific order, declare @Order or implement Ordered explicitly.

## 10. Callbacks and immutable entities

Spring Data R2DBC generally works well with immutable entities such as Java records. Callbacks need to return a new instance rather than relying on mutating the object.

Example:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        String email,
        String status
) {
    public Customer withEmail(String newEmail) {
        return new Customer(id, name, newEmail, status);
    }
}
~~~

Callback:

~~~java
@Component
class NormalizeCustomerEmail
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return customer.withEmail(
                customer.email().trim().toLowerCase(Locale.ROOT)
        );
    }
}
~~~

When calling save:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

Use the Customer emitted from saved:

~~~java
return customerRepository.save(customer)
        .map(savedCustomer ->
                new CustomerResponse(
                        savedCustomer.id(),
                        savedCustomer.email()
                )
        );
~~~

Do not assume the original customer variable has changed. A callback may return a new instance, and Spring Data continues using that instance in the pipeline.

## 11. Callbacks and auditing

Auditing is a classic application of lifecycle callbacks. Spring Data supports annotations such as:

- @CreatedDate.
- @LastModifiedDate.
- @CreatedBy.
- @LastModifiedBy.

With R2DBC, auditing must be enabled through the appropriate Spring Data R2DBC configuration, such as **@EnableR2dbcAuditing**, along with an auditor provider if actor information is needed.

Entity example:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;
}
~~~

Spring Data auditing uses the callback infrastructure to populate timestamp and actor metadata during the entity lifecycle. If the application uses a reactive security context to determine the auditor, configure a ReactiveAuditorAware compatible with the version in use.

Do not write multiple custom callbacks to reimplement auditing if the standard auditing feature meets requirements. Centralized auditing configuration ensures entities share a single policy and reduces duplicate logic.

## 12. Callbacks are not a replacement for service/domain logic

EntityCallback is useful when logic is genuinely tied to the persistence lifecycle. However, callbacks should not become a container for all business rules.

For example, the following generally belong in the service/domain layer:

- Checking whether a user has permission to modify an entity.
- Calculating order prices across multiple aggregates.
- Checking account limits.
- Calling payment services or external services.
- Orchestrating multiple repositories in a single use case.
- Deciding whether to send a notification to a customer.

Tasks better suited for callbacks:

- Normalizing a property before conversion.
- Populating shared persistence metadata.
- Applying auditing.
- Transforming technical values before/after mapping.
- Handling a mapping rule repeated across many places.

Callbacks run implicitly whenever the corresponding persistence path is used. Placing critical business logic there makes it harder for callers to see why save triggers extra queries, errors, or side effects. Keeping callbacks small makes repository behavior predictable.

## 13. Callbacks do not replace ApplicationEvent or transactional outbox

EntityCallback and ApplicationEvent serve different purposes.

| Mechanism | Purpose |
|---|---|
| EntityCallback | Intervene on the entity within the mapping/persistence lifecycle |
| Spring ApplicationEvent | Notify other components in the application of an event |
| Transactional outbox | Persist event intent in the same database transaction for a publisher to send after commit |

Callbacks can return a transformed entity, making them suitable when modified data should continue into the persistence pipeline. ApplicationEvent is typically used to notify or decouple processing components. An outbox is appropriate when message publishing intent must be persisted atomically alongside business changes.

Do not send emails or publish messages directly from BeforeSave/AfterSave and assume side effects will roll back with the database. If the message has been sent and the transaction rolls back, the external system has already received the message. If the transaction commits and sending the message fails, the message may be lost.

For consistency requirements, write an outbox row in the same transaction as the entity, and then let a worker/publisher emit the message. Consumers should implement deduplication because message delivery can occur more than once.

## 14. Do callbacks participate in reactive transactions?

When a callback executes as part of a repository or template operation inside a reactive transaction, the callback publisher resides inside that persistence pipeline. A reactive callback can execute other R2DBC operations if they share the same transaction context and ConnectionFactory.

Service example:

~~~java
@Transactional
public Mono<Customer> createCustomer(CreateCustomerCommand command) {
    return customerRepository.save(toCustomer(command));
}
~~~

If ReactiveBeforeConvertCallback invokes another repository using the same ConnectionFactory, that publisher can participate in the active transaction. When the callback emits an error and the error crosses outside the transaction boundary, the transaction can roll back.

However, note these distinctions:

- A callback does not start a new transaction on its own.
- A callback does not guarantee an external non-database operation will roll back.
- A callback using a different ConnectionFactory does not automatically join the current transaction manager.
- If an error is caught and converted into a normal completion, the transaction may commit.
- A callback running after SQL has already executed may require an enclosing transaction if a post-save error must roll back the write.

Do not call subscribe() inside a callback. Return the publisher so Spring Data and the transaction manager can coordinate the entire pipeline.

## 15. Performance and operation count in callbacks

Callbacks are invoked at their corresponding lifecycle points. If a callback runs a secondary query per entity, cost can grow linearly with the number of rows.

For example, loading 500 Customers where each AfterConvertCallback calls another repository to fetch a policy risks issuing 500 additional queries. This is an N+1 query pattern.

Consider:

- Does the callback run for every row of a Flux?
- Can the required data be fetched in a single JOIN query or projection?
- Can reference metadata be loaded once in the service and passed into the operation?
- Can reference data be cached by key with clear TTL/invalidation?
- Does a reactive callback prolong transactions or hold connections longer?
- Does any callback perform blocking or CPU-heavy work?

Reactive callbacks avoid blocking threads when using proper reactive APIs, but they do not make I/O free. They still consume connections, database time, and downstream resources.

With AfterConvertCallback, pay special attention to the fact that the callback runs per entity in a Flux. Do not add a network call per row when it can be solved via a query or batch lookup.

## 16. Errors in callbacks and how to handle them

Synchronous callbacks can throw exceptions. Reactive callbacks can return an error signal. That error propagates into the persistence pipeline and typically fails the current operation.

Synchronous callback example:

~~~java
@Override
public Customer onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    if (customer.email() == null || customer.email().isBlank()) {
        throw new IllegalArgumentException("Email is required");
    }

    return customer;
}
~~~

Reactive callback example:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    if (customer.email() == null || customer.email().isBlank()) {
        return Mono.error(
                new IllegalArgumentException("Email is required")
        );
    }

    return Mono.just(customer);
}
~~~

Do not catch all exceptions in a callback and return the original entity. Doing so can mask mapping errors, data-source errors, or integrity errors.

If validation is an API input rule, perform it at the boundary/service so callers receive errors early and clearly. Callbacks can enforce final technical invariants before persistence, but should not be the sole validation layer.

With AfterSaveCallback, remember that the SQL may already have executed. If the callback emits an error without an enclosing transaction, you cannot assume the write was rolled back. Use a transaction when atomicity between the write and post-save processing is a business requirement.

## 17. Are callbacks invoked when using DatabaseClient?

DatabaseClient is a SQL-oriented API. When the application writes raw SQL and maps Rows manually:

~~~java
databaseClient.sql("""
        INSERT INTO customers (name, email, status)
        VALUES (:name, :email, :status)
        """)
    .bind("name", name)
    .bind("email", email)
    .bind("status", status)
    .fetch()
    .rowsUpdated();
~~~

DatabaseClient does not automatically create an entity lifecycle operation like R2dbcEntityTemplate. Therefore, do not expect BeforeConvertCallback, BeforeSaveCallback, or AfterSaveCallback to run automatically for this raw SQL.

If you want to use callbacks, go through an entity-oriented API with callback support, or explicitly invoke service/domain logic before executing SQL. Do not assume a raw SQL statement automatically triggers callbacks just because the table name matches an entity's @Table.

Similarly, if a callback is the only place normalizing emails, yet part of the application writes via DatabaseClient, the raw SQL write path can bypass that rule. Logic that must apply to all write paths should live in the service/domain layer or be explicitly reused across both paths.

## 18. Choosing the right callback for your purpose

| Requirement | Appropriate callback or layer |
|---|---|
| Normalize properties before mapping | BeforeConvertCallback / ReactiveBeforeConvertCallback |
| Intervene on OutboundRow before SQL | BeforeSaveCallback / ReactiveBeforeSaveCallback |
| Process entity after saving | AfterSaveCallback / ReactiveAfterSaveCallback |
| Transform entity after reading | AfterConvertCallback / ReactiveAfterConvertCallback |
| Process before deleting entity | BeforeDeleteCallback / ReactiveBeforeDeleteCallback |
| Process after deleting entity | AfterDeleteCallback / ReactiveAfterDeleteCallback |
| Domain calculation across multiple aggregates | Service/domain layer |
| Authorization check | Security/service layer |
| Send reliable message after commit | Transactional outbox |
| Call external service via reactive I/O | Usually placed in service; only use reactive callback when truly part of lifecycle |
| Run custom SQL via DatabaseClient | Invoke necessary logic explicitly; do not expect entity callbacks to run |

When choosing a callback, ask: does this logic really need to run every time the entity passes through that phase? If only one use case needs the logic, a service usually expresses the intent more clearly.

## 19. Testing synchronous callbacks

Synchronous callbacks can be tested directly by calling the method and asserting on the returned entity:

~~~java
@Test
void shouldNormalizeEmailBeforeConvert() {
    NormalizeEmailCallback callback = new NormalizeEmailCallback();

    Customer input = new Customer(
            10L,
            "An",
            "  AN@EXAMPLE.TEST ",
            "ACTIVE"
    );

    Customer result = callback.onBeforeConvert(
            input,
            SqlIdentifier.unquoted("customers")
    );

    assertThat(result.email()).isEqualTo("an@example.test");
}
~~~

This unit test verifies the transformation logic. It does not yet prove that Spring Data actually detects and invokes the callback in the persistence pipeline.

You can add integration tests with a repository or template to confirm the callback is registered in the ApplicationContext and the saved data has the normalized value.

## 20. Testing reactive callbacks

For reactive callbacks, use StepVerifier to verify emitted values, empty signals, and error signals:

~~~java
@Test
void shouldNormalizeCustomerReactively() {
    ReactiveBeforeConvertCallback<Customer> callback =
            new ReactiveCustomerCallback(policy);

    Customer input = sampleCustomer();

    StepVerifier.create(
            Mono.from(callback.onBeforeConvert(
                    input,
                    SqlIdentifier.unquoted("customers")
            ))
    )
    .assertNext(customer ->
            assertThat(customer.email()).isEqualTo("an@example.test")
    )
    .verifyComplete();
}
~~~

If the callback invokes another repository or reactive service, verify:

- Is the Publisher returned and consumed?
- Are there no internal subscribe/block calls?
- Are errors from dependencies propagated properly?
- Is callback ordering applied correctly?
- Is the transaction context preserved when needed?
- Does cancellation stop downstream work appropriately?

Use integration tests against a compatible database to verify that the callback actually runs when using R2dbcEntityTemplate or a repository. Directly mocking callbacks does not verify lifecycle wiring.

## 21. Common mistakes

| Symptom | Possible cause | How to handle |
|---|---|---|
| Callback is not called | Bean not registered or operation bypasses entity lifecycle API | Register callback in ApplicationContext and check repository/template path |
| Data is not normalized before saving | Logic placed in AfterSave or raw DatabaseClient path | Use BeforeConvert or a shared service |
| Reactive callback runs but save does not proceed | Callback returns Mono.empty() | Emit the entity or an explicit error signal |
| Callback generates repeated queries | Callback calls repository per entity | Batch, JOIN, or move lookup up to service |
| Event loop gets blocked | Synchronous callback calls blocking API or reactive callback uses block | Use lightweight synchronous logic or non-blocking reactive APIs |
| Original entity does not change | Callback returns a new instance but caller uses old object | Use the entity emitted by the save publisher |
| Row and entity are inconsistent | BeforeSave edits OutboundRow without syncing entity | Prefer editing entity before convert or manage mapping explicitly |
| AfterSave error yet data remains | No transaction wrapping the write and callback | Use a reactive transaction if atomicity is required |
| Callbacks run in the wrong order | Relying on accidental bean order | Declare @Order/Ordered |
| Callback does not run with raw SQL | DatabaseClient does not execute entity lifecycle mapping | Call logic explicitly or use an appropriate entity API |
| Side effects are duplicated or not rolled back | Sending messages/emails directly inside callback | Use outbox and consumer deduplication |
| Callback applies across more databases than expected | Shared callback bean in context | Check entity/table and scope logic explicitly |

## 22. Callback implementation workflow

When adding a callback to an application, you can follow this sequence:

1. Identify the lifecycle phase to intercept: before convert, before save, after save, after convert, or delete.
2. Determine whether the logic is a synchronous transformation or requires a Publisher.
3. Choose the corresponding callback interface.
4. Register the callback as a Spring bean.
5. Use constructor injection for dependencies.
6. For immutable entities, return a new instance.
7. For BeforeSaveCallback, only edit OutboundRow when genuinely necessary and keep data consistent.
8. If there are multiple callbacks in the same phase, declare their order.
9. Avoid blocking, manual subscribing, and non-database side effects.
10. Check whether the callback is invoked per row or per entity in batches/aggregates.
11. Ensure raw SQL paths do not bypass required logic.
12. Test the callback directly and run integration tests through the repository/template.
13. If the callback fails after SQL runs, determine whether a transaction guarantees rollback.

## 23. Conclusion

EntityCallback provides extension points in the Spring Data R2DBC entity lifecycle. Synchronous callbacks return the entity directly and fit fast, local transformations such as data normalization or metadata enrichment. Reactive callbacks return a Publisher, allowing asynchronous operations to be composed in the pipeline without blocking threads.

The main phases include BeforeConvert, BeforeSave, AfterSave, AfterConvert, BeforeDelete, and AfterDelete. Choose the callback based on exact timing: modifying the entity before conversion is usually clearest; BeforeSave is for intervening at the OutboundRow level; AfterConvert runs after mapping on read. Register callbacks as Spring beans and use @Order when execution order needs control.

Callbacks are part of the entity persistence lifecycle; they do not create transactions by themselves and do not replace service/domain logic, ApplicationEvent, or a transactional outbox. Do not use subscribe/block in reactive callbacks, do not perform blocking I/O in synchronous callbacks, and do not assume raw SQL via DatabaseClient will trigger entity callbacks. Test both the standalone callback and the actual repository/template path to confirm behavior for your Spring Data R2DBC version.
