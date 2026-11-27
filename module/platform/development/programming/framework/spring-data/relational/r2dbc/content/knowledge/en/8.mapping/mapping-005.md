# Skipping Non-Persistent Properties with @Transient

In Spring Data Relational R2DBC, an entity can contain both data stored in the database and data that only has meaning in application memory. For example, `Order` may have `id`, `total`, and `status` as persistent properties, along with `displayStatus` or `canCancel` derived from those properties for UI purposes. If a property does not represent a column of data to be read or written, you can mark it with Spring Data's `@Transient` to exclude it from persistence mapping.

`@Transient` tells Spring Data that the property does not belong to the entity's relational data model. When saving or reading an entity through a repository and `R2dbcEntityTemplate`, the mapping layer skips this property. The application can still use the property in Java as usual, compute values, assign additional data, or return it in responses if a serializer allows it.

## 1. Why Is @Transient Needed?

An entity class often serves multiple needs in an application: storing data, computing state, displaying information, and passing data between layers. Not every property in a class needs a corresponding column in the database.

For example, an order might have:

- `id`: identifier stored in the table.
- `total`: total amount stored in the table.
- `status`: business status stored in the table.
- `displayStatus`: friendly status label computed from `status`.
- `canCancel`: flag indicating whether the current user can cancel the order, computed from status and user permissions.
- `formattedTotal`: currency string for display, produced from `total` and locale.

The last three properties may vary by context or be computed from other data. If Spring Data treats them as persistent properties, mapping may attempt to map them to columns or include them when writing data. That can lead to missing-column errors, SQL errors, or an entity model that does not accurately reflect the schema.

`@Transient` marks a clear boundary: the property remains in the Java object, yet does not participate in Spring Data persistence mapping.

## 2. Importing the Right Annotation

For Spring Data Relational R2DBC, use the annotation:

```java
import org.springframework.data.annotation.Transient;
```

Do not confuse this annotation with:

```java
import jakarta.persistence.Transient;
```

`jakarta.persistence.Transient` belongs to Jakarta Persistence/JPA. Spring Data R2DBC uses Spring Data Relational mapping metadata, so you should use `org.springframework.data.annotation.Transient` for R2DBC entities.

Both annotations share the same short name yet belong to two different persistence systems. Your IDE may auto-import the wrong one if the project also has a JPA dependency. Always check the `import` line when adding the annotation.

## 3. Example of an Entity with a Transient Property

Suppose the `purchase_order` table only stores columns `id`, `total`, and `status`. The application wants to add `displayStatus` to show a readable status.

```java
import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private BigDecimal total;

    private String status;

    @Transient
    private String displayStatus;

    public PurchaseOrder() {
    }

    public PurchaseOrder(Long id, BigDecimal total, String status) {
        this.id = id;
        this.total = total;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getDisplayStatus() {
        return displayStatus;
    }

    public void setDisplayStatus(String displayStatus) {
        this.displayStatus = displayStatus;
    }
}
```

`id`, `total`, and `status` are persistent properties. `displayStatus` still has a getter and setter so the service or presentation layer can use it, while Spring Data Relational ignores it in entity mapping.

This entity does not require the table to have a `display_status` column. The `@Transient` annotation also does not create or drop columns in the database; the schema is still managed by migrations or the project's dedicated DDL tools.

## 4. What Happens When Reading and Writing the Entity?

`@Transient` affects Spring Data Relational mapping. It does not remove the property from the object and does not prevent Java code from reading or writing that property's value.

### 4.1. During INSERT or UPDATE

When saving `PurchaseOrder` with a reactive repository:

```java
public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {
}
```

Example:

```java
PurchaseOrder order = new PurchaseOrder(
    null,
    new BigDecimal("125000.00"),
    "PAID"
);
order.setDisplayStatus("Paid");

Mono<PurchaseOrder> saved = purchaseOrderRepository.save(order);
```

Spring Data Relational uses persistent properties to build the save operation. `displayStatus` is not included in the INSERT or UPDATE column list. The database does not need a column corresponding to that property.

If a property must be saved yet is marked `@Transient`, its value will not be persisted through this mapping. In that case, remove the annotation or redesign the mapping/schema.

### 4.2. During SELECT and Entity Materialization

When reading an entity:

```java
Mono<PurchaseOrder> order = purchaseOrderRepository.findById(100L);
```

Spring Data reads persistent columns and constructs the `PurchaseOrder` object. `displayStatus` is not populated from a database column via entity mapping. Its value remains at the default state or whatever the constructor/application initialization sets.

If you need to display a label, compute it after reading:

```java
Mono<PurchaseOrder> findOrderForDisplay(Long id) {
    return purchaseOrderRepository.findById(id)
        .map(order -> {
            order.setDisplayStatus(switch (order.getStatus()) {
                case "NEW" -> "Newly created";
                case "PAID" -> "Paid";
                case "CANCELLED" -> "Cancelled";
                default -> "Unknown";
            });
            return order;
        });
}
```

The transient value is populated in memory after the entity is read. When the entity is saved again, `displayStatus` is still not written to the database.

### 4.3. Lifecycle Diagram

```text
Database row
     |
     | SELECT persistent columns
     v
Spring Data Relational mapping
     |
     | Create entity, skip @Transient
     v
PurchaseOrder in memory
     |
     | Service computes displayStatus
     v
Enriched entity
     |
     | INSERT/UPDATE persistent properties only
     v
Database row (without displayStatus)
```

The key point is that a transient property can hold a value in the object after service enrichment, while persistence mapping does not save that value.

## 5. Common Use Cases

### 5.1. Properties Computed from Persistent Data

A property can be derived from existing columns:

```java
@Transient
private BigDecimal taxAmount;

public BigDecimal getTaxAmount() {
    if (total == null) {
        return null;
    }
    return total.multiply(new BigDecimal("0.10"));
}
```

If the value can always be calculated from `total`, you may not even need a separate `taxAmount` field. A computed getter avoids storing redundant state in the object. If you need to cache the result or assign it from another service, a transient field can be more suitable.

### 5.2. UI-Oriented Properties

For example, `displayStatus`, `formattedTotal`, `thumbnailUrl`, or `shortDescription` serve presentation only. These values may depend on locale, time zone, or user settings, so they are not necessarily persistent data.

### 5.3. Enriched Results from Another Service

An entity can be enriched with data from another service, for example:

```java
@Transient
private String shippingEstimate;

@Transient
private boolean eligibleForPromotion;
```

`shippingEstimate` might come from a shipping service; `eligibleForPromotion` might depend on an active promotional campaign. These values do not belong to the orders table and should not be accidentally written to it.

### 5.4. Temporary Flags Within a Use Case

A property such as `selected`, `expanded`, or `validationMessage` can be useful within a workflow or screen. If placed on an entity, mark it transient so Spring Data does not treat it as table data.

However, if a property serves only a single API response, a separate DTO is usually a cleaner choice. Entities should focus on data and behavior tied to the persistence model; DTOs can hold presentation data or aggregated results for a specific use case.

## 6. @Transient Is Not the Same as a Read-Only Column

`@Transient` means the property is excluded from persistence mapping. If the database has a column that needs to be read yet the application must not write to it, that is a different requirement.

Spring Data Relational provides `@ReadOnlyProperty` for cases where a property is read from the database but not written by the mapping layer, depending on the capabilities of the version in use:

```java
import org.springframework.data.annotation.ReadOnlyProperty;

@ReadOnlyProperty
private Instant createdAt;
```

Comparison:

| Annotation | Read from Database | Written to Database | Use Case |
|---|---|---|---|
| `@Transient` | Not via that property mapping | No | In-memory-only values or computed/enriched values |
| `@ReadOnlyProperty` | Yes | No | Database-managed columns or mapping-read-only columns |
| Normal persistent property | Yes | Yes, per mapping operations | Normal application-stored data |

For example, `created_at` may be database-generated and read-only to the application, whereas `displayStatus` may be computed from `status` with no table column. These two cases should not share `@Transient`.

If using `@ReadOnlyProperty`, verify that the database actually generates/updates that column and that the driver/mapping can read it. The annotation does not generate values on the database side.

## 7. Distinguishing from Other Mechanisms Named Transient

In a Java project, you may encounter several mechanisms with similar names yet different scopes.

| Mechanism | Scope of Impact | Meaning |
|---|---|---|
| `org.springframework.data.annotation.Transient` | Spring Data mapping | Skips the property in Spring Data persistence mapping |
| `jakarta.persistence.Transient` | JPA | Marks a non-persistent property in JPA |
| Java `transient` keyword | Java serialization and field modifier | Affects Java serialization; should not replace the Spring Data annotation when aiming for explicit R2DBC mapping configuration |
| Jackson `@JsonIgnore` | JSON serialization/deserialization | Hides or ignores a property during JSON processing per Jackson configuration |

These mechanisms do not automatically replace one another. A property can be excluded from persistence mapping yet still appear in JSON, or vice versa.

For example, `@Transient` does not automatically prevent Jackson from serializing the `getDisplayStatus()` getter. If an API must not return that field, design a response DTO or apply appropriate serialization annotations/configuration. Conversely, `@JsonIgnore` does not cause Spring Data Relational to skip a column when saving an entity.

## 8. Querying by Transient Properties

Because a `@Transient` property is not a persistent property, Spring Data cannot treat it as a table column when generating property-based queries.

For example, if `displayStatus` is derived from `status`, you should not create a derived query like:

```java
// Not suitable: displayStatus is not a persistent property.
Flux<PurchaseOrder> findByDisplayStatus(String displayStatus);
```

Instead, query by the source property:

```java
Flux<PurchaseOrder> findByStatus(String status);
```

Or write SQL/`@Query` based on the real column:

```java
@Query("""
    SELECT id, total, status
    FROM purchase_order
    WHERE status = :status
    """)
Flux<PurchaseOrder> findByStoredStatus(String status);
```

If the filter criterion is a complex expression, express it in SQL or create a suitable column/view in the database if business and performance requirements call for it. You cannot filter directly in the database on a value that only exists in memory without a corresponding expression or data in the database.

## 9. @Transient and Custom SQL Queries

`@Transient` controls Spring Data Relational mapping. It does not control the database engine and does not alter hand-written SQL.

When using `DatabaseClient`, the application decides which columns to SELECT and how to map rows:

```java
databaseClient.sql("""
        SELECT id, total, status
        FROM purchase_order
        WHERE id = :id
        """)
    .bind("id", id)
    .map((row, metadata) -> {
        PurchaseOrder order = new PurchaseOrder(
            row.get("id", Long.class),
            row.get("total", BigDecimal.class),
            row.get("status", String.class)
        );
        order.setDisplayStatus("Processing");
        return order;
    })
    .one();
```

In the code above, `displayStatus` is assigned because the mapper written directly by the application sets it. The `@Transient` annotation does not prevent the Java mapper from calling the setter. When using `DatabaseClient`, mapping responsibility belongs to the `map(...)` callback; the annotation neither performs nor forbids assignments in manual code.

Similarly, if you write a manual `INSERT` or `UPDATE` SQL statement and include a column name yourself, the database processes that SQL against the schema. `@Transient` does not rewrite the SQL. If the column does not exist, the statement still fails as usual.

## 10. Constructors and Entity Creation

Spring Data can use a constructor or factory method to create entities when reading data. With transient properties, design constructors around data actually read from the database.

For example, keep the primary constructor focused on persistent properties:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private BigDecimal total;

    private String status;

    @Transient
    private String displayStatus;

    public PurchaseOrder(Long id, BigDecimal total, String status) {
        this.id = id;
        this.total = total;
        this.status = status;
    }
}
```

The constructor does not require `displayStatus` because the database does not supply that value. After the entity is materialized, a service can compute or assign the transient property.

If a constructor requires a parameter that has no corresponding data in the persistence result, materialization may fail to work as expected or receive default values depending on the mapping approach and version. Avoid forcing the persistence constructor to accept in-memory-only data. If multiple ways of creating the object are needed, provide an appropriate constructor and use `@PersistenceCreator` on the constructor Spring Data should use.

With immutable entities or Java records, consider this carefully because transient properties cannot be assigned after creation without an appropriate initialization mechanism. When presentation data is added after reading, a DTO is usually simpler than making an immutable entity carry many non-persistence values.

## 11. Enriching Transient Data at the Service Layer

A controllable pattern is to let the repository read the persistent entity, then have the service compute temporary properties:

```java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<PurchaseOrder> findForDisplay(Long id) {
        return repository.findById(id)
            .map(this::enrich);
    }

    private PurchaseOrder enrich(PurchaseOrder order) {
        String label = switch (order.getStatus()) {
            case "NEW" -> "Newly created";
            case "PAID" -> "Paid";
            case "CANCELLED" -> "Cancelled";
            default -> "Unknown";
        };

        order.setDisplayStatus(label);
        return order;
    }
}
```

For a simple property that depends only on the entity, it can be calculated directly in a getter. For data requiring calls to another service, compose publishers rather than blocking threads:

```java
public Mono<OrderView> findOrderView(Long id) {
    return repository.findById(id)
        .flatMap(order -> shippingClient.estimate(order.getId())
            .map(estimate -> new OrderView(
                order.getId(),
                order.getTotal(),
                order.getStatus(),
                estimate
            )));
}
```

In the second example, `OrderView` is a DTO tailored for the use case. This is usually a better choice than stuffing lots of external-service data into a persistence entity, especially when the enriched data has its own lifecycle or update source.

If you need automatic enrichment every time an entity is converted, Spring Data provides entity callbacks such as an after-convert callback. Callbacks must be implemented using the reactive API and the Spring Data version in use; keep callbacks short, avoid blocking I/O, and weigh the cost if they run for every entity read. For logic serving only one endpoint, the service layer is usually easier to understand and test.

## 12. Testing @Transient Properties

Tests should verify two things: the property remains usable in the Java object, and persistence mapping neither saves nor reads it as a column.

### 12.1. Testing Object Behavior

You can test the getter/setter of a transient property like ordinary Java properties:

```java
PurchaseOrder order = new PurchaseOrder(
    10L,
    new BigDecimal("125000.00"),
    "PAID"
);

order.setDisplayStatus("Paid");

assertEquals("Paid", order.getDisplayStatus());
```

`@Transient` does not remove the ability to hold a value in the field in memory.

### 12.2. Integration Testing with a Repository

An integration test can save an entity, read it back, and confirm that persistent properties are preserved while the transient property is not restored from the database:

```java
StepVerifier.create(
        purchaseOrderRepository.save(order)
            .flatMap(saved -> purchaseOrderRepository.findById(saved.getId()))
    )
    .assertNext(reloaded -> {
        assertEquals(order.getTotal(), reloaded.getTotal());
        assertEquals(order.getStatus(), reloaded.getStatus());
        assertNull(reloaded.getDisplayStatus());
    })
    .verifyComplete();
```

The example assumes `displayStatus` is not automatically initialized in the constructor. Real tests should use a database and schema compatible with the project, and confirm that the table does not require a `display_status` column.

### 12.3. Testing Custom SQL

If a `DatabaseClient` mapper actively sets a transient property, test that mapper separately. `@Transient` does not prevent manual mapper code from running, so results can differ from entities read via a repository.

## 13. Common Errors

| Error | Consequence | Resolution |
|---|---|---|
| Mistakenly importing `jakarta.persistence.Transient` | Spring Data Relational may not apply the annotation as expected | Use `org.springframework.data.annotation.Transient` |
| Assuming `@Transient` removes the field from the object | Code confuses developers when getters/setters still work | Remember the annotation only controls persistence mapping |
| Expecting a transient property to be saved when calling `save()` | The value is ignored on write | Remove the annotation or use a persistent column if it needs saving |
| Expecting the database to return a transient value on SELECT | Default or code-initialized value is kept | Compute/enrich after reading or use a DTO projection |
| Using a transient property in a derived query | No corresponding persistent column exists to build the SQL condition | Query by the source field or an SQL expression |
| Using `@Transient` for a read-only database column | Mapping does not read the column at all | Consider `@ReadOnlyProperty` if appropriate |
| Thinking `@Transient` hides a field from JSON | The serializer can still invoke the getter and serialize the field | Use a DTO or separate Jackson configuration |
| Thinking `@Transient` rewrites hand-written SQL | Manual SQL still runs exactly as sent | Update the SQL and mapper explicitly |
| Putting a required transient value into the persistence constructor | Materialization may lack data to construct the object | Base the constructor on persistent properties and enrich afterward |
| Putting data from many services onto an entity | Entity becomes tied to one use case and hard to reuse | Create a DTO/view model at the service layer |

## 14. When Should You Use a DTO Instead of @Transient?

`@Transient` is helpful when a temporary property genuinely belongs to how the application uses the entity. However, an entity should not be treated as a container for all data returned by an API.

Consider a DTO when:

- The extra data serves only one endpoint or one screen.
- Data comes from multiple tables, services, or external sources.
- The response structure differs significantly from the database entity.
- You need exact control over which fields are serialized outward.
- A property depends on the current user, locale, permissions, or processing time.
- You want to prevent the persistence entity from changing with presentation requirements.

Example:

```java
public record PurchaseOrderView(
    Long id,
    BigDecimal total,
    String status,
    String displayStatus,
    boolean canCancel
) {}
```

The service can map the entity to the view:

```java
Mono<PurchaseOrderView> findView(Long id, UserContext user) {
    return repository.findById(id)
        .map(order -> new PurchaseOrderView(
            order.getId(),
            order.getTotal(),
            order.getStatus(),
            toDisplayStatus(order.getStatus()),
            canCancel(order, user)
        ));
}
```

Here, `canCancel` depends on the current user, so it should not be stored in the orders table and does not even need to be a field on the entity. The DTO makes it clear that this is data for a specific response.

## 15. Usage Guidelines

- Use `org.springframework.data.annotation.Transient` for properties excluded from Spring Data Relational mapping.
- Place the annotation on the exact field or property used by mapping; verify the entity's access strategy.
- Keep the persistence constructor focused on properties that can be materialized from the database.
- Compute or enrich transient values after reading if they depend on runtime data.
- Do not use transient properties as columns in derived queries.
- Distinguish `@Transient` from `@ReadOnlyProperty`: one is ignored by mapping, while the other can be read but not written.
- Distinguish Spring Data's annotation from JPA annotations, Java `transient`, and `@JsonIgnore`.
- Remember that `DatabaseClient` with a manual mapper does not automatically enforce `@Transient` rules on Java code you write.
- Use a DTO when extra data serves a single use case or depends on user context.
- Test with a repository on a compatible database to verify actual read/write behavior.

`@Transient` is an explicit way to declare that a property belongs to the in-memory object but not to Spring Data Relational's persistence model. Using the right annotation and understanding its scope keeps entities aligned with the schema, prevents SQL from referencing nonexistent columns, and still lets the application attach computed values or runtime data when needed.
