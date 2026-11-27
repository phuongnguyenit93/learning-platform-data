# @Embedded Mapping and the prefix Option

In **Spring Data Relational JDBC**, a Java object does not have to correspond to a separate table. Some objects simply describe a group of properties that belong together conceptually, such as a billing address, shipping address, contact details, or an effective date range. You can embed those properties into the same row as the aggregate root using the **`@Embedded`** annotation.

`@Embedded` enables Spring Data JDBC to map a child object's properties to columns on the table containing the parent object. The **`prefix`** attribute prepends a prefix to the mapped column names, which is very useful when a table holds multiple embedded objects of the same type or when column name collisions could occur.

For example, an order has two addresses:

```text
PurchaseOrder
  id
  orderNumber
  billingAddress
    street
    city
    postalCode
  shippingAddress
    street
    city
    postalCode
```

These can be stored in **one table** with the columns:

```text
purchase_orders
  id
  order_number
  billing_street
  billing_city
  billing_postal_code
  shipping_street
  shipping_city
  shipping_postal_code
```

You do not need to create an `addresses` table and foreign keys just to store these two value groups. That is the core idea of an *embedded object*: the object is preserved in the domain model, while its fields are *flattened* into the containing table's row.

## 1. What Is an Embedded Object?

An embedded object is usually a **value object**: a group of properties describing a value in the context of its owning object. For example:

- `Address` describes an address, consisting of street, city, and postal code.
- `Money` describes a monetary amount and currency.
- `ContactInfo` describes an email and phone number.
- `Dimensions` describes length, width, and height.

These properties generally do not have a lifecycle independent of the aggregate root. If the order is deleted, the billing address stored directly in the order row disappears along with that row.

### 1.1. Embedded vs. Entity Relationships and Foreign Keys

**Embedded: columns reside in the same table**

```text
purchase_orders
+----+-------------+----------------+-------------+
| id | order_no    | billing_street | billing_city|
+----+-------------+----------------+-------------+
| 42 | ORD-0042    | 12 Nguyen Hue  | Ho Chi Minh |
+----+-------------+----------------+-------------+
```

**Separate relation: child table and foreign key**

```text
purchase_orders                 addresses
+----+-------------+-----------+   +----+---------------+-------------+
| id | order_no    | address_id|   | id | street        | city        |
+----+-------------+-----------+   +----+---------------+-------------+
| 42 | ORD-0042    | 9         |   | 9  | 12 Nguyen Hue | Ho Chi Minh |
+----+-------------+-----------+   +----+---------------+-------------+
```

| Criterion | `@Embedded` | Separate Entity / Table |
|---|---|---|
| Storage location | Columns in the containing table | Rows in another table |
| Independent identity | Usually none | Usually has a primary key |
| Querying | Read in the same row, no JOIN needed just for the embedded object | May require a JOIN or separate query |
| Lifecycle | Usually owned by the parent object | Can exist independently or be referenced from multiple places |
| Best suited for | Value objects, property groups belonging to an aggregate | Entities with independent identity/lifecycle referenced by multiple objects |

Do not choose `@Embedded` merely to reduce the number of tables. If an address has its own ID, is shared by multiple orders, tracks change history, or is managed independently, a separate table model may be more appropriate.

## 2. Basic Example with @Embedded

Suppose a sales application has `PurchaseOrder` and `Address`. The address is stored as part of the order.

### 2.1. Declaring the Value Object

```java
public record Address(
    String street,
    String city,
    String postalCode
) {}
```

`Address` is a Java record and does not need `@Id` because it has no independent identity in this example. It also does not need its own table.

### 2.2. Embedding into the Aggregate Root

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
    @Id Long id,
    String orderNumber,

    @Embedded(prefix = "billing_")
    Address billingAddress
) {}
```

`@Embedded` marks `billingAddress` as an embedded object. The `billing_` prefix is prepended to the column names mapped from properties inside `Address`.

With Spring Data Relational's common naming strategy:

| Java Property | Mapped Column Name |
|---|---|
| `billingAddress.street` | `billing_street` |
| `billingAddress.city` | `billing_city` |
| `billingAddress.postalCode` | `billing_postal_code` |

The prefix is provided verbatim as a string; if you want an underscore separator, include the underscore in the prefix value such as `"billing_"`. Do not assume the framework inserts separators for you automatically.

### 2.3. Corresponding SQL Schema

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    billing_street VARCHAR(200),
    billing_city VARCHAR(100),
    billing_postal_code VARCHAR(20)
);
```

There is no `addresses` table in this schema. The columns `billing_street`, `billing_city`, and `billing_postal_code` belong to `purchase_orders`.

A save operation:

```java
PurchaseOrder order = new PurchaseOrder(
    null,
    "ORD-0042",
    new Address(
        "12 Nguyen Hue",
        "Ho Chi Minh City",
        "700000"
    )
);

PurchaseOrder saved = repository.save(order);
```

In SQL terms, the operation may correspond to a single INSERT into the root table:

```sql
INSERT INTO purchase_orders (
    order_number,
    billing_street,
    billing_city,
    billing_postal_code
)
VALUES (?, ?, ?, ?);
```

The exact SQL statement depends on dialect, ID generation strategy, mapping, and framework version. What matters is that the embedded object's fields are written into columns of the **same row**.

## 3. What Is prefix Used For?

Prefix provides two common benefits:

1. Avoiding column name collisions between properties of the parent object and the embedded object.
2. Allowing multiple properties of the same type to be embedded into one table with distinct column names.

### 3.1. Avoiding Column Name Collisions

Suppose an order has its own `city` property representing the city where the order was created, alongside `billingAddress.city`.

Without a prefix, both properties could try to map to the `city` column. That structure causes a collision and fails to express clear meaning.

Using a prefix:

```java
@Table("purchase_orders")
public record PurchaseOrder(
    @Id Long id,
    String orderNumber,
    String city,

    @Embedded(prefix = "billing_")
    Address billingAddress
) {}
```

Schema:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    city VARCHAR(100),
    billing_street VARCHAR(200),
    billing_city VARCHAR(100),
    billing_postal_code VARCHAR(20)
);
```

Now:

- `city` is the city directly attached to the order.
- `billing_city` is the city within the billing address.

Column names convey the right context and no longer collide.

### 3.2. Embedding Two Objects of the Same Address Type

An order can have both a billing address and a shipping address:

```java
@Table("purchase_orders")
public record PurchaseOrder(
    @Id Long id,
    String orderNumber,

    @Embedded(prefix = "billing_")
    Address billingAddress,

    @Embedded(prefix = "shipping_")
    Address shippingAddress
) {}
```

Corresponding schema:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,

    billing_street VARCHAR(200),
    billing_city VARCHAR(100),
    billing_postal_code VARCHAR(20),

    shipping_street VARCHAR(200),
    shipping_city VARCHAR(100),
    shipping_postal_code VARCHAR(20)
);
```

Both properties share the same Java type `Address`, yet are stored in two separate column groups.

| Java Property | SQL Column |
|---|---|
| `billingAddress.street` | `billing_street` |
| `billingAddress.city` | `billing_city` |
| `billingAddress.postalCode` | `billing_postal_code` |
| `shippingAddress.street` | `shipping_street` |
| `shippingAddress.city` | `shipping_city` |
| `shippingAddress.postalCode` | `shipping_postal_code` |

There is no need to create two types `BillingAddress` and `ShippingAddress` just because the column names differ. Prefixes allow reusing the same value object across multiple contexts.

### 3.3. Prefixes Also Make Schemas Easier to Read

A table can hold multiple embedded property groups:

```text
purchase_orders
├── id
├── order_number
├── billing_street
├── billing_city
├── billing_postal_code
├── shipping_street
├── shipping_city
├── shipping_postal_code
├── contact_email
└── contact_phone
```

Looking at the column names, readers can easily recognize which columns belong to billing, shipping, or contact. That is a schema design benefit beyond avoiding name collisions.

## 4. The prefix Option and Actual Column Names

The `prefix` attribute of `@Embedded` is a prefix applied when mapping the columns of the embedded object. It is not a table name and does not create a new relationship.

Example:

```java
@Embedded(prefix = "shipping_")
Address shippingAddress
```

If `Address` has properties `street`, `city`, and `postalCode`, the column names under the common naming strategy will be:

```text
shipping_street
shipping_city
shipping_postal_code
```

### 4.1. Choosing Meaningful Prefixes

| Context | Suggested Prefix |
|---|---|
| Billing address | `billing_` |
| Shipping address | `shipping_` |
| Contact address | `contact_` |
| Recipient | `recipient_` |
| Validity period | `validity_` |
| Delivery coordinates | `location_` |

Prefix names should be short, consistent, and reflect the business meaning. Avoid generic prefixes like `a_` or `obj2_` because they make the schema hard to understand.

### 4.2. Empty Prefix

If you embed only one object and there is no risk of collision, you can use the default prefix:

```java
@Embedded
Address address
```

In that case, the columns are typically mapped as `street`, `city`, and `postal_code` according to the naming strategy.

However, if the table has properties with the same names or might later add another object of the same type, an explicit prefix keeps the schema stable and more readable. Changing a prefix after data has been stored is a schema change requiring migration.

### 4.3. Combining with @Column

When column names must be specified explicitly, `@Column` can be placed on properties of the embedded type:

```java
import org.springframework.data.relational.core.mapping.Column;

public record Address(
    @Column("street_name") String street,
    @Column("city_name") String city,
    String postalCode
) {}
```

With a prefixed embedded field:

```java
@Embedded(prefix = "billing_")
Address billingAddress
```

The mapping target is columns reflecting the billing context, such as `billing_street_name` and `billing_city_name`, along with the postal code column according to mapping conventions. When combining a prefix with custom column names, verify the actual column names produced by your project's version and naming strategy, then declare the DDL accordingly. Do not let annotations and migrations describe two different schemas.

## 5. Empty Embedded Objects and the onEmpty Option

An important question: if all columns of an embedded object are `NULL`, should Spring Data JDBC materialize the property as `null` or create an object whose internal properties are null?

Row example:

```text
id = 42
order_number = ORD-0042
billing_street = NULL
billing_city = NULL
billing_postal_code = NULL
```

There are two interpretations:

- No billing address exists: `billingAddress == null`.
- An address object exists, but all of its fields are empty: `billingAddress != null`, with all internal properties null.

Spring Data Relational provides the `onEmpty` option on `@Embedded` to choose how to handle the case where **all columns of the embedded object are null**.

### 5.1. USE_NULL

```java
import static org.springframework.data.relational.core.mapping.Embedded.OnEmpty.USE_NULL;

@Embedded(prefix = "billing_", onEmpty = USE_NULL)
Address billingAddress
```

With `USE_NULL`, when all columns mapped from the embedded object are null, the property is restored as `null`.

This fits when the object is genuinely optional: an order without a billing address yet has no `billingAddress`.

### 5.2. USE_EMPTY

```java
import static org.springframework.data.relational.core.mapping.Embedded.OnEmpty.USE_EMPTY;

@Embedded(prefix = "billing_", onEmpty = USE_EMPTY)
Address billingAddress
```

With `USE_EMPTY`, when all columns are null, Spring Data JDBC constructs an empty embedded object according to the mapping instead of setting the property to null.

This fits when the domain wants a value object to always be present, even if its properties have not been populated yet.

### 5.3. Choosing Semantics Based on the Domain

| Column State | `USE_NULL` | `USE_EMPTY` |
|---|---|---|
| All NULL | Property is `null` | Property is an empty object |
| At least one non-NULL value | Object is created and fields mapped | Object is created and fields mapped |
| Input object is null on write | Embedded columns written in null state | Embedded columns written in null state; on read, `onEmpty` decides how to build the object |

`onEmpty` matters most on the **read path**: the database stores columns and has no separate column to distinguish "null object" from "existing object whose properties are all null". Since both states are persisted as the same set of NULL columns, `onEmpty` determines how the object is reconstructed.

### 5.4. Notes on Null

- If an embedded object has one non-null field and other fields null, it is still an object with data; `onEmpty` does not turn it into null just because some columns are null.
- Only when all embedded columns are null does `onEmpty` decide the outcome.
- Use wrapper types such as `Integer` or `Long` instead of primitives if an embedded property needs to represent SQL NULL.
- If the schema declares `NOT NULL` on all embedded columns, the all-NULL state cannot exist through normal INSERT/UPDATE statements. Ensure DDL nullability aligns with the object model.
- `USE_EMPTY` does not replace business validation. An empty created object may still be invalid for billing or shipping.

## 6. Full Example: BillingAddress and ShippingAddress

Let us build an order aggregate with two embedded addresses. The goal is to clearly see how Java objects, annotations, schema, and repository fit together.

### 6.1. Value Object

```java
public record Address(
    String street,
    String city,
    String postalCode
) {}
```

This is a simple value object with no independent ID.

### 6.2. Aggregate Root

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

import static org.springframework.data.relational.core.mapping.Embedded.OnEmpty.USE_NULL;

@Table("purchase_orders")
public record PurchaseOrder(
    @Id Long id,
    String orderNumber,

    @Embedded(prefix = "billing_", onEmpty = USE_NULL)
    Address billingAddress,

    @Embedded(prefix = "shipping_", onEmpty = USE_NULL)
    Address shippingAddress
) {}
```

`billingAddress` and `shippingAddress` both use the `Address` type, but each property has its own prefix.

### 6.3. Schema

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,

    billing_street VARCHAR(200),
    billing_city VARCHAR(100),
    billing_postal_code VARCHAR(20),

    shipping_street VARCHAR(200),
    shipping_city VARCHAR(100),
    shipping_postal_code VARCHAR(20)
);
```

The address columns are nullable because an order may not yet have one of the two addresses. If business rules require addresses before confirmation, the service can check that condition during the order confirmation step; or the schema can be designed with appropriate constraints if every row state must have an address.

### 6.4. Repository

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

### 6.5. Creating an Order

```java
Address billing = new Address(
    "12 Nguyen Hue",
    "Ho Chi Minh City",
    "700000"
);

Address shipping = new Address(
    "25 Le Loi",
    "Ho Chi Minh City",
    "700000"
);

PurchaseOrder order = new PurchaseOrder(
    null,
    "ORD-0042",
    billing,
    shipping
);

PurchaseOrder saved = repository.save(order);
```

An SQL row can be inserted with the columns:

```sql
INSERT INTO purchase_orders (
    order_number,
    billing_street,
    billing_city,
    billing_postal_code,
    shipping_street,
    shipping_city,
    shipping_postal_code
)
VALUES (?, ?, ?, ?, ?, ?, ?);
```

No INSERT into an `addresses` table is needed because no such table exists in the schema.

### 6.6. Reading Back

```java
PurchaseOrder loaded = repository.findById(saved.id())
    .orElseThrow();

System.out.println(loaded.billingAddress().city());
System.out.println(loaded.shippingAddress().street());
```

Spring Data JDBC reads the columns of the `purchase_orders` row and constructs the two `Address` objects according to the mapping. Prefixes identify which columns belong to the billing address and which belong to the shipping address.

## 7. What Data Types Can an Embedded Object Contain?

Properties of an embedded type are mapped according to the standard mapping rules of Spring Data Relational. They can be simple types supported by JDBC converters, for example:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record PaymentTerms(
    Integer dueInDays,
    LocalDate dueDate,
    BigDecimal creditLimit,
    String note
) {}
```

Embedding into the aggregate:

```java
@Table("purchase_orders")
public record PurchaseOrder(
    @Id Long id,
    String orderNumber,

    @Embedded(prefix = "terms_")
    PaymentTerms paymentTerms
) {}
```

Illustrative schema:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    terms_due_in_days INTEGER,
    terms_due_date DATE,
    terms_credit_limit NUMERIC(19, 2),
    terms_note VARCHAR(500)
);
```

`PaymentTerms` still has no separate table. Its fields are flattened into the orders table with the `terms_` prefix.

### 7.1. Embedded Is Not a Place for Arbitrary Relationships

If a property inside an embedded object is itself an entity with an ID and separate table, carefully review the relationship model and Spring Data JDBC aggregate rules. `@Embedded` is meant to describe properties residing in the same row, not a general mechanism for stuffing arbitrary object graphs into one table.

Keep embedded objects simple, value-oriented, and containing only properties appropriate for mapping to columns of the owning row.

## 8. Querying Embedded Object Columns

Because embedded properties are stored as ordinary columns, you can query them with SQL using their mapped column names.

For example, finding orders by shipping city:

```sql
SELECT id, order_number,
       billing_city, shipping_city
FROM purchase_orders
WHERE shipping_city = 'Ho Chi Minh City'
ORDER BY id;
```

If using a repository query with declared SQL:

```java
import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, order_number,
               billing_street, billing_city, billing_postal_code,
               shipping_street, shipping_city, shipping_postal_code
        FROM purchase_orders
        WHERE shipping_city = :city
        ORDER BY id
        """)
    List<PurchaseOrder> findByShippingCity(String city);
}
```

When mapping results to `PurchaseOrder`, the query must return all columns needed to construct the aggregate per its mapping. Omitting embedded columns from `SELECT` can lead to missing data or failure to satisfy the expected entity structure.

### 8.1. Derived Queries and Property Paths

In appropriate cases, Spring Data can parse property paths to derive queries for nested properties. Conceptual example:

```java
List<PurchaseOrder> findByBillingAddress_City(String city);
```

The method name uses the property path `billingAddress.city`. Property path separator syntax must follow Spring Data's parser rules; if property names could be ambiguous, use explicit underscore syntax or `@Query` to keep the query unambiguous. Verify the parsing capabilities of the version in use rather than assuming all nested paths are supported identically across every repository and query type.

## 9. Embedded Objects and Schema Migrations

The `@Embedded` annotation describes Java mapping; it does not replace schema management. When changing a prefix, property name, or embedded type structure, the database columns must be updated accordingly.

Initial example:

```java
@Embedded(prefix = "billing_")
Address billingAddress
```

Columns:

```text
billing_street
billing_city
billing_postal_code
```

Later changing the prefix to `invoice_address_`:

```java
@Embedded(prefix = "invoice_address_")
Address billingAddress
```

The new mapping looks for columns:

```text
invoice_address_street
invoice_address_city
invoice_address_postal_code
```

If the database still only has the old columns, querying or saving data may fail or mapping will not work as expected. A corresponding migration is required:

```sql
ALTER TABLE purchase_orders
    RENAME COLUMN billing_street TO invoice_address_street;

ALTER TABLE purchase_orders
    RENAME COLUMN billing_city TO invoice_address_city;

ALTER TABLE purchase_orders
    RENAME COLUMN billing_postal_code TO invoice_address_postal_code;
```

In production environments with live data, renaming columns requires a compatibility plan for running application versions, migration rollbacks, and legacy data. Do not rename a prefix purely for cosmetic reasons without a business or schema justification.

### 9.1. Adding a New Property to an Embedded Type

Adding `countryCode`:

```java
public record Address(
    String street,
    String city,
    String postalCode,
    String countryCode
) {}
```

The schema needs new columns:

```sql
ALTER TABLE purchase_orders
    ADD COLUMN billing_country_code VARCHAR(2),
    ADD COLUMN shipping_country_code VARCHAR(2);
```

If the new column is required, examine existing data and backfill strategies before setting `NOT NULL`. Adding a property in Java without updating the schema will cause a mapping mismatch.

### 9.2. Switching from Embedded to a Separate Table

If an address needs its own identity and lifecycle, moving from embedded to a separate-table entity is a significant domain and schema change:

- Create the address table.
- Define foreign keys and cardinality.
- Migrate data from prefixed columns into the new table.
- Update Java mappings, repositories, and services.
- Update queries, migrations, and integration tests.

Do not make this change by merely removing `@Embedded` and adding `@Table`; redesign the aggregate boundaries and data migration path properly.

## 10. Limitations and Design Considerations

### 10.1. Embedded Objects Have No Separate ID

An embedded `Address` has no independent database identity in this model. Do not use `@Id` to turn it into an independent entity if the goal is to keep it as a value object inside the same row.

### 10.2. Reading Embedded Objects Does Not Create a JOIN

Because the columns already live in the parent table's row, reading `PurchaseOrder` retrieves address data in the same `SELECT`. This differs from a relationship between two tables that requires extra queries or a `JOIN`.

### 10.3. Many Columns Make the Table Wider

If you embed many objects with numerous properties, the table can become quite wide. That is not automatically a problem, but consider:

- Are all these properties frequently read together with the aggregate?
- Do they share the same lifecycle as the aggregate root?
- Are there many nullable columns because the object is often absent?
- Do you need to search or index on several embedded properties?
- Does the object need to be shared across multiple aggregates?

If many objects have independent lifecycles or are rarely read together, a separate table may be a better fit.

### 10.4. Nullability Must Be Consistent

If `billingAddress` can be null, the billing columns must allow null. If the object is required, ensure valid data before writing and consider database constraints if the schema can express that rule.

For `USE_EMPTY`, understand that an empty object can still be constructed when all columns are null. Do not use primitives for properties that need to preserve SQL NULL states, because Java primitives cannot hold null.

### 10.5. Prefix Is Part of the Mapping Contract

The prefix is used on both reads and writes. Changing a prefix is equivalent to renaming columns, so it must be managed alongside migrations, raw SQL, indexes, and other queries. Do not let column names in code, schema, and queries evolve independently.

## 11. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| Column not found when reading aggregate | Prefix in annotation does not match DDL | Verify column names after applying the naming strategy |
| Two properties try to use the same column | Missing prefix or insufficiently distinct prefixes | Assign a distinct prefix to each embedded property |
| Embedded object reads back as null | All object columns are NULL and `onEmpty` uses `USE_NULL` | Check data and choose appropriate semantics |
| Empty object created unexpectedly | `onEmpty = USE_EMPTY` | Choose `USE_NULL` if absent data should be null |
| INSERT/UPDATE fails with NOT NULL error | Object is null while embedded columns are declared NOT NULL | Align schema and domain nullability |
| Added property but SQL reports missing column | Migration has not been run | Add/modify columns via schema migration |
| Custom query fails to map object | `SELECT` omits required embedded columns or uses wrong aliases | Return all columns required by the mapping |
| Want to reuse one address across orders with synchronized updates | Modeling shared data as embedded | Consider a separate entity/table with identity |
| Prefix change breaks older running app instances | Code and schema migrations deployed out of sync | Use a backward-compatible migration plan |
| NULL values converted to 0 | Code assigns defaults during mapping/initialization | Distinguish NULL, 0, and empty object |

## 12. Comprehensive Practice

Based on the `PurchaseOrder` model with two addresses:

**Exercise 1.** Write the annotations to embed `billingAddress` with prefix `billing_` and `shippingAddress` with prefix `shipping_`.

```java
@Embedded(prefix = "billing_")
Address billingAddress,

@Embedded(prefix = "shipping_")
Address shippingAddress
```

**Exercise 2.** Given `Address(String street, String city, String postalCode)`, list the columns corresponding to `shippingAddress`.

Answer:

- `shipping_street`
- `shipping_city`
- `shipping_postal_code`

**Exercise 3.** If all three billing columns are NULL, what happens to the property with `onEmpty = USE_NULL` vs. `onEmpty = USE_EMPTY`?

Answer: `USE_NULL` yields a `null` property; `USE_EMPTY` constructs an empty embedded object according to the mapping.

**Exercise 4.** Why is no `addresses` table created for the order example with two addresses?

Answer: In this model, the address is just a value object belonging to the order, with no independent identity or lifecycle. Its fields are stored in the same `purchase_orders` row.

**Exercise 5.** A table already has an order `city` column and adds `Address.city`. Why is a prefix needed?

Answer: If both mapped to `city`, column names would collide. A prefix creates a distinct name such as `billing_city`.

**Exercise 6.** If the prefix is changed from `billing_` to `invoice_` without a database migration, what can happen?

Answer: The new mapping will look for `invoice_*` columns while the database only has `billing_*`. Read/write operations may fail due to a schema mismatch.

**Exercise 7.** If an address is shared across multiple orders and has its own change history, should it remain embedded?

Answer: Consider moving to a separate table/entity with its own ID and explicit relationship. Embedded fits value objects belonging to an aggregate's lifecycle, not shared data with an independent lifecycle.

## 13. Key Takeaways

- **`@Embedded`** maps a child object's properties to columns in the same row of the containing table.
- **`prefix`** prepends a string prefix to mapped column names; include a separator like `"billing_"` for readable column names.
- Multiple embedded objects of the same type can use different prefixes to reuse a value object without column collisions.
- **`onEmpty`** determines how an object is constructed when all embedded columns are NULL: `USE_NULL` or `USE_EMPTY`.
- Embedded objects generally have no independent ID or lifecycle; they are part of an aggregate or value object.
- Schema migrations must stay synchronized with annotations, naming strategies, and custom SQL queries.
- Embedded does not create child tables, foreign keys, or JOINs just to read embedded properties.

### References

- [Spring Data Relational — Object Mapping Fundamentals](https://docs.spring.io/spring-data/relational/reference/object-mapping.html)
- [Spring Data JDBC — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Data Relational — Embedded Entities](https://docs.spring.io/spring-data/relational/reference/object-mapping.html#mapping-embedded-entities)

When implementing, consult the JavaDoc and reference documentation for your exact version of Spring Data Relational, especially regarding the `onEmpty` option, naming strategies, and custom conversions.
