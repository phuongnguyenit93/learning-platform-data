# Modeling Addresses or Money as Value Objects

In a Spring Data Relational JDBC application, not every piece of data needs to become an entity or its own table. A shipping address, billing address, or monetary amount is often a **value object**: a group of values describing a domain concept, owned by another object, and having no independent identity in the domain.

Spring Data JDBC supports this pattern using **embedded objects**. The properties of the value object are mapped to columns in the same row as the aggregate root. As a result, Java code still expresses meaningful structures like `Address` or `Money`, while the relational schema stores those values in regular columns.

This lesson covers how to design value objects, use `@Embedded` and prefixes to map addresses and monetary amounts, choose how to handle cases where all columns are `NULL`, design database constraints, and recognize when to use a separate table instead of an embedded object.

## 1. What Is a Value Object?

A **value object** is an object defined by its constituent values rather than a separate ID. Two value objects with the same values are considered equivalent in business meaning.

Examples:

- An address consisting of street, city, postal code, and country.
- A monetary amount consisting of a numeric value and a currency.
- A time range consisting of start and end timestamps.
- Coordinates consisting of longitude and latitude.

An address typically does not need an `address_id` just to represent the shipping address of a single order. That address has meaning in the context of the order that owns it. Similarly, `100.00 USD` and `100.00 VND` do not mean the same thing; storing only `100.00` does not convey enough information.

### How Do Entities and Value Objects Differ?

| Criterion | Entity | Value Object |
| --- | --- | --- |
| Identity | Has a stable identity, usually an ID | Needs no separate identity |
| Comparison | Primarily by identity | By all constituent values |
| Lifecycle | Can exist independently in the domain | Usually belongs to the owning object's lifecycle |
| Mutability | State can be updated while preserving identity | Usually immutable; changed by creating a new value |
| Examples | `Customer`, `PurchaseOrder`, `Product` | `Address`, `Money`, `DateRange` |

Suppose an order has a shipping address. If the buyer edits the order's address before shipment, the business logic can replace the entire `Address` value object. That address does not necessarily need to be managed as a separate entity.

Conversely, if the business manages a list of verified addresses, allows multiple orders to reference a shared address, and tracks verification status and edit history independently, the address may need to become an entity or independent aggregate.

**The choice between value object and entity comes from lifecycle and business rules**, not merely from whether a group of fields can be bundled into a Java class.

## 2. Embedded Objects in Spring Data JDBC

Spring Data JDBC uses the `@Embedded` annotation to declare a value object property stored in the same row as its containing object.

Simple example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Embedded(prefix = "shipping_")
    private Address shippingAddress;
}
~~~

If `Address` has properties `street`, `city`, and `postalCode`, the values are stored in the `purchase_orders` table using columns prefixed with `shipping_`, such as:

- `shipping_street`
- `shipping_city`
- `shipping_postal_code`

No separate `addresses` table is created just because the `Address` class exists. An embedded object has no separate ID, is not a new aggregate root, and is not stored as an independent row.

~~~mermaid
flowchart TD
    A["PurchaseOrder<br/>aggregate root"] --> B["Address<br/>value object"]
    B --> C["street"]
    B --> D["city"]
    B --> E["postalCode"]
    A --> F["One purchase_orders row"]
    C --> F
    D --> F
    E --> F
~~~

The columns of `Address` are flattened into the `purchase_orders` row. When reading that row, Spring Data JDBC assembles the column values to construct an `Address` object and assigns it to `PurchaseOrder`.

### Comparison with Collections or Child Entities

Embedded objects and child entities in Spring Data JDBC have different storage structures:

| Java Model | Common Storage | Relationship |
| --- | --- | --- |
| `@Embedded Address address` | Address columns reside in the parent table | Same row |
| `@MappedCollection List<OrderLine> lines` | Rows in a child table, with a column referencing the aggregate root | Separate table, inside aggregate |
| `Long customerId` or `AggregateReference<Customer, Long>` | FK/ID column in the orders table | Reference to another aggregate |

Avoid using `@MappedCollection` for an address that only makes sense within a single order if it has no separate lifecycle. Conversely, avoid embedding an unbounded list of order lines into the same order row; a child entity collection is more appropriate.

## 3. Designing the Address Value Object

An address value object can be a Java record to express immutability:

~~~java
import java.util.Objects;
import java.util.Locale;

import org.springframework.data.relational.core.mapping.Column;

public record Address(
    @Column("street") String street,
    @Column("city") String city,
    @Column("postal_code") String postalCode,
    @Column("country_code") String countryCode
) {
    public Address {
        street = requireText(street, "street");
        city = requireText(city, "city");
        countryCode = requireText(countryCode, "countryCode")
            .toUpperCase(Locale.ROOT);

        if (countryCode.length() != 2) {
            throw new IllegalArgumentException(
                "countryCode must contain two characters"
            );
        }

        // postalCode can be optional depending on the country's address rules.
    }

    private static String requireText(String value, String field) {
        Objects.requireNonNull(value, field + " must not be null");
        if (value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }
}
~~~

A record automatically provides a constructor, accessors, `equals`, and `hashCode` based on its components. Thus, two addresses with the same component values can be compared by value.

Checks inside the compact constructor protect object invariants whenever the application creates an address. However, keep in mind that when data is read from the database, the constructor is also invoked during materialization. If the schema has legacy rows containing invalid values, reading those rows may fail. Legacy data must be cleaned up, or validation rules must be designed to match real-world data.

### Why Use a Value Object Instead of Four Separate Fields?

If the aggregate root declares:

~~~java
private String shippingStreet;
private String shippingCity;
private String shippingPostalCode;
private String shippingCountryCode;
~~~

then fields describing a single concept have their validation, normalization, and comparison logic scattered throughout the aggregate. When using `Address`, address-related rules are grouped into one meaningful type.

This also prevents passing strings in the wrong order across APIs. A method accepting `Address` clearly expresses that it needs a complete address; a method accepting four strings does not convey the same level of meaning.

## 4. Embedding Address with @Embedded

An aggregate root can declare both a shipping address and a billing address:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Embedded.Nullable(prefix = "shipping_")
    private Address shippingAddress;

    @Embedded.Nullable(prefix = "billing_")
    private Address billingAddress;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Address shippingAddress, Address billingAddress) {
        this.shippingAddress = shippingAddress;
        this.billingAddress = billingAddress;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public Address getBillingAddress() {
        return billingAddress;
    }
}
~~~

The example uses `@Embedded.Nullable` because an address might not have been provided yet. Prefixes distinguish the columns of two value objects of the same type:

| Java Property | Prefix | SQL Column |
| --- | --- | --- |
| `shippingAddress.street` | `shipping_` | `shipping_street` |
| `shippingAddress.city` | `shipping_` | `shipping_city` |
| `shippingAddress.postalCode` | `shipping_` | `shipping_postal_code` |
| `shippingAddress.countryCode` | `shipping_` | `shipping_country_code` |
| `billingAddress.street` | `billing_` | `billing_street` |
| `billingAddress.city` | `billing_` | `billing_city` |
| `billingAddress.postalCode` | `billing_` | `billing_postal_code` |
| `billingAddress.countryCode` | `billing_` | `billing_country_code` |

The prefix is part of the mapped column name. Without prefixes, two embedded properties of the same type would both attempt to use column names like `street` and `city`, causing a collision.

### Illustrative DDL

With PostgreSQL, the schema can be created as follows:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    shipping_street VARCHAR(200),
    shipping_city VARCHAR(120),
    shipping_postal_code VARCHAR(30),
    shipping_country_code CHAR(2),

    billing_street VARCHAR(200),
    billing_city VARCHAR(120),
    billing_postal_code VARCHAR(30),
    billing_country_code CHAR(2)
);
~~~

All embedded columns reside in the same row. When the shipping address changes, saving the aggregate updates the corresponding columns of the order row.

Column names in the DDL must match the mapping metadata. If the project uses a different naming strategy or quoting, verify the actual SQL names generated by the framework.

## 5. @Embedded.Nullable and @Embedded.Empty

A value object can be optional. When there is no address, the aggregate may hold `shippingAddress = null`. In the database, however, this is represented across multiple columns: all columns of the address are `NULL`.

Spring Data Relational provides variants of `@Embedded` to specify how to handle this situation.

### 5.1. @Embedded.Nullable

~~~java
@Embedded.Nullable(prefix = "shipping_")
private Address shippingAddress;
~~~

With `@Embedded.Nullable`, if all columns of the embedded object are `NULL`, the embedded property is materialized as `null`. If at least one column has a value, the framework constructs the object from the corresponding columns.

This is the natural choice for an optional address: no address means no `Address` object.

Distinguish carefully:

- All columns `NULL`: the object is `null`.
- One or more columns non-`NULL`: the framework constructs the embedded object; the constructor/validation may reject combinations missing required components.

For example, if `shipping_street` has a value while `shipping_city` and `shipping_country_code` are `NULL`, the `Address` constructor above will reject the data. This is intentional if business rules require a complete address.

### 5.2. @Embedded.Empty

~~~java
@Embedded.Empty(prefix = "shipping_")
private Address shippingAddress;
~~~

`@Embedded.Empty` takes a different approach: when all columns of the embedded object are `NULL`, Spring Data still creates an embedded instance instead of setting the property to `null`. This fits a model that wants to represent an "empty value object" according to application conventions.

However, not every value object has a valid empty state. For an `Address` whose constructor requires street/city/country, constructing an object from all `NULL` values can violate invariants. Use `@Embedded.Empty` only when the embedded type can meaningfully represent that state, such as an optional structure designed to allow empty fields.

### 5.3. Comparing the Options

| Annotation | When All Embedded Columns Are `NULL` | Meaning |
| --- | --- | --- |
| `@Embedded` | Follows the annotation's `onEmpty` policy, defaulting to `USE_NULL` | Embedded object with default configuration |
| `@Embedded.Nullable` | Property receives `null` | Value object is absent |
| `@Embedded.Empty` | Creates an embedded instance | Empty object exists as allowed by the model |

Do not use `@Embedded.Empty` just to avoid `null` in Java. If the domain does not define a valid empty address, forcing object creation will mask incomplete data.

### 5.4. Database Constraints for Optional Addresses

For optional addresses, ensure database data has two clear states: either no address (all columns null) or an address with required fields present.

PostgreSQL example:

~~~sql
ALTER TABLE purchase_orders
ADD CONSTRAINT ck_shipping_address_complete
CHECK (
    (
        shipping_street IS NULL
        AND shipping_city IS NULL
        AND shipping_postal_code IS NULL
        AND shipping_country_code IS NULL
    )
    OR
    (
        shipping_street IS NOT NULL
        AND shipping_city IS NOT NULL
        AND shipping_country_code IS NOT NULL
    )
);
~~~

`postal_code` is allowed to be null because some countries/regions do not use postal codes or business rules allow omitting it. Required fields must be decided based on actual application requirements.

Constraints help block partial data written via direct SQL or another application. Constructor validation and database constraints protect two different layers.

## 6. Modeling Money as a Value Object

A monetary amount is a particularly important example of a value object. You should not store only a `double` or `BigDecimal` without storing the currency, because `100 USD` and `100 VND` do not have the same meaning.

A minimal `Money` value object includes:

- `amount`: exact numeric value, usually using `BigDecimal`.
- `currency`: currency code, e.g., `USD`, `VND`, `EUR`.

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;
import java.util.Locale;

import org.springframework.data.relational.core.mapping.Column;

public record Money(
    @Column("amount") BigDecimal amount,
    @Column("currency") String currency
) {
    public Money {
        Objects.requireNonNull(amount, "amount must not be null");
        Objects.requireNonNull(currency, "currency must not be null");

        currency = Currency.getInstance(
            currency.trim().toUpperCase(Locale.ROOT)
        ).getCurrencyCode();
    }

    public Money plus(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money minus(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other must not be null");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Cannot combine different currencies"
            );
        }
    }
}
~~~

Example:

~~~java
Money subtotal = new Money(new BigDecimal("120.00"), "USD");
Money shipping = new Money(new BigDecimal("8.50"), "USD");

Money total = subtotal.plus(shipping);
// total = 128.50 USD
~~~

If you try to add `120 USD` and `8.500 VND`, the `plus` method rejects it because the two currencies differ. Currency conversion requires an exchange rate, effective timestamp, rate source, and rounding rules; it cannot be performed by simply adding two `BigDecimal` numbers.

### Why Not Use float or double?

Binary floating-point types can represent a decimal number like `0.1` only as an approximation. For money, this easily leads to accumulated errors or unexpected results.

Use `BigDecimal` with decimal strings:

~~~java
new BigDecimal("19.95");
~~~

Avoid:

~~~java
new BigDecimal(19.95);
~~~

The latter initializes from an already approximated floating-point value, so it does not preserve the exact original decimal intent.

### Scale and Rounding Rules

There is no single rounding rule that applies to every currency and every business domain. Some currencies commonly have 0 decimal places, while others have 2 or 3; accounting, tax, product pricing, and payment systems may also specify different scales.

Therefore:

- Do not automatically call `setScale(2)` for every `Money`.
- Determine scale based on the currency and business rules.
- Choose an explicit `RoundingMode` at calculation boundaries that require rounding.
- Retain necessary precision during intermediate calculations.
- Decide whether to store amounts using a uniform scale or per-currency scale in the schema.

## 7. Embedding Money into an Aggregate

An order can have a required total and an optional discount:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Embedded(prefix = "total_")
    private Money total;

    @Embedded.Nullable(prefix = "discount_")
    private Money discount;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Money total, Money discount) {
        this.total = total;
        this.discount = discount;
    }

    public Money getTotal() {
        return total;
    }

    public Money getDiscount() {
        return discount;
    }
}
~~~

Mapping:

| Property | Prefix | Columns |
| --- | --- | --- |
| `total` | `total_` | `total_amount`, `total_currency` |
| `discount` | `discount_` | `discount_amount`, `discount_currency` |

Illustrative PostgreSQL DDL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    total_amount NUMERIC(19, 4) NOT NULL,
    total_currency CHAR(3) NOT NULL,

    discount_amount NUMERIC(19, 4),
    discount_currency CHAR(3),

    CONSTRAINT ck_discount_pair
        CHECK (
            (discount_amount IS NULL AND discount_currency IS NULL)
            OR
            (discount_amount IS NOT NULL AND discount_currency IS NOT NULL)
        )
);
~~~

In this example:

- `total` is required, so both total columns are `NOT NULL`.
- `discount` is optional, so both discount columns are either null together or present together.
- `NUMERIC(19,4)` is an illustrative choice; actual precision/scale should be based on the system's amount limits and currency rules.
- `CHAR(3)` stores the three-letter currency code; the application can normalize codes using `Currency`.

If you need to restrict currencies to an accepted list, you can use a `CHECK` constraint or a reference currency table depending on the model. Do not assume `Currency.getInstance` and database constraints share the same list or business rules at all times.

### Two Money Fields in the Same Table Need Prefixes

If both `total` and `discount` embed `Money` without prefixes, both will try to use the columns `amount` and `currency`. Prefixes clearly distinguish which role in the aggregate each value belongs to.

This also applies if an object has `originalPrice` and `salePrice`, or `subtotal` and `tax`. Column names should reflect the business context rather than merely repeating field names inside the value object.

## 8. Combining Address and Money in One Aggregate

A more complete order example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Embedded.Nullable(prefix = "shipping_")
    private Address shippingAddress;

    @Embedded(prefix = "total_")
    private Money total;

    @Embedded.Nullable(prefix = "discount_")
    private Money discount;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            Address shippingAddress,
            Money total,
            Money discount) {
        this.shippingAddress = shippingAddress;
        this.total = total;
        this.discount = discount;
    }
}
~~~

The relational table stores flat columns:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    shipping_street VARCHAR(200),
    shipping_city VARCHAR(120),
    shipping_postal_code VARCHAR(30),
    shipping_country_code CHAR(2),

    total_amount NUMERIC(19, 4) NOT NULL,
    total_currency CHAR(3) NOT NULL,

    discount_amount NUMERIC(19, 4),
    discount_currency CHAR(3),

    CONSTRAINT ck_shipping_address_complete
        CHECK (
            (
                shipping_street IS NULL
                AND shipping_city IS NULL
                AND shipping_postal_code IS NULL
                AND shipping_country_code IS NULL
            )
            OR
            (
                shipping_street IS NOT NULL
                AND shipping_city IS NOT NULL
                AND shipping_country_code IS NOT NULL
            )
        ),

    CONSTRAINT ck_discount_pair
        CHECK (
            (discount_amount IS NULL AND discount_currency IS NULL)
            OR
            (discount_amount IS NOT NULL AND discount_currency IS NOT NULL)
        )
);
~~~

The Java structure expresses domain concepts; the relational schema expresses storage. When reading an order, Spring Data JDBC constructs `Address` from the `shipping_*` column group, constructs `Money` from the `total_*` group, and either constructs or omits `Money` for `discount_*` depending on the column state.

There is no separate address table or money table in the example. If a value object needs to be shared, looked up, or have an independent history or lifecycle, re-evaluate embedding it.

## 9. Value Object Validation and Database Constraints

A value object should protect its own invariants. For example, `Money` requires a valid amount and currency; `Address` requires required fields to be non-empty.

However, Java validation alone is not enough, because the database can also be updated by:

- SQL scripts or administration tools.
- Another service.
- Batch jobs or data imports.
- Older application versions.
- Concurrent transactions.

Therefore, use SQL constraints to protect data rules that can be expressed at the database level.

| Rule | Validation in Java | Possible SQL Constraint |
| --- | --- | --- |
| Address has street/city/country | Constructor checks null/blank | `NOT NULL` per column or `CHECK` for column group |
| Country code has valid format | Normalize/validate code | Format `CHECK` or FK to lookup table |
| Money has amount and currency | Constructor checks non-null | `NOT NULL` for column pair |
| Optional money columns both present or both null | Nullable value object | `CHECK` for amount/currency pair |
| Amount within business bounds | Range check | `CHECK` if rule can be stably expressed |
| Supported currency | Business list/registry | `CHECK` or FK to currency table |

### Constraints for Address

If an address requires street and country while postal code is optional, use a `CHECK` constraint to allow two states: the whole group is null, or the required fields have values. Do not mark every column `NOT NULL` if the entire `Address` can be absent.

### Constraints for Money

For required Money, both amount and currency columns should be `NOT NULL`. For optional Money, a constraint must ensure both are present or both are absent. Having only `discount_amount` without `discount_currency` leaves the data insufficient to interpret the monetary amount.

### Validation Should Not Do the Schema's Job

If the `Money` constructor rejects negative amounts while the schema allows writing negative amounts via direct SQL, bad data can still exist and cause failures on subsequent reads. If the business forbids negative amounts, consider `CHECK(amount >= 0)`. If an accounting system allows negative adjustments, do not mechanically add a non-negative constraint; define the exact semantics of each Money field.

## 10. Updating Value Objects in Spring Data JDBC

Because value objects are typically immutable, updating an address means creating a new value and assigning it to the aggregate:

~~~java
Address newAddress = new Address(
    "12 Nguyen Hue",
    "Ho Chi Minh City",
    "700000",
    "VN"
);

order.changeShippingAddress(newAddress);
~~~

A domain method on the aggregate root can express the change:

~~~java
public void changeShippingAddress(Address newAddress) {
    this.shippingAddress = java.util.Objects.requireNonNull(newAddress);
}
~~~

With an immutable aggregate, you can instead return a new instance:

~~~java
public PurchaseOrder withShippingAddress(Address newAddress) {
    return new PurchaseOrder(newAddress, total, discount);
}
~~~

When saving the aggregate with Spring Data JDBC, embedded columns are written as part of the aggregate root row's data. There is no separate repository for `Address` or `Money` merely because they are Java classes.

Distinguish replacing a value object from updating a child entity in a collection. An embedded object belongs to the root's row; a child entity in `@MappedCollection` has its own table and persistence lifecycle within the aggregate.

## 11. When to Use a Separate Table Instead of Embedded?

An embedded object is not the right choice in every situation.

| Business Indicator | Typically Suitable Model |
| --- | --- |
| Address only has meaning within a single order | Embedded `Address` |
| Address has an ID, is shared, and is managed independently | Separate `Address` entity/aggregate |
| Monetary amount only describes the order total | Embedded `Money` |
| Payment transaction has a transaction ID, status, timestamp, and its own lifecycle | `Payment` entity or payment aggregate |
| Value object has a fixed number of components | Embedded |
| Object has an unbounded number of elements | Collection/child table or separate table |
| Needs independent querying, updating, or authorization on the child | Consider a separate entity/table |

A value object can be used across multiple aggregates without needing to share a database row. For instance, two orders may have the same shipping address by value, yet each stores its own snapshot. When the customer changes their profile address, order history preserves the address at the time the order was placed.

If instead two orders reference the same shared address record, changing that record could affect both orders. That is completely different semantics and requires an independent entity/aggregate.

## 12. Embedded Objects Are Not JSON Columns

Another way to store a group of values is to encode the entire object into a JSON or text column. This is not the default behavior of `@Embedded`.

| Embedded Mapping | JSON / Custom Conversion |
| --- | --- |
| Each property becomes an SQL column | Entire object can become a single column |
| Can use `NOT NULL`, `CHECK`, indexes on individual columns | Constraints/queries depend on database JSON capabilities |
| Column names have clear prefixes | Field structure lives inside JSON |
| Suitable for data with a stable structure | Can suit flexible data or evolving schemas |
| Mapped with `@Embedded` | Usually requires converters or JSON data type support |

For example, if you want to store `Address` in a JSON column, you must design the corresponding conversion and schema. You cannot simply add `@Embedded` and expect the framework to automatically serialize all fields into JSON.

For addresses or money whose fields matter for filtering, validation, constraints, and reporting, embedded columns are usually easier to manage. JSON fits when you need to store a flexible structure and accept the querying/constraint trade-offs.

## 13. Migrations When Changing a Value Object

The schema of an embedded object is part of the aggregate root table. Adding a field to a value object can mean adding columns to multiple tables that embed it.

For example, adding `district` to `Address`:

~~~java
public record Address(
    @Column("street") String street,
    @Column("district") String district,
    @Column("city") String city,
    @Column("postal_code") String postalCode,
    @Column("country_code") String countryCode
) {}
~~~

If `Address` is embedded in `purchase_orders` with prefix `shipping_`, the schema needs `shipping_district`. If it is also embedded in other tables with different prefixes, those tables need corresponding migrations as well.

A safe rollout process:

1. Identify all aggregates/tables embedding the value object.
2. Create migrations adding the new columns compatibly with existing data (e.g., nullable or with a sensible default).
3. Update Java mapping and read/write logic.
4. Backfill existing data if required by the business.
5. Add required constraints once existing data satisfies them.
6. Deploy with a compatible rollout strategy if multiple application versions run concurrently.

Do not simply change a record component and expect Spring Data JDBC to alter the schema automatically. Mapping describes how to read/write; migrations change the database structure.

## 14. Debugging Embedded Mapping Errors

Some common errors:

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| Embedded column not found | Prefix or column name does not match DDL | `@Embedded(prefix)`, `@Column`, and migrations |
| Two value objects of the same type overwrite column names | Missing distinct prefix per property | Use `shipping_`, `billing_`, `total_`, etc. |
| Read produces null object when empty object was expected | All embedded columns are null and `USE_NULL` policy is used | Clarify semantics and choose Nullable/Empty |
| Value object constructor throws an exception | Row has partially null columns or invalid legacy data | Inspect data, constraints, and invariants |
| Money saved without currency | Schema lacks currency column or wrong prefix mapping | Protect column pair with NOT NULL / CHECK |
| Wrong monetary data type used | Using float/double or inappropriate scale | Use `BigDecimal` and explicit rounding rules |
| Expecting an `Address` table but none exists | `@Embedded` stores columns in the parent table | Check whether the model needs a separate entity |
| Changed embedded field and application fails | New column has not been migrated | Verify schema and deployment order |

### Inspecting PostgreSQL Schema

You can list the columns of the orders table:

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'purchase_orders'
ORDER BY ordinal_position;
~~~

The output helps confirm that `shipping_*`, `total_*`, and `discount_*` columns exist with the expected types and nullability.

To find addresses in a partial state:

~~~sql
SELECT id
FROM purchase_orders
WHERE
    (
        shipping_street IS NULL
        OR shipping_city IS NULL
        OR shipping_country_code IS NULL
    )
    AND
    (
        shipping_street IS NOT NULL
        OR shipping_city IS NOT NULL
        OR shipping_country_code IS NOT NULL
    );
~~~

This query is just an example check based on the chosen set of required fields. Specific rules must be adjusted to your schema and application address requirements.

## 15. Design Conventions to Adopt

When creating value objects for Spring Data JDBC, standardize on the following principles:

- **Use domain-meaningful types:** `Address`, `Money` instead of a group of loose strings or numbers.
- **Prefer immutability:** records or classes with final fields and invariant-checking constructors.
- **Do not add artificial IDs:** a value object needs no ID if the business does not manage an identity for it.
- **Use `@Embedded`:** when components are stored in the same row as the aggregate root.
- **Use clear prefixes:** when there are multiple embedded objects or multiple objects of the same type.
- **Choose null semantics intentionally:** `@Embedded.Nullable` when absence is represented as null; `@Embedded.Empty` when an empty object has valid meaning.
- **Keep constraints in the database:** especially for column groups that must be present together or null together.
- **Use `BigDecimal` for money:** always pair amount with currency and rounding rules.
- **Manage schema with migrations:** changing a value object requires assessing all tables that embed it.
- **Choose a separate entity when lifecycle is independent:** do not embed solely to reduce table count.

Quick-choice reference table:

| Requirement | Choice |
| --- | --- |
| Optional address of an order | `@Embedded.Nullable(prefix = "shipping_")` |
| Required value object whose required columns have values | `@Embedded(prefix = "total_")` and SQL constraints |
| Want an instance created when all columns are null | `@Embedded.Empty` if an empty object is valid |
| Same `Address` type for shipping and billing | Two distinct prefixes |
| Total amount with amount and currency | `Money` with `BigDecimal` and currency code |
| Value with its own ID, history, or independent queries | Separate entity or aggregate |
| Flexible data stored in one JSON column | Converter/JSON mapping, not default embedded |

## 16. Practice Exercises

### Exercise 1 — Optional Address

Create an `Address` record with street, city, postalCode, and countryCode. Embed it into `PurchaseOrder` using `@Embedded.Nullable(prefix = "shipping_")`. Create a PostgreSQL schema with the corresponding columns and a constraint allowing either no address at all or all required fields present.

### Exercise 2 — Two Addresses of the Same Type

Add `billingAddress` of the same `Address` type. Use the `billing_` prefix. List the column names for both properties and explain why the same prefix cannot be used.

### Exercise 3 — Distinguishing Nullable and Empty

Create an embedded type that can represent a valid empty state. Compare materialization results when all columns are null using `@Embedded.Nullable` versus `@Embedded.Empty`. State a case where Empty should not be used.

### Exercise 4 — Money

Create a `Money(BigDecimal amount, String currency)` record. Write a method to add two `Money` values while rejecting mismatched currencies. Embed `total` and `discount` in the same aggregate with two prefixes. Create a constraint so that discount's amount and currency are either both null or both non-null.

### Exercise 5 — Monetary Values and Rounding

Try `new BigDecimal("0.1")` and `new BigDecimal(0.1)`. Observe their representations and explain why money should use `BigDecimal`. Design a rounding rule for a specific currency and business case instead of defaulting to two decimal places everywhere.

### Exercise 6 — When Does Address Become an Entity?

Suppose addresses are verified, shared by multiple customers, and have a status and edit history. Analyze the lifecycle and decide whether to keep a snapshot value object or create a separate `Address` aggregate. Explain the impact on schema and relationships between aggregates.

## 17. Official References

- [Spring Data Relational — Object Mapping](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): object mapping mechanism, embedded entities, prefixes, and handling empty embedded objects.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): how Spring Data JDBC maps aggregates and property types.
- [Spring Data Relational — @Embedded API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/Embedded.html): embedded annotation, prefixes, and policy when embedded data is empty.
- [Spring Data Relational — @Column API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/Column.html): specifying physical column names for properties.
- [Java BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): exact decimal numbers, scale, and rounding.
- [Java Currency API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html): currency code representation and currency information.

Value objects help a Java model speak the business language accurately: an address is an address, and a monetary amount is an amount with a currency. With Spring Data JDBC, `@Embedded` lets you keep that object structure in source code while storing values as columns on the aggregate root. When prefixes, null semantics, validation, and constraints are chosen consistently, the model is both clear in Java and protective of relational data.
