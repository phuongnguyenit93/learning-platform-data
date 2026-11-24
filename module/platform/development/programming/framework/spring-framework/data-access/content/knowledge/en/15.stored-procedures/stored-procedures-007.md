# Mapping Returned Results with `RowMapper` When Calling Procedures and Functions

## 1. Problem statement and target outcome

In **Spring Framework – Data Access**, a stored procedure or stored function can accept parameters, execute logic in the database, and return data. When the output contains **multiple rows and multiple columns**, the application typically needs to convert each row of a JDBC `ResultSet` into a Java object rather than letting the service layer handle raw `ResultSet`s.

Spring JDBC provides the `RowMapper<T>` interface to define the transformation **one row → one object of type `T`**. For procedure/function results, `RowMapper` is commonly configured via `SimpleJdbcCall.returningResultSet(...)` or by declaring `SqlReturnResultSet`/an appropriate cursor `OUT` parameter.

After this lesson, you will be able to:
- Distinguish ordinary `ResultSet` output, `REF_CURSOR` (an `OUT` cursor), scalar `OUT` parameters, and function return values.
- Write `RowMapper<T>` following its contract, using column labels and JDBC data types safely.
- Call a procedure with `SimpleJdbcCall`, map results into `List<T>`, and read the right key from `Map<String, Object>`.
- Handle multiple `ResultSet`s, `NULL` values, column-name mismatches, driver/database issues, and verify results.

**Scope limit:** examples are based on Spring JDBC and Java 17+. Do not apply them mechanically to JPA/Hibernate, R2DBC, or every stored function return type.

## 2. Where does `RowMapper` fit in the procedure call chain?

A typical call:

~~~text
Java code (input parameters)
  -> SimpleJdbcCall.execute(...)
  -> JDBC CallableStatement
  -> PROCEDURE in database
  -> JDBC ResultSet (or REF_CURSOR opened as ResultSet)
  -> Spring iterates each row, calling RowMapper.mapRow(rs, rowNum)
  -> List<EmployeeRow>
  -> output Map with key defined by returningResultSet configuration
  -> Repository returns DTO to Service
~~~

Contract:

~~~java
@FunctionalInterface
public interface RowMapper<T> {
    T mapRow(java.sql.ResultSet rs, int rowNum)
            throws java.sql.SQLException;
}
~~~

This is an **abbreviated signature for explanation**, not code you declare yourself: the actual interface is `org.springframework.jdbc.core.RowMapper` in Spring JDBC. Each `mapRow` receives the **current row** of the `ResultSet` and returns the corresponding object. Spring advances the cursor and manages resources.

Key rules:

1. **Do not call `rs.next()` inside `mapRow`**: Spring has already moved to the current row. Calling it again skips rows or breaks iteration.
2. **Do not close the `ResultSet` or connection**: Spring/JDBC manages their lifecycle. Return a DTO/record with data copied out of the result set.
3. **`rowNum` is 0-based**, meant for auxiliary logic such as tracking position; it is not a business ID and does not replace `ORDER BY`.
4. Keep mappers **stateless** so they can be reused safely; avoid accumulating lists, opening other connections, or causing side effects inside the callback.
5. `SQLException` from reading columns may propagate out; Spring translates it at the data-access layer. Do not catch it and return a dummy object that hides data errors.

Example of a concise mapper:

~~~java
RowMapper<EmployeeRow> mapper = (rs, rowNum) ->
    new EmployeeRow(
        rs.getLong("employee_id"),
        rs.getString("full_name"),
        rs.getBigDecimal("salary")
    );
~~~

Each time the callback runs, a new `EmployeeRow` object is created from exactly one row. With 0 rows, the collection result is normally an empty list; with 3 rows, there are 3 objects.

## 3. Classify the result type before choosing `RowMapper`

Not every procedure or function returns a list.

| Database result type | Example | Handling in Spring JDBC |
| --- | --- | --- |
| `ResultSet` emitted during procedure execution | MySQL procedure containing `SELECT ...` | `SimpleJdbcCall.returningResultSet("employees", mapper)` |
| `OUT` parameter of type `REF_CURSOR` / cursor | Oracle procedure exposing a cursor via an `OUT` parameter | `returningResultSet("out_cursor_name", mapper)` when supported by the driver and properly declared |
| One or more ordinary `OUT` parameters | `OUT total_count INT` | Declare `SqlOutParameter` and read the value from `Map`; **no `RowMapper` needed** |
| Function returning a scalar value | Function returning `VARCHAR` or `DECIMAL` | `withFunctionName(...).executeFunction(Type.class, ...)` |
| Set/table-returning function queryable via `SELECT` | Some table-valued/set-returning functions | `JdbcTemplate.query("SELECT ...", mapper, ...)` can be used per DB syntax |
| Multiple `ResultSet`s | Procedure executing multiple `SELECT` statements | Declare multiple `returningResultSet(...)` calls **in exact order** |

The name in `returningResultSet("employees", ...)` serves **two roles depending on the database**:

- For an unnamed `ResultSet` returned directly during execution, `"employees"` is an **application-chosen key** to read the list from the output `Map`.
- For a named `REF_CURSOR` `OUT` parameter, the name declared in Java must **match the cursor parameter name used by the procedure**; the driver and parameter declarations affect how the cursor is received.

Therefore, never take a table name, DTO name, or SQL alias and assume it is the `OUT` cursor name. Verify the routine signature and JDBC driver behavior.

## 4. End-to-end example: MySQL 8 returning a ResultSet from a procedure

Suppose we need to list employees in a department. This example uses **MySQL 8 + MySQL Connector/J + Spring JDBC**, because MySQL procedures can return `SELECT` results directly. The SQL snippets below run in a MySQL environment with privileges to create tables/procedures; they are not universal syntax across all DBs.

### 4.1. Creating the data

~~~sql
CREATE TABLE employees (
    id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    salary DECIMAL(12, 2) NOT NULL
);

INSERT INTO employees (id, department_id, full_name, salary)
VALUES
    (101, 7, 'Lan', 2000.00),
    (102, 7, 'Minh', 2300.00),
    (103, 9, 'Hoa', 2800.00);
~~~

The procedure returns rows with **stable column labels**. In the MySQL CLI, `DELIMITER` is a client directive to enter a procedure body containing `;` characters; it is not a standard SQL command sent directly over JDBC:

~~~sql
DELIMITER $$

CREATE PROCEDURE list_employees_by_department(
    IN p_department_id BIGINT
)
BEGIN
    SELECT
        id AS employee_id,
        full_name,
        salary
    FROM employees
    WHERE department_id = p_department_id
    ORDER BY id;
END$$

DELIMITER ;
~~~

Test before writing Java:

~~~sql
CALL list_employees_by_department(7);
~~~

Expected data:

| employee_id | full_name | salary |
| ---: | --- | ---: |
| 101 | Lan | 2000.00 |
| 102 | Minh | 2300.00 |

`ORDER BY id` guarantees a deterministic result order. Never rely on natural table order, especially when mappers or business logic depend on position.

### 4.2. Output DTO as a Java record

File `EmployeeRow.java`:

~~~java
package example.data;

import java.math.BigDecimal;

public record EmployeeRow(
    long id,
    String fullName,
    BigDecimal salary
) {}
~~~

`record` is a suitable data carrier for passing values out of the JDBC layer. In this example, `id`, `full_name`, and `salary` are all `NOT NULL`. Use `BigDecimal` for `DECIMAL` to avoid floating-point representation errors of `double` in monetary calculations.

### 4.3. Repository calling the procedure and registering `RowMapper`

File `EmployeeProcedureRepository.java`:

~~~java
package example.data;

import java.sql.Types;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.stereotype.Repository;

@Repository
public class EmployeeProcedureRepository {

    private static final RowMapper<EmployeeRow> EMPLOYEE_MAPPER =
        (rs, rowNum) -> new EmployeeRow(
            rs.getLong("employee_id"),
            rs.getString("full_name"),
            rs.getBigDecimal("salary")
        );

    private final SimpleJdbcCall listEmployees;

    public EmployeeProcedureRepository(DataSource dataSource) {
        this.listEmployees = new SimpleJdbcCall(dataSource)
            .withProcedureName("list_employees_by_department")
            .withoutProcedureColumnMetaDataAccess()
            .declareParameters(
                new SqlParameter("p_department_id", Types.BIGINT)
            )
            .returningResultSet("employees", EMPLOYEE_MAPPER);
    }

    public List<EmployeeRow> findByDepartment(long departmentId) {
        Map<String, Object> out = listEmployees.execute(
            Map.of("p_department_id", departmentId)
        );

        Object raw = out.get("employees");
        if (!(raw instanceof List<?> rows)) {
            throw new IllegalStateException(
                "Procedure did not return the expected employees result set"
            );
        }
        return rows.stream().map(EmployeeRow.class::cast).toList();
    }
}
~~~

This is **Spring component code**, not a `main` program runnable with just the JDK. It requires an application with a configured `DataSource` bean, the `spring-jdbc` dependency, a Spring context, and the MySQL JDBC driver—for example, a Spring Boot project with `spring-boot-starter-jdbc` and `mysql-connector-j` at runtime. Do not create or close a `DataSource` on every call.

Key points to understand:

1. `withProcedureName(...)` selects a procedure; do not use `withFunctionName(...)` for this example.
2. `withoutProcedureColumnMetaDataAccess()` disables parameter inference from JDBC metadata. Therefore, we **explicitly declare** the `IN` parameter using `SqlParameter("p_department_id", Types.BIGINT)`. This is helpful when driver metadata is unstable, though the declaration must match the signature.
3. `returningResultSet("employees", EMPLOYEE_MAPPER)` registers the mapper for the directly returned result set; `employees` is a Java-chosen key, **not** a parameter in the MySQL procedure.
4. `execute(Map.of(...))` supplies the `IN` parameter name and value. For nullable parameters, do not use `Map.of` (it rejects `null`); choose `MapSqlParameterSource` and declare the SQL type explicitly.
5. Spring iterates the result set and invokes `EMPLOYEE_MAPPER.mapRow(...)` for each row. `out.get("employees")` returns the list of mapped objects.
6. The `instanceof List<?>` check helps detect configurations/drivers that fail to return the expected result set. `EmployeeRow.class::cast` verifies element types when building the result list. If mapping is already guaranteed by the system, a controlled cast with `@SuppressWarnings("unchecked")` may be used.

With the SQL data above, calling `findByDepartment(7L)` returns **two** `EmployeeRow` instances with IDs 101 and 102. Calling `findByDepartment(99L)` normally returns an **empty list** if the procedure executed and produced a properly structured result set with zero rows. Distinguish an empty list from **a missing `"employees"` key** caused by the routine or configuration failing to return the expected result.

For a procedure with no `IN` parameters, use `listEmployees.execute(Map.of())` when the configuration and routine definition match. Do not pass a dummy value just to invoke the method.

## 5. Why map by column label?

In the example, the SQL returns `id AS employee_id`. The mapper must read `rs.getLong("employee_id")` because that is the **column label** of the `ResultSet`. Writing `rs.getLong("id")` depends on driver and metadata behavior and may fail with `Column 'id' not found`.

Contract design rules between the procedure and Java:

| SQL output | Java field | Getter |
| --- | --- | --- |
| `id AS employee_id` | `id: long` | `rs.getLong("employee_id")` |
| `full_name` | `fullName: String` | `rs.getString("full_name")` |
| `salary` `DECIMAL(12,2)` | `salary: BigDecimal` | `rs.getBigDecimal("salary")` |

Modifying the `SELECT` inside the procedure must be treated as changing the **output contract**. Update mappers, integration tests, and DTO consumers whenever column names or types change. Avoid `SELECT *` for stable contracts.

### Handling `NULL` properly

Primitive getters return default values for SQL `NULL`; for instance, `rs.getLong("nullable_id")` returns `0`, and only `rs.wasNull()` called immediately afterward distinguishes `NULL` from 0. For nullable data, consider:

~~~java
Long managerId = rs.getObject("manager_id", Long.class);
String nickname = rs.getString("nickname");
~~~

`managerId` can be `null` if the driver supports the corresponding JDBC 4.2 type mapping. With older drivers, use `getLong(...)` paired with `wasNull()` to handle it explicitly. Do not use primitive `long` when business semantics need to represent a missing value.

For `DATE`/`TIMESTAMP`, choose `LocalDate`/`LocalDateTime` or `Instant` based on the SQL type and actual timezone rules. Some drivers support `rs.getObject("created_date", LocalDate.class)`; a portable fallback may require converting from `getDate(...)`. Do not assume `TIMESTAMP WITHOUT TIME ZONE` means UTC.

## 6. A procedure returning multiple ResultSets

Suppose a procedure `department_report` executes in order:

~~~sql
SELECT id AS employee_id, full_name, salary
FROM employees
WHERE department_id = p_department_id
ORDER BY id;

SELECT COUNT(*) AS employee_count
FROM employees
WHERE department_id = p_department_id;
~~~

**This is an illustrative procedure body**, not a standalone runnable SQL file; place it inside your database's `CREATE PROCEDURE` syntax.

When the driver returns **two result sets in sequence**, you can register:

~~~java
record DepartmentSummary(long employeeCount) {}

RowMapper<DepartmentSummary> summaryMapper =
    (rs, rowNum) ->
        new DepartmentSummary(rs.getLong("employee_count"));

SimpleJdbcCall reportCall = new SimpleJdbcCall(dataSource)
    .withProcedureName("department_report")
    .returningResultSet("employees", employeeMapper)
    .returningResultSet("summary", summaryMapper);

Map<String, Object> out = reportCall.execute(
    Map.of("p_department_id", 7L)
);
~~~

This example is a **Java snippet inside a method/class that already has `dataSource` and `employeeMapper`**. When using automatic metadata, the driver must provide enough metadata to recognize `p_department_id`. If metadata is disabled, add `SqlParameter` declarations as in the full example in section 4.

Meaning:
- `out.get("employees")` is the employee list from the first `ResultSet`.
- `out.get("summary")` is the `DepartmentSummary` list from the second `ResultSet` (in this example, a single-element list containing `employeeCount`).
- The order of the two `returningResultSet(...)` calls **must match** the order in which the driver emits the result sets. If the routine swaps the two `SELECT` statements, mappers may read the wrong columns and fail.

Do not assume every `SELECT` in every routine always surfaces as a result set: some DBs/drivers have different semantics, interleaved update counts, or driver options affecting the result stream. Verify on the real database.

## 7. Case of `REF_CURSOR` as an `OUT` parameter

Some DBMSs, notably Oracle, let a procedure open a cursor and expose it through an **`OUT` parameter**. Here the result is not merely an unnamed result set; the cursor name is part of the procedure signature.

When the driver and Spring JDBC support this declaration style:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(dataSource)
    .withProcedureName("find_employees")
    .returningResultSet("p_employees_cursor", employeeMapper);

Map<String, Object> out = call.execute(
    Map.of("p_department_id", 7L)
);
~~~

This is a **configuration pattern**, not a standalone program or a guarantee of cross-DB compatibility. The procedure is assumed to actually have an `OUT` cursor named `p_employees_cursor`. With `REF` cursors, the parameter must be **registered and handled per driver**, and some cases require explicitly configuring the `OUT` parameter via `SqlOutParameter` together with a `RowMapper`/matching SQL type. When metadata is disabled, declare all `IN`/`OUT` parameters and use the cursor type supported by the driver; do not apply a single `Types` constant across all databases.

Beyond the cursor name, also check:
- Does the cursor stay alive long enough in the current transaction? Some databases require an active open transaction while reading the cursor.
- Does the driver return the cursor via `CallableStatement.getObject(...)`, a vendor-specific type, or a normal result set?
- Which schema/catalog holds the procedure signature, and does parameter name casing change?
- Are `EXECUTE` privileges and underlying data access privileges granted?

**Do not use an invented name like `"employees"` as the `OUT` cursor name** if the database actually declares `p_employees_cursor`; if you want a different logical name at the service layer, rename it after reading the procedure's output properly.

## 8. Lower-level option: `JdbcTemplate.call` and `SqlReturnResultSet`

`SimpleJdbcCall` is convenient for pre-configured calls. When direct control over `CallableStatement` is needed, Spring JDBC provides `JdbcTemplate.call(...)` and `SqlReturnResultSet`.

Example on the same MySQL procedure from section 4 (one result set):

~~~java
List<SqlParameter> declared = List.of(
    new SqlParameter("p_department_id", Types.BIGINT),
    new SqlReturnResultSet("employees", EMPLOYEE_MAPPER)
);

Map<String, Object> out = jdbcTemplate.call(
    connection -> {
        CallableStatement cs = connection.prepareCall(
            "{call list_employees_by_department(?)}"
        );
        cs.setLong(1, departmentId);
        return cs;
    },
    declared
);
~~~

This is a **snippet placed in a repository that already has `jdbcTemplate`, `departmentId`, and `EMPLOYEE_MAPPER`**; it requires imports for `java.sql.CallableStatement`, `java.sql.Types`, `java.util.List`, `java.util.Map`, `org.springframework.jdbc.core.SqlParameter`, and `org.springframework.jdbc.core.SqlReturnResultSet`.

`SqlReturnResultSet("employees", EMPLOYEE_MAPPER)` describes a **result set returned by the procedure**, and Spring puts the mapped list into `out` under the `"employees"` key. This is not how you read an `OUT` integer or scalar function. For a `REF` cursor `OUT`, configuration may be `SqlOutParameter("p_cursor", sqlCursorType, mapper)`, depending on the database/driver.

Pick one API for a given call; there is no need to run `SimpleJdbcCall.execute(...)` and then also call `JdbcTemplate.call(...)` just to map results once.

## 9. Manual `RowMapper` vs. built-in mappers

| Strategy | When to use | Things to keep in mind |
| --- | --- | --- |
| Lambda or class implementing `RowMapper<T>` | Need full control over column names, casting, defaults, and domain DTOs | Column signatures must match; avoid overly complex business logic |
| `BeanPropertyRowMapper<T>` | JavaBeans with a no-arg constructor and matching setters/getters | Relies on property name ↔ column label matching; should not be the default for immutable records |
| `DataClassRowMapper<T>` | Data classes with parameterized constructors / Java records matching column names | Constructor/property names and types must match; watch reflection overhead |
| `SingleColumnRowMapper<T>` | Single-column result set, each row mapped to a scalar | Does not map multiple columns into a complex DTO |
| `ResultSetExtractor<T>` | Need to aggregate multiple rows into a parent–child structure or map the whole set | You control iteration directly; no longer single-row mapping |
| `RowCallbackHandler` | Need to process each row with stateful logic/callback instead of building a `List` | Must check the procedure API and appropriate resource strategy |

For example, if you want to auto-map a record `EmployeeRow(long id, String fullName, BigDecimal salary)`, the SQL output should use matching column labels `id`, `full_name`, `salary`; then `DataClassRowMapper.newInstance(EmployeeRow.class)` can be considered. When the example uses label `employee_id` while the Java property is named `id`, the manual mapper in section 4 expresses the mapping more accurately.

Do not force every case into automatic mappers: when a procedure has calculations, aggregate columns, enums, or JSON, an explicit manual mapper is usually easier to review and test.

## 10. Special considerations for stored functions

**Scalar-returning stored functions** such as name, total amount, or count: use the dedicated API:

~~~java
SimpleJdbcCall getName = new SimpleJdbcCall(dataSource)
    .withFunctionName("get_employee_name");

String name = getName.executeFunction(
    String.class,
    Map.of("p_employee_id", 101L)
);
~~~

This **snippet depends on the function's signature and metadata in the database**. Do not build a `RowMapper` when there is no multi-row result table; the primary payload is a single return value.

**Set-returning stored functions:** some DBs support syntax like `SELECT * FROM some_function(?)`, in which case `JdbcTemplate.query(sql, rowMapper, args...)` can be used. Another pattern is an `OUT` cursor. Choose based on **how the driver exposes the result**, not solely on the keyword "function".

Example of a queryable result table (illustrative syntax, use only when supported by the DB):

~~~java
List<EmployeeRow> rows = jdbcTemplate.query(
    "SELECT employee_id, full_name, salary " +
    "FROM some_set_returning_function(?)",
    EMPLOYEE_MAPPER,
    departmentId
);
~~~

Do not take `SELECT ... FROM function(?)` from one DB and apply it to MySQL/Oracle/SQL Server without checking the corresponding function syntax.

## 11. Common errors and how to identify them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `out.get("employees")` is `null` | Wrong key name, procedure returns no result set, or wrong result set registration | Check procedure signature, output keys, result set order, and driver |
| "column not found" error | Mapper reads `id` while the SQL alias is `employee_id` | Inspect actual result set column labels and SQL `AS` aliases |
| Missing or swapped data | Mapper consumes `ResultSet`s in the wrong order for a multi-result procedure | Check order of `SELECT` / `returningResultSet(...)` |
| Value 0 instead of missing data | Primitive getter encountered SQL `NULL` | Use `wasNull()` or wrapper types |
| Procedure not found / parameter count mismatch | Wrong schema/catalog, signature, SQL type, or metadata | Declare `IN`/`OUT` explicitly, configure schema, and verify names |
| No results after transaction closes | Cursor depends on transaction lifecycle or resources were closed | Map data **inside** the valid cursor scope |
| Differences between dev/prod environments | Different DB, driver version, privileges, or metadata | Integration test on the same DB and driver |
| Sharp memory growth | Procedure returns too many rows and Spring materializes them all into a `List` | Limit results, paginate at the business level, or choose a streaming strategy |

With Spring JDBC, `SQLException` is normally translated into `DataAccessException`. Do not merely catch `SQLException` around `SimpleJdbcCall.execute(...)`; inspect the Spring-layer exception and walk its cause chain for `SQLState`/vendor code when investigating. If the application uses `@Transactional`, watch how exceptions propagate across boundaries and trigger rollbacks.

**Security and performance:** bind input parameters through JDBC placeholders/`SqlParameterSource` instead of concatenating user-supplied strings; never let arbitrary input become a procedure name or SQL identifier. Mappers should be pure transformations, avoiding extra queries per row (N+1 pattern) or logging sensitive data. `RowMapper` does not stream or lazy-load by default: lists returned by `returningResultSet` are normally fully materialized.

## 12. Testing what actually needs to be guaranteed

Prefer **integration tests** against a real database and driver, because stored procedure/`REF_CURSOR`/metadata behavior cannot be verified solely by unit testing `RowMapper`.

Scenarios to verify:

1. **Single row and multiple rows:** calling `CALL list_employees_by_department(7)` returns two rows; the mapper produces two `EmployeeRow`s with exact ID, name, and `BigDecimal`.
2. **No data:** calling with a nonexistent department returns an empty list rather than a missing key or `null` from misconfiguration.
3. **Column label change:** temporarily alter an alias in a test environment; verify the test catches the mapping error instead of silently assigning the wrong column.
4. **Nullable values:** add a nullable field if the schema permits, verifying SQL `NULL` is distinguished from 0/empty.
5. **Multiple result sets:** verify order, element types, output keys, and any interleaved update counts if the procedure executes DML.
6. **`REF` cursors and transactions:** on DBs using `OUT` cursors, test reading before transaction close, `OUT` names, type registration, and access privileges.
7. **Database errors:** nonexistent procedure, wrong SQL type, or missing privileges must produce observable errors; never convert them into an empty list.
8. **Large payloads:** check list size, latency, memory, and pagination strategies when result sets can grow very large.

An isolated unit test for the mapper can construct or mock a `ResultSet` with matching column labels, invoke `EMPLOYEE_MAPPER.mapRow(rs, 0)`, and assert the DTO. That proves **single-row** mapping logic, not the stored procedure call path. Add separate integration tests for `SimpleJdbcCall` configuration and the driver.

To run the two Java files in section 4 as application components, you need a Spring project build with the corresponding libraries and datasource; **you cannot run `javac EmployeeProcedureRepository.java` alone without Spring JDBC on the classpath**. The example does not promise a fixed stdout because output depends on data/database/driver. You can verify the data using `CALL list_employees_by_department(7)` first, then assert the returned fields.

## 13. Implementation checklist

- [ ] Determined whether the routine returns a direct `ResultSet`, `REF` cursor, or scalar?
- [ ] Configured the right `withProcedureName`/`withFunctionName`, `IN`/`OUT`, and schema?
- [ ] `returningResultSet(name, mapper)` uses the right **logical key** or exact **`OUT` cursor name** as applicable?
- [ ] With multiple result sets, does mapper order match the driver's return order?
- [ ] Does the mapper read the exact column labels, SQL types, `NULL`s, and timezones?
- [ ] Does the mapper avoid calling `rs.next()`/`close()` and avoid side effects?
- [ ] Is an empty list distinguished from a missing result set, and are errors never swallowed?
- [ ] Are there integration tests on the target DB/driver, including exception/transaction paths?
- [ ] Is output size reasonably bounded so it does not cause out-of-memory errors?

## References

- [Spring Framework – SimpleJdbcCall, Stored Function, Returning ResultSet/REF Cursor](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/simple.html): `SimpleJdbcCall` configuration, `returningResultSet`, output `Map`, metadata, and calling functions.
- [Spring Framework – RowMapper Javadoc (6.2)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/RowMapper.html): `mapRow(ResultSet, int)` contract, do not call `next()`.
- [Spring Framework – SqlReturnResultSet Javadoc (6.2)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/SqlReturnResultSet.html): describes result sets returned from procedures and mapping options.
- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html): `JdbcTemplate`, `RowMapper`, resource handling, and exceptions.
- [Java SE 17 – ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): getters, `wasNull()`, cursor, and column labels.
