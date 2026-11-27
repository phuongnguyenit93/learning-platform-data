# Mapping Return Values, Multiple OUTs, and Result Sets from Stored Procedures in Spring Data JPA

A stored procedure is a routine defined and executed inside a database management system. Spring Data JPA provides `@Procedure` to invoke procedures from repositories; JPA provides `@NamedStoredProcedureQuery`, `StoredProcedureQuery`, and `@SqlResultSetMapping` to declare parameters and map results.

You should distinguish three forms of returned data:

- **Single OUT parameter:** typically mapped directly to the repository method's return type.
- **Multiple OUT parameters:** can be received as a `Map<String, Object>` when using `@Procedure` with a named stored procedure.
- **One or more result sets:** can be mapped to entities or DTOs. When you need to iterate through multiple result sets, update counts, and OUT parameters in a single call, `StoredProcedureQuery` provides clearer control over processing order.

Exact capabilities also depend on the database, JDBC driver, and JPA provider. The examples below use Java 17+, Spring Boot 3.x, Spring Data JPA, and Hibernate 6; illustrative DDL uses MySQL 8 syntax.

## 1. Types of parameters and results

JPA defines the following stored procedure parameter modes:

| Mode | Meaning |
|---|---|
| `IN` | Application passes a value into the procedure |
| `OUT` | Procedure returns a value to the application |
| `INOUT` | Application passes a value in and the procedure can modify it |
| `REF_CURSOR` | Reference to a cursor/result set; support depends on database and provider |

A stored procedure can return OUT parameters, result sets, or both. A result set consists of data rows returned from a `SELECT` statement inside the procedure. An OUT parameter is a separate value declared in the procedure signature. They are two distinct result channels.

Conceptual signature example:

```sql
PROCEDURE update_customer_credit(
    IN  p_customer_id,
    IN  p_delta,
    OUT p_new_credit,
    OUT p_status
)
```

The procedure accepts a customer ID and an amount delta, then returns the new credit balance and a processing status.

## 2. Declaring a named stored procedure

JPA allows declaring a stored procedure using `@NamedStoredProcedureQuery` on an entity. The `name` attribute is the logical name referenced by the application; `procedureName` is the actual procedure name in the database.

MySQL 8 example:

```sql
DELIMITER //

CREATE PROCEDURE update_customer_credit(
    IN p_customer_id BIGINT,
    IN p_delta DECIMAL(12, 2),
    OUT p_new_credit DECIMAL(12, 2),
    OUT p_status VARCHAR(20)
)
BEGIN
    DECLARE v_exists INT DEFAULT 0;

    SELECT COUNT(*)
      INTO v_exists
      FROM customers
     WHERE id = p_customer_id;

    IF v_exists = 0 THEN
        SET p_new_credit = NULL;
        SET p_status = 'NOT_FOUND';
    ELSE
        UPDATE customers
           SET credit_limit = credit_limit + p_delta
         WHERE id = p_customer_id;

        SELECT credit_limit
          INTO p_new_credit
          FROM customers
         WHERE id = p_customer_id;

        SET p_status = 'UPDATED';
    END IF;
END//

DELIMITER ;
```

This is MySQL-specific DDL; delimiters and data types may differ in PostgreSQL, SQL Server, Oracle, or other databases.

Place the procedure metadata on the `Customer` entity:

**Customer.java** — relevant declarations:

```java
package com.example.customer;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.NamedStoredProcedureQuery;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureParameter;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "customers")
@NamedStoredProcedureQuery(
    name = "Customer.updateCredit",
    procedureName = "update_customer_credit",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_customer_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_delta",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_new_credit",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_status",
            type = String.class
        )
    }
)
public class Customer {

    @Id
    private Long id;

    protected Customer() {
    }
}
```

This snippet shows the entity portion needed for procedure mapping; in a real application, the entity also contains fields and column mappings corresponding to the `customers` table.

Each parameter must declare the proper mode, name, and Java type matching the database signature. Declaration order should also match the procedure's parameter order for compatibility with providers and drivers that bind positionally. Parameter names improve code readability, though not all databases/drivers support named binding identically.

## 3. Mapping a single OUT parameter with `@Procedure`

If a procedure returns only one OUT parameter that the repository method needs, you can map that value directly to the return type.

Example of a procedure named `get_customer_credit` in the database that takes a customer ID and returns `p_credit`:

```java
package com.example.customer;

import java.math.BigDecimal;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.query.Procedure;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Transactional
    @Procedure(
        procedureName = "get_customer_credit",
        outputParameterName = "p_credit"
    )
    BigDecimal getCredit(
        @Param("p_customer_id") Long customerId
    );
}
```

Here:

- `procedureName` points to the procedure name in the database.
- `outputParameterName` specifies the OUT parameter to use as the method result.
- `@Param` binds the Java argument to the IN parameter.
- The `BigDecimal` return type must be compatible with the OUT parameter type.

If `@NamedStoredProcedureQuery` is already declared, you can reference the logical name using `@Procedure(name = "Customer.updateCredit")`. In this case, the `name` attribute is the JPA named query name, distinct from `procedureName` which is the database procedure name.

## 4. Mapping multiple OUT parameters to a Map

A procedure with multiple OUT parameters cannot be fully represented by a single scalar return value. Spring Data JPA allows a repository method to return `Map<String, Object>` when referencing a named stored procedure.

**CustomerRepository.java** — adding the method:

```java
@Transactional
@Procedure(name = "Customer.updateCredit")
Map<String, Object> updateCredit(
    @Param("p_customer_id") Long customerId,
    @Param("p_delta") BigDecimal delta
);
```

Invocation:

```java
Map<String, Object> output =
    customerRepository.updateCredit(42L, new BigDecimal("25.00"));

BigDecimal newCredit =
    (BigDecimal) output.get("p_new_credit");

String status =
    (String) output.get("p_status");
```

The `Map` contains the OUT values returned by the provider, accessed by the declared parameter names. Verify the actual keys with integration tests on the database/driver in use; casing rules and how names are exposed may vary across providers.

Do not confuse an OUT `Map` with a result set: a `Map` holds output parameter values, whereas a result set is a list of rows from a `SELECT` statement. If a procedure returns both multiple OUT parameters and multiple result sets, consider JPA `StoredProcedureQuery` or JDBC to control the entire result stream.

## 5. Mapping a result set to a DTO

A procedure can return rows of data. If the result columns do not directly match an entity, you can use `@SqlResultSetMapping` with `@ConstructorResult` to map them to a DTO.

Two Java DTOs:

**CustomerSummary.java**

```java
package com.example.customer;

public record CustomerSummary(
    Long customerId,
    String customerName
) {
}
```

**RegionSummary.java**

```java
package com.example.customer;

public record RegionSummary(
    String region,
    Long orderCount
) {
}
```

Declare both mappings on a managed entity, such as `Customer`:

```java
@SqlResultSetMappings({
    @SqlResultSetMapping(
        name = "CustomerSummaryMapping",
        classes = @ConstructorResult(
            targetClass = CustomerSummary.class,
            columns = {
                @ColumnResult(name = "customer_id", type = Long.class),
                @ColumnResult(name = "customer_name", type = String.class)
            }
        )
    ),
    @SqlResultSetMapping(
        name = "RegionSummaryMapping",
        classes = @ConstructorResult(
            targetClass = RegionSummary.class,
            columns = {
                @ColumnResult(name = "region", type = String.class),
                @ColumnResult(name = "order_count", type = Long.class)
            }
        )
    )
})
@Entity
@Table(name = "customers")
public class Customer {
    // Entity fields and mappings.
}
```

The names in `@ColumnResult` must match the column aliases returned by the procedure. The column order in `@ConstructorResult` must match the DTO constructor's parameter order.

Example MySQL procedure returning two result sets:

```sql
DELIMITER //

CREATE PROCEDURE customer_report(
    IN p_year INT,
    OUT p_total BIGINT
)
BEGIN
    SELECT id AS customer_id,
           name AS customer_name
      FROM customers
     WHERE YEAR(created_at) = p_year
     ORDER BY id;

    SELECT region,
           COUNT(*) AS order_count
      FROM orders
     WHERE YEAR(created_at) = p_year
     GROUP BY region
     ORDER BY region;

    SELECT COUNT(*)
      INTO p_total
      FROM orders
     WHERE YEAR(created_at) = p_year;
END//

DELIMITER ;
```

The first result set has columns `customer_id` and `customer_name`; the second has `region` and `order_count`. The OUT parameter `p_total` returns the total order count for the given year.

## 6. Iterating multiple result sets with `StoredProcedureQuery`

A `@Procedure` repository method works well for simple signatures. When you need to handle multiple result sets in order, interleaved with update counts, and read OUT parameters, the JPA API provides clearer control.

Create an aggregate result:

**CustomerReport.java**

```java
package com.example.customer;

import java.util.List;

public record CustomerReport(
    List<CustomerSummary> customers,
    List<RegionSummary> regions,
    Long totalOrders
) {
}
```

Custom DAO/repository:

**CustomerReportDao.java**

```java
package com.example.customer;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.StoredProcedureQuery;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class CustomerReportDao {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public CustomerReport loadReport(int year) {
        StoredProcedureQuery query =
            entityManager.createStoredProcedureQuery(
                "customer_report",
                "CustomerSummaryMapping",
                "RegionSummaryMapping"
            );

        query.registerStoredProcedureParameter(
            "p_year", Integer.class, ParameterMode.IN
        );
        query.registerStoredProcedureParameter(
            "p_total", Long.class, ParameterMode.OUT
        );
        query.setParameter("p_year", year);

        List<List<?>> resultSets = new ArrayList<>();

        boolean hasResultSet = query.execute();

        while (true) {
            if (hasResultSet) {
                resultSets.add(query.getResultList());
            } else if (query.getUpdateCount() == -1) {
                break;
            }

            hasResultSet = query.hasMoreResults();
        }

        if (resultSets.size() != 2) {
            throw new IllegalStateException(
                "Expected two result sets, got " + resultSets.size()
            );
        }

        @SuppressWarnings("unchecked")
        List<CustomerSummary> customers =
            (List<CustomerSummary>) (List<?>) resultSets.get(0);

        @SuppressWarnings("unchecked")
        List<RegionSummary> regions =
            (List<RegionSummary>) (List<?>) resultSets.get(1);

        Number totalValue =
            (Number) query.getOutputParameterValue("p_total");

        Long totalOrders =
            totalValue == null ? null : totalValue.longValue();

        return new CustomerReport(customers, regions, totalOrders);
    }
}
```

How it works:

1. `createStoredProcedureQuery` receives the procedure name and the result set mappings in the order returned by the procedure.
2. Register `IN` and `OUT` parameters, then set the `IN` value.
3. `execute()` runs the procedure and indicates whether the current result is a result set.
4. If it is a result set, call `getResultList()`; if it is an update count, read `getUpdateCount()`.
5. Call `hasMoreResults()` to advance to the next result until no result sets or update counts remain.
6. After processing the results, read the OUT parameter via `getOutputParameterValue()`.

Handling update counts is necessary because a stored procedure may execute DML statements before returning `SELECT` results. If you only call `getResultList()` once, the application can miss subsequent result sets.

The result set mapping names in the example must be declared on a JPA-managed entity mapping. The database, driver, and provider must support returning multiple result sets in this manner; verify the actual order and data types in an integration test.

## 7. When to use `REF_CURSOR` or JDBC?

Some databases, especially DBMSs that support cursor parameters, return result sets via `REF_CURSOR`. JPA provides `ParameterMode.REF_CURSOR`, though cursor registration and retrieval support depend on the database, JDBC driver, and provider. Do not assume all databases support it identically.

If the provider does not properly handle multiple result sets, update counts, or cursors for your database, you can invoke the procedure via Spring JDBC (`JdbcTemplate`, `SimpleJdbcCall`) and `CallableStatement`. JDBC lets you use `getMoreResults()`, `getUpdateCount()`, and read OUT parameters according to driver capabilities. When using JDBC in the same application, ensure it uses the same `DataSource` and appropriate transaction manager so operations participate in the right transaction.

Do not mix multiple invocation approaches inside one transaction without clearly understanding connections and transaction boundaries. A procedure may issue its own commit or rollback if permitted by the database; that behavior can affect the Spring-managed transaction.

## 8. Transactions, mapping errors, and testing

A stored procedure can read or modify data. For procedures containing DML, set explicit transaction boundaries with `@Transactional` on the service or DAO. Avoid relying solely on a method residing in a repository without checking the transaction semantics of query methods.

Common errors:

| Symptom | Possible cause | What to check |
|---|---|---|
| Procedure not found | Wrong schema, name, or execute privilege | Check DDL, current schema, and database user privileges |
| Procedure runs but OUT is null/wrong type | Wrong mode, order, name, or Java/JDBC type | Cross-check procedure signature and `@StoredProcedureParameter`; check provider/driver |
| Map lacks expected key | Differences in how OUT parameter names are exposed | Print/log keys in a test environment; confirm naming per provider and database |
| DTO mapping column error | `SELECT` alias does not match `@ColumnResult` | Compare column names, data types, and constructor order |
| Only first result set is read | Did not iterate `hasMoreResults()` or driver lacks support | Handle update counts as well and verify driver multi-result support |
| Test passes on H2 but fails in production | Differences in procedure syntax, cursors, OUT parameters, or types | Run integration tests with the same database family or Testcontainers |

With stored procedures, H2 cannot always emulate the syntax and behavior of a production database. Prefer integration tests using the exact database family, driver, and version close to production. Tests should verify:

- Return value of scalar OUT parameters.
- Every key/value in the `Map` when there are multiple OUT parameters.
- Count, order, aliases, and data types of each result set.
- OUT parameters after consuming result sets, if the procedure returns both.
- Transaction commit/rollback and procedure side effects.
- Behavior on invalid parameters or missing data.

Do not use mocked repositories to conclude that stored procedure mapping is correct. Mocks only verify Java method calls; they do not verify that the procedure exists, parameters bind properly, or result sets map accurately.

## 9. Choosing the right mapping approach

| Need | Approach |
|---|---|
| Single OUT parameter, simple signature | `@Procedure` returning a scalar |
| Multiple OUT parameters, no multiple result sets needed | `@NamedStoredProcedureQuery` + `@Procedure` returning `Map<String, Object>` |
| Single result set mapped to entity/DTO | `@Procedure` or `StoredProcedureQuery` with appropriate result mapping |
| Multiple result sets or combining update counts and OUT | `EntityManager.createStoredProcedureQuery()` and iterating `hasMoreResults()` |
| Detailed driver-level control needed | Spring JDBC with `CallableStatement` |

When mapping stored procedures, treat the database signature as a contract: parameter modes, names, order, and types must match, and result set aliases and structures must match mappings. Use `@Procedure` for simple signatures, `Map` for multiple OUT parameters, and lower-level JPA/JDBC APIs when handling multiple result sets.