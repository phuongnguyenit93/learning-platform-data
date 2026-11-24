# Script Paths and Default Script Detection

In Spring testing, SQL scripts are commonly used to create schemas, load sample data, prepare state before a test, or clean up data after a test. Spring TestContext provides the `@Sql` annotation to declare scripts to execute and rules for resolving the corresponding resources.

Two key things to understand clearly are **how Spring resolves resource paths** and **how Spring automatically detects a default script when the annotation declares no path**. Confusing a relative path with a path relative to the application working directory, or not knowing the default file naming convention, can cause tests to report missing scripts even when the files exist in the project.

## 1. Role of @Sql in Spring TestContext

`@Sql` belongs to the `org.springframework.test.context.jdbc` package. This annotation allows declaring SQL scripts or inline SQL statements directly on test classes and test methods. Spring TestContext uses `SqlScriptsTestExecutionListener` to read metadata, locate resources, and execute SQL at the configured phase.

Example of declaring a script on a test method:

```java
@Test
@Sql("classpath:/db/test/insert-order.sql")
void findsInsertedOrder() {
    // Test queries data prepared by the script.
}
```

The `value` attribute is an alias for `scripts`, so the following two forms are equivalent:

```java
@Sql("classpath:/db/test/insert-order.sql")
```

```java
@Sql(scripts = "classpath:/db/test/insert-order.sql")
```

When there are multiple files, pass an array of paths:

```java
@Sql(scripts = {
        "classpath:/db/test/clear-orders.sql",
        "classpath:/db/test/insert-orders.sql"
})
```

Scripts within the same declaration are processed in the order listed. This is useful when the first script deletes or creates the required structure before the next script loads data.

`@Sql` can be declared at the class or method level. Class-level declarations generally apply to the test methods in the class; method-level declarations describe scripts specific to that method. By default, scripts execute before the test method unless `executionPhase` is configured otherwise.

## 2. Resource path resolution rules

Each element in `scripts` is interpreted by Spring as a resource. Paths can be interpreted relative to the test class's package or via an explicit resource prefix.

| Declaration style | How Spring resolves it | Example |
|---|---|---|
| No prefix, not starting with `/` | Classpath resource relative to the test class's package | `db/seed.sql` |
| Starting with `/` | Absolute classpath resource from the classpath root | `/db/seed.sql` |
| With `classpath:` prefix | Resource on the classpath at the specified location | `classpath:/db/seed.sql` |
| With `file:` prefix | Resource on the filesystem | `file:/opt/test-data/seed.sql` |

Key point to remember: package-relative paths are resolved from the Java package of the test class, not from the current terminal directory, the project directory, or the Java file's location on the filesystem.

### 2.1. Paths relative to the test class package

Suppose a test class declares the package:

```java
package com.example.orders;
```

And has the annotation:

```java
@Sql("db/seed-orders.sql")
class OrderRepositoryTest {
}
```

Spring searches for the resource on the classpath at:

```text
com/example/orders/db/seed-orders.sql
```

In a standard Maven or Gradle project, the corresponding file is located at:

```text
src/test/resources/com/example/orders/db/seed-orders.sql
```

During the build, contents under `src/test/resources` are placed onto the test runtime classpath. The annotation uses the logical path on the classpath, not the source filesystem path `src/test/resources/...`.

Example layout:

```text
src/
  test/
    java/
      com/
        example/
          orders/
            OrderRepositoryTest.java
    resources/
      com/
        example/
          orders/
            db/
              seed-orders.sql
              clean-orders.sql
```

With this structure, `@Sql("db/seed-orders.sql")` is a relative path matching the `com.example.orders` package.

### 2.2. Absolute classpath paths starting with /

If a path starts with `/`, Spring treats it as a location from the classpath root:

```java
@Sql("/db/test/seed-orders.sql")
class OrderRepositoryTest {
}
```

Corresponding resource:

```text
src/test/resources/db/test/seed-orders.sql
```

The `com/example/orders` package is not prepended to this path. The leading `/` switches resolution from package-relative to classpath-absolute.

### 2.3. The classpath: prefix

You can use `classpath:` to make it explicit that the resource resides on the classpath:

```java
@Sql("classpath:/db/test/seed-orders.sql")
```

This style is often easier to read in projects with many resource types because readers immediately know the script comes from the classpath root. It also avoids depending on the test class's package.

If `classpath:` is used without a `/` after the colon, the resource is still resolved according to Spring's classpath rules; to express the path from the root clearly, write `classpath:/...`.

### 2.4. The file: prefix

If a script resides outside the classpath, you can use the `file:` resource prefix:

```java
@Sql("file:/opt/test-fixtures/orders/seed.sql")
```

On Windows, a file URI typically looks like:

```java
@Sql("file:///C:/test-fixtures/orders/seed.sql")
```

Absolute filesystem paths can depend on the host machine and operating system. Therefore, `file:` fits fixtures provided by the test environment or an explicitly configured path; scripts committed with the project should usually live in `src/test/resources` so tests run consistently locally and in CI.

### 2.5. Do not confuse resource paths with source paths

The following declarations have different meanings:

```java
// Package-relative classpath resource
@Sql("seed.sql")

// Absolute classpath resource
@Sql("/db/seed.sql")

// Explicit classpath resource
@Sql("classpath:/db/seed.sql")

// Filesystem resource
@Sql("file:/opt/fixtures/seed.sql")
```

Do not write `@Sql("src/test/resources/db/seed.sql")` expecting Spring to understand it as a source resource location. Without a prefix, this string is treated as a classpath path relative to the test class's package. If you want to load a file from the filesystem, use `file:` and the actual filesystem path.

## 3. Default script detection mechanism

Spring TestContext can automatically detect a default script when `@Sql` declares neither `scripts` nor inline statements in `statements`.

The convention depends on where the annotation is placed:

- If `@Sql` is at the class level, Spring looks for a file named after the simple name of the test class plus the `.sql` extension, in the same package as the test class.
- If `@Sql` is at the method level, Spring looks for a file named after the simple name of the test class, followed by a dot, the method name, then `.sql`, also in the same package.

### 3.1. Default script at the class level

Suppose the test class is:

```java
package com.example.orders;

@SpringJUnitConfig(TestConfiguration.class)
@Sql
class OrderRepositoryTest {

    @Test
    void findsPendingOrders() {
        // ...
    }

    @Test
    void findsCompletedOrders() {
        // ...
    }
}
```

Because `@Sql` is declared at the class level without specifying `scripts` or `statements`, Spring searches for the default script:

```text
com/example/orders/OrderRepositoryTest.sql
```

In the project, the file typically lives at:

```text
src/test/resources/com/example/orders/OrderRepositoryTest.sql
```

A class-level script applies to the test methods in the class according to the declared execution phase. With the default `BEFORE_TEST_METHOD`, the script executes before each method in the class.

### 3.2. Default script at the method level

Suppose a test method is named `findByStatus`:

```java
package com.example.orders;

class OrderRepositoryTest {

    @Test
    @Sql
    void findByStatus() {
        // ...
    }
}
```

Spring searches for the script by convention:

```text
com/example/orders/OrderRepositoryTest.findByStatus.sql
```

Corresponding file in source resources:

```text
src/test/resources/com/example/orders/OrderRepositoryTest.findByStatus.sql
```

The Java method name is used to construct the file name. `@DisplayName` does not replace the method name in default script detection conventions.

### 3.3. Default file naming convention table

| `@Sql` location | Test class name | Test method name | Script Spring searches for |
|---|---|---|---|
| Class level | `OrderRepositoryTest` | Not applicable | `OrderRepositoryTest.sql` |
| Method level | `OrderRepositoryTest` | `findById` | `OrderRepositoryTest.findById.sql` |
| Method level | `AccountServiceTest` | `createsAccount` | `AccountServiceTest.createsAccount.sql` |

Files are searched in the package of the test class. For example, if the test class belongs to `com.example.account`, the default file for method `createsAccount` has the classpath path:

```text
com/example/account/AccountServiceTest.createsAccount.sql
```

This convention keeps scripts organized close to the test class and avoids repeating long paths in annotations.

### 3.4. When does Spring NOT search for a default script?

Spring only applies default script detection when neither script paths nor inline statements are declared. If `scripts` is specified, Spring uses that resource. If `statements` has values, Spring executes those inline SQL statements instead of inferring a default file.

Example not using a default script because a path is declared:

```java
@Test
@Sql("classpath:/db/orders/seed.sql")
void findsOrder() {
}
```

Example not using a default script because inline SQL statements are declared:

```java
@Test
@Sql(statements = "delete from orders where status = 'TEMP'")
void ignoresTemporaryOrders() {
}
```

If Spring needs to detect a default script but the resource matching the convention does not exist, the test will fail when processing the SQL annotation. In that case, create the expected default file or declare an explicit path. Do not create an empty file just to hide a configuration error if the test actually needs data.

## 4. Complete example of default scripts

Suppose there is a repository test:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.jdbc.Sql;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(OrderTestConfiguration.class)
@Sql
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void findsPendingOrders() {
        assertEquals(2, repository.countByStatus("PENDING"));
    }

    @Test
    @Sql
    void findsCompletedOrders() {
        assertEquals(1, repository.countByStatus("COMPLETED"));
    }
}
```

With the default configuration, Spring looks for two scripts:

```text
src/test/resources/com/example/orders/OrderRepositoryTest.sql
src/test/resources/com/example/orders/OrderRepositoryTest.findsCompletedOrders.sql
```

The class-level file can create the schema or base data needed by tests in the class. The method-level file provides data specific to the `findsCompletedOrders` scenario.

However, by default, a method-level `@Sql` **overrides** the class-level declaration for that method. Therefore, when `findsCompletedOrders()` has its own `@Sql`, Spring does not automatically run the class-level script for this method under the default mode. If both the class-level base script and the method-level script need to run, use `@SqlMergeMode(MERGE)` or explicitly declare the scripts to execute.

## 5. Explicit paths when controlling resource structure

Default script detection is useful when each test class/method has its own corresponding script. In projects with shared SQL layouts, file names not tightly coupled to test classes, or scripts living in a separate resource module, explicit paths should be declared.

### 5.1. One shared script across multiple tests

```java
@Sql("classpath:/db/test/schema.sql")
class AccountRepositoryTest {
    // ...
}
```

### 5.2. Base script and method-specific script

```java
@SpringJUnitConfig(TestConfiguration.class)
@Sql("classpath:/db/test/clean-and-schema.sql")
class OrderRepositoryTest {

    @Test
    @Sql("classpath:/db/test/orders/pending-orders.sql")
    void findsPendingOrders() {
        // ...
    }
}
```

In the default configuration, a method with its own `@Sql` overrides the class-level declaration. If `clean-and-schema.sql` still needs to run for this method, use merge mode or combine the required scripts in one declaration.

### 5.3. Multiple scripts in order

```java
@Test
@Sql(scripts = {
        "classpath:/db/test/cleanup.sql",
        "classpath:/db/test/insert-customers.sql",
        "classpath:/db/test/insert-orders.sql"
})
void loadsOrdersForCustomers() {
    // ...
}
```

The declaration order ensures reference data is created before dependent data. For example, if the `orders` table has a foreign key to `customers`, the customer script needs to execute before the order script.

## 6. Interaction between class-level and method-level @Sql

Spring allows declaring SQL scripts on both the class and the method. By default, a method-level declaration replaces the class-level declaration for that method. This mechanism is called `OVERRIDE`.

### 6.1. Default OVERRIDE

```java
@Sql("classpath:/db/test/base-data.sql")
class OrderRepositoryTest {

    @Test
    void usesBaseData() {
        // Only the base-data.sql script is applied.
    }

    @Test
    @Sql("classpath:/db/test/special-order-data.sql")
    void usesSpecialData() {
        // Method-level @Sql replaces class-level @Sql.
    }
}
```

This is the default behavior of `@SqlMergeMode`. It is useful when each method wants a completely independent fixture.

### 6.2. MERGE to combine class and method scripts

If you want the method-level script to run in addition after the class-level script, use `@SqlMergeMode`:

```java
@SpringJUnitConfig(TestConfiguration.class)
@Sql("classpath:/db/test/base-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class OrderRepositoryTest {

    @Test
    @Sql("classpath:/db/test/pending-orders.sql")
    void findsPendingOrders() {
        // Both base-data.sql and pending-orders.sql are applied.
    }
}
```

In merge mode, class-level declarations are combined with method-level declarations. Execution order runs the class-level declaration group first, followed by the method-level group, which suits preparing base data first and then adding a specific fixture.

`@SqlMergeMode` can be placed at the class or method level. When placed on a method, that configuration can alter the merge behavior for that specific method. When a test class has multiple inheritance levels, determine the effective merge mode to avoid surprises about which scripts are applied.

### 6.3. Default scripts in merge mode

When using `@Sql` without declaring scripts at the class or method level, Spring can detect the corresponding default file at each level. If you need to combine both the class-level default script and the method-level default script, use `@SqlMergeMode(MERGE)` to explicitly declare the intent.

Example resource structure:

```text
OrderRepositoryTest.sql
OrderRepositoryTest.findsPendingOrders.sql
```

With `MERGE`, the class-level base script can prepare shared schema/data and the method-level script supplements data for the scenario under test. If merging is not needed, keep the default `OVERRIDE` so each method defines its own fixture.

## 7. Script execution timing

`@Sql` has an `executionPhase` attribute to decide whether the script runs before or after the test method:

| Value | Timing | Common purpose |
|---|---|---|
| `BEFORE_TEST_METHOD` | Before each test method; default | Create schema, clear stale data, or load fixtures |
| `AFTER_TEST_METHOD` | After each test method | Clean up data or run post-check scripts |

Example:

```java
@Test
@Sql(
        scripts = "classpath:/db/test/seed.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(
        scripts = "classpath:/db/test/cleanup.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
void processesSeededData() {
    // ...
}
```

The two declarations above illustrate preparing and cleaning up at two phases. If cleanup only deletes data belonging to the test transaction, check the transaction mode and default rollback; a DELETE statement running inside a transaction about to roll back may itself be rolled back. Do not rely on an AFTER script to clean up data committed in an independent transaction without configuring the proper transaction mode.

## 8. Configuring how Spring reads SQL scripts

Resource paths specify **which file is read**. `@SqlConfig` controls **how the file's contents are parsed and executed**.

Example:

```java
@Sql(
        scripts = "classpath:/db/test/seed.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = ";",
                commentPrefix = "--"))
```

Common attributes:

| Attribute | Meaning |
|---|---|
| `encoding` | Encoding used to read the file, e.g. `UTF-8` |
| `separator` | Statement separator, defaults to `;` |
| `commentPrefix` | Line comment prefix, defaults to `--` |
| `blockCommentStartDelimiter` | Block comment opening delimiter, defaults to `/*` |
| `blockCommentEndDelimiter` | Block comment closing delimiter, defaults to `*/` |
| `dataSource` | Name of the DataSource bean to use if multiple datasources exist |
| `transactionManager` | Name of the transaction manager to use |
| `transactionMode` | How the script participates in or creates a transaction |
| `errorMode` | How errors are handled when executing the SQL script |

`@SqlConfig` can be declared at the class level for shared settings across `@Sql` declarations in the class, or nested directly inside an `@Sql` for local configuration. When declaring local config, keep in mind that unspecified attributes are merged with global configuration according to Spring's rules.

### 8.1. Encoding

If an SQL script contains Vietnamese or Unicode characters, save the file as UTF-8 and declare the corresponding encoding when needed:

```java
@Sql(
        scripts = "classpath:/db/test/vietnamese-data.sql",
        config = @SqlConfig(encoding = "UTF-8"))
```

Incorrect encoding can cause Vietnamese strings to corrupt on insert or cause the database to receive unexpected data.

### 8.2. Statement separator and comments

By default, Spring splits SQL statements using `;`. If a script uses a different delimiter, configure `separator` accordingly. Scripts can also contain line comments and block comments according to the parser configuration.

```sql
-- Create sample data for the test
insert into customer(id, name)
values (101, 'Nguyen Van A');

/* Order referencing the customer above */
insert into orders(id, customer_id, status)
values (501, 101, 'PENDING');
```

If a stored procedure or SQL block contains internal `;` characters, check the database's parser and delimiter; you can configure a different separator or split procedure creation into a dialect-appropriate script.

### 8.3. Script transaction mode

`@SqlConfig(transactionMode = ...)` controls whether the script runs in an existing transaction or its own transaction:

- `INFERRED` is the default: if a suitable active transaction exists, the script joins that transaction; otherwise, the script executes via `ResourceDatabasePopulator` without creating a new test transaction on its own.
- `ISOLATED`: the script runs in an independent transaction and that transaction is committed upon completion.

Example:

```java
@Sql(
        scripts = "classpath:/db/test/reference-data.sql",
        config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
```

With `ISOLATED`, data can persist after the test-managed transaction rolls back because the script committed in its own transaction. Only use this when that is the intended behavior; if the fixture should roll back with the test, keep the appropriate transaction mode so the script joins the test's transaction.

## 9. Default scripts and inline SQL statements

Not every data preparation step needs a `.sql` file. `@Sql` can accept `statements` to execute inline SQL:

```java
@Test
@Sql(statements = {
        "delete from orders where status = 'TEMP'",
        "insert into orders(id, status) values (900, 'PENDING')"
})
void loadsTemporaryOrder() {
    // ...
}
```

Inline statements suit a few short, clear SQL statements. For schemas or large fixtures, script files are easier to organize, read, and reuse.

If `statements` is declared, Spring does not need to infer a default script. Similarly, when `scripts` is declared, the specified path determines the resource to load.

Avoid cramming too much long SQL inside annotations, as it is hard to read, hard to manage ordering, and clutters the test class with data details. Move to resource files when a fixture has many statements or is reused.

## 10. Distinguishing @Sql from Spring Boot SQL initialization

A common misconception is thinking that `schema.sql` or `data.sql` are always the default scripts for `@Sql`. These are two distinct mechanisms.

| Mechanism | Managing component | Purpose |
|---|---|---|
| `@Sql` | Spring TestContext Framework | Execute scripts tied to test class/method by execution phase |
| `schema.sql`, `data.sql` in Spring Boot | Spring Boot SQL database initialization | Initialize schema and data at application startup per Boot configuration |
| `@Sql` default script detection | Spring TestContext test class/method naming convention | Locate `TestClass.sql` or `TestClass.testMethod.sql` |

If a test uses Spring Boot and the application automatically loads `schema.sql`/`data.sql`, those files may run when the context starts up. That does not mean `@Sql` automatically picks them up for each test method. `@Sql` without a path and without inline statements searches for files by the test class/method name described above.

To avoid loading data twice, identify which scripts run at context startup and which scripts run per test. Do not put the same insert statements in both `data.sql` and method-level `@Sql` unless intentional.

## 11. Common mistakes when Spring cannot find a script

### 11.1. Mistakenly using a path relative to the project root

Wrong expectation:

```java
@Sql("src/test/resources/db/seed.sql")
```

This is not a classpath root path. If the file is in `src/test/resources/db/seed.sql`, use:

```java
@Sql("/db/seed.sql")
```

or:

```java
@Sql("classpath:/db/seed.sql")
```

### 11.2. Forgetting package-relative resolution

If a test class in package `com.example.orders` uses:

```java
@Sql("seed.sql")
```

Spring searches for `com/example/orders/seed.sql`, not `seed.sql` at the classpath root. If you want it at the root, add a leading `/` or the `classpath:/` prefix.

### 11.3. Placing the file in the wrong source resource directory

Files in `src/test/java` are not automatically included on the classpath as regular resources. Scripts should reside in `src/test/resources` or a test resource directory configured for the build tool.

### 11.4. Case sensitivity mismatches

The Windows filesystem can be case-insensitive, whereas Linux CI is typically case-sensitive. `Seed.sql` and `seed.sql` may be treated as two different names. Keep file names and annotations matching in exact case.

### 11.5. Default script does not match the method name

If the method is named `findByStatus`, the default file must include the name portion:

```text
OrderRepositoryTest.findByStatus.sql
```

Do not use `@DisplayName`, a display test case name, or a descriptive Vietnamese name in place of the Java method name.

### 11.6. Method-level @Sql accidentally overrides class-level

A test class with a base script but a method declaring its own `@Sql` may skip running the base script because the default merge mode is `OVERRIDE`. If both are needed, use `@SqlMergeMode(MERGE)` or declare all required scripts.

### 11.7. Script is found but SQL fails to execute

Once the resource is loaded, subsequent errors may come from SQL syntax, table names, schema, dialect, database permissions, encoding, or transaction mode. Distinguish resource-not-found errors from statement execution errors; they occur at different stages.

## 12. Organizing SQL resources in a project

A common layout:

```text
src/test/resources/
  db/
    test/
      schema.sql
      cleanup.sql
      common/
        reference-data.sql
      orders/
        seed-pending-orders.sql
        seed-completed-orders.sql
      accounts/
        seed-active-accounts.sql
```

Then the test declares an explicit classpath path:

```java
@Sql("classpath:/db/test/common/reference-data.sql")
```

For scripts dedicated to a single test class, you can use default script detection and place files in the resource package matching the test class package. Both approaches are valid; choose one consistent convention in the module so team members can locate files easily.

Some organization principles:

- Place test scripts in `src/test/resources`, not mixed with production migrations unless there is a clear reason.
- Use `classpath:/...` for scripts shared across multiple packages.
- Use package-relative paths or default detection when a script belongs solely to one test class.
- Name files to describe the data or state being created.
- Separate cleanup, schema, and fixtures when ordering control is needed.
- Keep SQL compatible with the test database in use; if multiple dialects exist, organize fixtures by database or appropriate profile.
- Do not include credentials or real personal data in committed SQL fixtures.

## 13. Script path troubleshooting workflow

When `@Sql` cannot find a file or runs the wrong script, check in order:

1. Is `@Sql` on the class or on the method?
2. Does the annotation declare `scripts` or `statements`? If not, Spring will look for a default script.
3. If using default detection, do the class/method name and package match the convention?
4. If a path is declared, does it start with `/`, or have a `classpath:` or `file:` prefix?
5. If the path is package-relative, was it resolved against the test class's package?
6. Is the file on the test runtime classpath, typically `src/test/resources`?
7. Do the casing and `.sql` extension match?
8. Does a method-level `@Sql` override a class-level declaration?
9. Is `executionPhase` set to the expected execution time?
10. Was the resource found, but statements failed due to SQL, datasource, transaction, or schema?

To reduce ambiguity, switch to an explicit path such as `classpath:/db/test/seed.sql`. When default script detection is an intentional convention of the test suite, keep file names strictly aligned with the test class and method names.

## 14. Combined example with explicit paths and default detection

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.jdbc.SqlConfig;

@SpringJUnitConfig(OrderTestConfiguration.class)
@Sql(
        scripts = "classpath:/db/test/schema-and-reference-data.sql",
        config = @SqlConfig(encoding = "UTF-8"))
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class OrderRepositoryTest {

    @Test
    @Sql // Looks for OrderRepositoryTest.findsPendingOrders.sql in the same package
    void findsPendingOrders() {
        // Both the base script and method script are executed.
    }

    @Test
    @Sql("db/seed-completed-orders.sql")
    void findsCompletedOrders() {
        // Package-relative path: com/example/orders/db/seed-completed-orders.sql
        // The class-level base script is also merged.
    }
}
```

This example illustrates three mechanisms at once:

- The class-level script uses `classpath:` to point to a shared resource from the classpath root.
- Method `findsPendingOrders` declares no path, so Spring looks for the default file named after the class and method in package `com.example.orders`.
- Method `findsCompletedOrders` uses a package-relative path, so Spring looks in the `db` directory under the test package.
- `@SqlMergeMode(MERGE)` instructs Spring to combine the method-level declaration with the class-level script.

In a real project, ensure the files above exist on the test runtime classpath and the script contents match the schema. If a method does not need the base script, keep the default `OVERRIDE` or adjust merge mode at the appropriate method scope.

## 15. References

- [Spring Framework Reference — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): guide to `@Sql`, resource paths, default script detection, execution phases, and SQL configuration.
- [Spring Framework Javadoc — @Sql](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/Sql.html): definition of `scripts`, `statements`, `executionPhase`, and annotation declaration.
- [Spring Framework Javadoc — @SqlMergeMode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/SqlMergeMode.html): description of `OVERRIDE` and `MERGE` modes between class-level and method-level declarations.
- [Spring Framework Javadoc — @SqlConfig](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.html): description of encoding, separator, datasource, transaction manager, and script execution options.

`@Sql` script paths are resolved according to Spring Resource rules: paths without a prefix and not starting with `/` are resolved relative to the test class's package; paths starting with `/` are classpath-absolute; `classpath:` and `file:` explicitly specify the resource type. When neither scripts nor inline statements are declared, Spring searches for a default file based on the test class name at the class level or the test class name plus method name at the method level. Understanding these two rules helps organize SQL fixtures clearly, avoid missing-resource errors, and precisely control the data prepared for each test.
