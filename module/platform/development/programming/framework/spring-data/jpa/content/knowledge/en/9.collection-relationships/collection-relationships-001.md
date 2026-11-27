# One-to-Many Mapping with @OneToMany

## 1. What Is a One-to-Many Relationship?

A one-to-many relationship represents a parent Entity that can be associated with multiple child Entities. For example, one `PurchaseOrder` has many `PurchaseOrderItem`s; each item belongs to one order. In the relational model, the foreign key usually resides on the child table:

```text
purchase_order
  id
  order_number

purchase_order_item
  id
  purchase_order_id  -> purchase_order.id
  product_code
  quantity
```

In Java, the parent side typically declares a collection using `@OneToMany`. If reverse navigation from child to parent is needed, the child Entity declares `@ManyToOne`. `@OneToMany` describes the collection; it does not by itself determine cascading, child deletion behavior, element ordering, or data loading strategy. Those behaviors must be designed explicitly.

## 2. Common Bidirectional Mapping: ManyToOne Owns the Foreign Key

For a schema with `purchase_order_item.purchase_order_id`, the standard pattern is a bidirectional relationship. The child Entity holds the `purchaseOrder` field and `@JoinColumn`, so the ManyToOne side is the owning side. The collection on the parent Entity uses `mappedBy` to point to the owning property:

```java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = {CascadeType.PERSIST, CascadeType.MERGE},
        orphanRemoval = true
    )
    private List<PurchaseOrderItem> items = new ArrayList<>();

    public void addItem(PurchaseOrderItem item) {
        items.add(item);
        item.setPurchaseOrder(this);
    }

    public void removeItem(PurchaseOrderItem item) {
        if (items.remove(item)) {
            item.setPurchaseOrder(null);
        }
    }
}
```

```java
@Entity
@Table(name = "purchase_order_item")
public class PurchaseOrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "purchase_order_id", nullable = false)
    private PurchaseOrder purchaseOrder;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    public void setPurchaseOrder(PurchaseOrder purchaseOrder) {
        this.purchaseOrder = purchaseOrder;
    }
}
```

These are the core mapping parts; in a real application, add constructors, getters, and any necessary business methods. `mappedBy = "purchaseOrder"` must match the exact Java property name in `PurchaseOrderItem`, not the column name `purchase_order_id`. `@JoinColumn` specifies the physical column holding the foreign key.

## 3. Why Is ManyToOne the Owning Side?

In this bidirectional relationship, the `purchase_order_item` table stores `purchase_order_id`. Therefore, Hibernate needs to know the value of `PurchaseOrderItem.purchaseOrder` to write or update the foreign key. The `PurchaseOrder.items` collection has `mappedBy`, so it is the inverse side.

When persisting the relationship, you must set the owning side:

```java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
PurchaseOrderItem item = new PurchaseOrderItem();
item.setProductCode("P-100");
item.setQuantity(2);
order.addItem(item);
```

The `addItem` helper both adds the item to the in-memory collection and sets `item.purchaseOrder`. Thanks to PERSIST cascade, when `order` is managed and the transaction commits, the new item can be persisted along with the parent. If cascade is not used, the item must be persisted separately. Only adding to `order.getItems()` without setting `item.purchaseOrder` can prevent the foreign key from being updated as expected.

For bidirectional relationships, JPA does not automatically synchronize the two Java fields. Helper methods should be the single place that adds or removes links to avoid a state where one side has changed while the other has not.

## 4. Unidirectional Mapping with @OneToMany

If you only need to navigate from parent to child, you can declare a unidirectional OneToMany without a ManyToOne field in the child Entity. You need to understand how JPA maps this relationship to the schema.

**Default using a join table:**

```java
@OneToMany
@JoinTable(
    name = "purchase_order_item_link",
    joinColumns = @JoinColumn(name = "purchase_order_id"),
    inverseJoinColumns = @JoinColumn(name = "item_id", unique = true)
)
private List<PurchaseOrderItem> items = new ArrayList<>();
```

The join table holds two foreign keys and represents the parent-child link. This is the common default structure of a unidirectional OneToMany when no join column is declared.

**Using a foreign key on the child table:**

```java
@OneToMany
@JoinColumn(name = "purchase_order_id")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

In this form, the collection is the owning side of the link and the `purchase_order_id` column lives on the child table. The child Entity does not need a back-reference property. Be sure to inspect the DDL and SQL generated by the provider, as adding children may involve extra insert/update statements depending on the mapping and provider. If the business logic frequently needs to navigate from an item back to the order, a bidirectional relationship with ManyToOne usually expresses the model more clearly.

## 5. Choosing Cascade Types Based on Child Entity Lifecycle

No cascade operations are enabled by default. Common cascade types:

| Cascade | Effect on OneToMany collection |
| --- | --- |
| `PERSIST` | Persists new children when the parent is persisted |
| `MERGE` | Merges associated children when the parent is merged |
| `REMOVE` | Deletes children when the parent is deleted |
| `REFRESH` | Refreshes children when the parent is refreshed |
| `DETACH` | Detaches children when the parent is detached |
| `ALL` | Includes all of the above |

Only enable cascades according to the lifecycle relationship. If `PurchaseOrderItem` only exists as part of an order, PERSIST/MERGE cascade may make sense. If the child is shared or can exist independently, do not automatically cascade REMOVE just because it appears in the collection.

`cascade = ALL` is convenient for small aggregates, but it can cause an operation on the parent to propagate to more Entities than intended. Choose each cascade type explicitly and review all deletion, update, import, and data synchronization flows.

## 6. orphanRemoval vs. Cascade REMOVE

`orphanRemoval = true` instructs the provider to delete a child Entity when it is removed from an eligible OneToMany or OneToOne relationship. For example, when an item is removed from `PurchaseOrder.items`, the item becomes an orphan and will be deleted at the appropriate flush.

This differs from cascade REMOVE:

- `cascade = REMOVE` propagates the remove operation from parent to child when the parent is deleted.
- `orphanRemoval = true` handles a child that is detached from the relationship, even while the parent still exists.

In the example above, `removeItem` removes the item from the collection and sets the parent reference to null to keep the object graph consistent. Because the mapping uses orphanRemoval, the item is marked for deletion on flush. This pattern is only appropriate when the item truly belongs to the order's lifecycle ownership. If you only want to unlink while keeping the item, do not use orphanRemoval and design a nullable foreign key or a rule to transfer the item to another parent.

Do not confuse orphanRemoval with database-level `ON DELETE CASCADE`. Orphan removal is an ORM lifecycle semantic; a database cascade constraint is a separate mechanism and must be configured in DDL.

## 7. Nullability Rules and Foreign Key Constraints

For a mandatory relationship, you can declare `optional = false` on ManyToOne and `nullable = false` on JoinColumn. The corresponding DDL should include the foreign key and NOT NULL:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE purchase_order_item (
    id BIGINT PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    product_code VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (purchase_order_id) REFERENCES purchase_order(id)
);
```

This is illustrative DDL; ID generation syntax, data types, and naming may need adjustment depending on the database. `nullable = false` in annotations does not replace migrations that create constraints on a running schema. If using Flyway/Liquibase, migrations must create the exact column names and constraints.

If you want to remove an item from the collection without deleting the record, the foreign key must allow null or the item must be moved to another parent before commit. If the FK is NOT NULL, you cannot simply unlink the item and leave it without a parent.

## 8. List, Set Collections, and Element Ordering

`List` is suitable when the application needs to preserve a display order; `Set` is suitable when the relationship requires non-duplicate semantics. However, a Java collection does not automatically produce a stable order in the database.

- `@OrderBy("productCode ASC")` sorts results by a property of the child Entity when the collection is loaded. The name in `@OrderBy` is the Java property name, not the physical column name.
- `@OrderColumn(name = "item_position")` stores the element position using an ordering column in the schema; the provider updates the position values when the list changes.
- If no ordering is declared, you should not rely on the order of elements returned from the database.
- With `Set`, `equals()` and `hashCode()` must remain stable while the Entity is in the collection. Avoid using mutable fields such as quantity or status as equality keys.

Example sorting by business line number:

```java
@OneToMany(mappedBy = "purchaseOrder")
@OrderBy("lineNumber ASC")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Example storing user-defined positions:

```java
@OneToMany(mappedBy = "purchaseOrder")
@OrderColumn(name = "item_position")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Choose only one strategy that fits the ordering requirement. `@OrderBy` reads based on an existing property value; `@OrderColumn` manages a separate position column and can cause extra updates when the list is reordered.

## 9. Lazy Loading and the N+1 Problem

`@OneToMany` defaults to LAZY in Jakarta Persistence. When loading the parent, the provider is not required to load the entire collection immediately. The collection can be loaded when the application accesses it within an active persistence context.

The N+1 problem occurs when querying a list of N parents, then accessing each parent's collection, causing Hibernate to issue an extra query per collection. For example, a page displaying 30 orders with their items can trigger 1 query to fetch orders plus 30 queries to fetch items.

Common solutions:

- Use `JOIN FETCH` for use cases that need both parent and children at the same time:

```java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.items
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithItemsById(@org.springframework.data.repository.query.Param("id") Long id);
```

- Use `@EntityGraph(attributePaths = "items")` on a repository method when you want to declare a fetch plan at the method level.
- Consider `@BatchSize` or `hibernate.default_batch_fetch_size` so Hibernate loads collections in batches, reducing round-trips where appropriate.
- Use DTOs/projections when only a subset of fields is needed for API responses or reports.

Do not apply collection fetch joins mechanically to paginated parent queries. Joining multiple children multiplies result rows, which can cause database pagination and the actual number of parents to mismatch expectations or force Hibernate to paginate in memory. For paginated screens, consider fetching the page of parent IDs first, then querying to fetch collections for that group of IDs, or using a suitable DTO query.

## 10. Saving and Updating Collections in a Transaction

Example of a service adding multiple items to an order:

```java
@Transactional
public void addItems(Long orderId, List<NewItemRequest> requests) {
    PurchaseOrder order = repository.findById(orderId)
        .orElseThrow(() -> new EntityNotFoundException("Order not found"));

    for (NewItemRequest request : requests) {
        PurchaseOrderItem item = new PurchaseOrderItem();
        item.setProductCode(request.productCode());
        item.setQuantity(request.quantity());
        order.addItem(item);
    }
}
```

Because `order` is managed, updating the owning side and having PERSIST cascade for new items will synchronize them on flush/commit. The service should validate the request, authorization, quantity limits, and business rules before adding items. If PERSIST cascade is not used, persist each item explicitly or use an appropriate repository.

For large collections, avoid loading all children just to add a single record if the use case does not need the collection. You can create the child and assign the managed parent directly via ManyToOne, then persist the child. This avoids the cost of loading the collection.

## 11. Deleting Parents and Children

When deleting a parent, the outcome depends on cascade, orphan removal, and FK constraints. If the collection uses `cascade = REMOVE` or orphanRemoval, Hibernate can delete the associated children before deleting the parent. Otherwise, the FK constraint may block the parent DELETE statement. For large datasets, deleting thousands of children through the ORM can consume significant memory and issue many statements; design controlled batch/delete queries and note that bulk JPQL deletes do not synchronize the persistence context.

Do not enable cascade REMOVE solely to avoid FK errors. First determine who owns the child's lifecycle and whether the child is referenced elsewhere. If the data must preserve history, consider soft delete or a business status instead of physical deletion.

## 12. Common Pitfalls and How to Diagnose Them

**Collection has elements, but FK is not written.** In a bidirectional relationship, check whether the ManyToOne owning side was set; helper methods must update both the collection and `child.parent`.

**Invalid `mappedBy`.** The `mappedBy` value must be the Java property name on the child Entity. Do not use the column name `purchase_order_id`.

**Unexpected join table generated.** Check whether a unidirectional OneToMany is missing `@JoinColumn`. JPA defaults to a join table for unidirectional mappings.

**Child removed, but row remains.** Check `orphanRemoval`, cascade, and the owning side; removing a child from the collection only triggers orphan deletion when the mapping is configured for it.

**Cannot unlink child due to NOT NULL FK.** Clarify whether the business rule is to delete the child, move it to another parent, or allow a nullable relationship. Align the mapping and migration consistently.

**Slow API responses or excessive SQL.** Inspect for N+1 queries, fetch plans, and serialization. Use DTOs/entity graphs/join fetch per use case.

**Serialization loops.** Avoid returning bidirectional Entities directly; create structured DTOs so parent and child do not serialize recursively.

## 13. @OneToMany Design Checklist

- Confirm whether the relationship is truly one parent to many children and whether children can exist independently.
- Choose unidirectional or bidirectional based on navigation needs.
- If bidirectional, place `@JoinColumn` on ManyToOne and set `mappedBy` to the exact property name on OneToMany.
- Create helper methods to keep both sides synchronized in memory.
- Choose cascade and orphanRemoval according to the data lifecycle.
- Match nullability, FK, unique constraints, and column names with migrations.
- Choose List/Set and an appropriate ordering rule.
- Verify LAZY loading, N+1, pagination, and DTO usage.
- Inspect the actual SQL generated when adding, updating, and deleting children.

`@OneToMany` describes the collection on the parent side; proper design also requires deciding where the foreign key lives, which side owns the relationship, the child's lifecycle, and how the collection is loaded. When these rules align with the schema and use cases, one-to-many relationships stay maintainable and avoid common ORM pitfalls.