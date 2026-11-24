# Preparing Schema and Purposeful Test Data

A test that interacts with a database is only reliable when it clearly knows what data structure exists, what data is created for the scenario, and what data must be cleaned up after running. Schema and test data are two distinct parts of the test environment: the schema defines tables, columns, keys, indexes, constraints, and relationships; test data consists of specific records prepared to verify behavior.

In Spring Framework Testing, a database can be prepared using SQL scripts, code in fixtures, or database creation tools for tests. The Spring TestContext Framework provides `@Sql` and `@SqlConfig` to declare script execution aligned with the test lifecycle. These options need to be combined with transactions, context caching, and data isolation strategies so tests can run independently, repeatedly, and in any order.

## Distinguishing schema, reference data, and scenario-specific data

Before writing SQL, categorize what needs to be prepared:

| Component | Content | Example |
|---|---|---|
| Schema | Database structure and constraints | Customer table, primary key, foreign key, unique constraint, index |
| Reference data | Background data shared across multiple scenarios | Countries, currencies, order statuses |
| Scenario-specific data | Records serving only a single behavior under test | Customer C-100, an unpaid order |
| Data generated during test | Records created by the action under test itself | An order saved by a service during the test |

For example, a test verifying a query to find a customer by email needs a customer table with an email column and one specific record. A test verifying a unique constraint needs two writes with the same email to confirm that the database rejects duplicate records. Both scenarios can share the same schema yet require different datasets.

A clear way to organize this is to split it into three layers:

1. **Base schema:** created once per database or test suite.
2. **Reference data:** loaded after the schema if multiple tests share it and do not modify it.
3. **Per-test data:** created before each test method or directly inside the test, then rolled back or cleaned up afterward.

Do not mix scenario-specific data into schema scripts. The schema should describe structure; data fixtures should describe the input conditions of a test.

## Determining the schema a test needs to use

Tests should run against a schema that matches the application. If the application has migration scripts, the reliable approach is to build the test schema using the same migration sequence the application uses, rather than writing a different simplified schema and concluding that the production database works properly.

Flyway or Liquibase can be used in test configuration to apply migrations to the test database. These are migration tools, not core APIs of the Spring TestContext Framework. Spring Test is responsible for initializing the context and connecting tests to the database; the migration tool is responsible for bringing the schema to the required version.

When choosing a schema for tests, keep in mind:

- Tables and columns must reflect the schema version that the code is using.
- Data types need to be compatible with the actual database, especially for decimals, timestamps, JSON, sequences, and generated identities.
- Foreign keys and unique constraints should be preserved if test behavior depends on them.
- Indexes can affect query plans and performance; performance tests should not rely on a stripped-down schema without indexes.
- Triggers, views, stored procedures, and default values need to be created if the application relies on them.
- If using multiple schemas or tenants, the test must clearly specify which schema is being accessed and how data is reset.

An embedded database like H2 is useful for some fast tests, but it does not completely replace the production database engine. SQL dialects, data types, isolation, locking, sequences, constraints, and DDL behavior can differ. When a test needs to prove that a query or migration is compatible with PostgreSQL, MySQL, or a specific engine, use that exact engine in the test environment, typically via Testcontainers or a dedicated test database.

## Preparing schema with SQL scripts

The Spring TestContext Framework can execute SQL scripts using `@Sql`. This approach is useful when a schema or fixture contains many statements, needs to be human-readable, and is shared across multiple tests.

Example of a schema script:

~~~sql
create table customer (
    id bigint primary key,
    email varchar(255) not null unique,
    name varchar(120) not null,
    active boolean not null
);

create table customer_order (
    id bigint primary key,
    customer_id bigint not null,
    status varchar(30) not null,
    total_amount decimal(12, 2) not null,
    constraint fk_order_customer
        foreign key (customer_id) references customer(id)
);
~~~

A test can instruct Spring to run a script before the test methods in the class begin:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Sql(
    scripts = "/sql/customer-schema.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS
)
@Sql(
    scripts = "/sql/customer-drop-schema.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS
)
class CustomerRepositoryIntegrationTest {
    // Tests use the prepared schema.
}
~~~

Class-level phases such as `BEFORE_TEST_CLASS` and `AFTER_TEST_CLASS` are available since Spring Framework 6.1. For earlier versions, an initializer, database configuration, or appropriate lifecycle fixture can be used to prepare the schema before test methods run.

Schema cleanup scripts must follow dependency order. If the order table has a foreign key referencing customer, the child table must be dropped before the parent table:

~~~sql
drop table if exists customer_order;
drop table if exists customer;
~~~

DDL syntax can vary across database engines. If multiple engines need to be supported, use migrations or dialect-specific scripts instead of assuming one SQL statement behaves identically across all databases.

### One-time schema and per-method fixtures

Not every test needs to recreate the schema. The schema is typically stable throughout the lifecycle of an ApplicationContext or test database, whereas scenario-specific data needs to be isolated per test method.

A readable directory structure:

~~~text
src/test/resources/
  sql/
    schema/
      customer-schema.sql
      customer-drop-schema.sql
    reference/
      countries.sql
      currencies.sql
    fixtures/
      customer-active.sql
      customer-inactive.sql
      orders-for-customer.sql
    cleanup/
      customer-fixture-cleanup.sql
~~~

File names should describe the purpose of the data. Avoid a single large file named `test-data.sql` containing hundreds of records where it is unclear which test needs them.

## @Sql: running scripts by test lifecycle

`@Sql` belongs to the `org.springframework.test.context.jdbc` package and lets you declare SQL scripts or statements to execute for a test class or test method.

An example of preparing a fixture for each test method:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    @Sql("/sql/fixtures/customer-active.sql")
    void findsActiveCustomer() {
        var result = repository.findActiveByEmail("lan@example.test");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getName()).isEqualTo("Lan");
    }
}
~~~

By default, `@Sql` scripts execute during the `BEFORE_TEST_METHOD` phase. Therefore, the data in the fixture file is available before the test method runs.

Multiple scripts can be declared:

~~~java
@Test
@Sql(scripts = {
    "/sql/fixtures/customer-active.sql",
    "/sql/fixtures/orders-for-customer.sql"
})
void findsCustomerOrders() {
    // Verify order query.
}
~~~

Script declaration order matters if a later script depends on data created by an earlier script. For example, the customer script must run before the order script if orders reference customers via a foreign key.

`@Sql` also allows declaring SQL statements directly using the `statements` attribute:

~~~java
@Test
@Sql(statements = {
    "insert into customer(id, email, name, active) " +
        "values (9101, 'lan@example.test', 'Lan', true)"
})
void loadsCustomer() {
    // ...
}
~~~

For short fixtures, `statements` is convenient. For lengthy data or data shared by multiple tests, script files are usually easier to read and manage.

## Execution phases of @Sql

`Sql.ExecutionPhase` determines when a script is executed:

| Phase | Timing | Purpose |
|---|---|---|
| `BEFORE_TEST_METHOD` | Before each test method | Prepare data specific to the method |
| `AFTER_TEST_METHOD` | After each test method | Clean up data or perform cleanup |
| `BEFORE_TEST_CLASS` | Before the class's test methods | Prepare schema or base data shared within the class |
| `AFTER_TEST_CLASS` | After the class's test methods | Drop schema or database resources of the class |

The two class-level phases have been supported since Spring Framework 6.1. For method-level phases, both setup and cleanup scripts can be declared:

~~~java
@Test
@Sql(
    scripts = "/sql/fixtures/customer-active.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/cleanup/customer-active-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void readsCustomer() {
    // ...
}
~~~

A cleanup script is not always necessary. If both the fixture and the test's actions run within a test-managed transaction and the transaction is rolled back, the data can be undone automatically. Cleanup scripts are useful when the test commits data, uses an isolated transaction, or manipulates state outside a transaction.

If a cleanup script deletes committed data, it must accurately scope the test's data. Do not use broad delete statements such as `delete from customer` on a shared database.

## @SqlConfig: controlling how SQL scripts execute

`@SqlConfig` lets you configure how Spring reads and executes scripts, such as encoding, separator, comment prefix, datasource, transaction manager, and transaction mode.

It can be configured at the class level to apply to `@Sql` declarations within the class:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@SqlConfig(
    encoding = "UTF-8",
    separator = ";",
    commentPrefix = "--"
)
class CustomerRepositoryTest {
    // ...
}
~~~

Or configured specifically for a single script set:

~~~java
@Test
@Sql(
    scripts = "/sql/fixtures/customer-active.sql",
    config = @SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        commentPrefix = "--"
    )
)
void findsCustomer() {
    // ...
}
~~~

Some notable attributes:

| Attribute | Meaning |
|---|---|
| `dataSource` | Name of the DataSource bean used to execute the script |
| `transactionManager` | Name of the PlatformTransactionManager bean |
| `transactionMode` | How the script participates in or creates a transaction |
| `encoding` | Encoding of the script resource |
| `separator` | Character separating SQL statements |
| `commentPrefix` | Single-line comment prefix |
| `blockCommentStartDelimiter` / `blockCommentEndDelimiter` | Start and end delimiters for multi-line comments |
| `errorMode` | How errors are handled when running scripts |

If the context has multiple datasources or transaction managers, the appropriate bean must be specified. If left to Spring to infer, the bean names and types in the context must be unambiguous enough to select the right database.

### TransactionMode.INFERRED and ISOLATED

`SqlConfig.TransactionMode` has two main options:

- `INFERRED`: Spring attempts to infer how to run the script based on the existing transaction and transaction manager in the context. If the test is running inside a test-managed transaction, the script can participate in that transaction. If there is no current transaction but a suitable transaction manager exists, Spring can create a transaction for executing the script.
- `ISOLATED`: the script runs in an independent transaction, with `REQUIRES_NEW`-style propagation. This transaction is committed independently according to the transaction manager mechanism, and is not rolled back along with the outer test-managed transaction.

Example requiring a fixture to be committed independently:

~~~java
@Test
@Sql(
    scripts = "/sql/fixtures/reference-customer.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
void readsCommittedFixture() {
    // Fixture is created in its own transaction.
}
~~~

Do not choose `ISOLATED` just to avoid understanding transactions. When a fixture needs to disappear after the test, running in a test-managed transaction and rolling back is usually simpler. An isolated transaction can leave data behind after the test finishes, so explicit cleanup is required.

If no suitable transaction manager exists, Spring cannot fulfill the script's transaction requirements as expected. Check the datasource and transaction manager in the context when encountering script initialization or execution errors.

## Combining @Sql with @Transactional

Spring Test supports test-managed transactions when a test class or method is annotated with `@Transactional` and a suitable transaction manager exists. By default, a transaction managed by Spring Test is rolled back when the test finishes.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class CustomerRepositoryTransactionalTest {

    @Autowired
    CustomerRepository repository;

    @Test
    @Sql("/sql/fixtures/customer-active.sql")
    void readsFixtureInsideTestTransaction() {
        var customer = repository.findByEmail("lan@example.test");

        assertThat(customer).isPresent();
    }
}
~~~

With the default inferred transaction mode, the setup script typically participates in the test-managed transaction. The test reads data within the same transaction, and the rollback at the end of the test undoes the data created in that transaction.

Distinguish these cases:

1. **Fixture participates in the test-managed transaction:** the test's rollback can undo the fixture data and the test's changes.
2. **Script uses an ISOLATED transaction:** data may have committed separately and persist after the test rolls back.
3. **Test is annotated with @Commit or @Rollback(false):** changes in the test transaction may be committed, so cleanup is required.
4. **Side effects outside the database transaction:** writing files, sending HTTP requests, messaging, or work running on another thread are not automatically rolled back.
5. **Database engine has specific DDL behavior:** some DDL commands may implicitly commit or not roll back like standard DML operations.

If a test needs to verify an actual commit, design separate data and explicit cleanup. Do not rely on the default rollback when the actual code opens a new transaction or commits independently.

## Combining class-level and method-level scripts

Base data can be declared at the class level and specific fixtures at the method level. By default, when both class-level and method-level `@Sql` are present, the method-level declaration can replace the class-level declaration. `@SqlMergeMode` lets you choose the merge behavior.

Example keeping the class-level base script and adding a method-level script:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Sql("/sql/reference/currencies.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class PaymentRepositoryTest {

    @Test
    @Sql("/sql/fixtures/payment-pending.sql")
    void findsPendingPayment() {
        // Both currencies and payment-pending scripts are applied.
    }
}
~~~

Without `@SqlMergeMode(MERGE)`, method-level `@Sql` by default can override class-level declarations. `@SqlMergeMode` can be placed on the class to apply globally or on a method to change behavior for a specific scenario.

Merging is useful when every test needs reference data while each method only adds its own fixture. However, if the base script creates mutable data or data modified by tests, merging can cause state leakage. Base data should be immutable across tests or restored via transactions/cleanup.

## Preparing data with code and fixture builders

Not every test needs SQL scripts. If the data is simple and the behavior under test directly involves a repository or service, creating data through the application's API can help the test express its intent more clearly.

~~~java
@Test
@Transactional
void createsCustomerAndFindsIt() {
    Customer customer = new Customer(
        "C-9101",
        "lan@example.test",
        "Lan",
        true
    );

    repository.save(customer);

    var result = repository.findByEmail("lan@example.test");

    assertThat(result).isPresent();
}
~~~

This approach fits when the test wants to verify the save operation of the repository or service itself. If the goal is purely to prepare database state for a query, an SQL script can be more direct and concise.

A fixture builder helps create structured data without repeating long constructors:

~~~java
class CustomerFixture {

    static Customer activeCustomer(String id, String email) {
        return new Customer(id, email, "Lan", true);
    }

    static Customer inactiveCustomer(String id, String email) {
        return new Customer(id, email, "Lan", false);
    }
}
~~~

Tests call the builder to create a new object for each scenario. Avoid using a mutable static object and modifying its fields across multiple tests, as tests can accidentally share the same reference.

Choose the data creation approach based on your goal:

| Goal | Suitable approach |
|---|---|
| Create database structure and constraints | Migration or schema SQL script |
| Prepare multiple records with complex relationships | SQL fixture or builder with clear relationships |
| Verify the write operation itself through a repository | Create objects and call the repository inside the test |
| Verify a query against existing data | SQL fixture or data builder before the query action |
| Verify migrations | Run migrations on a clean test database |
| Verify constraints enforced by the database | Write real data to the test database and assert the error |

## Designing stable and repeatable test data

Test data should be chosen purposefully. A good fixture lets readers immediately understand the test conditions and does not depend on leftover data from previous runs.

### Use minimal yet meaningful data

Create only the records necessary for the behavior under test. If a test finds a customer by email, there is no need to create dozens of orders, payments, and shipments if they are not involved in the query.

Excessive data slows tests down and makes it hard to tell which record determines the outcome. Overly simplistic data can miss relationships, constraints, or edge cases. Keep the exact attributes required for the test condition.

### Choose non-colliding keys and identifiers

If multiple tests run against the same database, use IDs or keys scoped individually to each test. Fixed identifiers can be used within a test-specific database/schema, or UUIDs can be generated when collisions across runs must be avoided.

~~~java
String email = "customer-" + UUID.randomUUID() + "@example.test";
~~~

Unique data reduces collisions, but it does not replace cleanup. If tests commit data, those records remain and can bloat the database.

### Declare related data in valid order

If the order table has a foreign key to customer, customer must be created before order. During cleanup, delete order before customer unless the database has a cascade mechanism intentionally used.

Do not disable constraints just to make fixture scripts easier to run. Tests must reflect the conditions that the application actually has to obey.

### Avoid relying on auto-increment order

Do not assume the first record always has ID 1 or that sequences always reset after each test. Many databases do not guarantee that sequences/identities revert to their previous values when a transaction rolls back. If a test needs a specific record, query by a business key or use purposefully assigned IDs.

### Use explicit time values

Do not use the current system time as a fixture if the test needs to check payment due dates, creation dates, or expiration times. Write explicit timestamps and clear timezones so results remain consistent between developer machines and CI.

### Do not use real personal data

Fixtures should use synthetic, meaningful data and must not contain real customer information. Emails should use test domains, and names and identification numbers should be fabricated for illustration purposes.

## Cleaning up data safely

There are three common strategies:

1. **Transaction rollback:** suitable when all write operations participate in a transaction managed by Spring Test.
2. **Cleanup script:** suitable when the test commits or the fixture is created outside the test's transaction.
3. **Dedicated database/schema:** suitable when tests need strong isolation, parallel execution, or migration/DDL verification.

Example cleanup by business key:

~~~sql
delete from customer_order
where customer_id = 9101;

delete from customer
where id = 9101;
~~~

Cleanup has a clear scope and respects foreign keys. If dynamic IDs are used, values can be passed via a test-generated fixture script or a shared namespace for the test run.

Avoid the following operations on a shared database:

- Unconditional `delete from customer`.
- `truncate table` when other tests might be using the table.
- Dropping a shared schema while other tests are running.
- Resetting global sequences in a way that alters assumptions of other tests.
- Sharing fixed keys across tests running in parallel.

If the entire database needs to be reset, perform it on a database or schema belonging solely to that test run.

## @SqlConfig and multi-statement scripts

An SQL script may contain comments, multi-line statements, or procedures with special delimiters. `@SqlConfig` lets you adjust the separator and delimiters so Spring parses the script correctly.

Example:

~~~java
@Sql(
    scripts = "/sql/fixtures/customer-procedure.sql",
    config = @SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        commentPrefix = "--",
        blockCommentStartDelimiter = "/*",
        blockCommentEndDelimiter = "*/"
    )
)
~~~

If a script contains a stored procedure or block with semicolons inside, the default separator may not be suitable. Configure the delimiter according to the database syntax and how the script is written. Do not change the separator globally if only one script has special requirements; place the config locally on that script.

The `errorMode` attribute determines how errors are handled when executing scripts. By default, SQL errors fail the test, which is usually the desired behavior because the schema or fixture was not prepared properly. Only ignore errors intentionally when a script is designed for multiple database states and there is already a way to verify the result.

## Supporting tools: ResourceDatabasePopulator and JdbcTestUtils

Beyond `@Sql`, Spring JDBC provides tools to execute scripts programmatically.

`ResourceDatabasePopulator` accepts one or more SQL resources, configures encoding/separator, and executes them against a database. It is useful when initializing a database from Java configuration or when fixtures need to be controlled via code.

~~~java
ResourceDatabasePopulator populator =
    new ResourceDatabasePopulator(
        new ClassPathResource("sql/customer-schema.sql"),
        new ClassPathResource("sql/reference-data.sql")
    );

DatabasePopulatorUtils.execute(populator, dataSource);
~~~

This approach suits initializers or test infrastructure that need to initialize the schema before the context is used. For scenarios tied directly to the test method lifecycle, `@Sql` usually expresses intent more clearly.

`JdbcTestUtils` provides useful helpers when interacting with a database in tests, such as counting rows or deleting data from tables:

~~~java
int count = JdbcTestUtils.countRowsInTable(jdbcTemplate, "customer");
int deleted = JdbcTestUtils.deleteFromTables(
    jdbcTemplate,
    "customer_order",
    "customer"
);
~~~

Helpers do not replace designing safe cleanup. When using `deleteFromTables`, you need to know which data belongs to the test and whether the table order respects foreign keys. Do not call full-table deletion helpers on a database shared with other tests.

## Running tests in parallel and sharing databases

If tests run in parallel against the same database, fixture data needs to be isolated per test method or worker. Two tests using the same email, same ID, and same table can hit unique constraints, delete each other's data, or read unstable results.

Some isolation approaches:

- A dedicated database per test suite or worker.
- A dedicated schema per test class or test run.
- A dedicated namespace/tenant for data.
- Unique UUIDs or business keys for fixtures.
- Separate transactions when operations actually participate in transactions.
- Synchronization locks when a resource cannot be safely shared.

Transaction rollback does not solve every conflict. Two concurrent transactions can still contend on unique keys or locks. A cleanup script can also delete another test's data if the delete condition is too broad.

If a test needs to verify isolation, locking, or concurrent updates, design explicit multi-transaction scenarios and use a real database engine. A simple test can run sequentially; a concurrency test needs intentional management of threads, transactions, and wait times.

## Verifying migrations and schema compatibility

If the production schema is managed by migrations, migration tests should start from a clean database and run the entire migration chain in the exact order. Then, verify the schema and required behavior.

Examples of things to verify:

- Migrations create all tables and columns used by repositories.
- Constraints and indexes are created properly.
- Reference data is inserted or transformed properly.
- Subsequent migrations can run on top of the state created by previous migrations.
- Upgrading from an older schema version does not lose data that must be retained.
- The application can read/write on the post-migration schema.

Do not simply run a simplified schema file in tests and treat it as proof that production migrations are correct. A simplified schema is still useful for fast unit/integration tests, but migration tests must run real migrations.

## Complete example with @Sql and transaction rollback

The following example illustrates a repository test using a Spring context, per-method SQL fixtures, and a test-managed transaction:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    @Sql(
        scripts = "/sql/fixtures/customer-active.sql",
        config = @SqlConfig(
            encoding = "UTF-8",
            transactionMode = SqlConfig.TransactionMode.INFERRED
        )
    )
    void findsActiveCustomerByEmail() {
        var customer = repository.findByEmail("lan@example.test");

        assertThat(customer).isPresent();
        assertThat(customer.orElseThrow().isActive()).isTrue();
    }

    @Test
    @Sql("/sql/fixtures/customer-inactive.sql")
    void excludesInactiveCustomerFromActiveSearch() {
        var result = repository.findActiveByEmail("mai@example.test");

        assertThat(result).isEmpty();
    }
}
~~~

The first fixture script might contain:

~~~sql
insert into customer(id, email, name, active)
values (9101, 'lan@example.test', 'Lan', true);
~~~

The second script might contain:

~~~sql
insert into customer(id, email, name, active)
values (9102, 'mai@example.test', 'Mai', false);
~~~

Because the test class uses `@Transactional` and the script uses the inferred transaction mode, the fixture data typically participates in the test-managed transaction. When each test finishes and the transaction rolls back, the records created for that test are undone. The two methods do not rely on data created by each other.

The example assumes the repository and schema are preconfigured in `PersistenceTestConfig`. In a real project, you need to choose IDs, unique keys, and a transaction manager suited to the test database in use.

## Common misconceptions

**Putting business data into schema scripts.** Schemas and fixtures have different lifecycles. Keep structure in schemas/migrations and scenario data in separate fixtures.

**Assuming @Sql always runs inside the test's transaction.** That depends on the transaction manager, existing transaction, and `transactionMode`. Check whether it is `INFERRED` or `ISOLATED` before relying on rollback.

**Using ISOLATED and expecting the test rollback to delete the fixture.** An isolated transaction can commit separately. Cleanup or a dedicated database/schema is required.

**Using cleanup that deletes the entire table.** On a shared database, that operation can delete other tests' data. Use business keys or a separate namespace.

**Assuming H2 is equivalent to the production database.** SQL dialects, DDL, locking, types, and constraints can differ. Test engine-dependent behavior on the actual engine.

**Relying on auto-increment IDs starting from a fixed value.** Sequences may not roll back/reset as expected. Query by business key or assign IDs purposefully.

**Assuming method-level @Sql always adds to class-level @Sql.** By default, method-level scripts can override class-level scripts. Use `@SqlMergeMode(MERGE)` when merging is needed.

**Putting overly large scripts for every test.** Base scripts should hold genuinely shared reference data; each method should only load the fixture needed for its scenario.

**Using production migrations as a tiny fixture for every test.** Migrations should test the schema; test fixtures should focus on data. Both can be used, but responsibilities should be clearly separated.

## Workflow for preparing schema and data for a test

When writing a test that needs a database, determine step by step:

1. Does the test need to verify the schema, queries, constraints, or business logic using data?
2. How closely must the schema match the production database? Does it need to run real migrations or use the exact database engine?
3. Which data is shared reference data, and which data belongs only to the test method?
4. Should the schema be prepared at the database/suite/class or method level?
5. Should `@Sql`, a builder, a repository, or `ResourceDatabasePopulator` be used to create the fixture?
6. At which phase does the script run, and which transaction mode does it use?
7. Will the data be rolled back? If committed, what exact scope does the cleanup delete?
8. Can the test run independently and in parallel without key or resource collisions?

A stable schema provides the foundation for tests. Minimal fixtures with clear identifiers enable each test to verify one specific behavior. When choosing the right phase, transaction mode, and cleanup scope, Spring Test makes database preparation repeatable, readable, and less dependent on leftover state from previous runs.
