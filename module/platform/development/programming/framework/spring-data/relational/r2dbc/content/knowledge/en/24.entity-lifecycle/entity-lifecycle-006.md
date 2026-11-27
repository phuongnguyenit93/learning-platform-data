# Returning a New Entity in Callbacks with Immutable Models

In Spring Data Relational R2DBC, entity callbacks allow intervening in the save and read lifecycle of entities. When the domain model is immutable, a callback cannot directly mutate fields on the existing object. Instead, the callback creates a new instance containing updated values and returns that instance via the publisher. Spring Data continues the persistence pipeline using the entity returned by the callback.

This pattern works well with Java records, classes with `final` fields, full constructors, Lombok `@With`, or models providing `with...` copy methods. The key point is that the callback must return a publisher emitting the new entity; merely creating a copy and ignoring the return value will not change the data Spring Data processes.

## 1. Immutable models in Spring Data Relational applications

An immutable object does not allow state changes after creation. Instead of setters like `setCreatedAt(...)`, the object provides constructors or methods that create a copy with a new value.

Mutable entity example:

```java
public class PurchaseOrder {
    private Long id;
    private Instant createdAt;

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
```

With a mutable entity, a callback can modify the current object. However, this mutates object state at a point in the pipeline that callers may not notice.

An immutable entity represents the same data with unchanging fields and a constructor:

```java
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        Instant createdAt,
        String createdBy
) {
}
```

A record has no setters. When `createdAt` needs to be set, the application creates another `PurchaseOrder`:

```java
PurchaseOrder updated = new PurchaseOrder(
        order.id(),
        order.orderNumber(),
        createdAt,
        order.createdBy()
);
```

The old instance retains its original values. The new instance holds the state to be persisted. This makes callbacks explicit and avoids unexpectedly mutating a reference currently used elsewhere.

## 2. Why must callbacks return the new entity?

Callbacks are part of the persistence operation chain. Spring Data invokes the callback at a point in the lifecycle, receives the entity emitted by the callback, and uses that result for the next step.

With an immutable model, the callback cannot call setters. It must:

1. Receive the current entity.
2. Determine the value to add or change.
3. Create a new instance via constructor, `with...`, or `copy`.
4. Return the new instance inside a `Mono`/`Publisher`.

Principle example:

```java
return Mono.just(entity.withCreatedAt(clock.instant()));
```

Creating a copy without returning it is insufficient:

```java
entity.withCreatedAt(clock.instant());
return Mono.just(entity); // The created copy is discarded.
```

Because the original object was not mutated, the second line returns the old entity. The new value never enters the mapping and persistence pipeline.

## 3. Position of callbacks in the entity save lifecycle

Spring Data R2DBC has callbacks at different stages. Exact API names and details should be checked against your Spring Data version, but the conceptual write flow typically looks like this:

```mermaid
flowchart TD
    A[Repository save(entity)] --> B[BeforeConvert callback]
    B --> C[Convert entity to OutboundRow]
    C --> D[BeforeSave callback]
    D --> E[Execute INSERT or UPDATE]
    E --> F[Map generated values if any]
    F --> G[AfterSave callback]
    G --> H[Emit saved entity]
```

`BeforeConvertCallback` is invoked before the entity is converted into write data (`OutboundRow`). This is typically the right place to construct a new immutable entity when you want the new values included in mapping and SQL.

`BeforeSaveCallback` is invoked after Spring Data has converted the entity into an `OutboundRow`. This callback is useful when viewing or adjusting write data at the row level. If you change a property in a new immutable instance at this stage, note that `OutboundRow` was already built from the previous entity; do not assume returning a new instance automatically remaps the row. When the goal is changing entity properties before writing, prefer `BeforeConvertCallback`.

`AfterSaveCallback` runs after the write operation. It can construct a new result entity to emit downstream to the caller, but cannot substitute for a pre-conversion callback to alter values already written to the database.

## 4. Using `BeforeConvertCallback` with Java records

Suppose every new order must have a creation timestamp if the caller has not provided one. Using `Clock` instead of calling `Instant.now()` directly keeps time controllable in tests.

Entity:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        Instant createdAt,
        String createdBy
) {

    public PurchaseOrder withCreatedAt(Instant value) {
        return new PurchaseOrder(id, orderNumber, value, createdBy);
    }
}
```

Reactive callback:

```java
import java.time.Clock;
import org.reactivestreams.Publisher;
import org.springframework.data.relational.core.sql.SqlIdentifier;
import org.springframework.data.r2dbc.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class PurchaseOrderTimestampCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    private final Clock clock;

    public PurchaseOrderTimestampCallback(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Publisher<PurchaseOrder> onBeforeConvert(
            PurchaseOrder entity,
            SqlIdentifier table) {

        if (entity.createdAt() != null) {
            return Mono.just(entity);
        }

        PurchaseOrder updated = entity.withCreatedAt(clock.instant());
        return Mono.just(updated);
    }
}
```

The callback receives the entity, creates a new record if `createdAt` is missing, and emits that instance. If the entity already has a creation timestamp, the callback emits the current instance unchanged. Both branches emit exactly one non-null entity.

The example illustrates a Spring Data R2DBC reactive callback. Packages and callback signatures must match the Spring Data R2DBC version in your project; in versions with API changes, use the corresponding callback interface while keeping the same principle of returning a publisher containing the entity.

## 5. Configuring `Clock`

Register `Clock` as a bean so callbacks can inject it:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

In production, `Clock.systemUTC()` provides the current UTC instant. In tests, it can be replaced with `Clock.fixed(...)` for deterministic results:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T08:00:00Z"),
        ZoneOffset.UTC
);
```

Do not instantiate `Clock.systemDefaultZone()` independently in multiple places if the application needs consistent UTC semantics. A single `Clock` bean lets all callbacks and services share one time policy.

## 6. Using `with...` methods to create copies

For standard Java classes, you can write `with...` methods manually:

```java
public final class PurchaseOrder {

    private final Long id;
    private final String orderNumber;
    private final Instant createdAt;

    public PurchaseOrder(Long id, String orderNumber, Instant createdAt) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.createdAt = createdAt;
    }

    public PurchaseOrder withCreatedAt(Instant value) {
        return new PurchaseOrder(id, orderNumber, value);
    }

    public PurchaseOrder withId(Long value) {
        return new PurchaseOrder(value, orderNumber, createdAt);
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Each `with...` method returns a new object, preserving all other properties and replacing only the requested property. This technique is useful when a callback only needs to change one or a few fields.

If a class has many properties, writing constructors inside every `with...` can become verbose. You can use records, Lombok `@With`, or an immutable data construct suitable for your codebase. Whichever tool you choose, verify that the copy method preserves all unchanged properties.

## 7. Using Lombok `@With`

Lombok can generate `with...` methods for final fields:

```java
import lombok.With;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@With
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private final Long id;

    private final String orderNumber;

    private final Instant createdAt;

    public PurchaseOrder(Long id, String orderNumber, Instant createdAt) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public Instant getCreatedAt() { return createdAt; }
}
```

After annotation processing runs, Lombok generates methods such as `withCreatedAt(Instant value)` returning a new instance. The callback can use:

```java
PurchaseOrder updated = entity.withCreatedAt(clock.instant());
return Mono.just(updated);
```

`@With` does not automatically make every part of the object graph immutable. If a field holds a mutable `List`, the copy may still share the same list. Use immutable collections or defensive copies if the domain requires deep immutability.

## 8. Using Kotlin data classes

In Kotlin, `data class` provides `copy(...)` to construct a new instance:

```kotlin
@Table("purchase_order")
data class PurchaseOrder(
    @Id val id: Long? = null,
    val orderNumber: String,
    val createdAt: Instant? = null,
    val createdBy: String? = null
)
```

When creation time needs to be populated:

```kotlin
val updated = entity.copy(createdAt = clock.instant())
```

In a Kotlin callback, return `Mono.just(updated)` or an equivalent publisher. `copy` preserves unspecified properties and creates a distinct instance. Like Java records, ensure internal properties do not reference mutable collections if deep immutability is desired.

## 9. Callbacks must not discard the new entity

A common mistake is creating a copy without using it:

```java
@Override
public Publisher<PurchaseOrder> onBeforeConvert(
        PurchaseOrder entity,
        SqlIdentifier table) {

    entity.withCreatedAt(clock.instant());
    return Mono.just(entity);
}
```

`withCreatedAt` returns a new instance, yet the result is discarded. Because the original entity is immutable, its `createdAt` remains unchanged. The callback must return the value created by `withCreatedAt`:

```java
@Override
public Publisher<PurchaseOrder> onBeforeConvert(
        PurchaseOrder entity,
        SqlIdentifier table) {

    return Mono.just(entity.withCreatedAt(clock.instant()));
}
```

Another mistake is returning an empty publisher when no changes are needed:

```java
if (entity.createdAt() != null) {
    return Mono.empty(); // Does NOT mean "keep the current entity".
}
```

`Mono.empty()` emits no entity for the persistence pipeline to continue. If no changes are needed, return `Mono.just(entity)`. Only use empty when the callback contract and use case intentionally mean emitting no result; for a pre-processing callback on an entity to be saved, empty usually stops the save from proceeding as expected.

## 10. `BeforeConvertCallback` fits changing entity properties

Suppose order numbers need normalization before writing. The new value must enter `OutboundRow`, so create the new entity at the pre-conversion stage:

```java
@Component
public class OrderNumberCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public Publisher<PurchaseOrder> onBeforeConvert(
            PurchaseOrder entity,
            SqlIdentifier table) {

        String normalized = entity.orderNumber().trim().toUpperCase(Locale.ROOT);

        if (normalized.equals(entity.orderNumber())) {
            return Mono.just(entity);
        }

        return Mono.just(entity.withOrderNumber(normalized));
    }
}
```

Here `withOrderNumber` is a copy method added to the entity. When the callback emits the new entity, Spring Data converts that instance into a row and writes the normalized value.

Callbacks should only perform normalization that belongs to persistence rules or a shared policy. Important business rules such as validating whether an order number is valid should still reside in the domain/service so they apply even when objects do not go through a repository.

## 11. `BeforeSaveCallback` and `OutboundRow`

`BeforeSaveCallback` is invoked after converting the entity into an `OutboundRow`. The callback typically receives both the entity and the row:

```java
// Illustrative signature of a reactive callback in Spring Data R2DBC.
Publisher<PurchaseOrder> onBeforeSave(
        PurchaseOrder entity,
        OutboundRow row,
        SqlIdentifier table);
```

At this stage you may need to modify row values directly, for example adding a database-written audit column. Because the row has already been built from the entity, distinguish two goals:

- Wanting to change an entity property and let Spring Data map it before writing: use `BeforeConvertCallback`.
- Wanting to adjust a SQL value in `OutboundRow` after mapping: update the row via the `OutboundRow`/`Parameter` API of your version.

If a `BeforeSave` callback returns a new immutable entity, the returned value may be passed downstream/to the caller per the callback contract, but do not assume changes in that instance are automatically reflected back into the already-created `OutboundRow`. When SQL data needs to change, modify the row or apply the change at the pre-conversion stage.

Do not use `BeforeSaveCallback` to do the same job as `BeforeConvertCallback` and expect the entity to be remapped automatically. Choose the callback based on when the data must change.

## 12. `AfterSaveCallback` does not change already-written data

After the database executes insert/update, `AfterSaveCallback` can create a new entity to enrich the emitted result:

```java
// Conceptual illustration: create a new result instance after saving.
PurchaseOrder result = entity.withPersistenceStatus("SAVED");
return Mono.just(result);
```

The value is added only to the result object after the SQL operation. If `persistenceStatus` is not a persisted database column, this can be appropriate for enriching the result. If it is a column that needs to be written, it must be set before conversion or updated in the row in the appropriate callback.

Do not use a post-save callback to generate a value that the database needs to persist in the same insert statement; at that point the statement has already executed.

## 13. Receiving database-generated IDs in immutable models

With database-generated primary keys, a new entity typically has `id == null`. After insert, Spring Data receives the generated value and creates a resulting entity with the ID. With immutable models, the returned instance can differ from the input instance.

```java
PurchaseOrder order = new PurchaseOrder(
        null,
        "PO-2026-001",
        clock.instant(),
        "system"
);

return purchaseOrderRepository.save(order)
        .map(saved -> saved.id());
```

Read the ID from `saved`, the entity emitted by `save()`. Do not read `order.id()` immediately after calling `save`, because the input object is not necessarily mutated. Persistence completion and generated-ID mapping occur inside the publisher.

When creating child data, use the saved entity's ID inside `flatMap`:

```java
return purchaseOrderRepository.save(order)
        .flatMap(saved -> lineRepository.saveAll(
                        lines.stream()
                                .map(line -> line.withOrderId(saved.id()))
                                .toList())
                .thenReturn(saved));
```

If parent/child operations must be atomic, place the entire pipeline inside the same reactive transaction. Do not call `subscribe()` separately for the child save step because that detaches it from error propagation and the parent creation transaction.

## 14. How can Spring Data create copies of immutable entities?

Spring Data Relational uses mapping metadata and instantiation mechanisms based on constructors/property access. With immutable entities, the framework can create a new instance when it needs to apply values such as a generated ID or version. Supported models can include:

- A constructor identified as the persistence constructor.
- A Java record with a canonical constructor.
- A Kotlin data class with a matching constructor.
- Properties with withers/creators to construct a new instance when a value is updated.
- Immutable structures supported by Spring Data per the mapping metadata of the corresponding version.

Therefore, do not rely on Spring Data mutating final fields or mutating the original object. Always use the entity emitted by the `save()` publisher as the operation's result.

If constructor mapping is ambiguous, provide a single persistence constructor or annotate the appropriate constructor with `@PersistenceCreator` when needed. Constructor parameter names should match properties and mapping metadata. For Java classes, retaining parameter names (`-parameters`) may be required depending on mapping configuration.

## 15. Are callbacks the right place for all logic?

Callbacks are suited for logic tied to the persistence lifecycle that must apply consistently whenever an entity goes through a Spring Data repository/template. For example:

- Populating shared audit metadata.
- Normalizing persisted fields before conversion.
- Generating a technical value required before writing.
- Applying a shared persistence rule for an entity type.

Callbacks are not the right place for every business rule:

- Do not hide long workflows or call multiple external services inside callbacks.
- Do not make blocking HTTP calls or call `block()` in reactive callbacks.
- Do not use callbacks to replace API/domain validation.
- Do not use callbacks to coordinate transactions across multiple aggregates that services should control explicitly.
- Do not place logic needed for only one specific use case into a global callback for every entity save.

Reactive callbacks should perform non-blocking work. If an extra database query is needed, evaluate lifecycle impact, query count, and repeatability; callbacks may run across many save paths and should not cause hard-to-control side effects.

## 16. When are callbacks invoked?

Callbacks execute inside the persistence pipeline, not immediately when creating an entity or calling a repository method if the publisher has not been subscribed to. Example:

```java
Mono<PurchaseOrder> saved = purchaseOrderRepository.save(order);
```

The code above describes a publisher. Only when the publisher is subscribed to does Spring Data execute the operation and invoke callbacks per the lifecycle.

This means:

- Do not place mandatory side effects outside the publisher expecting them to run when `save()` is called.
- Callbacks may be invoked again if the publisher is subscribed to multiple times, depending on how the pipeline is constructed and used.
- Do not share mutable state inside a callback across concurrent requests.
- Use `Clock`, stateless services, or thread-safe dependencies instead of mutable instance variables.
- If a callback needs to generate a random value or business code, consider generating it in the service/domain so one logical intent produces one value, especially when retries occur.

For example, if a callback generates a UUID every time it is called and a publisher is re-subscribed, the value can differ across attempts. If the UUID is a business identifier that must remain stable across retries, generate it in the command/service or use an idempotency key rather than depending on how many times the callback is invoked.

## 17. Do not call `block()` or `subscribe()` in callbacks

Reactive callbacks must return a publisher so Spring Data can chain it into the pipeline. Do not manually subscribe inside a callback:

```java
@Override
public Publisher<PurchaseOrder> onBeforeConvert(
        PurchaseOrder entity,
        SqlIdentifier table) {

    auditRepository.save(...).subscribe(); // Not recommended
    return Mono.just(entity);
}
```

This code spawns an unawaited side stream whose errors are not composed and which may run outside the entity save's transaction. The callback can complete before the audit save finishes.

If a callback genuinely needs a dependent publisher, chain it with `flatMap` or `thenReturn`:

```java
return auditRepository.findPolicyFor(entity.orderNumber())
        .map(policy -> entity.withPolicyCode(policy.code()));
```

However, evaluate whether querying the database inside a callback introduces N+1 queries or persistence circular dependencies. For multi-operation logic, a service is usually easier to control.

## 18. Combining callbacks with auditing

Spring Data Relational supports auditing to automatically record creation/update timestamps and actors. With R2DBC, auditing configuration can use `@EnableR2dbcAuditing` alongside annotations such as `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy`.

Entity example:

```java
@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        @CreatedDate Instant createdAt,
        @LastModifiedDate Instant modifiedAt,
        @CreatedBy String createdBy,
        @LastModifiedBy String modifiedBy
) {
}
```

The auditing infrastructure can update values on entities through mapping support for immutable instances. Therefore, before writing a custom callback to set `createdAt` or `modifiedAt`, check whether auditing already meets the requirement. Avoid having two mechanisms write to the same field with unclear ordering.

For auditing to resolve the current user, provide an appropriate `ReactiveAuditorAware<T>` if the application uses a reactive security context. The auditor provider must read the reactive context properly rather than relying on ThreadLocal/blocking assumptions from imperative applications.

## 19. Ordering multiple callbacks

An entity may pass through multiple callbacks of the same type. When order matters, configure execution order using the callback ordering mechanism supported by your Spring Data and Spring Framework versions, such as `Ordered` or `@Order` where supported.

Do not let two callbacks write the same property without an established convention. For instance, if one callback normalizes an order number and another computes a hash from the order number, running hash before normalization means the hash reflects the unnormalized value.

You can combine dependent steps into one explicit callback or define explicit ordering. Either way, each immutable callback must return the current step's new entity so the next callback receives the updated state.

## 20. Testing callbacks in isolation

Callbacks can be tested as regular Java components by invoking the method and verifying the publisher emits the new entity:

```java
class PurchaseOrderTimestampCallbackTest {

    private final Instant fixedInstant =
            Instant.parse("2026-01-15T08:00:00Z");

    private final Clock clock = Clock.fixed(fixedInstant, ZoneOffset.UTC);

    private final PurchaseOrderTimestampCallback callback =
            new PurchaseOrderTimestampCallback(clock);

    @Test
    void returnsNewEntityWithCreatedAtWhenMissing() {
        PurchaseOrder original = new PurchaseOrder(
                null, "PO-1", null, "system");

        StepVerifier.create(callback.onBeforeConvert(
                        original, SqlIdentifier.unquoted("purchase_order")))
                .assertNext(updated -> {
                    assertThat(updated.createdAt()).isEqualTo(fixedInstant);
                    assertThat(updated).isNotSameAs(original);
                    assertThat(original.createdAt()).isNull();
                })
                .verifyComplete();
    }

    @Test
    void returnsOriginalEntityWhenValueAlreadyExists() {
        PurchaseOrder original = new PurchaseOrder(
                null, "PO-1", fixedInstant, "system");

        StepVerifier.create(callback.onBeforeConvert(
                        original, SqlIdentifier.unquoted("purchase_order")))
                .expectNextSame(original)
                .verifyComplete();
    }
}
```

The test assumes the callback and `SqlIdentifier` API of your version match the example signatures. If package or factory methods differ, adjust imports to your project dependencies; the test goal remains verifying that a new entity is emitted, the original entity is untouched, and the unchanged branch returns a valid entity.

## 21. Integration tests through the repository

Unit testing the callback does not prove Spring Data registered the callback or used the returned entity to build SQL. Integration tests with a repository and compatible R2DBC database are needed:

```java
@Test
void saveUsesEntityReturnedByBeforeConvertCallback() {
    PurchaseOrder input = new PurchaseOrder(
            null, "PO-1", null, "system");

    StepVerifier.create(purchaseOrderRepository.save(input))
            .assertNext(saved -> {
                assertThat(saved.id()).isNotNull();
                assertThat(saved.createdAt()).isNotNull();
            })
            .verifyComplete();

    assertThat(input.createdAt()).isNull();
}
```

This test illustrates what to verify: the callback is registered, values are populated before mapping, the database saves successfully, the ID is generated, and the resulting entity has the new value. In real tests, also read the row back by ID to confirm `created_at` was actually written.

```java
StepVerifier.create(purchaseOrderRepository.save(input)
                .flatMap(saved -> purchaseOrderRepository.findById(saved.id())))
        .assertNext(loaded -> {
            assertThat(loaded.createdAt()).isNotNull();
            assertThat(loaded.orderNumber()).isEqualTo("PO-1");
        })
        .verifyComplete();
```

Run integration tests against the actual database/driver or a compatible environment. H2 and another database can differ in generated IDs, timestamps, and mapping.

## 22. Checking whether an entity callback is registered

If a callback does not run, check the following:

- The callback is registered as a Spring bean, for example with `@Component` or `@Bean`.
- The callback's package is within the application's component-scan scope.
- The callback's generic type matches the entity being saved.
- The repository/template used belongs to Spring Data R2DBC, not a direct SQL write path bypassing the entity lifecycle.
- The callback interface and package match the Spring Data version in dependencies.
- The callback publisher is returned and not bypassed via an internal `subscribe()`.
- The `save()` operation's publisher is actually subscribed to.

Direct SQL statements via `DatabaseClient` or R2DBC SPI do not automatically run Spring Data entity callbacks because they do not go through the corresponding entity mapping lifecycle. If the same logic is needed for both repositories and direct SQL, extract the shared logic into a service/factory or enforce it at the appropriate database layer instead of relying solely on callbacks.

## 23. Error handling in callbacks

A callback can emit an error if data is invalid or a required dependency fails. In a reactive callback, you can return `Mono.error(...)`:

```java
if (entity.orderNumber() == null || entity.orderNumber().isBlank()) {
    return Mono.error(new InvalidOrderNumberException());
}

return Mono.just(entity);
```

The error propagates through the `save()` publisher and can trigger a transaction rollback if the operation is inside a transaction. Do not turn errors into `Mono.empty()` to pretend the callback finished; empty does not mean "skip changes."

Do not catch all exceptions and return the old entity. Doing so can let writes proceed with missing audit data or unnormalized values. Only use a fallback if business rules permit it and the fallback is clearly defined.

## 24. Avoiding non-idempotent side effects in callbacks

Callbacks may execute across different subscriptions or retries. If a callback sends emails, calls external services, increments counters, or initiates financial transactions, retries can duplicate side effects.

Callbacks should focus on controllable entity/row transformations. For side effects that must fire after commit, use transactions and a Transactional Outbox. For identifiers or idempotency keys that must stay stable, generate them in the service/command before saving and preserve them across retries.

Example to avoid:

```java
return emailClient.sendOrderCreated(entity).thenReturn(entity);
```

If the callback is invoked again, the email can be sent again. Instead, save an outbox event in the same transaction as the entity, then let a worker send the email and handle duplicate deliveries idempotently.

## 25. Common mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Creating a new entity without returning it | Spring Data proceeds with the old entity | Return `Mono.just(updated)` |
| Trying to call setters on records/final fields | Does not compile or breaks immutability | Use constructors, `with...`, or `copy` |
| Returning `Mono.empty()` when no change is needed | Pipeline may emit no entity to continue saving | Return `Mono.just(entity)` |
| Returning null instead of a publisher | Violates reactive contract and causes errors | Return a valid publisher |
| Using `BeforeSave` to change a property without editing the row | New entity and SQL data may be out of sync | Use `BeforeConvert` or update `OutboundRow` properly |
| Using `AfterSave` to change a value that needs to be written | Database already executed the statement before callback | Move change to a pre-conversion callback |
| Reading ID from the input entity after `save()` | ID may still be null for immutable entities | Use the entity emitted by the `save()` publisher |
| Calling `subscribe()` in callback | Detaches side work from transaction and errors | Compose publishers with `flatMap`/`then` |
| Calling blocking I/O in a reactive callback | Blocks processing threads and reduces scalability | Use non-blocking APIs or move logic to an appropriate service |
| Two callbacks write the same property without order | Result depends on execution order | Merge logic or configure explicit ordering |
| Relying on callbacks for all write paths | Direct SQL can bypass callbacks | Use services/factories or apply logic at an appropriate layer |
| Callback causes external side effects | Retries can cause duplicate sends or duplicate transactions | Use outbox and idempotent consumers |

## 26. Workflow for designing callbacks for immutable entities

When needing to populate or normalize data during the entity save lifecycle, proceed in order:

1. Identify which values need changing and whether they must be written to the database or only enrich the result.
2. If changes are needed before mapping, choose `BeforeConvertCallback`.
3. If SQL values need adjustment after mapping, choose `BeforeSaveCallback` and update `OutboundRow` per your version's API.
4. If only the entity emitted after the write operation needs adjustment, consider `AfterSaveCallback`.
5. Use constructors, records, `with...`, Lombok `@With`, or Kotlin `copy` to create the new instance.
6. Return the new instance with `Mono.just(updated)`; if unchanged, return `Mono.just(entity)`.
7. Inject stateless dependencies such as `Clock`; avoid mutable state and blocking I/O.
8. Register the callback as a bean and confirm its generic type matches the entity.
9. Use the entity emitted from `repository.save()` to obtain the ID and final state.
10. Unit test the callback in isolation and integration test via the repository with a compatible database.

## 27. Best practices

- For immutable entities, do not mutate the object; create a new instance and return it via the callback publisher.
- Use `BeforeConvertCallback` when new values must participate in entity-to-row mapping.
- Use `BeforeSaveCallback` for changes at the `OutboundRow` level; do not assume an entity copy is automatically remapped.
- Use `AfterSaveCallback` to enrich the result after SQL has executed, not to replace data that needs to be written.
- Use Java records, constructors, `with...`, Lombok `@With`, or Kotlin `copy` to create explicit copies.
- Return `Mono.just(entity)` when no changes occur; do not use `Mono.empty()` as a way to keep the entity unchanged.
- Do not ignore the return value of `with...` or `copy`.
- Do not call `block()`/`subscribe()` in reactive callbacks; compose publishers into the pipeline.
- Do not perform non-idempotent side effects or call blocking services in callbacks.
- Use an injectable `Clock` to produce consistent, testable timestamps.
- Read the ID and final state from the entity emitted by `save()`, without assuming the input object was mutated.
- Verify the callback is registered and the write path actually passes through Spring Data entity mapping.
- Test the returned instance, the unchanged input object, and the actual values persisted in the database.

## 28. Conclusion

With immutable models, Spring Data Relational R2DBC callbacks need to create a new entity instead of mutating the current object. The callback must emit the new instance via a publisher so Spring Data uses that result in the next step. `BeforeConvertCallback` is usually the right place when new values must become database columns; `BeforeSaveCallback` operates once `OutboundRow` has been created, while `AfterSaveCallback` can only enrich the result after SQL has run.

Java records, constructors, `with...` methods, Lombok `@With`, and Kotlin `copy` all support clean copy creation. When saving, use the entity emitted by `save()` to receive generated IDs or final state. Keeping callbacks reactive, avoiding blocking or detached subscriptions, avoiding repeated side effects, and testing both the callback and actual persisted results keeps the immutable entity lifecycle consistent and predictable.
