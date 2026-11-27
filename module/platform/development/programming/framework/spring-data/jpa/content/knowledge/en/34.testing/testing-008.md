# Testing Mappings, Cascades, orphanRemoval, and Data Constraints

Testing Spring Data JPA is not just about confirming a repository returns the right entity. A mapping can be readable yet write to the wrong relationship side; cascades can persist or delete more entities than intended; `orphanRemoval` can delete data accidentally; and constraints are only caught by the database when SQL is actually flushed.

A solid test suite must verify both object state in the persistence context and persisted data after writing to and reloading from the database. This lesson uses a PurchaseOrder – OrderLine relationship to illustrate how to test mappings, entity lifecycles, and key constraints.

## 1. Distinguishing Mapping Responsibilities From Database Responsibilities

JPA mappings describe how entities relate to tables and columns:

- `@OneToMany`, `@ManyToOne`, and `@OneToOne` describe relationships between entities.
- `mappedBy` designates the inverse side; the other side is the owning side, where JPA reads foreign key information to persist.
- `cascade` specifies which lifecycle operations propagate from parent to related entities.
- `orphanRemoval` specifies that a child entity must be deleted when removed from its owning relationship.
- `@Column`, `@JoinColumn`, and `@Table` describe column attributes, foreign keys, and uniqueness.

The database is what enforces constraints such as `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, and `CHECK`. Annotations can be used to generate schemas in suitable environments, but if production schemas are managed by Flyway or Liquibase, migrations must create the corresponding constraints. Never assume merely adding `nullable = false` in Java code guarantees `NOT NULL` exists in the production database.

Therefore, you need both JPA-level mapping tests and constraint integration tests against the database engine your application actually uses.

## 2. Example Bidirectional Relationship Mapping

An order has multiple order lines. Each order line belongs to exactly one order. This is a parent–child relationship with dependent lifecycles, so the example uses `cascade` and `orphanRemoval`.

**PurchaseOrder Entity:**

~~~java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(
    name = "purchase_orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_purchase_orders_external_ref",
        columnNames = "external_ref"
    )
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "external_ref", nullable = false, length = 40)
    private String externalRef;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String externalRef) {
        this.externalRef = externalRef;
    }

    public Long getId() {
        return id;
    }

    public String getExternalRef() {
        return externalRef;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public void removeLine(OrderLine line) {
        lines.remove(line);
        line.setOrder(null);
    }
}
~~~

**OrderLine Entity:**

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

In this mapping:

- `OrderLine.order` is the owning side because it declares `@ManyToOne` and holds the `order_id` foreign key.
- `PurchaseOrder.lines` is the inverse side because `mappedBy = "order"` points to the `order` field on the child entity.
- `addLine()` updates both the parent collection and the child reference.
- `removeLine()` removes the element from the collection and synchronizes both sides.
- `cascade = CascadeType.ALL` propagates supported lifecycle operations from parent to children.
- `orphanRemoval = true` marks a child removed from the collection as an orphan to be deleted upon synchronizing the persistence context.

If you only call `order.getLines().add(line)` without setting `line.setOrder(order)`, the owning side is not updated. The database may receive `NULL` for `order_id` or fail to persist the relationship as intended. Helper methods help prevent forgetting to synchronize both sides.

## 3. How Do Cascade and orphanRemoval Differ?

The two mechanisms are often used together, yet their meanings differ.

### Cascade

Cascade propagates a JPA operation from one entity to related entities. Common values:

| Cascade Type | Meaning |
|---|---|
| `PERSIST` | Persisting the parent persists cascaded child entities |
| `MERGE` | Merging the parent merges cascaded child entities |
| `REMOVE` | Removing the parent removes cascaded child entities |
| `REFRESH` | Refreshing the parent refreshes cascaded child entities |
| `DETACH` | Detaching the parent detaches cascaded child entities |
| `ALL` | Includes all of the operations above |

For example, `cascade = CascadeType.PERSIST` is suitable when saving a new parent and children together. `CascadeType.ALL` is broader: it also propagates `REMOVE`. Therefore, do not use `ALL` mechanically if related entities can be shared or have independent lifecycles.

### orphanRemoval

`orphanRemoval = true` applies to `@OneToOne` or `@OneToMany` relationships. When a child entity is removed from the owning relationship, the provider deletes the child entity when synchronizing the persistence context.

Example:

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
OrderLine line = order.getLines().get(0);

order.removeLine(line);
entityManager.flush();
~~~

After flush, the `OrderLine` has been dissociated and marked for deletion. `orphanRemoval` is useful when the child entity is truly owned by the parent, such as line items of an order.

Distinguish the scenarios:

- Deleting the parent entity: `CascadeType.REMOVE` can propagate the remove operation to children.
- Removing an element from the parent's collection: `orphanRemoval` deletes the orphaned child entity.
- Deleting a shared entity: do not enable cascade `REMOVE` or `orphanRemoval` if that entity can still be referenced by other objects.

JPA cascading also differs from database `ON DELETE CASCADE`. JPA cascading is executed by the provider through the entity lifecycle; `ON DELETE CASCADE` is a database-level constraint/behavior. If using both, understand the deletion path thoroughly and test against a real database.

## 4. Testing Mappings With @DataJpaTest

Spring Boot's `@DataJpaTest` creates a JPA test slice: configuring entities, repositories, and transactions for persistence testing. By default, tests usually run inside a transaction and roll back after each method.

`TestEntityManager` can be used to persist, flush, clear, and reload entities. This is a good practice to avoid checking only objects sitting in memory.

**Repository:**

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

**Testing cascade persist and bidirectional mapping:**

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class PurchaseOrderMappingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void persistsChildThroughCascadeAndOwningSide() {
        PurchaseOrder order = new PurchaseOrder("PO-100");
        OrderLine line = new OrderLine("SKU-1", 2);
        order.addLine(line);

        entityManager.persist(order);
        entityManager.flush();

        Long orderId = order.getId();
        Long lineId = line.getId();

        entityManager.clear();

        PurchaseOrder reloaded =
                entityManager.find(PurchaseOrder.class, orderId);
        OrderLine reloadedLine =
                entityManager.find(OrderLine.class, lineId);

        assertThat(reloaded.getLines()).hasSize(1);
        assertThat(reloaded.getLines().get(0).getSku()).isEqualTo("SKU-1");
        assertThat(reloadedLine.getOrder().getId()).isEqualTo(orderId);
    }
}
~~~

The test confirms three things:

1. Only `PurchaseOrder` was persisted, yet `OrderLine` was still inserted thanks to `CascadeType.PERSIST` included in `CascadeType.ALL`.
2. The relationship was written to the database because the helper method updated the owning side.
3. After `clear()`, data is read back from the database; assertions do not rely solely on the initial in-memory object.

If a test only asserts `order.getLines().size()` before flush/clear, it has not proven the foreign key was written properly. The collection can hold items in memory while the owning side remains null.

## 5. Testing orphanRemoval

Verify that removing a child from the collection actually deletes the corresponding row in the database.

~~~java
@Test
void deletesChildWhenRemovedFromParentCollection() {
    PurchaseOrder order = new PurchaseOrder("PO-200");
    OrderLine line = new OrderLine("SKU-2", 1);
    order.addLine(line);

    entityManager.persist(order);
    entityManager.flush();

    Long orderId = order.getId();
    Long lineId = line.getId();

    entityManager.clear();

    PurchaseOrder managed =
            entityManager.find(PurchaseOrder.class, orderId);
    OrderLine child = managed.getLines().get(0);

    managed.removeLine(child);
    entityManager.flush();
    entityManager.clear();

    assertThat(entityManager.find(OrderLine.class, lineId)).isNull();

    PurchaseOrder reloaded =
            entityManager.find(PurchaseOrder.class, orderId);
    assertThat(reloaded.getLines()).isEmpty();
}
~~~

Crucially, the test calls `flush()` before `clear()`. `flush` forces the provider to synchronize the delete operation to the database; `clear()` evicts managed entities so subsequent checks reload persisted state.

This test also confirms the parent still exists after removing one order line. That is the intended behavior of `orphanRemoval`: delete the child detached from the relationship, not the parent.

## 6. Testing Cascade REMOVE

Testing cascade `REMOVE` checks deleting the parent entity and confirming child entities are deleted along with it.

~~~java
@Test
void removesChildrenWhenParentIsRemoved() {
    PurchaseOrder order = new PurchaseOrder("PO-300");
    order.addLine(new OrderLine("SKU-3", 1));
    order.addLine(new OrderLine("SKU-4", 2));

    entityManager.persist(order);
    entityManager.flush();

    Long orderId = order.getId();
    Long firstLineId = order.getLines().get(0).getId();
    Long secondLineId = order.getLines().get(1).getId();

    entityManager.clear();

    PurchaseOrder managed =
            entityManager.find(PurchaseOrder.class, orderId);

    entityManager.remove(managed);
    entityManager.flush();
    entityManager.clear();

    assertThat(entityManager.find(PurchaseOrder.class, orderId)).isNull();
    assertThat(entityManager.find(OrderLine.class, firstLineId)).isNull();
    assertThat(entityManager.find(OrderLine.class, secondLineId)).isNull();
}
~~~

`CascadeType.ALL` includes `CascadeType.REMOVE`, so when `PurchaseOrder` is removed, the remove operation cascades to the related `OrderLine` instances. `orphanRemoval` also participates in this relationship lifecycle; the test verifies the observable result that child rows no longer exist in the database.

If child entities can be referenced by multiple parents or have independent lifecycles, reconsider cascade `REMOVE` before using a similar mapping.

## 7. Testing Database Constraints

Mappings can declare several attributes:

- `@Column(nullable = false)`: column requires a value when the schema is generated from mappings.
- `@Column(unique = true)`: declares uniqueness for a single column during schema generation.
- `@Table(uniqueConstraints = ...)`: declares multi-column unique constraints or names constraints.
- `@JoinColumn(nullable = false)`: foreign key cannot be NULL in generated schema.
- `@Column(length = ...)`: column length during schema generation.

For example, `PurchaseOrder` requires a non-null, unique `external_ref`. Verify that production migrations actually create the corresponding `NOT NULL` and `UNIQUE` constraints.

**Testing UNIQUE:**

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.springframework.dao.DataIntegrityViolationException;

@Test
void rejectsDuplicateExternalReference() {
    repository.saveAndFlush(new PurchaseOrder("PO-DUPLICATE"));

    assertThatThrownBy(() ->
            repository.saveAndFlush(
                    new PurchaseOrder("PO-DUPLICATE")))
            .isInstanceOf(DataIntegrityViolationException.class);
}
~~~

`saveAndFlush()` forces Hibernate to send SQL immediately, so constraints are usually caught right where the test expects instead of at the end of the transaction. Spring Data repositories translate certain persistence errors into `DataIntegrityViolationException`.

After a failed flush, the transaction is normally marked rollback-only and the persistence context is no longer safe for further persistence operations. Let the test finish and roll back instead of attempting to continue using the same persistence context.

### 7.1. Constraints to Test

| Constraint | Example | Test Objective |
|---|---|---|
| `NOT NULL` | `external_ref` cannot be null | Inserting a null value is rejected |
| `UNIQUE` | `external_ref` must not duplicate | Inserting two records with the same value is rejected |
| `FOREIGN KEY` | `order_lines.order_id` must reference an existing order | Inserting a child with a nonexistent parent ID is rejected |
| `CHECK` | `quantity > 0` | Inserting zero or negative quantity is rejected |
| Composite `UNIQUE` | a product appears only once per order | Duplicate `(order_id, sku)` pair is rejected |

These constraints should be defined in migrations or database schemas. Example SQL migration:

~~~sql
ALTER TABLE order_lines
    ADD CONSTRAINT fk_order_lines_order
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id);

ALTER TABLE order_lines
    ADD CONSTRAINT ck_order_lines_quantity_positive
    CHECK (quantity > 0);

ALTER TABLE purchase_orders
    ADD CONSTRAINT uk_purchase_orders_external_ref
    UNIQUE (external_ref);
~~~

Migration syntax may need adjustments depending on the database and current schema state. Before adding constraints to tables containing existing data, identify and resolve any violating rows.

### 7.2. Bean Validation vs. Database Constraints

You can use `@NotBlank`, `@NotNull`, `@Positive`, or `@Size` to validate data at the application layer. Example:

~~~java
@NotBlank
@Size(max = 40)
@Column(name = "external_ref", nullable = false, length = 40)
private String externalRef;
~~~

Bean Validation provides errors close to where data enters. Database constraints protect data regardless of whether writes come through JPA, direct SQL, batch jobs, or another application.

Do not treat the two validation layers as substitutes for each other. A validation test proves data is rejected in Java, not that the database enforces a constraint. To test the database, execute SQL or flush persistence operations against a database with real constraints.

## 8. Testing Foreign Keys and the Owning Side

With bidirectional relationships, verify the foreign key is actually written in the child table. A common mistake is adding the child only to the parent-side collection:

~~~java
PurchaseOrder order = new PurchaseOrder("PO-400");
OrderLine line = new OrderLine("SKU-5", 1);

// Wrong: modifies only the inverse side.
order.getLines().add(line);
~~~

Because `PurchaseOrder.lines` uses `mappedBy = "order"`, JPA reads the foreign key value from `OrderLine.order`. The snippet above does not set `OrderLine.order`, so the relationship is not properly established.

Correct approach:

~~~java
PurchaseOrder order = new PurchaseOrder("PO-400");
OrderLine line = new OrderLine("SKU-5", 1);

order.addLine(line);
~~~

A test can call `flush()` and reload `OrderLine` to confirm `line.getOrder()` points to the right order. If the database enforces a `NOT NULL` foreign key, the test also catches cases where the owning side was left unset.

Do not rely solely on the collection getter to conclude a bidirectional mapping works. Check both sides after reloading.

## 9. Testing With a Real Database via Testcontainers

`@DataJpaTest` can automatically configure an embedded database if H2 is present in the project. H2 is convenient for fast tests, yet does not guarantee identical behavior to MySQL, PostgreSQL, or Oracle regarding:

- Constraint syntax and enforcement behavior.
- Data types, collations, and string comparisons.
- Locking and transaction rules.
- SQL dialects and DDL.
- Database-level cascades, triggers, and migrations.

For database-dependent behaviors, run integration tests using Testcontainers with the exact production engine. For instance, on Spring Boot 3.1+ you can use `@ServiceConnection`:

~~~java
@Testcontainers
@DataJpaTest
class PurchaseOrderDatabaseTest {

    @Container
    @ServiceConnection
    static MySQLContainer<?> mysql =
            new MySQLContainer<>("mysql:8.4");
}
~~~

You need Testcontainers dependencies for JUnit Jupiter and MySQL, plus the appropriate migration/schema configuration. On older Spring Boot versions without `@ServiceConnection`, use `@DynamicPropertySource` to supply the container's JDBC URL, username, and password.

Running migrations in tests verifies the actual production schema builds cleanly. Especially for `CHECK`, composite `UNIQUE`, and `FK` behaviors, this is far more reliable than relying solely on H2.

## 10. Common Mistakes When Writing Tests

**Testing only in-memory objects.** Collections may look right while the owning side was never persisted. Flush, clear, and reload.

**Forgetting to synchronize both sides of a relationship.** Adding a child to the inverse collection without setting the parent reference on the child can leave the foreign key wrong or null.

**Confusing cascade with orphanRemoval.** Cascade propagates lifecycle operations; `orphanRemoval` deletes a child when detached from the relationship. Test both scenarios separately.

**Using CascadeType.ALL on shared entities.** Deleting a parent via cascade `REMOVE` can delete data still needed by other entities. Cascade only operations matching real ownership.

**Not flushing in constraint tests.** SQL errors may only appear at flush or commit. Use `saveAndFlush()` or `entityManager.flush()` to pinpoint the exact failure trigger.

**Testing constraints only on H2.** Differences from the production database can create false-positive tests. Add tests on the target engine when verifying DDL and constraints.

**Continuing to use the persistence context after a constraint error.** The transaction may already be rollback-only. Let the test end and roll back.

**Skipping migrations.** Mapping annotations do not update production schemas if migrations manage DDL. Test real migrations and schemas alongside entity code.

## 11. Checklist for a Mapping Test Suite

1. Verify the correct owning side and `mappedBy`.
2. Check that helper methods update both sides of the relationship.
3. Persist the parent and confirm cascade `PERSIST` saves children.
4. Flush, clear, and reload to confirm foreign keys.
5. Remove a child from the collection, flush, and confirm `orphanRemoval` deletes the child.
6. Remove the parent and confirm cascade `REMOVE` aligns with ownership.
7. Test violating `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, and `CHECK`.
8. Confirm constraint errors surface at flush or the expected SQL point.
9. Run migrations and tests on the target database for engine-dependent behavior.
10. Ensure no shared entity is deleted unintentionally.

## Conclusion

Mapping tests must verify data is written properly on the owning side and relationships remain intact after reloading from the database. Cascades govern lifecycle operations propagated from parent to child; `orphanRemoval` deletes children detached from an owning relationship. Database constraints protect data integrity even when operations bypass JPA.

Combining `@DataJpaTest`, `flush`/`clear`, constraint tests, and Testcontainers when needed catches mapping and entity lifecycle bugs before they reach production.