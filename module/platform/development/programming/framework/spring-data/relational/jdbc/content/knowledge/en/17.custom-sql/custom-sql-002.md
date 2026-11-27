# Named Parameter Binding with @Param and Parameter Name Information

When writing custom SQL for Spring Data JDBC, queries often need to receive values from repository method parameters. Instead of concatenating SQL strings with input data, we use **named parameters** such as `:email` or `:status` and bind those names to Java parameters using the **`@Param`** annotation.

This approach makes SQL queries easier to read, avoids parameter-order mistakes, and allows JDBC to bind values safely. Spring Data can also discover parameter names from bytecode metadata if the project is compiled with parameter name information. However, when a query is an important part of the persistence contract, declaring `@Param` explicitly usually makes code clearer and less dependent on build configuration.

This lesson focuses on how to declare `@Query` and `@Param` in Spring Data JDBC, how parameter names are discovered, placeholder naming rules, how to diagnose binding errors, and limitations to keep in mind when using named parameters.

## 1. Named parameters in custom SQL

Suppose a repository needs to find a customer by email. The SQL can be written as:

```sql
SELECT id, name, email
FROM customers
WHERE email = :email
```

`:email` is a **named parameter**. This name is mapped to a Java value when Spring Data JDBC executes the query.

Repository method:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> findByEmail(@Param("email") String email);
```

Here:

- `:email` in SQL is the placeholder name.
- `@Param("email")` specifies which Java parameter supplies the value for the placeholder.
- `String email` is the actual value bound when the method is called.
- `Optional<Customer>` represents a result where no matching row may be found.

The name inside `@Param` must match the placeholder name in SQL. The Java variable name can differ if the annotation explicitly specifies the binding name.

## 2. Required annotations and packages

With Spring Data JDBC, import `@Query` from the JDBC package:

```java
import org.springframework.data.jdbc.repository.query.Query;
```

`@Param` is provided by Spring Data Commons:

```java
import org.springframework.data.repository.query.Param;
```

Full repository example:

```java
// Customer.java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
    @Id Long id,
    String name,
    String email,
    boolean active
) {}
```

```java
// CustomerRepository.java
import java.util.Optional;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.ListCrudRepository;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, email, active
        FROM customers
        WHERE email = :email
        """)
    Optional<Customer> findByEmail(
        @Param("email") String email
    );
}
```

`@Query` tells the framework that the method uses developer-declared SQL. `@Param` binds the method parameter to the named placeholder in that SQL statement.

Do not confuse `@Param` with Spring MVC's `@PathVariable` or controller `@RequestParam`. Those web annotations bind HTTP data into controller methods; `@Param` here binds repository parameters into a SQL query.

## 3. Why use names instead of positional parameters?

For a query with multiple values, named parameters clarify the meaning of each value:

```sql
SELECT id, name, email
FROM customers
WHERE status = :status
  AND city = :city
  AND created_at >= :createdAfter
```

Corresponding method:

```java
List<Customer> search(
    @Param("status") CustomerStatus status,
    @Param("city") String city,
    @Param("createdAfter") Instant createdAfter
);
```

A reader can immediately see:

- `:status` receives the status value.
- `:city` receives the city.
- `:createdAfter` receives the timestamp threshold.

With a positional parameter list, you have to remember which condition corresponds to the first parameter, the second parameter, and so on. When SQL is edited or conditions are added, names reduce the risk of swapping values by mistake.

Named parameters are also convenient when a single value appears multiple times in a query. The same placeholder name can be used in several places and receive the same bound value.

## 4. How does @Param bind names?

`@Param` takes a string representing the name used in the query:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> lookup(
    @Param("email") String address
);
```

In this example:

| Element | Value |
| --- | --- |
| SQL placeholder name | `:email` |
| Annotation value | `"email"` |
| Java variable name | `address` |
| Bound value | Contents of the `address` variable |

The Java variable name does not have to match the placeholder name when `@Param` provides an explicit mapping. This is an important benefit: the query can keep clear domain names even when the method parameter uses a different name.

If you change the SQL to `WHERE email = :customerEmail` while keeping `@Param("email")`, the mapping no longer matches. Update both sides together.

### 4.1. A method with multiple named parameters

Example:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE status = :status
      AND city = :city
      AND email <> :excludedEmail
    """)
List<Customer> search(
    @Param("status") CustomerStatus status,
    @Param("city") String city,
    @Param("excludedEmail") String excludedEmail
);
```

Each placeholder has a corresponding parameter. Placeholder names do not depend on the declaration order of the Java parameters.

### 4.2. Reusing a single parameter multiple times

Example query that searches the same keyword in either name or email:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE name LIKE :pattern
       OR email LIKE :pattern
    """)
List<Customer> searchByPattern(
    @Param("pattern") String pattern
);
```

When called:

```java
repository.searchByPattern("%an%");
```

The same `pattern` value is bound to both positions. Reusing the placeholder avoids declaring two Java parameters with identical content just because the SQL uses the value in two conditions.

## 5. Parameter name information in bytecode

Spring Data can discover method parameter names from Java reflection metadata. However, variable names written in source code are not always preserved in bytecode.

For the Java compiler, the `-parameters` option requests storing parameter name information so reflection can read it via `Parameter.getName()`.

Example:

```java
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

This is a Gradle Groovy configuration. If the project already enables this option in a convention plugin or shared configuration, there is no need to add it again.

With Maven Compiler Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Without parameter name metadata, reflection may return generic names such as `arg0`, `arg1` instead of source names like `email`. In that case Spring Data cannot rely on source names to bind placeholders as intended.

### 5.1. Does @Param work without -parameters enabled?

`@Param` provides an explicit binding name directly on the parameter, so the code does not need to rely on discovering variable names from bytecode for that parameter.

Example:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> findByEmail(
    @Param("email") String email
);
```

This declaration makes the contract clear directly in source code. Even so, the `-parameters` configuration remains useful for other APIs/frameworks that need parameter name discovery and for methods that omit `@Param`.

### 5.2. Using Java parameter names without @Param

In Spring Data versions supporting parameter name discovery, you can write:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> findByEmail(String email);
```

The framework needs to discover the Java parameter name `email` from metadata. If bytecode does not retain the name, binding may fail or fail to find the matching name.

Therefore, when a method has SQL named parameters, there are two options:

| Approach | Requirement | Characteristics |
| --- | --- | --- |
| Declare `@Param("email")` | Annotation name matches placeholder | Explicit, readable, less dependent on compiler metadata. |
| Use parameter name directly | Spring Data can discover names from bytecode, usually needing `-parameters` | Fewer annotations, but depends on build configuration. |

For repository methods with multiple parameters or important SQL, explicit `@Param` is usually the more maintainable choice.

## 6. Safe binding and preventing SQL injection

An important benefit of named parameters is that values are passed separately to JDBC for binding into the SQL statement. User input data should never be concatenated directly into SQL strings.

**Unsafe:**

```java
String sql = "SELECT id, name FROM customers "
    + "WHERE email = '" + email + "'";

return jdbcTemplate.queryForList(sql);
```

If `email` comes from a request and contains malicious SQL content, the query structure can be altered.

**Using parameter binding:**

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :email
    """)
Optional<Customer> findByEmail(
    @Param("email") String email
);
```

Spring Data JDBC forwards parameter values to the JDBC binding mechanism rather than treating them as part of the SQL syntax. This prevents SQL injection through properly bound **values**.

Note: parameter binding protects values, but cannot be used to substitute table names, column names, SQL keywords, or arbitrary ORDER BY clauses. If users can choose a sort column, map the input against an allowlist of permitted identifiers instead of binding the column name as a value.

### 6.1. Parameter names are not SQL content

Example:

```java
@Param("email") String email
```

`email` is the binding name. The actual value might be `an@example.test`. The framework does not substitute the raw string into SQL like string concatenation; it binds the value via JDBC.

When logging SQL, be careful because some logging configurations record parameter values as well and can expose personal data. Only enable verbose logging in appropriate environments and use test data.

## 7. Example: searching with LIKE

A common case is string searching. You can prepare the pattern in Java and bind it:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE name LIKE :pattern
    """)
List<Customer> findByNamePattern(
    @Param("pattern") String pattern
);
```

Service:

```java
public List<Customer> searchByName(String keyword) {
    String pattern = "%" + keyword + "%";
    return customers.findByNamePattern(pattern);
}
```

Here the `%` wildcard characters are added to the Java value and then bound like a normal value. This keeps the SQL clean and avoids concatenating the keyword into the query string.

If case-insensitive search is required, syntax depends on the database. For example, PostgreSQL has `ILIKE`; other databases may use collations or case-conversion functions. Choose syntax according to your project's dialect.

If the keyword itself can contain literal `%` or `_` wildcard characters and business requirements need a literal search, escape those characters according to database rules and declare an appropriate `ESCAPE` clause. Parameter binding does not automatically disable `LIKE` wildcard semantics.

## 8. Binding null values

A named parameter can accept a null value if the Java type and mapping allow it. However, the SQL comparison:

```sql
WHERE email = :email
```

when `:email` is NULL does not mean "find rows where email is NULL". In SQL, comparing `= NULL` evaluates to UNKNOWN, not TRUE.

To find rows with a NULL column, use:

```sql
WHERE email IS NULL
```

If a query has an optional condition, it can be designed explicitly:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE (:status IS NULL OR status = :status)
    """)
List<Customer> findByOptionalStatus(
    @Param("status") String status
);
```

This example illustrates the SQL idea; null binding support and SQL type inference depend on the driver/database. Some databases require an explicit cast for a null parameter because they cannot infer the data type. For complex queries, consider splitting into two queries or using a custom repository to avoid optional expressions that are hard to optimize.

Do not treat `@Param` as a mechanism that automatically turns null comparisons into IS NULL.

## 9. Named parameters with different data types

Named parameters are not limited to String. You can bind Java types compatible with JDBC mapping:

```java
@Query("""
    SELECT id, name, created_at
    FROM customers
    WHERE created_at >= :from
      AND created_at < :to
    """)
List<CustomerSummary> findCreatedBetween(
    @Param("from") Instant from,
    @Param("to") Instant to
);
```

Common types:

| Java type | Typical SQL data type |
| --- | --- |
| `String` | VARCHAR/TEXT |
| `Long`, `Integer` | BIGINT/INTEGER |
| `BigDecimal` | DECIMAL/NUMERIC |
| `Boolean` | BOOLEAN or database equivalent |
| `LocalDate` | DATE |
| `LocalDateTime` | TIMESTAMP |
| `Instant` | Timestamp/instant depending on driver and mapping |
| `UUID` | UUID or corresponding storage type per database |

Exact mapping depends on the database, JDBC driver, and application conversion configuration. When using temporal types or UUID in legacy schemas, check the actual column type and configured conversions.

## 10. Parameter names must match placeholders

Several common errors occur when renaming methods or editing queries.

### 10.1. Placeholder and @Param mismatch

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :customerEmail
    """)
Optional<Customer> findByEmail(
    @Param("email") String email
);
```

The query expects `customerEmail`, but the method only provides `email`. The framework cannot find a bound value for that placeholder.

Fix one of the two sides:

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE email = :customerEmail
    """)
Optional<Customer> findByEmail(
    @Param("customerEmail") String email
);
```

Or change the placeholder to `:email` to match the existing annotation.

### 10.2. Forgetting @Param on a parameter

```java
@Query("""
    SELECT id, name, email, active
    FROM customers
    WHERE status = :status
      AND city = :city
    """)
List<Customer> search(
    @Param("status") CustomerStatus status,
    String city
);
```

The `city` parameter relies on parameter name discovery from bytecode. If the build lacks `-parameters` or metadata is unavailable, binding can fail.

For consistency:

```java
List<Customer> search(
    @Param("status") CustomerStatus status,
    @Param("city") String city
);
```

### 10.3. Using property names instead of physical column names

If the domain has property `contactEmail` while the database column is `contact_email`, handwritten SQL must use the physical column name:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

// Illustrative mapping for a different schema from Customer above.
@Table("customers")
public record Customer(
    @Id Long id,
    @Column("contact_email") String contactEmail,
    @Column("display_label") String displayName
) {}
```

```java
// CustomerRepository.java
import java.util.Optional;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.ListCrudRepository;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {

@Query("""
    SELECT id, contact_email, display_label
    FROM customers
    WHERE contact_email = :email
    """)
Optional<Customer> findByContactEmail(
    @Param("email") String email
);
}
```

`@Param` binds a Java parameter to a placeholder; it does not translate property names into column names. With explicit SQL in `@Query`, the developer is responsible for writing accurate table and column names according to the schema and dialect.

## 11. Named parameters vs. derived query methods

Not every repository method needs `@Query` and `@Param`.

If the query is simple and follows property-naming rules, query derivation can be used:

```java
Optional<Customer> findByEmail(String email);

List<Customer> findByStatusAndCity(
    CustomerStatus status,
    String city
);
```

Spring Data parses the method name and generates a query based on domain properties. Parameters are bound by method order/metadata according to query derivation rules; no SQL placeholders are needed.

Use `@Query` and `@Param` when you need:

- Database-specific SQL.
- Explicit JOINs or SQL expressions.
- Aggregate queries.
- SELECT structures or conditions that are awkward to express via method names.
- Exact control over the query sent to the database.

| Need | Approach |
| --- | --- |
| Find by a simple property | `findByEmail(String email)` |
| Combine a few properties using supported rules | Query derivation |
| SQL JOIN or aggregate/report query | `@Query` with named parameters |
| Complex SQL requiring custom mapping | Custom repository and Spring JDBC operations |

## 12. Named parameters with a custom repository

When a query is complex or needs control over result mapping, you can use `NamedParameterJdbcOperations` directly.

Example:

```java
@Repository
public class CustomerSearchRepository {

    private final NamedParameterJdbcOperations jdbc;

    public CustomerSearchRepository(
        NamedParameterJdbcOperations jdbc
    ) {
        this.jdbc = jdbc;
    }

    public List<CustomerSummary> search(String city, String keyword) {
        String sql = """
            SELECT id, name, email
            FROM customers
            WHERE city = :city
              AND name LIKE :pattern
            ORDER BY name
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("city", city)
            .addValue("pattern", "%" + keyword + "%");

        return jdbc.query(sql, params, (rs, rowNum) ->
            new CustomerSummary(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getString("email")
            )
        );
    }
}
```

The result DTO can be declared separately:

```java
public record CustomerSummary(Long id, String name, String email) {}
```

Named parameters are still used here, while binding and row mapping are handled by custom code. This approach fits complex read-model queries while the CRUD repository continues to manage aggregates.

Spring Data repository `@Param` and Spring JDBC `MapSqlParameterSource` serve the same idea of naming SQL values, but belong to two different APIs.

## 13. Testing repository queries with @Param

A repository test should verify that the query returns the right results for parameter values without relying on implicit ordering.

Example:

```java
@DataJdbcTest
class CustomerRepositoryQueryTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void findsCustomerByEmailUsingNamedParameter() {
        customers.save(new Customer(
            null,
            "Lan",
            "lan@example.test",
            true
        ));

        Optional<Customer> found =
            customers.findByEmail("lan@example.test");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().email())
            .isEqualTo("lan@example.test");
    }
}
```

Tests need an appropriate test datasource, schema, and entity mapping. For custom SQL with PostgreSQL/MySQL/SQL Server-specific syntax, run tests against the corresponding database or Testcontainers instead of relying solely on H2.

### 13.1. Testing values containing quotes

You can test with input like:

```java
String email = "o'connor@example.test";
repository.findByEmail(email);
```

If parameter binding works properly, the quote is treated as value data and does not alter SQL syntax. This is a useful check to catch code that improperly concatenates SQL strings.

### 13.2. Verifying build metadata

If a project omits `@Param` on some methods and relies on parameter names, tests should run against artifacts compiled with the proper configuration. An IDE run can differ from a CI build if compiler arguments are inconsistent.

Enabling `-parameters` in the shared build configuration helps reduce differences between local and CI builds.

## 14. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Value not found for named parameter | Placeholder and `@Param` have different names. | Match the name after `:` with the annotation value. |
| Parameter name resolved as `arg0` | Bytecode does not preserve parameter name metadata. | Use explicit `@Param` or enable `-parameters`. |
| Query runs but returns empty results | Wrong bound value, wrong column/property name, or non-matching data. | Check SQL, input values, and actual schema. |
| Value containing quotes causes query error | SQL uses string concatenation instead of parameter binding, or syntax error in query. | Use named parameter binding. |
| Using parameter to substitute table/column name | Bind parameters are only for values, not SQL identifiers. | Choose identifiers from an allowlist and construct queries safely. |
| Passing null expecting to match NULL columns | `= NULL` comparison does not follow SQL NULL semantics. | Use `IS NULL` or an explicit optional condition. |
| LIKE fails to match wildcard characters literally | `%` and `_` have wildcard semantics. | Escape wildcards per dialect and use `ESCAPE`. |
| H2 test passes, production database fails | Different SQL syntax, parameter types, or dialect. | Run integration tests on the real database. |

## 15. Declaration and maintenance workflow

When writing a repository method with custom SQL:

1. Write SQL with named placeholders such as `:email`, `:status`.
2. Declare method parameters with `@Param("...")` using the matching names.
3. Choose Java types compatible with column types and the JDBC driver.
4. Never concatenate user data into SQL strings.
5. Use exact physical table/column names in SQL; `@Param` does not substitute identifier mapping.
6. If omitting `@Param`, ensure the compiler retains parameter names via `-parameters` and Spring Data can discover the metadata.
7. Check null, wildcard, collection, and database-specific limitations for the use case.
8. Write repository tests against an appropriate database/dialect.
9. When renaming a placeholder, update the corresponding annotation in the same change.
10. Use a custom repository with `NamedParameterJdbcOperations` when the query needs finer control than `@Query`.

> **Named parameters make SQL statements clearly express the meaning of each value. `@Param("name")` binds a Java parameter to placeholder `:name`; parameter name information in bytecode can allow Spring Data to discover names without the annotation, but explicit declarations keep the repository contract stable and readable.**

### References

- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): declaring custom queries in JDBC repositories.
- [Spring Data Commons — Repository Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): query methods and parameter binding.
- [Spring Data Commons — @Param API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/Param.html): annotation for naming query parameters.
- [Java Compiler — -parameters option](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): storing method/constructor parameter names in class files.
- [Spring Framework — NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): named parameters when using Spring JDBC directly.
