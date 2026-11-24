# `@SqlConfig`: Encoding, Separators, and Error Handling

Spring Test lets you run SQL scripts before or after a test method using `@Sql`. This approach is commonly used to create schemas, load sample data, or clean up data after testing repositories and services. When a script contains Vietnamese or non-ASCII characters, stored procedures with multiple semicolons, or runs on a database with custom comment syntax, default settings may no longer suffice.

`@SqlConfig` provides options to control how Spring reads and executes scripts: file encoding, statement separator, comment prefix, multi-line comment delimiters, datasource, transaction manager, transaction mode, and SQL error handling. Proper configuration helps tests read scripts consistently on developer machines and in CI, while avoiding situations where setup fails yet the test continues with incomplete data.

## 1. How do `@Sql` and `@SqlConfig` work together?

`@Sql` declares SQL scripts or SQL statements to execute in a test. Example:

```java
@SpringBootTest
@Sql("/db/test-data.sql")
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void findsCustomerInsertedByScript() {
        assertThat(customers.findByEmail("lan@example.test")).isPresent();
    }
}
```

Scripts are placed on the test classpath, for example `src/test/resources/db/test-data.sql`. By default, `@Sql` runs scripts before each test method (`BEFORE_TEST_METHOD`).

`@SqlConfig` configures how Spring reads and executes scripts. There are two common scopes:

- **Global configuration for a test class:** place `@SqlConfig` directly on the class. Attributes apply to `@Sql` declarations within the class and corresponding inheritance scope.
- **Local configuration for a script group:** place `@SqlConfig` in the `config` attribute of an `@Sql`. Local configuration applies only to scripts declared on that `@Sql` and can override global configuration.

Global configuration example:

```java
@SpringBootTest
@SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        commentPrefixes = {"--"},
        errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
class CustomerRepositoryTest {
    @Test
    @Sql("/db/customers.sql")
    void loadsCustomerFixture() {
        // Script uses the class's shared configuration.
    }
}
```

Local configuration example:

```java
@Test
@Sql(
        scripts = "/db/create-procedure.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = "@@",
                errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR))
void createsProcedureWithCustomDelimiter() {
    // Only this script uses the @@ separator.
}
```

When an attribute is configured in both scopes, the local value is used for that `@Sql`. Unoverridden attributes continue to inherit the global configuration or Spring's default values.

## 2. Encoding: reading SQL scripts with the right character set

The `encoding` attribute specifies the charset Spring uses when reading SQL file contents. If omitted, Spring uses the platform's default encoding. Default encodings can vary between developer machines, CI containers, and operating systems, so scripts containing non-ASCII characters should declare it explicitly.

Example script containing Vietnamese data:

```sql
INSERT INTO customer (id, full_name, city)
VALUES (101, 'Nguyễn Thị Lan', 'Thành phố Hồ Chí Minh');
```

If the file is saved as UTF-8, declare:

```java
@SqlConfig(encoding = "UTF-8")
```

Or configure it for a single script:

```java
@Sql(
        scripts = "/db/vietnamese-fixtures.sql",
        config = @SqlConfig(encoding = "UTF-8"))
```

Charset names are passed as strings using Java charset names, such as `UTF-8`, `UTF-16`, or any charset supported by the JVM. In modern projects, UTF-8 is usually the right choice for SQL files stored in Git.

### 2.1. File encoding must match the configuration

Merely declaring `encoding = "UTF-8"` does not automatically convert file contents. The file itself must also be saved in UTF-8. If a file was saved in Windows-1258 but Spring reads it as UTF-8, Vietnamese data can suffer character corruption or invalid SQL literals.

When encountering encoding errors:

1. Check the actual file encoding in your editor or a file inspection tool.
2. Choose one consistent encoding for all SQL fixtures.
3. Re-save the file in that encoding.
4. Declare the same charset in `@SqlConfig`.
5. Run tests in the CI environment to confirm results do not depend on local machine settings.

Do not rely on the operating system's default encoding as an implicit convention for shared fixtures. Explicit encoding declaration makes script reading behavior much more stable.

### 2.2. Encoding does not replace database collation settings

`encoding` only controls how Java reads the SQL file into characters. It does not determine the charset, collation, or data type of columns in the database. If the script is read correctly but data is stored or compared incorrectly, inspect the database configuration, column types, and collation separately.

## 3. SQL statement separator (`separator`)

The `separator` attribute specifies the character sequence used to split statements in a script. By default, Spring uses a semicolon (`;`). Example:

```sql
INSERT INTO department (id, name) VALUES (1, 'Engineering');
INSERT INTO department (id, name) VALUES (2, 'Support');
UPDATE department SET name = 'Platform Engineering' WHERE id = 1;
```

Spring splits the script into statements by the separator and executes them sequentially. You can declare it explicitly:

```java
@SqlConfig(separator = ";")
```

When a script contains only standard SQL, keeping the default separator is usually sufficient. Only change the separator when script syntax causes `;` to appear inside a complex statement.

### 3.1. Stored procedures with internal semicolons

A stored procedure or function may contain multiple internal statements, each ending with `;`. If Spring uses `;` as the separator for the entire file, the script can be split incorrectly into fragments.

Example of a procedure whose body contains multiple statements:

```sql
CREATE PROCEDURE update_customer_status(IN customer_id BIGINT)
BEGIN
    UPDATE customer
       SET status = 'ACTIVE'
     WHERE id = customer_id;

    INSERT INTO audit_log (entity_id, action)
    VALUES (customer_id, 'CUSTOMER_ACTIVATED');
END
@@
```

For databases supporting this syntax, you can use a custom separator at the end of the definition:

```java
@Sql(
        scripts = "/db/procedures.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = "@@"))
```

In this case, `;` inside the procedure belongs to the statement's syntax, while `@@` marks the statement boundary so Spring sends the entire definition to the database. Specific procedure syntax depends on the database; use a delimiter suitable for the dialect in use.

### 3.2. Separator must match the script exactly

If `separator = "@@"` is configured while the file still ends statements with `;`, Spring may treat the entire file as one statement or fail to split as expected. Conversely, if the file uses `@@` while the configuration keeps `;`, the procedure may be split improperly.

Keep the separator in the file and the annotation as a matched pair. You can add a note at the top of the script so readers know the delimiter:

```sql
-- This script uses @@ as the statement separator.
CREATE PROCEDURE refresh_summary()
BEGIN
    UPDATE summary_table SET refreshed = TRUE;
END
@@
```

`separator` is a literal string, not a regular expression. Choose a delimiter unlikely to appear inside statement contents.

### 3.3. Scripts with a single statement or special delimiter

If a script contains only one complex statement, you can choose an appropriate delimiter so Spring sends the statement as a single unit. Spring also has the constant `ScriptUtils.EOF_STATEMENT_SEPARATOR` for using the end of file as the statement boundary. When using this special delimiter, make sure the script contains only the statement the test intends to execute and does not rely on the parser splitting on internal semicolons.

For most fixtures, the default `;` separator is readable and compatible with standard SQL. Only use special delimiters when database syntax requires them.

## 4. Comment prefixes and block comments

SQL scripts often have comments explaining fixtures or temporarily disabling a statement. `@SqlConfig` lets you configure comment syntax so the parser ignores comments when splitting statements.

### 4.1. Single-line comments

By default, Spring recognizes `--` as the single-line comment prefix. Example:

```sql
-- Seed a customer used by repository tests.
INSERT INTO customer (id, name) VALUES (101, 'Lan');
```

You can specify the comment prefix with `commentPrefix`:

```java
@SqlConfig(commentPrefix = "--")
```

Since Spring Framework 6.1, `commentPrefixes` allows declaring multiple prefixes:

```java
@SqlConfig(commentPrefixes = {"--", "#"})
```

This is useful when scripts contain comments using conventions from multiple tools or databases. Only declare prefixes that are actually used; a character might appear in SQL literals or dialect operators and must be handled properly by the parser.

### 4.2. Block comments

By default, Spring recognizes block comments using the `/*` and `*/` pair:

```sql
/*
  Fixture for the customer repository integration test.
  Keep the IDs stable so assertions remain deterministic.
*/
INSERT INTO customer (id, name) VALUES (101, 'Lan');
```

You can configure the delimiters explicitly:

```java
@SqlConfig(
        blockCommentStartDelimiter = "/*",
        blockCommentEndDelimiter = "*/")
```

If a script uses a custom block comment style produced by an SQL generation tool, declare the matching delimiter pair. Both values must accurately reflect the syntax in the file.

### 4.3. Comments are not sent as SQL statements

The parser strips comments when preparing statements. This lets the file include explanations without causing the database to receive an invalid statement. However, do not use comments as a substitute for configuring the separator or to hide broken SQL. If a script contains specialized syntax the parser does not understand, adjust the comment delimiters or split scripts by purpose.

## 5. Selecting datasource and transaction manager for scripts

`@SqlConfig` not only controls how files are read, but also has attributes specifying where and under which transaction the script runs:

- `dataSource`: name of the `DataSource` bean used to execute SQL.
- `transactionManager`: name of the `PlatformTransactionManager` bean used to manage the script's transaction.
- `transactionMode`: how the script participates in or creates a transaction.

If the application has only one suitable datasource and one transaction manager, Spring can infer them. When there are multiple data sources, specify bean names to prevent scripts from running against the wrong database.

Example:

```java
@SpringBootTest
@SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        encoding = "UTF-8",
        separator = ";")
class OrderSqlIntegrationTest {
    @Test
    @Sql("/db/orders-fixture.sql")
    void loadsOrderFixture() {
        // Script runs on the orders datasource.
    }
}
```

If a script uses an audit datasource, configure the corresponding `dataSource` and `transactionManager`. Both beans need to manage the same resource or the same persistence setup the script is targeting.

When a test method already has `@Transactional`, transaction mode determines whether the script joins the current transaction or runs in its own transaction. Understanding this is essential to know whether setup data rolls back with the test.

## 6. Transaction mode in `@SqlConfig`

`SqlConfig.TransactionMode` has three values:

| Value | Meaning |
|---|---|
| `DEFAULT` | Uses the default mode inferred from global configuration or Spring's default behavior. |
| `INFERRED` | Uses an active transaction if present; otherwise, Spring can create a separate transaction if a suitable transaction manager is found. |
| `ISOLATED` | Runs the script in its own transaction, independent of the current transaction, and commits that separate transaction upon successful completion. |

In most tests, inferred mode is sufficient. If the test method has a transaction managed by Spring Test, the setup script typically joins that transaction. When the test ends and the transaction rolls back, the setup data also rolls back.

### 6.1. Using scripts in a test-managed transaction

```java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    @Sql("/db/customer-fixture.sql")
    void readsFixtureInsideTestTransaction() {
        assertThat(customers.findByEmail("lan@example.test")).isPresent();
    }
}
```

With the inferred transaction mode, the script can join the active test transaction. Data is created in the same transaction and rolled back after the test by default. This is a convenient way to set up fixtures without leaving data behind after each method.

### 6.2. Using `ISOLATED` when setup must commit independently

There are cases where setup data must be committed before the test runs, such as testing a component that reads data from another transaction or verifying behavior that depends on committed data. You can choose `ISOLATED`:

```java
@Test
@Transactional
@Sql(
        scripts = "/db/committed-fixture.sql",
        config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
void readsCommittedFixture() {
    // Fixture is committed in its own transaction.
}
```

The script runs in a separate transaction and commits on success. Because that transaction is independent of the test transaction, rolling back the test method does not automatically undo data committed by the script. The test needs to clean up this data with another script or a dedicated fixture cleanup mechanism.

Do not choose `ISOLATED` just because a script fails to run. Clearly identify the transaction boundary under test. If you want setup to roll back with the test, keep the inferred mode and ensure the script uses the right manager.

## 7. `errorMode`: handling errors during script execution

`@SqlConfig.errorMode` decides what happens when a statement in a script fails. This is an important setting because a script may contain many statements; if one fails, Spring can stop or continue depending on the mode.

Values of `SqlConfig.ErrorMode`:

| Value | Behavior |
|---|---|
| `DEFAULT` | Uses the default error behavior of Spring's ScriptUtils. By default, it stops on SQL errors while providing special handling for certain failed `DROP` statements. |
| `FAIL_ON_ERROR` | Reports an error and stops the script immediately when any statement fails, including `DROP` statements. |
| `CONTINUE_ON_ERROR` | Logs the error and continues executing the remaining statements. |
| `IGNORE_FAILED_DROPS` | Ignores errors from `DROP` statements, while still failing on other statement types. |

### 7.1. `DEFAULT`

If `errorMode` is omitted, Spring uses `ScriptUtils`'s default behavior. By default, errors in regular statements fail the script; errors in `DROP` commands may be ignored to support repeatable cleanup scripts.

For example, a script might drop a temporary table before recreating it:

```sql
DROP TABLE temporary_customer;
CREATE TABLE temporary_customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
```

If the table does not yet exist, `DROP` may fail while the script continues under default handling for failed drops. Errors in `CREATE TABLE` or `INSERT` still need to be caught.

### 7.2. `FAIL_ON_ERROR`

Use this mode when every statement is required to succeed:

```java
@SqlConfig(errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
```

This is usually the right choice for fixtures creating data that tests depend on directly. If an `INSERT` violates a constraint or a column was renamed, the test should fail right at setup instead of continuing with missing data.

`FAIL_ON_ERROR` also turns a failed `DROP` into an error. If a script contains commands dropping objects that may not exist yet, use database-appropriate idempotent syntax like `DROP TABLE IF EXISTS` or choose the failed-drop handling mode when that fits the script's purpose.

### 7.3. `CONTINUE_ON_ERROR`

This mode tells Spring to continue executing remaining statements upon encountering an error:

```java
@SqlConfig(errorMode = SqlConfig.ErrorMode.CONTINUE_ON_ERROR)
```

It can be helpful for special migration or teardown scripts when you want to collect multiple errors in one run. However, for unit/integration test fixtures, this mode easily hides incomplete setup. Tests may fail later on assertions, making the real root cause hard to spot, or even pass if the failing statement does not affect the assertion.

Only use `CONTINUE_ON_ERROR` when the script is designed to continue past errors and the author understands the resulting data state. Never use it as a way to make tests pass when SQL has errors.

### 7.4. `IGNORE_FAILED_DROPS`

This mode ignores errors from `DROP` statements while failing the script on other errors:

```java
@SqlConfig(errorMode = SqlConfig.ErrorMode.IGNORE_FAILED_DROPS)
```

It fits teardown scripts that need to delete objects if they exist while still catching errors in `INSERT`, `UPDATE`, `CREATE`, or other statements. If the database supports `IF EXISTS`, that syntax usually expresses intent more clearly:

```sql
DROP TABLE IF EXISTS temporary_customer;
```

Choose syntax by dialect. Not every database supports the same `IF EXISTS` variant for every object type.

## 8. Combining encoding, separator, and error mode

A script may require multiple settings at the same time. For example, a script creating a stored procedure with internal semicolons, comments, and Unicode data:

```java
@Test
@Sql(
        scripts = "/db/customer-procedures.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = "@@",
                commentPrefixes = {"--"},
                blockCommentStartDelimiter = "/*",
                blockCommentEndDelimiter = "*/",
                errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR))
void installsCustomerProcedures() {
    // Script is read as UTF-8, split by @@, and stops on any error.
}
```

Each attribute controls a distinct aspect:

- `encoding` determines how file bytes are decoded into characters.
- `separator` determines statement boundaries.
- `commentPrefixes` and block delimiters determine comment sections to skip.
- `errorMode` determines how Spring reacts when the database reports an error while executing a statement.

These settings do not fix invalid database SQL syntax. If a statement is invalid for the dialect, choosing a different encoding or separator will not make it valid SQL; only `errorMode` decides how Spring reacts when the database returns an error.

## 9. Global and local configuration

A test class may contain multiple scripts with different requirements. For instance, normal fixtures use `;`, while stored procedures use `@@`:

```java
@SpringBootTest
@SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
class CustomerDatabaseTest {
    @Test
    @Sql("/db/customer-fixture.sql")
    void loadsCustomerData() {
        // Uses global config: UTF-8, ;, and fail on error.
    }

    @Test
    @Sql(
            scripts = "/db/customer-procedure.sql",
            config = @SqlConfig(separator = "@@"))
    void createsCustomerProcedure() {
        // Only separator is overridden; encoding and error mode are inherited.
    }
}
```

When local configuration only sets `separator`, the remaining attributes continue to receive values from the global configuration or defaults. This avoids repeating the entire configuration for every script.

### 9.1. When a script needs a completely different configuration

If a script uses a different dialect, datasource, or transaction mode, declare all differing attributes locally:

```java
@Sql(
        scripts = "/db/audit-fixture.sql",
        config = @SqlConfig(
                dataSource = "auditDataSource",
                transactionManager = "auditTransactionManager",
                transactionMode = SqlConfig.TransactionMode.ISOLATED,
                encoding = "UTF-8",
                separator = ";",
                errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR))
```

This script runs on the specified audit datasource and transaction manager. Because `ISOLATED` is used, data can commit independently of the test transaction; proper cleanup is required.

### 9.2. Configuration inheritance in a test class hierarchy

If `@SqlConfig` is placed on a base test class, it can act as global configuration for `@Sql` declarations across the class hierarchy. Subclasses can add or override configuration according to Spring Test's merged annotation rules.

Keep base class configuration strictly to genuinely shared settings, such as UTF-8 and strict error mode. If a subclass uses a different datasource, declare `dataSource` and `transactionManager` separately where needed to avoid running against the wrong database.

## 10. `@Sql` with multiple scripts and execution phases

`@Sql` can declare multiple scripts:

```java
@Test
@Sql(scripts = {
        "/db/schema.sql",
        "/db/reference-data.sql",
        "/db/customer-fixture.sql"
})
void runsScriptsInDeclaredOrder() {
    // Scripts are executed in declared order.
}
```

Order matters when later scripts depend on tables or data created by earlier scripts. Keeping scripts small and focused on single responsibilities makes them easier to reuse and diagnose than one large setup file.

`executionPhase` determines whether a script runs before or after the test method:

```java
@Test
@Sql(
        scripts = "/db/cleanup-customer.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
void createsCustomer() {
    // Clean up data after the method according to the corresponding transaction config.
}
```

The default value is `BEFORE_TEST_METHOD`. `AFTER_TEST_METHOD` can be used for teardown. When a test has a transaction, understand which transaction the teardown script joins and how that transaction is committed or rolled back. If cleanup must take effect independently of the test transaction, configure `transactionMode = ISOLATED` and the appropriate transaction manager.

### 10.1. `@Sql` at the class and method levels

`@Sql` can be placed on a class to run scripts for test methods in the class, or on a method to set up a specific scenario. When both scopes declare scripts, Spring has merge/override modes to determine which scripts execute. If a test class uses shared setup and some methods have their own fixtures, declare merge intent explicitly with `@SqlMergeMode` when needed.

Do not assume a method-level `@Sql` always replaces or always supplements class-level scripts without checking the active merge mode. Default settings and the `@SqlMergeMode` annotation determine how they combine. For important tests, keep class-level setup concise and use method-level scripts for specific data.

## 11. Configuring SQL scripts with multiple datasources

If an application has multiple `DataSource` or `PlatformTransactionManager` beans, Spring may not be able to infer which source a script should use. Specify bean names explicitly:

```java
@SpringBootTest
class MultiDatabaseSqlTest {
    @Test
    @Sql(
            scripts = "/db/orders-fixture.sql",
            config = @SqlConfig(
                    dataSource = "ordersDataSource",
                    transactionManager = "ordersTransactionManager",
                    encoding = "UTF-8"))
    void loadsOrders() {
        // Fixture is executed on the orders database.
    }

    @Test
    @Sql(
            scripts = "/db/audit-fixture.sql",
            config = @SqlConfig(
                    dataSource = "auditDataSource",
                    transactionManager = "auditTransactionManager",
                    encoding = "UTF-8"))
    void loadsAuditEntries() {
        // Fixture is executed on the audit database.
    }
}
```

If a test method has `@Transactional`, ensure `@SqlConfig`'s transaction manager matches the transaction the script should join. A script running on the audit datasource is not automatically rolled back by the orders manager's transaction.

With JPA, `@Sql` executes SQL directly through the datasource. If the test has an open persistence context holding cached entities, the script may modify the database without automatically updating entities in the persistence context. When you need to re-read state created by the script, consider flushing/clearing the `EntityManager` or using a repository in a new transaction/persistence context.

## 12. Diagnosing SQL script errors

### 12.1. Vietnamese characters are corrupted

Check the actual encoding of the file and `@SqlConfig.encoding`. Align both file and config to UTF-8. If characters are read properly but stored incorrectly, check the database charset/collation and column types.

### 12.2. Stored procedure gets split into multiple statements

Check for `;` inside the procedure. Choose a custom separator such as `@@` and place the matching delimiter at the end of each statement in the file. Ensure the separator does not appear unintentionally inside SQL contents.

### 12.3. Parser sends comments as part of SQL

Check `commentPrefixes`, `blockCommentStartDelimiter`, and `blockCommentEndDelimiter`. Make sure they match the comment syntax in the file and that your Spring version supports the attributes used.

### 12.4. Script continues even though setup failed

Check `errorMode`. If `CONTINUE_ON_ERROR` is used, Spring may continue after a failed statement. For fixtures that must be complete, use `FAIL_ON_ERROR` or the appropriate `DEFAULT` behavior.

### 12.5. Script fails because table does not exist yet

If the error comes from `DROP`, consider dialect-specific `DROP TABLE IF EXISTS` or `IGNORE_FAILED_DROPS`. If the error comes from `INSERT`/`UPDATE`/`CREATE`, do not ignore it just to let the script continue.

### 12.6. Script runs on the wrong database

Check `dataSource` and `transactionManager` in `@SqlConfig`, bean names, and the datasource the repository uses. With multiple datasources, do not rely on automatic inference if the context has multiple candidates.

### 12.7. Fixture data disappears after the test

If the script joined a test-managed transaction, data may be rolled back after the method. If the fixture must commit independently, use `ISOLATED` and remember to clean up because test rollback will not remove independently committed data.

## 13. Combined example: UTF-8 fixtures and stored procedures

Suppose a test needs to create customer data with Vietnamese text and install a stored procedure. Normal fixture scripts use `;`:

```sql
-- src/test/resources/db/customer-fixture.sql
INSERT INTO customer (id, full_name, city)
VALUES (101, 'Nguyễn Thị Lan', 'Thành phố Hồ Chí Minh');

INSERT INTO customer (id, full_name, city)
VALUES (102, 'Trần Minh Đức', 'Đà Nẵng');
```

Procedure script uses `@@` as the separator:

```sql
-- src/test/resources/db/customer-procedure.sql
CREATE PROCEDURE activate_customer(IN p_id BIGINT)
BEGIN
    UPDATE customer
       SET status = 'ACTIVE'
     WHERE id = p_id;

    INSERT INTO audit_log (entity_id, action)
    VALUES (p_id, 'CUSTOMER_ACTIVATED');
END
@@
```

Test class with shared configuration:

```java
@SpringBootTest
@SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        commentPrefixes = {"--"},
        errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
class CustomerSqlIntegrationTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    @Sql("/db/customer-fixture.sql")
    void readsUnicodeFixture() {
        Customer customer = customers.findById(101L).orElseThrow();

        assertThat(customer.name()).isEqualTo("Nguyễn Thị Lan");
        assertThat(customer.city()).isEqualTo("Thành phố Hồ Chí Minh");
    }

    @Test
    @Sql(
            scripts = "/db/customer-procedure.sql",
            config = @SqlConfig(separator = "@@"))
    void installsProcedureUsingCustomSeparator() {
        // Verify procedure exists or execute it per database dialect.
    }
}
```

The fixture script inherits UTF-8, the default separator, and fail-on-error. The procedure script only overrides `separator` to `@@`; other attributes continue to be inherited. Stored procedure syntax in the example should be adapted to the database used by the project.

## 14. `@SqlConfig` configuration workflow

When an SQL script does not run properly or has special requirements, check in order:

1. Identify the script file and the active `@Sql` scope: class-level or method-level.
2. Check the actual file encoding; declare `encoding` explicitly if the script contains Unicode.
3. Check the delimiter of each statement; if a procedure contains internal `;`, choose a custom `separator`.
4. Declare the right comment prefixes and block comment delimiters if the script uses non-default syntax.
5. Select `dataSource` and `transactionManager` if the application has multiple data sources.
6. Choose transaction mode based on whether it should join the test transaction or commit separately.
7. Choose error mode: strict for mandatory fixtures; only continue or ignore failed drops when the script intends so.
8. Run the test and read the first SQL error to identify which statement failed.
9. If using `ISOLATED` or independently committed scripts, add cleanup for data that persists after the test.

Keep shared configuration at the class level when multiple scripts share the same encoding, delimiter, and error policy. Use local configuration for procedures or special scripts to change only the necessary attributes without altering other fixtures.

## 15. Principles to remember

- `@Sql` declares scripts; `@SqlConfig` controls how scripts are read and executed.
- `encoding` should match the actual file encoding; UTF-8 is a stable choice for fixtures with Unicode.
- `separator` defaults to `;`; use a custom delimiter when statements like stored procedures contain internal semicolons.
- `commentPrefix` configures single-line comments; `commentPrefixes` supports multiple prefixes since Spring Framework 6.1.
- `blockCommentStartDelimiter` and `blockCommentEndDelimiter` configure multi-line comments.
- `dataSource` and `transactionManager` help select the right data source when the context has multiple beans.
- `DEFAULT`, `FAIL_ON_ERROR`, `CONTINUE_ON_ERROR`, and `IGNORE_FAILED_DROPS` have different behaviors; critical fixtures usually require a strict error policy.
- `INFERRED` can join the current transaction; `ISOLATED` runs and commits a separate transaction.
- Class-level `@SqlConfig` configuration is shared; configuration in `@Sql(config = ...)` applies locally and overrides the corresponding attributes.
- SQL scripts are executed by a real database, so they must still conform to database dialect, schema, constraints, and permissions.

`@SqlConfig` gives clear control over how Spring reads files, splits statements, and reacts when SQL fails. When encoding, delimiters, transaction manager, and error mode are matched properly to the script, test setup data remains consistent and SQL errors are reported at the exact step instead of being masked by incomplete data state.
