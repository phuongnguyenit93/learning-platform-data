# Declaring @Query With nativeQuery and Version Availability of @NativeQuery

## Objectives

After this lesson, you will be able to write native SQL queries in Spring Data JPA using `@Query(nativeQuery = true)`; recognize `@NativeQuery` introduced in Spring Data JPA 3.4; choose how to map results to an entity, interface projection, or DTO; handle parameters, pagination, count queries, and update/delete statements; and understand limitations around portability, dynamic sorting, and version compatibility.

Examples use Java 17+, Spring Boot 3+, and Jakarta Persistence. Table and column names in SQL must match the actual schema. Repository snippets assume the application already has `spring-boot-starter-data-jpa`, the corresponding entities, and a working `DataSource`.

## 1. How Does Native SQL Differ From JPQL?

Spring Data JPA lets you write queries in two main ways:

- **JPQL** queries entities and Java properties. The provider translates JPQL into SQL appropriate for the database.
- **Native SQL** is SQL written for the database management system. You write table names, column names, functions, joins, and syntax supported directly by the database.

Example with the same goal of finding customers by status:

JPQL:

```java
@Query("select c from Customer c where c.status = :status")
List<Customer> findByStatus(@Param("status") String status);
```

Native SQL:

```java
@Query(
    value = "select c.* from customers c where c.status = :status",
    nativeQuery = true
)
List<Customer> findByStatusNative(@Param("status") String status);
```

JPQL uses `Customer` and `status` as entity/property names. Native SQL uses `customers` and `status` as table/column names in the database. If the entity maps `status` to column `customer_status`, the native SQL query must use `customer_status`.

Native queries are useful when you need:

- CTEs (`WITH`), window functions, JSON operators, full-text search, or database-specific features.
- Tuning for a complex query already analyzed via an execution plan.
- SQL structures that are hard to express or guarantee performance for in JPQL.
- Calling specialized SQL statements, views, or stored procedures in ways supported by repositories.

Native SQL increases coupling to the schema and dialect. If JPQL or derived queries satisfy the requirement well, they are usually easier to maintain and migrate across databases.

## 2. Using @Query(nativeQuery = true)

`@Query` is a Spring Data JPA annotation. Setting `nativeQuery = true` tells Spring Data that the query string is native SQL rather than JPQL.

Repository example:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Query(
        value = """
            SELECT c.*
            FROM customers c
            WHERE c.status = :status
            ORDER BY c.created_at DESC, c.id DESC
            """,
        nativeQuery = true
    )
    List<Customer> findNativeByStatus(@Param("status") String status);
}
```

In this example:

- `value` holds the actual SQL sent to the database.
- `nativeQuery = true` enables native query mode.
- `:status` is a named parameter; `@Param("status")` binds the Java parameter to that name.
- `customers`, `status`, `created_at`, and `id` must match the physical schema.
- `ORDER BY` is written explicitly in SQL so results have a deterministic order.

Because the method returns `Customer`, the SQL query must select enough columns for the provider to construct the entity. `SELECT c.*` works well for this simple table example. Do not select an arbitrary subset of columns and ask JPA to build a full entity; use a projection or DTO when you only need partial data.

### 2.1. Named Parameters and Positional Parameters

Named parameters are generally easier to read and less error-prone regarding argument order:

```java
@Query(
    value = "SELECT c.* FROM customers c WHERE c.status = :status AND c.active = :active",
    nativeQuery = true
)
List<Customer> search(
    @Param("status") String status,
    @Param("active") boolean active
);
```

You can also use positional parameters matching parameter order:

```java
@Query(
    value = "SELECT c.* FROM customers c WHERE c.status = ?1 AND c.active = ?2",
    nativeQuery = true
)
List<Customer> search(String status, boolean active);
```

In Spring Data JPA, positional parameters in `@Query` strings use indices `?1`, `?2`, ... corresponding to the method parameter order. When using named parameters, declare `@Param` explicitly so the binding name is clear and does not depend on compiler settings retaining parameter names.

### 2.2. Bind Values, Do Not Concatenate SQL Strings

Never build SQL statements by directly concatenating request data:

```java
// Unsafe: do not concatenate user input into SQL.
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";
```

Use parameter binding instead:

```java
@Query(value = "SELECT c.* FROM customers c WHERE c.email = :email", nativeQuery = true)
Optional<Customer> findByEmailNative(@Param("email") String email);
```

Parameter binding separates data from statement structure, reducing SQL injection risk and ensuring proper data type handling. Parameters represent **values** only; they cannot substitute table names, column names, `ASC`/`DESC` keywords, or arbitrary SQL fragments.

If you need to choose a sort column from a request, map the input through an allowlist in code and select the corresponding query or SQL branch. Never concatenate user-submitted column names or sort directions directly into SQL.

## 3. What Is @NativeQuery and Since Which Version Is It Available?

`@NativeQuery` is a dedicated Spring Data JPA annotation introduced in **Spring Data JPA 3.4.0**. It is a specialized annotation for native SQL built on top of `@Query(nativeQuery = true)` and adds attributes such as `sqlResultSetMapping` to specify a Jakarta Persistence result set mapping.

Import:

```java
import org.springframework.data.jpa.repository.NativeQuery;
```

Example:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.NativeQuery;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @NativeQuery("""
        SELECT c.*
        FROM customers c
        WHERE c.status = :status
        ORDER BY c.created_at DESC, c.id DESC
        """)
    List<Customer> findByStatusUsingNativeQuery(
        @Param("status") String status
    );
}
```

For basic native SQL needs, `@NativeQuery` and `@Query(nativeQuery = true)` serve the same purpose. You do not need to rewrite all older repositories to the new annotation; you can continue using `@Query` if you want compatibility with Spring Data JPA versions prior to 3.4.

### 3.1. Version Availability

| Spring Data JPA Version | How to Declare Native SQL |
| --- | --- |
| Before 3.4.0 | Use `@Query(value = "...", nativeQuery = true)` |
| 3.4.0 and later | Use `@Query(nativeQuery = true)` or `@NativeQuery` |

Spring Boot 3.4 and later typically manage a Spring Data JPA version that includes `@NativeQuery` via dependency management. However, the actual resolved version may differ if the project overrides dependencies or BOMs. Always check the resolved artifact rather than looking only at the Spring Boot version number.

If your IDE reports that `NativeQuery` cannot be found, the cause is usually that Spring Data JPA is on a version earlier than 3.4 or the dependency classpath has not been refreshed. You can use `@Query(nativeQuery = true)` right away, or upgrade Spring Data using a compatible Spring Boot dependency set. Avoid upgrading `spring-data-jpa` individually without checking compatibility with other Spring Data modules.

### 3.2. Checking the Resolved Version

With Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-jpa
```

With Gradle:

```bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
```

On Windows PowerShell you can run `./mvnw.cmd` or `./gradlew.bat`. Inspect the resolved `spring-data-jpa` version in the dependency tree/insight output. If the project uses the Spring Boot BOM, prefer upgrading Boot to an appropriate version to receive a consistent set of Spring Data dependencies.

## 4. Mapping Native Query Results

Native SQL can return entities, projections, DTOs, or scalar data. The repository return type must match the selected columns and mapping strategy.

### 4.1. Returning an Entity

```java
@NativeQuery("SELECT c.* FROM customers c WHERE c.id = :id")
Optional<Customer> findEntityByIdNative(@Param("id") Long id);
```

Use this when the result represents an entity managed by the persistence context. The SQL query must return all columns required by the entity mapping, including the primary key and relevant persistent columns. If the entity has associations or inheritance mapping, check the requirements of that specific mapping.

### 4.2. Interface Projections

If you only need a few columns, use a projection to avoid loading the entire entity:

```java
package com.example.learning.customer;

public interface CustomerEmailView {
    Long getId();
    String getEmail();
}
```

Repository:

```java
@NativeQuery("""
    SELECT c.id AS id, c.email AS email
    FROM customers c
    WHERE c.status = :status
    """)
List<CustomerEmailView> findEmailViewsByStatus(
    @Param("status") String status
);
```

SQL aliases should match the property names expected by the projection—here, `id` and `email`. Case sensitivity rules and how the database returns column labels can vary; if an alias uses camelCase or special characters, check how the database handles identifiers and quote them according to the dialect when necessary.

Projections are suited for read-only lists, summary views, and APIs that only need partial data. They are not managed entities; do not treat a projection as an object for updating persistence state.

### 4.3. DTOs With @SqlResultSetMapping

For DTO classes requiring explicit constructor mapping, Jakarta Persistence provides `@SqlResultSetMapping` and `@ConstructorResult`. DTO example:

```java
package com.example.learning.customer;

public class CustomerSummaryDto {
    private final Long id;
    private final String email;

    public CustomerSummaryDto(Long id, String email) {
        this.id = id;
        this.email = email;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
}
```

Declare the mapping on an entity in the persistence unit:

```java
package com.example.learning.customer;

import jakarta.persistence.ColumnResult;
import jakarta.persistence.ConstructorResult;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.SqlResultSetMapping;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SqlResultSetMapping(
    name = "CustomerSummaryMapping",
    classes = @ConstructorResult(
        targetClass = CustomerSummaryDto.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "email", type = String.class)
        }
    )
)
public class Customer {
    @Id
    private Long id;

    private String email;

    protected Customer() {
    }
}
```

Repository using `sqlResultSetMapping` on `@NativeQuery`:

```java
@NativeQuery(
    value = """
        SELECT c.id AS customer_id, c.email AS email
        FROM customers c
        WHERE c.status = :status
        """,
    sqlResultSetMapping = "CustomerSummaryMapping"
)
List<CustomerSummaryDto> findSummaries(
    @Param("status") String status
);
```

The names `customer_id` and `email` in `@ColumnResult` must match the column labels returned by SQL. The order and types of `ColumnResult` entries must be compatible with the DTO constructor. `sqlResultSetMapping` is an added convenience on `@NativeQuery` starting in Spring Data JPA 3.4; on older versions, you can apply the mapping using `EntityManager.createNativeQuery(sql, mappingName)` in a custom repository.

These files are shown together in the same package for illustration; in a real application, declare only one `Customer` entity and add the mapping to the existing entity rather than creating duplicate classes with the same name.

## 5. Paginating Native Queries With countQuery

When a repository returns `Page<T>`, Spring Data needs the total number of matching rows to build page metadata. For native SQL, declare `countQuery` explicitly for complex queries or whenever you do not want to rely on automatic SQL parsing.

Example:

```java
@Query(
    value = """
        SELECT c.*
        FROM customers c
        WHERE c.status = :status
        ORDER BY c.created_at DESC, c.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM customers c
        WHERE c.status = :status
        """,
    nativeQuery = true
)
Page<Customer> findPageByStatus(
    @Param("status") String status,
    Pageable pageable
);
```

With Spring Data JPA 3.4+, you can write the equivalent using `@NativeQuery`:

```java
@NativeQuery(
    value = """
        SELECT c.*
        FROM customers c
        WHERE c.status = :status
        ORDER BY c.created_at DESC, c.id DESC
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM customers c
        WHERE c.status = :status
        """
)
Page<Customer> findPageByStatusNative(
    @Param("status") String status,
    Pageable pageable
);
```

`countQuery` must apply the exact same filter conditions as the main query. If the main query joins a one-to-many table and can produce multiple rows per customer, `COUNT(*)` will overcount duplicates; in that case, count the proper result unit, such as `COUNT(DISTINCT c.id)`, and test with data that has multiple relationships.

Simple native SQL can sometimes be parsed by Spring Data to generate a count query, but queries with CTEs, subqueries, unions, `GROUP BY`, or vendor-specific syntax can exceed rewriting capabilities. Declaring `countQuery` explicitly is usually easier to control. Spring Data JPA can also use JSqlParser if that library is on the classpath, but a parser does not eliminate the need to verify the SQL and count results.

### 5.1. Page, Slice, and List

- `Page<T>` provides total elements and total pages; it usually requires an extra count query.
- `Slice<T>` indicates whether a next page exists; it can avoid the total-record count query.
- `List<T>` carries no pagination metadata; it works well when the result size is bounded or the use case does not need pagination.

Choose `Page` when the UI genuinely needs the total page count. For large tables, count queries can be expensive; `Slice` may be a better fit.

### 5.2. Dynamic Sorting With Native Queries

Do not assume that `Pageable` or `Sort` can inject arbitrary `ORDER BY` clauses into every native SQL query. Rewriting SQL depends on the dialect and query complexity; CTEs, unions, subqueries, or aliases can make automatic sorting unsafe or unsupported.

With native queries, the most predictable approach is writing a fixed `ORDER BY` in SQL. If dynamic sorting is needed, use a whitelisted set of column/direction options in code or build a custom repository with dedicated logic. Never concatenate raw sort strings from requests.

## 6. Native Queries That Update or Delete Data

Native queries are not only for reading. You can combine `@Modifying` with `@Query(nativeQuery = true)` or `@NativeQuery` for `UPDATE`/`DELETE`.

Repository example:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query(
    value = """
        UPDATE customers
        SET active = :active
        WHERE last_login_at < :cutoff
        """,
    nativeQuery = true
)
int updateActiveBefore(
    @Param("active") boolean active,
    @Param("cutoff") Instant cutoff
);
```

Service calling inside a transaction:

```java
package com.example.learning.customer;

import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerMaintenanceService {
    private final CustomerRepository customers;

    public CustomerMaintenanceService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public int deactivateBefore(Instant cutoff) {
        return customers.updateActiveBefore(false, cutoff);
    }
}
```

`@Modifying` informs Spring Data that the query method performs a write operation. The method must execute inside a transaction; `@Transactional` can be placed on the service as shown or on the repository method depending on application design. The `int` return value is the number of rows updated by the database.

Bulk updates/deletes execute directly against the database and bypass per-entity dirty checking. Entities already in the persistence context may retain stale data. `flushAutomatically = true` flushes pending changes before running the query; `clearAutomatically = true` clears the persistence context afterward to prevent continued use of stale entities.

`clearAutomatically` affects all managed entities currently in the persistence context, not just the updated customers. If you do not want to clear everything, consider refreshing the relevant entities or managing persistence context boundaries explicitly.

With `@NativeQuery` on Spring Data JPA 3.4+, you can combine `@Modifying` under the same rules because it is Spring Data's dedicated native query annotation. Regardless of which annotation you use, a transaction is still required and you must account for persistence context state after bulk operations.

## 7. Native Queries With IN, NULL, and Data Types

Native SQL follows database rules. Example:

```sql
SELECT c.*
FROM customers c
WHERE c.status IN ('NEW', 'ACTIVE');
```

For collection parameters, how a list is bound in a native query can depend on the JPA provider, database, and how the provider expands bind parameters. If you need to pass multiple values, test against the actual production database. For simple queries, derived queries or JPQL `IN :statuses` are usually more portable.

SQL still uses three-valued logic: `column = NULL` will not match null rows; you must use `IS NULL`. `NOT IN` with a set containing a `NULL` element can evaluate to `UNKNOWN` and unexpectedly exclude rows. Filter out null elements in the service or write a separate `IS NULL` condition if the business logic requires it.

Java types passed in must be compatible with SQL types. For instance, `Instant` may map to timestamp depending on provider/database; enums must be consistent regarding string vs. ordinal storage; UUID, JSON, arrays, and vendor-specific types may need custom mappings. When using native SQL, do not assume one database's function names or casting rules will run on another database.

## 8. Stored Procedures, CTEs, and Database-Specific Features

Native SQL fits well when you need database syntax that JPQL cannot express. For example, PostgreSQL can use CTEs and window functions:

```sql
WITH ranked_customers AS (
    SELECT
        c.id,
        c.email,
        c.status,
        ROW_NUMBER() OVER (
            PARTITION BY c.status
            ORDER BY c.created_at DESC, c.id DESC
        ) AS row_number
    FROM customers c
)
SELECT id, email, status
FROM ranked_customers
WHERE row_number = 1;
```

This example retrieves the newest customer in each status in deterministic order. It demonstrates SQL syntax supported by modern databases; verify CTE/window function support and column names on your target DBMS.

If you need to call stored procedures, JPA provides `@Procedure` and `StoredProcedureQuery`; native SQL is not always the best approach. Choose the API that matches how the procedure accepts parameters, returns result sets, and participates in transactions.

## 9. Organizing Repositories and Custom Repositories

Avoid stuffing a single repository with dozens of very long native SQL statements if they serve distinct complex queries. Split into a custom repository when you need:

- Dynamic condition assembly with whitelisting.
- Dialect-specific SQL variants.
- Mapping multiple result sets or specialized DTOs.
- Tuning queries that require hints or provider-specific configuration.
- Custom control over pagination, sorting, and count queries.

Example structure:

```text
customer/
├── Customer.java
├── CustomerRepository.java
├── CustomerRepositoryCustom.java
├── CustomerRepositoryImpl.java
├── CustomerSummaryView.java
└── CustomerService.java
```

`CustomerRepository` retains CRUD and simple derived queries. `CustomerRepositoryCustom` declares the custom API; `CustomerRepositoryImpl` uses `EntityManager` or `JdbcTemplate` when finer control over SQL and mapping is needed.

Keep native queries on repository methods when the statements are static, short, and easy to follow. Move to a custom repository when SQL construction logic or result processing becomes complex.

## 10. Testing Native Queries

Native SQL must be tested on a database close to the real runtime environment, especially when using vendor-specific syntax, JSON, CTEs, window functions, hints, specialized data types, or count queries.

For portable queries and simple schemas, you can use `@DataJpaTest` with H2:

```java
package com.example.learning.customer;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerNativeQueryTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void findsCustomersUsingNativeSql() {
        customers.saveAll(List.of(
            new Customer("a@example.test", "ACTIVE"),
            new Customer("b@example.test", "SUSPENDED")
        ));
        customers.flush();

        List<Customer> result = customers.findNativeByStatus("ACTIVE");

        assertThat(result)
            .extracting(Customer::getEmail)
            .containsExactly("a@example.test");
    }
}
```

This test assumes the `Customer` entity has a `Customer(String email, String status)` constructor, a `getEmail()` getter, and the `findNativeByStatus` repository method from the earlier example; the project also has `spring-boot-starter-test` and H2 on the test runtime classpath.

H2 does not fully emulate all PostgreSQL, MySQL, SQL Server, or Oracle syntax. If native SQL uses engine-specific features, run integration tests against that same DBMS, typically via Testcontainers or a dedicated test database.

For paginated queries, verify both page content and total row count. For updates/deletes, verify the affected row count and re-read the data after refreshing/clearing the persistence context. For projections/DTOs, verify aliases, data types, and constructor mapping order.

## 11. Common Pitfalls

- **Forgetting `nativeQuery = true` when writing SQL in `@Query`.** Spring parses the string as JPQL and may report nonexistent entity/property errors.
- **Using entity/property names in native SQL.** SQL requires physical table and column names per the schema.
- **Selecting too few columns when returning an entity.** The provider lacks enough data to hydrate the entity; use a projection/DTO if only partial data is needed.
- **Forgetting `@Param` or mismatching parameter names.** Names in SQL must match `@Param`.
- **Concatenating input into SQL.** Use bind parameters for values and whitelist identifiers/sort fields.
- **Using `Page` with an inaccurate count query.** The count query must preserve the same filters and avoid overcounting when joining.
- **Assuming native queries always support dynamic `Sort`.** Write an explicit `ORDER BY` or manage safe sorting yourself.
- **Writing a native `UPDATE` without `@Modifying`.** Spring Data needs to know it is a write operation.
- **Running a bulk update and continuing to use stale entities in the persistence context.** Refresh/clear or design appropriate transaction boundaries.
- **Using `@NativeQuery` on Spring Data JPA earlier than 3.4.** Use `@Query(nativeQuery = true)` or upgrade dependencies as a compatible set.
- **Testing vendor-specific native SQL only on H2.** Test against the target database to catch dialect differences.
- **Assuming function names, data types, and SQL syntax are portable.** Native queries are tied to a specific DBMS; document the target database/version when needed.

## 12. Workflow for Choosing Annotations and Implementing

1. Check whether the query truly needs native SQL or if derived queries/JPQL already suffice.
2. Determine the resolved Spring Data JPA version in the build.
3. If the version is below 3.4, use `@Query(value = "...", nativeQuery = true)`; from 3.4 onward, `@NativeQuery` can be used.
4. Choose the result type: entity, interface projection, or DTO with `@SqlResultSetMapping`.
5. Use bound parameters for values; never concatenate user input into SQL.
6. For `Page`, write and test `countQuery`; consider `Slice` when total count is unnecessary.
7. For `UPDATE`/`DELETE`, add `@Modifying` and ensure a transaction is active.
8. Check persistence context impact after bulk operations.
9. Run integration tests on a compatible database and inspect SQL/execution plans when performance matters.
10. Document dialect/version assumptions if the query relies on database-specific features.

## 13. Quick Selection Table

| Need | Suitable Approach |
| --- | --- |
| Simple CRUD or conditions by entity | Derived query |
| Queries over entities/properties needing JPA joins and predicates | JPQL with `@Query` |
| Native SQL, Spring Data JPA below 3.4 | `@Query(nativeQuery = true)` |
| Native SQL, Spring Data JPA 3.4+ | `@NativeQuery` or `@Query(nativeQuery = true)` |
| Only a few columns needed | Interface projection |
| DTO constructor mapping from a result set | `@NativeQuery(sqlResultSetMapping = ...)` from 3.4+ or custom repository with `EntityManager` |
| Paginated native query | `Page<T>` with explicit `countQuery` |
| Native UPDATE/DELETE | `@Modifying` + transaction |
| Complex dynamic SQL or whitelisted sorting | Custom repository |

## Conclusion

`@Query(nativeQuery = true)` has long been the standard way to declare native SQL in Spring Data JPA. `@NativeQuery`, introduced in Spring Data JPA 3.4.0, offers a more specialized syntax and supports `sqlResultSetMapping`. Always verify the actual resolved dependency version, use physical table/column names, bind parameters, pick an appropriate result mapping, declare `countQuery` for pagination, and manage the persistence context after bulk updates/deletes. Native SQL is very helpful when you need statement-level control or database-specific features, provided you test on the target DBMS and accept tighter coupling to schema and dialect.