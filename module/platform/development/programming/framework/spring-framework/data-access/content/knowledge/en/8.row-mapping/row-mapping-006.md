# BeanPropertyRowMapper and Property Name Mapping Rules

In Spring JDBC, data from a `ResultSet` usually has SQL-style column names such as `first_name`, `email_address`, `created_at`, whereas Java objects use properties `firstName`, `emailAddress`, `createdAt`. `BeanPropertyRowMapper<T>` is a `RowMapper<T>` implementation that can instantiate a JavaBean and populate column values into the corresponding **properties with public setters**. It reduces boilerplate when mapping common JDBC queries, but only works properly if you understand the rules for naming, constructors, setters, data types, `NULL`, and mapping scope.

This lesson explains how `BeanPropertyRowMapper` matches column names to property names, when SQL aliases are needed, the limits of automatic mapping, and when to switch to `DataClassRowMapper` or a hand-written `RowMapper`. Examples use **Java 17+, Spring JDBC 6.1.x, and H2**.

## 1. Where `BeanPropertyRowMapper` Fits in the JDBC Flow

A JDBC query typically goes through these steps:

```text
JdbcTemplate.query(sql, rowMapper, args...)
        |
        v
PreparedStatement -> ResultSet (n rows, m columns)
                          |
                          | each row
                          v
              BeanPropertyRowMapper<T>.mapRow(...)
                          |
              instantiate JavaBean via no-arg constructor
                          |
              read column name/label metadata
                          |
              find matching JavaBeans PropertyDescriptor
                          |
              read SQL value, convert type when supported
                          |
              call appropriate setter
                          |
                          v
                      object T
        |
        v
List<T> (for query) or exactly 1 T (for queryForObject)
```

`BeanPropertyRowMapper` operates at the **one row → one object** level. It does not decide how many rows SQL returns, does not create tables, does not manage transactions, and does not automatically turn one-to-many relationships into nested lists. `JdbcTemplate` manages query execution and the lifecycle of JDBC resources.

Typical usage:

```java
// Integration example: jdbc is JdbcTemplate, CustomerBean is a JavaBean.
List<CustomerBean> customers = jdbc.query(
    "SELECT id, first_name, email_address FROM customer ORDER BY id",
    BeanPropertyRowMapper.newInstance(CustomerBean.class)
);
```

If `CustomerBean` has a no-argument constructor and setters `setId`, `setFirstName`, and `setEmailAddress`, the columns can be populated automatically. This is an **integration snippet**, not a standalone program; a complete runnable example appears later.

## 2. Name Mapping Rules: JavaBeans Properties, Not Arbitrary Field Names

`BeanPropertyRowMapper` uses the **JavaBeans writable properties** model. Spring discovers properties with standard JavaBeans setter methods and prepares candidate column names for each property.

JavaBean example:

```java
public class CustomerBean {
    private String firstName;
    private String emailAddress;

    public CustomerBean() {}

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public String getEmailAddress() {
        return emailAddress;
    }

    public void setEmailAddress(String emailAddress) {
        this.emailAddress = emailAddress;
    }
}
```

This is a standalone JavaBean class declaration, to be placed in `CustomerBean.java` and used alongside Spring JDBC to run mapping. For property `firstName`, the mapper recognizes corresponding lowercase names such as `firstname` or underscore-separated names like `first_name` by default. For `emailAddress`, `emailaddress` or `email_address` matches.

Common rules table:

| JavaBeans property | Required setter | Typical column name / SQL alias | Result |
| --- | --- | --- | --- |
| `id` | `setId(...)` | `id`, `ID` | Matches. |
| `firstName` | `setFirstName(...)` | `first_name`, `FIRST_NAME`, `firstName` | Matches equivalent names under default rules. |
| `emailAddress` | `setEmailAddress(...)` | `email_address` | Matches. |
| `createdAt` | `setCreatedAt(...)` | `created_at` | Matches if the type can be converted. |
| `isActive` (field name) | Depends on actual property | `is_active` | Does not infer property `isActive` from field name alone; must examine the setter. |
| `departmentName` | `setDepartmentName(...)` | `department_name` | Matches when the query explicitly provides that column/alias. |

For booleans, the JavaBeans property is normally `active` when `isActive()` and `setActive(boolean)` exist. In that case, SQL alias `active` is clearest; the internal field name may be `isActive`, yet the field is not the source of truth for the JavaBeans property.

**Key takeaway:** The mapper does not simply find fields with matching names via reflection and set them directly. It relies on property descriptors—primarily **public setters**—and data must have compatible or convertible types.

### How Does the Mapper Handle Casing and Underscores?

The default mechanism prepares candidate names for a property, including a lower-case form and an underscore-lower-case form. For `firstName`, the two main forms are `firstname` and `first_name`. JDBC column names/labels are normalized to lowercase before lookup. Thus, DBs returning metadata `FIRST_NAME`, `first_name`, or `firstName` usually still map to property `firstName`.

This does not mean the mapper understands arbitrary name variations. A column `given_name` **does not automatically map** to `firstName`; a column `customer_email` **does not automatically map** to `emailAddress`; arbitrary separators, unfamiliar prefixes, or abbreviations are not inferred semantically either.

When conventions do not match, **SQL aliases** are the direct, readable, and maintainable solution.

## 3. SQL Aliases and `columnLabel`: The Standard Way to Rename

Suppose the physical column is `given_name` while the JavaBean has `firstName`:

```sql
SELECT
    customer_id AS id,
    given_name  AS first_name,
    mail_addr   AS email_address
FROM legacy_customer
WHERE customer_id = ?;
```

The mapper inspects the **column labels** reported by JDBC (usually the alias when the query uses `AS`), so labels `id`, `first_name`, and `email_address` map into the corresponding setters.

Visualizing the transformation:

```text
DB column: given_name
       |
SQL projection: given_name AS first_name
       |
ResultSetMetaData column label: first_name
       |
BeanPropertyRowMapper lookup: first_name -> firstName
       |
CustomerBean.setFirstName(value)
```

There is no need to alter the database schema just to match Java naming conventions. Aliases are also helpful with `JOIN`s:

```sql
SELECT
    c.id           AS id,
    c.full_name    AS full_name,
    d.name         AS department_name
FROM customer c
JOIN department d ON d.id = c.department_id
WHERE c.id = ?;
```

Assuming the target bean has `setId`, `setFullName`, and `setDepartmentName`, the mapper can populate all three properties. Conversely, `SELECT c.*, d.*` easily produces duplicate labels like `id` and `name`, or properties absent from the bean. When two columns share a label or resolve to the same property, do not rely on “whichever column wins” as a business rule; **select columns explicitly with unique aliases**.

**Not all aliases are equal:** `AS first_name` is more reliable than `AS firstName` on DBs with case-folding rules for unquoted identifiers. For columns with spaces or names requiring quotes in a SQL dialect, alias them to clean `snake_case`.

## 4. Requirements for a Target Class to Be Mappable

### 4.1. JavaBean, Not an Immutable Record

`BeanPropertyRowMapper<T>` requires the target class to be a top-level class or **static nested class** with a **no-argument default constructor** so the mapper can instantiate it; the class needs public setters for the properties to be populated.

Valid example:

```java
public class ProductBean {
    private long id;
    private String productName;

    public ProductBean() {}

    public void setId(long id) {
        this.id = id;
    }

    public void setProductName(String productName) {
        this.productName = productName;
    }

    public long getId() {
        return id;
    }

    public String getProductName() {
        return productName;
    }
}
```

This code is a Java class definition, placed in `ProductBean.java` when used on its own. Conversely, a class with only a parameterized constructor and `final` fields is usually **incompatible with BeanPropertyRowMapper** if it lacks matching JavaBeans setters.

Example:

```java
// Not a suitable target for the default BeanPropertyRowMapper.
public record ProductView(long id, String productName) {}
```

Records have no no-arg constructor or mutating setters. For Java records, use `DataClassRowMapper` (Section 9) or a custom `RowMapper`.

### 4.2. Only Writable Properties Are Populated

A field with a getter but no public setter **is not automatically assigned** merely because its name matches. Extra properties not present in the column set keep their values from the constructor/initializer when `checkFullyPopulated` is at its default `false`; columns matching no property are normally ignored.

Example:

```java
// Illustration: target has an extra displayName field.
public class ProfileBean {
    private String firstName;
    private String displayName = "(unknown)";

    public ProfileBean() {}

    public void setFirstName(String value) {
        this.firstName = value;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

`displayName` here is a read-only property with no setter; the mapper cannot populate it directly via JavaBeans introspection. Do not assume every field on the target is synchronized with SQL. If you need a property populated, design an appropriate setter/target structure or use a different mapping approach.

### 4.3. Use Explicit Projections

Querying only a subset of columns is valid when the DTO/JavaBean represents that **projection**:

```sql
SELECT id, display_name
FROM account
WHERE active = TRUE;
```

If the bean also has `createdAt` and `emailAddress` that the query does not select, those properties **do not appear out of nowhere** by default and keep their default values. That may be intentional for a projection, or an omitted-data bug. Use a dedicated DTO when the contract only needs two fields instead of reusing an overly broad bean.

## 5. Writing `JdbcTemplate` with `BeanPropertyRowMapper`

Given a `CustomerBean` and a configured `JdbcTemplate`:

```java
BeanPropertyRowMapper<CustomerBean> mapper =
    BeanPropertyRowMapper.newInstance(CustomerBean.class);

// Multiple rows, returns List.
List<CustomerBean> all = jdbc.query(
    "SELECT id, first_name, email_address " +
    "FROM customer WHERE active = ? ORDER BY id",
    mapper,
    true
);

// Exactly one row per contract.
CustomerBean one = jdbc.queryForObject(
    "SELECT id, first_name, email_address " +
    "FROM customer WHERE id = ?",
    mapper,
    customerId
);
```

This is illustrative repository code requiring `jdbc`, `customerId`, and the bean/table; it is not a standalone program.

Important:

- `query(...)` with `RowMapper<T>` produces a list, which can contain 0, 1, or many beans.
- `queryForObject(...)` expects **exactly one row**. Zero rows normally throws `EmptyResultDataAccessException`; more than one row throws `IncorrectResultSizeDataAccessException`. `BeanPropertyRowMapper` does not change row-count rules.
- `BeanPropertyRowMapper` creates a **new object per row**; it does not collapse multiple rows sharing a key into one object.
- If SQL returns extra unneeded columns, the mapper may ignore them; do not equate that with “fully mapped”.

If a project executes JDBC SQL repeatedly, you can create one shared mapper instance per type and reuse it: it caches property metadata once configured, so there is no need to instantiate a new mapper on every call. Do not mutate `setMappedClass`/`setCheckFullyPopulated`/conversion config while multiple threads use a shared mapper.

## 6. Checking for Missing Properties: `checkFullyPopulated`

Default:

```java
BeanPropertyRowMapper<CustomerBean> mapper =
    BeanPropertyRowMapper.newInstance(CustomerBean.class);
System.out.println(mapper.isCheckFullyPopulated()); // false
```

When `false`, if SQL omits some columns corresponding to writable properties, the mapper still constructs the bean and leaves unmapped properties at their initial values. Useful for partial projections, yet it can also hide queries missing columns after schema edits.

To require **every writable property to be mapped**, enable strict mode:

```java
BeanPropertyRowMapper<CustomerBean> strict =
    BeanPropertyRowMapper.newInstance(CustomerBean.class);
strict.setCheckFullyPopulated(true);

CustomerBean customer = jdbc.queryForObject(
    "SELECT id, first_name, last_name, email_address, reward_points " +
    "FROM customer WHERE id = ?",
    strict,
    1L
);
```

If the target has five writable properties while the query only selects `id` and `first_name`, the strict mapper throws `InvalidDataAccessApiUsageException` because the remaining properties were not populated. It checks **coverage of properties with setters**, not physical field counts or whether a business value is non-null.

**Do not enable strict mode on a bean shared across multiple different projections.** A query that genuinely only needs `id` and `firstName` will be rejected if the bean has additional setters. When strict mode does not fit, use a separate DTO or an explicit mapper.

Nor should strict mode be mistaken for full domain validation:

- It does not enforce that `emailAddress` is a valid email.
- It does not guarantee `id` is positive.
- If a column is mapped yet its SQL value is `NULL`, “property was mapped” still requires checking **Java types and nullability** separately.
- It does not enforce single-row queries; `query` can map multiple beans using a strict mapper.

## 7. SQL NULL, Primitives, and Wrappers

A SQL `NULL` value can be mapped to Java `null` for reference-type properties such as `String`, `Integer`, `Long`, `BigDecimal`. However, Java primitives `int`, `long`, `boolean` cannot hold `null`.

Target example:

```java
public class ScoreBean {
    private int score;

    public ScoreBean() {}

    public void setScore(int score) {
        this.score = score;
    }

    public int getScore() {
        return score;
    }
}
```

If the `score` column returns SQL `NULL`, `BeanPropertyRowMapper` by default attempts to invoke the setter with an incompatible value and can throw `TypeMismatchException`. Switching to `Integer score` preserves the distinction between **no score yet** and **a score of 0**.

There is an option:

```java
BeanPropertyRowMapper<ScoreBean> mapper =
    BeanPropertyRowMapper.newInstance(ScoreBean.class);
mapper.setPrimitivesDefaultedForNullValue(true);
```

When enabled, the mapper **skips** setting the primitive property if the column is `NULL`, so the property keeps its post-construction value (usually 0/false). Use this option with great caution: SQL `NULL` loses its distinction from a real 0/false; if the object is written back to the DB, there is a risk of unintentionally replacing `NULL` with the default value.

How to choose:

| DB value | Java type | Expected outcome |
| --- | --- | --- |
| `score = 15` | `int` or `Integer` | 15. |
| `score = NULL` | `Integer` | `null`, preserving the “no data” meaning. |
| `score = NULL` | `int`, default config | Error converting value to primitive, helping catch mismatches. |
| `score = NULL` | `int`, default-for-null enabled | Skips setter in this case; initialized primitive value remains. |

Do not solve every `NULL` by converting the SQL column with `COALESCE(score, 0)` if 0 differs semantically from NULL. Only do so when business rules confirm the two cases are equivalent.

## 8. Type Conversion and Limits of Auto-Mapping

`BeanPropertyRowMapper` does more than assign `String` to `String`: Spring reads JDBC values appropriate to the target type and uses a `ConversionService` (defaulting to `DefaultConversionService` in many versions) to support common types such as `Integer`, `Long`, `BigDecimal`, `Boolean`, and certain date/time types.

However, having a setter does not guarantee every SQL type / Java type pair converts cleanly. For example:

- The driver returns `Timestamp` while the target uses another temporal type: check JDBC driver, time zone, and conversion behavior.
- A text column holds non-numeric data while the setter takes `Integer`: can throw a type conversion error.
- JSON/array/vendor-specific columns: usually need specialized retrieval/converters.
- A column holds a value outside the Java type's range: can overflow or convert inappropriately.
- Booleans and enums stored as custom strings/codes: semantics are not inferred automatically across all databases.

You can configure:

```java
BeanPropertyRowMapper<CustomerBean> mapper =
    BeanPropertyRowMapper.newInstance(CustomerBean.class);
mapper.setConversionService(customConversionService);
```

This is an integration example because it requires a configured `customConversionService` of type `org.springframework.core.convert.ConversionService`. A custom conversion service should express stable, tested rules and never silently turn invalid data into defaults.

**Note on annotations:** `BeanPropertyRowMapper` is a Spring JDBC utility, **not a JPA provider**. Annotations like `@Entity`, `@Column(name = "db_name")`, or JPA relationship mappings have no effect on turning `db_name` into an arbitrary JavaBeans property in this mapper. When column names diverge, use SQL aliases, change the target type, or write a custom `RowMapper`.

## 9. When Using Java Records, Choose `DataClassRowMapper`

A Java record is an immutable type passing data through its constructor rather than public setters:

```java
public record CustomerView(
    long id,
    String firstName,
    String emailAddress
) {}
```

Standard `BeanPropertyRowMapper` is unsuitable because records lack a no-arg constructor and setters. Spring JDBC provides `DataClassRowMapper<T>` for classes with **constructors with named parameters**, such as Java records or Kotlin data classes:

```java
CustomerView customer = jdbc.queryForObject(
    "SELECT id, first_name, email_address " +
    "FROM customer WHERE id = ?",
    DataClassRowMapper.newInstance(CustomerView.class),
    customerId
);
```

This is an integration snippet requiring the bean/database and `jdbc`. `DataClassRowMapper` maps constructor parameters like `firstName` via column name `first_name`, while still supporting setters for certain hybrid classes. If both a constructor and a setter can receive the same property, the constructor takes precedence to avoid duplicate assignment.

For ordinary immutable classes with parameterized constructors, name-based mapping requires **parameter-name metadata** to be present; for regular Java classes, compile with `-parameters`. Java records carry record component metadata natively, yet consistent compiler configuration prevents surprises if refactored to a regular class later.

Comparison:

| Criterion | `BeanPropertyRowMapper` | `DataClassRowMapper` | Custom `RowMapper` |
| --- | --- | --- | --- |
| Target type | JavaBean with no-arg constructor and setters | Record/data class/constructor parameters; can combine with setters | Any object code can construct |
| Naming rules | Property name and underscore name | Matching constructor parameter/property name | Defined by your code |
| SQL alias | Recommended when names differ | Recommended when names differ | Can read any column name desired |
| Complex mapping | Limited capability | Limited capability | Most flexible |
| Optimizing hot paths | Favors convenience over peak optimization | Convenient | Can avoid reflection overhead when written deliberately |

Not every constructor DTO should use `DataClassRowMapper`. When conversion needs business logic, nested objects, relationships, or careful validation, a custom mapper is usually clearer.

## 10. Complete Java 17+ Example: Column Names, Aliases, NULL, Strict Mode, and Record

This program uses **Spring JDBC 6.1.14, H2 2.2.224, Java 17+, and Maven**. Spring Boot is not needed. The goal is to observe:

1. Column `first_name` goes into setter `setFirstName`.
2. Column `email_address` goes into `setEmailAddress`.
3. SQL alias `chosen_name` goes into `setChosenName` even though the original column is `first_name`.
4. SQL `NULL` is preserved as `null` in `String`/`Integer` properties.
5. `DataClassRowMapper` constructs a record via its constructor.
6. `query(...)` returns two beans for two rows.
7. `checkFullyPopulated(true)` detects missing writable properties.

### Project Structure

```text
bean-mapper-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── BeanMapperDemo.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>bean-mapper-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### File `src/main/java/BeanMapperDemo.java`

```java
import java.util.List;

import org.springframework.dao.InvalidDataAccessApiUsageException;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class BeanMapperDemo {
    // Static nested class + public no-arg constructor.
    public static class CustomerBean {
        private long id;
        private String firstName;
        private String lastName;
        private String emailAddress;
        private Integer rewardPoints;

        public CustomerBean() {}

        public long getId() {
            return id;
        }

        public void setId(long id) {
            this.id = id;
        }

        public String getFirstName() {
            return firstName;
        }

        public void setFirstName(String firstName) {
            this.firstName = firstName;
        }

        public String getLastName() {
            return lastName;
        }

        public void setLastName(String lastName) {
            this.lastName = lastName;
        }

        public String getEmailAddress() {
            return emailAddress;
        }

        public void setEmailAddress(String emailAddress) {
            this.emailAddress = emailAddress;
        }

        public Integer getRewardPoints() {
            return rewardPoints;
        }

        public void setRewardPoints(Integer rewardPoints) {
            this.rewardPoints = rewardPoints;
        }
    }

    public static class LabelBean {
        private String chosenName;

        public LabelBean() {}

        public String getChosenName() {
            return chosenName;
        }

        public void setChosenName(String chosenName) {
            this.chosenName = chosenName;
        }
    }

    public record CustomerView(
            long id, String firstName, String emailAddress) {}

    public static void main(String[] args) {
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:bean_mapper;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(source);
        jdbc.execute(
            "CREATE TABLE customer (" +
            "id BIGINT PRIMARY KEY, " +
            "first_name VARCHAR(80) NOT NULL, " +
            "last_name VARCHAR(80), " +
            "email_address VARCHAR(120) NOT NULL, " +
            "reward_points INTEGER)"
        );

        jdbc.update(
            "INSERT INTO customer " +
            "(id, first_name, last_name, email_address, reward_points) " +
            "VALUES (?, ?, ?, ?, ?)",
            1L, "An", "Nguyen", "an@example.test", 15
        );
        jdbc.update(
            "INSERT INTO customer " +
            "(id, first_name, last_name, email_address, reward_points) " +
            "VALUES (?, ?, ?, ?, ?)",
            2L, "Binh", null, "binh@example.test", null
        );

        BeanPropertyRowMapper<CustomerBean> beanMapper =
            BeanPropertyRowMapper.newInstance(CustomerBean.class);

        String columns =
            "SELECT id, first_name, last_name, " +
            "email_address, reward_points " +
            "FROM customer WHERE id = ?";

        CustomerBean an = jdbc.queryForObject(
            columns, beanMapper, 1L
        );
        System.out.println(
            "Bean: " + an.getId() + " | " +
            an.getFirstName() + " " + an.getLastName() +
            " | " + an.getRewardPoints()
        );

        CustomerBean binh = jdbc.queryForObject(
            columns, beanMapper, 2L
        );
        System.out.println(
            "SQL NULL: lastName=" + (binh.getLastName() == null) +
            ", rewardPoints=" + (binh.getRewardPoints() == null)
        );

        LabelBean label = jdbc.queryForObject(
            "SELECT first_name AS chosen_name " +
            "FROM customer WHERE id = ?",
            BeanPropertyRowMapper.newInstance(LabelBean.class),
            1L
        );
        System.out.println("Alias: " + label.getChosenName());

        CustomerView record = jdbc.queryForObject(
            "SELECT id, first_name, email_address " +
            "FROM customer WHERE id = ?",
            DataClassRowMapper.newInstance(CustomerView.class),
            1L
        );
        System.out.println(
            "Record: " + record.id() + " | " +
            record.firstName() + " | " + record.emailAddress()
        );

        List<CustomerBean> all = jdbc.query(
            "SELECT id, first_name, last_name, " +
            "email_address, reward_points " +
            "FROM customer ORDER BY id",
            beanMapper
        );
        System.out.println("List size: " + all.size());

        BeanPropertyRowMapper<CustomerBean> strict =
            BeanPropertyRowMapper.newInstance(CustomerBean.class);
        strict.setCheckFullyPopulated(true);
        try {
            jdbc.queryForObject(
                "SELECT id, first_name FROM customer WHERE id = ?",
                strict, 1L
            );
            throw new AssertionError("Strict mapping should fail");
        } catch (InvalidDataAccessApiUsageException expected) {
            System.out.println(
                "Strict: missing writable properties detected"
            );
        }
    }
}
```

### Compiling and Running

In the directory containing `pom.xml`, JDK 17+ and Maven are required:

```bash
mvn -q compile exec:java -Dexec.mainClass=BeanMapperDemo
```

The program's `System.out.println` lines:

```text
Bean: 1 | An Nguyen | 15
SQL NULL: lastName=true, rewardPoints=true
Alias: An
Record: 1 | An | an@example.test
List size: 2
Strict: missing writable properties detected
```

Depending on the environment, Maven and libraries may print their own logs; those lines are not part of the application output above.

### Output Explanation

- The `Bean` line proves that `FIRST_NAME`/`LAST_NAME` labels exposed by H2 metadata still assign `firstName`/`lastName` properly. `reward_points` maps to `Integer rewardPoints`.
- The `SQL NULL` line shows that Binh's `last_name` and `reward_points` are both SQL `NULL`; both Java reference properties remain `null`.
- The `Alias` line verifies that `first_name AS chosen_name` maps into setter `setChosenName` even though the bean has no `firstName` property.
- The `Record` line shows `DataClassRowMapper` mapping via the record constructor with parameters `id`, `firstName`, and `emailAddress`; no setters are needed.
- `List size: 2` illustrates `RowMapper` running per row and `query` collecting the list.
- The strict mapper receives a projection containing only `id` and `first_name` while the target still has writable properties `lastName`, `emailAddress`, and `rewardPoints`. It throws `InvalidDataAccessApiUsageException`, which is caught to print the final line.

The example uses a simple `DriverManagerDataSource` to run standalone; this implementation **is not a connection pool** and should not be treated as a production performance setup. The program does not need an application context, `@Repository`, or `@Transactional` to demonstrate the mapping mechanism.

## 11. Comparing Automatic Mappers with a Hand-Written `RowMapper`

`BeanPropertyRowMapper` works well when SQL results map directly to a simple bean and column naming is consistent. However, if the query involves complex logic, explicit mapper code can be better.

Example with a result record whose column names do not match or require formatting:

```java
public record PersonSummary(long id, String label) {}

// Illustrative snippet inside an application with JdbcTemplate jdbc.
List<PersonSummary> people = jdbc.query(
    "SELECT user_id, first_name, last_name FROM legacy_user",
    (rs, rowNum) -> new PersonSummary(
        rs.getLong("user_id"),
        rs.getString("first_name") + " " +
        rs.getString("last_name")
    )
);
```

This is an example snippet, not runnable on its own as it lacks the table, `JdbcTemplate`, and enclosing type file. A hand-written mapper makes label concatenation explicit. If `last_name` can be `NULL`, the example above also needs a business rule to avoid producing `"null"` strings; handle it explicitly with `rs.getString(...)`, conditions, and domain rules rather than expecting `BeanPropertyRowMapper` to infer it.

Cases where an explicit mapper should be considered:

- Queries spanning multiple tables where one row must build nested objects with custom logic.
- JSON/array/enum/vendor-specific SQL types needing controlled conversion.
- Inconsistent column names, or one property computed from **multiple columns**.
- Complex validation/domain invariants: e.g., start date must precede end date.
- Performance-sensitive hot paths needing to avoid part of the reflection/property-binding overhead.
- Immutable models with constructors/records whose mapping rules do not match parameter names.

Even with a hand-written mapper, each `mapRow` call still represents one row. If you need to **collapse multiple rows into an object tree**, design an extractor/aggregation over the entire `ResultSet` or build a keyed map in the data access layer. `BeanPropertyRowMapper` does not solve one-to-many relationships automatically.

## 12. Common Mistakes When Using Property Naming Rules

| Symptom | Possible cause | How to inspect and fix |
| --- | --- | --- |
| `firstName` is always `null` | SQL column is named `given_name` while the bean only has `setFirstName`. | `SELECT given_name AS first_name` or custom mapper. |
| Field exists yet remains unpopulated | Missing writable JavaBeans property (public setter), or unsuitable class. | Check JavaBeans `PropertyDescriptor`; add setter or change mapper. |
| Bean cannot be instantiated | Only parameterized constructor exists, or non-static inner class. | Use top-level/static nested JavaBean with no-arg constructor; use `DataClassRowMapper` for records. |
| `NULL` causes `TypeMismatchException` | Property is a primitive like `int`/`boolean`. | Use wrappers `Integer`/`Boolean` if DB allows NULL; do not mask NULL with arbitrary defaults. |
| SQL returns rows but some properties stay blank | Query omits those columns; default `checkFullyPopulated=false`. | Inspect projection, use a matching bean DTO, or enable strict mode when all writable properties are truly required. |
| Strict mapper fails on a valid projection | Target bean has more setters than selected columns. | Split out a projection DTO or intentionally turn strict mode off. |
| SELECT has JOIN, property assigned unpredictably | Column names/aliases collide across tables. | Explicit projections and unique aliases. |
| `@Column(name="...")` has no effect on mapper | Annotation belongs to JPA, not Spring JDBC's bean mapper rules. | Use SQL aliases, DTOs, or a custom mapper. |
| `queryForObject` throws `IncorrectResultSizeDataAccessException` | Query returned 0 or more than 1 row, not a property-naming bug. | Respect cardinality; use `query` when a list is expected. |
| `BeanPropertyRowMapper` does not build nested children | Mapper does not aggregate multiple rows or perform nested mapping. | Custom `RowMapper` or `ResultSetExtractor`/aggregation. |
| Wrong date/time, enum, or JSON type | JDBC value or conversion service does not satisfy domain rules. | Check driver/SQL type and custom converter/mapper. |
| Reusing a shared mapper and mutating config across threads | Mapping metadata and options become inconsistent. | Configure once, then reuse as a read-only object. |

## 13. Testing Strategy for Automatic Mapping

A good test does not only verify that `id` is populated; it must check cases prone to breaking when SQL/schema changes:

1. **Naming rules:** `first_name` → `firstName`; `email_address` → `emailAddress`; alias `chosen_name` → `chosenName`.
2. **Present and missing columns:** explicit partial projections and strict mapping requiring all writable properties.
3. **NULL:** `String`/`Integer` receive null; primitive null throws under default config; verify if default-for-null is deliberately enabled.
4. **Constructors:** beans have no-arg/setters; records use `DataClassRowMapper`; non-static inner classes are not used as ordinary DTOs.
5. **Data types:** numbers, booleans, dates/times, enums, or custom converters if used by the domain.
6. **Aliases in JOINs:** SQL joining multiple tables with `id`, `name`; ensure explicit aliases and no mis-mapping.
7. **Cardinality:** zero rows, one row, and multiple rows with `queryForObject`; lists with `query`.
8. **Assert values rather than only checking no exception is thrown:** assert every important property precisely, including unwanted default values.

Example of useful assertions in a unit/integration test:

```java
// Illustrative snippet in a test that already has a mapped bean.
assertEquals("An", bean.getFirstName());
assertEquals("an@example.test", bean.getEmailAddress());
assertEquals(Integer.valueOf(15), bean.getRewardPoints());
```

This is not a complete test; it requires an assertion framework (such as JUnit), the `bean` instance, and fixture data. For JDBC mapping, tests running against a database of the same dialect or a carefully designed H2 fixture catch many alias/case/type issues. H2 can differ from PostgreSQL/MySQL/Oracle in column-name metadata and SQL types, so critical paths should also be tested against the actual production database.

## 14. Choosing a Mapper for Real Needs

A decision flow:

```text
Need to map a ResultSet row to an object?
        |
        +-- JavaBean with no-arg + public setters, matching column names?
        |       |
        |       +-- Yes, simple mapping
        |             -> BeanPropertyRowMapper
        |             -> SQL alias when DB and property names diverge
        |
        +-- Record / Kotlin data class / constructor parameters?
        |       -> DataClassRowMapper
        |
        +-- Values need transformation / nesting / custom logic?
        |       -> Hand-written RowMapper or appropriate extractor/aggregation
        |
        +-- Multiple rows in the result?
                -> query(...) or appropriate collection/stream API
                -> Do not expect BeanPropertyRowMapper to merge multiple rows
```

For larger projects, keep clear boundaries:

- **SQL** decides which data is selected and the names/aliases of output columns.
- **`RowMapper`** decides which object one row turns into.
- **Repository API** decides whether to return a single object, `Optional`, or a list.
- **Service/domain** decides invariants, validation, and business transformations.
- **Transaction manager** decides transaction boundaries; the mapper does not replace it.

Putting too much transformation logic inside a bean setter with side effects can also make behavior unpredictable. Keep DTOs simple, and place complex logic in a layer with clear contracts and dedicated tests.

## 15. Checklist Before Using `BeanPropertyRowMapper` in Production

1. **Is the class suitable?** Top-level or static nested, instantiable via a no-arg constructor, with public setters for properties to map.
2. **Is the SQL projection explicit?** Avoid `SELECT *`, especially in JOINs.
3. **Do column names/aliases match JavaBeans properties?** Check `camelCase` ↔ `snake_case`; use aliases for non-matching names.
4. **Are there duplicate column labels?** Use unique aliases to avoid misassignment.
5. **Does every SQL NULL have a compatible Java type?** Prefer wrappers if the DB allows NULL.
6. **Are any properties silently omitted?** Consider strict mode or a projection-specific DTO.
7. **Are there JPA annotations you wrongly expect the mapper to honor?** `BeanPropertyRowMapper` does not use JPA annotations.
8. **Is the object type immutable?** Records/constructor DTOs should use `DataClassRowMapper` or a custom mapper.
9. **Does row cardinality match the repository contract?** Distinguish `queryForObject` and `query`.
10. **Are there tests covering names, aliases, NULL, conversions, multiple rows, and the real database dialect?**
11. **Is automatic mapping clear enough?** If handling complex nested/derived values or performance-critical paths, prefer an explicit mapper.

### Key Takeaways

- `BeanPropertyRowMapper<T>` creates **one JavaBean per ResultSet row** and populates **writable JavaBeans properties** via setters.
- Typical naming rule: `first_name` or `FIRST_NAME` matches `firstName`; `email_address` matches `emailAddress`. It does not infer that `given_name` has the same meaning as `firstName`.
- When column names differ from property names, **`SELECT db_column AS java_property_in_snake_case`** is a simple and explicit solution.
- JavaBeans need a no-arg constructor and setters; **records** should use `DataClassRowMapper` or a custom `RowMapper`.
- `checkFullyPopulated` defaults to `false`, so missing properties can retain default values; enable `true` when you need to enforce that all writable properties are mapped.
- SQL `NULL` maps to `null` on reference types; primitive nulls fail by default with a type mismatch. Avoid enabling primitive-default-for-null if it erases data semantics.
- `BeanPropertyRowMapper` does not replace `JdbcTemplate`, cardinality handling, transactions, domain validation, or nested relationship handling.
- When automatic mapping becomes hard to reason about or performance-sensitive, use an explicit `RowMapper`; clear code and exact contracts matter more than fewer lines of code.

### References

- Spring Framework — `BeanPropertyRowMapper` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/jdbc/core/BeanPropertyRowMapper.html
- Spring Framework — `DataClassRowMapper` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html
- Spring Framework — JDBC querying: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — `JdbcTemplate` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Java SE — JavaBeans introspection: https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html
