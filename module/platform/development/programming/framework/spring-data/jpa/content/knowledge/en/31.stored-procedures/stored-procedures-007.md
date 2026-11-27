# Transactions, Procedure Errors, and Database-Specific Rules

## Objectives

A stored procedure is a program stored and executed inside a database management system (DBMS). Spring Data JPA can invoke procedures via the `@Procedure` annotation; Jakarta Persistence provides the `StoredProcedureQuery` API to register parameters, execute, and retrieve results.

Being able to invoke a procedure is only part of the design. A procedure can modify data, acquire or hold locks, raise SQL errors, return status codes, OUT parameters, or ResultSets. These behaviors must be placed inside clear transaction boundaries and tested against the exact database the application deploys to.

After this lesson, you will be able to:

- Distinguish JPA procedure metadata from the actual procedure in the database.
- Invoke procedures using `@Procedure` and `StoredProcedureQuery`.
- Register `IN`, `OUT`, `INOUT`, and `REF_CURSOR` parameters.
- Manage transactions when a procedure reads or writes data.
- Understand rollbacks, the persistence context, and stale entity data after bulk DML.
- Handle database errors via Spring `DataAccessException`.
- Distinguish SQL errors from business error codes returned by a procedure.
- Recognize differences across PostgreSQL, MySQL, SQL Server, Oracle, and providers.
- Test procedures against a production-compatible database.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA. Procedure creation syntax in the SQL sections is explicitly written for PostgreSQL; do not treat that DDL as portable SQL.

## 1. Where are procedures stored and who manages them?

Stored procedures live in the database schema. They can be created via SQL migrations, database administration tools, or separate deployment pipelines.

JPA does not automatically create a procedure simply because an entity has `@NamedStoredProcedureQuery`. That annotation only declares metadata so the persistence provider knows how to call an existing procedure.

Distinguish two names in metadata:

- `name`: the logical name JPA uses within the persistence unit.
- `procedureName`: the actual procedure name in the database, optionally schema-qualified.

Example:

```java
@Entity
@NamedStoredProcedureQuery(
    name = "Employee.raiseSalary",
    procedureName = "raise_salary",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_employee_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_increment",
            type = BigDecimal.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_new_salary",
            type = BigDecimal.class
        )
    }
)
public class Employee {
    // entity mapping
}
```

JPA looks up the metadata by `Employee.raiseSalary`; the database executes the procedure `raise_salary`. Migrations must ensure this procedure exists before the application calls it.

### 1.1. Managing DDL with migrations

In production applications, manage procedures using Flyway, Liquibase, or a standardized migration workflow:

- Create procedures in versioned migrations.
- Modify procedures in new migrations rather than editing previously executed migration history.
- Deploy procedures compatible with the running application version during rollouts.
- Grant `EXECUTE` privileges to the application's database user.
- Have a rollback or forward-fix plan if a migration fails.
- Test migrations on the exact target database type and version.

Do not embed procedure-creation DDL in Java code and run it arbitrarily on every application startup. Schema deployment needs clear ordering, permissions, and auditability.

## 2. Example of a data-modifying procedure

Suppose the `employees` table has columns `id` and `salary`. The procedure increases salary by employee ID and returns the new salary.

The example below uses PostgreSQL PL/pgSQL:

```sql
CREATE OR REPLACE PROCEDURE raise_salary(
    IN p_employee_id BIGINT,
    IN p_increment NUMERIC,
    OUT p_new_salary NUMERIC
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE employees
    SET salary = salary + p_increment
    WHERE id = p_employee_id
    RETURNING salary INTO p_new_salary;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Employee % does not exist', p_employee_id
            USING ERRCODE = 'P0002';
    END IF;
END;
$$;
```

The procedure does two things:

1. Updates `salary` in the database.
2. Returns the updated `salary` via the OUT parameter `p_new_salary`.

If no matching employee exists, the procedure raises a database error. This is appropriate when the caller expects the transaction to fail and roll back. Another design might return a status code; in that case, the service must inspect that code and decide whether to throw an exception to roll back.

The `CREATE OR REPLACE PROCEDURE` syntax, `plpgsql` block, `RETURNING INTO`, and SQLSTATE above belong to PostgreSQL. MySQL, SQL Server, and Oracle have different syntax for creating procedures, declaring parameters, handling exceptions, and returning results.

## 3. Calling procedures with @Procedure

Spring Data JPA provides `@Procedure` to declare a procedure on a repository method. With metadata on the entity, the repository references the JPA name via the `name` attribute:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Procedure(name = "Employee.raiseSalary")
    BigDecimal raiseSalary(
            @Param("p_employee_id") Long employeeId,
            @Param("p_increment") BigDecimal increment
    );
}
```

The method has two IN parameters and returns a single OUT value of type `BigDecimal`. Parameter names in `@Param` must match those declared in `@StoredProcedureParameter` and be supported by the provider/database.

The service wraps the call in a transaction:

```java
@Service
public class EmployeeSalaryService {

    private final EmployeeRepository repository;
    private final EntityManager entityManager;

    public EmployeeSalaryService(
            EmployeeRepository repository,
            EntityManager entityManager
    ) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional
    public BigDecimal increaseSalary(
            Long employeeId,
            BigDecimal increment
    ) {
        if (increment == null || increment.signum() <= 0) {
            throw new IllegalArgumentException(
                    "increment must be positive"
            );
        }

        entityManager.flush();

        BigDecimal newSalary =
                repository.raiseSalary(employeeId, increment);

        entityManager.clear();

        return newSalary;
    }
}
```

The service validates inputs, flushes pending JPA changes, calls the procedure, and clears the persistence context after the procedure updates data. The reasoning for flush/clear is explained in the persistence context section below.

### 3.1. Calling the database procedure name directly

If you do not need `@NamedStoredProcedureQuery`, Spring Data lets you specify the actual procedure name:

```java
@Procedure(procedureName = "raise_salary")
BigDecimal callRaiseSalary(
        Long employeeId,
        BigDecimal increment
);
```

`value` is an alias for `procedureName`. When using this direct declaration, Spring Data invokes the procedure in the database and does not use `@NamedStoredProcedureQuery` metadata declared for a JPA name.

The direct approach works well for simple procedures, especially when there is only a single OUT parameter. When multiple OUT parameters, `REF_CURSOR`, or detailed parameter metadata are needed, a named stored procedure is usually clearer.

### 3.2. Do not confuse name with procedureName

| Attribute | Example | Meaning |
|---|---|---|
| `@Procedure(name = ...)` | `Employee.raiseSalary` | JPA metadata name |
| `@Procedure(procedureName = ...)` | `raise_salary` | Procedure name in the database |
| `@Procedure("...")` | `@Procedure("raise_salary")` | Shorthand for `procedureName` |

Passing the logical JPA name to `procedureName` can cause the database to report that the procedure was not found. Conversely, passing the database name to `name` makes JPA look up metadata under that name in the persistence unit.

## 4. Parameter modes: IN, OUT, INOUT, and REF_CURSOR

Jakarta Persistence defines the primary modes:

| Mode | Role | Usage |
|---|---|---|
| `IN` | Input value | Java passes value to procedure |
| `OUT` | Output value | Procedure assigns result for Java to read |
| `INOUT` | Both receives input and returns result | Java passes initial value, procedure may modify it |
| `REF_CURSOR` | Returned cursor/result set | Provider fetches rows from cursor as supported by the database |

Parameters must be registered with the proper Java types and modes. `BigDecimal` is generally suitable for `NUMERIC`/`DECIMAL`; date/time types must be chosen compatibly with SQL types and the JDBC driver.

Do not guess mappings from column names alone. Confirm data types, numeric precision, time zones, and nullability across the procedure, JDBC driver, and Java.

### 4.1. Single OUT parameter

For example, the `raise_salary` procedure has one OUT parameter. Spring Data can return that OUT value directly as the repository method's return value:

```java
@Procedure(name = "Employee.raiseSalary")
BigDecimal raiseSalary(
        @Param("p_employee_id") Long employeeId,
        @Param("p_increment") BigDecimal increment
);
```

This is the simplest approach when a procedure returns a single scalar output and does not need to return a `ResultSet`.

### 4.2. Multiple OUT parameters

If a procedure has multiple OUT parameters, declare metadata via `@NamedStoredProcedureQuery` and return `Map<String, Object>`:

```java
@Entity
@NamedStoredProcedureQuery(
    name = "Employee.salarySummary",
    procedureName = "salary_summary",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_department_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_employee_count",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_total_salary",
            type = BigDecimal.class
        )
    }
)
public class Employee {
    // entity mapping
}
```

Repository:

```java
@Procedure(name = "Employee.salarySummary")
Map<String, Object> salarySummary(
        @Param("p_department_id") Long departmentId
);
```

Reading results:

```java
Map<String, Object> result =
        repository.salarySummary(departmentId);

Long employeeCount =
        ((Number) result.get("p_employee_count")).longValue();

BigDecimal totalSalary =
        (BigDecimal) result.get("p_total_salary");
```

Map keys are the parameter names declared in metadata. Actual value types may depend on the JDBC driver/provider; for numeric types, inspect the returned type rather than casting blindly.

### 4.3. INOUT parameter

With `INOUT`, Java passes an initial value and reads back the value after the procedure executes:

```java
@StoredProcedureParameter(
    mode = ParameterMode.INOUT,
    name = "p_counter",
    type = Integer.class
)
```

In the `EntityManager` API, register the parameter with `ParameterMode.INOUT`, set the initial value with `setParameter`, and retrieve the value with `getOutputParameterValue`. With repository annotations, verify how your provider and Spring Data version map `INOUT` to method signatures; do not assume every `INOUT` combination behaves like an independent `IN` plus `OUT`.

### 4.4. REF_CURSOR and ResultSet

Some databases support returning reference cursors. JPA metadata can declare:

```java
@StoredProcedureParameter(
    mode = ParameterMode.REF_CURSOR,
    name = "p_result",
    type = void.class
)
```

`REF_CURSOR` depends heavily on the database, JDBC driver, and JPA provider. PostgreSQL, Oracle, and other databases have their own cursor rules; do not assume one configuration works across all DBMSs.

Spring Data JPA notes that if a procedure returns a `ResultSet`, `OUT` parameters may be ignored when a method only has a single return type. To retrieve multiple `OUT` parameters, named procedure metadata is required and the method may need to return a `Map` as supported. When multiple result sets or complex DTO mappings are needed, use `StoredProcedureQuery` or a custom repository to control result reading.

## 5. Calling procedures with StoredProcedureQuery

When you need control over parameter registration, result sets, or processing order, use `EntityManager` directly:

```java
@Repository
public class EmployeeProcedureDao {

    @PersistenceContext
    private EntityManager entityManager;

    public BigDecimal raiseSalary(
            Long employeeId,
            BigDecimal increment
    ) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery("raise_salary");

        query.registerStoredProcedureParameter(
                "p_employee_id",
                Long.class,
                ParameterMode.IN
        );
        query.registerStoredProcedureParameter(
                "p_increment",
                BigDecimal.class,
                ParameterMode.IN
        );
        query.registerStoredProcedureParameter(
                "p_new_salary",
                BigDecimal.class,
                ParameterMode.OUT
        );

        query.setParameter("p_employee_id", employeeId);
        query.setParameter("p_increment", increment);

        query.execute();

        return (BigDecimal) query.getOutputParameterValue(
                "p_new_salary"
        );
    }
}
```

Execution steps:

1. Create a `StoredProcedureQuery` with the database procedure name.
2. Register each parameter: name or position, Java type, and `ParameterMode`.
3. Assign values for `IN`/`INOUT` parameters.
4. Call `execute()`.
5. Retrieve `OUT` values after execution and process result sets if present.

Parameters can be registered by position:

```java
query.registerStoredProcedureParameter(
        1, Long.class, ParameterMode.IN
);
```

Parameter names and positions must match the procedure metadata and provider/driver support. When a database or driver only handles positional parameters, declaration order must match the procedure signature exactly.

### 5.1. Procedures returning a ResultSet

If a procedure returns a result set, the API can read results after `execute`:

```java
boolean hasResultSet = query.execute();

if (hasResultSet) {
    List<?> rows = query.getResultList();
}
```

For procedures returning multiple results, you may need `hasMoreResults()`, `getUpdateCount()`, and operations to retrieve subsequent results per the Jakarta Persistence/provider contract. The ordering among `ResultSet`, update counts, and `OUT` parameters should be tested against the actual driver.

To map a result set to an entity or DTO, declare an appropriate result class/result set mapping in `createStoredProcedureQuery` or named procedure metadata. Column counts, aliases, and SQL types must match the declared mapping.

## 6. Transaction boundaries when calling procedures

Procedures can read and write data. For write operations, invoke them inside a Spring-managed transaction:

```java
@Service
public class PayrollService {

    private final EmployeeProcedureDao procedureDao;

    public PayrollService(EmployeeProcedureDao procedureDao) {
        this.procedureDao = procedureDao;
    }

    @Transactional
    public BigDecimal increaseSalary(
            Long employeeId,
            BigDecimal increment
    ) {
        return procedureDao.raiseSalary(employeeId, increment);
    }
}
```

Placing the transaction boundary at the service layer allows the procedure to participate in the same unit of work as other JPA operations in the method, provided they use the same transaction manager and transactional resource.

For example, a business operation might:

1. Check permissions and input data.
2. Read required information via repositories.
3. Call a procedure that updates multiple tables.
4. Write audit or related data via JPA.
5. Commit when the entire operation succeeds.

If the procedure fails and an exception escapes the transactional method, Spring can roll back the transaction according to rollback rules. By default, Spring rolls back on `RuntimeException` and `Error`; checked exceptions do not trigger automatic rollback unless `rollbackFor` or equivalent configuration is specified.

### 6.1. Repository query methods do not create transactions in every situation

CRUD methods inherited from a repository have default transaction configurations. For custom-declared query methods, do not rely on an assumption that every method opens a transaction automatically.

Placing `@Transactional` at the service boundary is usually easier to manage because it encompasses the entire business operation, including procedure calls and related JPA work.

Do not open a new transaction solely to call a procedure if the business operation requires the procedure and JPA operations to commit/roll back together. `Propagation.REQUIRES_NEW` starts a separate transaction and can cause the procedure to commit independently of the outer transaction.

### 6.2. Do procedures issue COMMIT or ROLLBACK themselves?

Transaction rules inside procedures depend on the DBMS. Some databases allow transaction control inside stored procedures under certain conditions; others restrict or forbid commits inside a caller-managed transaction.

If a procedure commits midway, Spring's rollback cannot undo the committed work. The business operation is then no longer atomic as intended by the application.

Safe guidelines for most Spring applications:

- Let Spring manage the transaction boundary.
- Avoid `COMMIT`/`ROLLBACK` inside procedures called from application transactions.
- Do not assume a procedure runs in an independent transaction.
- Verify transaction control rules for the specific database.
- If autonomous transactions or separate commits are required, design them explicitly as vendor-specific behavior and test failure/recovery separately.

## 7. Persistence context can become stale after a procedure

The JPA persistence context tracks loaded entities. If a procedure directly `UPDATE`s or `DELETE`s rows, JPA does not automatically synchronize the state of managed entities with changes made by the procedure.

Example:

```java
Employee employee = employeeRepository.findById(id).orElseThrow();

employeeProcedureDao.raiseSalary(id, new BigDecimal("100.00"));

// employee.getSalary() may still hold the old in-memory value.
```

The database has updated the salary, but the `Employee` object in the persistence context may still hold the pre-procedure value.

### 7.1. Flushing before calling a procedure

If there are entity changes not yet written to the database prior to calling the procedure, call:

```java
entityManager.flush();
```

to force pending changes to synchronize before the procedure executes. This makes execution order clearer, especially when the procedure reads rows recently changed within the same transaction.

### 7.2. Refreshing or clearing after a procedure

If you need to continue using a specific entity, you can refresh it:

```java
entityManager.refresh(employee);
```

If the procedure updates many entities or rows and the application does not know all affected objects, you can clear the persistence context:

```java
entityManager.clear();
```

`clear()` detaches all managed entities. Subsequent reads will fetch fresh data from the database. However, clearing before flushing can discard unsynchronized changes; therefore, usually flush before the procedure and only clear after the procedure succeeds.

Do not call `clear()` mechanically if the service still needs to continue updating previously loaded entities. In that case, refresh the specific entities or redesign the persistence context boundaries.

## 8. Rollback and handling procedure errors

A procedure can fail due to:

- Unique, foreign key, check, or NOT NULL constraint violations.
- Missing data.
- Deadlocks or lock timeouts.
- Wrong parameter types or counts.
- Missing procedure or lack of `EXECUTE` privilege.
- Syntax errors or errors in SQL logic.
- Timeouts, lost connections, or transaction errors.

When a database error escapes the JPA provider, Spring can translate the error into Spring DAO's exception hierarchy, typically under `DataAccessException`. Examples include:

| Error category | Spring exceptions you may encounter |
|---|---|
| Constraint violation | `DataIntegrityViolationException` |
| Invalid SQL syntax or object | `BadSqlGrammarException` or corresponding data access exception |
| Unable to acquire lock | `CannotAcquireLockException` or related exception |
| Timeout | `QueryTimeoutException` or corresponding data access exception |
| Other persistence/provider errors | `JpaSystemException` or another specific `DataAccessException` |

Exact mapping depends on SQLState, vendor error code, provider, and exception translator. Do not write code that relies unconditionally on a single subclass across all databases.

### 8.1. Do not swallow exceptions inside a transaction

Dangerous example:

```java
@Transactional
public void updateSalary(Long id, BigDecimal increment) {
    try {
        repository.raiseSalary(id, increment);
    } catch (DataAccessException ex) {
        log.error("Procedure failed", ex);
        // Swallows the error and returns normally.
    }
}
```

If an exception is caught and not rethrown, Spring may treat the transactional method as having completed normally. The database or transaction manager might already have marked the transaction rollback-only, but the service should not rely on that behavior accidentally.

If an error is unrecoverable, rethrow the exception or translate it into a domain runtime exception:

```java
@Transactional
public void updateSalary(Long id, BigDecimal increment) {
    try {
        repository.raiseSalary(id, increment);
    } catch (DataAccessException ex) {
        throw new SalaryUpdateException(
                "Unable to update employee salary",
                ex
        );
    }
}
```

`SalaryUpdateException` should extend `RuntimeException` to trigger rollback by default. If using a checked exception, declare `@Transactional(rollbackFor = ...)` appropriately.

### 8.2. Business error codes returned by a procedure

Not every procedure raises a SQL exception when a business condition fails. A procedure may return:

- `status_code`: result code.
- `status_message`: message.
- `affected_count`: affected row count.

If a procedure returns `status_code = 0` for success and `status_code = 10` for record not found, Spring does not automatically interpret code `10` as a transaction error. The service must interpret the result:

```java
ProcedureResult result = repository.runBusinessProcedure(...);

if (result.statusCode() != 0) {
    throw new BusinessProcedureException(result.statusMessage());
}
```

When a runtime exception escapes the transactional method, Spring can roll back. If the service merely returns the failure result to a controller without throwing an error or marking rollback-only, the transaction may commit changes the procedure already performed before returning the status. Define the procedure contract clearly: does a failure status guarantee no writes occurred, or does the caller need to roll back?

### 8.3. Do not parse database error messages as a business contract

Error messages and vendor error codes can change across versions, locales, or providers. Avoid writing business logic based on message strings such as `duplicate key value violates unique constraint`.

Prefer:

- Unique/check/foreign key constraints in the database.
- `OUT` status codes with a clear contract if the procedure is designed that way.
- SQLState/vendor codes when classifying technical errors, tested per DBMS.
- Translating exceptions into domain exceptions at the service boundary.
- Preserving the underlying cause for logging and diagnostics.

## 9. Deadlocks, lock timeouts, and retries

Procedures can update multiple tables and acquire locks in their own order. If two transactions invoke procedures in different orders, deadlocks can occur.

Example:

- Transaction A locks Account 1 and then needs Account 2.
- Transaction B locks Account 2 and then needs Account 1.
- The database detects the wait cycle and aborts one transaction.

To reduce the risk:

- Standardize the order of updating/locking tables and rows.
- Keep transactions short.
- Add indexes for conditions locating rows to update.
- Avoid network calls or slow operations while holding locks.
- Configure timeouts on the transaction manager/database appropriately.
- Record deadlocks and lock timeouts for monitoring.

### 9.1. Retries must be intentional

Only retry identified transient errors, such as deadlock victims or serialization failures depending on the DBMS. Do not retry every `DataAccessException`, because permission errors, wrong parameters, or missing procedures will not resolve on their own.

When retrying a transaction, re-execute the entire transaction in a fresh boundary. Never continue using a transaction already marked rollback-only.

Procedures that write data require idempotency if clients might resend requests after timeouts without knowing whether the database committed. Use a unique request ID, idempotency table, or unique constraint to prevent duplicate execution. Never rely solely on client-side timeouts to conclude a procedure did not run.

## 10. Database-specific rules

The same procedure concept may be implemented differently across DBMSs.

| Aspect | What to verify |
|---|---|
| Creating procedures | `CREATE PROCEDURE`, body delimiters, block syntax, and replace/alter differ |
| Names/schemas | Schema rules, catalogs, quoted identifiers, and case sensitivity |
| Parameters | Named/positional parameters, ordering, `INOUT`/`OUT`, and default values |
| ResultSet/cursor | `REF_CURSOR`, multiple result sets, and result retrieval order |
| Transactions | Whether `COMMIT`/`ROLLBACK` is allowed inside procedures; autonomous transactions |
| Exceptions | `raise`/`throw` syntax, SQLState, vendor codes, and rollback behavior |
| Data types | `NUMERIC`, boolean, date/time, UUID, JSON, and proprietary types |
| Execution privileges | `EXECUTE` grants, owner/definer, invoker rights, and schema search path |
| Timeouts/locks | Setting statement timeout, lock timeout, and handling cancellation |
| Migrations | Versioning syntax, replacing procedures, and DDL rollbacks |

Some differences to remember:

- PostgreSQL uses PL/pgSQL and distinguishes procedures from functions; procedures are invoked with `CALL`, while functions are typically used in `SELECT` expressions.
- MySQL has delimiter rules when creating routines in client scripts, along with its own `IN`/`OUT`/`INOUT` syntax.
- SQL Server uses T-SQL, `OUTPUT` parameters, and `TRY`/`CATCH`, `THROW` mechanisms.
- Oracle uses PL/SQL, procedures/packages, `OUT` parameters, and `REF CURSOR` according to Oracle/JDBC rules.

This is guidance on what to check, not a complete DDL guide for each DBMS. Exact syntax must be taken from the documentation for the database version you deploy.

### 10.1. Procedures and functions are not the same

A procedure is typically invoked as an action via `CALL` or `StoredProcedureQuery`. A function typically returns a value used in a SQL expression, such as `SELECT calculate_tax(?)`.

How functions are called via JPA depends on the DBMS and may require native queries or separate APIs. Do not arbitrarily replace `@Procedure` with `@Query` without verifying syntax and result types.

### 10.2. Named parameters are not guaranteed portable

Jakarta Persistence allows registering parameters by name or position, but the provider must translate those declarations down to JDBC/database calls. Some drivers/providers may require positional parameters or process `OUT` parameters in signature order.

Therefore:

- Cross-check parameter order against the procedure definition.
- Test both `IN` and `OUT` with the production driver.
- Do not assume `@Param` names always translate to database named-argument syntax.
- Verify schema qualification and `EXECUTE` privileges of the application user.

## 11. Testing procedures with a production-compatible database

Because stored procedures depend on the DBMS, H2 or embedded databases cannot always emulate production behavior accurately. If the application deploys PostgreSQL, MySQL, SQL Server, or Oracle, use Testcontainers or an integration test environment running the same database type.

Repository test example:

```java
@DataJpaTest
class EmployeeProcedureRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void procedureUpdatesSalaryAndReturnsNewValue() {
        Employee employee = repository.saveAndFlush(
                new Employee(
                        "An Nguyen",
                        new BigDecimal("1000.00")
                )
        );

        BigDecimal result = repository.raiseSalary(
                employee.getId(),
                new BigDecimal("100.00")
        );

        entityManager.clear();

        Employee reloaded = repository.findById(employee.getId())
                .orElseThrow();

        assertThat(result).isEqualByComparingTo("1100.00");
        assertThat(reloaded.getSalary())
                .isEqualByComparingTo("1100.00");
    }
}
```

The test assumes `Employee` has an appropriate constructor and getters, the repository has a `raiseSalary` method, the procedure has been created by migrations in the test database, and the test database supports the corresponding procedure syntax. `@DataJpaTest` normally runs inside a transaction and rolls back after the test; `clear()` ensures the subsequent read fetches from the database rather than returning the entity cached in the persistence context.

Additional scenarios to test:

- Procedure succeeding with boundary values and allowed nulls.
- Non-existent ID and corresponding error contract.
- `OUT`/`INOUT` returning the right types and values.
- Multiple `OUT` parameters mapped to the expected keys.
- `ResultSet`/`REF_CURSOR` if the use case uses cursors.
- Constraint violations and exception translation.
- Rollback when the procedure raises an error midway.
- Whether failed business status codes roll back properly.
- Persistence context after a procedure not returning stale data.
- Deadlocks/timeouts and retries if required in practice.
- `EXECUTE` privileges and schema of the deployment database user.

Do not use H2 tests as evidence that PostgreSQL/Oracle/MySQL procedures behave like production. Tests must run real migrations and use real JDBC drivers.

## 12. Logging and error observability

When a procedure fails, logs should contain enough information to diagnose the root cause without exposing sensitive data.

What to log:

- Normalized business or procedure name.
- Correlation/request ID.
- Diagnostic entity/business key if permitted.
- Execution duration and transaction outcome.
- Exception type, SQLState, or vendor code when available.
- Database/schema/version and application version in telemetry.

Avoid logging all `IN` parameters if they contain salaries, personal info, tokens, or financial data. Mask or omit sensitive data according to logging policies.

You can track procedure duration, call counts, errors by category, timeouts, deadlocks, and retries. Do not only count total exceptions; separating technical errors from business errors helps operations teams know whether to inspect the database, data, or request.

## 13. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| Procedure does not exist | Confused JPA name with DB name or wrong schema | Check `name`/`procedureName`, schema, and migrations |
| Wrong parameter count | Metadata differs from procedure signature | Cross-check `IN`/`OUT`/`INOUT` and parameter order |
| OUT parameter always null | Wrong mode, name, type, or driver mapping | Verify `OUT` registration and read results after `execute` |
| Method returns wrong numeric type | JDBC driver returns a different `Number` type than expected | Inspect runtime type and convert safely |
| Unable to retrieve ResultSet | Procedure/cursor unsupported by provider as configured | Check `REF_CURSOR`, result mapping, and DBMS |
| Exception occurs yet data still changed | Procedure self-committed or error converted to status and ignored | Check transaction control and error contract |
| Spring does not roll back | Exception caught/swallowed or checked exception lacks `rollbackFor` | Rethrow runtime exception or configure rollback |
| Entity returns stale data | Procedure DML did not sync persistence context | Flush beforehand; refresh or clear afterward |
| H2 test passes but production fails | Different DDL, driver, cursor, type, or transaction semantics | Test with the exact DBMS via Testcontainers |
| Permission denied | Application user lacks `EXECUTE` or schema access | Grant least-privilege permissions per deployment |
| Deadlock/timeout | Lock order, long transactions, or missing indexes | Standardize lock order, shorten transactions, and inspect plan |
| Procedure runs twice | Retries/duplicate requests without idempotency | Use a request key or unique constraint |
| Errors misclassified | Relying on message strings or assuming exception subclasses | Use `DataAccessException` and tested SQLState/vendor codes |

## 14. Pre-production checklist for procedures

- [ ] Procedure is managed by versioned migrations.
- [ ] JPA metadata properly distinguishes logical name from database name.
- [ ] Parameter modes, order, data types, and nullability match the signature.
- [ ] `OUT`, `INOUT`, and `REF_CURSOR` are tested with the actual JDBC driver.
- [ ] Transaction boundaries are placed at the service layer.
- [ ] Procedure does not self-commit/roll back in violation of desired atomicity.
- [ ] Rollback behavior is defined for both SQL exceptions and business status codes.
- [ ] Persistence context is flushed/refreshed/cleared appropriately around procedure DML.
- [ ] Deadlocks, lock timeouts, statement timeouts, and retries have clear policies.
- [ ] Retryable requests are protected by idempotency where needed.
- [ ] Database user has minimal `EXECUTE` privileges and proper schema access.
- [ ] Exceptions are translated into domain errors while preserving causes.
- [ ] Logs do not leak sensitive parameters.
- [ ] Integration tests run on the exact target DBMS/version for production.
- [ ] Migrations and procedures are compatible with running application versions during rollout.

## 15. References

- [Spring Data JPA — Stored Procedures](https://docs.spring.io/spring-data/jpa/reference/jpa/stored-procedures.html)
- [Jakarta Persistence — StoredProcedureQuery API](https://jakarta.ee/specifications/persistence/4.0/apidocs/jakarta.persistence/jakarta/persistence/storedprocedurequery)
- [Jakarta Persistence — NamedStoredProcedureQuery](https://jakarta.ee/specifications/platform/9/apidocs/jakarta/persistence/namedstoredprocedurequery)

## Conclusion

Spring Data JPA invokes procedures via `@Procedure`; Jakarta Persistence offers finer control with `StoredProcedureQuery`. `@NamedStoredProcedureQuery` metadata describes how to invoke a procedure that already exists in the database, while migrations are responsible for deploying the actual DDL.

For procedures that write data, place calls inside Spring-managed transactions and verify whether the procedure self-commits. Database exceptions are typically translated to `DataAccessException`; to preserve default rollbacks, do not swallow runtime exceptions. If a procedure returns status codes instead of throwing errors, the service must interpret the status and decide on rollback. After bulk DML, flush beforehand and refresh/clear the persistence context appropriately to avoid stale entities.

DDL syntax, parameters, cursors, transaction control, and exception codes depend on the DBMS, JDBC driver, and JPA provider. Manage procedures via migrations, test against the real production database, and document vendor-specific rules in the integration contract.