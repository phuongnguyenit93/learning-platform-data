# Foreign Key Violations, Unique Constraints, and Unexpected Child Data

When saving an aggregate with Spring Data JDBC, the database still enforces integrity constraints such as foreign keys, primary keys, unique constraints, and check constraints. If data fails a constraint, the SQL statement fails and Spring typically translates the JDBC error into an exception in the `DataAccessException` hierarchy.

Beyond input data errors, Spring Data JDBC also exhibits an important behavior to understand when diagnosing child data: **when saving an existing aggregate root, the framework deletes the referenced child entities, updates the root, and then re-inserts the child entities according to the object's current state**. Because Spring Data JDBC does not track the aggregate's previous state, a root object missing its child collection can cause existing child data to be deleted upon save.

This lesson explains common causes of foreign key and unique constraint errors, how to map parent-child relationships using `@MappedCollection`, why child data can disappear or be recreated, how to keep aggregates consistent, and how to diagnose exceptions within transactions.

## 1. Three Common Constraint Categories

### 1.1. Foreign key constraint

A foreign key ensures that a referencing value points to an existing row in the referenced table.

For example, each order line must belong to an order:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id)
);
~~~

The `order_line.order_id` column must hold a value that exists in `purchase_order.id`.

Foreign key errors can occur when:

- Inserting a child with a nonexistent parent ID.
- Updating a foreign key to point to a nonexistent parent.
- Deleting a parent while a row in another table still references that parent.
- Mapping generates a back-reference column name that does not match the schema.
- Data written via manual SQL skips the proper insert/delete ordering.

### 1.2. Unique constraint

A unique constraint ensures that a value or combination of values does not repeat.

For example, an SKU may appear only once within the same order:

~~~sql
ALTER TABLE order_line
ADD CONSTRAINT uq_order_line_sku
UNIQUE (order_id, sku);
~~~

If the application adds two lines with the same `order_id` and `sku`, the database rejects the duplicate row.

Unique constraints are commonly used to protect rules such as:

- Unique customer email addresses.
- Unique order numbers.
- One line per SKU within an order.
- One membership per user in an organization.
- A composite key pair that must not appear twice.

Do not confuse a unique constraint with a primary key. A primary key is always unique and non-null; unique constraints can be defined on other business columns.

### 1.3. Check constraints and NOT NULL

In addition to foreign keys and unique constraints, the database can reject data because:

- A required column receives null.
- A value fails a `CHECK` constraint.
- A value exceeds column length or precision.
- Data types are incompatible.

Example:

~~~sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
~~~

An order line with zero or negative quantity cannot be persisted.

## 2. Which exceptions does Spring translate database errors into?

Spring JDBC uses exception translation to convert `SQLException` and data access framework errors into consistent exceptions in the `org.springframework.dao` package.

Two common types:

| Exception | Meaning |
| --- | --- |
| `DataIntegrityViolationException` | An insert/update/delete operation violates an integrity constraint or data cannot be persisted under the schema |
| `DuplicateKeyException` | A more specific error related to a duplicate key; this is a subclass of `DataIntegrityViolationException` |

`DataIntegrityViolationException` is the general exception for integrity violations. It can encompass foreign keys, unique constraints, primary keys, check constraints, or schema-incompatible data.

Not every JDBC driver classifies the same constraint violation into the exact same subclass. Therefore, in business handling, you should generally catch `DataIntegrityViolationException` at an appropriate boundary. Only catch `DuplicateKeyException` when the database's translator reliably provides that specific subtype.

Example of handling a duplicate SKU error:

~~~java
try {
    orderRepository.save(order);
} catch (DuplicateKeyException ex) {
    throw new DuplicateOrderLineException(
        "SKU already exists in this order",
        ex
    );
}
~~~

If you want to handle multiple violation types, catch the more general exception:

~~~java
try {
    orderRepository.save(order);
} catch (DataIntegrityViolationException ex) {
    throw new OrderPersistenceException(
        "Order data violates a database constraint",
        ex
    );
}
~~~

Do not turn every `DataIntegrityViolationException` into a "duplicate key" error. A foreign key violation and a unique violation have different business causes.

### 2.1. Finding the root cause

Spring exceptions typically preserve the underlying exception from the JDBC driver. You can retrieve the specific cause for logging or diagnostics:

~~~java
catch (DataIntegrityViolationException ex) {
    Throwable rootCause = ex.getMostSpecificCause();

    log.error(
        "Database constraint violation: {}",
        rootCause.getMessage(),
        ex
    );

    throw ex;
}
~~~

Useful details for identifying the failure include:

- The violated constraint name if provided by the database/driver.
- Table and column names.
- SQLState.
- Vendor error code.
- The running SQL statement and bind values suitable for debug environments.

Do not rely on parsing message strings to drive business control flow because message formats vary by database, driver, and version.

## 3. Parent-Child Mapping with @MappedCollection

Spring Data JDBC treats entities referenced from an aggregate root as part of the aggregate. For example, `PurchaseOrder` is the root and `OrderLine` is a child entity. All consistent modifications go through the root.

Root:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_no"
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String status) {
        this.status = status;
    }

    public void addLine(String sku, int quantity) {
        lines.add(new OrderLine(sku, quantity));
    }

    public void removeLine(String sku) {
        lines.removeIf(line -> line.sku().equals(sku));
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
~~~

Child entity:

~~~java
import org.springframework.data.relational.core.mapping.Table;

@Table("order_line")
public record OrderLine(
    String sku,
    int quantity
) {
}
~~~

`@MappedCollection` tells Spring Data which column in the child table references the root's primary key and which column stores the List index or Map key.

In this example:

- `idColumn = "order_id"` is the foreign key pointing to `purchase_order.id`.
- `keyColumn = "line_no"` stores the element index in the List.
- `OrderLine` does not need an independent ID in this example; child rows are identified within the aggregate by parent ID and key/index.

### Corresponding schema

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),

    CONSTRAINT pk_order_line
        PRIMARY KEY (order_id, line_no),

    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id),

    CONSTRAINT uq_order_line_sku
        UNIQUE (order_id, sku)
);
~~~

The child table has three distinct constraints:

- Primary key `(order_id, line_no)` ensures each position in an order has only one row.
- Foreign key `order_id` ensures the parent exists.
- Unique `(order_id, sku)` ensures the same SKU cannot appear twice in one order.

The default back-reference column name is typically derived from the aggregate root's table name. `@MappedCollection(idColumn = "order_id")` lets you specify the column name explicitly to match the schema. For Lists and Maps, the key column can also be customized.

## 4. Aggregate Write and Delete Order

Spring Data JDBC processes the entire aggregate via its root. When saving a new aggregate:

1. Insert the aggregate root.
2. Insert directly and indirectly referenced child entities.

The parent is inserted first so child rows can reference a valid ID.

When saving an existing aggregate, current behavior differs from ORMs with a persistence context:

1. Delete child entities referenced by the aggregate.
2. Update the aggregate root.
3. Re-insert child entities according to the object's current state.

When deleting an aggregate, Spring Data JDBC deletes the child entities belonging to the aggregate and then deletes the root according to the framework's persist/delete pipeline.

### Why does Spring Data JDBC rewrite all child entities?

Spring Data JDBC does not maintain a persistence context and does not track prior snapshots of individual child entities. It takes the current aggregate state from the passed-in object and materializes that state in the database.

Therefore, the framework must ensure existing rows become the exact set of rows represented by the new object. It accomplishes this by deleting referenced child rows and re-inserting the current set.

This can generate extra SQL even when changing only a single property on the root. For large collections, the write overhead can be substantial.

## 5. Child Data Deleted or Modified Unexpectedly

This is a frequent root cause when an aggregate is reconstructed from incomplete data and passed to `save`.

Suppose the database currently contains:

| order_id | line_no | sku | quantity |
| ---: | ---: | --- | ---: |
| 10 | 0 | BOOK-01 | 2 |
| 10 | 1 | PEN-02 | 3 |

The application constructs a root object containing only the order status and no order lines:

~~~java
PurchaseOrder partial = new PurchaseOrder("PAID");
// No OrderLine in the collection.
~~~

If this object is recognized as an existing aggregate and saved, Spring Data JDBC treats the empty collection as the desired final state. The existing order lines are deleted, and none are re-inserted.

As a result, child data disappears even though the code only intended to update the root status.

### 5.1. Always load the full aggregate before modifying it

A sound approach is to load the current aggregate, mutate it through domain methods, and save:

~~~java
@Transactional
public void markPaid(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.markPaid();

    orderRepository.save(order);
}
~~~

With a fully loaded aggregate, the existing child collection remains present in the object upon save.

If you need to update a single column without synchronizing the entire collection, consider a custom repository method or explicit SQL update. When doing so, the application assumes responsibility for preserving invariants and data relationships.

### 5.2. Do not treat child entities as independent aggregates

In the Spring Data JDBC model, child entities inside an aggregate root have their lifecycle managed by the root. When a reference is removed from the root, the corresponding child entity is deleted from the database.

If a child entity must be referenced independently by multiple aggregates or have its own lifecycle, it likely should not be a child of the current aggregate. Consider extracting it into its own aggregate root.

### 5.3. Many-to-one and many-to-many relationships belong to separate aggregates

Spring Data JDBC restricts entity references inside an aggregate to one-to-one or one-to-many relationships. If you need many-to-one or many-to-many relationships across aggregates, use IDs or `AggregateReference` to store references.

Example:

~~~java
import org.springframework.data.jdbc.core.mapping.AggregateReference;

public class PurchaseOrder {

    private AggregateReference<Customer, Long> customer;
}
~~~

`AggregateReference` represents the ID of another aggregate. It does not instruct Spring Data to save or delete the referenced aggregate as a child of the current root.

Do not place an entity referenced by multiple aggregates into the child collection of one root. When that root saves, the framework can delete and recreate child rows, causing foreign key errors or wiping out external references.

## 6. Diagnosing Foreign Key Violations

When encountering `DataIntegrityViolationException`, first identify which SQL statement failed and which constraint was violated.

### 6.1. Child insert cannot find parent

Common causes:

- Foreign key value does not match the parent ID.
- Parent has not been inserted yet, or parent insert failed.
- `@MappedCollection(idColumn = "...")` specifies a column name differing from the schema.
- Hand-written SQL inserts the child before inserting the parent.
- Legacy data holds an invalid foreign key.

For parent-child relationships within the same aggregate, Spring Data JDBC normally inserts the root first and then the child. If an error occurs along the standard repository save path, verify back-reference names, mappings, schema, and actual ID values.

### 6.2. Deleting a parent while referencing rows remain

For example, a `payment` table directly references `purchase_order`. If the database uses `ON DELETE RESTRICT` or equivalent default behavior, deleting the order fails while payments still exist.

You can address this according to business rules:

- Delete dependent rows before deleting the parent.
- Use `ON DELETE CASCADE` if the data lifecycle genuinely requires cascading deletes.
- Disallow parent deletion and transition business state to cancelled/closed instead.
- Use soft delete if historical data must be preserved.

Do not add cascades merely to silence exceptions. `ON DELETE CASCADE` can delete rows in other tables that the application never intended to remove.

### 6.3. Mismatched back-reference column

If Spring Data uses a back-reference column name that differs from the schema, inserting a child may report a missing column or fail to populate the foreign key.

Declare the column names explicitly:

~~~java
@MappedCollection(
    idColumn = "order_id",
    keyColumn = "line_no"
)
private List<OrderLine> lines;
~~~

Compare the mapping with DDL and naming strategy. For Lists/Maps, also verify the key column because it stores the collection index or key.

## 7. Diagnosing Unique Constraint Violations

A unique constraint usually signals that a business invariant was violated.

For example, the application enforces a rule that each order contains at most one line per SKU. If the service does not check the list before adding a new line, the database rejects inserting a duplicate SKU.

You can validate beforehand in the domain model:

~~~java
public void addLine(String sku, int quantity) {
    boolean alreadyExists = lines.stream()
        .anyMatch(line -> line.sku().equals(sku));

    if (alreadyExists) {
        throw new DuplicateOrderLineException(sku);
    }

    lines.add(new OrderLine(sku, quantity));
}
~~~

Checking in Java produces clear business errors. However, it does not replace a database unique constraint.

### Why is a unique constraint still needed?

Two concurrent requests can both check for an SKU before either inserts. Both observe that the SKU is absent and proceed. Only the database can serialize writes and guarantee uniqueness ultimately.

Therefore, combine:

1. Domain/service checks for early feedback.
2. Unique constraints to protect data against race conditions and other write paths.
3. Exception handling when the database rejects a competing request.

Do not rely solely on running a SELECT check before inserting. Between the SELECT and INSERT, another transaction can still write the same value.

### Constraints may be overly strict or mis-scoped

If business rules allow the same SKU to appear multiple times within one order, `UNIQUE(order_id, sku)` is wrong. You may need a different key, such as `line_no`, or an additional distinguishing attribute in the unique key.

Conversely, if uniqueness applies system-wide, the constraint must sit on the global business column, not merely on the parent-child pair.

Design unique keys to match the exact business scope: global, per-tenant, per-parent, or within a time window.

## 8. Handling Exceptions at the Business Boundary

Spring exception translation keeps code decoupled from individual JDBC driver exception classes. You can catch `DataIntegrityViolationException` or a specific subclass when provided by the translator.

For example, a service translates a duplicate SKU error into a business exception:

~~~java
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder save(PurchaseOrder order) {
        try {
            return orders.save(order);
        } catch (DuplicateKeyException ex) {
            throw new DuplicateOrderLineException(
                "The order already contains this SKU",
                ex
            );
        } catch (DataIntegrityViolationException ex) {
            throw new OrderDataIntegrityException(
                "The order violates a database constraint",
                ex
            );
        }
    }
}
~~~

This example catches `DuplicateKeyException` first because it is a subclass of `DataIntegrityViolationException`. Some drivers may return only the general exception for certain constraints, so do not assume every unique error always produces the same subclass.

Never catch an exception and ignore it:

~~~java
try {
    orders.save(order);
} catch (DataIntegrityViolationException ex) {
    log.warn("Could not save order", ex);
    // Continuing as if the save succeeded is wrong.
}
~~~

If an exception is swallowed inside the service, the transaction interceptor may never see it to trigger default rollback rules. Some databases also mark a transaction as failed after a constraint violation and disallow further SQL until rollback.

Translate the error into a business exception and throw it out of the transaction boundary, or explicitly trigger rollback per your transaction strategy. Never continue processing as if the aggregate was saved successfully.

### Do not parse messages to classify constraints

Constraint names, SQLState, and vendor error codes may live in the cause chain. When precise classification is needed, inspect the root cause consistently with your driver/database or implement a custom exception translator.

Avoid logic like:

~~~java
if (ex.getMessage().contains("uq_order_line_sku")) {
    // ...
}
~~~

Messages can change across driver or database versions. Using explicit constraint names in migrations and inspecting cause/SQLState in a controlled way is more resilient.

## 9. How Recreating Child Data Can Trigger Foreign Key Errors

Suppose `order_line` is a child of `purchase_order`. Another table `shipment_line` has a foreign key pointing to `order_line.id`.

If the application saves the aggregate and Spring Data JDBC deletes old child rows before re-inserting them, the foreign key from `shipment_line` can block deleting the child rows. If the database has cascading deletes configured, deleting child rows could unexpectedly delete shipment lines as well.

This signals an aggregate design mismatch: an entity modeled as a child is being referenced independently by another aggregate.

Common resolutions:

- Promote the entity with an independent lifecycle to its own aggregate root.
- Reference it from other aggregates by ID or `AggregateReference`.
- Avoid letting tables outside the aggregate reference child rows directly if Spring Data JDBC manages those children as root-owned data.
- If an existing schema mandates that relationship, consider a custom repository/SQL to manage child updates in a database-compatible way.

## 10. Diagnostic Workflow from Exception to Data

When a save or delete operation fails, investigate in order:

1. **Identify the operation:** which repository method ran—save root, insert child, update, or delete?
2. **Read the constraint:** which constraint name, table, and columns appear in the exception or database logs?
3. **Inspect data state:** does the parent exist, is a unique value duplicated, is the current child collection complete?
4. **Verify mappings:** do `@Table`, `@Column`, `@MappedCollection`, `idColumn`, and `keyColumn` match the schema?
5. **Inspect SQL:** enable JDBC logging in an appropriate environment to inspect the actual statements and execution order.
6. **Inspect transactions:** did the failure roll back the entire use case, or was the exception caught and ignored?
7. **Check other write paths:** are manual SQL scripts, batch jobs, or other services writing to the same tables?

### Enabling SQL logging

You can enable Spring JDBC logging in test environment configuration:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

Depending on the version and logging setup, you may need more specific loggers to see SQL and bind parameters. Do not log sensitive user values in production logs.

### Reading constraint details from the database

Constraint names in DDL should be descriptive, for example:

- `fk_order_line_order` for foreign keys.
- `uq_order_line_sku` for unique constraints.
- `pk_order_line` for primary keys.
- `ck_order_line_quantity` for check constraints.

Clear names make diagnosing failures much faster than database-generated constraint names. If the database omits the constraint name from the exception, inspect the cause chain, SQLState, vendor code, and server logs.

## 11. Transactions and Rollback on Constraint Violations

A constraint violation is a runtime data access exception in Spring. When it escapes a `@Transactional`-managed method, Spring rolls back the transaction by default.

Example:

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;

    public OrderApplicationService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void addLine(Long orderId, String sku, int quantity) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.addLine(sku, quantity);

        orders.save(order);
    }
}
~~~

If a unique or foreign key constraint is violated during save, an exception is thrown and the transaction rolls back according to default rules.

If you need to translate the exception into a business error, throw the new exception past the transaction boundary while preserving the original exception as the cause. If you catch the error and continue inside the same method, clearly verify whether the transaction remains valid and whether rollback must be marked.

Do not split a single use case—loading the root, modifying children, and saving the root—across separate transactions if consistency requires all-or-nothing execution.

## 12. Designing Aggregates to Prevent Unexpected Child Data Loss

Spring Data JDBC relies on aggregate boundaries to decide which data is written and deleted together.

### 12.1. Let the root manage only children sharing its lifecycle

An Order and its OrderLines typically form a one-to-many relationship: order lines belong to the order, have no independent lifecycle, and are not directly referenced by multiple other aggregates.

In this scenario, `@MappedCollection` is the right mapping.

If an entity can be shared among multiple parents, or must be updated/deleted independently, model it as a separate aggregate root and store IDs/references in other aggregates.

### 12.2. Do not save partial aggregates

If a service only wants to update status, load the full aggregate and update the status. Never construct a new object with the same ID but missing child collections and pass it to `save`.

If you need to update specific columns directly without reading the full aggregate, use a custom repository method or explicit JDBC SQL. In that case, you must explicitly account for child rows, version, constraints, and transactions.

### 12.3. Do not let other aggregates reference child rows

Spring Data JDBC assumes only the owning aggregate has foreign keys to its child tables. If another aggregate's table references a child row directly, deleting and re-inserting children on root save can be blocked or cause unintended cascades.

Reference aggregate roots by ID or `AggregateReference`. If historical data requires direct references to child rows, design custom persistence logic to preserve stable child identities.

### 12.4. Choose constraints matching business invariants

Database constraints should reflect the rules being enforced:

| Rule | Appropriate constraint |
| --- | --- |
| Child must have a parent | Foreign key |
| One SKU appears only once per order | Unique `(order_id, sku)` |
| Each List position holds one child | Primary key `(order_id, line_no)` |
| Quantity must be positive | Check `quantity > 0` |
| Status cannot be null | `NOT NULL` |

Constraints protect data even when multiple application instances, concurrent transactions, or external tools write directly to the database.

## 13. Testing Constraints and Child Lifecycles

Include integration tests on the target database to verify both mappings and constraint behavior.

### 13.1. Testing unique constraints

~~~java
@Test
void rejectsDuplicateSkuWithinOrder() {
    PurchaseOrder order = new PurchaseOrder("NEW");
    order.addLine("BOOK-01", 1);
    order.addLine("BOOK-01", 2);

    assertThatThrownBy(() -> orders.save(order))
        .isInstanceOf(DataIntegrityViolationException.class);
}
~~~

This test assumes the schema has `UNIQUE(order_id, sku)`. If the domain model already checks duplicates before persisting, a repository-level test can use JDBC directly to verify the database constraint independently.

### 13.2. Testing foreign keys

You can use `JdbcTemplate` to attempt inserting a child with a nonexistent parent ID and verify the database rejects it. This tests the schema constraint rather than repository mapping.

### 13.3. Testing saves of existing aggregates

A helpful test flow:

1. Save an order with two order lines.
2. Reload the aggregate through the repository.
3. Change status and save.
4. Reload and verify both order lines still exist.
5. Remove one line via a domain method and save.
6. Verify only the removed line is absent from the final state.

This test catches cases where a service builds a partial aggregate and accidentally wipes out child collections.

### 13.4. Testing transaction rollback

Execute a save that triggers a unique violation after making another write within the same transaction. Confirm the transaction rolls back and leaves no partial state behind.

For deadlocks, race conditions, or constraints under concurrent load, run integration tests on a real database or Testcontainers. Embedded databases may have different transaction and locking semantics than production.

## 14. Common Pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| Child insert reports foreign key violation | Parent does not exist yet or back-reference is wrong | Verify parent ID, `idColumn`, and SQL order |
| Root delete rejected by database | Another table still references the root | Delete dependents, use soft delete, or design appropriate cascade |
| Saving root wipes out all children | Passed object has missing or empty collection | Load full aggregate before modifying and saving |
| Saving root re-inserts children | This is how Spring Data JDBC synchronizes current aggregate state | Align child lifecycle with root; avoid external FKs to children |
| Adding child reports duplicate key | Duplicate primary key, list index, or unique business key | Verify key column and unique constraints |
| Duplicate SKU line rejected | Unique constraint `(order_id, sku)` enforced | Validate in domain first, or adjust constraint if business allows |
| Cannot populate foreign key column | `@MappedCollection` mismatches schema column name | Declare `idColumn` and `keyColumn` explicitly |
| Child data deleted on status update | Saving a detached/partial aggregate object | Load root fully before modifying; or use a separate SQL update |
| Exception caught, yet transaction fails to roll back as expected | Exception swallowed inside transactional method | Rethrow exception or mark rollback |
| Cannot distinguish unique vs. FK error | Only logging generic message | Inspect root cause, SQLState, vendor code, and constraint name |

## 15. Troubleshooting Workflow

When encountering foreign key, unique constraint, or unexpected child data issues, follow this sequence:

1. Identify the aggregate root and all child entities belonging to the aggregate.
2. Read the DDL to list primary key, foreign key, unique, check, and not-null constraints.
3. Cross-check `@MappedCollection`, naming strategy, `idColumn`, and `keyColumn` against the schema.
4. Verify whether the aggregate object passed to `save` reflects the intended final state of child collections.
5. Confirm whether referenced entities genuinely belong in the aggregate or should become separate aggregates.
6. Inspect SQL statements and insert/delete ordering in logs.
7. Handle exceptions at the service boundary and ensure transactions roll back when a use case fails.
8. Write integration tests reproducing the constraint on the target database.

## 16. Practice Exercises

### Exercise 1 — Foreign Key

Create Order and OrderLine with `@MappedCollection`. Try inserting a child via manual SQL with a nonexistent order ID and observe the exception.

### Exercise 2 — Unique Constraint

Add unique constraint `(order_id, sku)`. Create two OrderLines with the same SKU in one order and verify the database rejects it.

### Exercise 3 — Missing Child Data

Save an order with two lines, then construct a new object containing only the ID and status and call save. Observe the child data. Explain why loading the full aggregate before modifying avoids this issue.

### Exercise 4 — Persistence Order

Enable JDBC logging when inserting and deleting aggregates. Identify the SQL ordering between root and child.

### Exercise 5 — AggregateReference

Separate Customer into an independent aggregate root. Reference Customer from Order by ID or `AggregateReference` and explain why Customer should not be a child of Order.

### Exercise 6 — External Foreign Key to Child

Create another table referencing OrderLine. Try saving the order and observe the impact of the child delete/re-insert strategy. Then redesign the aggregate boundary.

### Exercise 7 — Exception Translation

Catch `DataIntegrityViolationException` and `DuplicateKeyException`. Compare cause chains on your database and translate errors into appropriate business exceptions.

### Exercise 8 — Transaction Rollback

Inside a `@Transactional` service, update the root and then create a child violating a unique constraint. Confirm the entire use case's changes roll back.

## 17. Official References

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): `@MappedCollection`, foreign key back-references, aggregate relationship limits, and child mapping.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): insert/update order and child entity delete/re-insert behavior when saving existing aggregates.
- [Spring Data Relational — Domain Driven Design and Relational Databases](https://docs.spring.io/spring-data/relational/reference/jdbc/domain-driven-design.html): aggregate roots, aggregate boundaries, and inter-aggregate reference rules.
- [Spring Framework — DataAccessException](https://docs.spring.io/spring-framework/reference/data-access/dao.html): unified exception hierarchy and exception translation at the data access layer.
- [Spring Framework — DataIntegrityViolationException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html): general exception for integrity constraint violations, including duplicate key cases.

Foreign keys and unique constraints protect data integrity at the database level. Spring Data JDBC adds aggregate-based persistence rules: the root manages child entity lifecycles, and saving an existing root deletes and recreates child entities based on current state. Understanding both layers helps separate invalid data errors from mapping or aggregate-design bugs, and prevents partial root updates from unintentionally wiping out child data.
