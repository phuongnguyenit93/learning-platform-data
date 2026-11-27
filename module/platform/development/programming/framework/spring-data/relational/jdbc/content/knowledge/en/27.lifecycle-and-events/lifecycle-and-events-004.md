# AfterConvertCallback for Derived Data After Loading

In **Spring Data Relational JDBC**, an aggregate is typically mapped from database rows into a Java object before the repository returns the result to the application. Some information only needs to exist on the object after loading, such as a display label derived from status, a short description combined from existing properties, or a helper value supporting presentation.

**`AfterConvertCallback`** is the lifecycle callback invoked by Spring Data JDBC after relational data has been converted into an aggregate. The callback receives the newly created aggregate, can enrich it with derived data, and must return the aggregate so Spring Data continues using that result.

A common usage is combining the callback with a `@Transient` property: the property lives in the Java object without being mapped to a database column. This lesson covers when the callback runs, how to register it, how to update mutable or immutable aggregates, how to test it, and what limitations to consider.

## 1. Position of AfterConvertCallback in the read lifecycle

When a repository reads an aggregate, Spring Data JDBC fetches data from the database and uses the mapping infrastructure to turn it into a domain object. Once conversion finishes, `AfterConvertCallback` can intervene on the aggregate before the result is returned to the caller.

General flow:

~~~mermaid
flowchart TD
    A["Repository reads data"] --> B["JDBC executes SELECT"]
    B --> C["Spring Data JDBC receives rows"]
    C --> D["Mapping converts data into aggregate"]
    D --> E["AfterConvertCallback.onAfterConvert()"]
    E --> F["Aggregate after callback"]
    F --> G["Repository returns result to caller"]
~~~

The callback fits when a derived value must be populated right after the aggregate is mapped, before a service or controller uses the object.

### 1.1. This callback runs on the read path

The name `AfterConvert` describes the exact timing: after Spring Data converts relational data into a Java object.

It is not a hook for:

- Preparing an aggregate before writing it to the database.
- Adjusting data immediately before an INSERT or UPDATE statement.
- Processing after an aggregate has been saved.
- Executing custom SQL in place of a repository.

Write operations have their own lifecycle callbacks, such as `BeforeConvertCallback`, `BeforeSaveCallback`, and `AfterSaveCallback`. Choose the callback matching the exact moment you need to intervene.

### 1.2. The callback works on the converted aggregate

`AfterConvertCallback<T>` receives an aggregate of type `T` and returns an object of type `T`:

~~~java
public interface AfterConvertCallback<T> extends EntityCallback<T> {
    T onAfterConvert(T aggregate);
}
~~~

In an application, you usually only need to implement the interface for a specific aggregate. Spring Data invokes the callback during mapping; there is no need to call it manually from a service.

This callback belongs to the package:

~~~java
org.springframework.data.relational.core.mapping.event.AfterConvertCallback
~~~

## 2. When should you use derived data after loading?

Suppose `PurchaseOrder` stores its status as an enum:

~~~java
public enum OrderStatus {
    DRAFT,
    SUBMITTED,
    CANCELLED
}
~~~

The database only stores the status code, while the application wants a simple descriptive label:

| Status | Derived label |
|---|---|
| `DRAFT` | Draft |
| `SUBMITTED` | Submitted |
| `CANCELLED` | Cancelled |

This label can be computed from the `status` property after the aggregate is loaded. If the label does not need to be stored in the database, it can be placed in a `@Transient` property.

Other suitable cases:

- Building a short description string from properties already present on the aggregate.
- Computing a display helper value that does not require storage.
- Preparing a secondary property needed by multiple consumers of the aggregate.
- Normalizing an in-object value after mapping, if the rule is stable and requires no extra data queries.

Do not use a callback just because you can. If the value can be computed directly via a simple getter or domain method, consider that approach first. A callback is useful when you need a centralized processing step after Spring Data has constructed the aggregate.

## 3. Marking derived properties with @Transient

Spring Data's `@Transient` marks a property as outside persistence mapping. The property can still exist on the Java object and be used by code, while Spring Data JDBC does not map it as a column to read or write.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    private OrderStatus status;

    @Transient
    private String statusLabel;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public String getStatusLabel() {
        return statusLabel;
    }

    public void setStatusLabel(String statusLabel) {
        this.statusLabel = statusLabel;
    }
}
~~~

The `statusLabel` property does not require a `status_label` column in the `purchase_orders` table. The callback will populate this property after Spring Data JDBC creates the object.

Distinguish two points:

- `@Transient` determines that the property is not managed by persistence mapping.
- `AfterConvertCallback` determines when and how that property is populated after reading.

Adding `@Transient` alone does not compute the value. Adding the callback without marking the property appropriately may cause Spring Data to try mapping that property as persistent data.

## 4. Implementing AfterConvertCallback

A callback can be declared as a Spring bean via `@Component` or registered through a bean configuration.

~~~java
import org.springframework.data.relational.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
        aggregate.setStatusLabel(toLabel(aggregate.getStatus()));
        return aggregate;
    }

    private String toLabel(OrderStatus status) {
        if (status == null) {
            return "Unknown";
        }

        return switch (status) {
            case DRAFT -> "Draft";
            case SUBMITTED -> "Submitted";
            case CANCELLED -> "Cancelled";
        };
    }
}
~~~

Key points:

1. The generic type `PurchaseOrder` specifies which aggregate the callback handles.
2. The `onAfterConvert` method receives the mapped aggregate.
3. The callback derives the label from data already in the aggregate.
4. The callback returns the enriched aggregate.

Because the callback is a Spring bean, Spring Data can detect and invoke it in the mapping lifecycle. There is no need to call `onAfterConvert()` directly in a repository or service.

### 4.1. Why must the aggregate be returned?

A callback can mutate the current object and return that same object:

~~~java
@Override
public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
    aggregate.setStatusLabel(toLabel(aggregate.getStatus()));
    return aggregate;
}
~~~

Or create and return a new instance, which is useful when the aggregate is immutable:

~~~java
@Override
public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
    return aggregate.withStatusLabel(toLabel(aggregate.getStatus()));
}
~~~

If the callback creates a new object yet returns the old object, the changes will not appear in the result Spring Data continues using. Always return the instance containing the final derived data.

## 5. Working with immutable aggregates

Not every domain model has setters. With an immutable class, you can create a copy containing the derived property.

Illustrative example:

~~~java
public final class PurchaseOrder {

    private final Long id;
    private final String orderNumber;
    private final OrderStatus status;
    private final String statusLabel;

    public PurchaseOrder(
            Long id,
            String orderNumber,
            OrderStatus status,
            String statusLabel) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.status = status;
        this.statusLabel = statusLabel;
    }

    public PurchaseOrder withStatusLabel(String label) {
        return new PurchaseOrder(
            id,
            orderNumber,
            status,
            label
        );
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public String getStatusLabel() {
        return statusLabel;
    }
}
~~~

Callback:

~~~java
@Component
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
        String label = switch (aggregate.getStatus()) {
            case DRAFT -> "Draft";
            case SUBMITTED -> "Submitted";
            case CANCELLED -> "Cancelled";
        };

        return aggregate.withStatusLabel(label);
    }
}
~~~

This outlines how to return a new instance; the constructor, creator, and mapping metadata of an immutable aggregate must align with your application's Spring Data JDBC configuration. If using `@Transient` on an immutable property, ensure the annotation is placed properly on the property that the mapping context excludes from persistence mapping.

There is no need to convert your entire domain model to mutable just to use callbacks. Choose the update approach matching how the aggregate is designed.

## 6. Registering callbacks with Spring

In a Spring Boot application with component scanning, callbacks are discovered like any other bean:

~~~java
@Component
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {
    // ...
}
~~~

If component scanning is not active for the package containing the callback, you can register it with `@Bean`:

~~~java
@Configuration
public class OrderCallbackConfiguration {

    @Bean
    PurchaseOrderAfterConvertCallback purchaseOrderAfterConvertCallback() {
        return new PurchaseOrderAfterConvertCallback();
    }
}
~~~

Do not register callbacks into `JdbcCustomConversions`. Converters and entity callbacks are two distinct extension points:

| Extension point | Purpose |
|---|---|
| `AfterConvertCallback` | Processes an aggregate after data has been converted into an object |
| `JdbcCustomConversions` | Converts values between domain types and JDBC types |

If the callback is not invoked, check whether the bean is in the application context and discovered by component scanning or a `@Bean` configuration.

## 7. When is the callback invoked?

The callback is invoked on read paths where Spring Data JDBC converts data into the corresponding aggregate. For example, repository operations that read aggregates such as finding by ID or querying a list go through this mapping lifecycle.

Importantly, the callback is tied to the **aggregate conversion process**, not to specific method names. If code uses `JdbcTemplate` to run SQL and manually maps a `ResultSet` into a DTO, Spring Data JDBC does not automatically invoke `AfterConvertCallback` for that result.

### 7.1. Do not confuse AfterConvert with AfterSave

`AfterConvertCallback` serves the read path. If you need to react after an aggregate is saved, look at write-lifecycle callbacks such as `AfterSaveCallback`.

Comparison examples:

| Need | Suitable lifecycle |
|---|---|
| Populating `statusLabel` after loading an aggregate | `AfterConvertCallback` |
| Preparing an aggregate before converting to write data | `BeforeConvertCallback` |
| Adjusting data before saving | `BeforeSaveCallback` |
| Performing work after saving | `AfterSaveCallback` |

Do not use `AfterConvertCallback` to emit notifications like "order was just created". An aggregate can be converted many times across read calls; re-reading does not mean a new business event occurred.

### 7.2. Do not assume callbacks run on every Java object

This callback belongs to Spring Data Relational mapping. It does not run automatically when:

- The application calls the constructor `new PurchaseOrder(...)` directly.
- Another mapper creates an object from JSON.
- `JdbcTemplate` maps results into a DTO directly.
- A test constructs an object directly without going through a repository or mapping infrastructure.

If you want the same logic applied across multiple object-creation paths, consider a domain factory, domain method, or shared mapper/service instead of relying entirely on callbacks.

## 8. Callbacks and execution order

An application may have multiple callbacks for the same lifecycle or multiple callbacks covering different aggregates. When order control is needed, Spring supports ordering rules via `Ordered` or the `@Order` annotation.

Example:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(100)
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {
    // ...
}
~~~

When multiple callbacks exist, define explicit ordering if a later callback depends on the result of an earlier one. Lower order values have higher priority and run first according to Spring's ordering rules.

However, avoid building long chains of callbacks with interdependent mutations. If data enrichment becomes complex, a dedicated service after the repository returns results can be easier to understand and control.

## 9. Do not turn callbacks into a place for per-aggregate queries

A common temptation is injecting another repository into a callback to look up related data:

~~~java
// Avoid for large lists if each callback invocation queries the DB.
@Component
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {

    private final CustomerRepository customers;

    public PurchaseOrderAfterConvertCallback(CustomerRepository customers) {
        this.customers = customers;
    }

    @Override
    public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
        Customer customer = customers.findById(aggregate.getCustomerId())
            .orElseThrow();
        aggregate.setCustomerName(customer.getName());
        return aggregate;
    }
}
~~~

If the repository loads 100 orders and the callback queries a customer for each order, the application can emit around 100 extra queries. This is the **N+1 query** problem.

For related data from other tables, consider:

- Writing a dedicated read query that JOINs tables and returns a DTO.
- Collecting IDs and querying all related data in one `IN` query.
- Using a query service to enrich the list after the repository returns results.
- Modeling data that genuinely belongs to the aggregate inside the aggregate mapping if that relationship fits the domain boundary.

Callbacks work best for data computable from the just-loaded aggregate. If I/O or additional queries are needed, measure query counts and consider moving enrichment to a read service capable of batching.

## 10. Callbacks should be deterministic and low on side effects

A callback is called as part of reading data. Consequently, the same input aggregate should produce predictable derived output.

Do:

- Compute values from already-loaded properties.
- Use pure transformation functions or side-effect-free services.
- Return the enriched aggregate.
- Keep callbacks short and easy to test.
- Explicitly handle null properties or legacy invalid data.

Avoid:

- Sending emails or making HTTP calls when an aggregate is read.
- Writing to another database as a side effect of loading.
- Creating business events every time a repository reads an object.
- Using current time or global locale to produce unexpectedly varying values.
- Placing authorization decisions or access checks inside callbacks.

For example, `statusLabel` depends on the user's language. If a callback uses the server's default locale, the same aggregate may get a label different from the request's language. In such cases, let the presentation layer or a mapper accept an explicit locale and produce an appropriate DTO.

## 11. Are derived values in callbacks saved to the database?

No, if the property is marked `@Transient`. The callback only modifies the object residing in memory.

Example:

~~~java
@Transient
private String statusLabel;
~~~

After `AfterConvertCallback` assigns `statusLabel`, code can read it:

~~~java
PurchaseOrder order = orders.findById(id).orElseThrow();
System.out.println(order.getStatusLabel());
~~~

However, this value does not create a column and is not written to the database as part of the aggregate mapping.

If the aggregate is later saved again, Spring Data JDBC continues ignoring the `@Transient` property. To persist a value, design a persistent property and matching schema, or store another piece of data consistent with the domain model.

Do not use `@Transient` for data that must persist long-term or be queried directly from the database.

## 12. Testing callbacks with integration tests

Unit tests can verify the label-computation function, but integration tests confirm Spring Data JDBC discovers the callback and calls it while reading aggregates.

Example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.context.annotation.Import;

@DataJdbcTest
@Import(PurchaseOrderAfterConvertCallback.class)
class PurchaseOrderAfterConvertCallbackTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void derivesStatusLabelAfterLoadingAggregate() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("SO-100", OrderStatus.SUBMITTED)
        );

        PurchaseOrder loaded = orders.findById(saved.getId())
            .orElseThrow();

        assertEquals(OrderStatus.SUBMITTED, loaded.getStatus());
        assertEquals("Submitted", loaded.getStatusLabel());
    }
}
~~~

The example assumes the aggregate has a `create` factory, repository, and matching schema. Adjust constructors, ID generation, package, and test setup to match your project.

The test must read the aggregate back through the repository. An object constructed directly in the test or the input object passed to `save` does not prove `AfterConvertCallback` ran, because the callback belongs to the stage after read data is converted.

### 12.1. Verifying the transient property is not persisted

You can verify that the database lacks a `status_label` column while the callback still populates the value on read. This tests two independent responsibilities:

1. Mapping skips the transient property.
2. The callback enriches the in-memory property after conversion.

If tests need to inspect SQL, use queries checking stored data or SQL logging in the test environment. Never add a database column just to make a callback test run.

## 13. Comparing AfterConvertCallback with alternatives

| Approach | When suitable | Notes |
|---|---|---|
| Getter/domain method | Value computed purely from existing properties | No need to store derived state |
| `AfterConvertCallback` | Need to populate a property right after Spring Data JDBC builds the aggregate | Invoked on the read mapping path |
| `AfterLoadCallback` | Need a hook at a different load stage in the relational lifecycle | Verify exact callback contract for your version |
| DTO mapper/query service | Enriching data for a screen or API | Can accept locale, user context, and batched data explicitly |
| SQL projection/DTO query | Value needs JOINs, aggregate functions, or database-side computation | Controls query and column set explicitly |
| `AfterSaveCallback` | Need processing after the aggregate is saved | Not a post-read callback |

A simple value like an enum label can be computed with a getter. If multiple consumers need a property prepared right after mapping, a callback can reduce duplication. If the value depends on the request or data from multiple tables, a DTO mapper/query service is usually better.

## 14. Common mistakes

| Symptom | Cause | How to fix |
|---|---|---|
| Callback does not run | Bean is not discovered by Spring | Use `@Component` within component scan or declare a `@Bean` |
| Derived value is missing | Callback did not return the modified aggregate | Return the instance containing the new value |
| Spring tries to map a column for the extra property | Missing `@Transient` | Mark the property outside persistence mapping |
| Value only appears after re-reading | Confusing `AfterConvertCallback` with a post-save callback | Use the right lifecycle; this callback runs when converting read data |
| Callback does not run when constructing objects manually | Object did not go through Spring Data mapping | Call a domain factory/method or shared mapper |
| Queries spike | Callback queries a repository for each aggregate | Batch data or use a DTO query with JOINs |
| Label is in the wrong request language | Callback uses default/global locale | Generate labels in a presentation mapper with an explicit locale |
| Callback emits repeated events | Aggregate reads are mistaken for business events | Use callbacks only for object conversion, not emitting business events |
| Transient value disappears on next load | Property exists only in memory on the current instance | Recompute on each conversion or use an appropriate DTO |
| Null data breaks the callback | Unhandled null status/property | Define fallback rules or report invalid data |

## 15. Practice exercises

### Exercise 1 — Create status labels

1. Create a `PurchaseOrder` aggregate with `id`, `orderNumber`, and `status`.
2. Add a `statusLabel` property marked `@Transient`.
3. Write `PurchaseOrderAfterConvertCallback`.
4. Map each `OrderStatus` to its corresponding label.
5. Read the aggregate through the repository and verify the label.

### Exercise 2 — Callback with immutable aggregates

1. Convert the aggregate to an immutable design.
2. Add a `withStatusLabel` method.
3. Create a callback returning a new instance.
4. Verify the repository returns the post-callback instance.

### Exercise 3 — Compare callback with getter

1. Compute `statusLabel` directly via a getter.
2. Create a version using `AfterConvertCallback`.
3. Compare complexity and testability.
4. Choose the right approach when the value depends solely on the status enum.

### Exercise 4 — Spot N+1 queries

1. Create a callback that attempts to query `CustomerRepository` for each order.
2. Read a list of multiple orders.
3. Observe the number of queries emitted.
4. Move enrichment to a batch query or DTO JOIN.
5. Compare query counts and execution time.

### Exercise 5 — Verify lifecycle boundaries

1. Create a new aggregate and call `save`.
2. Read it back with `findById`.
3. Observe when the callback runs.
4. Construct an object manually via constructor and confirm the callback does not run automatically.
5. Try `JdbcTemplate` with `RowMapper` and confirm that mapping path does not automatically trigger Spring Data JDBC callbacks.

## 16. Conclusion

`AfterConvertCallback` is Spring Data JDBC's lifecycle hook invoked after relational data has been converted into an aggregate. The callback receives the aggregate, can attach derived values, and returns the instance the application will receive. Combined with `@Transient`, callbacks let you keep helper properties on Java objects without creating columns or writing those properties to the database.

Register the callback as a Spring bean and implement `AfterConvertCallback<T>` for the aggregate to process. Keep logic short, deterministic, and primarily based on already-loaded data. If data from other tables, additional queries, or context like locale/user is needed, consider a DTO mapper or query service to avoid N+1 queries and unpredictable side effects.

Remember that this callback belongs to the aggregate read and conversion path. It does not run when code constructs objects manually or maps SQL manually via `JdbcTemplate`, nor does it replace write-lifecycle callbacks. Choosing the right hook keeps post-load data enrichment clear and controllable.
