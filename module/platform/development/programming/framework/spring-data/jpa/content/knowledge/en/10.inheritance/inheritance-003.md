# SINGLE_TABLE Strategy and Discriminator Columns

## 1. What Problem Does SINGLE_TABLE Solve?

JPA supports mapping an Entity inheritance tree to a database using several strategies. With `InheritanceType.SINGLE_TABLE`, the entire superclass and all subclasses in the same hierarchy are stored in **a single table**. A discriminator column indicates which specific Entity type each row belongs to.

For example, a payment domain has a superclass `Payment`, and two subclasses `CardPayment` and `BankTransfer`. All records reside in the `payment` table; the `payment_type` column stores `CARD` or `BANK_TRANSFER` so Hibernate instantiates the right subtype when reading data.

The major advantage of SINGLE_TABLE is that polymorphic queries and reading data across the entire hierarchy usually do not require joining multiple tables. In return, columns used only by one subtype must allow NULL in rows belonging to other subtypes. The table can grow wide and requires data validation rules based on the discriminator.

## 2. Declaring the Hierarchy in JPA

`@Inheritance` is placed on the root entity to specify the strategy for the entire hierarchy. With SINGLE_TABLE, the root entity and child entities share one table. `@DiscriminatorColumn` declares the discriminator column on the root; `@DiscriminatorValue` assigns a value to each entity in the hierarchy.

Example:

```java
import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.DiscriminatorType;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "payment")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 30
)
public abstract class Payment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    protected Payment() {
    }

    protected Payment(BigDecimal amount) {
        this.amount = amount;
    }
}
```

Child entities declare their specific attributes:

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    @Column(name = "card_last_four", length = 4)
    private String cardLastFour;

    protected CardPayment() {
    }
}
```

```java
@Entity
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransfer extends Payment {
    @Column(name = "bank_reference", length = 80)
    private String bankReference;

    protected BankTransfer() {
    }
}
```

These are the core declarations; a real application needs to add appropriate constructors, getters, setters, or factory/domain methods. The no-arg constructor must have at least `protected` visibility as required by JPA. Child entities inherit the `id` and `amount` attributes from the root.

In this hierarchy, `Payment` is abstract so it cannot be instantiated directly. `CardPayment` and `BankTransfer` are concrete types. Only the root declares `@Inheritance` and `@DiscriminatorColumn`; each subtype declares its own discriminator value.

## 3. Discriminator Column and Discriminator Value

`@DiscriminatorColumn` specifies the column the provider uses to distinguish subtypes:

- `name`: the physical column name, e.g., `payment_type`.
- `discriminatorType`: the discriminator data type. `STRING` fits human-readable values like `CARD`; JPA also supports `CHAR` and `INTEGER`.
- `length`: the column length when the type is a string.

`@DiscriminatorValue` specifies the value stored for a concrete entity. In the example, `CardPayment` rows carry `payment_type = 'CARD'`, while `BankTransfer` rows carry `payment_type = 'BANK_TRANSFER'`.

If `@DiscriminatorColumn` is omitted, JPA uses the default column `DTYPE` with string type. If `@DiscriminatorValue` is omitted, the provider applies a default value based on the entity name per JPA rules. For schemas managed by migrations or requiring long-term compatibility, explicitly declare the column name and discriminator values to avoid depending on class names.

Discriminator values are part of the data contract between the application and the schema. Do not arbitrarily rename `CARD` to `CREDIT_CARD` if the database already holds existing data; you need a migration to update existing rows and a deployment compatible with the application version.

## 4. Physical Schema of SINGLE_TABLE

With the example above, the table can be described as follows:

```sql
CREATE TABLE payment (
    id BIGINT PRIMARY KEY,
    payment_type VARCHAR(30) NOT NULL,
    amount DECIMAL(19, 2) NOT NULL,
    card_last_four VARCHAR(4),
    bank_reference VARCHAR(80)
);
```

The DDL is illustrative; ID generation and exact syntax depend on the database. All columns from the root and every subtype reside together in `payment`. Because a row belongs to only one subtype, columns not applicable to that subtype are typically NULL:

| payment_type | amount | card_last_four | bank_reference |
| --- | ---: | --- | --- |
| `CARD` | 125.00 | `4821` | NULL |
| `BANK_TRANSFER` | 300.00 | NULL | `TRX-2026-001` |

Therefore, do not place an unconditional `NOT NULL` on `card_last_four` or `bank_reference` if the other subtype does not use that column. If a column is required within a subtype, validate it at the domain/Bean Validation layer and consider a discriminator-based CHECK constraint in the database.

Illustrative CHECK constraint example:

```sql
ALTER TABLE payment
ADD CONSTRAINT ck_payment_subtype_fields
CHECK (
    (payment_type = 'CARD' AND card_last_four IS NOT NULL AND bank_reference IS NULL)
    OR
    (payment_type = 'BANK_TRANSFER' AND bank_reference IS NOT NULL AND card_last_four IS NULL)
);
```

The CHECK constraint above expresses a specific rule for the example and should be adjusted to real requirements, database capabilities, and how NULL values are handled. If a subtype has many optional fields, do not force every field to be NOT NULL just because it appears in a subclass.

## 5. Polymorphic Queries

JPA queries on the root entity are polymorphic: querying `Payment` can return both `CardPayment` and `BankTransfer`. Hibernate reads the discriminator to instantiate the right Java class.

```java
List<Payment> payments = entityManager
    .createQuery("select p from Payment p", Payment.class)
    .getResultList();
```

The results can contain instances of the subclasses. You can check the type in Java with `instanceof` or use `TYPE` in JPQL when filtering by subtype:

```java
List<Payment> cardPayments = entityManager
    .createQuery(
        "select p from Payment p where type(p) = CardPayment",
        Payment.class
    )
    .getResultList();
```

JPQL uses entity names and Java properties, not physical table/column names. When you need to query fields specific to a subtype, you can use `TREAT` in JPQL or a dedicated subtype repository query, depending on the use case and provider capabilities.

Because all subtypes share one table, root queries do not need to join child tables to assemble data like JOINED does. Hibernate can use the discriminator in the query condition to restrict subtypes when querying a child entity.

## 6. How Do INSERT and UPDATE Work?

When persisting `CardPayment`, Hibernate writes a row into `payment` containing the inherited attributes, the CardPayment-specific columns, and the discriminator `CARD`. Columns reserved for BankTransfer are left NULL. When persisting `BankTransfer`, the discriminator is `BANK_TRANSFER` and card-specific columns are left NULL.

Logically, the data takes this form:

```sql
INSERT INTO payment
    (payment_type, amount, card_last_four, bank_reference)
VALUES
    ('CARD', 125.00, '4821', NULL);
```

This is illustrative SQL to explain the data structure; actual SQL may differ in column order, placeholders, generated keys, and parameter binding depending on the dialect/provider.

When updating a subtype, Hibernate updates the row in the same table. There is no separate child table to join. Thus subtype attributes coexist on a single row, though only columns matching the discriminator carry business meaning.

## 7. SINGLE_TABLE vs. JOINED and TABLE_PER_CLASS

| Criterion | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
| --- | --- | --- | --- |
| Structure | One table for the entire hierarchy | Root table and a separate table per subtype | Each concrete class has its own table, usually repeating inherited columns |
| Polymorphic reads | Usually no subtype joins needed | Usually requires joining subtype tables | May require UNION |
| Subtype-specific columns | Many nullable columns in a shared table | Reside in subtype tables | Reside in subtype tables |
| Subtype NOT NULL constraints | Harder in a single shared table | More natural in subtype tables | Can be enforced on each table |
| Data writes | Usually one table | May have to write to multiple tables in the hierarchy | Writes to the concrete subtype table |
| Suitability | Moderate hierarchy, frequent polymorphic queries | Need normalized schema and clear subtype constraints | Subtypes rarely need polymorphic queries or have independent schemas |

SINGLE_TABLE often provides good polymorphic read performance because it avoids multi-table joins. However, when a hierarchy has many subtypes with many distinct columns, the table can become very wide with many NULL values and a hard-to-manage schema. Choose a strategy based on query patterns, number of subtypes, data rules, and migration cost—not merely on table count.

## 8. When Should You Use SINGLE_TABLE?

Suitable when:

- Subtypes share many common attributes.
- The application frequently queries lists across the entire root type.
- The number of subtypes and specialized fields remains manageable.
- Allowing NULL for other subtypes' columns is acceptable.
- You want to simplify polymorphic read queries.

Consider another strategy when each subtype has many distinct fields, differing NOT NULL constraints are critical, or the shared table becomes too wide. JOINED may be suitable when you need to separate data by subtype and enforce stricter schema constraints, at the cost of joins.

## 9. Design Considerations

**Do not use the discriminator as arbitrary business data.** The discriminator determines the Java type of a row. Do not mutate it like an ordinary business status if that change would require the row to become a different subtype. Changing subtypes may require creating a new instance, migrating data, and handling related associations.

**Discriminator values must be stable.** Use explicit strings rather than relying on default class names for long-lived schemas. When changing values, migrate data and ensure compatible application versions during rollout.

**Do not repeat `@DiscriminatorColumn` on subclasses.** The discriminator column belongs to the hierarchy configuration on the root entity. Subclasses only need `@DiscriminatorValue`.

**Do not create separate Entities per subtype just to add a few attributes without modeling value.** Consider composition/association when the types are not genuinely an `is-a` inheritance relationship.

**Control subtype fields.** Fields not belonging to the current subtype should normally be NULL; add discriminator-based CHECK constraints when the database supports them and the rules are clear enough.

## 10. Migrations and Data Compatibility

With Flyway or Liquibase, migrations must create the shared table, discriminator column, shared columns, and all subtype columns. If switching from another strategy to SINGLE_TABLE, plan how to consolidate data from old tables, assign discriminators to each row, handle duplicate IDs, and update foreign keys, indexes, views, and native queries.

When adding a new subtype, add the corresponding columns and new discriminator value; existing rows must remain readable. When renaming a discriminator column or value, migrations must update existing data. Avoid deploying new code before the schema can store the new values and columns.

Do not rely on `ddl-auto=update` to convert production data across inheritance strategies. Use versioned migrations and verify with representative data.

## 11. Common Issues and Troubleshooting

**Hibernate does not recognize a subtype.** Check that the subclass has `@Entity`, the discriminator value matches the data in the discriminator column, and package scanning includes the class.

**Column not found errors.** Compare names in `@Column`, the physical naming strategy, and DDL. SINGLE_TABLE places subtype columns on the root table rather than creating a separate table for each subclass.

**NOT NULL error when inserting a subtype.** Check whether the required column belongs only to another subtype. Subtype-specific columns in the shared table usually need to be nullable or governed by a conditional CHECK constraint.

**Root query returns multiple object types.** This is normal polymorphic behavior. If you only need one subtype, filter via the subtype's repository or JPQL `TYPE`.

**Data has an invalid discriminator.** Check migrations, manually imported data, and application versions that wrote that value. Do not arbitrarily alter the discriminator because it determines which class is hydrated.

**Shared table is too wide or has many NULL columns.** Re-evaluate the number of subtypes, specialized fields, and query patterns. Consider moving to JOINED or composition if schema benefits outweigh join costs.

## 12. Implementation Checklist

- Place `@Inheritance(strategy = InheritanceType.SINGLE_TABLE)` on the root entity.
- Declare `@DiscriminatorColumn` explicitly and a stable `@DiscriminatorValue` for each subtype.
- Ensure all subtypes are `@Entity` within the scan scope.
- Design DDL with shared and subtype-specific columns; do not apply unconditional NOT NULL to another subtype's columns.
- Update migrations, indexes, constraints, and native SQL.
- Verify polymorphic queries on the root and targeted queries per subtype.
- Verify discriminator data and insert/update behavior on the target database.
- Choose SINGLE_TABLE for query characteristics and data model fit, not simply to reduce table count.

SINGLE_TABLE stores the entire hierarchy in one table and uses a discriminator to identify subtypes. This keeps polymorphic queries simple, but requires careful design of nullable columns, discriminator values, and migrations so the schema stays consistent with the Entity model.