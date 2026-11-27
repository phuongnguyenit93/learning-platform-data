# Intervening Before Save and Controlling Callback Order

Spring Data Relational R2DBC provides entity callbacks so applications can intervene on data at specific milestones in the persistence lifecycle. Callbacks fit operations that must run consistently when an entity is saved or loaded through repositories and R2dbcEntityTemplate, such as normalizing values, enriching metadata, adjusting data written to the database, or completing an entity after reading.

Two key pre-write callbacks are BeforeConvertCallback and BeforeSaveCallback. They run at two different stages: the first intervenes on the entity before Spring converts it into database data; the second runs after data has been converted into an OutboundRow but before the write statement executes. Understanding this order helps choose the right intervention point and avoid modifying data too late.

When multiple callbacks of the same type exist, execution order can be controlled with Ordered or @Order. Ordering between lifecycle stages is fixed by the persistence pipeline; @Order sorts callbacks of the same type. With R2DBC, callbacks must also follow the reactive model: return a Publisher, do not manually subscribe, and do not block.

## 1. Where do entity callbacks sit in the save lifecycle?

When calling repository.save(entity) or a corresponding save operation via R2dbcEntityTemplate, Spring Data performs multiple steps before and after sending SQL.

Conceptual model:

~~~mermaid
flowchart TD
    A[Entity passed to save] --> B[BeforeConvertCallback]
    B --> C[Convert entity to OutboundRow]
    C --> D[BeforeSaveCallback]
    D --> E[Execute INSERT or UPDATE]
    E --> F[AfterSaveCallback]
    F --> G[Return reactive result]
~~~

The stages have distinct meanings:

1. **Before convert:** the entity is still a Java object. You can normalize it, compute derived values, or return a new entity.
2. **Convert:** Spring Data maps the entity into an OutboundRow, representing the columns and values to be bound.
3. **Before save:** the callback receives the entity and OutboundRow; it can adjust the data representation about to be written.
4. **Save:** the database executes INSERT or UPDATE.
5. **After save:** the callback can observe or finalize the result after the write operation.

Exact API names and signatures must match your project's Spring Data R2DBC version. The examples below illustrate common reactive callback APIs in Spring Data Relational.

### BeforeConvertCallback

BeforeConvertCallback<T> is invoked before the entity is converted into an OutboundRow. The callback receives the entity and the table name, then returns a Publisher<T>.

Use this callback when you want to modify the entity itself before mapping occurs, for example:

- Normalizing strings before saving.
- Generating slugs or derived search values.
- Populating application-managed timestamps or metadata.
- Normalizing business identifiers.
- Validating or transforming data state before writing.

Because the callback returns an entity, it fits immutable entities such as Java records: create and return a new instance containing the adjusted values.

### BeforeSaveCallback

BeforeSaveCallback<T> runs after the entity has been converted into an OutboundRow, but before data is written to the database. The callback receives the entity, the OutboundRow containing mapped data, and the SqlIdentifier representing the target table.

This callback is appropriate when you need to adjust the exact data the database is about to receive, such as adding or modifying a column in the OutboundRow. Modifying the row does not necessarily mutate the original entity object; distinguish between data written to the database and the object returned to the caller.

### AfterSaveCallback

AfterSaveCallback<T> runs after the save operation. It is suitable for observing results or adding post-save processing within the same reactive pipeline. If the callback emits an error, the save publisher can terminate with an error even though the write statement has already executed.

When a side effect must happen only after the transaction commits, do not assume AfterSaveCallback means after-commit. This callback is after the save operation, while an enclosing transaction may still be open and later roll back.

## 2. Normalizing an entity before mapping

Example Customer entity using a record:

~~~java
@Table("customers")
public record Customer(
    @Id UUID id,
    String name,
    String normalizedName,
    Instant createdAt
) {
    public Customer withNormalizedName(String value) {
        return new Customer(id, name, value, createdAt);
    }
}
~~~

Suppose we want to store normalizedName derived from name, without duplicating normalization logic in every service.

Create the callback:

~~~java
@Component
public class NormalizeCustomerBeforeConvert
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String normalized = customer.name()
            .trim()
            .toLowerCase(Locale.ROOT);

        return Mono.just(customer.withNormalizedName(normalized));
    }
}
~~~

Exact callback imports may vary by Spring Data Relational/R2DBC version; use the callback package provided by your project's dependencies. The core idea is that the callback receives the entity, produces the new value, and returns a Publisher<Customer>.

When the repository saves Customer, Spring Data takes the entity returned by the callback and continues mapping that entity into a row. Consequently, normalizedName is computed before SQL is generated.

### Why use Locale.ROOT?

Data normalization should not depend on the default locale of the host running the application. For technical codes or strings used in case-insensitive matching, Locale.ROOT keeps results consistent across environments.

However, lower-casing is not the right normalization rule for every language or every search requirement. If Unicode normalization, accent folding, or collation rules are needed, define the data contract clearly and apply the same rule at both write time and query time.

### Do not overwrite source data unintentionally

If name is user-entered data, preserve it as-is and store the derived value in normalizedName. Do not automatically overwrite the original field if the business needs the original casing preserved.

If the entity is a mutable class, the callback can update the field and return the same entity. With records or immutable objects, create a new instance. In both cases, the callback should behave deterministically and be safe to repeat without unexpected mutations.

## 3. Adjusting OutboundRow before writing

BeforeSaveCallback allows intervening after mapping. This is an option when you want to change a column value without changing the Java entity.

Illustrative callback adding a search_key column to the row:

~~~java
@Component
public class AddCustomerSearchKeyBeforeSave
        implements BeforeSaveCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeSave(
            Customer customer,
            OutboundRow row,
            SqlIdentifier table) {

        String searchKey = customer.name()
            .trim()
            .toLowerCase(Locale.ROOT);

        row.put(
            SqlIdentifier.unquoted("search_key"),
            Parameter.from(searchKey)
        );

        return Mono.just(customer);
    }
}
~~~

OutboundRow represents the values to be bound into the write statement. SqlIdentifier specifies the column, while Parameter represents the bound value. Exact API types and packages may differ by Spring Data R2DBC version; check your dependency version before copying imports.

Use this approach when:

- The value only needs to exist in the database representation.
- The entity has no corresponding field.
- Mapped values need adjustment right before writing.
- You want to intervene in how a specific column is bound.

If the derived value needs to appear in the returned object, be used in domain logic, or be serialized for an API, place it on the entity before conversion rather than only editing OutboundRow.

### Do not add columns that do not exist in the schema

Before adding a value to OutboundRow, ensure the column exists and has a compatible data type. Callbacks do not replace migrations. If a callback attempts to write a column missing from the schema, the database will return a SQL or missing-column error.

### Handle NULL with the right type

If a value can be null, do not construct a Parameter from a null reference without checking API support. Use the typed null parameter representation provided by your project's Spring Data R2DBC API. Nullable and non-nullable columns should also have clear policies.

## 4. Distinguishing BeforeConvert and BeforeSave

Both callbacks run before the database writes data, but they intervene at two different layers.

| Criterion | BeforeConvertCallback | BeforeSaveCallback |
| --- | --- | --- |
| Primary inputs | Entity and table identifier. | Entity, OutboundRow, and table identifier. |
| Timing | Before mapping entity into a row. | After mapping, before executing the write statement. |
| What can change | Java entity. | OutboundRow; can return an adjusted entity per API. |
| Best fit for | Normalizing domain data, computing derived fields. | Adjusting database representation or specific column values. |
| When to choose | Value must exist in both entity and row. | Value only needs adjustment at the persistence mapping layer. |

For example, if you want to store the trimmed customer name in the name property itself, use BeforeConvertCallback. If you want to keep the original name in the entity while writing a separate search_key column, BeforeSaveCallback may be appropriate.

Avoid using both callbacks to perform the same transformation. If the first callback normalizes the entity and the second normalizes the same field again, the logic becomes hard to follow and prone to discrepancies between the returned object and database data.

## 5. Callback ordering across stages

Lifecycle stage ordering is dictated by the persistence pipeline. For a standard save operation:

1. BeforeConvertCallbacks run before mapping.
2. Spring Data converts the entity into an OutboundRow.
3. BeforeSaveCallbacks run before SQL is executed.
4. The database executes the write operation.
5. AfterSaveCallbacks run after the write operation.

You cannot use @Order to make a BeforeSaveCallback run before the convert stage. @Order sorts callbacks within the same callback stage; it does not alter the fixed order between lifecycle stages.

For example, a callback that normalizes the name needs to run before a callback that computes the search key. Both can be BeforeConvertCallbacks, with their order specified via @Order.

~~~java
@Component
@Order(10)
public class TrimCustomerName
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return Mono.just(customer.withName(customer.name().trim()));
    }
}
~~~

~~~java
@Component
@Order(20)
public class BuildCustomerSearchKey
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String key = customer.name().toLowerCase(Locale.ROOT);
        return Mono.just(customer.withSearchKey(key));
    }
}
~~~

The example assumes Customer has withName and withSearchKey methods. The first callback trims the name; the second receives the entity updated by the first callback and builds the search key from that value.

In Spring ordering, lower order values have higher precedence and execute earlier. Ordered constants can be used instead of magic numbers:

~~~java
@Component
public class TrimCustomerName
        implements BeforeConvertCallback<Customer>, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        return Mono.just(customer.withName(customer.name().trim()));
    }
}
~~~

### Avoid two callbacks modifying the same field without a contract

If two callbacks both write normalizedName, the final result depends on order. Clearly designate which callback owns the field and which only reads the result. If callbacks share the same order, do not rely on bean registration order or classpath scan order to determine the outcome.

For tightly coupled logic, a single callback orchestrating sequential steps can be easier to understand than many small callbacks modifying one entity.

## 6. Ordering among callbacks of the same type

When multiple callbacks implement the same interface, order can be controlled via:

- @Order on the callback class.
- Ordered and getOrder().
- Bean ordering metadata supported by the framework.

Example:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class NormalizeCodeCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

~~~java
@Component
@Order(Ordered.LOWEST_PRECEDENCE - 10)
public class AddAuditMetadataCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Callbacks with smaller order values run first. Using Ordered.HIGHEST_PRECEDENCE and Ordered.LOWEST_PRECEDENCE avoids magic numbers when placing callbacks near the beginning or end of the chain.

If multiple callbacks have the same order, do not rely on arbitrary container bean discovery order. When order has business significance, assign explicit order values or combine dependent steps into one callback with deterministic internal order.

### Order does not change transaction boundaries

@Order only controls callback order within the framework-invoked chain. It does not start a transaction, commit data, or guarantee a callback runs after transaction commit. To control transactions, use @Transactional or TransactionalOperator at the proper boundary.

## 7. Reactive callbacks must return a Publisher

R2DBC entity callbacks are reactive. A callback returns Publisher<T>, commonly using Mono<T> when processing a single entity.

Do not call subscribe() inside a callback:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    auditService.record(customer).subscribe();
    return Mono.just(customer);
}
~~~

This creates a detached subscription. Spring Data does not wait for the audit to complete, audit errors do not propagate to the save operation, and the transaction context may not be shared as intended.

If an asynchronous step is genuinely needed to produce the entity, compose it into the returned publisher:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    return policyService.resolveCustomerTier(customer)
        .map(customer::withTier);
}
~~~

The example assumes resolveCustomerTier returns Mono<CustomerTier> and withTier creates a new entity. Spring Data waits for the callback publisher to complete before continuing mapping and saving.

However, callbacks should not become a place that calls multiple remote services per entity. That makes persistence depend on the network, increases latency, and introduces hard-to-control side effects. If data needed for saving must be fetched from another service, orchestrate that in the application service before calling the repository.

### Do not block inside callbacks

Do not call block() to wait for reactive data:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    CustomerTier tier = policyService.resolveCustomerTier(customer).block();
    return Mono.just(customer.withTier(tier));
}
~~~

This breaks non-blocking execution, can deadlock on event-loop threads, and detaches the callback from the reactive transaction context. Return a publisher and compose using map, flatMap, then, or other suitable operators.

## 8. Callbacks can emit errors and affect the save operation

If BeforeConvertCallback or BeforeSaveCallback emits an error, the save pipeline normally stops before the write statement executes. This is an appropriate place for checks or transformations that must succeed before writing.

Example:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product product,
        SqlIdentifier table) {

    if (product.price().signum() < 0) {
        return Mono.error(
            new InvalidProductPriceException(product.price())
        );
    }

    return Mono.just(product);
}
~~~

If the callback emits an error, repository save returns an error publisher. The application service can translate the exception into an appropriate domain/API error.

AfterSaveCallback behaves differently: the write statement may already have executed before the callback runs. If a post-save callback emits an error:

- When save is inside a transaction and the error propagates past the transaction boundary, the transaction can roll back.
- Without an enclosing transaction, the database write may already have succeeded even though the publisher returns the callback error.
- Callers may retry and cause duplicate operations if idempotency is absent.

Therefore, do not put an unreliable network operation in AfterSaveCallback and treat its failure as proof that the database did not save.

### Callbacks are not the place to send emails or arbitrary notifications

If events must be emitted after data commits, AfterSaveCallback is not synonymous with after-commit. An outer transaction can still roll back after the callback. Use proper transaction synchronization or a transactional outbox so messages are emitted based on committed state.

## 9. Callbacks and auditing

Spring Data R2DBC supports auditing to automatically populate fields such as:

- CreatedDate: creation time.
- LastModifiedDate: last update time.
- CreatedBy: creator.
- LastModifiedBy: last updater.

Entity example:

~~~java
@Table("orders")
public record Order(
    @Id UUID id,
    String status,
    @CreatedDate Instant createdAt,
    @LastModifiedDate Instant updatedAt,
    @CreatedBy String createdBy,
    @LastModifiedBy String modifiedBy
) {}
~~~

Enable auditing using the corresponding Spring Data R2DBC configuration:

~~~java
@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
~~~

If the current user needs to be resolved from a reactive security context, configure a ReactiveAuditorAware<T> returning Mono<T>:

~~~java
@Component
public class CurrentAuditor implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }
}
~~~

The example assumes the application uses reactive Spring Security with an authentication in the Reactor Context. If there is no current user, decide whether to return Mono.empty() or provide a system actor per your application contract.

Auditing is implemented on top of internal entity callbacks. Avoid also manually populating the same fields in another callback unless intentional, as that creates two value sources and unnecessary ordering dependencies.

### Creation and update timestamps must have clear semantics

Do not always overwrite createdAt on every save. This field should preserve the initial creation time. updatedAt can change on every successful update. For immutable entities, the auditing infrastructure must be configured to create new copies compatible with constructor/property mapping.

Do not pull timestamps from multiple inconsistent sources. If the database has default timestamps or triggers, decide whether the primary source of truth is the application or the database and map results accordingly.

## 10. Callbacks when reading data

Besides pre-save and post-save callbacks, Spring Data Relational also has callbacks in the load/convert flow, depending on version and API:

- Callbacks after a row is loaded.
- Callbacks after a row is converted into an entity.

They can be useful for finalizing an object after reading, but should not be used to mask a broken schema mapping. If columns are missing from SELECT or converters are wrong, fix the mapping first.

Distinguishing read and write callbacks:

| Group | Purpose | Example |
| --- | --- | --- |
| BeforeConvert | Prepare entity before writing. | Trim name, compute normalized field. |
| BeforeSave | Adjust row before writing. | Add a database representation value. |
| AfterSave | Process after write operation. | Observe save result or add metadata to returned object. |
| AfterLoad/AfterConvert | Finalize entity in the read pipeline. | Compute a derived value not persisted separately. |

Specific callback names, ordering, and signatures must be verified against your Spring Data Relational version. Do not assume read callbacks can replace SELECT joins or lazy loading; R2DBC does not provide lazy loading automatically like traditional blocking ORMs.

## 11. Where and when are callbacks invoked?

Callbacks are integrated into Spring Data entity mapping operations, such as repositories and R2dbcEntityTemplate. If the application uses DatabaseClient to write raw SQL and map rows manually, do not assume entity lifecycle callbacks will run automatically.

Repository example:

~~~java
return customerRepository.save(customer);
~~~

Or template:

~~~java
return template.insert(Customer.class)
    .using(customer);
~~~

These operations go through Spring Data's mapping lifecycle, where configured entity callbacks are applied.

Meanwhile:

~~~java
return databaseClient.sql("""
        INSERT INTO customers (id, name)
        VALUES (:id, :name)
        """)
    .bind("id", customer.id())
    .bind("name", customer.name())
    .fetch()
    .rowsUpdated();
~~~

This is direct SQL. The application is responsible for normalizing data, binding parameters, and mapping results; do not expect entity callbacks to be invoked automatically.

This matters when a project mixes repositories with raw SQL. If a normalization rule lives only in a repository callback, writes through DatabaseClient can bypass that rule. Put shared business rules into a domain/application service or a shared component invoked by all write paths.

## 12. Callbacks and repository saveAll

When saving multiple entities, callbacks can be invoked per entity along the corresponding mapping path. Do not assume a callback runs only once for the entire batch.

This affects:

- Performance if the callback performs secondary queries.
- Processing order of individual entities.
- Side effects if the callback sends notifications.
- Consistency if one entity in the batch emits an error.
- Timestamp or derived-value generation per element.

For instance, a callback that only normalizes strings is lightweight and fine. A callback that calls a remote service per entity can trigger hundreds of requests during one saveAll call. If reference data must be loaded, consider fetching it once in the service and passing it into the entities before calling the repository.

If using DatabaseClient with a batch SQL statement or custom bulk insert, entity lifecycle callbacks are not automatically guaranteed. Check the exact execution path.

## 13. Avoiding recursion and side effects in callbacks

Callbacks run inside the persistence pipeline. If a callback calls the repository again to save the very entity being processed, it can trigger the callback again and create a loop.

Example to avoid:

~~~java
@Component
public class UpdateCustomerCallback
        implements BeforeConvertCallback<Customer> {

    private final CustomerRepository repository;

    public UpdateCustomerCallback(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        return repository.save(customer)
            .thenReturn(customer);
    }
}
~~~

This callback calls save again, which can invoke the same callback again in an infinite loop. A callback should transform the passed-in entity or row, not re-invoke persistence operations for that same entity.

Also avoid:

- Sending emails or calling webhooks.
- Publishing messages directly before commit.
- Executing secondary queries per entity when they can be precomputed.
- Reading global state or using mutable singletons to pass data between callbacks.
- Using callbacks to run multi-step business workflows.

Callbacks should focus on small, deterministic, testable persistence concerns.

## 14. Registering callbacks in the Spring context

Callbacks can be registered as Spring beans via @Component or @Bean configuration. Spring Data uses the entity callback infrastructure to discover and run callbacks matching the entity type.

Configuration registration example:

~~~java
@Configuration
public class CustomerCallbackConfiguration {

    @Bean
    NormalizeCustomerBeforeConvert normalizeCustomerBeforeConvert() {
        return new NormalizeCustomerBeforeConvert();
    }
}
~~~

If a callback needs dependencies, constructor injection can be used:

~~~java
@Component
public class NormalizeCustomerBeforeConvert
        implements BeforeConvertCallback<Customer> {

    private final CustomerNameNormalizer normalizer;

    public NormalizeCustomerBeforeConvert(
            CustomerNameNormalizer normalizer) {
        this.normalizer = normalizer;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        return Mono.just(
            customer.withNormalizedName(
                normalizer.normalize(customer.name())
            )
        );
    }
}
~~~

Do not instantiate callbacks with `new` inside a service if you want Spring to manage ordering and dependency injection. Registering callbacks as beans lets the framework apply callbacks consistently.

## 15. Testing callbacks and execution order

Testing callbacks should verify two things: that the callback runs at the expected stage, and that the final written data matches expectations.

### Unit testing BeforeConvertCallback

You can invoke the callback directly to verify the transformation:

~~~java
@Test
void normalizesNameBeforeConversion() {
    Customer input = new Customer(
        UUID.randomUUID(),
        "  Alice Example  ",
        null,
        Instant.now()
    );

    Customer result = Mono.from(
        callback.onBeforeConvert(input, SqlIdentifier.unquoted("customers"))
    ).block();

    assertEquals("alice example", result.normalizedName());
    assertEquals("  Alice Example  ", result.name());
}
~~~

This is a unit test for callback logic; calling block in a synchronous test is acceptable as long as it is not in production reactive flows. If tests run in reactive style, StepVerifier can be used instead.

### Integration tests confirming persisted data

Call the real repository and read back:

~~~java
@Test
void savesNormalizedName() {
    Customer customer = new Customer(
        UUID.randomUUID(),
        "  Alice Example  ",
        null,
        Instant.now()
    );

    StepVerifier.create(
        customerRepository.save(customer)
            .flatMap(saved ->
                customerRepository.findById(saved.id())
            )
    )
    .assertNext(saved ->
        assertEquals("alice example", saved.normalizedName())
    )
    .verifyComplete();
}
~~~

This test confirms the callback is wired into the repository mapping path and the normalizedName value is written to the database.

### Testing callback ordering

If order matters, use two callbacks with different @Order values and verify the outcome. For example, callback A trims the string first, and callback B builds a slug from the trimmed string. If the order were reversed, the test should catch the difference in output.

Do not test only getOrder(); test the final pipeline output, because what matters is that the framework actually discovers and runs the callbacks in order.

### Testing callback errors

Verify that when a pre-save callback emits an error, no matching record appears in the database. For errors from AfterSaveCallback, test both with and without a transaction to understand actual persistence state. Do not assume an error publisher always means INSERT did not occur.

## 16. Common mistakes when using callbacks

| Mistake | Cause | How to handle |
| --- | --- | --- |
| Callback does not run | Callback not registered as a bean or operation goes through raw SQL. | Register bean and use repository/template mapping path. |
| Normalization missing in DB | Callback updates entity without returning new entity, or edits wrong OutboundRow. | Return updated entity properly and test readback. |
| Callbacks run in wrong order | No order declared or multiple callbacks share same order. | Use @Order/Ordered explicitly. |
| Entity data differs from DB | Edited only OutboundRow without updating entity. | Choose the right callback layer based on where change is needed. |
| Save is unusually slow | Callback performs network calls or extra queries per entity. | Keep callbacks light; orchestrate I/O in services. |
| Callback causes infinite loop | Calling repository.save again inside callback. | Only transform the passed-in entity/row. |
| Post-save callback error surprises caller | AfterSaveCallback emits error after SQL already ran. | Review transaction, idempotency, and side-effect placement. |
| Event emitted despite transaction rollback | Confusing AfterSave with after-commit. | Use outbox or an appropriate after-commit mechanism. |
| Bulk SQL bypasses callback rules | DatabaseClient does not pass through entity lifecycle mapping. | Share logic in service/domain or invoke explicitly in bulk paths. |
| Auditing gets overwritten | Multiple callbacks update audit fields. | Use auditing infrastructure or establish a single field owner. |

## 17. Callback design workflow

When you need to intervene on data before saving, follow this sequence:

1. **Identify what data needs to change:** Java field or database representation value?
2. **Choose the stage:** use BeforeConvertCallback to modify the entity before mapping; use BeforeSaveCallback to modify OutboundRow.
3. **Keep callbacks pure and small:** avoid network calls, side effects, and recursive repository calls.
4. **Use reactive composition:** return a Publisher; do not subscribe or block in production.
5. **Define ordering:** set @Order/Ordered for same-type callbacks if dependencies exist.
6. **Avoid multiple writers:** each derived or audit field should have a clear owner.
7. **Consider transactions:** AfterSave does not mean after-commit; use an outbox for guaranteed side effects.
8. **Check write paths:** repositories/templates invoke callbacks; raw SQL needs separate handling.
9. **Test logic and integration:** test callbacks standalone, then save/readback against a real database.
10. **Measure performance:** especially with saveAll and callbacks doing I/O.

Entity callbacks help centralize persistence rules that must run consistently across the entity lifecycle. BeforeConvertCallback fits modifying the entity before mapping; BeforeSaveCallback fits adjusting the row being written; AfterSaveCallback runs after the save operation but does not guarantee the transaction has committed. Use @Order or Ordered to define ordering among callbacks in the same stage, keep reactive publishers unbroken, and test through actual repositories/templates so data is intercepted at the right moment.
