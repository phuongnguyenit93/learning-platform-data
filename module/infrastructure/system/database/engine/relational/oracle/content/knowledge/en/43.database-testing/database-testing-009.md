# Testing Packages, Functions, and Procedures with utPLSQL or JDBC

Oracle PL/SQL often holds a significant share of logic executing close to the data: packages, functions, procedures, triggers, and business-supporting routines. When Java/Spring Boot invokes these routines via JDBC or JPA, system quality depends on both the PL/SQL logic and the contract between the database and the application. A routine might work when a DBA calls it in SQL Developer yet still fail when invoked from Java due to parameter types, execution privileges, transaction boundaries, session state, or how the driver maps results.

Two complementary testing approaches exist:

- **utPLSQL** runs tests directly inside Oracle Database. It is ideal for verifying PL/SQL logic, data state, exceptions, package APIs, and database-enforced rules.
- **JDBC/JUnit** runs on the Java side, invoking packages/functions/procedures via the real JDBC driver. It is ideal for verifying the contract between the application and the database: bind parameters, `IN`/`OUT`, `REF CURSOR`, data types, transactions, privileges, and error handling.

Do not pick one approach and discard the other when PL/SQL is an important part of the application. utPLSQL tests logic near the database; JDBC integration tests verify the real path from Java to Oracle. Tests require independent data, repeatable results, and clear cleanup rules.

## 1. Objectives and scope of PL/SQL testing

A package typically groups related procedures and functions into an API. The public specification defines routine names, parameter types, return types, and exceptions that may be raised; the package body implements the logic. When testing, focus on the public behavior consumed by applications or other packages.

Example order-management package:

    CREATE OR REPLACE PACKAGE order_api AS
      PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_amount      IN NUMBER,
        p_order_id    OUT NUMBER
      );

      FUNCTION calculate_total(
        p_order_id IN NUMBER
      ) RETURN NUMBER;

      PROCEDURE approve_order(
        p_order_id IN NUMBER,
        p_actor    IN VARCHAR2
      );
    END order_api;
    /

Tests must verify:

- Routines accept valid inputs and return expected results.
- Invalid inputs are rejected according to the defined contract.
- Functions return accurate values, including `NULL` and arithmetic boundaries where permitted.
- Procedures modify the right rows and only the expected rows.
- `OUT` parameters, return values, and `REF CURSOR`s have the right types, order, and contents.
- Transactions do not commit or roll back unintentionally.
- Business exceptions are raised with stable codes and messages.
- `EXECUTE` privileges, privileges on dependent objects, and schema resolution are correct.
- Results do not depend on leftover test data, NLS, timezones, or stale session state.
- Java clients can invoke routines with proper parameter binding and result reading.

### 1.1. Distinguishing unit tests from integration tests

Unit tests verify a unit of logic within a controlled scope. In PL/SQL, a unit may be a function, procedure, or public package API. However, PL/SQL routinely accesses tables, sequences, views, and other packages; tests running in real Oracle may be considered database unit tests even though they still exercise the database engine.

Integration tests verify multiple components working together, for example:

- Packages calling other packages and querying multiple tables.
- Triggers, constraints, and foreign keys participating in a transaction.
- Java calling procedures through Oracle JDBC.
- The Spring transaction manager coordinating with JDBC connections.
- `OUT` parameters or cursors mapped into DTOs.
- Application user privileges differing from package owner privileges.

A well-structured suite separates fast, focused tests from broad integration tests. When a test fails, the team should immediately know whether the fault lies in PL/SQL logic, schema fixtures, privileges, the driver, or Java invocation.

### 1.2. Testing against the public contract

Do not depend on package-private helpers or internal implementation details when they are not part of the API. Invoke public procedures/functions and observe:

- Return values.
- `OUT`/`IN OUT` parameters.
- Rows created, updated, or deleted.
- Exceptions and error codes.
- Documented side effects.
- Consistency after commit/rollback.

Private procedures in the package body are normally tested indirectly through the public API. This allows refactoring implementations without rewriting the entire test suite just because helper names changed.

## 2. What is utPLSQL?

utPLSQL is a PL/SQL testing framework that runs inside Oracle Database. Tests are written as separate PL/SQL packages that declare suites, test cases, setup/teardown hooks, and assertions. A runner executes the suite and returns detailed results on passing, failing, or errored tests.

A common layout:

    Application schema
      +-- ORDER_API package
      +-- ORDER_TABLE
      +-- CUSTOMER_TABLE

    Test schema
      +-- TEST_ORDER_API package
      +-- utPLSQL framework objects

    utPLSQL runner
      +-- discovers suite annotations
      +-- runs setup and test procedures
      +-- evaluates expectations
      +-- reports results

The framework should be installed according to instructions for the utPLSQL version compatible with your Oracle Database release. Depending on organizational policy, the framework may live in a dedicated schema or follow a DBA-approved layout. Never install testing frameworks into a production schema just to run tests.

### 2.1. Why test directly inside the database?

utPLSQL can inspect data and behavior directly in the exact database engine where packages execute. It reduces test harness boilerplate and supports PL/SQL testing without spinning up a Java application for every assertion.

Common benefits:

- Tests can call packages, functions, and procedures directly.
- Assertions can compare scalars, collections, and query results.
- Setup/teardown logic is organized into hooks.
- Suites can be selected individually or by package/path.
- Tests can run from SQL*Plus, SQLcl, SQL Developer, or compatible CI runners.
- Structured results integrate easily into test pipelines.

utPLSQL does not replace Java-side testing. It does not prove that the Oracle JDBC driver binds types properly, that Spring transactions behave as intended, or that the application user holds sufficient privileges.

### 2.2. Installation and privileges

Installing utPLSQL is a database administration task. Clarify:

- Oracle Database version and supported features.
- utPLSQL framework version.
- Framework owner schema.
- Schema containing test packages.
- Privileges to execute the runner and access tested packages.
- How suites are run locally, in CI, and in integration environments.
- How to upgrade or uninstall the framework per administrative procedures.

The test user should only have privileges required to execute suites and access fixtures. Avoid granting `DBA` to test accounts. If tests must access objects in another schema, grant privileges directly or through mechanisms supported by the framework/database and verify actual privileges in the execution context.

## 3. Writing your first utPLSQL suite

utPLSQL discovers suites via annotations placed inside comments of the package specification. Common annotations include:

- `--%suite`: marks a package as a test suite.
- `--%suitepath`: groups suites in a hierarchical tree.
- `--%test`: marks a procedure as a test case.
- `--%beforeall` / `--%afterall`: hooks running once before/after the entire suite.
- `--%beforeeach` / `--%aftereach`: hooks running before/after each test.
- `--%context`: groups tests by context.
- `--%rollback(auto)` or `--%rollback(manual)`: declares rollback handling per framework version capabilities.

Example suite testing an addition function:

    CREATE OR REPLACE PACKAGE test_math_api AS
      --%suite(Math API)
      --%suitepath(Database.Unit)

      --%test(Adds two positive numbers)
      PROCEDURE adds_positive_numbers;

      --%test(Handles zero)
      PROCEDURE handles_zero;
    END test_math_api;
    /

Package body:

    CREATE OR REPLACE PACKAGE BODY test_math_api AS

      PROCEDURE adds_positive_numbers IS
        l_actual NUMBER;
      BEGIN
        l_actual := math_api.add_numbers(2, 3);

        ut.expect(l_actual).to_equal(5);
      END adds_positive_numbers;

      PROCEDURE handles_zero IS
        l_actual NUMBER;
      BEGIN
        l_actual := math_api.add_numbers(0, 8);

        ut.expect(l_actual).to_equal(8);
      END handles_zero;

    END test_math_api;
    /

Run the suite via the runner:

    BEGIN
      ut.run('TEST_SCHEMA.TEST_MATH_API');
    END;
    /

Replace schema and package names with your actual environment. Suite selection syntax, output reporters, and runner parameters vary by utPLSQL version.

### 3.1. Organizing suites by business package

A test package usually corresponds to one application package or a cohesive group of behaviors. Example:

    TEST_ORDER_API
      +-- create_order
      +-- calculate_total
      +-- approve_order
      +-- rejects_unknown_customer
      +-- rejects_negative_amount

Test names should describe behavior, not merely repeat routine names. When a test fails, logs should immediately show which condition was violated.

### 3.2. One test case should verify one primary behavior

For example, a `create_order` test should not simultaneously test tax calculation, email sending, inventory updates, and report generation if those behaviors can be tested independently. Small tests make failure causes easy to isolate and lower maintenance costs.

A single test can contain multiple assertions when they describe one cohesive contract—such as a procedure returning an `OUT` ID and inserting one matching row with the right customer/amount. Avoid packing unrelated scenarios into one test.

## 4. Assertions and expectations in utPLSQL

utPLSQL uses the `ut.expect` API to express expectations. Common matchers:

    ut.expect(l_actual).to_equal(l_expected);
    ut.expect(l_actual).to_be_null();
    ut.expect(l_actual).not_to_be_null();
    ut.expect(l_actual).to_be_true();
    ut.expect(l_actual).to_be_false();
    ut.expect(l_actual).to_be_greater_than(0);

Verify exact matcher names and overloads in the documentation for your installed utPLSQL version. The examples above show common usage; do not assume every PL/SQL type or custom type has a built-in default matcher.

### 4.1. Testing functions returning scalars

Suppose a function:

    FUNCTION calculate_discount(
      p_amount IN NUMBER,
      p_rate   IN NUMBER
    ) RETURN NUMBER;

Test:

    PROCEDURE calculates_discount IS
      l_actual NUMBER;
    BEGIN
      l_actual := pricing_api.calculate_discount(100, 0.10);

      ut.expect(l_actual).to_equal(10);
    END;

Also test boundary inputs:

- Zero amount.
- Zero rate.
- Maximum allowed rate.
- `NULL` values if allowed by contract.
- Negative values if the routine must reject them.
- Precision/rounding according to currency rules.

For financial decimals, do not test using arbitrary floating-point comparisons. Oracle `NUMBER` and Java `BigDecimal` are far better suited for exact decimal values. Clearly specify scale, rounding mode, and currency rules.

### 4.2. Testing procedures that mutate data

Suppose a procedure:

    PROCEDURE set_order_status(
      p_order_id IN NUMBER,
      p_status   IN VARCHAR2
    );

The test can prepare an order, invoke the procedure, and query back:

    PROCEDURE changes_order_status IS
      l_status order_header.status%TYPE;
    BEGIN
      INSERT INTO order_header(order_id, status)
      VALUES (900001, 'NEW');

      order_api.set_order_status(900001, 'APPROVED');

      SELECT status
      INTO l_status
      FROM order_header
      WHERE order_id = 900001;

      ut.expect(l_status).to_equal('APPROVED');
    END;

Fixtures must use isolated keys without touching shared data. If the framework rolls back automatically, do not commit inside the test. If the package commits internally, use a dedicated test database/schema or a controlled cleanup strategy.

### 4.3. Checking multiple conditions

You can check `OUT` parameters, row counts, and row column values:

    PROCEDURE creates_order_with_expected_values IS
      l_order_id NUMBER;
      l_customer_id NUMBER;
      l_amount NUMBER;
      l_status VARCHAR2(30);
    BEGIN
      order_api.create_order(
        p_customer_id => 7001,
        p_amount      => 125.50,
        p_order_id    => l_order_id
      );

      SELECT customer_id, amount, status
      INTO l_customer_id, l_amount, l_status
      FROM order_header
      WHERE order_id = l_order_id;

      ut.expect(l_order_id).not_to_be_null();
      ut.expect(l_customer_id).to_equal(7001);
      ut.expect(l_amount).to_equal(125.50);
      ut.expect(l_status).to_equal('NEW');
    END;

If assertion order aids diagnostics, split tests by behavior or attach descriptive failure messages. Never check only the `OUT` ID and assume all underlying data was persisted accurately.

### 4.4. Testing collections and query results

When a routine returns a collection or ref cursor, tests must verify both element count and contents. Project results into a deterministically ordered set before comparing. Without `ORDER BY`, SQL row order is not guaranteed; tests must never depend on incidental ordering.

For query results, consider matcher/table comparisons or helpers supported by your utPLSQL version. When only checking a specific condition, querying `COUNT`, `EXISTS`, or aggregates can make tests clearer.

## 5. Fixtures: preparing and cleaning up test data

A fixture is the data and state required for a test to run independently. Good fixtures are deterministic, small, reproducible, and independent of test order.

For example, an order test requires:

- An active customer.
- An order that does not yet exist.
- A product with a known price.
- Inventory with sufficient quantity.
- Appropriate currency/exchange rate if the package calculates prices.
- Related sequences, triggers, and constraints in normal state.

Do not pick a production customer or random ID from a shared database. Every test must know precisely which data belongs to it.

### 5.1. beforeeach and aftereach hooks

Hooks can create and clean up fixtures for each test:

    CREATE OR REPLACE PACKAGE test_order_api AS
      --%suite(Order API)

      --%beforeeach
      PROCEDURE setup;

      --%aftereach
      PROCEDURE cleanup;

      --%test(Creates a new order)
      PROCEDURE creates_order;
    END test_order_api;
    /

Package body:

    CREATE OR REPLACE PACKAGE BODY test_order_api AS

      PROCEDURE setup IS
      BEGIN
        INSERT INTO customer(customer_id, customer_name, active_flag)
        VALUES (7001, 'UTPLSQL CUSTOMER', 'Y');
      END;

      PROCEDURE cleanup IS
      BEGIN
        DELETE FROM order_line WHERE order_id IN (
          SELECT order_id
          FROM order_header
          WHERE customer_id = 7001
        );

        DELETE FROM order_header
        WHERE customer_id = 7001;

        DELETE FROM customer
        WHERE customer_id = 7001;
      END;

      PROCEDURE creates_order IS
        l_order_id NUMBER;
      BEGIN
        order_api.create_order(7001, 125.50, l_order_id);
        ut.expect(l_order_id).not_to_be_null();
      END;

    END test_order_api;
    /

This is an illustrative structure. If the test runner rolls back automatically, cleanup may not need to delete transactional changes; if using manual rollback or routines that commit, design explicit cleanup. Fixture data must avoid collisions during parallel runs.

### 5.2. beforeall and afterall

`beforeall` runs once before the suite; `afterall` runs once after the suite. Use them for shared state with a clear lifecycle, such as immutable reference data within test transactions or initializing package context.

Do not use `beforeall` to create mutable fixtures modified by multiple tests unless every test resets state. Order-dependent tests easily break when runners reorder suites or run tests in parallel.

### 5.3. Automatic and manual rollback

In utPLSQL, rollback annotations control how the runner manages test transactions per framework capabilities. Auto mode typically rolls back transactional changes after each test so data does not leak into the next test. Manual mode is for tests requiring explicit transaction/cleanup control.

Understand clearly:

- Transactional DML rolls back if uncommitted.
- `COMMIT` inside a package alters the transaction boundary and can leave data behind after the test.
- DDL normally triggers an implicit commit; never create/drop tables inside normal tests.
- Autonomous transactions do not roll back with the caller's transaction.
- Sequence `NEXTVAL` is not returned on rollback.
- Sending emails, making HTTP calls, enqueueing messages, or writing files are out-of-transaction side effects that do not vanish on rollback.
- Global temporary tables follow transaction or session semantics depending on configuration; session pooling can retain state if not cleaned properly.

Never write tests assuming rollback reverses every side effect. For self-committing routines or external calls, use dedicated test schemas/databases, appropriate mocks/stubs, or intentional cleanup.

### 5.4. Do not depend on exact sequence values

Oracle sequences can produce gaps due to caching, rollbacks, concurrency, or instance restarts. Tests must not expect the next ID to equal a fixed number. Instead verify the ID is non-`NULL`, exists in the table, and links properly to child rows.

## 6. Testing exceptions and business errors with utPLSQL

A routine must normally reject invalid inputs with well-defined exceptions. Examples:

- Non-existent customer.
- Already-cancelled order.
- Negative amount.
- Disallowed state transition.
- Caller lacks execution permission.
- Locked resource or concurrent data modification.

Tests must verify the routine rejects the right cases and leaves no partial data behind.

Example package raising a business error:

    PROCEDURE approve_order(p_order_id IN NUMBER) IS
      l_status order_header.status%TYPE;
    BEGIN
      SELECT status
      INTO l_status
      FROM order_header
      WHERE order_id = p_order_id
      FOR UPDATE;

      IF l_status <> 'NEW' THEN
        RAISE_APPLICATION_ERROR(
          -20041,
          'Only NEW orders can be approved'
        );
      END IF;

      UPDATE order_header
      SET status = 'APPROVED'
      WHERE order_id = p_order_id;
    END;

State-error tests must confirm the procedure actually raises the business error with the expected code. You can use exception expectations/helpers provided by your utPLSQL version. A plain, readable PL/SQL approach independent of exception matchers catches the exception and asserts `SQLCODE`:

    PROCEDURE rejects_approved_order IS
      l_error_code NUMBER;
    BEGIN
      INSERT INTO order_header(order_id, status)
      VALUES (900002, 'APPROVED');

      BEGIN
        order_api.approve_order(900002);
      EXCEPTION
        WHEN OTHERS THEN
          l_error_code := SQLCODE;
      END;

      ut.expect(l_error_code).to_equal(-20041);
    END;

If the routine raises no error, `l_error_code` stays `NULL` and the test fails. To verify messages, inspect `SQLERRM` inside the exception handler and match stable substrings. Avoid asserting the entire error text if it varies by language or Oracle version.

### 6.1. Do not swallow exceptions accidentally

The following pattern is harmful:

    BEGIN
      order_api.approve_order(p_order_id);
    EXCEPTION
      WHEN OTHERS THEN
        NULL;
    END;

If exceptions are swallowed, callers never know the operation failed and tests can report false passes. Only catch exceptions when taking concrete action: translating to a business error, adding context and re-raising, rolling back appropriately, or logging per policy.

In tests, always distinguish "received the expected exception" from "routine threw no exception". Never merely assert that the test procedure ran to completion.

## 7. Testing functions with side effects and determinism

Functions are frequently invoked inside SQL expressions, so function design should favor pure computation and return values. Functions performing DML or complex side effects can face restrictions when called from SQL and behave unpredictably.

When testing functions:

- Test normal, boundary, and `NULL` inputs.
- Verify precision/rounding.
- Test deterministic behavior only when the contract genuinely guarantees identical output for identical input.
- Never assume a function executes exactly once per row in a SQL expression; the optimizer can alter evaluation.
- Test exceptions on invalid inputs.
- If a function reads tables, prepare isolated fixture data.

Example:

    FUNCTION calculate_tax(
      p_net_amount IN NUMBER,
      p_rate       IN NUMBER
    ) RETURN NUMBER;

Tests can verify amount `100`, rate `0.08` returns `8`; amount `0` returns `0`; `NULL` rate follows contract; and negative numbers are rejected if business rules forbid them.

Avoid calling random functions or `SYSDATE` directly inside uncontrolled tests. For time-dependent logic, pass a reference timestamp into the routine or use an abstraction/test seam to test month-ends, timezones, and expiration boundaries.

## 8. Testing package state and session state

PL/SQL packages can hold global variables, constants, cursors, or state initialized in the package initialization block. Package state typically persists for the lifetime of the session after the first invocation.

If a connection pool reuses sessions, a subsequent request can observe package state mutated by an earlier request. Tests running on a single session may fail to catch this issue.

Scenarios to test:

- Procedures mutating package global variables.
- Packages caching data per session.
- Package initialization reading NLS or timezone settings.
- `DBMS_SESSION.SET_CONTEXT` setting application contexts.
- `DBMS_APPLICATION_INFO` setting `MODULE`/`ACTION`.
- Temporary tables using `ON COMMIT PRESERVE ROWS`.
- Packages invalidated or recompiled while a session retains state.

utPLSQL tests may execute multiple tests within one session or let the runner manage sessions in specific ways. Verify package state behavior and reset state explicitly when packages are stateful. Never rely on each test opening a fresh connection unless the runner genuinely does so.

If a package requires stateless behavior for application pools, design the API to pass state via parameters and clear contexts inside `finally`/transaction boundaries. Run integration tests through the pool to test session reuse.

## 9. Testing procedures/functions from Java via JDBC

JDBC integration tests verify how the Java application actually invokes PL/SQL. Use an Oracle JDBC driver compatible with your JDK/database and connect to a dedicated test database.

A Java test should verify:

- `CallableStatement` calls the exact package/routine.
- `IN` parameters bind with the right types and order.
- `OUT` parameters are registered with appropriate JDBC types.
- Function return values are registered at the right position.
- `REF CURSOR`s are read and closed properly.
- `SQLException`s map accurately.
- Transactions commit/roll back as intended.
- Database state after execution matches the contract.

### 9.1. JUnit 5 and DataSource

Example test structure:

    @SpringBootTest
    class OrderApiJdbcTest {

        @Autowired
        DataSource dataSource;

        @Test
        void createsOrderAndReturnsId() throws Exception {
            try (Connection connection = dataSource.getConnection()) {
                // call the package procedure
            }
        }
    }

You can use the Spring Boot context to obtain the `DataSource` and application-like configuration. For simpler tests, instantiate a test `DataSource` directly. Either way, tests must run against real Oracle or a compatible Oracle environment—never solely mock H2 when validating Oracle PL/SQL, packages, types, or driver behavior.

### 9.2. Calling procedures with IN and OUT parameters

Suppose:

    PROCEDURE create_order(
      p_customer_id IN NUMBER,
      p_amount      IN NUMBER,
      p_order_id    OUT NUMBER
    );

Java JDBC:

    String call = "{ call order_api.create_order(?, ?, ?) }";

    try (Connection connection = dataSource.getConnection();
         CallableStatement statement =
             connection.prepareCall(call)) {

        statement.setLong(1, 7001L);
        statement.setBigDecimal(2, new BigDecimal("125.50"));
        statement.registerOutParameter(3, Types.NUMERIC);

        statement.execute();

        BigDecimal orderId = statement.getBigDecimal(3);
        assertNotNull(orderId);
    }

Use `BigDecimal` for Oracle `NUMBER` when decimal precision matters, especially currency. `setLong` works for integers within `long` range; if `NUMBER` has larger precision, use `BigDecimal`.

Parameter order in `CallableStatement` must match the routine signature. If the package API changes parameter ordering or types, these tests catch it immediately.

### 9.3. Calling scalar-returning functions

Functions with return values must register the return parameter at the first position in JDBC escape calls:

    FUNCTION calculate_total(p_order_id IN NUMBER)
      RETURN NUMBER;

Java:

    String call = "{ ? = call order_api.calculate_total(?) }";

    try (Connection connection = dataSource.getConnection();
         CallableStatement statement =
             connection.prepareCall(call)) {

        statement.registerOutParameter(1, Types.NUMERIC);
        statement.setLong(2, 900001L);

        statement.execute();

        BigDecimal total = statement.getBigDecimal(1);
        assertEquals(new BigDecimal("125.50"), total);
    }

You can use a PL/SQL block instead of escape syntax when tighter control is needed:

    BEGIN
      ? := order_api.calculate_total(?);
    END;

Escape call syntax is usually concise for scalar returns. Check the Oracle JDBC driver version and how the driver handles actual return types.

### 9.4. Procedures with IN OUT parameters

An `IN OUT` parameter both receives an input value and returns an updated value after execution. JDBC must register the output and bind the input at the same index:

    String call = "{ call account_api.normalize_code(?) }";

    try (CallableStatement statement =
             connection.prepareCall(call)) {

        statement.setString(1, " ab-100 ");
        statement.registerOutParameter(1, Types.VARCHAR);
        statement.execute();

        String normalized = statement.getString(1);
        assertEquals("AB-100", normalized);
    }

Driver support for `set` vs. `register` ordering varies; follow a consistent, tested convention. Read `OUT` values only after `execute`, never before execution.

### 9.5. Calling PL/SQL blocks directly

For complex signatures or routines requiring a PL/SQL block, use:

    String plsql = """
        BEGIN
          order_api.approve_order(?);
        END;
        """;

    try (CallableStatement statement =
             connection.prepareCall(plsql)) {

        statement.setLong(1, 900001L);
        statement.execute();
    }

Text blocks require Java 15 or newer. On older Java versions, use string concatenation or supported multiline string literals. Never concatenate input values directly into PL/SQL text; bind with `?` placeholders.

## 10. Reading REF CURSORs from JDBC

Procedures can return `SYS_REFCURSOR` to expose result sets. Oracle JDBC supports `REF CURSOR` via `OracleTypes.CURSOR` or `Types.REF_CURSOR` depending on driver/JDBC API version.

Package example:

    PROCEDURE list_orders(
      p_customer_id IN NUMBER,
      p_result      OUT SYS_REFCURSOR
    );

Java example with Oracle JDBC type:

    try (Connection connection = dataSource.getConnection();
         CallableStatement statement =
             connection.prepareCall(
                 "{ call order_api.list_orders(?, ?) }")) {

        statement.setLong(1, 7001L);
        statement.registerOutParameter(2, OracleTypes.CURSOR);
        statement.execute();

        try (ResultSet rs = (ResultSet) statement.getObject(2)) {
            while (rs.next()) {
                long orderId = rs.getLong("ORDER_ID");
                String status = rs.getString("STATUS");
            }
        }
    }

`OracleTypes.CURSOR` resides in the Oracle JDBC API; import the right package for your driver version. If using `Types.REF_CURSOR`, verify driver support. Always close `ResultSet`, `CallableStatement`, and `Connection` via try-with-resources.

Never read a cursor after the connection has been returned to the pool. `ResultSet` depends on an open statement/connection. To return data up to the service layer, map rows into DTOs or collections before closing resources.

## 11. Testing transactions and rollbacks from JDBC

JDBC tests must clearly define who owns the transaction. When the test manages the connection directly, disable auto-commit, invoke the procedure, inspect data on the same connection, and then roll back.

Example:

    @Test
    void rollsBackOrderCreation() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                callCreateOrder(connection, 7001L,
                    new BigDecimal("125.50"));

                int count = countOrdersForCustomer(connection, 7001L);
                assertEquals(1, count);
            } finally {
                connection.rollback();
            }
        }
    }

This example assumes the procedure does not `COMMIT` itself and operates inside the caller's transaction. If the procedure commits internally, Java's rollback cannot undo the committed work.

In Spring Boot, tests can use `@Transactional` to roll back after each test when both the transaction manager and test execution coordinate the transaction. However, understand clearly:

- A procedure executing `COMMIT` ends the session's transaction.
- Autonomous transactions operate outside the caller's transaction.
- Data written by a separate connection belongs to a separate transaction.
- HTTP calls to external services do not participate in the local transaction.
- DDL triggers implicit commits in Oracle.
- Tests may observe different data depending on connection/session.

Never assume `@Transactional` in a test automatically cleans up all data created by PL/SQL. Inspect the package body and transaction contract before relying on automatic rollback.

### 11.1. Avoid relying on unintended commits in tests

If a business procedure insists on committing internally, consider redesigning transaction ownership or running integration tests on a resettable schema/database. Routines intended to compose inside application transactions should normally let callers control commit/rollback unless the contract explicitly dictates otherwise.

If the package cannot be changed, cleanup must delete committed data by isolated keys. Never use production tables or shared data to test self-committing routines.

### 11.2. Spring @Transactional tests

Example:

    @SpringBootTest
    @Transactional
    class OrderServiceIntegrationTest {

        @Autowired
        OrderService service;

        @Test
        void createsOrder() {
            Long id = service.createOrder(
                new OrderRequest(7001L, new BigDecimal("125.50"))
            );

            assertNotNull(id);
        }
    }

Spring test transactions typically roll back after the test unless explicitly committed. However, if the package commits or runs an autonomous transaction, that data will persist. For tests verifying commit visibility from another connection, configure dedicated test transactions and explicit cleanup.

## 12. Testing exceptions from JDBC

Oracle JDBC typically throws `SQLException` when PL/SQL raises an exception. For `RAISE_APPLICATION_ERROR`, the application error code normally appears in `SQLException.getErrorCode()` as the corresponding Oracle code—usually the positive counterpart of `-20xxx`; verify on your active driver.

Example:

    @Test
    void rejectsApprovalForClosedOrder() throws Exception {
        try (Connection connection = dataSource.getConnection();
             CallableStatement statement =
                 connection.prepareCall(
                     "{ call order_api.approve_order(?) }")) {

            statement.setLong(1, 900003L);

            SQLException error =
                assertThrows(SQLException.class, statement::execute);

            assertEquals(20041, error.getErrorCode());
        }
    }

Do not compare full error messages if messages vary by NLS or Oracle version. Prefer error codes and stable contract message substrings if needed.

If the application layer translates `SQLException` into a domain exception, write service tests verifying that mapping. For instance, `ORA-20041` might map to `OrderStateConflictException`, returning HTTP 409 to REST clients per API contract. Separating database error tests from HTTP mapping tests speeds up root-cause isolation.

## 13. Testing data types and null parameters

A common mistake in JDBC calls is binding the wrong type or mishandling `NULL`. Oracle `NUMBER`, `VARCHAR2`, `DATE`, `TIMESTAMP`, `CLOB`, `BLOB`, collections, and object types each have specific binding rules.

Example binding `NULL`:

    statement.setNull(1, Types.NUMERIC);

For `DATE`/`TIMESTAMP` parameters, use `java.time`/JDBC 4.2 where supported by the driver and choose the right semantics. For Oracle `DATE` holding hours/minutes/seconds, avoid `java.sql.Date` if time-of-day must be preserved. For `TSTZ`/`TSLTZ`, verify timezone/session semantics.

For `BigDecimal`, avoid constructing from `double`:

    new BigDecimal(0.1)

Because binary floating-point representation can introduce imprecise decimal digits. Use:

    new BigDecimal("0.10")

Tests should cover:

- Allowed and disallowed `NULL` inputs.
- Large numbers, high scales, and rounding.
- Empty strings and `NULL` under Oracle `VARCHAR2` semantics.
- Unicode and maximum lengths.
- Datetimes, timezones, and fractional seconds.
- `OUT` parameters returning `NULL`.
- Empty `REF CURSOR`s.
- Empty collections and `NULL` elements.

Oracle treats empty `VARCHAR2` strings as `NULL` in many contexts. When Java passes an empty string, do not assume the database preserves it as a distinct non-`NULL` empty value.

## 14. Testing privileges and execution context

A package may succeed when tested as the schema owner yet fail when invoked by the application user. Common causes include missing privileges, synonyms, `current_schema`, or missing grants on dependent objects.

Verify:

- Does the application user hold `EXECUTE` on the package?
- Does the package run with `AUTHID DEFINER` or `AUTHID CURRENT_USER`?
- Does the package owner hold privileges on dependent tables/views/packages?
- Were privileges granted directly or via roles, and does the execution context utilize those roles?
- Do synonyms point to the right owner/object?
- Do the database service and PDB match the target environment?
- Do VPD, application contexts, or policies alter outcomes?

Example grant:

    GRANT EXECUTE ON order_api TO app_user;

Do not grant `DBA` or broad DML privileges if the application only needs to invoke packages. For definer-rights packages, the owner requires direct object grants per Oracle's stored PL/SQL rules.

JDBC integration tests should connect as the actual application user or an account with equivalent privileges. Running all tests as `SYSTEM`/`SYS` masks privilege bugs.

## 15. Testing package dependencies and mocks/stubs

PL/SQL packages may depend on other packages, sequences, tables, database links, or external services. Tests may need to control dependencies for stable results.

Common techniques:

- Extract pure calculation logic into small functions for independent testing.
- Pass dependencies or timestamp parameters instead of reading `SYSDATE` directly.
- Provision a dedicated test schema with isolated fixtures.
- Use package interfaces/wrappers to swap dependencies in tests when architecture permits.
- Deploy contract-matching test-double packages in a test schema when safe deployment mechanisms exist.
- Use stubbed database links/services in integration test environments.
- For off-database side effects, write to an outbox/event table for verification instead of calling external systems in unit tests.

Do not mock so deeply that tests only validate the mocks. Maintain final integration tests exercising real packages and dependencies.

## 16. Testing concurrency and locking

A procedure may pass single-threaded tests yet fail when multiple sessions update the same data concurrently. Common issues:

- Lost updates.
- Deadlocks.
- Unique constraint races.
- `SELECT FOR UPDATE` timeouts.
- Lock contention.
- Sequence/number allocation assumptions.
- Isolation and read consistency.

Concurrency tests require multiple independent connections/sessions and concurrent coordination. utPLSQL tests sequential logic within a session; JDBC/JUnit or dedicated harnesses are better suited for spawning concurrent sessions and measuring outcomes.

Example of two transactions approving the same order simultaneously:

    Session A                         Session B
    ---------                         ---------
    SELECT order FOR UPDATE
    UPDATE status = APPROVED
                                      SELECT order FOR UPDATE (wait)
    COMMIT
                                      resumes and reads current state
                                      detects status is no longer NEW
                                      raises business error

Tests must confirm only one request succeeds, the other receives the expected conflict error per contract, and final data remains valid. Use latches/barriers or deterministic test synchronization to reproduce race conditions; never rely on random sleeps.

## 17. Organizing test suites in CI/CD

A pipeline can be structured into layers:

    Commit / Pull Request
          |
          v
    Compile PL/SQL and schema migration
          |
          v
    utPLSQL unit suites
          |
          v
    Java JDBC integration tests
          |
          v
    Service / API integration tests
          |
          v
    Deployment candidate

Each layer needs dedicated databases/schemas or proper fixture isolation. Never run tests concurrently over shared mutable data where conflicts can occur.

### 17.1. Running utPLSQL in a pipeline

The pipeline should:

1. Start an Oracle test database or allocate a dedicated test schema.
2. Deploy migrations and packages under test.
3. Install/verify a compatible version of the utPLSQL framework.
4. Grant test runner privileges.
5. Run selected suites.
6. Collect reports and logs.
7. Fail the build on any test failure/error.
8. Tear down the test environment per policy.

The runner can be invoked via SQLcl/SQL*Plus or compatible tooling. Reporter syntax, exit codes, and suite selectors depend on the framework version. Do not simply `grep` for `PASS` in stdout; use structured reporters/exit statuses if supported by the pipeline.

### 17.2. Running JDBC integration tests

The Java pipeline requires:

- An Oracle database with matching package and schema migration versions.
- An Oracle JDBC driver matching the JDK/runtime.
- Test connection secrets injected securely.
- A test user with privileges matching the application user.
- Dedicated JUnit/Spring test profiles.
- Timeouts and cleanup to avoid hanging tests or leaked sessions.
- SQL error logs with sensitive data masked.

When using Oracle Free/XE or database containers in CI, confirm the image/version supports the features required by your packages. Never assume H2 or other databases accurately emulate Oracle PL/SQL, `NUMBER`, `REF CURSOR`, packages, triggers, or transaction behavior.

### 17.3. Never run destructive tests on production

Tests can `INSERT`/`UPDATE`/`DELETE`, increment sequences, commit, or fire triggers. Run them only against test databases or isolated schemas with cleanup policies. Never treat production as a routine testing ground merely because real data exists there.

### 17.4. Categorizing tests by execution speed

- Fast database unit tests: calculation functions and package APIs with small fixtures.
- Database integration tests: multi-table, constraint, trigger, and package dependencies.
- JDBC contract tests: callable statements, `OUT` parameters, cursors, and exceptions.
- Service integration tests: Spring transactions, repositories, and exception mapping.
- Concurrency tests: multiple sessions and locking behavior.
- Performance tests: data volumes, execution plans, throughput, and latency.

Run fast tests on every pull request; heavier or concurrency suites can run on a schedule or pre-release, while keeping critical paths covered early enough to catch regressions.

## 18. Comparing utPLSQL and JDBC/JUnit

| Criterion | utPLSQL | JDBC/JUnit |
|---|---|---|
| Test language | PL/SQL | Java |
| Execution location | Inside Oracle Database | Application/test JVM connecting to Oracle |
| Testing PL/SQL logic | Very well suited | Possible, but heavier test harness |
| Testing JDBC bind/`OUT` | Does not test Java driver | Well suited |
| `REF CURSOR` mapping | Tests cursor logic inside PL/SQL | Tests how Java reads the cursor |
| Spring transactions | Does not test Spring | Can verify via Spring context |
| Application user privileges | Can run under a test user | Can run directly as the application user |
| Session pool behavior | Limited by runner/session | Can test connection reuse |
| Multi-session concurrency tests | Possible but requires orchestration | Well suited with multiple JDBC connections |
| CI integration | Requires Oracle runner/reporters | Native JUnit/Surefire/Gradle/Maven integration |
| Oracle JDBC driver dependency | No | Yes |
| HTTP API testing | Not its goal | Extensible through service/API tests |

The two approaches are not mutually exclusive. A package rich in database logic should have a utPLSQL suite testing internal rules alongside JDBC contract tests for every routine Java invokes.

## 19. Example end-to-end test strategy for order_api

Suppose package `order_api` exposes:

- `create_order`: creates an order and returns an `OUT` ID.
- `calculate_total`: calculates total amount.
- `approve_order`: transitions status from `NEW` to `APPROVED`.
- `list_orders`: returns `SYS_REFCURSOR`.
- `cancel_order`: rejects if order is already delivered.

Tests can be partitioned as:

### 19.1. utPLSQL

    TEST_ORDER_API
      +-- creates_order_for_active_customer
      +-- rejects_unknown_customer
      +-- rejects_negative_amount
      +-- calculates_total_with_discount
      +-- calculates_zero_total
      +-- approves_new_order
      +-- rejects_approval_for_closed_order
      +-- cancels_eligible_order
      +-- rejects_cancel_for_delivered_order

Tests use dedicated customer/product/order fixtures and roll back transactional changes. Verify both row state and exception codes.

### 19.2. JDBC contract tests

    OrderApiJdbcTest
      +-- binds_create_order_in_parameters
      +-- reads_create_order_out_parameter
      +-- calls_calculate_total_function
      +-- reads_list_orders_ref_cursor
      +-- maps_application_error_to_sql_exception
      +-- rolls_back_when_caller_rolls_back
      +-- executes_as_application_user

These tests validate PL/SQL signatures, JDBC types, driver behavior, and privileges.

### 19.3. Spring service tests

    OrderServiceIntegrationTest
      +-- creates_order_with_transaction
      +-- maps_business_error_to_domain_exception
      +-- returns_expected_order_dto
      +-- does_not_hold_transaction_during_external_call

Service tests verify Spring transaction boundaries, exception translation, and DTO mapping. When services invoke packages through repositories/adapters, run against real Oracle in the integration profile.

## 20. Test design checklist

### Before writing tests

- Identify the public package API and each routine's contract.
- Document `IN`, `OUT`, `IN OUT`, return types, and exception codes.
- Identify dependent tables, sequences, triggers, packages, and required privileges.
- Determine whether routines perform `COMMIT`, autonomous transactions, or external side effects.
- Choose fixtures with isolated keys and never use production data.
- Select test layers: utPLSQL, JDBC/JUnit, or both.
- Record Oracle version, utPLSQL version, JDK, and `ojdbc` version.

### When writing utPLSQL

- Suites use proper annotations.
- Each test targets one primary behavior.
- Fixtures are created per test or explicitly reset.
- Assertions check return values, row state, and exceptions.
- Rollback mode matches transaction behavior.
- Tests do not depend on execution order, exact sequence values, or default NLS.
- Tests never assume DDL, `COMMIT`, or autonomous transactions roll back.

### When writing JDBC/JUnit

- Connect using the real Oracle JDBC driver.
- `CallableStatement` binds matching types and parameter order.
- `OUT` parameters/function returns are registered before `execute`.
- `REF CURSOR`s are read before closing connections.
- `BigDecimal` is used for exact decimals.
- `SQLException`s are verified by error code/contract.
- Transaction cleanup is verified, especially if procedures commit.
- Tests run under the application user or equivalent privileges.
- Connections, statements, and result sets are closed via try-with-resources.

### After test execution

- Inspect all test failures/errors and SQL errors in full.
- Verify no committed test data was left behind.
- Verify sessions/connections were released.
- Re-run suites to confirm repeatability.
- Archive reports and schema/driver/framework versions.
- Never treat owner-schema passes as proof that the application user has proper privileges.

## 21. Common testing pitfalls

### 21.1. Tests pass as owner but fail as application user

Cause: the owner has direct privileges on objects while the application user lacks `EXECUTE` or package dependencies lack grants. Run JDBC tests as the application user and inspect `AUTHID`/privileges.

### 21.2. Tests leave data behind after running

Cause: package `COMMIT`s, autonomous transactions, DDL, or off-database side effects. Inspect transaction contracts and use dedicated test schemas or key-scoped cleanup.

### 21.3. Tests fail when run in parallel

Fixtures using hardcoded IDs or shared mutable data cause unique constraint conflicts and races. Use isolated ID namespaces, independent data, and worker/session isolation.

### 21.4. JDBC reads wrong OUT parameters

Cause: wrong JDBC type registered, wrong parameter index, or reading before `execute`. Inspect package signatures, parameter order, and driver mappings. Use `BigDecimal` for high-precision `NUMBER`.

### 21.5. REF CURSOR closed prematurely

A `ResultSet` returned from a cursor depends on its statement and connection. Map rows into memory before closing resources; never return a `ResultSet` out of a repository after the connection is released.

### 21.6. Assertions relying on unguaranteed SQL ordering

Without `ORDER BY`, the database does not guarantee result order. Add deterministic `ORDER BY` keys or compare as unordered sets rather than positional indices.

### 21.7. Tests depending on current date/time

Using `SYSDATE`/`SYSTIMESTAMP` directly makes tests flaky across time and timezones. Pass reference timestamps into routines, pin session timezones, or construct relative data with clear boundaries.

## 22. Key principles to remember

- utPLSQL tests packages, procedures, and functions inside Oracle; JDBC/JUnit verifies the Java-to-database contract.
- Test public behavior rather than coupling to private implementation details.
- Fixtures must be independent, deterministic, and cleanly torn down.
- Never assume rollback automatically undoes `COMMIT`, autonomous transactions, DDL, sequences, or external side effects.
- `CallableStatement` must bind `IN`/`OUT`/`IN OUT` accurately and register function returns at the right position.
- `REF CURSOR`s must be consumed while the statement and connection remain open.
- Use `BigDecimal` for exact `NUMBER`; test `NULL`, precision, and empty strings per Oracle semantics.
- Test as the application user to catch `EXECUTE`, `AUTHID`, and object privilege errors.
- Connection pool/session state and transaction boundaries must be verified at the integration layer.
- Run tests against compatible Oracle and real drivers; mocked databases cannot prove full Oracle behavior.
- CI requires reliable reporting/exit codes and isolated test environments.
- Never run tests with DML/`COMMIT` on production.

A solid PL/SQL testing strategy pairs utPLSQL to verify database-internal rules with JDBC/JUnit to verify how the application invokes those routines. When contracts, fixtures, transactions, and privileges are under control, bugs surface at the right layer and package changes carry far less risk of breaking consuming Spring Boot applications.
