# Configuring `@MappedCollection` with `idColumn` and `keyColumn`

In **Spring Data Relational JDBC**, `@MappedCollection` describes how a collection belonging to an aggregate root is stored in a relational table. The two attributes `idColumn` and `keyColumn` determine the column names in the table of the referenced elements:

- **`idColumn`** is the column holding the ID of the entity owning the collection—typically the aggregate root. This is the foreign key linking the child row back to the parent row.
- **`keyColumn`** is the column holding the `Map` key or the element position in a `List`. For a `Set`, there is no collection key or position to store, so this attribute is normally omitted.

The two columns serve different roles. `idColumn` answers "which aggregate does this row belong to?", whereas `keyColumn` answers "which element is this row within that aggregate's collection?". `keyColumn` does not replace the child table's primary key; nor is `idColumn` the child entity's own ID.

## 1. `@MappedCollection` represents an ownership relationship inside an aggregate

Spring Data JDBC organizes data around the **aggregate root**. A collection declared with `@MappedCollection` is an ownership relationship: the elements belong to the root's aggregate and are persisted along with that aggregate's lifecycle.

Example of an order with multiple lines:

```text
PurchaseOrder (aggregate root)
  id = 101
  lines
    [0] OrderLine (id = 501, productId = 10, quantity = 2)
    [1] OrderLine (id = 502, productId = 15, quantity = 1)
```

In the database, the lines live in a separate table and have a column pointing back to the order:

```text
purchase_order
┌─────┐
│ id  │
├─────┤
│ 101 │
└─────┘

order_line
┌─────┬──────────┬─────────┬────────────┬──────────┐
│ id  │ order_id │ line_no │ product_id │ quantity │
├─────┼──────────┼─────────┼────────────┼──────────┤
│ 501 │ 101      │ 0       │ 10         │ 2        │
│ 502 │ 101      │ 1       │ 15         │ 1        │
└─────┴──────────┴─────────┴────────────┴──────────┘
```

In this example:

- `order_id` is **`idColumn`**: both lines belong to `PurchaseOrder.id = 101`.
- `line_no` is **`keyColumn`**: stores each element's position in `List<OrderLine>`.
- `order_line.id` is the child entity's own primary key, completely distinct from `order_id` and `line_no`.

`@MappedCollection` does not automatically turn a relationship between two aggregate roots into an ownership relationship. It is meant for elements inside an aggregate. If `OrderLine` references an independent aggregate root `Product`, typically store `productId` or `AggregateReference<Product, Long>` in the line; do not embed the entire `Product` aggregate into the order's collection.

## 2. Meaning of `idColumn`

`idColumn` is the column name in the **referenced table** used to store the ID of the entity containing the collection property. For `PurchaseOrder.lines`, the `order_id` column in the `order_line` table holds the value of `PurchaseOrder.id`.

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();
}
```

Here Spring Data JDBC understands that `OrderLine` rows are attached to `PurchaseOrder` through the `order_id` column. The `order_id` property does not need to appear as an ordinary field in the `OrderLine` class; the framework manages the link column from collection metadata.

### Things to keep accurate for `idColumn`

1. The column must exist in the table used to store the collection's elements.
2. The column's data type must be compatible with the owning entity's ID type. If `PurchaseOrder.id` is `BIGINT`, `order_line.order_id` should also be `BIGINT`.
3. The column name must match the actual schema, even if the application's naming strategy uses different conventions.
4. In schemas with relational constraints, the column should normally have a foreign key referencing the root's primary key.
5. If a child entity has its own collection, the child collection's `idColumn` points to the ID of the entity directly owning that collection, not by default to the top-level root.

`idColumn` is not the ID column name of the child itself. For example, `order_line.id` can still be the primary key, while `order_line.order_id` is the foreign key back to `purchase_order.id`.

## 3. Meaning of `keyColumn`

`keyColumn` stores element-locating information in the collection when the collection type is ordered or keyed:

| Property type | Value stored in `keyColumn` | Is `keyColumn` needed? |
|---|---|---|
| `List<T>` | Index/position of the element in the list | Useful to store and restore order |
| `Map<K, V>` | Key `K` corresponding to value `V` | Yes, to restore key/value pairs |
| `Set<T>` | No key or stable position per `Set`'s contract | Normally no |

The `keyColumn` name is configured on the collection property. Example:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "line_no")
private List<OrderLine> lines;
```

In the `order_line` table, the `line_no` column stores the element's position. If `keyColumn` is omitted, Spring Data Relational uses `NamingStrategy`'s default naming rules; if the schema is managed independently by the team or requires stable column names, configure it explicitly.

For `Map`, the key is stored in a dedicated column. For example, an order has named extended attributes:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "attribute_name")
private Map<String, OrderAttribute> attributes = new LinkedHashMap<>();
```

`attribute_name` holds keys like `"giftMessage"`, while the properties of `OrderAttribute` map to other data columns in the child table.

**Note:** avoid generic column names like `key` if the database may treat it as a reserved keyword or if it is easily confused with the primary key. Names like `line_no`, `attribute_name`, or `locale_code` express the meaning much more clearly.

## 4. Complete example with `List<OrderLine>`

### Aggregate root

```java
package com.example.sales;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public void addLine(Long productId, int quantity) {
        if (productId == null || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
        lines.add(new OrderLine(productId, quantity));
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }

    public Long getId() {
        return id;
    }
}
```

### Child entity

```java
package com.example.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_line")
public class OrderLine {

    @Id
    private Long id;

    @Column("product_id")
    private Long productId;

    private int quantity;

    protected OrderLine() {}

    public OrderLine(Long productId, int quantity) {
        this.productId = productId;
        this.quantity = quantity;
    }

    public Long getId() { return id; }
    public Long getProductId() { return productId; }
    public int getQuantity() { return quantity; }
}
```

`OrderLine` does not declare an `orderId` property. `@MappedCollection` on the root already tells Spring Data JDBC how to store the foreign key and list position. Adding a regular `orderId` property to the child without clear mapping risks creating a second data column or causing the mapping to stop reflecting ownership properly.

### Repository

```java
package com.example.sales;

import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {}
```

Using the repository through the aggregate root:

```java
PurchaseOrder order = new PurchaseOrder();
order.addLine(10L, 2);
order.addLine(15L, 1);

PurchaseOrder saved = purchaseOrderRepository.save(order);

PurchaseOrder loaded = purchaseOrderRepository.findById(saved.getId())
        .orElseThrow();

List<OrderLine> lines = loaded.getLines();
```

When saving the root, Spring Data JDBC uses the collection mapping to write the lines belonging to the aggregate. When loading the root, the framework uses `order_id` to find the child rows and `line_no` to restore the `List` order.

## 5. Corresponding SQL schema

Example DDL for PostgreSQL:

```sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_order(id),
    CONSTRAINT uk_order_line_position
        UNIQUE (order_id, line_no)
);

CREATE INDEX idx_order_line_order_id
    ON order_line(order_id);
```

How the elements match the annotations:

| Annotation | SQL column | Role |
|---|---|---|
| `idColumn = "order_id"` | `order_line.order_id` | ID of the `PurchaseOrder` owning the collection |
| `keyColumn = "line_no"` | `order_line.line_no` | Element position in `List<OrderLine>` |
| `@Id` on `OrderLine` | `order_line.id` | Child's own primary key |
| `@Column("product_id")` | `order_line.product_id` | Value of the `productId` property |

The `UNIQUE(order_id, line_no)` constraint prevents one order from having two elements at the same position. This is an illustrative schema constraint; choose constraints suited to your data rules and actual database. If multiple transactions modify the same aggregate, transactions and optimistic locking on the root still need to be designed separately.

`@MappedCollection` **does not create tables or migrations**. The schema must be managed via migrations (Flyway/Liquibase) or appropriate scripts. The annotation describes how mapping works; the DDL must actually contain the declared columns.

## 6. Example of `Map<String, OrderAttribute>` with `keyColumn`

A `Map` stores both the root's ID and the entry's key. For example, an order has named metadata:

```java
package com.example.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("order_attribute")
public class OrderAttribute {

    @Id
    private Long id;

    private String value;

    protected OrderAttribute() {}

    public OrderAttribute(String value) {
        this.value = value;
    }

    public Long getId() { return id; }
    public String getValue() { return value; }
}
```

In the root:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "attribute_name")
private Map<String, OrderAttribute> attributes = new LinkedHashMap<>();
```

Sample data:

```text
PurchaseOrder.id = 101

attributes:
  "giftMessage" -> OrderAttribute(value = "Happy birthday")
  "channel"     -> OrderAttribute(value = "web")
```

The `order_attribute` table might look like:

| id | order_id | attribute_name | value |
|---:|---:|---|---|
| 801 | 101 | `giftMessage` | `Happy birthday` |
| 802 | 101 | `channel` | `web` |

Illustrative DDL:

```sql
CREATE TABLE order_attribute (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    attribute_name VARCHAR(100) NOT NULL,
    value VARCHAR(500),
    CONSTRAINT uk_order_attribute_name UNIQUE (order_id, attribute_name)
);
```

Here `attribute_name` is the `Map` key, not the `value` property of `OrderAttribute`. If the key is an enum, determine how the enum is represented in the database (usually string name or a converter) and pick the corresponding column type.

## 7. `Set` does not need `keyColumn`

If the collection needs neither ordering nor keys, use `Set` and declare only `idColumn`:

```java
@MappedCollection(idColumn = "order_id")
private Set<OrderTag> tags = new LinkedHashSet<>();
```

Example `order_tag` table:

```sql
CREATE TABLE order_tag (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES purchase_order(id),
    tag_name VARCHAR(80) NOT NULL,
    UNIQUE (order_id, tag_name)
);
```

Do not declare `keyColumn` for a `Set` expecting it to produce a stable ordering. `Set` has no index; if ordering carries business meaning, use `List` with an appropriate `keyColumn`. If named keys are needed, use `Map`.

## 8. Nested collections: `idColumn` points to the direct owning entity

An aggregate can contain multiple levels of child entities:

```text
PurchaseOrder (id = 101)
  └── OrderLine (id = 501)
        └── LineNote (id = 901)
```

When `OrderLine` owns `List<LineNote>`, the `notes` collection is mapped by `OrderLine`'s ID, not `PurchaseOrder`'s ID:

```java
@Table("order_line")
public class OrderLine {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_line_id", keyColumn = "note_no")
    private List<LineNote> notes = new ArrayList<>();
}
```

Corresponding DDL:

```sql
CREATE TABLE line_note (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_line_id BIGINT NOT NULL REFERENCES order_line(id),
    note_no INTEGER NOT NULL,
    text VARCHAR(500) NOT NULL,
    UNIQUE (order_line_id, note_no)
);
```

`order_line_id` connects the note to `OrderLine.id`. The fact that the note indirectly belongs to the order via `OrderLine` does not change this collection's direct relationship. This rule is crucial when naming FKs in multi-level aggregates.

## 9. Default naming rules and when explicit declaration is needed

If `idColumn` or `keyColumn` is omitted, Spring Data Relational uses `NamingStrategy` to derive column names from the mapping metadata. Specific rules can be customized in configuration. Therefore:

- If the schema is built following the application's default conventions, you can let the framework derive the names.
- If the schema is managed independently, pre-existing, or uses explicit business column names, declare `idColumn`/`keyColumn` explicitly to avoid name mismatches.
- If using a custom `NamingStrategy`, understand how it names collection FK and key columns; explicit annotations help document the contract on the property.
- Column names in the annotation must be valid **SQL identifiers** for the database. Do not pass a table name, Java property name, or SQL expression.

Good example:

```java
@MappedCollection(idColumn = "purchase_order_id", keyColumn = "line_position")
private List<OrderLine> lines;
```

Example to avoid:

```java
// Ambiguous names, prone to colliding with reserved words or obscuring the schema
@MappedCollection(idColumn = "id", keyColumn = "key")
private List<OrderLine> lines;
```

`idColumn = "id"` is only valid if the child table truly has a column named `id` used to reference the root. In most schemas where the child has its own primary key, the FK column should have a distinct name like `order_id`.

## 10. Reordering a `List` and key stability

With `List`, `keyColumn` stores the element position. If an element is inserted in the middle or the list is reordered, the positions of subsequent elements can change when the aggregate is saved. Therefore:

- Do not treat `line_no` as the stable ID of an `OrderLine`.
- Do not use the list index as an external identifier or as a foreign reference key from another aggregate.
- If an order line needs a stable reference, use `OrderLine.id`.
- If order has business meaning, update the list through the root so ordering changes deliberately.
- If you need a display sequence number that stays unchanged when lines are added/removed, make that a separate domain property (`displaySequence`) rather than the collection position.

`keyColumn` stores the collection structure; it does not automatically represent every concept of business ordering. Distinguish the internal index from user-visible sequence numbers.

## 11. Common configuration errors

| Symptom | Possible cause | How to resolve |
|---|---|---|
| SQL reports `order_id` not found | `idColumn` does not match the actual FK column | Inspect child table DDL and the annotation on the collection property |
| FK has wrong value or mismatches root | Incompatible column type or ID mapping | Check root ID, FK data type, and schema relationship |
| List loads in wrong order | Missing/wrong `keyColumn`, or incorrect index column | Point `keyColumn` to the position-storing column; inspect existing data |
| Map loses keys or fails to restore entries | Key column missing or wrong type mapping | Configure `keyColumn`, check key type and converters if needed |
| Two elements have duplicate position/key | Missing unique constraint or invalid data written | Consider `UNIQUE(idColumn, keyColumn)` for List/Map per schema |
| Child has an extra unnecessary parent column | Using both `@MappedCollection` and a separately mapped parent property | Choose one clear ownership mechanism; normally let the framework manage the collection FK |
| `Set` has unexpected order | Using a collection with no ordering semantics | Use `List` with `keyColumn` if ordering is required |
| Nested collection links to wrong root | Using top-level root ID instead of direct owner ID | Set `idColumn` according to the entity owning that collection property |
| Schema migration succeeds but save fails | Annotation and DDL have diverged | Synchronize names, types, nullability, FKs, and constraints |

When troubleshooting errors, check in order: collection property in root → `@MappedCollection` → child table name → FK/key columns in DDL → ID types → data/constraints. Enabling SQL logging in development also helps identify which columns Spring Data is actually using.

## 12. Observing SQL and testing the mapping

You can enable JDBC logging in development/test environments:

```yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
```

After saving an order with two lines, run an inspection query:

```sql
SELECT id, order_id, line_no, product_id, quantity
FROM order_line
WHERE order_id = :orderId
ORDER BY line_no;
```

What the results should verify:

- All child rows have `order_id` equal to the aggregate root's ID.
- The `line_no` values allow restoring the list order.
- The child's `id` is its own key, not confused with `order_id` or `line_no`.
- Data read back through the repository retains the expected elements and order.

An integration test should save the root, read it back, and assert that the list/map is restored. If using `@DataJdbcTest`, ensure the test schema has all `idColumn`, `keyColumn`, foreign key, and related constraint columns. When production uses PostgreSQL/MySQL/Oracle, run tests against the same engine via Testcontainers; H2 does not always reflect SQL, identifier, and constraint differences of the real database.

## 13. Choosing `idColumn` and `keyColumn` by use case

| Domain need | Suggested declaration | Child table structure |
|---|---|---|
| Root owns an ordered list of lines | `@MappedCollection(idColumn = "order_id", keyColumn = "line_no")` | `order_id` + `line_no` + line columns |
| Root owns a map keyed by attribute name | `@MappedCollection(idColumn = "order_id", keyColumn = "attribute_name")` | `order_id` + `attribute_name` + value columns |
| Root owns an unordered set of elements | `@MappedCollection(idColumn = "order_id")` | `order_id` + element columns |
| Child owns a deeper nested list | `@MappedCollection(idColumn = "order_line_id", keyColumn = "note_no")` | `order_line_id` + `note_no` + note content |
| Reference an independent aggregate root | Use ID/`AggregateReference`, do not use `@MappedCollection` | ID column referencing the other root; independent lifecycle |

When designing the schema, adopt a consistent naming convention: `<owner>_id` for `idColumn`, and `<child>_position` or a business name for `keyColumn`. Consistent naming helps anyone reading the SQL understand the relationship without even opening the Java classes.

## Official References

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): collection, entity, and aggregate relationship mapping.
- [Spring Data Relational — `MappedCollection` API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/mapping/MappedCollection.html): meaning of `idColumn` and `keyColumn`.
- [Spring Data JDBC — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): how Spring Data JDBC persists aggregates and owned entities.
- [Spring Data Relational — `NamingStrategy` API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/mapping/NamingStrategy.html): rules for deriving table/column names.
