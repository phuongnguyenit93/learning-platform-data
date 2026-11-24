# Recognizing the `StoredProcedure` Class When Working with Existing Code

## 1. Goal: reading and understanding legacy-style Spring JDBC code

When maintaining a Spring application, you may encounter a Java class extending `StoredProcedure`, a `GenericStoredProcedure` bean, or a repository class calling `execute(...)` and receiving a `Map`. Looking only at the name, it is easy to confuse them with SQL statements, with `SimpleJdbcCall`, or with JPA. This lesson shows how to **accurately recognize `org.springframework.jdbc.object.StoredProcedure` in existing code and trace where its configuration, parameters, calls, and results live**, so you understand its behavior before debugging or considering changes.

The target class to recognize is:

```java
org.springframework.jdbc.object.StoredProcedure
```

This is an **abstract class** in Spring JDBC following the *RDBMS operation object* design pattern: a Java object representing a database stored procedure or stored function call. That class is **not the SQL procedure itself**, nor does it define the SQL routine in the database. It uses Spring JDBC infrastructure to create and execute a JDBC `CallableStatement`.

Inheritance hierarchy:

```text
java.lang.Object
    └── org.springframework.jdbc.object.RdbmsOperation
            └── org.springframework.jdbc.object.SqlCall
                    └── org.springframework.jdbc.object.StoredProcedure
                            └── Project-defined subclass
```

Key points to grasp before reading examples:

- `RdbmsOperation` handles configuring the data source, declaring parameters, and tracking `compile` state.
- `SqlCall` models the procedure/function call, including the `setFunction(true)` option when calling a function.
- `StoredProcedure` provides `execute(...)` methods taking parameters and returning `OUT` results as a `Map<String, Object>`.
- The **subclass** is typically named after the business operation, such as `ReadCustomerProcedure`, defining a strongly typed method like `findCustomerName(long id)` to hide the `Map`.
- `GenericStoredProcedure` is another concrete implementation used when you do not want to write a custom subclass with strongly typed methods.

This is an API you may still encounter in Spring JDBC projects; recognizing existing code **does not mean** you should automatically replace it with a newer API. Parameter, transaction, driver, and data-type behaviors must be verified before making changes.

## 2. Quick recognition signs in source code

A typical class looks like this:

```java
// File: ReadCustomerNameProcedure.java
import java.sql.Types;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.object.StoredProcedure;

public final class ReadCustomerNameProcedure extends StoredProcedure {

    public ReadCustomerNameProcedure(DataSource dataSource) {
        // "read_customer_name" is the routine name in the database.
        super(dataSource, "read_customer_name");

        // IN/OUT directions and declaration order reflect the routine signature.
        declareParameter(new SqlParameter("in_customer_id", Types.BIGINT));
        declareParameter(new SqlOutParameter("out_name", Types.VARCHAR));

        // Finalize configuration for reuse across multiple calls.
        compile();
    }

    public String findName(long customerId) {
        Map<String, Object> result =
                super.execute(Map.of("in_customer_id", customerId));

        Object value = result.get("out_name");
        return value == null ? null : (String) value;
    }
}
```

This Java class **can compile once Spring JDBC and its dependencies are present**, but **cannot run standalone**: it requires a database containing a procedure named `read_customer_name` with the matching `IN`/`OUT` signature and a properly configured `DataSource`. The procedure and parameter names in this example are hypothetical to illustrate how to read the code; they are not a built-in Spring procedure.

Reading the snippet sign by sign:

1. `extends StoredProcedure` confirms this is an adapter class for an SQL routine, not a typical repository using only `JdbcTemplate.update`.
2. `super(dataSource, "read_customer_name")` provides the **`DataSource` and routine name**. Do not mistake this for a table name or a `SELECT` query.
3. `declareParameter(new SqlParameter(...))` declares an `IN` parameter with the SQL type corresponding to `Types.BIGINT`.
4. `declareParameter(new SqlOutParameter(...))` declares an `OUT` parameter; the expected key in the result is `"out_name"`, whose actual value is unknown until execution.
5. `compile()` marks call configuration complete and prepares internal components; **it is neither a command that executes the procedure nor Java source compilation**.
6. `findName(...)` is a business method named by the subclass author; **`super.execute(...)` is what calls down into Spring JDBC**.
7. The input `Map` maps parameter names to values; the output `Map` maps `OUT` parameter names to returned values.

If you only see a DAO method call:

```java
String name = readCustomerNameProcedure.findName(42L);
```

trace backward: **type of `readCustomerNameProcedure` → constructor → `super(...)`/`setSql(...)` → `declareParameter(...)` calls → `super.execute(...)`**. That chain is what determines which procedure runs, what parameters it receives, and what it returns.

## 3. Step-by-step workflow for reading legacy code

When encountering `StoredProcedure` in a project, use the questions below rather than guessing from variable names:

| Step | What to find | What to conclude |
| --- | --- | --- |
| 1 | `import org.springframework.jdbc.object.StoredProcedure` or `extends StoredProcedure` | Confirms it is Spring JDBC's abstraction, not a same-named class in another package. |
| 2 | `super(dataSource, routineName)`, `setSql(...)`, `setDataSource(...)`, `setJdbcTemplate(...)` | Which routine is called? Which connection pool/`DataSource` is used? |
| 3 | `setFunction(true)`, `setSqlReadyForUse(true)`, `setSql(...)` | Is it a function or a procedure? Does Spring build the call syntax or use a pre-built SQL call string? |
| 4 | All `declareParameter(...)` calls | Do order, names, `java.sql.Types`, `IN`/`OUT`/`INOUT`, and data mappings match the routine? |
| 5 | `compile()`, `afterPropertiesSet()`, `isCompiled()` | Where is configuration finalized—before the first call or during Spring bean initialization? |
| 6 | `execute(Object...)`, `execute(Map)`, `execute(ParameterMapper)` | Are values passed positionally or by name? Is there vendor-specific handling? |
| 7 | `result.get("...")` or map-to-DTO conversion code | Which `OUT` values are actually used, can they be `null`, and what are their data types? |
| 8 | Repository callers and transactions | Which business flow triggers the call? What transactions and side effects exist? |

Do not stop at `execute(...)`: the business semantics usually reside in the database procedure alongside its **actual signature** and the `OUT` value conversion code. If you have schema access, inspect the routine definition in the deployed database. Never assume all environments share the same schema or routine version.

### Example: tracing backward from a call site

```text
OrderService.confirmOrder(orderId)
    ↓
OrderRepository.confirm(orderId)
    ↓
ConfirmOrderProcedure.executeConfirmation(orderId)
    ↓
super.execute(Map.of("in_order_id", orderId))
    ↓
JdbcTemplate.call(...) / JDBC CallableStatement
    ↓
database routine: confirm_order
    ↓
Map output ["out_status", "out_message"]
    ↓
Service decides to log / return response / throw error
```

The flow above is an **illustrative architectural diagram**, not a description of a built-in Spring implementation. Be sure to read classes outside the procedure wrapper too: transactions and business validation may live in the service rather than inside the `StoredProcedure` subclass.

## 4. Meaning of constructors and SQL properties

Two common initialization styles:

```java
// Style A — subclass constructor calls super:
super(dataSource, "calculate_discount");
```

```java
// Style B — JavaBean-style in the subclass constructor:
setDataSource(dataSource);
setSql("calculate_discount");
```

Both identify the routine in the database. `StoredProcedure` has `protected` constructors; therefore, you normally subclass it or use the concrete `GenericStoredProcedure` class.

Sometimes the class uses:

```java
setFunction(true);
```

That directs the call to a **stored function with a return value** instead of a standard procedure. This flag is especially important because the function return typically occupies an `OUT` slot in the JDBC call string; **do not delete that `OUT` parameter thinking it was a stray parameter**.

Another case:

```java
setSqlReadyForUse(true);
setSql("{call legacy_proc(?, ?)}");
```

This is an intentional setup to supply a **ready-to-use JDBC call string**; do not blindly treat `sql` as a plain routine name when `setSqlReadyForUse(true)` is present. `{call ...}` and `{? = call ...}` follow JDBC escape syntax with distinct semantics depending on the driver and parameter order. Read all `declareParameter` calls to see which placeholders are bound/registered.

**Rule:** Never judge whether code calls a procedure or a function solely from a class name like `XxxProcedure`; check `setFunction(...)`, the call string, and the routine definition.

## 5. Parameter types are the key to reading behavior accurately

Declarations typically appear in the constructor:

```java
declareParameter(new SqlParameter("in_customer_id", Types.BIGINT));
declareParameter(new SqlOutParameter("out_name", Types.VARCHAR));
declareParameter(new SqlInOutParameter("io_total", Types.DECIMAL));
```

These three lines are **illustrative parameter types**, not the signature of the single procedure from section 2.

| Type | Meaning | Where does data go? |
| --- | --- | --- |
| `SqlParameter(name, sqlType)` | `IN` | Accepts a Java value at call time and passes it into `CallableStatement`. |
| `SqlOutParameter(name, sqlType)` | `OUT` | Registers a value returned by the DB and retrieves it by `name` in the result map. |
| `SqlInOutParameter(name, sqlType)` | `INOUT` | Both passes an input value in and reads back the value modified by the routine. |
| `SqlOutParameter(name, type, rowMapper)` | Cursor/result `OUT` such as `REF CURSOR` with row mapping | Maps result rows, depending on cursor type and database. |
| `SqlReturnResultSet(name, rowMapper)` | Direct result set from JDBC results | Used with drivers/procedures returning result sets directly; not identical to scalar `OUT`. |
| `SqlReturnUpdateCount(name)` | Update row count from the JDBC result stream | Not a generated key or routine `OUT` value. |

With cursor-type `SqlOutParameter`, you may encounter vendor-specific codes such as `OracleTypes.CURSOR` or `Types.REF_CURSOR`. Do not assume every driver supports them identically; how the database returns cursors, key names, and result order must be verified with real tests.

**The order of `declareParameter` calls matters.** That structure is used to build `CallableStatement`, and when calling `execute(Object...)`, the order of `IN` values must match the order of input-accepting parameters as declared. Changing declaration order during a refactor can alter behavior even when parameter names stay unchanged.

**Legacy compatibility detail:** unlike `SimpleJdbcCall`, `StoredProcedure` contains compatibility behavior allowing input values to be supplied even for parameters declared as `SqlOutParameter`. Do not immediately assume all code passing input to a `SqlOutParameter` is a bug, and do not blindly migrate signatures to `SimpleJdbcCall` without verifying how the real routine behaves. This is one of the easiest differences to cause regressions when switching APIs.

## 6. Three `execute(...)` styles and reading values

### A. `execute(Map<String, ?>)` — passing by name

```java
Map<String, Object> outputs =
        super.execute(Map.of("in_customer_id", 42L));
String name = (String) outputs.get("out_name");
```

This snippet is **inside a `StoredProcedure` subclass** that has declared the matching `IN`/`OUT` parameters. Input keys must match the declared parameter names. For `null` values, **do not use `Map.of`** because it rejects `null`; use `HashMap` or another container allowing nullable values.

The result map does not necessarily represent an entity, a row list, or an ID. It is the collection of values Spring aggregates from declared `OUT` parameters and results. Never assume the returned map is a database table row.

### B. `execute(Object...)` — passing by position

```java
Map<String, Object> outputs = super.execute(42L);
```

This is another overload inside the subclass, suitable when there is exactly **one input**. With multiple inputs, value order must match the order of declared input-accepting parameters:

```java
// If IN "in_id" was declared first and IN "in_region" second:
Map<String, Object> outputs = super.execute(42L, "APAC");
```

These two snippets do not belong to the section 2 procedure signature; they illustrate call forms. When reading legacy code, you cannot tell what `42L` represents without checking `declareParameter` order.

### C. `execute(ParameterMapper)` — custom parameter binding

When you see `execute(ParameterMapper)`, the callback receives a `Connection` to construct the parameter map. This pattern was often used for data/vendor-specific types needing special binding. During review, check whether the mapper depends on a specific JDBC driver class, creates custom SQL objects, and manages resources properly. Do not refactor blindly to a plain `Map` before understanding that logic.

### Results are typically converted to domain types

```java
public String findName(long customerId) {
    Map<String, Object> out =
            super.execute(Map.of("in_customer_id", customerId));
    Object value = out.get("out_name");
    return value == null ? null : (String) value;
}
```

The subclass's public method shields the service layer from knowing `OUT` key names. This is why a `StoredProcedure` class can survive for many years in existing codebases: it encapsulates the database call protocol behind a strongly typed business API.

## 7. Small runnable demo: recognizing and calling a stored function via `StoredProcedure`

To see the full flow `extends StoredProcedure → declareParameter → compile → super.execute → OUT result` without deploying a custom procedure on an external database server, we use the built-in SQL `ABS` function in H2 in-memory mode. **This is a function example**, hence `setFunction(true)`. Legacy wrappers still use `StoredProcedure` itself, showing that this Java class name does not restrict calls to SQL procedures alone.

Create the project:

```text
stored-procedure-recognition/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── Demo.java
```

`build.gradle` (Groovy DSL, JDK 17+, Gradle 8.x):

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'Demo'
}
```

`src/main/java/Demo.java`:

```java
import java.sql.Types;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.object.StoredProcedure;

public class Demo {

    // Adapter class with structure similar to legacy project code.
    static final class AbsFunction extends StoredProcedure {

        AbsFunction(DataSource dataSource) {
            super(dataSource, "ABS");
            setFunction(true); // JDBC function: {? = call ABS(?)}

            // OUT for function result; IN for ABS argument.
            declareParameter(
                    new SqlOutParameter("absolute_result", Types.INTEGER));
            declareParameter(
                    new SqlParameter("input_value", Types.INTEGER));

            compile();
        }

        int absolute(int value) {
            Map<String, Object> output =
                    super.execute(Map.of("input_value", value));

            Object result = output.get("absolute_result");
            if (!(result instanceof Number number)) {
                throw new IllegalStateException(
                        "Function ABS did not return a numeric result");
            }
            return number.intValue();
        }
    }

    public static void main(String[] args) {
        // H2 in-memory and simple DataSource for illustration, without pooling.
        DataSource ds = new DriverManagerDataSource(
                "jdbc:h2:mem:legacy_proc;DB_CLOSE_DELAY=-1", "sa", "");

        AbsFunction wrapper = new AbsFunction(ds);

        System.out.println("ABS(-7)=" + wrapper.absolute(-7));
        System.out.println("ABS(12)=" + wrapper.absolute(12));
    }
}
```

From the project directory, run:

```bash
gradle run
```

If Gradle Wrapper is present, use `./gradlew run` (Linux/macOS) or `.\gradlew.bat run` (Windows PowerShell). Dependencies must be downloaded from Maven Central on the first run. Output produced by **`Demo.main`**, excluding Gradle logs, is:

```text
ABS(-7)=7
ABS(12)=12
```

Step-by-step explanation:

1. The `AbsFunction` constructor binds the object to the `DataSource` and SQL function name `ABS`.
2. `setFunction(true)` tells Spring this call has a return value in the first `OUT` slot.
3. `SqlOutParameter("absolute_result", Types.INTEGER)` declares the function result; `SqlParameter("input_value", Types.INTEGER)` declares the input.
4. `compile()` prepares the JDBC call configuration; it does not compute the absolute value.
5. `super.execute(Map.of(...))` actually performs the call via `JdbcTemplate`/`CallableStatement`.
6. Spring returns a map with key `absolute_result`, then `absolute` converts the result to `int`.
7. Both calls reuse the **same** configured wrapper instance; that is the standard reuse model of `RdbmsOperation`.

The demo uses H2's function call capability. A different database may have different function naming rules, schemas, result types, or call syntax; do not use the demo's output to infer the signature of a business procedure in your project.

### If you encounter a procedure with `OUT` in existing code

Compared to the function demo, a wrapper for a procedure might simply declare:

```java
super(dataSource, "read_stock");
declareParameter(new SqlParameter("in_sku", Types.VARCHAR));
declareParameter(new SqlOutParameter("out_quantity", Types.INTEGER));
compile();
```

This is an **illustrative constructor snippet, not a standalone program**. It assumes the database has a `read_stock` routine taking `in_sku` and returning `out_quantity`, with driver support for `OUT` parameters. Do not add `setFunction(true)` because this is an ordinary procedure.

Inside the wrapper, the call might look like:

```java
Map<String, Object> out =
        super.execute(Map.of("in_sku", "SKU-10"));
Object quantity = out.get("out_quantity");
```

If `out_quantity` can be SQL `NULL`, handle `null`; if it is numeric, do not blindly cast to `Integer` if the driver returns `Long`/`BigDecimal`. `Map.of(...)` is only suitable when `in_sku` is non-`null`.

## 8. `GenericStoredProcedure`: what if there is no `extends`?

In existing codebases, authors do not always create a subclass with `extends StoredProcedure`. Spring provides `org.springframework.jdbc.object.GenericStoredProcedure`, a concrete subclass of `StoredProcedure` allowing generic configuration.

JavaBean-style example:

```java
GenericStoredProcedure procedure = new GenericStoredProcedure();
procedure.setDataSource(dataSource);
procedure.setSql("read_stock");
procedure.declareParameter(
        new SqlParameter("in_sku", Types.VARCHAR));
procedure.declareParameter(
        new SqlOutParameter("out_quantity", Types.INTEGER));
procedure.compile();

Map<String, Object> output =
        procedure.execute(Map.of("in_sku", "SKU-10"));
```

This is an **illustrative snippet**; it requires importing `GenericStoredProcedure`, `SqlParameter`, `SqlOutParameter`, `Types`, `Map`, plus an existing `dataSource` and actual stored procedure. It does not run standalone against the H2 setup from the previous demo.

When inspecting Spring XML beans or legacy configuration, look for class name `org.springframework.jdbc.object.GenericStoredProcedure`, `dataSource`/`jdbcTemplate` properties, `sql`, the parameter list, and bean initialization. Spring may call `afterPropertiesSet()` to complete compilation when configured as a bean; do not conclude that code missing `compile()` in a constructor is uncompiled. With pure Java configuration, calling `compile()` after declaring all parameters is the clearest practice.

## 9. Distinguishing `StoredProcedure` from similar-looking APIs

| Found in project | What it actually is | How to read it properly |
| --- | --- | --- |
| `org.springframework.jdbc.object.StoredProcedure` | Abstract Spring JDBC RDBMS operation object; usually subclassed. | Check `super`/`setSql`, `declareParameter`, `compile`, and `super.execute`. |
| `org.springframework.jdbc.object.GenericStoredProcedure` | Concrete class for generic configuration. | Check bean properties, declared parameters, and callers of `execute`. |
| `org.springframework.jdbc.core.simple.SimpleJdbcCall` | Spring JDBC API for calling procedures/functions, with metadata support. | Check `withProcedureName`/`withFunctionName`, `declareParameters`, `execute`/`executeFunction`. |
| `org.springframework.jdbc.core.JdbcTemplate.call(...)` | Direct call via `CallableStatementCreator` and parameter list. | Check the `CallableStatement` creation callback and register/bind calls. |
| `java.sql.CallableStatement` | Low-level JDBC API. | Check `prepareCall`, `registerOutParameter`, `setXxx`, `execute`, and `getXxx`. |
| `jakarta.persistence.StoredProcedureQuery` | JPA API for stored procedures. | Check `EntityManager`, `registerStoredProcedureParameter`, `execute`. |
| `org.springframework.data.jpa.repository.query.Procedure` | Spring Data JPA annotation on a repository method. | Check JPA mapping, annotation, and repository method. |

**Easy pitfall:** `SimpleJdbcCall` sounds similar, and some codebases use both approaches. The fact that both call stored procedures does not prove they handle parameter binding, metadata, return values, or result sets identically.

### Comparing procedure configuration with `SimpleJdbcCall`

Legacy `StoredProcedure` style:

```java
class ReadStockProcedure extends StoredProcedure {
    ReadStockProcedure(DataSource ds) {
        super(ds, "read_stock");
        declareParameter(new SqlParameter("in_sku", Types.VARCHAR));
        declareParameter(
                new SqlOutParameter("out_quantity", Types.INTEGER));
        compile();
    }
}
```

Hypothetical `SimpleJdbcCall` for the same signature:

```java
SimpleJdbcCall readStock = new SimpleJdbcCall(dataSource)
        .withProcedureName("read_stock")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
                new SqlParameter("in_sku", Types.VARCHAR),
                new SqlOutParameter("out_quantity", Types.INTEGER));

Map<String, Object> out =
        readStock.execute(Map.of("in_sku", "SKU-10"));
```

These two snippets only illustrate **corresponding configurations** and require imports and a real database environment. `SimpleJdbcCall` does not require subclassing and can infer metadata when the driver provides enough information; the example disables parameter metadata to represent a fixed signature. Do not treat this example as proof that refactoring will behave identically across every DB.

Check carefully if legacy code uses: `setFunction(true)`, `setSqlReadyForUse(true)`, `SqlInOutParameter`, `OUT` cursors, `SqlOutParameter` used as input for backward compatibility, output ordering, or SQL with schema/catalog names. These are the areas requiring regression tests before considering a migration to `SimpleJdbcCall`.

## 10. When spotting this in a real system: what to check before modifying?

Answer these questions using **the existing code and actual schema**:

1. **Where does the routine live?** `super(ds, "proc_name")` only shows the configured name; locate the database migration/DDL and connected schema before concluding what business logic the procedure performs.
2. **Who owns the transaction?** `StoredProcedure` itself does not state where transactions begin/commit. Check `@Transactional`, the transaction manager, and service-layer calls. A routine may write to multiple tables rather than just returning a value.
3. **Are parameters in the right order and types?** Cross-check `declareParameter` against the DB signature; pay special attention to `Object...` and function return values.
4. **Can `OUT` values be null?** Avoid unboxing `null` into primitives or casting blindly; convert `Number` values safely with checks.
5. **Where are result sets or cursors read?** Look for `SqlReturnResultSet`, `SqlOutParameter` with `RowMapper`, result key names, and list-consuming code.
6. **Are there driver dependencies?** `REF CURSOR`, custom SQL types, schemas, letter casing, metadata, and callable syntax must be tested against a production-equivalent database.
7. **Is there thread contention?** The wrapper is configured/compiled once and reused; never mutate configuration while threads are calling it. Each `execute` call holds its own parameter data.
8. **Where do exceptions go?** Spring JDBC throws runtime `DataAccessException`s rather than forcing callers to catch `SQLException` directly. Inspect handlers and transaction rollback rules.
9. **When are results visible externally?** A procedure with side effects may run inside a transaction that later rolls back; receiving `OUT` successfully does not prove commit succeeded.

### Example: diagnosing errors by pipeline stage

Suppose the code calls:

```java
Map<String, Object> output =
        myProcedure.execute(Map.of("in_id", id));
```

- If it fails when initializing `myProcedure` or calling `compile()`, check `DataSource` config, routine name, parameter list, and compile error.
- If it fails at execution time, check the database routine, `EXECUTE` privileges, schema, SQL types, bind order, driver, and transaction.
- If the call succeeds but the map lacks key `out_name`, check declared `OUT` parameters, key casing, callbacks/result sets, and return types.
- If the map has a value yet the service fails, check type conversion, `null` handling, business method contracts, and caller exception handling.

Do not blame the JDBC driver solely from a `ClassCastException` in `OUT`-reading code: that can be a Java mapping bug after the DB returned the right value.

## 11. Common misconceptions

| Misconception | Why it is wrong | Correct understanding |
| --- | --- | --- |
| "`StoredProcedure` is an SQL annotation that runs directly" | It is a Spring JDBC Java class. | An instance wraps a database routine call via `CallableStatement`. |
| "`compile()` executes the procedure" | Compile is the configuration preparation step. | The actual call happens during `execute(...)`. |
| "The Java class name is the SQL routine name" | The Java class is named by the project. | Look for `super(ds, name)`, `setSql`, or the raw call string. |
| "`execute(Map)` returns all rows of a table" | The output map reflects declared `OUT`/results. | Read individual keys and mappers; never assume it is an entity. |
| "`execute(Object...)` accepts every value by name" | That overload accepts values positionally. | Check the order of `declareParameter`. |
| "`OUT` parameters do not affect function calls" | Function return values usually need an `OUT` slot. | Check `setFunction(true)` and proper `OUT` declaration. |
| "A new `StoredProcedure` must be created per run" | `RdbmsOperation` supports reuse once configured. | Initialize/compile once, execute many times with separate arguments. |
| "Switching everything to `SimpleJdbcCall` is always equivalent" | There are differences in metadata, input/`OUT` handling, cursors, and compatibility behavior. | Write integration tests against the DB signature before migrating. |
| "Once `OUT` arrives, data is definitely committed" | The transaction can roll back after the routine executes. | Check transaction boundaries and side-effect behavior. |
| "Must import `jakarta.sql.DataSource`" | `DataSource` is a Java SE JDBC API. | Use `javax.sql.DataSource`; `jakarta.persistence.StoredProcedureQuery` is a different API. |

## 12. Short code-reading exercise

Examine this snippet:

```java
final class StatusFunction extends StoredProcedure {
    StatusFunction(DataSource ds) {
        super(ds, "order_status_code");
        setFunction(true);
        declareParameter(
                new SqlOutParameter("status", Types.INTEGER));
        declareParameter(
                new SqlParameter("in_order_id", Types.BIGINT));
        compile();
    }

    int getStatus(long orderId) {
        Map<String, Object> out =
                super.execute(Map.of("in_order_id", orderId));
        Object value = out.get("status");
        if (!(value instanceof Number number)) {
            throw new IllegalStateException("Invalid status result");
        }
        return number.intValue();
    }
}
```

This is an **illustrative snippet**: imports and the database function `order_status_code` are omitted, so it is not a standalone program.

Answer for yourself:

1. **Is this a procedure or a function?** A function, because of `setFunction(true)`. The class name `StatusFunction` is only a hint; the configuration is the proof.
2. **What is the input?** One `IN` parameter `in_order_id` of SQL type `BIGINT`; its value comes from `orderId`.
3. **Where is the output read from?** From the map returned by `super.execute(...)` under key `status`, declared with `SqlOutParameter`.
4. **Does `compile()` query the DB to fetch the status?** No. Fetching happens in `execute`.
5. **What must be verified before running in production?** That the routine actually exists, return/`IN` signatures match, the driver supports callable functions, return value could be `null` or another numeric type, execution privileges, and transactions if there are side effects.

If you can answer these five questions, you can already recognize most `StoredProcedure` wrappers in a codebase before debugging or modifying them.

## 13. Cheat sheet when reviewing legacy code

```text
extends StoredProcedure / GenericStoredProcedure
    │
    ├── super(dataSource, "routine") / setSql / setJdbcTemplate
    ├── [setFunction(true)]            -> function with return value
    ├── [setSqlReadyForUse(true)]      -> raw JDBC call string
    ├── declareParameter(...)          -> IN, OUT, INOUT, cursor/result
    └── compile() / afterPropertiesSet
                       │
                       ▼
              Domain wrapper method
                       │
                       ▼
                super.execute(...)
                       │
                       ▼
             JdbcTemplate.call(...)
                       │
                       ▼
              JDBC CallableStatement
                       │
                       ▼
                    DB routine
                       │
                       ▼
              OUT/result Map
                       │
                       ▼
            Mapping to business type
```

**Key takeaway:** when reading legacy Spring JDBC code, do not look only for `execute()`. Read **class/package → routine name → procedure/function mode → parameter declarations → input passing style → `OUT` map → caller/transaction**. This chain explains exactly where data originates and usually pinpoints upgrade risks.

### Official references

- Spring Framework — *Modeling JDBC Operations as Java Objects*, including the `StoredProcedure` section: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/object.html
- Spring Framework — *Choosing an Approach for JDBC Database Access*: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/choose-style.html
- Spring Framework Javadoc — `StoredProcedure` (Spring 6.2): https://docs.spring.io/spring-framework/docs/6.2.14-SNAPSHOT/javadoc-api/org/springframework/jdbc/object/StoredProcedure.html
- Spring Framework Javadoc — `RdbmsOperation`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/object/RdbmsOperation.html
- Spring Framework Javadoc — `GenericStoredProcedure`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/object/GenericStoredProcedure.html
- Spring Framework — `SimpleJdbcCall` in *Simplifying JDBC Operations*: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/simple.html
- H2 Database — *User-Defined Functions and Stored Procedures*: https://h2database.com/html/features.html
