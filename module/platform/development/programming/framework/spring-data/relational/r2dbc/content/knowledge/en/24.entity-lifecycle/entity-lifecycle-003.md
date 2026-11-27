# Preparing Data Before Conversion with BeforeConvertCallback

## 1. Position of BeforeConvertCallback in the entity lifecycle

When saving an entity with Spring Data R2DBC, the application passes a Java object to a repository or `R2dbcEntityTemplate`. Spring Data needs to convert that object into values suitable for SQL columns before generating and executing an INSERT or UPDATE statement.

`BeforeConvertCallback` is an extension point in the entity lifecycle, invoked before Spring Data converts the entity into write data for the database. The callback allows preparing or normalizing the object right before the mapping step.

For example, before saving `Customer`, the application can:

- Normalize email to lowercase and trim leading/trailing whitespace.
- Generate a slug or business code if the entity does not have one yet.
- Assign an application-managed UUID.
- Populate application-managed timestamps.
- Normalize an enum value or value object before a converter processes it.
- Ensure a required property already has a value according to domain rules.

Callbacks are suitable for small, deterministic transformations directly tied to preparing an entity for persistence. Complex business rules should still reside in the domain model or application service.

## 2. Position of the callback in the write flow

A high-level entity write flow:

```mermaid
flowchart TD
    A[Repository.save(entity)] --> B[Detect new or existing entity]
    B --> C[BeforeConvertCallback]
    C --> D[Convert entity to OutboundRow]
    D --> E[BeforeSaveCallback]
    E --> F[Build and bind SQL]
    F --> G[Execute INSERT or UPDATE]
    G --> H[AfterSaveCallback]
    H --> I[Return entity via Mono]
```

`BeforeConvertCallback` runs before the entity is converted into an `OutboundRow`. This is the appropriate point to modify Java properties that the mapping layer will read.

In the read flow, Spring Data converts data from SQL rows into entities; `BeforeConvertCallback` is not a read callback. For read operations, there are other callbacks such as post-conversion callbacks depending on the store and version.

Exact callback ordering details and steps depend on the implementation, but the principle to remember is: **BeforeConvert acts on the entity before mapping; BeforeSave acts at the stage right before saving, once outbound data has already been created.**

## 3. BeforeConvertCallback in Spring Data R2DBC

With R2DBC, callbacks execute in the reactive flow. The callback receives the entity and table identifier, then returns a `Publisher` containing the prepared entity.

Example of the reactive callback style commonly used in Spring Data R2DBC:

```java
import org.reactivestreams.Publisher;
import org.springframework.data.r2dbc.mapping.event.BeforeConvertCallback;
import org.springframework.data.relational.core.sql.SqlIdentifier;
import org.springframework.stereotype.Component;

@Component
public class CustomerBeforeConvertCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        customer.setEmail(customer.getEmail().trim().toLowerCase(Locale.ROOT));
        return Mono.just(customer);
    }
}
```

The code snippet requires the corresponding `Mono` and `Locale` imports. Callback package names/signatures must match the project's Spring Data R2DBC version; Spring Data Relational versions using imperative and reactive callbacks may have separate interfaces/packages. With R2DBC, choose the reactive interface for the store being used rather than mistakenly implementing a synchronous callback from another module.

Key points in the example:

- The callback is registered as a Spring bean using `@Component`.
- The generic type `Customer` scopes the callback to the `Customer` entity.
- `SqlIdentifier table` indicates the table identifier being processed.
- `onBeforeConvert` returns a publisher containing the normalized entity.
- Do not call `block()` or manually `subscribe()` inside the callback.

If the callback does not modify the entity, still return the entity:

```java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {
    return Mono.just(customer);
}
```

The callback needs to emit the entity so mapping can proceed. If it returns `Mono.empty()`, the pipeline may complete without performing the save operation; do not use empty as a way to skip errors or represent an invalid entity.

## 4. Normalizing data before mapping

An application often wants emails to share a consistent format regardless of whether users enter uppercase, lowercase, or whitespace.

Entity:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Column("email_address")
    private String email;

    // getters and setters
}
```

Callback:

```java
@Component
public class NormalizeCustomerEmailCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        if (customer.getEmail() != null) {
            customer.setEmail(
                    customer.getEmail().trim().toLowerCase(Locale.ROOT));
        }

        return Mono.just(customer);
    }
}
```

When the application saves:

```java
Customer customer = new Customer();
customer.setName("Lan Nguyen");
customer.setEmail("  LAN@EXAMPLE.COM  ");

return customerRepository.save(customer);
```

The callback normalizes the email to `lan@example.com` before Spring Data creates the write data. As a result, the database receives the normalized value.

### 4.1. Why use Locale.ROOT?

Parameterless `String.toLowerCase()` uses the JVM's default locale. Case conversion results can differ across locales, especially for certain characters. For technical strings such as emails, slugs, or identifiers independent of UI language, `Locale.ROOT` avoids server-locale dependence.

Normalization in a callback does not replace a unique constraint. If emails must be unique after normalization, the schema still needs an appropriate constraint, such as a unique constraint on the normalized email column. Concurrent requests can still pass an existence check before insert; a database constraint is the final safeguard.

## 5. Generating a UUID before conversion

If the application is the authoritative source for IDs, a callback can populate a UUID when the entity does not have an ID yet:

```java
@Table("customer")
public class Customer {

    @Id
    private UUID id;

    private String name;
}
```

```java
@Component
public class CustomerIdCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        if (customer.getId() == null) {
            customer.setId(UUID.randomUUID());
        }

        return Mono.just(customer);
    }
}
```

When an ID already exists, the callback keeps the existing ID. This ensures repeated operations on the same entity do not generate a new ID on every save.

### 5.1. Coordinating with newness detection

Assigning an ID in a callback before mapping can affect the new-entity detection mechanism. Spring Data typically uses the ID or `@Version`/`Persistable.isNew()` to determine whether an entity is new. If the initial ID is `null` but a callback assigns a UUID before the framework decides insert vs. update, verify the processing order in the Spring Data version in use.

With application-assigned IDs, design newness detection explicitly instead of assuming a non-null ID always means an existing entity. You can use `Persistable<ID>` to provide `isNew()` or a nullable version property depending on the appropriate model.

If a callback is not needed, generating the UUID in a factory method/domain constructor is often clearer because the ID exists as soon as the aggregate is created. Only place ID generation logic in `BeforeConvertCallback` when it is genuinely a shared persistence policy for the entity.

### 5.2. Do not overwrite database-managed IDs

If the ID is generated by the database via identity or sequence, do not generate a different value in a callback. Leave the ID unset and use Spring Data/driver generated-ID support. Assigning an ID in a callback can prevent the database from using its default/identity or cause Spring Data to choose the update path by mistake.

## 6. Populating timestamps before saving

A callback can assign creation or update timestamps if the application is the authoritative source for timestamps.

Example using `Clock` for testability:

```java
@Component
public class CustomerTimestampCallback
        implements BeforeConvertCallback<Customer> {

    private final Clock clock;

    public CustomerTimestampCallback(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        Instant now = clock.instant();

        if (customer.getCreatedAt() == null) {
            customer.setCreatedAt(now);
        }
        customer.setUpdatedAt(now);

        return Mono.just(customer);
    }
}
```

`Clock` can be configured as a bean:

```java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
```

In the example, `createdAt` is only set if unset; `updatedAt` is updated every time the callback runs. Because the callback can run for both inserts and updates, do not unconditionally overwrite `createdAt`.

### 6.1. Choosing the time source

If the timestamp must reflect the time the database records the transaction, using a database default or expression may be more appropriate:

```sql
created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
```

In that case, do not set `createdAt` in a callback if you want the database to apply its default. If the callback sets a Java value and mapping sends that column in INSERT, the database receives the explicit value instead of using the default.

If the timestamp represents when the application received an event or when the domain created a command, `Clock` in Java can be the appropriate source. Clearly define the timestamp's semantics before choosing where to assign it.

## 7. Generating slugs or business codes

A callback can generate a slug from a name when the entity does not have a slug yet:

```java
@Component
public class ArticleSlugCallback
        implements BeforeConvertCallback<Article> {

    @Override
    public Publisher<Article> onBeforeConvert(
            Article article,
            SqlIdentifier table) {

        if (article.getSlug() == null || article.getSlug().isBlank()) {
            article.setSlug(toSlug(article.getTitle()));
        }

        return Mono.just(article);
    }

    private String toSlug(String value) {
        return Normalizer.normalize(value, Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9]+", "-")
                .replaceAll("^-|-$", "");
    }
}
```

This is a simple example; handling Vietnamese, Unicode, punctuation, and non-ASCII characters may require product-specific slug rules.

The callback only derives a value from existing data. If the slug must be unique, do not query to check existence and append a suffix inside the callback without race-condition protection. Two requests can generate the same slug concurrently. Use a unique constraint and a retry/unique-generation strategy in the application service or database.

## 8. How do BeforeConvertCallback and BeforeSaveCallback differ?

Spring Data Relational provides several callbacks at different points in the lifecycle. Two callbacks that are easy to confuse are `BeforeConvertCallback` and `BeforeSaveCallback`.

| Callback | Timing | Data received by callback | Suitable purpose |
| --- | --- | --- | --- |
| `BeforeConvertCallback` | Before the entity is converted into outbound data | Entity and table identifier | Normalize or populate Java properties |
| `BeforeSaveCallback` | After the entity has been converted into outbound representation, before saving | Entity, outbound row, and table identifier | Adjust outbound data before SQL is executed |
| `AfterSaveCallback` | After the save operation | Entity and related data per API | Observe or process after saving |
| Post-convert/read callback | After a row is converted into an entity | Loaded entity | Populate state after read mapping |

For example, if you want to normalize `customer.email` on the object so subsequent layers also see the normalized value, `BeforeConvertCallback` is suitable. If you need to directly adjust a value in `OutboundRow` after mapping, `BeforeSaveCallback` is more appropriate.

Do not use `BeforeSaveCallback` to replace everything `BeforeConvertCallback` does; the two extension points have different inputs and purposes.

## 9. Callbacks are not a replacement for domain logic

Callbacks are invoked automatically during persistence. Therefore, putting too much business logic into callbacks can make entity behavior unpredictable when reading service code.

Good candidates for `BeforeConvertCallback`:

- Normalizing data representations before saving.
- Populating technical values determined from the entity.
- Assigning timestamps according to persistence policy.
- Generating a technical identifier when the entity lacks one.
- Applying a shared mapping rule across all write paths of an entity.

Better placed in the domain model/application service:

- Checking whether an order is allowed to be confirmed.
- Calculating totals, taxes, or discounts across multiple rules.
- Checking inventory from another aggregate.
- Calling a payment service or remote service.
- Emitting domain events based on a business decision.
- Determining state based on user permissions or request context.

Callbacks should not become a hiding place for multi-step business workflows. Readers of `repository.save(entity)` should be able to expect that callbacks prepare persistence data rather than unexpectedly executing a major use case.

## 10. Avoid querying the database or calling services from callbacks

Reactive callbacks can return a `Publisher`, but that does not mean they should be used to perform arbitrary network operations before every save.

For example, avoid designing a callback that calls another repository to look for duplicate slugs, load a customer, or make an HTTP call for exchange rates before saving the entity. Problems that can arise:

- Every save generates multiple extra database round trips.
- Callbacks can introduce circular dependencies between repositories and callback beans.
- A callback applied implicitly across many use cases makes costs hard to observe.
- Calling external services can prolong transaction/connection hold times.
- Errors from external systems fail the save operation in unpredictable ways.
- Pre-write checks still suffer from race conditions without constraints.

If data from another system is needed to determine entity state, fetch that data in the application service before calling the repository, then pass the result into the domain object. Callbacks should focus on local, predictable transformations.

If a callback genuinely needs asynchronous computation, keep it non-blocking, return the publisher properly, and evaluate its impact on lifecycle, transactions, and latency. Do not call `.block()` in a reactive callback.

## 11. Callbacks must be stable when run multiple times

Do not assume a callback runs only once in an object's lifecycle. An entity can be saved multiple times; retries or other persistence operations can also cause callbacks to run again.

Unsafe example:

```java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    customer.setReference(UUID.randomUUID().toString());
    return Mono.just(customer);
}
```

Every save generates a new reference, potentially altering a business identifier even when the entity already had a reference.

Check before assigning:

```java
if (customer.getReference() == null || customer.getReference().isBlank()) {
    customer.setReference(UUID.randomUUID().toString());
}
```

A callback that is idempotent when re-run does not alter values already normalized or generated on a previous run. Idempotency makes retries and repeated save operations much more predictable.

## 12. Do not overwrite database-managed values

Some columns are generated or managed by the database:

- Identity/sequence IDs.
- `created_at DEFAULT CURRENT_TIMESTAMP`.
- Generated columns.
- Columns computed by triggers.
- Values assigned by the database on INSERT.

If a callback assigns values to these columns before mapping, the INSERT statement may send an explicit value and prevent the database from applying its default. Example:

```java
customer.setCreatedAt(clock.instant());
```

If the schema defines `created_at DEFAULT CURRENT_TIMESTAMP`, assigning it in a callback can prevent the default from being used.

Establish the authoritative source:

| Managing source | Approach |
| --- | --- |
| Application | Callback or domain factory assigns the value before mapping |
| Database | Omit the property from writes, use default/generated values, and re-read if needed |
| Both needed as fallback | Keep Java policy and schema aligned, and inspect the actual SQL |

For properties fully managed by the database, consider appropriate read-only mapping such as `@ReadOnlyProperty` and generated-value configuration based on database/driver capabilities.

## 13. Ordering when multiple callbacks exist

An application can have multiple callbacks for the same entity or lifecycle phase. For example, one callback normalizes email and another generates a slug.

When order matters, specify callback ordering explicitly using Spring's ordering mechanisms, such as `@Order` or `Ordered` when supported by the callback infrastructure of your version:

```java
@Component
@Order(10)
public class NormalizeNameCallback
        implements BeforeConvertCallback<Customer> {
    // ...
}

@Component
@Order(20)
public class CustomerSearchKeyCallback
        implements BeforeConvertCallback<Customer> {
    // ...
}
```

This example assumes the second callback needs the value already normalized by the first callback. If callbacks are independent, do not introduce unnecessary ordering dependencies.

Reactive callbacks execute in a framework-managed chain. Each callback must return a publisher of the processed entity so subsequent callbacks and the mapping step receive the updated result. Check the ordering rules for your Spring Data version.

## 14. Which operations trigger the callback?

`BeforeConvertCallback` is tied to converting an entity into write data. Typically, it is invoked in insert/update flows when an entity is persisted through the corresponding Spring Data Relational APIs.

Do not assume the callback is invoked by default for:

- Every custom SQL query written with `DatabaseClient`.
- Bulk UPDATE/DELETE statements using `@Modifying`.
- SQL statements executed directly via R2DBC `Connection`.
- Entity read operations.
- An entity converted manually outside Spring Data's mapping pipeline.

Low-level persistence APIs can bypass entity lifecycle callbacks because they do not pass through the same repository/template mapping flow. If an application uses multiple write paths, decide where normalization is applied so no write path skips required rules.

In particular, `DatabaseClient.sql("UPDATE ...")` does not automatically invoke callbacks per entity because the statement operates directly on SQL. If the same rules are needed, invoke normalization logic from the service or use a shared persistence adapter.

## 15. Registering callbacks in Spring

Callbacks are typically registered as Spring beans:

```java
@Component
public class CustomerBeforeConvertCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        // Prepare customer here
        return Mono.just(customer);
    }
}
```

When an application uses Spring Boot with Spring Data R2DBC auto-configuration, callback beans can be discovered and registered into the entity callback infrastructure. With manual configuration or a custom `R2dbcEntityTemplate`, ensure the template uses the corresponding `ReactiveEntityCallbacks`.

Do not instantiate callbacks with `new` inside a service on every save; doing so leaves the callback unmanaged by Spring and may bypass dependency injection or ordering.

### 15.1. Dependency injection

A callback can receive pure dependencies such as `Clock` or a conversion component that does not access persistence:

```java
@Component
public class CustomerTimestampCallback
        implements BeforeConvertCallback<Customer> {

    private final Clock clock;

    public CustomerTimestampCallback(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        if (customer.getCreatedAt() == null) {
            customer.setCreatedAt(clock.instant());
        }
        return Mono.just(customer);
    }
}
```

Dependencies are injected once when Spring creates the bean. Callbacks should be stateless or hold only thread-safe dependencies; do not store the current entity in a callback field because multiple requests may run concurrently.

## 16. Callbacks with immutable entities

Not every entity uses setters. With a Java record or immutable class, the callback should create a new instance containing the prepared values:

```java
public record Customer(
        @Id UUID id,
        String name,
        String email) {

    public Customer withEmail(String normalizedEmail) {
        return new Customer(id, name, normalizedEmail);
    }
}
```

Callback:

```java
@Component
public class ImmutableCustomerCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String normalized = customer.email() == null
                ? null
                : customer.email().trim().toLowerCase(Locale.ROOT);

        return Mono.just(customer.withEmail(normalized));
    }
}
```

Spring Data must use the entity returned by the callback for the subsequent mapping step. With immutable entities, do not create a new instance and then discard it by returning the old object.

## 17. Callbacks and auditing

Spring Data Relational has an auditing mechanism for fields such as creator, creation timestamp, modifier, and modification timestamp. If the requirement is only standard auditing, consider using the auditing infrastructure instead of writing multiple custom timestamp callbacks.

Entity example:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;
}
```

Auditing must be enabled and configured with an appropriate `DateTimeProvider`/auditor according to the Spring Data version. If you need to record the actor, configure `ReactiveAuditorAware` to resolve the auditor from the reactive context rather than relying on a request `ThreadLocal`.

`BeforeConvertCallback` can still be used for other data-preparation rules. Avoid having a callback set timestamps on the same property managed by auditing, as the two mechanisms can overwrite each other.

## 18. Error handling in callbacks

If data cannot be prepared, the callback can emit an error:

```java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    if (customer.getEmail() == null || customer.getEmail().isBlank()) {
        return Mono.error(new IllegalArgumentException(
                "Email must not be blank"));
    }

    customer.setEmail(customer.getEmail().trim().toLowerCase(Locale.ROOT));
    return Mono.just(customer);
}
```

When a callback emits an error, subsequent mapping/write steps do not execute normally; the error propagates through the save operation's publisher.

However, input validation should usually live in Bean Validation, domain constructors/factories, or application services so callers receive errors at the right business boundary. Callbacks are appropriate for persistence-preparation preconditions that every mapped write path must satisfy.

Do not catch all exceptions and return the entity as if no error occurred. That can allow unprepared data to be saved anyway.

## 19. Testing BeforeConvertCallback

You can test the callback directly to verify the transformation:

```java
@Test
void shouldNormalizeEmailBeforeConvert() {
    Customer customer = new Customer();
    customer.setEmail("  LAN@EXAMPLE.COM  ");

    CustomerBeforeConvertCallback callback =
            new CustomerBeforeConvertCallback();

    StepVerifier.create(callback.onBeforeConvert(
                    customer,
                    SqlIdentifier.unquoted("customer")))
            .assertNext(result ->
                    assertEquals("lan@example.com", result.getEmail()))
            .verifyComplete();
}
```

The example assumes the callback returns `Publisher<Customer>` and appropriate constructors/fields exist. If the callback uses a dependency such as `Clock`, inject a fixed clock in tests so results are deterministic.

### 19.1. Testing that the callback is invoked on repository save

Directly unit-testing a callback only verifies the callback's logic. Integration tests need to save the entity through the repository and read it back to confirm the callback is genuinely registered in the Spring Data R2DBC mapping infrastructure:

```java
StepVerifier.create(customerRepository.save(customer)
        .flatMap(saved -> customerRepository.findById(saved.getId())))
        .assertNext(loaded ->
                assertEquals("lan@example.com", loaded.getEmail()))
        .verifyComplete();
```

Tests should verify:

- The callback is called for the correct entity type.
- The entity is normalized before mapping.
- Existing values are not overwritten unintentionally.
- The callback applies on insert and update as required.
- Immutable entities return a new instance that is used.
- When the callback emits an error, no data is written.
- Multiple callbacks execute in the desired order.
- Write paths using `DatabaseClient` or `@Modifying` have their own behavior and do not go through callbacks by default.

## 20. Common mistakes

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Callback does not run | Bean not registered or template lacks callback infrastructure | Register Spring bean and inspect template's `ReactiveEntityCallbacks` |
| Callback does not compile | Using wrong imperative/reactive interface or wrong package for version | Use the Spring Data R2DBC interface and check version signature |
| Changes in callback are not saved | Callback creates a new instance but returns old entity | Return the publisher containing the modified entity |
| Save completes without INSERT/UPDATE | Callback returns an empty publisher | Emit the entity with `Mono.just(...)` or an explicit error |
| Callback generates a different ID on every save | Unconditionally assigning a new ID | Only generate when ID is absent and handle newness detection |
| Database default is not used | Callback assigns a value to a database-managed column | Omit the column from writes or use appropriate generated/read-only mapping |
| Duplicate emails still occur | Only checking in callback or service | Add a unique constraint and handle concurrency errors |
| Save is unusually slow | Callback performs queries or HTTP calls | Move data fetching to the application service |
| Timestamp gets overwritten | Both callback and auditing manage the same field | Choose a single authoritative source |
| Callback causes unclear errors | Swallowing errors or failing to classify preparation errors | Emit meaningful errors and handle them at the right layer |
| Bulk SQL does not apply normalization | `DatabaseClient`/`@Modifying` bypass entity lifecycle callbacks | Reuse normalization logic at an appropriate layer |

## 21. Designing a BeforeConvertCallback workflow

When needing to prepare an entity before conversion in Spring Data R2DBC, determine:

1. Which properties need normalization or population before mapping?
2. Is the value managed by the application or the database?
3. Is the rule a domain invariant that belongs in a constructor/factory/service?
4. Can the callback run repeatedly without causing unintended changes?
5. Is the entity mutable or immutable, and does the callback return the modified instance?
6. Does the reactive callback return a non-blocking publisher without calling `block()` or `subscribe()`?
7. Is the callback registered as a bean and scoped to the right entity type?
8. Are there other callbacks in the same lifecycle phase that require ordering?
9. Do custom SQL write paths need to share the same normalization rule?
10. Do integration tests verify the callback is invoked in the actual repository/template flow?

`BeforeConvertCallback` is an extension point for preparing an entity before Spring Data R2DBC converts it into write data. Callbacks are suitable for idempotent normalization and technical value population, whereas complex domain rules should be expressed in the domain model or application service. When a callback is properly registered, returns a valid publisher, and avoids overwriting database-managed values, the application can standardize data before mapping while keeping the reactive pipeline clean.
