# Differences in Quoting, Limit/Offset, Generated Keys, and Data Types

Spring Data JDBC supports multiple database management systems through an abstraction called **Dialect**. A dialect describes SQL and JDBC differences the framework needs to know, such as how identifiers are quoted, how rows are limited, how database-generated IDs are retrieved, and certain data type capabilities.

Thanks to the dialect, repositories and JdbcAggregateTemplate can generate SQL tailored to the configured database without forcing application code to write every vendor-specific syntax manually. However, a dialect does not turn custom SQL into cross-platform SQL. When writing statements in @Query or JdbcTemplate, developers must still use identifier, pagination, generated-key, and data type syntax suited to the actual DBMS/driver.

This lesson explains four differences that commonly cause failures when switching databases or changing JDBC drivers: **identifier quoting and casing rules; LIMIT/OFFSET; generated keys; and data type mapping**.

## 1. What is a Dialect?

A dialect is a set of SQL/JDBC rules for a specific database management system. Spring Data Relational uses the dialect to generate statements and map features whose SQL varies across databases.

For example, databases can differ in:

- Characters used to quote table/column names.
- How unquoted identifiers are normalized to uppercase or lowercase.
- Syntax for limiting rows and skipping rows.
- How newly generated IDs are returned after INSERT.
- Support for sequences, identity columns, and generated columns.
- Data types such as UUID, JSON, array, enum, boolean, and timestamp.
- Capabilities for row locking, returning rows after INSERT/UPDATE, or other specialized features.

In Spring Data JDBC, the dialect is used by SQL generation and mapping components. CRUD repositories and JdbcAggregateTemplate can rely on the dialect to choose appropriate syntax.

~~~mermaid
flowchart TD
    A[Repository or JdbcAggregateTemplate] --> B[Spring Data Relational mapping]
    B --> C[Database dialect]
    C --> D[SQL identifier processing]
    C --> E[Pagination and generated key strategy]
    C --> F[JDBC type and converter support]
    D --> G[JDBC driver]
    E --> G
    F --> G
    G --> H[(Database)]
~~~

A dialect is not a configuration that replaces the JDBC driver. The driver remains responsible for executing the JDBC API, converting data types, and communicating with the database. The dialect gives Spring Data the rules needed to generate compatible SQL.

## 2. How is the Dialect selected per database?

In a Spring Boot application, the DataSource is typically configured from a URL, driver class, and connection credentials. Spring Data JDBC uses database metadata and supported dialects to select appropriate handling.

Example PostgreSQL connection configuration:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: app
    password: secret
~~~

Example H2 configuration for a test environment:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:shop;DB_CLOSE_DELAY=-1
    username: sa
    password:
~~~

Applications should not hard-code the assumption that SQL generated for H2 will always behave identically on PostgreSQL, MySQL, SQL Server, or Oracle. Changing the URL/driver can also change the dialect and certain JDBC behaviors.

Spring Data Relational has dialect implementations for supported databases. For a new unrecognized database or JDBC driver, check the Spring Data Relational version, existing dialect capabilities, and supported extension mechanisms in that version. Do not simply swap the driver and assume all specialized syntax is handled automatically.

### Inspecting the running database and driver

JDBC DatabaseMetaData reveals information about the connection environment:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());
    System.out.println(metadata.getIdentifierQuoteString());
}
~~~

This information is useful when debugging across different environments. Note that the connection in the example is opened directly and must be closed; in code running inside a transaction, do not acquire an independent connection to infer the state of the current transaction.

## 3. What is an Identifier and why is quoting needed?

An identifier is the name of an object in SQL, such as:

- Table name: customers, purchase_orders.
- Column name: id, created_at, display_name.
- Schema, sequence, index, or alias name.

An identifier differs from a **value**. A value is data passed into a condition, such as an email, status, or ID.

For example:

~~~sql
SELECT id, display_name
FROM customers
WHERE email = ?;
~~~

In the statement above:

- customers, id, display_name, and email are identifiers.
- The email value passed via the question mark is a value.

Bind parameters are used to pass values, not to substitute identifiers. The following example does not mean selecting a table by parameter value:

~~~sql
SELECT * FROM ?;
~~~

If a table or column name needs to be chosen dynamically, map the user input to an allowlisted set of identifiers and then build the appropriate SQL. Never concatenate user-supplied identifiers directly into SQL statements.

### Identifier quoting

Quoting wraps an identifier in delimiter characters so the database treats that name as an exact identifier, especially when the name has significant uppercase/lowercase letters, spaces, or collides with a keyword.

Common quoting styles:

| Database / SQL system | Common identifier quote character | Example |
|---|---|---|
| PostgreSQL | Double quotes | "Order" |
| H2 | Double quotes | "Order" |
| Oracle | Double quotes | "Order" |
| MySQL | Backticks | `order` |
| MariaDB | Backticks | `order` |
| SQL Server | Square brackets; double quotes when configured appropriately | [Order] |

Exact syntax depends on the DBMS and configuration. Do not take a backtick-quoted SQL statement from MySQL and run it verbatim on PostgreSQL.

## 4. Reserved words and collision-prone table/column names

Certain words are SQL keywords or reserved words. Names like order, user, group, rank, or value can cause conflicts depending on the database and version.

Example schema using table name order:

~~~sql
CREATE TABLE order (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30)
);
~~~

The statement may be rejected by the parser because ORDER is a keyword. You can quote the identifier according to the DBMS syntax:

~~~sql
CREATE TABLE "order" (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30)
);
~~~

However, the statement above is only an example for systems supporting double quotes. In MySQL, the common quoting style is:

~~~sql
CREATE TABLE `order` (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30)
);
~~~

Names that avoid keywords are usually easier to maintain. For instance, using purchase_orders instead of order reduces the need for quoting and makes the schema more readable.

If tables/columns already exist with names matching keywords, unify quoting practices across migrations, custom SQL, views, triggers, and query code.

## 5. Identifier letter-casing rules

Databases do not agree on how unquoted identifiers are handled.

Common differences:

- PostgreSQL folds unquoted identifiers to lowercase.
- Oracle typically normalizes unquoted identifiers to uppercase.
- SQL Server generally resolves names according to collation and configuration.
- MySQL has specific rules for database/table names that can be affected by the operating system and lower_case_table_names configuration; column names are usually case-insensitive.

Example on PostgreSQL:

~~~sql
CREATE TABLE Customer (
    id BIGINT PRIMARY KEY
);
~~~

The unquoted name is normalized to customer. Whereas:

~~~sql
CREATE TABLE "Customer" (
    id BIGINT PRIMARY KEY
);
~~~

creates an identifier where the uppercase C is preserved. Subsequent queries must use the matching quoting and spelling:

~~~sql
SELECT * FROM "Customer";
~~~

If a query writes SELECT * FROM Customer, PostgreSQL looks for lowercase customer and will not necessarily find the "Customer" table.

This rule can cause errors when migrating schemas from one database to another, especially when migrations create mixed-case or quoted names.

### Portable naming conventions

To minimize quoting issues:

- Use lowercase table/column names.
- Use snake_case for physical identifiers.
- Avoid SQL keywords.
- Do not use spaces or special characters in names.
- Keep naming strategies consistent across entities, migrations, and custom SQL.
- Only use quoted mixed-case identifiers when there is a clear reason and you accept having to match the exact spelling everywhere.

## 6. Quoting in Spring Data JDBC mapping

Entities can declare tables and columns via metadata:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Column("order_number") String orderNumber,
        String status
) {}
~~~

The Java property name is orderNumber, while the physical column name is order_number. Spring Data uses mapping metadata and the dialect's identifier processing when generating SQL.

The dialect may quote identifiers in framework-generated SQL according to database rules. Therefore, generated SQL does not necessarily match the exact hand-written SQL you might expect, even though they share the same meaning.

If you need to use a table/column name that collides with a keyword, you can configure the mapped name as supported by your Spring Data Relational version and dialect. Verify the generated SQL against the real database. Do not assume @Table or @Column annotations will automatically fix custom SQL statements.

### Hand-written SQL is not rewritten by the dialect

Example repository method:

~~~java
@Query("""
    SELECT id, order_number, status
    FROM purchase_orders
    WHERE status = :status
    """)
List<PurchaseOrder> findByStatus(@Param("status") String status);
~~~

Table/column names inside @Query are identifiers written by the developer. The framework binds the status parameter, but cannot automatically convert arbitrary SQL from MySQL quoting syntax to PostgreSQL or fix every reserved word.

When custom SQL must run across multiple databases, you should:

- Use a common SQL syntax subset where possible.
- Avoid identifiers requiring quoting.
- Separate queries per dialect/database when truly necessary.
- Use custom repository abstractions to encapsulate differences.
- Test migrations and queries against each target DBMS.

## 7. LIMIT and OFFSET for pagination

Offset-based pagination has two parts:

- **LIMIT**: maximum number of rows to receive.
- **OFFSET**: number of rows to skip before returning results.

For example:

~~~sql
SELECT id, order_number, status
FROM purchase_orders
ORDER BY created_at DESC, id ASC
LIMIT 20 OFFSET 40;
~~~

The statement fetches at most 20 rows after skipping the first 40 rows in the sorted order.

If page numbers are 0-based, the formula is:

~~~text
offset = pageNumber * pageSize
~~~

For example, pageNumber = 2, pageSize = 20 gives offset = 40.

Without ORDER BY, the database does not guarantee row order. Pagination without a stable order can cause a record to appear on multiple pages or be skipped when data changes.

## 8. Pagination syntax differs across databases

Not every database uses LIMIT/OFFSET like PostgreSQL/MySQL.

| Database | Example result-limiting syntax |
|---|---|
| PostgreSQL | LIMIT n OFFSET m |
| MySQL / MariaDB | LIMIT n OFFSET m or LIMIT m, n |
| H2 | LIMIT n OFFSET m; also supports standard syntax depending on version |
| SQL Server | ORDER BY ... OFFSET m ROWS FETCH NEXT n ROWS ONLY |
| Modern Oracle | OFFSET m ROWS FETCH NEXT n ROWS ONLY |
| Older Oracle versions | May use ROWNUM or nested subqueries |

SQL Server example:

~~~sql
SELECT id, order_number, status
FROM purchase_orders
ORDER BY created_at DESC, id ASC
OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Modern Oracle example:

~~~sql
SELECT id, order_number, status
FROM purchase_orders
ORDER BY created_at DESC, id ASC
OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

This is a difference that the dialect can handle when Spring Data generates queries. If you write a manual @Query containing LIMIT 20 OFFSET 40, that statement may fail on SQL Server or older Oracle versions that do not support that syntax.

## 9. Using Pageable and Query to avoid writing pagination syntax manually

In a repository, a method can accept Pageable according to Spring Data JDBC capabilities:

~~~java
Page<PurchaseOrder> findByStatus(String status, Pageable pageable);
~~~

When using JdbcAggregateTemplate, you can apply Pageable to a Query:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")
        )
);

Query baseQuery = Query.query(
        Criteria.where("status").is("OPEN")
);

Query pageQuery = baseQuery.with(pageable);

List<PurchaseOrder> content =
        template.findAll(pageQuery, PurchaseOrder.class);
~~~

The dialect produces the appropriate SQL limit and offset clauses. Application code does not need to decide whether to use LIMIT, OFFSET FETCH, or ROWNUM.

If you need a Page<T> with total element count, count using the unpaginated base query:

~~~java
long total = template.count(baseQuery, PurchaseOrder.class);
Page<PurchaseOrder> page = new PageImpl<>(content, pageable, total);
~~~

Fetching the data and counting are two separate queries. Under concurrent data modifications, total and content may reflect different points in time; transaction/isolation should be considered according to requirements.

### Stable sorting is practically mandatory

A stable page should have a deterministic order, especially when the primary sort column may have ties:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);
~~~

If sorting only by createdAt, multiple orders with the same timestamp may change order across queries. Adding a unique key such as id as the final tie-breaker makes pagination results stable.

## 10. Offset pagination has performance limits

Large offsets can be expensive because the database must locate and skip many rows before returning results.

For example, page 1,000 with page size 50 has an offset of 49,950. Depending on the execution plan and indexes, the database may have to scan a large amount of data.

When traversing large datasets or deep pages, consider **keyset/seek pagination**. For example, sorting created_at descending and id descending; the next page uses the last pair of values from the previous page:

~~~sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
ORDER BY created_at DESC, id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

The final limit syntax still depends on the dialect. The keyset idea is filtering from the last key of the previous page rather than skipping rows by offset.

Keyset pagination fits when:

- The dataset is large.
- Users mainly navigate to the next page.
- There is a stable sort column and unique key as tie-breaker.
- Arbitrary jumps to very distant page numbers are not required.

Do not assume Pageable automatically turns offset pagination into keyset pagination. That is a different query strategy and must be explicitly designed.

## 11. What are generated keys?

When INSERTing a row, the database can automatically generate the primary key. For example, an identity/auto-increment column:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
~~~

The application inserts without passing id:

~~~sql
INSERT INTO customers(name) VALUES ('Lan');
~~~

The database generates an ID, such as 101. The application often needs that ID to:

- Return the saved object to the caller.
- Attach foreign keys for child rows belonging to the aggregate.
- Build a URL or response.
- Write audit or outbox records.
- Perform the next step within the same transaction.

A generated key is a key value allocated by the database. It differs from the update count, which is the number of rows affected by the statement.

## 12. How does Spring Data JDBC retrieve generated IDs?

When an aggregate root has an @Id property and the ID value represents a new entity under newness rules, Spring Data JDBC uses a strategy matching the dialect/driver to insert and retrieve the generated ID.

For example:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Saving a new aggregate:

~~~java
Customer input = new Customer(null, "Lan");
Customer saved = repository.save(input);

Long generatedId = saved.id();
~~~

With immutable records, use the object returned from save. Do not assume the input object was mutated to receive the ID.

Spring Data JDBC may use the JDBC driver's generated-keys capability or a database-specific strategy. Exact SQL/returning strategy details depend on the dialect and driver.

### Application-assigned IDs differ from database-generated IDs

If the application generates the ID, such as a UUID:

~~~java
Customer input = new Customer(UUID.randomUUID(), "Lan");
Customer saved = repository.save(input);
~~~

then the ID already exists before INSERT and no generated identity needs to be retrieved from the database. However, the new-entity detection strategy must match how IDs are assigned; do not just change the ID type and assume every repository will automatically recognize the object as new.

In Spring Data JDBC, new-entity detection rules can rely on a null ID or null version when the entity uses @Version, and can be customized via Persistable when needed. Choose an explicit strategy so entities with pre-assigned IDs are not mistakenly treated as existing entities.

## 13. JDBC generated keys API

JDBC provides the ability to request generated keys when creating a PreparedStatement and read results via getGeneratedKeys():

~~~java
PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO customers(name) VALUES (?)",
        Statement.RETURN_GENERATED_KEYS
);
~~~

After executeUpdate:

~~~java
int affected = statement.executeUpdate();

try (ResultSet keys = statement.getGeneratedKeys()) {
    if (keys.next()) {
        long id = keys.getLong(1);
    }
}
~~~

This is the generic JDBC API. The driver/database must support returning generated keys in that manner, and there can be differences in returned columns, column names, or data types.

You can check whether the driver reports support:

~~~java
boolean supportsGeneratedKeys =
        connection.getMetaData().supportsGetGeneratedKeys();
~~~

Metadata information does not replace integration testing. Test the exact INSERT statement with the exact driver in use.

## 14. Retrieving generated keys with JdbcTemplate and KeyHolder

When writing custom JDBC code, Spring JDBC provides KeyHolder and GeneratedKeyHolder:

~~~java
import java.sql.Statement;
import org.springframework.jdbc.core.PreparedStatementCreator;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

KeyHolder keyHolder = new GeneratedKeyHolder();

PreparedStatementCreator creator = connection -> {
    PreparedStatement statement = connection.prepareStatement(
            "INSERT INTO customers(name) VALUES (?)",
            Statement.RETURN_GENERATED_KEYS
    );
    statement.setString(1, "Lan");
    return statement;
};

int affected = jdbcTemplate.update(creator, keyHolder);

Number key = keyHolder.getKey();
Long generatedId = key == null ? null : key.longValue();
~~~

The example uses the standard JDBC generated-keys API. Some drivers require specifying generated key columns or support alternative retrieval mechanisms. Check driver documentation and test against the target database.

Do not write ID-retrieval logic by running a separate SELECT like "current maximum ID":

~~~sql
SELECT MAX(id) FROM customers;
~~~

This approach is unsafe under concurrent insert transactions; the maximum value may belong to another transaction. Use the generated key from the INSERT itself or an appropriate sequence/returning mechanism.

## 15. PostgreSQL RETURNING and similar mechanisms

Some databases support returning data from INSERT/UPDATE/DELETE statements. PostgreSQL has RETURNING:

~~~sql
INSERT INTO customers(name)
VALUES ('Lan')
RETURNING id;
~~~

SQL Server has OUTPUT inserted:

~~~sql
INSERT INTO customers(name)
OUTPUT inserted.id
VALUES ('Lan');
~~~

This is database-specific syntax. The JDBC driver and Spring Data dialect may use an appropriate strategy for framework-managed operations, but hand-written SQL must use the DBMS's exact syntax.

If a custom query needs to return an ID or full row after INSERT, determine the JDBC API suited to the returned result set. Do not assume every INSERT with RETURNING can be called via JdbcTemplate.update(...) and return an ID like an update count; depending on the API, you may need query/PreparedStatement or a RowMapper to read the ResultSet.

## 16. Sequences and identity are not the same

Two common ID generation strategies:

- **Identity/auto-increment**: the database generates the value when inserting a row.
- **Sequence**: the database provides a sequence object to issue values before or during insert.

Sequence SQL example:

~~~sql
CREATE SEQUENCE customer_id_seq START WITH 1 INCREMENT BY 1;
~~~

One database may use:

~~~sql
INSERT INTO customers(id, name)
VALUES (NEXT VALUE FOR customer_id_seq, 'Lan');
~~~

Another database may use nextval syntax or a different sequence expression. Retrieving sequence values also has specific semantics.

Spring Data JDBC supports ID generation according to the mapping/dialect capabilities of the version and database. If a schema uses a specialized sequence or an ID strategy not automatically supported, configure it according to the current Spring Data Relational API or implement controlled custom persistence. Do not copy sequence syntax from Oracle to PostgreSQL or vice versa without checking.

## 17. JDBC types and Java types do not always map one-to-one

JDBC defines standard data types via java.sql.Types/JDBCType, but each DBMS has its own physical type set and driver mapping.

For example:

| Common database type | Common Java type | Notes |
|---|---|---|
| BIGINT | Long / long | Use Long if nullable |
| INTEGER | Integer / int | Check overflow and nullability |
| VARCHAR | String | Encoding, collation, and length |
| BOOLEAN / BIT | Boolean / boolean | Behavior depends on database/driver |
| DECIMAL / NUMERIC | BigDecimal | Preserves precision and scale |
| DATE | LocalDate | Represents calendar date only |
| TIMESTAMP | LocalDateTime or suitable time type | Distinguish local time vs instant |
| TIMESTAMP WITH TIME ZONE | OffsetDateTime / Instant depending on mapping | Timezone semantics vary by DBMS |
| BINARY / VARBINARY / BLOB | byte[] | Size and streaming |
| UUID | UUID or String | Physical type support depends on database |
| JSON / JSONB | String or domain type via converter | Not a uniform portable JDBC type |
| ARRAY | SQL Array or collection via converter | Driver support varies greatly |

Do not assume every database has the same BOOLEAN, UUID, or JSON type. Some DBs use native types; others use CHAR/VARCHAR, BINARY, or extension types.

## 18. Booleans, enums, and numeric types

### Boolean

Some databases have a true BOOLEAN type; some systems use BIT, NUMBER(1), or numeric/string representations. Drivers may convert them in their own way.

If a legacy schema stores active as CHAR(1) with Y/N, a Java Boolean property needs a converter to map explicitly:

~~~java
@WritingConverter
public class BooleanWritingConverter
        implements Converter<Boolean, String> {

    @Override
    public String convert(Boolean source) {
        return Boolean.TRUE.equals(source) ? "Y" : "N";
    }
}
~~~

A reading converter must map Y/N back to Boolean. Do not use this converter if the database already has a native boolean type and suitable driver mapping.

### Enum

If an enum is stored by name, the database value depends on the Java enum constant name. Renaming an enum constant may require a data migration.

~~~java
enum OrderStatus {
    NEW, PAID, SHIPPED
}
~~~

For long-lived systems, a converter storing stable codes such as N/P/S can be used instead of relying on enum names. Both writing and reading converters are needed to ensure bidirectional consistency.

### Numbers and currency

Use BigDecimal for DECIMAL/NUMERIC. Avoid converting through double when values require exactness such as currency.

~~~java
BigDecimal total = new BigDecimal("1250.50");
~~~

Align precision/scale across Java, schema, and data. If the database uses DECIMAL(12,2), values with excess digits or scale may be rejected, rounded, or truncated depending on DBMS behavior.

## 19. Temporal types and timezones

Date and time handling is a common source of bugs when switching databases or drivers.

Distinguish between:

- LocalDate: calendar date, no time of day.
- LocalTime: time of day, no date.
- LocalDateTime: local date and time, carrying no offset/timezone.
- OffsetDateTime: date and time with a UTC offset.
- Instant: a point on the UTC timeline.

TIMESTAMP and TIMESTAMP WITH TIME ZONE do not share identical semantics across all DBMSs. Some databases store local timestamps; some normalize to UTC; some store offsets or interpret according to session timezone.

Example domain storing Instant:

~~~java
public record AuditEntry(
        Long id,
        Instant createdAt
) {}
~~~

When reading/writing, standardize on a timezone policy, typically UTC at the persistence boundary and converting to display timezone at the presentation layer. Verify that the JDBC driver supports the desired type conversion and database timestamp precision.

Do not assume LocalDateTime can replace Instant if business logic needs an absolute point in time. LocalDateTime carries no offset and therefore cannot uniquely identify an instant without an additional timezone.

## 20. UUID, JSON, and specialized data types

UUIDs can be stored as a native UUID type, CHAR(36), VARCHAR(36), or BINARY(16). The physical type affects storage size, indexing, and how the driver binds/reads values.

JSON can be stored in JSON/JSONB or text columns. The JDBC driver may require a specialized object, PGobject, or converter depending on the DBMS. Do not assume String always binds directly to every native JSON column without casting or type mapping.

Example domain value object:

~~~java
public record ShippingAddress(String street, String city) {}
~~~

A converter can serialize the object to a JSON string, but serialization format, schema versioning, and reading legacy data must be standardized. If JSON is frequently queried by keys, evaluate the database's JSON operators/indexes and avoid sacrificing portability unnecessarily.

For ARRAY, XML, spatial, or vendor-specific types, inspect the JDBC driver and converters. These types typically require custom mapping code.

## 21. Custom converters in Spring Data JDBC

Spring Data JDBC lets you register custom conversions to convert domain types to store types and back. You can use @WritingConverter and @ReadingConverter to distinguish conversion directions.

Example value object Money stored as BigDecimal:

~~~java
public record Money(BigDecimal amount) {}
~~~

Writing converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyWritingConverter implements Converter<Money, BigDecimal> {
    @Override
    public BigDecimal convert(Money source) {
        return source.amount();
    }
}
~~~

Reading converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class MoneyReadingConverter implements Converter<BigDecimal, Money> {
    @Override
    public Money convert(BigDecimal source) {
        return new Money(source);
    }
}
~~~

Registering in JDBC configuration:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new MoneyWritingConverter(),
                new MoneyReadingConverter()
        );
    }
}
~~~

Exact configuration signatures may vary by Spring Data Relational version; cross-check your project dependency API. If the application uses Spring Boot auto-configuration, avoid declaring extra configurations that inadvertently replace or disable default JDBC beans.

Spring Data JDBC custom converters are used within Spring Data-managed mappings. Do not assume JdbcTemplate automatically invokes the same conversion service for every parameter and ResultSet. For custom JDBC code, invoke converters explicitly or use a dedicated RowMapper/parameter mapping.

## 22. Nulls and JDBC types

A nullable column needs a Java type capable of representing null. For example:

- Nullable BIGINT should map to Long rather than long.
- Nullable BOOLEAN should map to Boolean rather than boolean.
- Nullable DECIMAL should map to a nullable BigDecimal.

When using PreparedStatement, binding null sometimes requires specifying the JDBC type so the driver/database knows the expected type:

~~~java
statement.setNull(1, Types.VARCHAR);
~~~

NamedParameterJdbcTemplate also lets you declare the SQL type for a parameter when needed, especially with nulls or specialized types:

~~~java
new MapSqlParameterSource()
        .addValue("status", null, Types.VARCHAR);
~~~

Do not replace null with an empty string, 0, or false if the domain distinguishes those states. SQL NULL has specific semantics and comparison conditions must use IS NULL/IS NOT NULL instead of = NULL.

## 23. Data types in @Query and JdbcTemplate

Derived queries and CRUD repositories use mapping metadata to bind values. With @Query, Spring Data JDBC still handles parameter binding via repository infrastructure and supported mappings, while the SQL/identifiers are written by the developer.

With JdbcTemplate, the application has more direct control over bind types and result mapping. For example:

~~~java
jdbcTemplate.query(
        "SELECT id, total FROM purchase_orders WHERE status = ?",
        (rs, rowNum) -> new PurchaseOrderSummary(
                rs.getLong("id"),
                rs.getBigDecimal("total")
        ),
        "OPEN"
);
~~~

If the ResultSet contains null in a numeric column, getLong returns 0 for SQL NULL as well; you must call wasNull() or use getObject with a wrapper type to distinguish:

~~~java
long value = rs.getLong("optional_count");
Long count = rs.wasNull() ? null : value;
~~~

Or:

~~~java
Long count = rs.getObject("optional_count", Long.class);
~~~

Support for getObject(column, Class) depends on the driver/JDBC version; check the driver when using specialized types.

## 24. Portability of hand-written SQL

When an application supports multiple DBMSs, distinguish two parts:

- **Spring Data-generated SQL**: the dialect can handle many differences modeled by the framework.
- **Application-written SQL**: exact syntax must be guaranteed compatible by the author.

For example, the following statements are not universally portable:

~~~sql
SELECT * FROM customers LIMIT 10 OFFSET 20;
~~~

~~~sql
INSERT INTO customers(name) VALUES ('Lan') RETURNING id;
~~~

~~~sql
SELECT nextval('customer_id_seq');
~~~

They may work on one database but fail on another. If multiple dialects must be supported, you can:

1. Use the repository/Query API so the framework generates SQL.
2. Use standard SQL syntax where supported by target DBMSs.
3. Separate statements per database into dedicated strategies.
4. Use custom repository fragments to encapsulate differences.
5. Write integration tests against every declared supported DBMS.

Do not write a single long SQL statement with multiple DBMS branches if separating strategies is cleaner.

## 25. Schema migrations must align with mappings

A dialect does not fix an existing schema automatically. When switching databases, adapt migrations for:

- Identity/auto-increment or sequence types.
- UUID, boolean, JSON, and temporal types.
- VARCHAR lengths, DECIMAL precision/scale.
- Quoting and casing of table/column names.
- Reserved words.
- Indexes and constraints.
- Default values, generated columns, and triggers.

Example DDL for PostgreSQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    total NUMERIC(18, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

DDL for MySQL may use AUTO_INCREMENT and different types:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    total DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Both schemas have similar intent but are not identical in timezone and generated-identity semantics. Migrations must be designed for the target DBMS rather than merely swapping type names.

## 26. Testing portability across databases

If an application claims multi-database support, testing solely with H2 is insufficient. Test dialect-dependent scenarios:

| Area | Recommended tests |
|---|---|
| Identifiers | Table/column names with reserved words or mixed case if actually used by the app |
| Pagination | First page, middle page, empty page, multi-column sorting |
| Generated keys | Insert new root, retrieve ID, insert aggregate with children |
| Type mapping | Boolean, enum, decimal, temporal, UUID, and null |
| Custom converters | Bidirectional read/write and legacy data |
| Custom SQL | @Query, JdbcTemplate, quoting, and pagination syntax |
| Transactions | Commit/rollback, optimistic locking, and required isolation |
| Migrations | Clean schema creation and schema upgrades from previous versions |

Testcontainers can run containers of target databases for integration tests on real drivers. Choose images/versions close to deployment environments and use the right JDBC driver dependencies. For commercial databases or those without suitable images, use vendor-supported test environments.

## 27. Common pitfalls

| Symptom | Common cause | Resolution |
|---|---|---|
| SQL syntax error near table/column name | Identifier is a reserved word or improperly quoted | Rename or quote according to dialect |
| PostgreSQL cannot find mixed-case table | Identifier was created quoted and is case-sensitive | Use exact quoted spelling or normalize schema |
| Query passes on H2 but fails on SQL Server | @Query uses unsupported LIMIT/OFFSET | Use Pageable/Query or dialect-specific SQL |
| ID after save remains null | Reading input object instead of returned object, or incompatible driver/generated strategy | Use returned object and verify generated-key support |
| ID retrieved via MAX(id) is wrong | Concurrent insert transactions | Use generated keys/RETURNING/sequences appropriately |
| UUID binding fails | Database/driver uses a specialized UUID type | Use a converter or appropriate JDBC type |
| Enum cannot be read back | Value stored in DB does not match converter | Standardize stored codes and bidirectional converters |
| Boolean wrong on another DB | BOOLEAN/BIT/NUMBER mapping differs | Use a converter or consistent physical type |
| Timestamp shifted by hours | LocalDateTime/Instant/timezone semantics confused | Establish clear temporal type and UTC policy |
| BigDecimal loses precision | Converted via double or insufficient schema precision/scale | Use BigDecimal and align DECIMAL definitions |
| Nullable column becomes 0/false | Primitive used or ResultSet getter did not check wasNull | Use wrappers and handle SQL NULL |
| JdbcTemplate ignores custom converter | Spring Data converters do not auto-apply to JdbcTemplate | Bind/map manually or share a mapper |
| Custom INSERT does not return ID | Using update count instead of generated keys | Use KeyHolder or appropriate result-set API |

## 28. Workflow when switching databases or drivers

When migrating an application to another DBMS or upgrading the JDBC driver, follow this order:

1. Identify the target DBMS, version, and JDBC driver version.
2. Check dialect support in the Spring Data Relational version.
3. Cross-check identifiers, reserved words, quoting, and case normalization.
4. Check LIMIT/OFFSET and ORDER BY syntax.
5. Check identity/sequence and generated-key retrieval.
6. Compare SQL types with Java types, nullability, and converters.
7. Adapt migrations/schemas, indexes, and constraints.
8. Run integration tests with the target driver/database.
9. Inspect generated SQL and bound parameters in development.
10. Measure execution plans and query/pagination performance on representative data.

## 29. Hands-on lab: observing the four differences

Use an orders table:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    total DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Complete the exercises:

1. Save a PurchaseOrder with a null id using repository.save and read the ID from the returned object.
2. Create a repository query taking Pageable and inspect the generated pagination SQL on your current database.
3. Add Sort by createdAt and id to ensure stable ordering.
4. Write a @Query using a collision-prone identifier, then rename or quote it according to the DBMS.
5. Use JdbcTemplate and GeneratedKeyHolder to insert a customer and retrieve the ID.
6. Inspect DatabaseMetaData.supportsGetGeneratedKeys and identifierQuoteString.
7. Add BigDecimal, Instant, and UUID properties; run read/write tests on the target driver.
8. Test null values with wrapper types and check ResultSet results.
9. Try a custom converter for an enum or value object.
10. Run integration tests on H2 and a production-like database, recording the observed differences.

The goal is to distinguish what the framework/dialect already handles from the SQL, schemas, and converters the application must manage itself.

## 30. Key principles to remember

- Dialect describes SQL/JDBC differences so Spring Data JDBC generates statements suited to the database.
- Identifiers are table/column names; values are bound data. Never use bind parameters to substitute identifiers.
- Quoting and case normalization differ across DBMSs; avoid reserved words and mixed-case identifiers unless necessary.
- SQL in @Query/JdbcTemplate is not automatically rewritten into portable syntax by the dialect.
- LIMIT/OFFSET syntax varies; use Pageable/Query so the framework generates appropriate pagination clauses when possible.
- Pagination requires a stable ORDER BY, typically adding ID as a tie-breaker.
- A generated key is a database-generated ID, distinct from the update count; use the object returned by repository.save.
- JdbcTemplate can use KeyHolder/GeneratedKeyHolder or database-specific RETURNING/OUTPUT mechanisms.
- Never retrieve IDs using MAX(id) after INSERT because it is unsafe under concurrent inserts.
- JDBC types and Java types do not always map one-to-one; pay attention to UUID, JSON, enum, boolean, and temporal types.
- Use BigDecimal for DECIMAL/NUMERIC and wrapper types for nullable columns.
- Spring Data JDBC custom converters do not automatically apply to all JdbcTemplate operations.
- Migrations, schemas, drivers, and integration tests must all reflect the supported DBMSs.

Dialect helps Spring Data JDBC handle many common differences across databases, but does not erase SQL and JDBC driver differences. Let the framework manage the generated SQL it supports; for hand-written SQL, identifiers, pagination, generated keys, and type conversions must be designed for the target database. Testing against the exact driver and DBMS prevents bugs that only appear after deployment or when switching environments.

## References

- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html)
- [Spring Data Relational — API](https://docs.spring.io/spring-data/relational/docs/current/api/)
- [Spring Data JDBC — JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html)
- [JDBC DatabaseMetaData API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DatabaseMetaData.html)
- [JDBC Connection API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html)
- [Spring JDBC Reference](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
