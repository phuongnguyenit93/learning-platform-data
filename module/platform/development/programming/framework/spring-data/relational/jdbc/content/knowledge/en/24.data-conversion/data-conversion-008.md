# Single-Property–Single-Value Limitation and Multi-Column Data

In **Spring Data Relational JDBC (Spring Data JDBC)**, standard mapping treats each property as stored in a single column value. When a custom domain type needs to be stored in one column, you can register a converter to translate that type to a simple JDBC type such as `String`, `Long`, `BigDecimal`, or a matching database type.

An important limitation is that a normal converter transforms **one source value into one target value**. It does not automatically split one property into multiple physical columns. If a value object such as `Money` has both an amount and a currency, and needs to be stored as two separate columns for querying and constraints, use `@Embedded`. Spring Data JDBC flattens the inner properties into the same table as the aggregate root.

This lesson distinguishes three models:

- **One property – one column:** a custom converter translates one domain type into one database value.
- **One value object – multiple columns:** `@Embedded` maps sub-properties to multiple columns in the same table.
- **Data across multiple tables:** use aggregate relationships or read queries/DTOs; converters do not replace JOINs or aggregate mapping.

## 1. Default Mapping and Converter Limitations

Suppose a `Product` entity has a `productCode` property with a custom domain type:

~~~java
public record ProductCode(String value) {}
~~~

The database only needs to store the product code text in one `product_code` column. Converters can turn `ProductCode` into `String` when writing and turn `String` back into `ProductCode` when reading.

~~~mermaid
flowchart LR
    Domain["ProductCode<br/>one property"]
    Write["Writing Converter"]
    Column[("product_code<br/>one column")]
    Read["Reading Converter"]
    Loaded["ProductCode<br/>one property"]
    Domain --> Write --> Column --> Read --> Loaded
~~~

This is a good fit for custom conversions: one domain value has a single database representation.

By contrast, if a `price` property has type `Money` containing `amount` and `currencyCode`, a `Money -> BigDecimal` converter can only return a single `BigDecimal` value. It does not automatically create an extra `currency_code` column. If a converter returns a string such as `"125000.00|VND"`, the database still receives **one value in one column**.

| Domain Property | Representation | Physical Columns |
|---|---|---|
| `ProductCode("BK-01")` | `String("BK-01")` | `product_code` |
| `Money(125000, "VND")` via converter to string | `"125000.00|VND"` | `price` |
| `Money(125000, "VND")` via `@Embedded` | Two sub-properties | `price_amount`, `price_currency_code` |

Do not expect a normal converter to return an object with multiple fields and have the framework automatically decompose that object into multiple columns. Splitting into multiple columns is the job of mapping metadata such as `@Embedded`.

## 2. When Should You Use a Custom Converter for a Single Column?

A converter is appropriate when the domain type is a single logical value and can be represented cleanly by one database type:

- Identifiers with custom formats such as `ProductCode`, `CustomerNumber`.
- A domain status with a scalar representation such as `String` or a number.
- A measurement value with a fixed unit convention.
- A wrapper type enforcing value domain invariants, such as `EmailAddress` or `PostalCode`.

Example `ProductCode` with validation:

~~~java
package com.example.inventory;

public record ProductCode(String value) {

    public ProductCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Product code must not be blank"
            );
        }
        if (value.length() > 40) {
            throw new IllegalArgumentException(
                "Product code is too long"
            );
        }
    }
}
~~~

The domain type keeps validation rules in one place. The database stores a scalar value in a `VARCHAR` column.

## 3. Writing a Reading Converter and a Writing Converter

Spring Data uses converters in two directions:

- **Writing converter:** converts the domain type to a type writable to the database.
- **Reading converter:** converts the database type read back into the domain type.

For `ProductCode`, the two converters can be written as:

~~~java
package com.example.inventory;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class ProductCodeWritingConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}

@ReadingConverter
public class ProductCodeReadingConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source);
    }
}
~~~

The `@WritingConverter` and `@ReadingConverter` annotations clarify conversion direction. This is especially helpful when both source and target types are simple types such as `String`, `Long`, or `BigDecimal`.

### Registering the Converters

In Spring Data JDBC configuration, converters can be registered by extending `AbstractJdbcConfiguration`:

~~~java
package com.example.config;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

import com.example.inventory.ProductCodeReadingConverter;
import com.example.inventory.ProductCodeWritingConverter;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new ProductCodeReadingConverter(),
            new ProductCodeWritingConverter()
        );
    }
}
~~~

Converter configuration methods can vary across Spring Data generations; use the API matching the version managed by your project. Do not create a standalone `ConversionService` and assume Spring Data JDBC will automatically pick it up.

### Using the Domain Type in an Entity

~~~java
package com.example.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;

    @Column("product_code")
    private ProductCode productCode;

    protected Product() {
    }

    public Product(String name, ProductCode productCode) {
        this.name = name;
        this.productCode = productCode;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public ProductCode getProductCode() {
        return productCode;
    }
}
~~~

Matching schema:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    product_code VARCHAR(40) NOT NULL UNIQUE
);
~~~

When saving `Product`, the writing converter turns `ProductCode` into a string to store in `product_code`. When reading, the reading converter reconstructs `ProductCode` from the string in the column. The data still occupies one column and can be searched/indexed in SQL as a string value.

## 4. A Converter Does Not Automatically Map One Property to Multiple Columns

Consider the value object:

~~~java
public record Money(
    BigDecimal amount,
    String currencyCode
) {}
~~~

It has two independent data components:

- `amount`: the monetary amount.
- `currencyCode`: the currency code such as `VND`, `USD`, or `EUR`.

If you register a converter:

~~~java
Converter<Money, String>
~~~

then the target of the converter is a single `String`. Spring Data JDBC writes the result into the single column mapped for that property. A converter has no contract for returning "two columns", and cannot tell the framework to create both `price_amount` and `price_currency_code`.

You can serialize `Money` into JSON or a formatted string to store in one column, but that is **one column holding a composite value**. It is fundamentally different from storing amount and currency in two independent columns.

### Why Avoid Packing Multiple Values Into One String When Querying Is Needed?

Suppose you store:

~~~text
125000.00|VND
~~~

The database no longer sees amount and currency as two separate attributes. To filter by amount, validate currency, or index individual parts, the application must rely on string-splitting/JSON functions or process it in another layer. That complicates queries and can limit index and constraint usage.

If the business needs to:

- Filter all products priced above a threshold.
- Group reports by currency.
- Enforce non-negative amounts.
- Create separate indexes for amount or currency.

then two separate columns express the schema much more clearly.

## 5. Using @Embedded for Multi-Column Value Objects

`@Embedded` embeds the properties of an object into the same table as its containing entity. A single Java property such as `price` can be flattened into multiple columns based on its sub-properties.

### Money Value Object

~~~java
package com.example.inventory;

import java.math.BigDecimal;

public class Money {

    private BigDecimal amount;
    private String currencyCode;

    protected Money() {
        // For Spring Data JDBC.
    }

    public Money(BigDecimal amount, String currencyCode) {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount must be non-negative"
            );
        }
        if (currencyCode == null ||
                !currencyCode.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Currency code must contain three uppercase letters"
            );
        }
        this.amount = amount;
        this.currencyCode = currencyCode;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }
}
~~~

### Product Entity Embedding Money

~~~java
package com.example.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;

    @Embedded(
        prefix = "price_",
        onEmpty = Embedded.OnEmpty.USE_NULL
    )
    private Money price;

    protected Product() {
    }

    public Product(String name, Money price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Money getPrice() {
        return price;
    }
}
~~~

With prefix `price_`, the sub-properties are mapped as:

| Java Property | SQL Column |
|---|---|
| `name` | `name` |
| `price.amount` | `price_amount` |
| `price.currencyCode` | `price_currency_code` |

One `price` property on the entity becomes two physical columns. This is the multi-column mapping that `@Embedded` provides.

### SQL Schema

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    price_amount NUMERIC(14, 2),
    price_currency_code VARCHAR(3)
);
~~~

Both price columns allow NULL in the example because `price` may be absent. If every product must have a price, make the columns `NOT NULL` and ensure the entity always carries a valid `Money`. Schema constraints must align with the mapping's null policy.

### Sample Data

~~~sql
INSERT INTO products (
    name,
    price_amount,
    price_currency_code
) VALUES
    ('Keyboard', 1250000.00, 'VND'),
    ('Notebook', 4.50, 'USD'),
    ('Sample item', NULL, NULL);
~~~

When reading:

- Keyboard has `Money(1250000.00, "VND")`.
- Notebook has `Money(4.50, "USD")`.
- Sample item has `price == null` because the entire group of embedded columns is NULL and `USE_NULL` is configured.

## 6. Prefixes Prevent Column Name Collisions

An entity can embed multiple objects of the same type. For example, a product has a selling price and a cost price, both typed as `Money`:

~~~java
@Embedded(
    prefix = "selling_",
    onEmpty = Embedded.OnEmpty.USE_NULL
)
private Money sellingPrice;

@Embedded(
    prefix = "cost_",
    onEmpty = Embedded.OnEmpty.USE_NULL
)
private Money costPrice;
~~~

Columns created by prefix:

| Property | Amount Column | Currency Column |
|---|---|---|
| `sellingPrice` | `selling_amount` | `selling_currency_code` |
| `costPrice` | `cost_amount` | `cost_currency_code` |

Final column names also depend on the application's naming strategy and mapping configuration; when explicit schema names are needed, you can declare column names on sub-properties using `@Column`. What matters is that the two embedded properties have non-colliding column groups.

Prefixes operate at the mapping and schema levels. They do not create new relationships or tables.

## 7. Handling Null Objects, Empty Objects, and Partial Nulls

When using `@Embedded`, Spring Data JDBC needs to decide when a group of null columns means the object does not exist. `onEmpty` controls this decision:

| Configuration | All Embedded Columns Are SQL NULL | Outcome |
|---|---|---|
| `USE_NULL` | Yes | Embedded property is Java `null` |
| `USE_EMPTY` | Yes | Framework creates an instance with null/default inner properties |
| Both | At least one column is non-NULL | Framework constructs the object and maps each property |

Example with `Money`:

| `price_amount` | `price_currency_code` | `USE_NULL` |
|---:|---|---|
| NULL | NULL | `price == null` |
| 125000 | VND | `price` has both values |
| 125000 | NULL | `price` exists, `currencyCode == null` |
| NULL | USD | `price` exists, `amount == null` |

A partial-null state does not automatically turn the entire object into null. If the domain requires amount and currency to always appear together, validation and database constraints are needed to forbid partial states.

Example PostgreSQL constraint:

~~~sql
ALTER TABLE products
ADD CONSTRAINT ck_product_price_pair
CHECK (
    (price_amount IS NULL AND price_currency_code IS NULL)
    OR
    (price_amount IS NOT NULL AND price_currency_code IS NOT NULL)
);
~~~

This constraint allows the price to be completely absent or present with both components. It prevents half-populated rows that could produce an invalid `Money`.

If using `USE_EMPTY`, the embedded class must be instantiable in an empty state per mapping rules. Do not rely on `USE_EMPTY` to generate default business values; the annotation only decides whether to instantiate the object when all columns are null.

## 8. When to Use a Converter vs. @Embedded?

Choose according to the shape of the data to store:

| Requirement | Solution | Column Count |
|---|---|---:|
| `ProductCode` has only a single code value | Reading/Writing Converter | 1 |
| `EmailAddress` normalized into a single string | Converter | 1 |
| `Money` needs independently queryable amount and currency | `@Embedded` | 2 |
| `Address` needs street, city, postal code | `@Embedded` | Multiple columns |
| An object needs to be stored whole as JSON | Converter/JSON mapping per database | 1 |
| Order has many OrderItems | `@MappedCollection` | Separate child table |
| Order references another Customer aggregate | ID or `AggregateReference` | Scalar FK |
| Report JOIN across multiple tables into a DTO | Spring JDBC `RowMapper`/`ResultSetExtractor` | Multi-column result set |

### Converter

Use when the entire property has a single database representation. Examples include postal codes, product codes, and enums with custom formats.

### @Embedded

Use when the object is a value object owned by its containing entity/aggregate and its components should be stored as multiple columns in the same table. The object has no independent identity or lifecycle.

### Aggregate Relationships

If the object has its own identity, lifecycle, or repository, consider an appropriate aggregate/relationship model. Do not embed an independent entity just to avoid creating a table.

### DTOs and RowMapper

If multiple columns come from JOINs or reporting calculations, that is usually a read model. Use custom queries and mappers instead of trying to coerce a result set into a single value object via a converter.

## 9. JSON in One Column Is Still One Value

Sometimes a multi-field object is stored as JSON:

~~~json
{
  "amount": 125000,
  "currencyCode": "VND"
}
~~~

If a converter serializes the object into JSON text, the database stores the entire payload in one column such as `price_json`. This approach is useful when:

- The object's structure changes frequently.
- The application typically reads/writes the entire object together.
- The database supports JSON types and appropriate JSON queries.
- Relational constraints on individual components are not needed.

However, single-column JSON differs from having two columns `price_amount` and `price_currency_code`:

| Criterion | Single-Column JSON | Multi-Column Embedded |
|---|---|---|
| Storage | One JSON/text column | Multiple typed columns |
| Filtering by amount | Requires JSON operators or extraction | Direct SQL comparison |
| Per-component constraints | Usually more complex | Can use NOT NULL/CHECK |
| Separate per-property indexes | Depends on DB JSON/index support | Standard column indexes |
| Schema evolution | Flexible | Requires schema migrations |
| Database data types | Typically JSON/JSONB or text | NUMERIC, VARCHAR, DATE... |

Do not choose JSON simply because a converter feels easy to write. Base the decision on how the application queries, validates, and updates the components.

## 10. JdbcValue Still Represents One JDBC Value

In some cases, a writing converter needs to explicitly specify the JDBC type used when binding a value. Spring Data JDBC provides `JdbcValue` to carry a value paired with its JDBC type.

Conceptual example:

~~~java
@WritingConverter
public class ProductCodeToJdbcValueConverter
        implements Converter<ProductCode, JdbcValue> {

    @Override
    public JdbcValue convert(ProductCode source) {
        return JdbcValue.of(
            source.value(),
            JDBCType.VARCHAR
        );
    }
}
~~~

`JdbcValue` clarifies how a value is bound to JDBC, such as `VARCHAR`, `BIGINT`, or `TIMESTAMP`. It is **not a container for returning multiple columns**. A single `JdbcValue` still describes one value for one column position in a write operation.

The exact package and API of `JdbcValue` depend on the Spring Data JDBC version. Only use this mechanism when JDBC type control is needed; if a converter to a plain Java type already works properly, no extra wrapper is necessary.

## 11. Limits of One Property Spanning Multiple Columns

When using `@Embedded`, one Java property has multiple sub-properties, and each sub-property is mapped individually. However, this is not an arbitrary way to map a property to any group of columns:

- Sub-properties must be recognized and mapped by Spring Data Relational.
- Prefix/column mapping must produce non-colliding column names.
- The embedded object belongs to the table of its containing entity.
- The embedded object has no primary key of its own.
- The embedded object has no independent repository.
- You cannot use `@Embedded` to JOIN multiple tables or invoke a converter and have the result automatically decomposed into multiple columns.

If an object is nested, inner value objects can also be embedded via appropriate mapping. When doing so, manage prefixes at each level and understand the null rules for every embedded property.

If part of the data belongs in another table because there are multiple rows or a separate relationship, use `@MappedCollection` for child components owned by the aggregate or an ID reference for other aggregates. Do not use embedded mapping as a substitute for table relationships.

## 12. Changing the Schema When Moving from One Column to Multiple Columns

Suppose version one stored `Money` in a single string column:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    price_value VARCHAR(80)
);
~~~

Later you want to query amount and currency independently, so the new schema has:

~~~sql
ALTER TABLE products
ADD COLUMN price_amount NUMERIC(14, 2),
ADD COLUMN price_currency_code VARCHAR(3);
~~~

The data transition requires a migration:

1. Add the new columns as nullable.
2. Migrate legacy data from `price_value` into amount and currency according to the stored format.
3. Inspect malformed/unparseable rows.
4. Reconcile row counts and values after migration.
5. Update the entity to use `@Embedded`.
6. Point queries, indexes, and constraints to the new columns.
7. Drop the old column only after all application versions and related jobs have stopped using it.

Do not parse legacy strings assuming the delimiter always appears exactly once or that data is always valid. Migrations must handle real historical data and detect unconvertible records.

## 13. Querying and Indexing with Multi-Column Data

The advantage of `@Embedded` is that each component can be queried like a regular column:

~~~sql
SELECT id, name, price_amount, price_currency_code
FROM products
WHERE price_currency_code = 'VND'
  AND price_amount >= 1000000
ORDER BY price_amount DESC, id DESC;
~~~

Indexes can be created to match the workload:

~~~sql
CREATE INDEX idx_products_currency_amount
    ON products(price_currency_code, price_amount);
~~~

A composite index can support filtering by currency and then comparing amount. Index column order should be based on filter predicates and execution plans. Not every combination needs an index.

With a converter storing a concatenated string, equivalent queries usually require parsing strings or database-specific functions. That is more complex and can reduce the effectiveness of standard indexes.

## 14. Domain Validation and Database Constraints

Multi-column mapping does not automatically guarantee a valid value object. For example, `Money` can be read into an object with a non-null amount and a null currency if the database holds partial data.

Define rules at both layers:

- **Domain validation:** constructors/factories verify non-negative amounts, valid currency codes, and that required components appear together.
- **Database constraints:** CHECK/NOT NULL/foreign keys protect data even when writers other than the application modify the database.
- **Migration:** fix or reject historical data that fails new rules.
- **Read mapping:** handle legacy/null data intentionally rather than assuming every row is pristine.

If the schema allows a value object to be absent, all of its columns can be null together. If the object is present, all sub-columns can be required to hold values. A CHECK constraint can express the rule "all null or all non-null".

## 15. Common Pitfalls

| Mistake | Consequence | Resolution |
|---|---|---|
| Expecting a converter to return multiple columns | Mapping does not split the object into columns automatically | Use `@Embedded` for multi-property value objects |
| `Money -> String` converter when amount/currency filtering is needed | Must parse strings or use DB functions | Store amount and currency in two columns |
| Using `@Embedded` for an entity with its own identity | Blurs aggregate boundaries and lifecycles | Use appropriate aggregate/table relationships |
| Forgetting prefixes when embedding the same type multiple times | Column name collisions | Set distinct prefixes for each embedded property |
| Thinking a prefix creates a new table | Wrong schema and mapping | Embedded flattens into the containing table |
| Using `USE_NULL` with partial-null data | Object is still instantiated with null sub-properties | Validate and add a CHECK constraint if needed |
| Using primitives for nullable embedded columns | Cannot represent SQL NULL | Use wrapper/reference types |
| Using `USE_EMPTY` as business default values | Empty objects get mistaken for valid data | Define explicit factories/defaults or use `USE_NULL` |
| Storing JSON because it is easy to serialize despite frequent per-field filtering | Complex queries/indexes | Consider embedded columns |
| Thinking `JdbcValue` can hold multiple columns | Confusing JDBC value with row/object mapping | Use it only to specify one JDBC value/type |
| Using a converter to build a DTO from a JOIN | No multi-row/multi-table mapping support | Use `RowMapper`/`ResultSetExtractor` |
| Changing schema without migrating legacy data | Data lost or unreadable | Run a reconciled migration |

## 16. Practice Exercises

1. Create `ProductCode` as a record and a reading/writing converter pair with `String`.
2. Register the converters in Spring Data JDBC configuration; save and reload a Product to verify the property is materialized as `ProductCode`.
3. Create a `Money` value object containing `BigDecimal amount` and `String currencyCode`.
4. Embed Money into Product using `@Embedded(prefix = "price_")`.
5. Create a schema with `price_amount` and `price_currency_code`; save and read products priced in VND and USD.
6. Test a row where both price columns are null, then read with `USE_NULL` and `USE_EMPTY`; observe the difference.
7. Test partial-null data and decide whether the domain permits it.
8. Add a CHECK constraint ensuring both columns are null together or non-null together.
9. Write a query filtering products by currency and amount; compare with storing Money as a single string.
10. Design a migration from a string `price_value` column to two embedded columns; list how invalid records are handled.
11. Discuss when an object should be stored as single-column JSON versus flattened into multiple columns.
12. Determine when an object should be an embedded value object versus needing its own table or aggregate reference.

## 17. Key Takeaways

Spring Data JDBC custom converters convert one domain type into one database value and vice versa. They fit properties with a single scalar representation, such as validated product codes or emails. Converters do not automatically decompose a property into multiple physical columns; `JdbcValue` likewise only describes a single JDBC value along with its bind type.

When a value object needs multiple independent columns in the same table, use `@Embedded` and prefixes to map sub-properties. When data belongs in another table, use aggregate relationship modeling; when results come from JOINs/reports, use queries and DTO/RowMapper. Choose storage based on querying needs, constraints, lifecycle, and domain semantics, while explicitly defining how null and partial-null objects are handled.
