# Declaring Repository Methods with @Procedure

## 1. Objectives

A stored procedure is a SQL program stored and executed inside the database. Spring Data JPA allows calling stored procedures from Repository methods using the `@Procedure` annotation, built on top of JPA's Stored Procedure API.

After this lesson, you will be able to:
- Distinguish the database procedure name from the JPA name used to register `@NamedStoredProcedureQuery`.
- Declare `IN`, `OUT`, `INOUT`, and `REF_CURSOR` parameter metadata.
- Call a procedure with `@Procedure` and receive a single OUT parameter as the return value.
- Map multiple OUT parameters to a `Map<String, Object>`.
- Choose between `value`, `procedureName`, and `name` in `@Procedure`.
- Invoke a procedure via `EntityManager` when finer control over parameters or results is needed.
- Manage transactions and the persistence context when a procedure modifies data.
- Test procedure calls against a database that supports stored procedures.

## 2. Stored procedures and Spring Data JPA

A stored procedure is a routine defined in the database. It can accept input parameters, modify data, return output parameters, or return one or more result sets.

Spring Data JPA provides `@Procedure` to declare how a Repository method invokes a procedure. JPA provides metadata and execution APIs through `StoredProcedureQuery`.

For example, the database has a `plus1inout` procedure that accepts an integer and returns that number plus 1:

```sql
CREATE PROCEDURE plus1inout (IN arg INT, OUT res INT)
BEGIN ATOMIC
    SET res = arg + 1;
END
```

The application calls the procedure with `arg = 41` and receives `res = 42`.

Stored procedures fit well when logic must run inside the database, is shared across multiple applications, leverages database data-processing capabilities, or adheres to an existing database contract. For simple CRUD queries, derived queries or JPQL are usually easier to maintain and less database-dependent.

## 3. Dependency configuration

Examples use Java 17+, Spring Boot 3.x, Spring Data JPA, and Hibernate managed by Spring Boot. A JDBC driver matching the running database is required.

Example application dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
```

Example HSQLDB dependency for integration testing only:

```xml
<dependency>
    <groupId>org.hsqldb</groupId>
    <artifactId>hsqldb</artifactId>
    <scope>test</scope>
</dependency>
```

Spring Boot 3 uses Jakarta Persistence (`jakarta.persistence.*`). Do not mix Jakarta annotations with legacy dependencies that only provide `javax.persistence.*`. Let Spring Boot dependency management manage compatible Hibernate, Spring Data JPA, and driver versions.

## 4. Two types of names in @NamedStoredProcedureQuery

JPA allows registering stored procedure metadata on an Entity using `@NamedStoredProcedureQuery`. The annotation has two distinct names:

| Attribute | Meaning |
| --- | --- |
| `name` | Logical JPA name used in EntityManager and referenced by `@Procedure(name = ...)`. |
| `procedureName` | Actual routine name in the database. |

Example:

```java
@NamedStoredProcedureQuery(
    name = "Calculator.plus1",
    procedureName = "plus1inout",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN, name = "arg", type = Integer.class),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT, name = "res", type = Integer.class)
    }
)
```

Here `Calculator.plus1` is the JPA name, while `plus1inout` is the procedure name in the database. The two names do not have to be identical. The logical JPA name must be unique within the persistence unit to avoid conflicts.

## 5. Declaring an Entity with procedure metadata

Example placing `@NamedStoredProcedureQuery` on the `Calculator` Entity:

`src/main/java/com/example/calculator/Calculator.java`:

```java
package com.example.calculator;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.NamedStoredProcedureQuery;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureParameter;
import jakarta.persistence.Table;

@Entity
@Table(name = "calculators")
@NamedStoredProcedureQuery(
    name = "Calculator.plus1",
    procedureName = "plus1inout",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "arg",
            type = Integer.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "res",
            type = Integer.class
        )
    }
)
public class Calculator {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String label;

    protected Calculator() {
        // JPA requires a no-arg constructor.
    }

    public Calculator(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("Label is required");
        }
        this.label = label.trim();
    }

    public Long getId() {
        return id;
    }

    public String getLabel() {
        return label;
    }
}
```

This Entity serves as the registration site for the procedure metadata. Calling `plus1inout` itself does not require creating or loading a `Calculator` row. The `calculators` table is still created/managed according to Entity mapping like other JPA Entities.

## 6. Repository calling a procedure with @Procedure

`@Procedure` resides in package `org.springframework.data.jpa.repository.query`.

`src/main/java/com/example/calculator/CalculatorRepository.java`:

```java
package com.example.calculator;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.query.Procedure;
import org.springframework.data.repository.query.Param;

public interface CalculatorRepository extends JpaRepository<Calculator, Long> {
    @Procedure(name = "Calculator.plus1")
    Integer plusOne(@Param("arg") Integer argument);
}
```

When invoked:

```java
Integer result = calculatorRepository.plusOne(41);
System.out.println(result);
```

Expected output:

```text
42
```

Method `plusOne` references the JPA name `Calculator.plus1`. `@Param("arg")` maps the Java argument to the IN parameter named `arg` in the metadata. The procedure returns an OUT parameter named `res`; Spring Data JPA converts that OUT value into the method's `Integer` return value.

For a single OUT parameter, the Repository return type must be compatible with the Java type declared for the OUT parameter. For example, `Integer.class` corresponds to `Integer`.

## 7. Choosing value, procedureName, or name

The `@Procedure` annotation has three common ways to reference a procedure:

### 7.1. Using name for a JPA named procedure

```java
@Procedure(name = "Calculator.plus1")
Integer plusOne(@Param("arg") Integer argument);
```

`name` references the `name` attribute of `@NamedStoredProcedureQuery`. This is suitable when the Entity already declares complete parameter metadata using JPA.

### 7.2. Using procedureName for the database name

```java
@Procedure(
    procedureName = "plus1inout",
    outputParameterName = "res"
)
Integer callPlusOne(@Param("arg") Integer argument);
```

`procedureName` points directly to the procedure in the database. This approach does not use `@NamedStoredProcedureQuery` configuration; you must ensure parameter and output metadata match how Spring Data/the provider registers the call.

### 7.3. Using value as shorthand

```java
@Procedure("plus1inout")
Integer callPlusOne(@Param("arg") Integer argument);
```

`value` is shorthand for `procedureName`. It also points directly to the procedure name in the database.

### 7.4. Omitting attributes

If none of `value`, `procedureName`, or `name` is specified, Spring Data uses the Repository method name as the JPA named procedure name. For example, a `plus1inout(...)` method looks up a named procedure with the corresponding name in `EntityManager`.

Do not confuse the Java method name with the database procedure name. When the two names differ, explicitly declare `name` or `procedureName` for readability.

## 8. IN, OUT, INOUT, and REF_CURSOR parameters

`@StoredProcedureParameter` describes each parameter of a stored procedure:

| ParameterMode | Meaning |
| --- | --- |
| `IN` | Application passes a value into the procedure. |
| `OUT` | Procedure writes a value for the application to read after the call. |
| `INOUT` | Application passes an initial value and the procedure can return a new value. |
| `REF_CURSOR` | Procedure returns a cursor/result set; support depends on database and provider. |

Metadata example for one IN parameter and one OUT parameter:

```java
@StoredProcedureParameter(
    mode = ParameterMode.IN, name = "customerId", type = Long.class
),
@StoredProcedureParameter(
    mode = ParameterMode.OUT, name = "orderCount", type = Long.class
)
```

Parameter names in metadata must match the procedure names recognized by the database/provider. For databases that are case-sensitive or have specific schema rules, verify the engine's naming conventions.

For `INOUT`, register mode `ParameterMode.INOUT` and the corresponding Java type. The input value is bound before execution; the output value is read after the procedure runs. Whether parameters are bound by name or position depends on JPA provider and driver support.

`REF_CURSOR` is not uniformly supported across all databases. Only use it when the project's database, JDBC driver, and Hibernate/JPA provider support that cursor-returning mechanism; test on the exact deployment engine.

## 9. Procedures with multiple OUT parameters

If a procedure declares multiple OUT parameters, Spring Data JPA can return them as a `Map<String, Object>` when the metadata is registered with `@NamedStoredProcedureQuery`.

Metadata example:

```java
@NamedStoredProcedureQuery(
    name = "Calculator.summary",
    procedureName = "order_summary",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN, name = "customerId", type = Long.class),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT, name = "orderCount", type = Long.class),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT, name = "totalAmount", type = BigDecimal.class)
    }
)
```

Repository:

```java
@Procedure(name = "Calculator.summary")
Map<String, Object> summarizeCustomer(
        @Param("customerId") Long customerId);
```

Calling and reading results:

```java
Map<String, Object> summary = repository.summarizeCustomer(101L);

Long orderCount = (Long) summary.get("orderCount");
BigDecimal totalAmount = (BigDecimal) summary.get("totalAmount");
```

The Map keys are the OUT parameter names declared in `@NamedStoredProcedureQuery`. Value types must match the Java/provider-returned types; for numeric types, drivers may return different wrapper types depending on the database, so verify the specific mapping.

`@NamedStoredProcedureQuery` metadata is required for multiple OUT parameters because it supplies the parameter list and modes needed to map the results.

## 10. Calling procedures with EntityManager

When you need dynamic parameter registration, handling of multiple parameters, or direct control over results, you can use JPA `StoredProcedureQuery` via `EntityManager` instead of `@Procedure` on a Repository.

Example calling procedure `plus1inout`:

```java
package com.example.calculator;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;
import org.springframework.stereotype.Repository;

@Repository
public class CalculatorProcedureGateway {
    private final EntityManager entityManager;

    public CalculatorProcedureGateway(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public Integer plusOne(Integer argument) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery("plus1inout");

        query.registerStoredProcedureParameter(
                "arg", Integer.class, ParameterMode.IN);
        query.registerStoredProcedureParameter(
                "res", Integer.class, ParameterMode.OUT);
        query.setParameter("arg", argument);

        query.execute();
        return (Integer) query.getOutputParameterValue("res");
    }
}
```

JPA also allows registering parameters by 1-based position. For example, `registerStoredProcedureParameter(1, Integer.class, ParameterMode.IN)`. Using names or positions must be consistent with metadata and provider/database support.

`EntityManager.createStoredProcedureQuery` accepts the procedure name in the database. If you need to map a result set to an Entity or predefined mapping, you can use the overloads accepting a result class or result set mapping from the JPA API.

## 11. Procedures returning a result set

A procedure can return one or more result sets instead of only scalar OUT values. For example, a procedure finding recent orders by customer.

The ability to read result sets depends on how the database declares procedures, the JDBC driver, and the JPA provider. In JPA, metadata can use `resultClasses` or `resultSetMappings`; some databases use `REF_CURSOR` to return cursors.

Do not assume a `@Procedure` method can simultaneously return arbitrary combinations of data types. If a procedure returns a ResultSet alongside OUT parameters, Spring Data JPA has limitations: ResultSet results and OUT parameters cannot both be represented as independent return values in a simple return type. For multiple OUT parameters, use a `Map`; if there are cursors/result sets, verify provider behavior and design the method/`EntityManager` call appropriately.

For procedures returning complex data, verify via integration tests on the exact database and driver. If mapping becomes hard to read, a custom repository or JDBC `CallableStatement` may be a better fit.

## 12. Transactions when calling procedures

If a procedure modifies data, invoke it within a Service-managed transaction:

```java
package com.example.calculator;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CalculatorService {
    private final CalculatorRepository repository;

    public CalculatorService(CalculatorRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Integer calculate(Integer argument) {
        if (argument == null) {
            throw new IllegalArgumentException("Argument is required");
        }
        return repository.plusOne(argument);
    }
}
```

`@Transactional` establishes the transaction boundary at the Service layer, encompassing the procedure call and other business steps. Specific commit/rollback rules depend on the database and how the procedure is defined. Do not add COMMIT/ROLLBACK statements inside the routine if the application manages transactions via Spring; some engines impose specific restrictions on transaction control inside procedures.

If a procedure only reads data, `@Transactional(readOnly = true)` may be used when compatible with the database/provider. Do not mark procedures that write data as read-only.

## 13. Persistence context when a procedure modifies data

Procedures execute SQL in the database and can update rows currently managed by JPA in the persistence context. Previously loaded Entities are not automatically synchronized just because the procedure modified the table.

Example:

1. Service loads `Product` with price 100 into the persistence context.
2. Procedure updates the price in the database to 120.
3. The managed `Product` object may still show price 100.

To avoid reading stale data:

- Call `EntityManager.flush()` before the procedure if pending JPA changes must be written before the routine executes.
- Call `EntityManager.refresh(entity)` for a specific Entity that needs to be re-synchronized.
- Call `EntityManager.clear()` after the procedure if you need to evict all managed Entities from the persistence context and reload them.

Clearing detaches every managed Entity, not just Entities modified by the procedure. Choose the timing carefully and avoid continuing to use old objects as if they were still managed.

`@Modifying(clearAutomatically = true)` is an attribute of `@Modifying` for modifying queries, not an attribute of `@Procedure`. With stored procedures, control flush/refresh/clear via `EntityManager` or an explicit Service workflow.

## 14. Do not use @Modifying with @Procedure

`@Modifying` marks a JPQL/native SQL `@Query` as an UPDATE or DELETE statement to execute rather than a query that reads data.

`@Procedure` already selects the execution path for stored procedures. Do not add `@Modifying` to the same method to try enabling write mode. Transactions for procedure operations are managed with `@Transactional` at the Service or Repository level as needed.

Example:

```java
@Procedure(name = "Calculator.plus1")
Integer plusOne(@Param("arg") Integer argument);
```

This is a procedure-calling method; `@Modifying` is not needed.

## 15. Defining the procedure in the database

A stored procedure is a database object; it is not created merely by Java annotations. You must deploy procedure DDL through migrations or schema management scripts.

HSQLDB example used in this lesson:

```sql
DROP PROCEDURE IF EXISTS plus1inout;

CREATE PROCEDURE plus1inout (IN arg INT, OUT res INT)
BEGIN ATOMIC
    SET res = arg + 1;
END
```

Procedure syntax differs among PostgreSQL, MySQL, SQL Server, Oracle, and HSQLDB. Write migrations for the actual target engine. If different environments use different databases, manage scripts per database/dialect rather than assuming a single DDL script runs on all engines.

Putting procedures in Flyway or Liquibase helps version routine changes, deploy alongside the application, and review change history.

## 16. Testing @Procedure with HSQLDB

The test example uses HSQLDB to run a procedure with one IN and one OUT parameter. HSQLDB uses `CREATE PROCEDURE ... BEGIN ATOMIC ... END` syntax suitable for this example.

Test dependency:

```xml
<dependency>
    <groupId>org.hsqldb</groupId>
    <artifactId>hsqldb</artifactId>
    <scope>test</scope>
</dependency>
```

`src/test/resources/application.properties`:

```properties
spring.datasource.url=jdbc:hsqldb:mem:storedprocdb
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

Repository used in the test:

```java
package com.example.calculator;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.query.Procedure;
import org.springframework.data.repository.query.Param;

public interface CalculatorRepository extends JpaRepository<Calculator, Long> {
    @Procedure(name = "Calculator.plus1")
    Integer plusOne(@Param("arg") Integer argument);
}
```

Integration test:

```java
package com.example.calculator;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.jdbc.core.JdbcTemplate;

@DataJpaTest
class CalculatorProcedureTest {
    @Autowired
    private CalculatorRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void createStoredProcedure() {
        jdbcTemplate.execute("DROP PROCEDURE IF EXISTS plus1inout");
        jdbcTemplate.execute("""
                CREATE PROCEDURE plus1inout (IN arg INT, OUT res INT)
                BEGIN ATOMIC
                    SET res = arg + 1;
                END
                """);
    }

    @Test
    void mapsSingleOutParameterToRepositoryReturnValue() {
        Integer result = repository.plusOne(41);

        assertThat(result).isEqualTo(42);
    }

    @Test
    void mapsNegativeInputWithoutChangingProcedureContract() {
        Integer result = repository.plusOne(-2);

        assertThat(result).isEqualTo(-1);
    }
}
```

The test verifies that Spring Data JPA invokes the right procedure, binds the IN parameter `arg`, and maps the OUT parameter `res` to the return value. The procedure is recreated using `JdbcTemplate` before each test so that each test stays independent of leftover routine state in the test database.

Run:

```bash
mvn test
```

The expected result is Maven finishing with `BUILD SUCCESS`; two tests verify that `41` returns `42` and `-2` returns `-1`. This is the expected outcome from the example, not a build log executed in this environment.

HSQLDB tests verify basic JPA/Spring Data mapping. If production uses PostgreSQL, MySQL, SQL Server, or Oracle, add integration tests on that exact engine to verify routine syntax, parameter types, transactions, cursors, and driver behavior.

## 17. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Procedure not found | Wrong `procedureName`, procedure not yet migrated, or wrong schema. | Check deployed DDL, schema/search path, and database procedure name. |
| Named procedure not found | `@Procedure(name = ...)` does not match `@NamedStoredProcedureQuery.name`. | Use the exact JPA name, distinct from `procedureName` in the database. |
| Unable to bind IN parameter | `@Param` name does not match `@StoredProcedureParameter.name` or position is wrong. | Synchronize parameter names and types between Java metadata and DDL. |
| OUT value is null or wrong type | OUT parameter missing proper mode/type declaration or database returns a different type. | Check `ParameterMode.OUT`, Java type, JDBC type, and provider mapping. |
| Multiple OUTs but method returns a scalar | A single return value cannot hold multiple independent outputs. | Register named procedure metadata and use `Map<String, Object>`. |
| Procedure runs but loaded Entity still holds stale data | Database changed outside persistence context dirty checking. | Flush beforehand if needed and refresh/clear after the procedure. |
| Procedure writes data but fails to roll back as expected | Transaction boundary does not wrap the call or routine uses its own transaction control. | Place `@Transactional` on the Service and inspect database transaction behavior. |
| HSQLDB test passes but production fails | Routine syntax, parameter types, or cursors differ across databases. | Run integration tests on the production engine and driver. |
| Procedure returns unmappable result set | Database/provider uses specific cursor or result mapping mechanisms. | Check `REF_CURSOR`, `resultClasses`/`resultSetMappings`, or use EntityManager/JDBC. |
| Adding @Modifying causes method failure | `@Modifying` is for `@Query` DML, not `@Procedure`. | Remove `@Modifying`; use transactions for procedures that write data. |

## 18. Design principles

1. Use `@Procedure` when calling routines deployed in the database; simple CRUD is usually better served by derived queries or JPQL.
2. Distinguish `@NamedStoredProcedureQuery.name` (logical JPA name) from `procedureName` (database name).
3. Use `@Procedure(name = ...)` when reusing JPA metadata declared on an Entity.
4. Use `value` or `procedureName` when referencing a database routine directly; keep in mind this bypasses named-query metadata.
5. Declare the exact mode, name, and Java type of each IN/OUT/INOUT parameter.
6. Use a scalar return type for a single OUT parameter and `Map<String, Object>` for multiple OUT parameters with named metadata.
7. Only use `REF_CURSOR`/result sets when supported by database, driver, and provider; test on the target engine.
8. Place transaction boundaries at the Service layer when procedures modify data or need coordination with other JPA operations.
9. Synchronize the persistence context after a procedure modifies tables with managed Entities.
10. Do not use `@Modifying` on `@Procedure` methods.
11. Version procedure DDL with Flyway/Liquibase and manage scripts by database dialect.
12. Test procedure names, parameter binding, output mapping, transactions, and result sets against a real database.

## 19. Completion checklist

- [ ] Can explain stored procedures and the role of `@Procedure`.
- [ ] Can distinguish the JPA `name` from the database procedure name `procedureName`.
- [ ] Can register a procedure with `@NamedStoredProcedureQuery`.
- [ ] Can declare `IN` and `OUT` parameters using `@StoredProcedureParameter`.
- [ ] Can call a procedure using `@Procedure(name = ...)`.
- [ ] Can use `value` or `procedureName` to reference a database procedure directly.
- [ ] Can map a single OUT parameter to a Repository method's return value.
- [ ] Can map multiple OUT parameters to `Map<String, Object>`.
- [ ] Knows when `EntityManager.createStoredProcedureQuery` is needed.
- [ ] Can manage transactions when a procedure modifies data.
- [ ] Can flush/refresh/clear the persistence context when necessary.
- [ ] Can test routines on the exact deployment database engine.

## 20. References

- [Spring Data JPA — Stored Procedures](https://docs.spring.io/spring-data/jpa/reference/jpa/stored-procedures.html)
- [Spring Data JPA — Procedure annotation API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/query/Procedure.html)
- [Jakarta Persistence — StoredProcedureQuery API](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/storedprocedurequery)
- [HyperSQL User Guide — SQL-Invoked Routines](https://hsqldb.org/doc/2.0/guide/sqlroutines-chapt.html)

Upon completion, you can declare Repository methods to invoke stored procedures, bind parameters properly, receive outputs, and manage transactions and the persistence context in Spring Data JPA.