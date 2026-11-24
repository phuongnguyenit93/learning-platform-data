# Transactions, Access Privileges, and Vendor Lock-In of Stored Procedures in Spring JDBC

## 1. Goals and context

A Spring application can invoke a stored procedure using `SimpleJdbcCall`, `JdbcTemplate`, or `CallableStatement`. Calling the right syntax alone does not prove data is written safely: a procedure executes inside the **database**, can modify multiple tables, throw or catch errors, run under dedicated privileges, and obey each RDBMS's semantics.

Consider transferring 25 units from account A to B. The service calls a procedure to debit A and credit B, then Java writes an audit log entry. If writing the audit log fails, does the balance transfer roll back? The answer depends on **Spring's transaction manager, the JDBC connection, the procedure body, and the DBMS rules**. The `@Transactional` annotation alone is not enough to conclude.

This lesson clarifies three groups of decisions:

- **Transactions:** who decides `COMMIT`/`ROLLBACK`, conditions for the procedure and Java to share one transaction, behavior when errors occur or are swallowed, and cases where a procedure terminates a transaction itself.
- **Access privileges:** `EXECUTE` privileges, access to internal tables, invoker/definer models, schema ownership, least-privilege restrictions, and privilege escalation risks.
- **Vendor lock-in:** PostgreSQL, MySQL, SQL Server, and Oracle differ in syntax, transaction control, metadata, functions/procedures, security contexts, `OUT` parameters, and how drivers translate JDBC calls.

Goal after this lesson: design procedure call sites compatible with Spring transactions, test rollbacks/privileges, clearly distinguish what Spring abstracts from what remains tied to the DBMS, and know how to diagnose production issues.

## 2. Spring manages the transaction outside, the DBMS executes inside

```text
Service method / TransactionTemplate
                |
                v
Spring PlatformTransactionManager
                |
                v
DataSource -> active transaction's connection
                |
                v
SimpleJdbcCall / JdbcTemplate / CallableStatement
                |
                v
Database CALL -> internal SQL -> trigger/lock/exception/security
                |
                v
Connection commit/rollback per actual boundary
```

When using `DataSourceTransactionManager` with a JDBC `DataSource`, Spring binds the transaction's connection to the execution thread. `JdbcTemplate` and `SimpleJdbcCall` obtain the matching connection through Spring JDBC infrastructure, allowing multiple SQL statements to run within **the same physical transaction**.

For this to work properly:

1. The transaction manager must manage the exact `DataSource` used to call the procedure; connections opened from another source do not automatically participate.
2. `@Transactional` must be active (for example, through a Spring proxy). Calling `this.someTransactionalMethod()` within the same bean in proxy mode typically bypasses the target method's transaction advice.
3. Operations must share the same transaction context; a new thread, manually acquired connection, or external service does not automatically share the open JDBC transaction.
4. The procedure body must respect the expected transaction contract. If the procedure commits on its own, uses an autonomous transaction, or runs DDL with implicit commit, a Spring rollback may not undo everything.
5. Spring and the database must align on isolation, timeouts, locks, error states, and retry strategies.

**Distinguish two concepts:** Spring decides when to request commit/rollback on the connection it manages; the DBMS decides whether `CALL` is allowed to control transactions itself, which statements roll back, and which statements have effects outside the transaction.

## 3. Procedure calling patterns in Spring do not start transactions on their own

### 3.1. `SimpleJdbcCall` and the parameter contract

```java
SimpleJdbcCall transfer = new SimpleJdbcCall(jdbcTemplate)
        .withSchemaName("finance")
        .withProcedureName("transfer")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
            new SqlParameter("p_from", Types.INTEGER),
            new SqlParameter("p_to", Types.INTEGER),
            new SqlParameter("p_amount", Types.INTEGER)
        );

Map<String, Object> output = transfer.execute(Map.of(
    "p_from", 1,
    "p_to", 2,
    "p_amount", 25
));
```

This snippet illustrates code **inside a class that already has `jdbcTemplate` and the required imports**; it is not a standalone program. `SimpleJdbcCall` configures the routine name, schema, and `IN`/`OUT` parameters, returning a Map containing `OUT` values (if any). `withoutProcedureColumnMetaDataAccess()` avoids relying on driver parameter metadata; all parameters must be accurately declared via `declareParameters(...)`. Initialize/compile the configuration once and reuse it afterwards.

A `SimpleJdbcCall` object does not open a transaction on behalf of the service. It joins an active transaction when the connection is acquired properly.

### 3.2. `JdbcTemplate` with `CallableStatement`

```java
jdbcTemplate.execute((Connection con) -> {
    try (CallableStatement cs =
                 con.prepareCall("{call finance.transfer(?, ?, ?)}")) {
        cs.setInt(1, 1);
        cs.setInt(2, 2);
        cs.setInt(3, 25);
        cs.execute();
    }
    return null;
});
```

This is a snippet inside a method that already has `jdbcTemplate`; import `java.sql.Connection` and `java.sql.CallableStatement`. The connection provided by `JdbcTemplate` can belong to Spring's transaction. Only close your `CallableStatement`; **never call `con.commit()`, `con.rollback()`, or `con.close()`** on a Spring-managed connection.

JDBC escape syntax `{call ...}` must be translated by the driver into database SQL. For instance, **pgJDBC defaults to `escapeSyntaxCallMode=select`** for function-call compatibility; when calling a PostgreSQL procedure, you may need `escapeSyntaxCallMode=callIfNoReturn` or `call`. PostgreSQL's `CALL ...` SQL statement differs from `SELECT ...` function calls. Do not assume every DBMS understands the same native syntax.

## 4. When do changes inside a procedure roll back with the service?

If a procedure only runs DML statements and **does not commit/roll back itself**, the typical rules are:

| Situation | Outcome to understand |
|---|---|
| Service has an active `@Transactional`; procedure uses the same connection | Changes normally participate in the service's transaction. |
| Service calls the procedure then throws an unchecked `RuntimeException` outside the transaction boundary | Spring rolls back by default; the DBMS undoes uncommitted DML in that transaction. |
| Procedure causes a `SQLException`; `JdbcTemplate` throws `DataAccessException` | This is an unchecked exception; Spring rolls back by default if the error crosses the transaction interceptor. |
| Procedure catches the error itself and returns a normal status code | Spring does not know it is a business failure; the transaction may commit if the service does not handle it. |
| Java catches `DataAccessException` and returns normally | Spring may commit if the transaction is still valid and not marked rollback-only. Some DBMSs like PostgreSQL put the transaction into an aborted state requiring rollback. |
| Procedure executes `COMMIT`, uses an autonomous transaction, or runs DDL with implicit commit | You cannot assume an outer rollback will undo those effects. |
| Procedure called outside a Spring transaction on an auto-commit connection | Success is normally committed per auto-commit/driver rules; do not assume one transaction spans multiple calls. |

### 4.1. Defaults of `@Transactional` and checked exceptions

Spring declarative transactions roll back by default on `RuntimeException`/`Error`; ordinary checked exceptions do not automatically trigger rollback. If business logic uses checked exceptions, declare the rule explicitly:

```java
@Transactional(rollbackFor = BusinessRuleException.class)
public void performBusinessOperation() throws BusinessRuleException {
    // Call the procedure and update other tables in the same transaction.
}
```

This is illustrative code and does not compile standalone: `BusinessRuleException` and the method body must be implemented in your project. Distinguish errors raised as **exceptions** from errors returned as an `OUT` status code. If a procedure returns `status = FAILED` while the service completes normally, Spring will not automatically roll back.

In proxy-based Spring, putting `@Transactional` on a `public` method called from outside the bean is the standard usage; internal self-invocation does not trigger new transaction advice. When multiple transaction managers exist, select the right manager for that JDBC `DataSource`.

### 4.2. Propagation and savepoints

- `REQUIRED` joins an existing transaction or starts a new one if none exists.
- `REQUIRES_NEW` creates an independent physical transaction; work committed in this transaction can persist even if the outer transaction rolls back. Watch connection pool capacity.
- `NESTED` can use JDBC savepoints with `DataSourceTransactionManager` and a supporting driver to roll back partially within the same physical transaction.

All three are **Spring** policies; they do not force a procedure to obey if the database engine lets the procedure manage its own transactions. Do not abuse `REQUIRES_NEW` to "fix rollback bugs" without understanding the impact on atomicity.

## 5. Java 17+ example with PostgreSQL: verifiable commit and rollback

This standalone example uses PostgreSQL 16, Spring JDBC 6.2.12, and pgJDBC 42.7.7. It creates a randomized test schema, an accounts table, an audit table, and a `transfer` procedure; two runs demonstrate rollback when Java throws an error and commit when finishing normally. The procedure omits `COMMIT`/`ROLLBACK` so Spring controls the transaction.

### 5.1. Project layout and `pom.xml`

```text
procedure-tx-demo/
├── pom.xml
└── src/main/java/demo/ProcedureTransactionDemo.java
```

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>procedure-tx-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>42.7.7</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ProcedureTransactionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Source code

```java
package demo;

import java.sql.Types;
import java.util.Map;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public final class ProcedureTransactionDemo {

    public static void main(String[] args) {
        String url = System.getenv().getOrDefault(
            "DB_URL",
            "jdbc:postgresql://localhost:54329/lesson"
                + "?escapeSyntaxCallMode=callIfNoReturn"
        );
        String username = System.getenv().getOrDefault("DB_USER", "postgres");
        String password = System.getenv().getOrDefault(
            "DB_PASSWORD", "postgres"
        );

        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl(url);
        dataSource.setUsername(username);
        dataSource.setPassword(password);

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        TransactionTemplate transaction = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );

        // Work only inside the newly created demo schema.
        String schema = "learn_" + UUID.randomUUID().toString()
                .replace("-", "").substring(0, 12);

        jdbc.execute("CREATE SCHEMA " + schema);
        try {
            jdbc.execute("""
                CREATE TABLE %s.accounts (
                    id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL CHECK (balance >= 0)
                )
                """.formatted(schema));

            jdbc.execute("""
                CREATE TABLE %s.audit_log (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    note TEXT NOT NULL
                )
                """.formatted(schema));

            jdbc.execute("""
                CREATE PROCEDURE %s.transfer(
                    p_from INTEGER, p_to INTEGER, p_amount INTEGER
                )
                LANGUAGE plpgsql
                AS $proc$
                BEGIN
                    IF p_amount <= 0 OR p_from = p_to THEN
                        RAISE EXCEPTION 'Invalid transfer parameters';
                    END IF;

                    UPDATE %s.accounts
                       SET balance = balance - p_amount
                     WHERE id = p_from AND balance >= p_amount;
                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'Sender missing or insufficient balance';
                    END IF;

                    UPDATE %s.accounts
                       SET balance = balance + p_amount
                     WHERE id = p_to;
                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'Receiver missing';
                    END IF;
                END;
                $proc$
                """.formatted(schema, schema, schema));

            jdbc.update("INSERT INTO " + schema
                    + ".accounts (id, balance) VALUES (1, 100), (2, 100)");

            SimpleJdbcCall call = new SimpleJdbcCall(jdbc)
                .withSchemaName(schema)
                .withProcedureName("transfer")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                    new SqlParameter("p_from", Types.INTEGER),
                    new SqlParameter("p_to", Types.INTEGER),
                    new SqlParameter("p_amount", Types.INTEGER)
                );
            call.compile();

            // Attempt 1: procedure updated data, but Java throws an error.
            try {
                transaction.execute(status -> {
                    call.execute(Map.of(
                        "p_from", 1, "p_to", 2, "p_amount", 30
                    ));
                    jdbc.update("INSERT INTO " + schema
                        + ".audit_log(note) VALUES (?)", "will rollback");
                    throw new IllegalStateException("simulate rollback");
                });
                throw new AssertionError("Expected demo exception");
            } catch (IllegalStateException ex) {
                if (!"simulate rollback".equals(ex.getMessage())) {
                    throw ex;
                }
            }
            printState(jdbc, schema, "After rollback");

            // Attempt 2: completes normally => commit.
            transaction.execute(status -> {
                call.execute(Map.of(
                    "p_from", 1, "p_to", 2, "p_amount", 25
                ));
                jdbc.update("INSERT INTO " + schema
                    + ".audit_log(note) VALUES (?)", "committed");
                return null;
            });
            printState(jdbc, schema, "After commit");
        } finally {
            jdbc.execute("DROP SCHEMA " + schema + " CASCADE");
        }
    }

    private static void printState(
            JdbcTemplate jdbc, String schema, String label) {
        Integer from = jdbc.queryForObject(
            "SELECT balance FROM " + schema + ".accounts WHERE id = 1",
            Integer.class
        );
        Integer to = jdbc.queryForObject(
            "SELECT balance FROM " + schema + ".accounts WHERE id = 2",
            Integer.class
        );
        Integer audit = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + schema + ".audit_log",
            Integer.class
        );
        System.out.printf("%s: from=%d, to=%d, audit=%d%n",
                          label, from, to, audit);
    }
}
```

This program is a standalone runnable example against an **existing PostgreSQL test server**. `DriverManagerDataSource` suits small demos; production projects should use a proper connection pool.

### 5.3. Running and explaining the output

If Docker is available, start a test PostgreSQL instance on a dedicated port:

```bash
docker run --rm -d --name jdbc-proc-lab \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=lesson \
  -p 54329:5432 postgres:16

# Check status; run again after database finishes starting:
docker exec jdbc-proc-lab pg_isready -U postgres -d lesson

# In the directory containing pom.xml and src/:
mvn -q compile exec:java

# When finished with the lab:
docker stop jdbc-proc-lab
```

**Expected** Java output against a freshly started PostgreSQL instance:

```text
After rollback: from=100, to=100, audit=0
After commit: from=75, to=125, audit=1
```

Explanation: on the first run, the procedure transfers 30 and then an audit row is inserted, but the callback throws an unchecked exception; `TransactionTemplate` rolls back both the procedure's DML and the audit row. On the second run, 25 is transferred and the audit row succeeds; Spring commits both. This proves rollback by inspecting **database state**, rather than merely checking the return value of `SimpleJdbcCall`.

The schema creation code only uses auto-generated characters `learn_[a-z0-9]`, and drops that demo schema on completion; never point it at a production database. If using an existing test DB, set `DB_URL`, `DB_USER`, and `DB_PASSWORD` via environment variables. Table/schema names in SQL are configured identifiers; business values use bind parameters. Never allow users to supply arbitrary schema names concatenated directly into SQL.

**Accuracy note:** the output above is derived from the program and the described test RDBMS state. To confirm in your own environment, run with the matching PostgreSQL and pgJDBC versions; if the DB is unavailable, lacks schema creation privileges, or has an invalid URL, the program cannot run successfully.

## 6. Procedures that COMMIT/ROLLBACK themselves: each vendor has different rules

### 6.1. PostgreSQL

PostgreSQL has **procedures** called with `CALL`, while functions are normally called with `SELECT`. Procedures can control transactions **in allowed top-level contexts**, yet when `CALL` runs inside a transaction block opened by Spring or a client, the procedure **cannot execute `COMMIT`/`ROLLBACK` to end that transaction**.

In addition, a PostgreSQL procedure declared with `SECURITY DEFINER` or a `SET ...` clause in its definition **cannot perform transaction control**. Other constraints around nested `CALL`/`DO` contexts and exception blocks can also restrict transaction control.

For Spring applications using `@Transactional`, the cleanest choice is usually **not placing `COMMIT`/`ROLLBACK` inside the procedure**; let the service govern the transaction. If a procedure genuinely needs internal commits, design a dedicated top-level call path, configure auto-commit deliberately, and test recovery rather than casually wrapping it in a Spring transaction.

### 6.2. MySQL

MySQL permits stored **procedures** to execute transaction statements such as `COMMIT` in valid contexts; stored **functions** are disallowed from containing statements that cause explicit or implicit commit/rollback. Consequently, a procedure with an internal `COMMIT` can terminate the transaction that a Spring service expects to control. MySQL also has DDL statements that trigger implicit commits.

Do not infer that "calling with `SimpleJdbcCall` is safe with every `@Transactional`": read the procedure body, check the storage engine and version, and verify rollback behavior on the database.

### 6.3. Microsoft SQL Server

T-SQL stored procedures can use `BEGIN TRANSACTION`, `COMMIT TRANSACTION`, `ROLLBACK TRANSACTION`, `TRY...CATCH`, and `THROW`. `@@TRANCOUNT` reflects nesting level, but ordinary nested transactions **are not independent like separate physical transactions**. A `ROLLBACK` without a savepoint name can roll back the entire session's transaction; this directly impacts an outer transaction started by the application.

Also examine `XACT_STATE()` and the `XACT_ABORT` setting when deciding whether execution can continue or must roll back. Never write catch/rollback logic in a procedure without understanding its contract with the caller.

### 6.4. Oracle

In normal PL/SQL, `COMMIT`/`ROLLBACK` inside a procedure can affect the calling session's transaction. Oracle also supports `PRAGMA AUTONOMOUS_TRANSACTION`: a block of code executes in an independent transaction, able to commit audit logs even if the outer transaction rolls back. If business rules demand all-or-nothing atomicity, carefully inspect autonomous routines and off-database side effects.

### 6.5. Comparison table

| DBMS | Typical procedure invocation | Transaction notes |
|---|---|---|
| PostgreSQL | `CALL schema.proc(...)` | Transaction control inside a procedure is only valid in specific contexts; disallowed from `CALL` inside a transaction block. |
| MySQL | `CALL schema.proc(...)` | Procedures can commit/roll back themselves; functions are restricted; DDL can trigger implicit commits. |
| SQL Server | `EXEC schema.proc ...` or JDBC call | Procedures can affect the caller's transaction; watch `@@TRANCOUNT` and `XACT_STATE()`. |
| Oracle | PL/SQL/JDBC call | Procedures can commit; autonomous transactions are independent. |

This is a scoped summary; before deploying, consult the documentation for your **exact DBMS + JDBC driver versions**.

## 7. Access privileges: who can call and who has privileges on the data?

There are typically two roles:

- **Invoker/caller:** the database account the Spring application uses to call the procedure.
- **Definer/owner:** the account/role that owns or defines the routine, which may act as the execution security context depending on the DBMS.

Check three separate privilege layers:

1. **Namespace/schema:** for example, `USAGE` privilege on the schema in PostgreSQL.
2. **Routine execution privilege:** `EXECUTE` on the procedure/function.
3. **Privileges on underlying tables, views, sequences, and nested routines:** depends on the definer/invoker model, ownership chaining, roles, and dynamic SQL.

Having `EXECUTE` does not automatically guarantee the procedure has access to every table, nor is it a reason to grant overly broad direct privileges to the runtime account.

### 7.1. PostgreSQL: granting least-privilege access

Assume schema `finance`, role `app_runtime`, and procedure `finance.transfer(integer, integer, integer)` already exist. A DBA can execute:

```sql
BEGIN;

REVOKE ALL ON PROCEDURE finance.transfer(integer, integer, integer)
    FROM PUBLIC;

GRANT USAGE ON SCHEMA finance TO app_runtime;

GRANT EXECUTE ON PROCEDURE finance.transfer(integer, integer, integer)
    TO app_runtime;

COMMIT;
```

This is an **illustrative privilege management snippet**, not a complete script to create roles/routines. PostgreSQL may grant `EXECUTE` to `PUBLIC` by default on new routines, so review permissions proactively. The `(integer, integer, integer)` signature disambiguates overloads; be careful not to grant privileges on the wrong same-named routine with different parameter types.

If the procedure runs as `SECURITY INVOKER` (usually the default), `app_runtime` also needs the required privileges on underlying objects. If the procedure runs as `SECURITY DEFINER`, internal access can use the owner's privileges; this lets you restrict direct table privileges for the app, but requires stricter security review of the procedure body.

### 7.2. Invoker vs. definer by vendor

| DBMS | Security context model | What to check |
|---|---|---|
| PostgreSQL | `SECURITY INVOKER` / `SECURITY DEFINER` | Owner privileges, `search_path`, schema/`EXECUTE` grants; definer procedures have restricted transaction control. |
| MySQL | `SQL SECURITY DEFINER` / `SQL SECURITY INVOKER` with `DEFINER` account | Default is usually `DEFINER`; caller needs `EXECUTE`, internal privileges follow context; definer account and active roles have specific rules. |
| SQL Server | `EXECUTE AS CALLER/OWNER/SELF`, ownership chaining, module signing | `EXECUTE` privileges and ownership chains; dynamic SQL may require separate permissions beyond static DML. |
| Oracle | `AUTHID DEFINER` / `AUTHID CURRENT_USER` | Definer rights by default; invoker rights use caller context; direct grants vs. roles must be checked carefully. |

### 7.3. Elevated privileges and dynamic SQL

A routine running with definer privileges can allow a caller to perform actions the caller is not permitted to perform directly. If the procedure takes input and concatenates it into dynamic SQL—table names, conditions, or paths from untrusted input—there is a risk of SQL injection or privilege abuse.

Rules:

- Bind data using typed parameters. **Never** concatenate input arbitrarily into dynamic SQL.
- If dynamic SQL with dynamic table/column names is truly unavoidable, use the DBMS's proper identifier quoting mechanism and an allowlist; `?` placeholders cannot bind table/column names.
- With PostgreSQL `SECURITY DEFINER`, pin `search_path` to trusted schemas and handle `pg_temp` safely; avoid schemas where untrusted users can create objects.
- Grant `EXECUTE` only on the exact routines needed; separate migration/schema-owner roles from runtime roles.
- Test privileges using the application's actual database account, not solely with a superuser account on a developer machine.

Spring's `withSchemaName(...)` only locates the routine; **it never issues `GRANT`**, enables definer rights, or switches the active role.

## 8. Vendor lock-in of procedures/functions: how far does Spring abstract?

Spring JDBC helps build `CallableStatement`, bind `IN`/`OUT` parameters, map result sets, and translate `SQLException` into `DataAccessException`. It **does not translate a PL/pgSQL body into PL/SQL or T-SQL**, nor does it guarantee identical transaction/privilege semantics across every database.

### 8.1. Syntax, functions, and procedures

- PostgreSQL distinguishes `CALL` for procedures and `SELECT` for functions; with pgJDBC, check `escapeSyntaxCallMode`.
- MySQL has `CREATE PROCEDURE/CREATE FUNCTION`, `CALL`, `IN/OUT/INOUT`, and `SQL SECURITY`.
- SQL Server uses T-SQL `EXEC`, `OUTPUT` parameters, return status, and can return multiple result sets.
- Oracle uses PL/SQL procedures/functions/packages, `REF CURSOR`, and vendor-specific types.

Never take an SQL procedure script written for one vendor and expect it to run unmodified on another.

### 8.2. JDBC metadata and explicit declarations

`SimpleJdbcCall` can rely on JDBC metadata to infer parameter counts, names, and SQL types. However, metadata is not always consistent across drivers/versions, especially with overloads, schemas/catalogs, `REF_CURSOR`, and `OUT` parameters. Explicit declaration example:

```java
SimpleJdbcCall queryTotal = new SimpleJdbcCall(jdbcTemplate)
        .withSchemaName("finance")
        .withProcedureName("read_total")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
            new SqlParameter("p_id", Types.INTEGER),
            new SqlOutParameter("p_total", Types.NUMERIC)
        );
```

This is an **API pattern**, valid only when the schema, procedure name, types, and parameter directions match reality. Requires importing `java.sql.Types`, `SqlParameter`, and `SqlOutParameter`. An `OUT` `NUMERIC` may return `BigDecimal`; do not cast blindly to `int`. Use `SqlInOutParameter` appropriately for `INOUT`.

Engine-specific points to test:

1. `OUT`/`INOUT` parameters can have different names, positions, and registration styles.
2. A function return value differs from a procedure's `OUT` parameter; choose `withFunctionName`/`executeFunction` when actually calling a function.
3. Oracle `REF_CURSOR`, PostgreSQL `refcursor`, and SQL Server/MySQL result sets have different protocols and connection lifecycles.
4. Output `Map` keys can change casing; `JdbcTemplate.setResultsMapCaseInsensitive(true)` can help when appropriate.
5. `SQLState`/error codes, locks, and timeouts differ; `DataAccessException` does not make them completely uniform.
6. Schema/case-sensitivity and routine overloads can create ambiguous calls or invoke the wrong routine.

### 8.3. Example pgJDBC-specific URL option

```text
jdbc:postgresql://localhost:54329/lesson?escapeSyntaxCallMode=callIfNoReturn
```

Per pgJDBC documentation, the default `select` favors function-call compatibility. `callIfNoReturn` translates JDBC escape syntax without a return parameter into `CALL` to invoke a procedure, while calls with a return parameter use the function path. Never copy this option to another vendor's driver without checking.

### 8.4. Isolating dependencies in the data-access layer

```java
public interface TransferGateway {
    void transfer(int fromAccount, int toAccount, int amount);
}
```

This is an illustrative interface; a PostgreSQL adapter can use `SimpleJdbcCall`, while an Oracle adapter can use a different API/SQL. The interface helps confine which parts of the application know procedure names and DBMS quirks. Nevertheless, routine logic, DDL migrations, privileges, and transaction semantics must still be re-tested when switching vendors. Never assume changing the JDBC URL alone is enough.

## 9. Common errors and how to resolve them

| Symptom | Common cause | What to check |
|---|---|---|
| `@Transactional` rolls back, yet procedure data remains | Procedure committed, autonomous transaction, DDL implicit commit, or different connection/transaction. | Routine body, transaction manager, `DataSource`, engine semantics. |
| PostgreSQL reports `invalid transaction termination` | Procedure tried `COMMIT`/`ROLLBACK` inside a transaction block or disallowed context. | Remove commit from routine or redesign as a top-level call. |
| `permission denied` on call | Missing `EXECUTE` or schema privilege, missing role, wrong overload. | Runtime user, signature, schema, grants. |
| Has `EXECUTE`, yet procedure lacks table privileges | Invoker lacks DML privilege, definer lacks privilege, or unexpected security context. | Invoker/definer, owner, and internal object privileges. |
| `OUT` result has wrong key or bind error | Unreliable driver metadata, casing mismatch, wrong `IN`/`OUT`/`INOUT` type. | Driver/version, `declareParameters`, `SqlOutParameter`. |
| PostgreSQL escape call looks for a function instead of a procedure | Driver is using `escapeSyntaxCallMode=select`. | Driver configuration or native `CALL`. |
| Procedure returns "FAIL", yet data committed | Error was caught and the caller completed normally. | Agreed `OUT` status/error contract, rollback rules, and data validation. |
| Lock timeouts, deadlocks, hanging requests | Procedure updates multiple objects with inconsistent lock ordering/isolation. | Lock waits, execution plans, timeouts, and proper retries. |
| Works in local tests, fails in production | Different DBMS/driver version, privileges, schema, collation, or types. | Integration tests using production-equivalent configuration and runtime role. |

Never retry unconditionally when a connection drops mid-call: a network error does not prove the procedure **did not** commit. Design idempotency keys, business unique constraints, reconciliation, or transactional outbox patterns when at-least-once/exactly-once business guarantees are needed. Data sent to email, HTTP endpoints, or external queues is not automatically rolled back by JDBC.

## 10. Integration testing and deployment checklist

A unit test mocking `SimpleJdbcCall` only checks Java mapping—it does not prove database rollback or security context. Essential test cases:

1. **Happy path:** procedure updates the right data, `OUT`/result sets are accurate, transaction commits.
2. **Rollback after `CALL`:** procedure writes data then the service throws an unchecked exception; re-read all affected tables.
3. **Mid-`CALL` failure:** procedure updates partially then hits a constraint violation or `RAISE`; leaves no unexpected changes behind.
4. **Testing with the real runtime role:** account has exact `USAGE`/`EXECUTE` grants, and is denied access to ungranted tables/routines.
5. **Definer/Invoker:** same call with different roles and dynamic SQL/`search_path` cases.
6. **Metadata mismatches:** overloads, `OUT` key casing, SQL types, schema/catalog, driver options.
7. **Transaction control:** test procedures containing transaction statements (if supported by the DBMS) to confirm the exact contract, especially alongside `@Transactional`.
8. **Concurrency:** two concurrent transactions, isolation levels, locks, deadlocks, and retries.
9. **Timeouts/disconnects:** reconcile commit state before retrying; verify off-database side effects.

Before releasing, explicitly document who owns the transaction, whether procedures are allowed to commit, least-privilege grants for the runtime role, vendor/version targets, and recovery procedures for partial failures.

## 11. Self-check knowledge questions

**1.** A `@Transactional` service calls a procedure that modifies two tables, then throws `RuntimeException`. When do both tables roll back?  
**Answer:** when Spring actually manages the same transaction/connection, the procedure does not commit independently, and the DBMS can roll back the associated DML.

**2.** Why can a PostgreSQL procedure containing `COMMIT` fail to run under `TransactionTemplate` like a normal statement?  
**Answer:** because `CALL` is inside a transaction block; PostgreSQL forbids a routine from terminating the transaction in that context.

**3.** The application account has `EXECUTE`, yet the routine still lacks `UPDATE` privilege on a table. Why might that happen?  
**Answer:** the procedure runs with invoker rights, or the definer lacks the needed privilege; inspect context/owner/roles/schemas.

**4.** An Oracle autonomous transaction wrote a log entry and executed `COMMIT`. Does rolling back the outer transaction erase that log entry?  
**Answer:** not automatically; it is an independent transaction.

**5.** A MySQL procedure commits itself, and then the Spring service reports an error. Are all changes guaranteed to roll back?  
**Answer:** no; you must inspect transaction control inside the procedure, auto-commit settings, and DBMS semantics.

**6.** If using `SimpleJdbcCall`, can PL/pgSQL logic be moved verbatim to SQL Server?  
**Answer:** no. Spring helps with the JDBC call, not translating vendor routine languages, privileges, and transaction rules.

**7.** A procedure catches an error, returns output `FAILED`, and throws no exception. Does Spring automatically roll back?  
**Answer:** no. The caller must interpret the output and trigger rollback/error per the business contract.

## References

- Spring Framework — SimpleJdbcCall: https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rollback Rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- PostgreSQL — CALL: https://www.postgresql.org/docs/current/sql-call.html
- PostgreSQL — CREATE PROCEDURE: https://www.postgresql.org/docs/current/sql-createprocedure.html
- PostgreSQL — PL/pgSQL Transaction Management: https://www.postgresql.org/docs/current/plpgsql-transactions.html
- PostgreSQL — SECURITY DEFINER and search_path: https://www.postgresql.org/docs/current/sql-createfunction.html
- pgJDBC — Calling Stored Functions and Procedures: https://jdbc.postgresql.org/documentation/callproc/
- pgJDBC — Driver Settings: https://jdbc.postgresql.org/documentation/use/
- MySQL 8.4 — Stored Procedures and Functions: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- Microsoft SQL Server — EXECUTE AS: https://learn.microsoft.com/en-us/sql/t-sql/statements/execute-as-clause-transact-sql
- Oracle Database — Definer's/Invoker's Rights: https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/definers-rights-and-invokers-rights.html
- Oracle Database — Autonomous Transactions: https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/autonomous-transactions.html
