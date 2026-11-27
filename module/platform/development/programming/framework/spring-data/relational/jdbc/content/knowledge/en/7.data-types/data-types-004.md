# Enums, Enum Names, and Rename Compatibility in Spring Data JDBC

An `enum` allows Java to represent a finite set of values such as order statuses, payment methods, or account types. In **Spring Data Relational JDBC**, an enum plays another critical role: its value is converted into data stored inside a **relational database column**. Consequently, renaming an enum constant in Java can prevent the new program from reading data written by an older version.

For example: an application initially defines `OrderStatus.PENDING`. If the database holds the string `'PENDING'` and a developer renames the Java constant to `AWAITING_PAYMENT` without preparing compatibility, Spring Data JDBC may fail to convert the string `PENDING` into the new enum when reading existing rows. This problem is especially common in systems with production data, rolling multi-version deployments, or a status column shared with other systems.

This lesson progresses from default enum mapping to designing **stable persistence codes**, writing converters, planning safe renames, and handling historical data. The content focuses on **Spring Data JDBC** and does not infer JDBC behavior from JPA mapping rules.

## 1. Enums in Java: Name, Display Value, and Persistence Code

Suppose there is an order processing workflow:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

An enum constant has several representations:

~~~java
OrderStatus status = OrderStatus.PENDING;

System.out.println(status.name());       // PENDING
System.out.println(status.toString());   // PENDING unless overridden
System.out.println(status.ordinal());    // 0 in the current declaration
~~~

**`name()`** returns the constant's exact identifier as declared in Java source code. This is a technical identifier; renaming `PENDING` to `AWAITING_PAYMENT` also changes `name()`.

**`toString()`** returns the same name by default, though it can be overridden for UI or logging purposes. Do not treat `toString()` as a durable data contract.

**`ordinal()`** is the constant's position in declaration order, starting at 0. Inserting or reordering constants changes ordinals. Avoid storing ordinals as long-lived business states when a stable code can be used.

**Persistence code (`database code`)** is an application-defined value written to the database, such as `WAIT_PAY`. This code can remain unchanged when renaming Java constants, altering UI wording, or translating languages.

| Concept | Example Value | Should It Be Treated as a Stable Contract? |
|---|---|---|
| `OrderStatus.PENDING` | Constant name in source | No, if developers may rename it |
| `status.name()` | `PENDING` | Only when deliberately committed never to change this value |
| `status.toString()` | `Đang chờ thanh toán` if overridden | No; typically used for display |
| `status.ordinal()` | `0` | No; depends on declaration order |
| `status.databaseCode()` | `WAIT_PAY` | Yes, if the code is managed as a data contract |

Core takeaway: **source code can be refactored freely; data in the database requires a controlled evolution plan**. These two lifecycles do not stay synchronized automatically.

## 2. How Does Spring Data JDBC Normally Store Enums?

For an ordinary enum property mapped to a **character column** like `VARCHAR`, Spring Data JDBC by default converts the enum to its **constant name** when writing, and converts the column string back to the matching enum constant when reading.

~~~text
Java object                   Database row
-------------------           ----------------------------
OrderStatus.PENDING   ---->    status = 'PENDING'

OrderStatus.PENDING   <----    status = 'PENDING'
~~~

This is a convenient convention for small enums, yet it creates an implicit coupling between **Java constant names** and **stored data**.

### Distinguishing from JPA

If you have used JPA before, you may recognize:

~~~java
// JPA syntax, NOT Spring Data JDBC enum configuration:
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

`@Enumerated` and `EnumType` belong to **Jakarta Persistence/JPA**. In this Spring Data JDBC lesson, we use **Spring Data**'s mapping and converter mechanism, such as `@Table`, `@Id`, `@Column`, and `@ReadingConverter` / `@WritingConverter`. Do not add `@Enumerated` to a Spring Data JDBC entity expecting it to control enum persistence.

Likewise, do not assume an enum will automatically be saved by `ordinal()` simply because it has three values. If you want to store numeric codes or a database-specific type, define explicit converters and matching column types.

### SQL Column Name and Enum Value Name Are Two Different Things

~~~java
@Column("order_status")
private OrderStatus status;
~~~

`@Column("order_status")` specifies the **SQL column name**. It does not change how `PENDING` is converted to `'PENDING'`. Renaming a column and renaming **the values stored inside the column** are two separate problems.

## 3. Practicing Default Enum Mapping with Spring Data JDBC

The small example below creates a `purchase_orders` table containing `id` and `status`. We save `PENDING`, read it back into Java, transition it to `PAID`, and inspect the string in the database. The application uses **Spring Boot + Spring Data JDBC + H2**.

### 3.1. Creating the Project

From Spring Initializr, create a Maven project with Java 17+ and select:

- **Spring Data JDBC**
- **H2 Database**

In the `pom.xml` generated by Initializr, the main dependencies look like:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Keep the parent, Java version, and Maven plugin generated by Spring Initializr. The Data JDBC starter also includes Spring JDBC infrastructure; the example uses `JdbcTemplate` to read the SQL string directly in order to observe the actual stored value.

File structure:

~~~text
enum-jdbc-demo/
└── src/main/
    ├── java/com/example/enumdemo/
    │   ├── EnumJdbcApplication.java
    │   ├── domain/OrderStatus.java
    │   ├── domain/PurchaseOrder.java
    │   └── repository/PurchaseOrderRepository.java
    └── resources/
        ├── application.yml
        └── schema.sql
~~~

### 3.2. Declaring the SQL Table

Create `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(32) NOT NULL
);
~~~

`status` is `VARCHAR`. No database-specific enum type is used in this basic example, allowing us to observe Spring Data JDBC's standard string conversion. Length `32` is only an example; real systems should choose a length large enough for stored values, or use short, fixed codes.

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:enumdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always

logging:
  level:
    org.springframework.jdbc.core: DEBUG
~~~

Spring Boot runs `schema.sql` at startup. An in-memory H2 database loses data when the application terminates; in environments with persistent data, it is precisely the rows written by older versions that trigger enum rename issues.

### 3.3. Enum and Aggregate Root

Create `src/main/java/com/example/enumdemo/domain/OrderStatus.java`:

~~~java
package com.example.enumdemo.domain;

public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Create `src/main/java/com/example/enumdemo/domain/PurchaseOrder.java`:

~~~java
package com.example.enumdemo.domain;

import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(@Id Long id, OrderStatus status) {

    public PurchaseOrder {
        Objects.requireNonNull(status, "status must not be null");
    }

    public static PurchaseOrder newOrder() {
        return new PurchaseOrder(null, OrderStatus.PENDING);
    }

    public PurchaseOrder markPaid() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Only PENDING orders can be paid");
        }
        return new PurchaseOrder(id, OrderStatus.PAID);
    }
}
~~~

`PurchaseOrder` is a simple **aggregate root** backed by a single table; `@Id` is from `org.springframework.data.annotation`, and `@Table` is from `org.springframework.data.relational.core.mapping`. Because records are immutable, `markPaid()` returns a new state with the same ID.

### 3.4. Repository

Create `src/main/java/com/example/enumdemo/repository/PurchaseOrderRepository.java`:

~~~java
package com.example.enumdemo.repository;

import com.example.enumdemo.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

No manual `INSERT`/`UPDATE` SQL is needed for these CRUD operations. Spring Data JDBC handles them using the mapping of `PurchaseOrder`.

### 3.5. Running and Observing Actual Values in the Database

Create `src/main/java/com/example/enumdemo/EnumJdbcApplication.java`:

~~~java
package com.example.enumdemo;

import com.example.enumdemo.domain.PurchaseOrder;
import com.example.enumdemo.repository.PurchaseOrderRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class EnumJdbcApplication {

    public static void main(String[] args) {
        SpringApplication.run(EnumJdbcApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            PurchaseOrderRepository orders,
            JdbcTemplate jdbc) {
        return args -> {
            PurchaseOrder created = orders.save(PurchaseOrder.newOrder());

            String valueInDatabase = jdbc.queryForObject(
                "SELECT status FROM purchase_orders WHERE id = ?",
                String.class,
                created.id()
            );
            System.out.println("SQL value: " + valueInDatabase);

            PurchaseOrder loaded = orders.findById(created.id())
                .orElseThrow();
            System.out.println("Java enum: " + loaded.status());

            PurchaseOrder paid = orders.save(loaded.markPaid());
            String updatedSqlValue = jdbc.queryForObject(
                "SELECT status FROM purchase_orders WHERE id = ?",
                String.class,
                paid.id()
            );
            System.out.println("SQL after update: " + updatedSqlValue);
        };
    }
}
~~~

Run on Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Or on macOS/Linux:

~~~bash
./mvnw spring-boot:run
~~~

Expected business output:

~~~text
SQL value: PENDING
Java enum: PENDING
SQL after update: PAID
~~~

This result clarifies that **the Java enum and SQL column data are two representations of the same state**. With default mapping to `VARCHAR`, the enum name becomes the string in the database. `JdbcTemplate` is used here to inspect the column directly, not to replace the repository in business workflows.

## 4. What Happens When an Enum Constant Is Renamed?

Suppose after operating for some time, the team decides `PENDING` is too vague and wants a clearer name: `AWAITING_PAYMENT`.

### Previous Version

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

The database already contains data:

~~~text
purchase_orders
id | status
---+----------
 1 | PENDING
 2 | PAID
 3 | CANCELLED
 4 | PENDING
~~~

### Version After Refactoring Java Only

~~~java
public enum OrderStatus {
    AWAITING_PAYMENT, // renamed from PENDING
    PAID,
    CANCELLED
}
~~~

When the new application runs and reads rows with `status = 'PENDING'`, the default mapping looks for a Java constant named `PENDING`. That constant no longer exists. The conversion can throw a conversion/`IllegalArgumentException` (typically wrapped in a data access or mapping exception depending on the call path).

~~~mermaid
flowchart LR
    A[("DB: status = 'PENDING'")] --> B["Read column as String"]
    B --> C["Convert String to OrderStatus"]
    C --> D{"Does enum still have PENDING?"}
    D -->|Yes| E["Read succeeds"]
    D -->|No| F["Data conversion error"]
~~~

Renaming an enum in the IDE only updates **Java references**. The IDE does not update values already stored in the database, nor does it guarantee that other systems, backups, old messages, or running jobs understand the new name.

### The Situation Gets Even More Complex with Multiple Running Instances

Consider a system running two versions concurrently during a deployment:

| Component | Understands Only `PENDING` | Understands Only `AWAITING_PAYMENT` |
|---|---|---|
| Old application instance | Yes | No |
| New application instance after simple refactor | No | Yes |
| Database containing `PENDING` | Readable by old version | Risk of error in new version |
| Rows written with `AWAITING_PAYMENT` | Risk of error in old version | Readable by new version |

Therefore, running an `UPDATE` statement to change every string in the database while old application instances are still serving traffic can break things in the reverse direction: **old instances cannot read the new values**. This is a bidirectional compatibility issue across versions, not merely a single rename operation.

## 5. Two Main Strategies When Renaming an Enum

### Strategy A — Keep Storing `name()`, Synchronizing Java and SQL Data

This option accepts the Java constant name as the database value. When renaming, treat it as a **schema/data contract change** and migrate data in a controlled manner.

For example, the `purchase_orders` table previously stored `PENDING` and needs to change to `AWAITING_PAYMENT`:

~~~sql
UPDATE purchase_orders
SET status = 'AWAITING_PAYMENT'
WHERE status = 'PENDING';
~~~

This statement only updates the data. For the system to work, the Java version, converters (if any), queries with hardcoded statuses, database constraints, and downstream status consumers must also be compatible.

**Suitable when:** the system is small, has maintenance windows or full control over the upgrade order of the entire application and data, and does not need to maintain compatibility while two versions run simultaneously.

**Limitations:** every constant rename may require a migration; Java names inadvertently become a contract across multiple systems. With large datasets or continuous deployment environments, coordination becomes more complex.

### Strategy B — Decouple Java Names from Stored Database Codes

This option defines a **fixed persistence code** for each status. Java names can change, while strings in the database remain unchanged.

~~~text
Java Name (refactorable)       Database Code (stable)
--------------------------    --------------------------------
AWAITING_PAYMENT              WAIT_PAY
PAID                          PAID
CANCELLED                     CANCELLED
~~~

If later `AWAITING_PAYMENT` is renamed to `WAITING_FOR_PAYMENT` while keeping `WAIT_PAY`, historical data does not need updating merely because a Java constant was refactored. You provide converters so Spring Data JDBC uses `WAIT_PAY` instead of the name `AWAITING_PAYMENT`.

**Suitable when:** the database is long-lived, multiple application versions access it concurrently, statuses flow into reports or integrations, and the team wants explicit control over the data contract.

**Limitations:** converters must be written, registered, and maintained; persistence codes must be defined carefully because they become a durable contract.

## 6. Mapping Enums Using Stable Database Codes

This section continues with the `PurchaseOrder` and repository built earlier. We change **how the enum is represented**, while keeping the `OrderStatus status` property in the aggregate root unchanged. The snippets below belong to **an alternative approach** to default mapping; do not run two conflicting enum/converter setups simultaneously in the same project.

### 6.1. Defining an Enum with Fixed Codes

Replace `OrderStatus.java` with:

~~~java
package com.example.enumdemo.domain;

import java.util.Arrays;

public enum OrderStatus {
    AWAITING_PAYMENT("WAIT_PAY"),
    PAID("PAID"),
    CANCELLED("CANCELLED");

    private final String databaseCode;

    OrderStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public String databaseCode() {
        return databaseCode;
    }

    public static OrderStatus fromDatabaseCode(String code) {
        return Arrays.stream(values())
            .filter(value -> value.databaseCode.equals(code))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException(
                "Unsupported status code: " + code
            ));
    }
}
~~~

In this example:

- `AWAITING_PAYMENT` is the constant name used in Java code.
- `WAIT_PAY` is the code stored in the database.
- `fromDatabaseCode` converts the database string back to the enum; unrecognized codes throw a clear error.

**Do not silently coerce unknown codes into a default status**, especially in payment or approval workflows. If data contains an invalid code, returning the wrong status can be far more dangerous than failing loudly and fixing the data.

When switching from the old enum to this one, update Java references in the aggregate: `PENDING` to `AWAITING_PAYMENT`. For example:

~~~java
public static PurchaseOrder newOrder() {
    return new PurchaseOrder(null, OrderStatus.AWAITING_PAYMENT);
}

public PurchaseOrder markPaid() {
    if (status != OrderStatus.AWAITING_PAYMENT) {
        throw new IllegalStateException(
            "Only orders awaiting payment can be paid");
    }
    return new PurchaseOrder(id, OrderStatus.PAID);
}
~~~

### 6.2. Converter for Writing an Enum as a String

Create `src/main/java/com/example/enumdemo/config/OrderStatusWritingConverter.java`:

~~~java
package com.example.enumdemo.config;

import com.example.enumdemo.domain.OrderStatus;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.databaseCode();
    }
}
~~~

When saving `OrderStatus.AWAITING_PAYMENT`, the converter returns `"WAIT_PAY"`. The `@WritingConverter` annotation explicitly declares the converter's conversion direction.

### 6.3. Converter for Reading a String into an Enum

Create `src/main/java/com/example/enumdemo/config/OrderStatusReadingConverter.java`:

~~~java
package com.example.enumdemo.config;

import com.example.enumdemo.domain.OrderStatus;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromDatabaseCode(source);
    }
}
~~~

When reading the column string `WAIT_PAY`, the converter returns `OrderStatus.AWAITING_PAYMENT`. The **read** and **write** conversion directions differ, so both must be declared if you want to manage a separate persistence code.

### 6.4. Registering Converters with Spring Data JDBC

Create `src/main/java/com/example/enumdemo/config/JdbcConversionConfig.java`:

~~~java
package com.example.enumdemo.config;

import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConversionConfig extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new OrderStatusWritingConverter(),
            new OrderStatusReadingConverter()
        );
    }
}
~~~

`AbstractJdbcConfiguration` provides the extension point for declaring Spring Data JDBC custom converters. The configuration sits in a subpackage of `com.example.enumdemo` so Spring Boot can detect it. This is an illustrative registration approach for Spring Data JDBC versions that provide `userConverters()`; when applying to a project on another version, verify the converter configuration API of that specific version.

**Note on scope:** the converter pair above applies to the `OrderStatus` type across applicable mappings, not solely to a single property named `status`. If multiple tables use the same enum type yet require different codes, that may be a sign to separate domain types or use a more suitably scoped conversion approach.

### 6.5. Data After Using Converters

With the new enum and registered converters:

~~~java
PurchaseOrder created = orders.save(PurchaseOrder.newOrder());
System.out.println(created.status()); // AWAITING_PAYMENT
~~~

SQL stores it as:

~~~text
purchase_orders
id | status
---+---------
 1 | WAIT_PAY
~~~

When read back, Java receives `OrderStatus.AWAITING_PAYMENT`. Renaming the Java constant again will not change the database as long as the `WAIT_PAY` code and converter logic remain the same.

**Switching to converters does not automatically migrate old data.** If the database currently has `'PENDING'` from the default mapping, the newly written converter only recognizes `WAIT_PAY`, `PAID`, and `CANCELLED`. You need a transitional reading phase or data migration as described in the next section.

## 7. Migrating Legacy Data to Stable Codes

Suppose the production database currently stores:

~~~text
id | status
---+----------
 1 | PENDING
 2 | PAID
 3 | CANCELLED
~~~

We want to migrate the old value `PENDING` to the stable code `WAIT_PAY`. In an environment where all writers and readers can be temporarily paused, the simple approach is to upgrade the application and migrate data within a controlled deployment window:

~~~sql
UPDATE purchase_orders
SET status = 'WAIT_PAY'
WHERE status = 'PENDING';
~~~

If the database has a `CHECK` constraint permitting only `PENDING`, update the constraint before writing `WAIT_PAY`. If views, triggers, SQL reports, stored procedures, or other services check the string `PENDING`, those components must also be audited against the data contract.

In a **rolling deployment** system where all instances cannot stop at once, roll out changes in phases so old and new versions can read data during the overlap period.

### 7.1. Transitional Phase Reading Both Codes

Temporarily define the mapper to accept both `PENDING` and `WAIT_PAY`, always representing them in Java as `AWAITING_PAYMENT`:

~~~java
public static OrderStatus fromDatabaseCode(String code) {
    return switch (code) {
        case "PENDING", "WAIT_PAY" -> AWAITING_PAYMENT;
        case "PAID" -> PAID;
        case "CANCELLED" -> CANCELLED;
        default -> throw new IllegalArgumentException(
            "Unsupported status code: " + code);
    };
}
~~~

This is a **transitional variant** of `fromDatabaseCode` in `OrderStatus`, replacing the earlier `Arrays.stream(...)` logic. Do not place two methods with the same signature in one class.

Adding dual-code reading to new instances alone is **not enough** to remain safe with old instances. If old instances only understand `PENDING`, they will fail upon encountering `WAIT_PAY`. Therefore, while old instances remain active, the new version must **continue writing the old code**:

~~~java
// Temporary use only during deployment while old instances still exist:
public String databaseCode() {
    return this == AWAITING_PAYMENT ? "PENDING" : databaseCode;
}
~~~

The snippet above illustrates a temporary write toggle to show deployment ordering. In a real system, managing the transitional write mode via configuration or an explicitly versioned converter is easier to operate than embedding temporary logic in a domain enum.

### 7.2. The Expand → Migrate → Contract Sequence

| Phase | Running Versions | What Can Be Read? | What Is Written? |
|---|---|---|---|
| 1. Initial | Old version | `PENDING` | `PENDING` |
| 2. Expand | Compatible new version, rolling out | `PENDING` and `WAIT_PAY` | Still `PENDING` |
| 3. Switch write mode | Only dual-reading versions remain | `PENDING` and `WAIT_PAY` | Begins writing `WAIT_PAY` |
| 4. Migrate data | Compatible instances | `PENDING` and `WAIT_PAY` | `WAIT_PAY`; update remaining `PENDING` rows |
| 5. Contract | Only new version remains | `WAIT_PAY` | `WAIT_PAY` |

Implementation details:

1. **Expand:** deploy the ability to read both old and new codes while continuing to write the old code. Verify every serving instance has upgraded before changing the written code.
2. **Switch writes:** configure the application to write `WAIT_PAY`. From this point on, no instance exists that can only read `PENDING`.
3. **Migrate:** update historical `PENDING` rows to `WAIT_PAY`. Also check batch jobs, retry queues, and any sources that might still write the old code.
4. **Contract:** once no old codes are being generated and all existing data has migrated, remove the `PENDING` alias branch; tighten constraints if needed.

For databases with many records, migration may need primary-key batching, careful transaction sizing, and low-traffic execution windows. Compatibility ordering matters more than the number of SQL statements. Application rollback must also be planned ahead of time: rolling back to a version that only understands `PENDING` after `WAIT_PAY` has been written will reintroduce read failures.

### 7.3. Inspecting Data Before and After Migration with SQL

Before migrating:

~~~sql
SELECT status, COUNT(*) AS total
FROM purchase_orders
GROUP BY status
ORDER BY status;
~~~

After all writers have switched to the new code and the migration runs:

~~~sql
UPDATE purchase_orders
SET status = 'WAIT_PAY'
WHERE status = 'PENDING';
~~~

Then re-run the `GROUP BY` query to check if any old codes remain. Seeing new rows appear with `PENDING` after migration indicates that a writer or job is still using the old contract.

If the database has a constraint restricting enum values, the general order is: **allow both values during the transition phase, then remove the old value after migration completes**. Syntax for altering constraints varies across H2, PostgreSQL, MySQL, and other DBMSs; do not blindly apply the same `ALTER TABLE` statement to every database.

## 8. Choosing How to Store Enums Based on Compatibility Needs

| Storage Approach | Example SQL Column | Advantages | Risks When Changing |
|---|---|---|---|
| Default enum name | `PENDING` | Simple, readable, minimal configuration | Renaming Java changes the data contract |
| Stable string code with converter | `WAIT_PAY` | Java refactoring decoupled from data; easy to query | Requires converters, code management, and migration from old data |
| Fixed business numeric code | `10`, `20` | Compact, stable if well-managed | Harder to read in SQL/reports; still needs converters and mapping docs |
| Java ordinal | `0`, `1` | Looks compact initially | Very prone to semantic corruption when reordering/adding constants |
| DB native enum type | DB-dependent values | Can enforce value set in schema | DDL migrations and JDBC driver/dialect have specific requirements |

**Fixed numeric codes differ from ordinals.** If the business chooses `10 = WAIT_PAY`, `20 = PAID` and never alters the meaning of those numbers, that is an intentionally designed contract. `ordinal()` depends on source declaration order, making it prone to accidental changes.

### Is Storing PostgreSQL's Native Enum Type the Same as VARCHAR?

Not necessarily. For instance, PostgreSQL supports user-defined enum columns; the JDBC driver may represent this type differently from an ordinary `VARCHAR` string. In that case, you may need PostgreSQL-specific converters and parameter binding, or controlled SQL casts. The `Converter<OrderStatus, String>` examples above target **standard character columns**. Do not adopt a native DB enum merely because it shares the word “enum” with Java.

Choosing `VARCHAR` paired with a `CHECK` constraint or a reference lookup table is a common approach when prioritizing clarity, migration ease, and decoupling between Java and the database. Choosing native enums requires evaluating migrations and driver support.

## 9. Frequently Overlooked Risks

### 9.1. Changing an Enum Name Is Not Changing a Display Label

An application might need to display “Chờ thanh toán” in Vietnamese and “Awaiting payment” in English. Do not put either string into `name()`. The UI should map statuses to display labels through message resources/i18n or a presentation layer.

~~~java
String label(OrderStatus status) {
    return switch (status) {
        case AWAITING_PAYMENT -> "Chờ thanh toán";
        case PAID -> "Đã thanh toán";
        case CANCELLED -> "Đã hủy";
    };
}
~~~

The function above only illustrates display mapping; it is not a converter for writing to the database. Labels can change by product or language without affecting column values.

### 9.2. JSON, APIs, and Messages Can Also Depend on Enum Names

With common JSON libraries, enum values are typically serialized to their constant names unless configured otherwise. For example, a client sending `"PENDING"` may break when the API only accepts `"AWAITING_PAYMENT"`.

**Spring Data JDBC converters apply only to saving/loading data through Spring Data JDBC.** They do not automatically change how Jackson serializes enums, how message queues encode statuses, or how other services write manual SQL.

If an enum appears in public APIs or events, establish a separate contract for APIs/messages—such as stable public codes and conversion logic suited to the serializer in use. Do not assume updating a DB converter fixes every data pipeline.

### 9.3. Hand-Written SQL May Depend on Old Values

~~~sql
SELECT *
FROM purchase_orders
WHERE status = 'PENDING';
~~~

Even after the repository adopts the `WAIT_PAY` converter, the SQL query above still compares against literal `PENDING`. When developers use `JdbcTemplate`, views, stored procedures, or SQL dashboards, those places must read from a unified data contract. Maintaining a documented registry of system-wide codes helps avoid subtle discrepancies.

### 9.4. Nulls and Invalid Codes Need a Clear Strategy

Suppose `status VARCHAR(32) NOT NULL` is declared and the domain forbids null statuses. That protects part of data integrity. However, the data could still contain a string outside the enum, such as `WAITING` from a faulty import.

In converters, fail loudly with a clear error instead of silently assigning `CANCELLED` or `PENDING`. Only design an `UNKNOWN` status if the product genuinely has a business requirement for it and defines how to handle it.

If a SQL column allows `NULL`, understand that Spring Data may skip invoking the converter for null values; null-handling rules must be defined at the schema and domain levels rather than relying solely on checks inside `fromDatabaseCode`.

### 9.5. Constrained Columns and New Data

If the database uses:

~~~sql
CONSTRAINT chk_order_status
    CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
~~~

then a converter attempting to write `WAIT_PAY` will be rejected by the database even though the Java code compiles cleanly. When expanding enum sets or changing codes, adjust constraints **in a compatible deployment order**. With native database enums or reference tables, the alteration steps differ.

### 9.6. Renaming vs. Changing Semantics Are Two Different Decisions

Renaming `PENDING` to `AWAITING_PAYMENT` without changing meaning can rely on a single stable persistence code. However, if a new status only covers part of the old behavior (for instance, splitting `PENDING` into `WAITING_PAYMENT` and `WAITING_APPROVAL`), **a simple rename is not possible**.

When splitting or merging statuses, you must determine how to classify legacy records, which auxiliary data derives the new status, how to handle edge cases, and how each version's business code stays compatible. A single `UPDATE ... SET status = ...` statement is unlikely to suffice.

## 10. Technical Checklist When Renaming an Enum Stored in a Database

| Item | Questions to Resolve |
|---|---|
| Column type | Is it `VARCHAR`, `CHAR`, numeric code, or DB native enum? |
| Current mapping | Does Spring Data JDBC use default naming or a custom converter? |
| Existing data | Which codes exist? Are there unexpected values or nulls? |
| Semantic contract | Is this purely a rename, or is the status meaning changing? |
| Concurrent versions | Can old versions read codes written by the new version? |
| Repositories and DAOs | Are there literal SQL queries, projections, or separate converters? |
| Database constraints | Are there `CHECK` constraints, foreign keys, triggers, or specialized indexes? |
| API / events | Do JSON payloads and messages serialize the enum by Java name? |
| Auxiliary jobs | Do import/export jobs, batches, reports, or schedulers write old codes? |
| Rollback | If rolling back to the old version, can it read the new data? |

This checklist is meant for **planning changes in a real project**; the lesson's examples explain why each question matters. In multi-application systems or continuous deployment environments, concurrent-version compatibility usually dictates the migration order.

## 11. Practice Exercises

### Exercise 1 — Observing Default Mapping

1. Run the `OrderStatus.PENDING` example with a `VARCHAR` column.
2. Use `JdbcTemplate` to read `status` directly and verify `PENDING` is stored in the database.
3. Try renaming `PENDING` to `AWAITING_PAYMENT` in Java while keeping a database that contains old data. Observe what happens when reading.
4. Explain why this change cannot be treated merely as a name refactor.

**Hint:** In-memory H2 loses data on restart. To practice with legacy data, use a file-backed H2 database or seed a `'PENDING'` row with SQL when starting the new application; do not assume an in-memory database retains data after the JVM exits.

### Exercise 2 — Stable Code Mapping

1. Replace the enum with `AWAITING_PAYMENT("WAIT_PAY")`, `PAID("PAID")`, and `CANCELLED("CANCELLED")`.
2. Create `@WritingConverter` and `@ReadingConverter`, and register them with Spring Data JDBC.
3. Save an aggregate with status `AWAITING_PAYMENT` and verify the SQL column contains `WAIT_PAY`.
4. Rename the Java constant to `WAITING_FOR_PAYMENT` while keeping `WAIT_PAY`; explain why historical data remains readable.

### Exercise 3 — Planning a Zero-Downtime Upgrade

Suppose three old application instances and three new instances run in a rolling update. The database contains `PENDING`, and the goal is to store `WAIT_PAY`.

Describe the exact sequence: deploy readers understanding both codes, keep writing the old code, retire old instances, switch writers to the new code, migrate data, and remove the old alias. For each stage, state clearly **what the application can read** and **what it writes**.

### Exercise 4 — Distinguishing Semantic Changes

Suppose the old `PENDING` covered both “waiting for customer payment” and “waiting for staff approval”. The new version splits these into two statuses. Identify what additional information is required to classify old rows; explain why blindly replacing `PENDING → WAIT_PAY` across all rows could violate business logic.

## 12. Summary

In **Spring Data JDBC**, enums are typically stored in character columns using their **Java constant names** under default mapping. This is convenient, yet it makes enum renames directly affect persisted data: newer versions may fail to read old strings, and older versions may fail to read new strings during deployment.

When enum names form part of a data contract, Java and the database must evolve together under a compatibility plan. For systems meant to evolve long-term, **stable database codes combined with `@ReadingConverter` / `@WritingConverter`** decouple Java identifiers from storage formats. Whichever approach you choose, treat enum value changes as **data and business contract changes**: account for historical data, SQL constraints, concurrently running versions, and external integrations before retiring old values.
