# One-to-Many Mapping with @OneToMany

## 1. Meaning of a one-to-many relationship

A one-to-many relationship represents a parent Entity that can be associated with multiple child Entities. For example, an order `PurchaseOrder` has multiple order items `PurchaseOrderItem`, while each order item belongs to one order.

In the relational model, the common representation places the foreign key on the child table:

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

`@OneToMany` maps the collection on the parent side. It does not by itself decide which side writes the foreign key, whether children are deleted along with the parent, element ordering, or how the collection is loaded. Those decisions must be configured separately.

## 2. Common bidirectional mapping

For a schema with `purchase_order_item.purchase_order_id`, the standard pattern is a bidirectional relationship: the child Entity has `@ManyToOne` and the parent Entity has `@OneToMany(mappedBy = ...)`. Because the foreign key lives on the child table, ManyToOne is the owning side.

```java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = {CascadeType.PERSIST, CascadeType.MERGE},
        orphanRemoval = true
    )
    private List<PurchaseOrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {
    }

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
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "purchase_order_id", nullable = false)
    private PurchaseOrder purchaseOrder;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected PurchaseOrderItem() {
    }

    public void setPurchaseOrder(PurchaseOrder purchaseOrder) {
        this.purchaseOrder = purchaseOrder;
    }
}
```

This is the core mapping; a real application needs to add appropriate constructors, accessors, and business methods. `mappedBy = "purchaseOrder"` must match the exact Java property name in `PurchaseOrderItem`, not the column name `purchase_order_id`. `@JoinColumn` declares the physical column holding the foreign key.

## 3. Owning side and mappedBy

In the example above, `PurchaseOrderItem.purchaseOrder` is the owning side because it declares `@JoinColumn` and corresponds to the foreign key on the child table. `PurchaseOrder.items` is the inverse side because it declares `mappedBy`.

JPA relies on the owning side to write association changes to the database. Therefore, if you only call `order.getItems().add(item)` without assigning `item.setPurchaseOrder(order)`, the in-memory collection may contain the element, yet `purchase_order_id` still will not be written as expected.

In a bidirectional relationship, JPA does not automatically synchronize the two Java properties. Encapsulate add/remove operations in helper methods to update both sides. If an item already belongs to another order, business logic must decide whether to allow transferring the item or reject it; do not silently let an item appear in two parents' collections.

## 4. Unidirectional OneToMany mapping

If you only need to navigate from parent to child, you can declare `@OneToMany` without creating a back-reference property in the child Entity. There are two common ways to map this.

**Using a join table:** When a unidirectional OneToMany does not declare a join column, JPA typically uses a join table to store the association. You can explicitly declare the table name and the two columns:

```java
@OneToMany
@JoinTable(
    name = "purchase_order_item_link",
    joinColumns = @JoinColumn(name = "purchase_order_id"),
    inverseJoinColumns = @JoinColumn(name = "item_id", unique = true)
)
private List<PurchaseOrderItem> items = new ArrayList<>();
```

The join table holds foreign keys to the parent and child. The unique constraint on `item_id` ensures an item can be associated with at most one order in this model.

**Placing the foreign key on the child table:** You can declare `@JoinColumn` directly on the collection:

```java
@OneToMany
@JoinColumn(name = "purchase_order_id")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

In this unidirectional form, the collection is the side declaring the association; the child Entity does not need a `purchaseOrder` property. The `purchase_order_id` column still resides on the child table. Depending on the provider and mapping, saving may involve inserting the child and then updating the FK; inspect the actual SQL if write performance matters. If business logic frequently needs to navigate from child to parent, a bidirectional mapping with ManyToOne is usually clearer.

## 5. Cascade: which operations propagate to child Entities?

No cascade is enabled by default. Common cascade types:

| Cascade | Behavior |
| --- | --- |
| `PERSIST` | Persists related children when persisting the parent |
| `MERGE` | Merges related children when merging the parent |
| `REMOVE` | Deletes children when deleting the parent |
| `REFRESH` | Refreshes children when refreshing the parent |
| `DETACH` | Detaches children when detaching the parent |
| `ALL` | Includes all of the above |

Choose cascade according to the data lifecycle. If `PurchaseOrderItem` only exists as part of an order, PERSIST/MERGE may make sense. If a child can be shared or exist independently, do not cascade REMOVE indiscriminately.

Cascade does not change the owning side and does not automatically synchronize the two Java properties. `cascade = ALL` also does not mean every collection operation is safe; consider the impact of persist, merge, remove, and import flows.

## 6. orphanRemoval and removing elements from a collection

`orphanRemoval = true` instructs the provider to delete a child Entity when it is removed from an appropriate OneToMany or OneToOne relationship. In the bidirectional example, `removeItem` removes the item from the collection and sets the parent reference to null; on flush, the item is treated as an orphan and deleted.

Difference from cascade REMOVE:

- `cascade = REMOVE`: deleting the parent propagates to the children.
- `orphanRemoval = true`: deletes a child when it is removed from the relationship, even while the parent still exists.

Only use orphanRemoval when the child truly has its lifecycle owned by the parent. If you only want to unlink while keeping the child, do not enable orphanRemoval, and design a nullable foreign key or rules for transferring the child to another parent. With a `NOT NULL` FK, a child cannot be kept existing without a parent.

Orphan removal is an ORM semantic. It differs from database-executed `ON DELETE CASCADE`; the two mechanisms must be understood and configured separately.

## 7. Nullability and migrations

For a required relationship, `optional = false` on ManyToOne and `nullable = false` on JoinColumn describe the mapping. The schema also needs the corresponding FK and NOT NULL:

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

The DDL is illustrative; ID types and syntax may vary by database. Annotations do not automatically update schemas managed by Flyway or Liquibase. Migrations must create the exact column names, foreign keys, unique constraints, and nullability. When changing a mapping, provide the corresponding migration and verify existing data.

## 8. List, Set, and element ordering

`List` preserves order in memory, but does not automatically guarantee order when loaded from the database. `Set` represents a collection of unique elements according to `equals()`/`hashCode()`, so Entity equality must be designed carefully.

**Sorting by a property:**

```java
@OneToMany(mappedBy = "purchaseOrder")
@OrderBy("lineNumber ASC")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

`@OrderBy` sorts when loading the collection by the Java property `lineNumber`, not the physical column name.

**Persisting each element's position:**

```java
@OneToMany(mappedBy = "purchaseOrder")
@OrderColumn(name = "item_position")
private List<PurchaseOrderItem> items = new ArrayList<>();
```

`@OrderColumn` uses a dedicated column to store the position; the provider may have to update multiple positions when the list changes. Choose this approach when user-arranged ordering must be persisted durably. If no ordering is declared, do not rely on the result order returned from the database.

## 9. Lazy loading and N+1

`@OneToMany` defaults to LAZY in Jakarta Persistence. When loading a parent, the collection is not necessarily loaded yet. Accessing the collection inside a persistence context can trigger additional queries.

N+1 occurs when fetching N parents and then accessing each parent's collection, causing Hibernate to issue roughly N extra queries. For example, a page displaying 20 orders where each order needs its item list can generate one query for the orders plus many queries for the items.

Approaches depending on the use case:

- `JOIN FETCH` when you need to retrieve the parent along with its collection in a single query:

```java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.items
    where o.id = :id
    """)
Optional<PurchaseOrder> findWithItemsById(
    @org.springframework.data.repository.query.Param("id") Long id
);
```

- `@EntityGraph(attributePaths = "items")` when you want to declare a fetch plan on a repository method.
- `@BatchSize` or `hibernate.default_batch_fetch_size` to load collections in batches where appropriate.
- DTOs/projections when only part of the data is needed for display or API responses.

Do not mechanically apply a collection fetch join to paginated parent queries. Joining a collection multiplies result rows and can break expected pagination or force Hibernate to paginate in memory. A common pattern is to fetch the page of parent IDs first, then query to fetch collections for that batch of IDs.

## 10. Managing large collections

Do not load tens of thousands of children into a collection just to add one record. For large collections, you can query the managed parent, create the child, assign ManyToOne directly, and persist the child. This avoids initializing the entire collection when the use case only needs to write one additional child.

When batch processing is required, split into chunks and manage transactions, flush, and clear appropriately. `flush()` synchronizes pending changes with the database; `clear()` detaches Entities from the persistence context to limit memory usage. After `clear()`, do not continue treating old objects as managed.

With bulk JPQL delete/update, the persistence context does not automatically synchronize managed Entities. After a bulk operation, clear or refresh appropriately to avoid reading stale state.

## 11. Deleting parent and child

When deleting a parent, the outcome depends on cascade, orphanRemoval, and FKs. If remove is not cascaded and referencing children still exist, the database may reject deleting the parent due to the foreign key constraint. If cascade remove is enabled, Hibernate may issue delete statements for the children before the parent.

Do not enable cascade REMOVE just to bypass FK errors. First determine whether children are shared or need to preserve history. For business data that must be retained, consider an inactive status or soft delete instead of physical deletion.

## 12. Common issues and diagnosis

**Added to collection but FK did not change.** In a bidirectional mapping, update the ManyToOne owning side; use helper methods to synchronize both sides.

**`mappedBy` throws an error.** Check the Java property name in the child Entity; do not use the database column name.

**Unexpected join table appears.** Check for a unidirectional OneToMany without `@JoinColumn`; the default typically uses a join table.

**Cannot remove child.** Check whether the FK is NOT NULL, whether orphanRemoval is enabled, and whether the business logic intends to delete, transfer, or unlink.

**Too many queries generated.** Check for N+1, fetch plans, serialization, and how many collections are being initialized.

**Infinite recursion in JSON.** Do not serialize bidirectional Entities directly; create DTOs with an intentional data direction.

**Set loses elements or fails to deduplicate properly.** Check equals/hashCode, and avoid using mutable properties as identifiers while an Entity is in a Set.

## 13. @OneToMany design checklist

- Choose unidirectional or bidirectional based on navigation needs.
- Identify which table holds the FK and which property is the owning side.
- For bidirectional mappings, point `mappedBy` to the exact ManyToOne property.
- Create helper methods that update both the collection and the owning-side reference.
- Choose cascade and orphanRemoval based on child lifecycle.
- Align nullability, FKs, indexes, and migrations with the mapping.
- Choose List/Set, `@OrderBy`, or `@OrderColumn` based on ordering requirements.
- Verify LAZY, N+1, pagination, and DTOs.
- Observe SQL when adding, modifying, removing children, and deleting the parent.

`@OneToMany` is the way to represent a collection on the parent side. A good mapping must be consistent across the object graph, owning side, child lifecycle, and database foreign key structure. Designing around real use cases helps prevent association bugs and preserves performance as collections grow.