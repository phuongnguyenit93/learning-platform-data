# Do Not Treat Automatic Mapping as a Substitute for Type and Input Validation

## 1. The Core Problem: Successful Mapping Does Not Mean Valid Data

When building a data-access layer with Spring Framework, we commonly read data via `JdbcTemplate`, `BeanPropertyRowMapper`, `DataClassRowMapper`, or a hand-written `RowMapper`. These tools transfer values from SQL columns to Java properties, convert certain data types, and construct objects. However, **converting into an object does not mean the values inside that object satisfy business rules, security rules, or API contracts**.

For example, a product record can be mapped completely “successfully”:

- `sku = "SKU-002"` → Java `String`.
- `price = -7.00` → `BigDecimal("-7.00")`.
- `stock = 2` → Java `Integer(2)`.
- `status = "ACTIVE"` → Java `String`.

There is no JDBC error or mapping error, yet **a negative price** can violate the application's data contract. Similarly, a `NULL` `stock` column can map into `Integer` without throwing any exception, even though the service requires stock quantity to be present. The string `status = "UNKNOWN"` is a valid `String` by type, yet outside the supported set of statuses.

Therefore, we must separate **three distinct concerns**:

1. **Reading data:** JDBC reads columns, SQL NULLs, numbers, strings, temporals, etc. from the `ResultSet`.
2. **Mapping / type conversion:** `RowMapper` or `ConversionService` assigns values into Java fields, setters, or constructors.
3. **Contract and data validation:** validating nullability, formats, value ranges, cross-field relationships, valid enums, numeric/temporal precision, business constraints, and trust boundaries.

A program that only finishes step 2 is not necessarily doing step 3 correctly.

## 2. Data Boundaries to Distinguish

Data flows through a system in two directions; each boundary has its own validation duties.

~~~text
HTTP / message / batch input
    │ parse JSON, read raw data
    ▼
Input DTO
    │ verify syntax/types, Bean Validation, business rules
    ▼
Service / domain
    │ bind SQL parameters; never concatenate user data
    ▼
Database
    │ NOT NULL, CHECK, UNIQUE, FK, DECIMAL, transaction...
    ▼
ResultSet (data may come from legacy data / imports / migration bugs)
    │ RowMapper / BeanPropertyRowMapper / DataClassRowMapper
    ▼
Mapped Java object
    │ validate nullability, actual type, domain range, field relations
    ▼
Validated DTO / domain object
    │ do not leak JDBC handles; expose only contract-compliant data
    ▼
Service / API / consumers
~~~

Key points to remember:

- **Input validation** guards new data entering *into* the system. It covers length limits, ranges, patterns, allowlists, and cross-field rules. A JSON parser successfully converting `"5"` into a number does not guarantee `5` is accepted by business rules.
- **Database constraints** are the storage-level line of defense: NOT NULL, CHECK, FK, UNIQUE, precision bounds, and transactions. They protect data across many write paths, yet legacy schemas, imports, historical data, migrations, bypass privileges, or cross-table logic can still leave rows that violate the API contract.
- **Result mapping** turns `ResultSet` values into Java. This layer must decide whether to accept `NULL`, unfamiliar values, unknown enums, precision loss, or incomplete data.
- **Post-mapping validation** is the step verifying that the mapped object genuinely conforms to the domain/response contract. It does not happen automatically just because you used an “automatic” mapper.

Here “input data” covers both data arriving from requests and data read back from the database. A database can contain outlier or legacy rows; **never blindly assume data read from storage is always valid**.

## 3. What Does BeanPropertyRowMapper Actually Do?

Spring JDBC's `BeanPropertyRowMapper<T>` instantiates a JavaBean via its no-arg constructor and assigns matching column values into properties with public setters. It recognizes column names matching property names; `first_name` can map to `firstName` via the underscore → camelCase rule. SQL aliases can be used to control mapped names explicitly.

Example bean class:

~~~java
public class PriceRow {
    private long id;
    private String sku;
    private BigDecimal price;

    public PriceRow() {}

    public long getId() { return id; }
    public void setId(long id) { this.id = id; }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
~~~

This is an **example JavaBean definition**, assuming `java.math.BigDecimal` is imported. In a repository you might write:

~~~java
List<PriceRow> rows = jdbc.query(
        "SELECT id, sku, price FROM inventory_rows",
        BeanPropertyRowMapper.newInstance(PriceRow.class));
~~~

This is an **illustrative snippet inside a class with field `JdbcTemplate jdbc`**, requiring imports for `BeanPropertyRowMapper` and `List`. If the database contains `price = -7.00`, the mapper still constructs a `PriceRow` with price `-7.00`. There is no automatic positive-price check.

### 3.1. Type Conversion Is Not Business Validation

The mapper supports many common types: `String`, `BigDecimal`, integers, booleans, date/time types, etc., and can use `ConversionService` to convert types. A value converting successfully does **not** mean:

- The product SKU matches the required pattern.
- The price is positive and within selling limits.
- Start date is less than or equal to end date.
- The status is within the list supported by the API.
- Currency units, scale, timezone, or precision match the contract.
- Unselected properties were actually populated.
- The object satisfies `@NotNull`, `@Positive`, or `@Pattern` annotations if no validator has been invoked.

A failed conversion can throw an exception, whereas a successful conversion only confirms **the type could be converted**, not that **the value is valid**.

### 3.2. Unmapped Properties Can Keep Default Values

By default, `BeanPropertyRowMapper` does not require all writable properties of the bean to be populated. If you forget to select a column in `SELECT`, the corresponding Java field may keep `null`, `0`, or a default value. The `setCheckFullyPopulated(true)` flag helps catch some cases where properties were left unmapped, yet **does not check domain rules** or guarantee the SQL column is non-NULL.

Example:

~~~java
BeanPropertyRowMapper<PriceRow> mapper =
        BeanPropertyRowMapper.newInstance(PriceRow.class);
mapper.setCheckFullyPopulated(true);
~~~

A mapper strict about **property population completeness** will still accept a price of `-7.00` as long as the `price` property received that value.

### 3.3. NULL Into Primitives Is Easily Overlooked

When a SQL NULL column maps into a Java primitive like `int`, the default mapper normally throws `TypeMismatchException` because it cannot assign null to a primitive. There is an option `setPrimitivesDefaultedForNullValue(true)` to skip that null and leave the primitive at its default or constructor-initialized value. However, enabling this option risks **turning missing information into 0 or false**, distorting business semantics.

For instance, `stock = NULL` does not mean `stock = 0`. For nullable data, use `Integer`/wrappers so null stays distinguishable, then decide explicitly: allow `null`, apply an intentional fallback, or reject the record.

### 3.4. Records Need a Different Mapper, and Still Need Validation

`BeanPropertyRowMapper` is for JavaBeans with setters; for Java `record`s or data classes with value-accepting constructors, Spring provides `DataClassRowMapper`. It maps by constructor parameters, yet still **does not automatically run all business rules**. Record constructors can self-validate, or the service can invoke a validator explicitly—never assume the mapper alone suffices to enforce all invariants.

## 4. Runnable Example: Comparing Automatic Mapping vs. Validated Mapping

The following Java 21 + Spring Boot 3.3.5 + H2 example simulates legacy data with one good row and several invalid rows. To observe the problem, the demo table **deliberately omits CHECK/NOT NULL constraints on business data columns**. In production, tighten database constraints after cleaning legacy data; this example does not encourage storing bad data.

Application business rules:

- `sku` must match the pattern `SKU-[0-9]{3}`.
- `price` is a **non-null** `BigDecimal` **greater than 0**.
- `stock` must be **non-null** and **non-negative**. Stock of 0 is valid in this model; NULL means “unknown”, not 0.
- `status` may only be `ACTIVE` or `INACTIVE`, in exact uppercase.
- `id` must be a positive integer.

When encountering an invalid record, the data-access layer does not silently patch it, does not clamp negative prices to 0, and does not silently fall back to a default status: it reports an error with the offending id and field.

### 4.1. Project Structure

~~~text
strict-mapping-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/mapping/
    │   ├── MappingApplication.java
    │   ├── InventoryRow.java
    │   ├── ProductStatus.java
    │   ├── ProductView.java
    │   ├── InvalidCatalogDataException.java
    │   └── InventoryRepository.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'strict-mapping-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:strictmapping;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE inventory_rows (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40),
    price DECIMAL(12, 2),
    stock INTEGER,
    status VARCHAR(32)
);
~~~

File `src/main/resources/data.sql`:

~~~sql
INSERT INTO inventory_rows(id, sku, price, stock, status) VALUES
    (1, 'SKU-001', 125.50, 3, 'ACTIVE'),
    (2, 'SKU-002', -7.00, 2, 'ACTIVE'),
    (3, 'SKU-003', 50.00, NULL, 'ACTIVE'),
    (4, 'SKU-004', 15.00, 1, 'UNKNOWN'),
    (5, 'bad-sku', 19.00, 1, 'ACTIVE');
~~~

Record 1 is valid. Record 2 is invalid due to a negative price; 3 is missing stock; 4 contains an out-of-enum status; 5 has an invalid SKU pattern. All five remain readable SQL rows with type-compatible SQL columns. That is the difference between **storable/mappable** and **business-valid data**.

### 4.2. Bean for Automatic Mapping

File `src/main/java/example/mapping/InventoryRow.java`:

~~~java
package example.mapping;

import java.math.BigDecimal;

public class InventoryRow {
    private long id;
    private String sku;
    private BigDecimal price;
    private Integer stock;
    private String status;

    public InventoryRow() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public Integer getStock() {
        return stock;
    }

    public void setStock(Integer stock) {
        this.stock = stock;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

The bean has a no-arg constructor and setters, with property names matching SQL columns. `Integer stock` allows NULL information to be preserved. There is no positive-price validation inside the setter; we deliberately observe that the auto mapper can map invalid rows.

### 4.3. Domain View Accepting Only Valid State

File `src/main/java/example/mapping/ProductStatus.java`:

~~~java
package example.mapping;

public enum ProductStatus {
    ACTIVE,
    INACTIVE
}
~~~

File `src/main/java/example/mapping/ProductView.java`:

~~~java
package example.mapping;

import java.math.BigDecimal;

public record ProductView(
        long id,
        String sku,
        BigDecimal price,
        int stock,
        ProductStatus status) {
}
~~~

This is a DTO containing only validated types. A record does not validate data automatically just by being a record; constraints must be enforced in a mapper/constructor/factory or an explicit validation step. In this example, we let the mapper perform validation before creating `ProductView`.

File `src/main/java/example/mapping/InvalidCatalogDataException.java`:

~~~java
package example.mapping;

public class InvalidCatalogDataException extends RuntimeException {
    public InvalidCatalogDataException(String message) {
        super(message);
    }
}
~~~

This is an invalid-data/business exception, **distinct** from JDBC errors. It helps callers distinguish “the database could not be queried” from “the database returned a row violating the application's contract”.

### 4.4. Repository: Auto Mapper vs. Validating Custom Mapper

File `src/main/java/example/mapping/InventoryRepository.java`:

~~~java
package example.mapping;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;

import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {
    private static final String SELECT = """
            SELECT id, sku, price, stock, status
            FROM inventory_rows
            WHERE id = ?
            """;

    private final JdbcTemplate jdbc;

    public InventoryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public InventoryRow findAutomatically(long id) {
        return jdbc.queryForObject(
                SELECT,
                BeanPropertyRowMapper.newInstance(InventoryRow.class),
                id);
    }

    public ProductView findStrictly(long id) {
        return jdbc.queryForObject(SELECT, this::mapAndValidate, id);
    }

    private ProductView mapAndValidate(ResultSet rs, int rowNumber)
            throws SQLException {

        long id = rs.getLong("id");
        if (id <= 0) {
            throw invalid(id, "id must be greater than 0");
        }

        String sku = rs.getString("sku");
        if (sku == null || !sku.matches("SKU-[0-9]{3}")) {
            throw invalid(id, "invalid sku format: " + sku);
        }

        BigDecimal price = rs.getBigDecimal("price");
        if (price == null || price.signum() <= 0) {
            throw invalid(id, "price must be greater than 0");
        }

        int stock = rs.getInt("stock");
        if (rs.wasNull()) {
            throw invalid(id, "stock must not be NULL");
        }
        if (stock < 0) {
            throw invalid(id, "stock must not be negative");
        }

        String statusText = rs.getString("status");
        if (statusText == null) {
            throw invalid(id, "status must not be NULL");
        }

        ProductStatus status = switch (statusText) {
            case "ACTIVE" -> ProductStatus.ACTIVE;
            case "INACTIVE" -> ProductStatus.INACTIVE;
            default -> throw invalid(
                    id, "invalid status: " + statusText);
        };

        return new ProductView(id, sku, price, stock, status);
    }

    private static InvalidCatalogDataException invalid(
            long id, String problem) {
        return new InvalidCatalogDataException(
                "id=" + id + ", " + problem);
    }
}
~~~

Technical notes:

- `BeanPropertyRowMapper.newInstance(InventoryRow.class)` populates compatible values into the bean **without knowing** that price must be positive.
- `getBigDecimal("price")` preserves monetary values in decimal form, avoiding unnecessary binary floating-point conversion via `double`.
- `ResultSet.getInt("stock")` returns 0 even on SQL NULL; **you must call `rs.wasNull()` immediately after the corresponding read** to distinguish NULL from 0. If using `rs.getObject("stock", Integer.class)` on a driver with proper support, you can hold a nullable wrapper and validate it.
- `switch` expresses an explicit status allowlist. If the database adds a new status, the code does not silently accept it and instead raises an error so the contract can be updated deliberately.
- `matches("SKU-[0-9]{3}")` checks the full SKU format, not merely that the value is a `String`.
- Each exception includes id and field details for debugging/quarantining source data. In applications handling sensitive data, do not print full raw input values into public logs/HTTP responses; separate internal diagnostics from client-facing messages.
- `queryForObject` requires exactly one row: zero rows throws `EmptyResultDataAccessException`, and multiple rows throw the corresponding exception. That differs from a row existing yet being **invalid**. The demo only queries existing IDs, and the primary key guarantees at most one row.

### 4.5. Program to Observe Behavior

File `src/main/java/example/mapping/MappingApplication.java`:

~~~java
package example.mapping;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MappingApplication {
    public static void main(String[] args) {
        SpringApplication.run(MappingApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(InventoryRepository repo) {
        return args -> {
            InventoryRow raw = repo.findAutomatically(2);
            System.out.println("Auto id=2: price="
                    + raw.getPrice().toPlainString());

            ProductView good = repo.findStrictly(1);
            System.out.printf(
                    "Valid: id=%d, sku=%s, price=%s, stock=%d, status=%s%n",
                    good.id(),
                    good.sku(),
                    good.price().toPlainString(),
                    good.stock(),
                    good.status());

            for (long id = 2; id <= 5; id++) {
                try {
                    repo.findStrictly(id);
                } catch (InvalidCatalogDataException ex) {
                    System.out.println(ex.getMessage());
                }
            }
        };
    }
}
~~~

Using JDK 21 and a Gradle version supporting Java 21 (e.g., Gradle 8.5), run:

~~~bash
gradle bootRun
~~~

Lines **printed by the application**, excluding Gradle build output:

~~~text
Auto id=2: price=-7.00
Valid: id=1, sku=SKU-001, price=125.50, stock=3, status=ACTIVE
id=2, price must be greater than 0
id=3, stock must not be NULL
id=4, invalid status: UNKNOWN
id=5, invalid sku format: bad-sku
~~~

The first line proves the auto mapper **does not catch a negative price**. The next five lines prove a custom `RowMapper` can block bad data right at the read boundary and hand callers a `ProductView` with application-verified invariants.

This application is designed to demonstrate fail-fast handling of bad records. A batch-processing system may instead want to **quarantine** bad rows, record error codes, skip per approved policy, and continue processing other rows. Never silently turn `-7.00` into 0 or convert `UNKNOWN` into `ACTIVE`.

## 5. Why Must Both Types and Values Be Checked?

### 5.1. SQL NULL and Java Primitives

A column with SQL NULL is not equivalent to 0, false, or an empty string. When reading an integer:

~~~java
int count = rs.getInt("stock");
if (rs.wasNull()) {
    throw new IllegalStateException("stock must not be NULL");
}
~~~

This is an **illustrative RowMapper snippet**, assuming an open `ResultSet rs`. `wasNull()` only reflects the most recent column read, so call it immediately after `getInt`. If null carries valid meaning, use `Integer` or `Optional` in the appropriate API rather than silently replacing null with 0.

`BeanPropertyRowMapper`'s `primitivesDefaultedForNullValue` option can turn nulls into default values on a bean. Only use it when you understand the consequences, never just to “make it run”.

### 5.2. BigDecimal, Precision, and Units

Money should use `DECIMAL`/`NUMERIC` in the database and `BigDecimal` in Java when exact decimal arithmetic is needed. Avoid routing through `float`/`double` because it can introduce binary rounding errors. Do not use `new BigDecimal(0.1)` to represent exact `0.1`; when constructing from decimal digits, use `new BigDecimal("0.1")` or an appropriate factory.

You still must validate:

- `price != null` and `price.signum() > 0` if prices must be positive.
- Upper bounds and currency unit rules.
- Scale and rounding policy if converting to minor units; do not arbitrarily call `setScale(2)` with uncontrolled rounding.
- A `DECIMAL(12,2)` column does not know on its own the policy “selling price must be greater than 0”.

### 5.3. Enums and Unexpected Statuses

Successfully reading a string does not mean the business attribute is valid. Use an explicit allowlist of statuses or `Enum.valueOf` with error handling; **do not** silently assign a default status when encountering a new value. If the schema evolves to add statuses, the read layer must decide compatibility contracts, migrations, and rollout order.

`Enum.valueOf` is case-sensitive. Calling `trim().toUpperCase()` can be useful if the contract specifies normalization, yet it can also mask bad data. Decide deliberately upfront.

### 5.4. Strings, Identifiers, and Unicode

Validate empty strings, blanks, lengths, patterns, normalization, and domain semantics. Do not use one generic pattern for every field. For Unicode data, length rules by code points, grapheme/display characters, or database storage limits can differ; pick the criterion matching your application.

A `sku` or `email` of valid `String` type can still be malformed. For user input, validate before writing; for data read from legacy tables or import systems, re-validate against the usage contract.

### 5.5. Dates, Times, and Timezones

Mapping `DATE` to `LocalDate` normally represents only a calendar date. `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, `Instant`, `LocalDateTime`, and `OffsetDateTime` **are not interchangeable**. Examine the database, JDBC driver, timezone, offset, and conversion rules explicitly. An automatic conversion that runs without error can still shift timezones or misrepresent “event instant” semantics.

For time-range data, check `start <= end`, non-future constraints if required by contract, and DST/timezone edge cases where relevant.

### 5.6. SQL Types and Value Domains

A SQL `INTEGER` converts to Java `int`, yet business rules might only allow 0–100; a `VARCHAR` can store any string, whereas the API allows only an allowlisted set. Data types are a **necessary** condition, not a **sufficient** condition.

Enforce invariants in DTO constructors/factories, explicit mappers, or a validation layer—where business knowledge lives—and add `CHECK`/`NOT NULL`/`UNIQUE` in the database where appropriate.

## 6. Input Validation Before Writing Must Not Be Skipped Either

In the reverse direction, request/input DTOs can be parsed into Java objects and passed to repositories. Spring MVC JSON binding, setter binding, `ConversionService`, or CSV parsing change data shape; they **do not replace validation**.

A request can contain `price = -7.00` that parses cleanly into `BigDecimal`. If the endpoint uses Jakarta Bean Validation, you can declare:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;

public record CreateProductRequest(
        @NotBlank
        @Pattern(regexp = "SKU-[0-9]{3}")
        String sku,

        @NotNull
        @Positive
        BigDecimal price,

        @NotNull
        @PositiveOrZero
        Integer stock) {
}
~~~

This is an **illustrative request definition**, not part of the console application in Section 4; running Bean Validation requires `spring-boot-starter-validation` (or a compatible provider) and **triggering validation** at the entrypoint, such as `@Valid` on a Spring MVC request parameter or explicitly calling `jakarta.validation.Validator.validate(...)`. Merely placing annotations on a record without running a validator performs no check.

In the service layer, continue enforcing database-related rules, access permissions, and business preconditions, since simple per-field constraints do not cover everything.

### Parameter Binding Solves a Different Threat

Never concatenate user strings into SQL:

~~~java
// Wrong: user input alters SQL structure.
String sql = "SELECT * FROM inventory_rows WHERE sku = '" + inputSku + "'";
~~~

Use parameter binding:

~~~java
List<InventoryRow> rows = jdbc.query(
        "SELECT id, sku, price, stock, status "
        + "FROM inventory_rows WHERE sku = ?",
        BeanPropertyRowMapper.newInstance(InventoryRow.class),
        inputSku);
~~~

Both snippets are **illustrative inside a repository with `JdbcTemplate jdbc` and `inputSku`**, not standalone sources. Parameter binding prevents data from becoming SQL syntax in value positions; it does **not** verify that the SKU matches a pattern or that the caller is authorized. Also, placeholders cannot substitute directly for table/column names; dynamic identifiers require a separate allowlist.

### Defense in Depth at the Database

After cleaning bad rows in a real environment, you can add:

~~~sql
ALTER TABLE inventory_rows
    ALTER COLUMN price SET NOT NULL;

ALTER TABLE inventory_rows
    ADD CONSTRAINT chk_price_positive CHECK (price > 0);

ALTER TABLE inventory_rows
    ADD CONSTRAINT chk_stock_nonnegative
    CHECK (stock IS NOT NULL AND stock >= 0);

ALTER TABLE inventory_rows
    ADD CONSTRAINT chk_status_allowed
    CHECK (status IN ('ACTIVE', 'INACTIVE'));
~~~

This is a **proposed migration for an already-clean schema**, not meant to run against the intentionally invalid dataset in Section 4 because the violating rows would cause migration to fail. `ALTER TABLE`/`CHECK` syntax varies across database engines; test against the target database. `CHECK` constraints must also account for SQL NULL semantics—for example, `CHECK (stock >= 0)` alone can allow NULLs under SQL three-valued logic; use `NOT NULL` or explicit predicates.

Database constraints and application-side validation **complement each other** rather than replacing one another.

## 7. Three Strategies for Handling Mapped Data

### 7.1. Fail Fast

For results used in billing, critical decisions, or order state transitions, it is best to reject invariant-violating objects right at the read boundary. Throw an exception with specific id/field details so the service can choose an appropriate response/log. That is the custom `RowMapper` strategy in the demo.

### 7.2. Validation Immediately After Automatic Mapping

If you want to leverage `BeanPropertyRowMapper`, you can map into an intermediate bean and validate **immediately afterward**:

~~~java
InventoryRow raw = jdbc.queryForObject(
        "SELECT id, sku, price, stock, status "
        + "FROM inventory_rows WHERE id = ?",
        BeanPropertyRowMapper.newInstance(InventoryRow.class),
        id);

// An explicit validation step is required before producing a safe DTO.
ProductView checked = validatorOrFactory.validateAndConvert(raw);
~~~

This is **illustrative code**; `validatorOrFactory` merely denotes an application-written validation component, not a built-in Spring API, and is not standalone runnable. If using Jakarta Validator, invoke the validator or integrate at the appropriate boundary. Pros: less mapping boilerplate. Cons: temporarily instantiates an invalid intermediate object, so never let that object leak into services before validation.

### 7.3. Structured Error Results for Batch/Import

When synchronizing thousands of rows, failing fast on the first row may be undesirable. Build a `ValidationResult`/error DTO separating valid rows from errors: row key, field, reason, timestamp, source. This enables quarantine, metrics, and controlled data remediation. Still, never “guess” valid values just to keep the job running. Define error thresholds, observability, and clear job rollback policies.

## 8. Verifying Schema Drift, Aliases, and Mapping Completeness

An automatic mapper only knows the selected columns and assignable setters. When schemas or APIs evolve, stay alert for:

- **Column name differs from property name:** e.g., `product_code` vs. `sku` will not match automatically. Use `AS sku` or an explicit mapper.
- **Forgotten SELECT field:** the object holds default property values; `setCheckFullyPopulated(true)` catches missing mappings for writable properties yet does not guarantee non-null values.
- **Extra columns:** the mapper can ignore columns without matching properties; convenient, yet can hide contract drift if tests do not cover it.
- **Duplicate column names/aliases:** two columns with the same name create ambiguous mapping; write explicit column lists and unique aliases.
- **Using `SELECT *`:** schema changes alter output and cost unpredictably; select an explicit column list and test mapping.
- **Migration data types:** widening `INT` to `BIGINT` can overflow Java `int`; `DECIMAL` to `DOUBLE` loses precision; changing timestamp timezone alters semantics. Test at the boundaries.
- **New nullable columns:** use wrappers/`Optional` per contract, never silently treat `0`/`null`/empty as equivalent.

When upgrading schemas or changing mappers, run real integration tests against the target database (or a sufficiently close compatible one), rather than mocking `ResultSet` alone since drivers differ in conversions, generated keys, and timezones.

## 9. Which Tests Prove Validation Is Real?

A solid test suite should cover both **happy paths and invalid data**:

| Input / read data | Expected reaction | Bug that occurs if trusting auto-mapping alone |
| --- | --- | --- |
| Price 125.50, stock 3, status ACTIVE | Returns valid DTO | None. |
| Price -7.00 | Rejected because price is not positive | Mapper accepts negative `BigDecimal` and returns object normally. |
| Price NULL | Rejected or handled as missing data per contract | Bean with `price=null` can leak into pricing logic. |
| Stock NULL | Rejected or intentionally retained as unknown | Can be misinterpreted as `stock=0`. |
| Stock = -1 | Rejected as negative | Converts to `Integer` cleanly yet violates domain. |
| Status UNKNOWN | Reports unsupported status | Valid `String` yet meaningless. |
| Malformed SKU pattern | Reports format error | `String` pattern is never checked by mapper. |
| No row found | Raises appropriate not-found | `queryForObject` may throw `EmptyResultDataAccessException`. |
| Missing SELECT column | Detects incomplete mapping | Bean holds null/defaults unnoticed. |
| Unconvertible type | Conversion error handled/observed | Never catch exception and substitute a default value. |
| Input with SQL characters | Bind parameter treats it as data | SQL string concatenation risks injection. |

Specific testing suggestions:

1. **Unit tests** on factories/validators for nulls, negatives, bad patterns, unknown enums, and boundary values. No database needed for pure logic.
2. **Integration tests** on JDBC/H2 or a real database with deliberate schemas and rows. Verify the strict mapper accepts valid rows and rejects each error case.
3. **Transaction tests** verifying exceptions bubbling through services trigger rollbacks as designed; failed validation leaves no inconsistent writes.
4. **Contract tests** when altering schemas/aliases: which DTO fields are selected, what nullability is permitted, and which schema version is supported.
5. **Observability**: track invalid row counts by field/source, log with IDs and appropriate tracing without exposing sensitive data, and alert before bad data spreads into APIs.

## 10. Misconceptions to Avoid

**“If mapping throws no exception, the data is valid.”** False: `-7.00` in the example converted to `BigDecimal` without error.

**“BeanPropertyRowMapper already enforces @NotNull/@Positive.”** False: the mapper only maps fields; Bean Validation must be enabled or invoked explicitly.

**“checkFullyPopulated validates all business data.”** False: that flag checks property coverage, not prices, patterns, cross-field rules, or non-null values.

**“Enabling primitivesDefaultedForNullValue is a safe fix for nulls.”** Not always: it can turn unknown values into default primitive values, skewing results.

**“The database uses DECIMAL, so all prices are valid.”** False: the storage type permits negative values unless constraints/business rules forbid them.

**“All unknown enums should default to UNKNOWN or ACTIVE.”** Only valid if the contract defines a fallback; never invent one implicitly.

**“Data already in the database can be trusted.”** Historical data, imports, migrations, and other producers may not obey newer rules.

**“Catching every exception and returning defaults improves stability.”** Usually hides bugs, loses data, and drives wrong business decisions; classify errors and define fallback policies explicitly.

**“Validation belongs only in controllers.”** Controllers validate incoming requests, yet repositories/services must also guard contracts when consuming data from external or legacy sources.

**“SQL bind parameters are enough to guarantee all input is valid.”** Binding prevents SQL injection in value positions; it does not check domain validity or authorization.

## 11. Safe Mapping Layer Design Checklist

- [ ] `SELECT` lists explicit columns and aliases, never relying on `SELECT *` unchecked.
- [ ] Java types match SQL types and required ranges; never lose precision/scale/timezone silently.
- [ ] `NULL` is handled as a distinct state; primitives are used only when columns are strictly non-null by contract.
- [ ] Use `BigDecimal` for exact decimal data, especially money; define clear rounding rules.
- [ ] Validate value domains: positive/non-negative, patterns, enum allowlists, bounds, and cross-field rules.
- [ ] `BeanPropertyRowMapper`, `DataClassRowMapper`, `ConversionService`, or JSON binding are never treated as validators.
- [ ] Run Bean Validation or explicit domain validation at appropriate boundaries.
- [ ] Enforce DB constraints where appropriate, while still validating read contracts for untrusted/legacy sources.
- [ ] Data enters SQL via bind parameters; dynamic identifiers, if any, use an allowlist.
- [ ] Invalid objects never silently pass to services/APIs; fail-fast/quarantine/fallback policies are explicit.
- [ ] Test valid data, out-of-range values, NULLs, type mismatches, schema drift, and adversarial inputs.
- [ ] Returned results are materialized DTOs/value objects, exposing neither JDBC handles nor unvalidated data.

**Conclusion:** Automatic mapping solves **moving values from a `ResultSet` into a Java object**. Type validation, NULL handling, precision, and business rules solve a separate problem: **verifying whether that object is trustworthy to use**. A resilient system needs both, combined with input validation and database constraints.

### References

- Spring Framework — JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — BeanPropertyRowMapper API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Framework — DataClassRowMapper API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/core/validation.html
- Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
