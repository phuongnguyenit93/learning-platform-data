# Mapping Enums with STRING, ORDINAL, and Ordering Change Risks

## Objectives

An enum in Java represents a finite set of values, such as order statuses `PENDING`, `PAID`, `CANCELLED`. When persisting an entity with JPA, enum values must be converted into a data type the database can store. JPA supports two standard mapping modes via `@Enumerated`: `EnumType.STRING` and `EnumType.ORDINAL`.

Choosing the wrong mapping mode can cause existing data to be interpreted as different statuses after adding, removing, or reordering enum constants. This lesson explains how data is stored, why `ORDINAL` is especially sensitive to ordering, the limits of `STRING`, and how to use `AttributeConverter` when stable storage codes are needed.

## 1. How are enums stored in the database?

Suppose Java has an enum:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
```

JPA does not store an enum object as a Java object. The provider converts the value into column data in the database and restores it when reading the entity.

| Mapping mode | Java value | Typically stored value |
| --- | --- | --- |
| `EnumType.STRING` | `PENDING` | String `PENDING` |
| `EnumType.ORDINAL` | `PENDING` | Number `0` |

`STRING` stores the result of `Enum.name()`. `ORDINAL` stores the result of `Enum.ordinal()`, which is the zero-based position in the enum declaration. These two modes behave differently when source code changes.

## 2. EnumType.STRING

Declare `@Enumerated(EnumType.STRING)` on the entity attribute:

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private OrderStatus status;
}
```

If `status` is `OrderStatus.PENDING`, the database stores the string `PENDING`. When read back, the JPA provider finds the enum constant with the matching name and restores `OrderStatus.PENDING`.

### Advantages

- Database values are readable and easy to inspect via SQL.
- Adding a new constant at any position does not alter how previously stored strings are interpreted.
- The order of constants in the Java file does not participate in stored data.
- Logs, reports, and exported data are usually easier to understand than ordinal numbers.

### Remaining risks

`STRING` depends on the constant's exact name. If `PENDING` is renamed to `WAITING`, existing rows storing `PENDING` do not update automatically. When reading them, the provider cannot find an enum constant named `PENDING` and entity hydration can fail.

Deleting a constant causes a similar problem if the database still contains that value. Changing uppercase/lowercase casing is also a data change because names are stored verbatim via `name()`.

`@Enumerated(EnumType.STRING)` does not call `toString()` when persisting. Overriding `toString()` only changes Java object display formatting; it does not change the string JPA writes to the column.

### Schema considerations

The column should be wide enough for the longest constant name. Set `length` explicitly so generated schemas have predictable sizing:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 24)
private OrderStatus status;
```

If you add a constant whose name exceeds the column limit, write operations can fail due to value truncation/overflow. Update the schema before or alongside the application version that uses the new constant.

## 3. EnumType.ORDINAL

Declaring `@Enumerated(EnumType.ORDINAL)` stores the enum's ordinal index:

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.ORDINAL)
    @Column(nullable = false)
    private OrderStatus status;
}
```

With the initial declaration:

```java
public enum OrderStatus {
    PENDING,    // ordinal = 0
    PAID,       // ordinal = 1
    CANCELLED   // ordinal = 2
}
```

The database stores `PENDING` as `0`, `PAID` as `1`, and `CANCELLED` as `2`. On read, the JPA provider uses that number as an index to look up the constant in the current enum.

### Why does reordering corrupt data?

Suppose a later version edits the enum to:

```java
public enum OrderStatus {
    PENDING,    // ordinal = 0
    CANCELLED,  // ordinal = 1
    PAID        // ordinal = 2
}
```

Existing data in the database stays untouched. Rows with value `1` previously meant `PAID`, but with the new code they are read as `CANCELLED`. There is not necessarily an exception: worse, the program keeps running while misinterpreting business state.

### Risky changes

| Enum change | Impact with ORDINAL |
| --- | --- |
| Inserting a constant in the middle | Subsequent constants shift ordinals; old data can turn into different statuses. |
| Reordering constants | Ordinals change to match new positions; old data is misinterpreted. |
| Deleting a constant in the middle | Trailing constants shift positions; old data can become different values. |
| Deleting the last constant | Old ordinals may exceed the current constant count and cause read failures. |
| Appending a constant at the end | Old ordinals stay intact, but the new value must be supported by every application version reading that data. |
| Renaming a constant while keeping position | ORDINAL still reads by position, so data maps to the new name; business meaning may have changed. |

Therefore, `ORDINAL` is only safe when the constant set and its ordering remain immutable across the entire lifetime of the data. An "append-only at the end" rule reduces some risk but still demands strict governance over deletions, meaning changes, and multi-version compatibility.

### What is JPA's default if @Enumerated is omitted?

Under Jakarta Persistence, if an enum attribute has neither `@Enumerated` nor an applied converter, the default mapping mode is `ORDINAL`. Therefore, do not rely on defaults when reading entity code; state your intent explicitly:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

Explicitly writing the annotation lets reviewers immediately see the storage format and avoids accidental ordinal usage.

## 4. Comparing STRING and ORDINAL

| Criterion | STRING | ORDINAL |
| --- | --- | --- |
| Stored data | Constant name | Position index |
| Readable in SQL | Yes | No, must cross-check enum order |
| Inserting constant in the middle | Does not alter old strings | Can alter meaning of old numbers |
| Renaming constant | Requires data migration or legacy name compatibility | Keeps number if position unchanged, though meaning still needs evaluation |
| Deleting constant | Must handle rows still holding the old name | Can shift ordinals of following constants or cause errors |
| Storage size | Usually larger | Usually smaller |
| Stability during refactoring | Better for ordering, depends on name | Very sensitive to ordering |

For most long-lived business enums, `STRING` is easier to maintain and less risky than `ORDINAL`. If you need a stored value that remains stable even when renaming constants, use an `AttributeConverter` with explicit codes.

## 5. Using AttributeConverter to store stable codes

`AttributeConverter<X, Y>` lets you define how Java type `X` converts to database type `Y` and back. This fits cases where stored values are stable business codes such as `P`, `S`, `C`, independent of enum constant names or ordering.

Example enum with dedicated codes:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("S"),
    CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return switch (code) {
            case "P" -> PENDING;
            case "S" -> PAID;
            case "C" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unknown OrderStatus code: " + code);
        };
    }
}
```

Converter:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.code();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String dbData) {
        return dbData == null ? null : OrderStatus.fromCode(dbData);
    }
}
```

Entity using the converter:

```java
@Convert(converter = OrderStatusConverter.class)
@Column(name = "status_code", nullable = false, length = 1)
private OrderStatus status;
```

The database stores `P`, `S`, or `C`. Renaming `PENDING` to `WAITING` does not alter stored data as long as code `P` is preserved and the converter still maps `P` to the new constant.

Do not combine `@Enumerated` and `@Convert` on the same attribute. The converter is the mechanism responsible for converting that attribute.

### Why are stable codes useful?

- Constant names can be renamed for clearer code without migrating data.
- Enum declaration order does not affect stored codes.
- Compact codes can preserve compatibility with external integrations or data contracts.
- Legacy codes, deprecated codes, and conversion rules can be actively controlled.

### Converter design rules

1. Each code must be unique and stable; never reuse a retired code for a new meaning.
2. Handle `null` explicitly in both directions.
3. Decide an intentional policy for unknown codes. Throwing an exception surfaces bad data; do not silently assign a default status that could mask errors.
4. Keep column length appropriate and add constraints if the schema should restrict the code set.
5. Never change a published code just because you want to rename an enum constant.
6. Only use `@Converter(autoApply = true)` when every attribute of that Java type must share the same storage format. For enums with multiple representations, attach `@Convert` explicitly per field.

## 6. Strategy for choosing a mapping approach

Choose based on data lifetime and compatibility requirements:

- **Internal enums with long-lived data:** prefer `@Enumerated(EnumType.STRING)`.
- **Enums with stable business codes or external system integrations:** use `AttributeConverter`.
- **Technical enums with immutable order, used only in transient data or tightly controlled lifecycles:** `ORDINAL` may be considered, but annotate explicitly and add tests guarding the order.

Do not pick `ORDINAL` just for a smaller column or because you think an enum will never change. Enums frequently evolve as business requirements grow; database data often outlives many versions of source code.

## 7. Runnable example with Java 17+, Spring Boot, and H2

This example stores `OrderStatus` using stable codes via `AttributeConverter`, then reads it back through Spring Data JPA. The project uses Spring Boot 3.4.5, Java 17, and an H2 in-memory database.

### Project structure

```text
enum-mapping/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/enummapping/
        │   ├── EnumMappingApplication.java
        │   ├── OrderStatus.java
        │   ├── OrderStatusConverter.java
        │   ├── PurchaseOrder.java
        │   └── PurchaseOrderRepository.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>enum-mapping</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:enumdb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`create-drop` is only suitable for in-memory experimental databases. Production should manage schemas with Flyway or Liquibase.

### `OrderStatus.java`

```java
package com.example.enummapping;

public enum OrderStatus {
    PENDING("P"),
    PAID("S"),
    CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return switch (code) {
            case "P" -> PENDING;
            case "S" -> PAID;
            case "C" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unknown OrderStatus code: " + code);
        };
    }
}
```

### `OrderStatusConverter.java`

```java
package com.example.enummapping;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.code();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String dbData) {
        return dbData == null ? null : OrderStatus.fromCode(dbData);
    }
}
```

### `PurchaseOrder.java`

```java
package com.example.enummapping;

import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = OrderStatusConverter.class)
    @Column(name = "status_code", nullable = false, length = 1)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(OrderStatus status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

### `PurchaseOrderRepository.java`

```java
package com.example.enummapping;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

Spring Data JPA translates the enum parameter of `findByStatus` through the attribute's mapping. With the converter above, the value bound to the database is the corresponding code.

### `EnumMappingApplication.java`

```java
package com.example.enummapping;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EnumMappingApplication {
    public static void main(String[] args) {
        SpringApplication.run(EnumMappingApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(PurchaseOrderRepository repository) {
        return args -> {
            PurchaseOrder saved = repository.saveAndFlush(
                    new PurchaseOrder(OrderStatus.PENDING));

            PurchaseOrder loaded = repository.findById(saved.getId())
                    .orElseThrow();

            System.out.println("Database code for PENDING: "
                    + loaded.getStatus().code());
            System.out.println("Loaded status: " + loaded.getStatus());
            System.out.println("PENDING orders: "
                    + repository.findByStatus(OrderStatus.PENDING).size());
        };
    }
}
```

### Running the program

```bash
mvn spring-boot:run
```

Application output:

```text
Database code for PENDING: P
Loaded status: PENDING
PENDING orders: 1
```

In the database, the `status_code` column stores `P`. When reading the entity, the converter converts `P` back to `OrderStatus.PENDING`. If you rename the constant in Java while keeping code `P`, stored data is still read properly.

## 8. Migrations when changing mapping modes

Switching a field from ORDINAL to STRING or a converter is a data format change, not just an annotation edit. If the database already holds data, perform a controlled data migration.

### From ORDINAL to STRING

Suppose the current enum order is `PENDING(0)`, `PAID(1)`, `CANCELLED(2)` and the legacy column is numeric. You can use an expand-and-contract workflow:

1. Audit enum constants and verify the meaning of every ordinal currently existing in data.
2. Add a new string column, e.g. `status_text`, temporarily nullable.
3. Backfill with an explicit mapping from ordinal to name or code. Do not use a newer version's enum order if ordering ever changed.
4. Verify row counts, null values, unrecognized values, and reconcile statuses.
5. Deploy application versions reading/writing the new format. In rolling deployments, design a compatibility phase so old and new versions do not write mutually incompatible formats.
6. After all instances have switched and data is verified, switch the application to the new column, then drop the old column in a separate migration.

Illustrative backfill example once the legacy mapping is confirmed accurate:

```sql
update purchase_orders
set status_text = case status
    when 0 then 'PENDING'
    when 1 then 'PAID'
    when 2 then 'CANCELLED'
    else null
end;
```

Do not run this SQL verbatim if ordinals in real data have a different mapping. Before dropping the old column, confirm no unconverted rows remain and no older application instances continue writing to the old column.

### From STRING to converter codes

The workflow is similar: add a code column, backfill old names to stable codes, verify data, deploy the converter reading/writing the code column, and only then drop the old column. If renaming constants simultaneously, maintain the mapping table between old names and new codes in the migration.

### Compatibility during multi-version deployments

In systems with multiple instances or workers, a new instance may write a value an old instance does not recognize. For example, a new version writes `REFUNDED`, which the old version lacks. Before allowing writes of new statuses, ensure all consumers can read them or follow a compatible rollout strategy.

## 9. Constraints and data validation

Java enums alone do not guarantee the database only contains valid values. Data may be written by scripts, ETL jobs, other applications, or old code versions. Consider:

- `NOT NULL` if the status is mandatory.
- `CHECK` constraints to restrict the value set when the schema and database engine support them appropriately.
- Column length large enough for all names or codes.
- Indexes if filtering frequently by status and query plans show a benefit.
- Migrations updating constraints whenever new statuses are added.

Example constraint for stable codes:

```sql
alter table purchase_orders
add constraint chk_purchase_order_status
check (status_code in ('P', 'S', 'C'));
```

Constraints must be updated in lockstep when adding new codes. If the application must read data from a new version during rollout, constraints and all relevant consumers must be deployed in the proper order.

## 10. Common mistakes

1. **Leaving ORDINAL as default:** a field without `@Enumerated` or a converter may map as ordinal. Declare the storage format explicitly.
2. **Inserting an enum constant in the middle:** shifts subsequent ordinals and can turn `PAID` into `CANCELLED` when reading legacy rows.
3. **Renaming constants when using STRING:** legacy rows still store old names and do not update automatically with source code.
4. **Thinking toString() determines STRING data:** JPA uses `name()`, not `toString()`.
5. **Making column length too short:** new enum names can exceed the column limit and cause INSERT/UPDATE failures.
6. **Combining @Enumerated with @Convert on the same field:** two mechanisms compete to control mapping; pick one.
7. **Converter not handling unknown codes:** encountering legacy data or newer codes can cause read failures. Define a clear compatibility policy and monitor invalid data.
8. **Changing annotations without migrating:** numeric values do not magically turn into names or codes; transform data before new code reads it.
9. **Reusing retired codes:** historical records may be misinterpreted as a new status with a different meaning.

## 11. Testing enum mappings

Tests should verify both write and read paths. With `STRING`, verify the database holds exact constant names. With `ORDINAL`, verify numbers match the committed mapping and add tests guarding order. With converters, verify bidirectional conversion for every code, confirm unknown codes follow the chosen policy, and check null handling.

Example unit test for a converter using JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderStatusConverterTest {
    private final OrderStatusConverter converter = new OrderStatusConverter();

    @Test
    void convertsStatusToStableCode() {
        assertEquals("P", converter.convertToDatabaseColumn(OrderStatus.PENDING));
    }

    @Test
    void convertsStableCodeToStatus() {
        assertEquals(OrderStatus.PAID, converter.convertToEntityAttribute("S"));
    }

    @Test
    void rejectsUnknownCode() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convertToEntityAttribute("X"));
    }
}
```

This is a unit test for the converter. Complement it with database integration tests to verify Hibernate actually writes and reads the right column values, especially after mapping changes or migrations.

## 12. Practical rules

- Prefer `@Enumerated(EnumType.STRING)` for ordinary business enums requiring durable storage.
- Use `AttributeConverter` when storage codes must remain independent of constant names and declaration order.
- Avoid `ORDINAL` for long-lived data or when multiple application versions read/write concurrently.
- If forced to use ordinal, keep order immutable, never delete or insert in the middle; test and enforce the rule in code reviews.
- Treat constant renames, code changes, status deletions, and annotation changes as data changes requiring migrations.
- Never reuse old names or codes for a different business meaning.
- Roll out changes backward-compatibly when multiple instances or consumers exist.

Key takeaway: **ORDINAL stores position so it is highly sensitive to order changes; STRING stores name so it is safer when reordering but still depends on constant names; AttributeConverter stores application-defined codes so it fits when durable identifiers are needed across refactors.**
