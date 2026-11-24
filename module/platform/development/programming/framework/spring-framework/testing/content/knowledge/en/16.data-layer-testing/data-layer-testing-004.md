# SQL Dialect Differences, Data Types, and Transaction Isolation

Data-layer testing must verify that the application stores, queries, and updates data properly on the database management system the system actually uses. A repository test may pass on an embedded database yet fail when deployed to PostgreSQL, MySQL, SQL Server, or Oracle because each DBMS has its own SQL dialect, data types, conversion rules, and transaction behavior.

Differences are not limited to statement syntax. Databases can handle `BOOLEAN`, `UUID`, JSON, time-zoned timestamps, decimals, identity/sequences, collations, `NULL` values, unique constraints, and transaction isolation levels differently. A test running on a substitute database may miss bugs that only surface in production. Therefore, choose the test environment based on what needs to be proven, and design tests to distinguish mapping bugs, SQL dialect bugs, and transaction isolation bugs.

## 1. What Is a SQL Dialect?

SQL is a query language with shared standards, yet each DBMS implements and extends the standard in its own way. A **SQL dialect** is the specific set of syntax, functions, data types, and SQL rules supported by a given database.

Some common differences:

| Topic | Example Differences |
|---|---|
| Row limits | PostgreSQL/MySQL support `LIMIT`; SQL Server typically uses `TOP` or `OFFSET ... FETCH` |
| Key generation | PostgreSQL supports sequences; MySQL typically uses `AUTO_INCREMENT`; SQL Server has `IDENTITY` and `SEQUENCE` |
| String concatenation | `||`, `CONCAT(...)`, or `+` operator depending on database and data type |
| Boolean type | Some databases have a `BOOLEAN` type; others store `BIT` or numeric representations |
| JSON | JSON types and query operators differ, e.g., `jsonb` in PostgreSQL vs. JSON type in MySQL |
| Date and time | `TIMESTAMP`, `DATETIME`, and `TIMESTAMP WITH TIME ZONE` have different semantics |
| Upsert | `ON CONFLICT`, `ON DUPLICATE KEY UPDATE`, `MERGE`, or custom syntax |
| String/date functions | Function names, parameters, and return types can differ |
| Identifiers | Case sensitivity rules, quoting, and reserved keywords differ |

A repository using JPQL or the Criteria API generally reduces reliance on database-specific syntax because Hibernate translates expressions into SQL matching the dialect. However, native SQL, custom functions, migration scripts, and certain data-type mappings still depend on a specific DBMS.

## 2. Distinguishing Repository Logic Tests from Real Dialect Tests

Not every test needs to run on the production database. Define what needs to be proven:

- Whether the repository implements search, filter, pagination, and sorting rules properly.
- Whether entity mappings are compatible with the real database's data types and constraints.
- Whether native queries have valid syntax and return the expected types on the target dialect.
- Whether migrations produce the right schema on the deployed database version.
- Whether transaction isolation prevents anomalies unacceptable to business rules.

A test using an embedded database may suit verifying simple mappings or dialect-independent repository logic. When tests involve native SQL, JSON operators, sequences, collations, locking, or isolation, run them on the same DBMS and a version compatible with production.

| Testing Goal | Suitable Environment |
|---|---|
| Service unit test, not testing SQL | Mock/fake repository |
| Simple repository queries, low dialect dependency | Embedded database may suffice for fast feedback |
| Native SQL or database-specific functions | Same database engine as production |
| Specialized data types, sequences, JSON, collations | Real database via Testcontainers or equivalent environment |
| Production migrations and schema | Run migrations on the exact engine/version |
| Transaction isolation and concurrency | Database supporting the deployed isolation/locking |

An embedded database is not a perfect simulator of a production database. For example, H2 may accept some compatibility syntax yet still differ from PostgreSQL or MySQL in data types, functions, constraints, and transactions. Passing on H2 only proves behavior on H2.

## 3. Portable SQL vs. Dialect-Dependent SQL

When writing repositories, you can choose JPQL, Criteria API, Spring Data derived queries, or native SQL. Each choice carries a different degree of database dependency.

### 3.1. Derived Queries and JPQL

Spring Data JPA can generate queries from method names:

```java
interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByStatusAndCreatedAtAfter(
            CustomerStatus status,
            Instant createdAt);
}
```

JPQL queries entities and Java attributes rather than tables/columns directly:

```java
@Query("""
       select o
       from Order o
       where o.customerId = :customerId
         and o.status = :status
       order by o.createdAt desc
       """)
List<Order> findRecentOrders(
        @Param("customerId") String customerId,
        @Param("status") OrderStatus status);
```

Hibernate translates JPQL to SQL based on dialect and mappings. This typically makes queries less dependent on database syntax. Still, behavior can be affected by collation, data types, null semantics, timestamp precision, generated SQL, and provider feature support.

### 3.2. Native Queries

Native queries allow writing SQL directly:

```java
@Query(value = """
        select *
        from customer
        where status = :status
        order by created_at desc
        limit :pageSize
        """, nativeQuery = true)
List<Customer> findLatestCustomers(
        @Param("status") String status,
        @Param("pageSize") int pageSize);
```

`LIMIT` is not portable across all databases. If production uses SQL Server, that query may fail to run. When using native queries, test against the exact target dialect and avoid relying on an embedded database to confirm syntactic correctness.

If multiple dialects must be supported, you can:

- Use JPQL/Criteria API if expressions meet requirements.
- Use Spring Data's pagination API instead of hand-writing `LIMIT`.
- Split repository implementations per database when syntax differs significantly.
- Use appropriate Hibernate functions or abstractions, while still testing generated SQL on each supported dialect.

Do not sacrifice query clarity solely to avoid all dialect differences. If a system intentionally relies on a specific database, writing SQL that leverages its features is reasonable; what matters is testing on the right engine and version.

## 4. Hibernate Dialect Configuration and Database Metadata

Hibernate needs to know the database to generate compatible SQL. In many modern setups, Hibernate detects the dialect from the database's JDBC metadata. Spring Boot usually configures the datasource and lets Hibernate determine the appropriate dialect.

In most cases, there is no need to hardcode `hibernate.dialect` if metadata suffices for detection. Hardcoding an outdated or incompatible dialect can cause Hibernate to generate SQL unsuitable for the running database/version.

When explicit configuration is needed, use the dialect matching the Hibernate version and database in use. Dialect class names can change across major Hibernate versions; do not copy configuration from an older version without checking current version documentation.

### 4.1. Testing on a Real Database with Testcontainers

Testcontainers helps run a real database engine in a container dedicated to tests. PostgreSQL example:

```java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class CustomerRepositoryPostgresTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private CustomerRepository customers;

    @Test
    void persistsCustomerUsingPostgres() {
        Customer saved = customers.save(new Customer("Lan"));
        customers.flush();

        assertThat(customers.findById(saved.getId())).isPresent();
    }
}
```

`@AutoConfigureTestDatabase(replace = Replace.NONE)` instructs Spring Boot to keep the configured datasource instead of replacing it with an embedded database. `@DynamicPropertySource` passes the JDBC URL and credentials allocated by the container at runtime. A static container is typically shared across the test class.

The example requires appropriate Testcontainers dependencies, including the PostgreSQL module and JUnit Jupiter integration. The image tag should be pinned to a version compatible with production; avoid using the `latest` tag because the database could change behavior across runs.

### 4.2. Testing Multiple Database Engines

If the application supports multiple engines, run dedicated tests on each engine the product commits to supporting. You can organize test suites via profiles or build tasks to select the corresponding database container.

Do not use a single embedded database and infer that every dialect works. A query may be valid on PostgreSQL yet fail on MySQL, or vice versa. Testing against an engine/version matrix catches discrepancies before deployment.

## 5. Data Type and Mapping Differences

Java data types and SQL data types do not always correspond one-to-one. Hibernate performs conversions based on mappings, JDBC drivers, and database dialects. Differences in precision, time zones, binary representation, or semantics can alter data during writes and reads.

### 5.1. `BOOLEAN` and Logical Values

Java has `boolean`/`Boolean`, while databases may represent logical values with `BOOLEAN`, `BIT`, or numeric types. Some databases lack a standalone boolean type and use another type to store true/false.

```java
@Entity
class FeatureFlag {
    @Id
    private Long id;

    @Column(nullable = false)
    private boolean enabled;
}
```

Tests should write and read back both values while verifying nullability as required. With nullable `Boolean`, distinguish `false` from `null`; with primitive `boolean`, Java cannot represent null.

Do not assume every database accepts `TRUE`/`FALSE` literals in native SQL. If a query uses dialect-specific literals, test it on the target engine.

### 5.2. `DECIMAL`/`NUMERIC` and `BigDecimal`

Monetary amounts or values needing decimal precision should generally use `BigDecimal` in Java and `DECIMAL`/`NUMERIC` in the database:

```java
@Column(precision = 19, scale = 4, nullable = false)
private BigDecimal amount;
```

`precision` is total digits and `scale` is digits after the decimal point. If data exceeds limits, the database may reject, round, or convert depending on engine and settings.

Tests should check:

- Values at precision/scale boundaries.
- Values with more decimal digits than scale.
- Negative or zero values if business rules allow them.
- Behavior when precision is exceeded.
- Values read back after flushing and clearing the persistence context.

In Java assertions, `BigDecimal.equals()` considers scale, so `10.0` and `10.00` are not equal under `equals`. If business logic only cares about numeric value, use `compareTo` or AssertJ's `isEqualByComparingTo`. If scale is part of the storage contract, check scale explicitly.

### 5.3. `UUID`

UUIDs may be stored as native UUID types, binary, or character strings depending on the database and mapping. PostgreSQL has a `uuid` type; other databases may use `BINARY(16)`, `CHAR(36)`, or equivalents.

```java
@Entity
class ApiClient {
    @Id
    private UUID id;
}
```

Do not assume native SQL can compare UUIDs using the same literal across every engine. Tests must verify round-trip behavior: save a known UUID, flush/clear, read back, and assert the exact value. If the application uses native queries with UUIDs, run tests on a real database to verify JDBC binding.

### 5.4. Timestamps, Time Zones, and Precision

Java has several temporal types with distinct semantics:

| Java | Meaning |
|---|---|
| `Instant` | An absolute point on the UTC timeline |
| `OffsetDateTime` | Date and time with a UTC offset |
| `ZonedDateTime` | Date and time attached to a `ZoneId` and time zone rules |
| `LocalDateTime` | Local date and time without zone/offset |
| `LocalDate` | Calendar date without time of day |
| `LocalTime` | Time of day without date or time zone |

Databases can store `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, `DATETIME`, or proprietary types. Type names do not guarantee identical semantics across engines. Some databases normalize to UTC; some store local fields; some do not preserve time zone identifiers, keeping only instants or offsets in their own way.

Tests should:

- Pick a fixed instant rather than calling `now()` directly.
- Set JVM and database time zones explicitly when testing zone conversions.
- Write/read back via JDBC/JPA to verify round-trip behavior.
- Check precision because databases may store to seconds, milliseconds, or microseconds depending on type and engine.
- Check timestamps near day boundaries and daylight saving time if business rules use DST-observing zones.

Example using `Clock.fixed`:

```java
@Test
void persistsInstantAtExpectedPrecision() {
    Instant expected = Instant.parse("2026-11-12T08:30:00.123456Z");
    EventRecord record = repository.save(new EventRecord(expected));
    repository.flush();
    entityManager.clear();

    Instant actual = repository.findById(record.getId()).orElseThrow()
            .getOccurredAt();

    assertThat(actual).isEqualTo(expected);
}
```

Strict equality assertions hold only if the column type and driver preserve the corresponding precision. If the database intentionally rounds or truncates precision, define the normalization rule and compare at supported precision. Do not add arbitrary tolerances just to make a test pass.

### 5.5. JSON and Semi-Structured Data Types

PostgreSQL has `json`/`jsonb`; MySQL has a JSON type; other DBMSs store JSON in text or use extensions. Indexing, comparison, path querying, and JSON normalization capabilities can differ.

If an entity stores JSON via a converter or Hibernate type, tests must verify both serialization and deserialization. If a repository uses dialect-specific operators like `->>` or JSON functions, it must be tested on the corresponding engine.

Tests should distinguish:

- Whether valid JSON serializes and reads back with the right structure.
- How a missing field differs from a field with value `null`.
- Whether numbers inside JSON undergo precision conversion.
- Whether key ordering is part of the contract or merely a serialization detail.
- Whether native JSON path queries return the expected types and results.

Do not compare raw JSON strings if key ordering or whitespace is not part of the contract. You can parse into a JSON tree and compare structures. However, if a database query relies on `jsonb`, test that query on real PostgreSQL.

### 5.6. Binary, BLOB, and CLOB

Java `byte[]`, `Blob`, `Clob`, or streams can map to `BLOB`, `BYTEA`, `VARBINARY`, `TEXT`, or equivalents. Size limits, streaming behavior, and row limits may vary.

Tests should check small payloads, empty payloads, large payloads near application limits, and exact byte round-trips. If using streams, ensure streams are closed and tests do not hold onto resources after context shutdown.

## 6. Identity, Sequences, and Generated Keys

Databases have multiple ways to generate keys:

- Identity/auto-increment columns.
- Dedicated sequences.
- Application-generated UUIDs.
- Triggers or default expressions.

Hibernate may choose different ID generation strategies depending on dialect. For instance, a database with sequences may use a sequence generator; another uses identity. These differences affect insert SQL timing, batching, and generated key retrieval.

Persistence tests should check the ID after saving and flushing:

```java
@Test
void assignsDatabaseGeneratedId() {
    Customer customer = new Customer("Lan");

    Customer saved = repository.save(customer);
    repository.flush();

    assertThat(saved.getId()).isNotNull();
    assertThat(repository.findById(saved.getId())).isPresent();
}
```

If an entity uses a named sequence or native sequence query, tests must run on a database with matching sequence semantics. If the database generates the ID, do not hardcode specific ID values unless the fixture actively controls the sequence.

### 6.1. Generated Values and Flush Timing

`save()` does not always mean SQL has been sent immediately. JPA can defer writes until flush or commit. When a test needs to verify constraints, generated keys, or SQL errors, call `flush()` to force the persistence context to synchronize with the database.

To verify data is read back from the database, call `clear()` on the persistence context after `flush()` and then re-query. If you only read the same managed entity, the test may receive the in-memory object and miss mapping or storage errors.

## 7. Identifiers, Collations, and String Comparison Rules

Databases can differ in string comparison, case handling, Vietnamese diacritics, accents, and whitespace. Collation affects `ORDER BY`, `LIKE`, unique constraints, and equality.

For example, `Lan` and `lan` may be treated as equal under a case-insensitive collation yet distinct under a case-sensitive collation. Strings with and without accents may also compare differently depending on collation.

Repository tests involving search or unique constraints should use a database with production-like collation. Do not assume `findByNameIgnoreCase` results or unique indexes behave identically across every engine.

Table/column names also differ due to identifier quoting and reserved keywords. A valid name on one database may be a reserved keyword on another. Use clear names, avoid keywords, and test migrations on the target engine.

## 8. Null Semantics and Constraints

SQL uses three-valued logic: `TRUE`, `FALSE`, and `UNKNOWN` due to `NULL`. The expression `column = NULL` is not equivalent to `column IS NULL`; normal comparisons against null evaluate to unknown.

JPQL/Criteria API can help produce proper predicates, but native queries must still adhere to SQL null semantics. Tests should cover:

- Non-null column values and `NULL` values.
- `IS NULL` and `IS NOT NULL`.
- Unique constraints when one or multiple null values exist.
- Foreign keys and `ON DELETE` behavior.
- Check constraints and default values.

How databases handle unique constraints with multiple nulls can vary. Some engines allow multiple nulls in a unique index; some configurations or index types behave differently. If business logic relies on this rule, test on the exact target database.

## 9. Migrations and Schemas Must Match the Test Database

Repository tests are only meaningful when the test schema reflects the schema the application uses. If tests auto-generate schemas with Hibernate `ddl-auto=create-drop` while production uses Flyway or Liquibase, tests can miss migration errors.

For migration tests, run the application's actual migrations on a same-engine test database:

```java
@SpringBootTest
@Testcontainers
class DatabaseMigrationIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void startsApplicationAgainstMigratedSchema() {
        // Context starts successfully after migrations are applied.
    }
}
```

Spring Boot can run Flyway/Liquibase automatically on context startup when dependencies and settings match. Tests should confirm migrations apply in the right order and the resulting schema supports repositories.

### 9.1. Avoiding Letting Hibernate Mask Migration Errors

If production relies on migrations yet tests let Hibernate create the entire schema, tests may pass even if migrations are missing columns, indexes, or constraints. For tests verifying migrations, let the migration tool create the schema and use Hibernate validate if aligned with application config.

Do not simultaneously enable multiple mechanisms managing the same schema unintentionally. For instance, Flyway creating the schema while Hibernate runs `create` again can cause tests to stop validating real migrations.

## 10. What Is Transaction Isolation?

Transaction isolation defines the degree to which one transaction sees changes from other transactions and how the database handles concurrent reads/writes. The goal is controlling anomalies that can arise when multiple transactions operate on data simultaneously.

Commonly referenced phenomena:

- **Dirty read:** a transaction reads uncommitted data from another transaction.
- **Non-repeatable read:** the same row is read twice within one transaction, but its value changes because another transaction committed an update.
- **Phantom read:** the same predicate query executes twice, but the matching row set changes because another transaction inserted/deleted rows and committed.
- **Lost update:** two transactions both update based on a stale value, causing one update to overwrite the other.
- **Write skew:** transactions read the same data set and update disjoint rows; each transaction individually preserves invariants, yet combined they violate a global invariant.

The chosen isolation level determines which anomalies the database must prevent. However, isolation level names do not guarantee identical behavior across all engines; databases may use MVCC, locking, or other mechanisms to achieve corresponding semantics.

## 11. Standard Isolation Levels

JDBC and Spring define standard isolation levels:

| Level | Dirty Read | Non-Repeatable Read | Phantom Read |
|---|---|---|---|
| `READ_UNCOMMITTED` | Possible | Possible | Possible |
| `READ_COMMITTED` | No | Possible | Possible |
| `REPEATABLE_READ` | No | No under standard model | Possible under standard model |
| `SERIALIZABLE` | No | No | No under standard model |

This classification follows traditional SQL/JDBC semantics. Specific databases may provide stronger guarantees than requested or implement levels differently using MVCC/locking. For example, PostgreSQL implements `READ UNCOMMITTED` as `READ COMMITTED`; PostgreSQL `REPEATABLE READ` provides snapshot isolation semantics and prevents more anomalies than the minimal SQL model, yet serialization anomalies/write skew can still occur. SQL Server has its own locking and row-versioning options; MySQL/InnoDB uses MVCC and locking based on isolation level.

### 11.1. `READ_UNCOMMITTED`

Under the standard model, this level permits a transaction to read uncommitted changes from another transaction. This creates the risk of dirty reads: transaction A reads a value that transaction B subsequently rolls back.

Example:

```text
T1: UPDATE account SET balance = 0 WHERE id = 1;  (not yet committed)
T2: SELECT balance FROM account WHERE id = 1;    (may read 0)
T1: ROLLBACK;
```

T2 read a value that was never committed. Many production databases disallow dirty reads even if a client requests `READ_UNCOMMITTED`; verify engine behavior rather than inferring solely from annotations.

### 11.2. `READ_COMMITTED`

A transaction reads only committed data. However, the same query or row can return different values across two reads if another transaction commits changes in between.

This level is commonly the default in many databases. It fits many applications, but does not by itself prevent lost updates or invariants requiring a stable snapshot across reads.

### 11.3. `REPEATABLE_READ`

This level aims to ensure data already read does not change across reads within the transaction under standard semantics. How a database achieves this may rely on locks or snapshots. Phantom rows remain allowed in the standard model, though some engines prevent many phantoms via next-key locks or stronger snapshot semantics.

Do not assume `REPEATABLE_READ` always prevents all concurrent updates or write skew. Verify against the specific engine and application invariants.

### 11.4. `SERIALIZABLE`

`SERIALIZABLE` requires outcomes equivalent to some serial execution order of transactions. The database may lock, detect conflicts, or abort a transaction with a serialization failure to preserve consistency.

Applications must be prepared to handle rejected transactions or retry on conflicts. Tests should verify both business outcomes and how services handle serialization errors if the database can return them.

## 12. Configuring Isolation with Spring `@Transactional`

Spring allows specifying isolation levels on `@Transactional`:

```java
@Transactional(isolation = Isolation.REPEATABLE_READ)
public AccountSnapshot readStableBalance(Long accountId) {
    // Queries in this transaction use the specified isolation
    // if a new transaction is started by the transaction manager.
}
```

Values in `org.springframework.transaction.annotation.Isolation` correspond to JDBC isolation levels:

- `DEFAULT`: uses the transaction manager/database default.
- `READ_UNCOMMITTED`.
- `READ_COMMITTED`.
- `REPEATABLE_READ`.
- `SERIALIZABLE`.

### 12.1. Isolation Only Applies When a New Transaction Is Created

An easy detail to miss: if a method joins an existing transaction with `REQUIRED` propagation, the isolation declared on the inner method does not change the active transaction's isolation. The transaction already began with its original manager and isolation.

For example, a test method opens a `READ_COMMITTED` transaction and then calls a service annotated with `@Transactional(isolation = SERIALIZABLE)` and default `REQUIRED` propagation. The service normally joins the existing transaction; it cannot upgrade that transaction's isolation mid-flight.

If a new transaction with dedicated isolation is required, use `REQUIRES_NEW` propagation or create a transaction explicitly via `TransactionTemplate`. Understand the commit/rollback impact of the new transaction because it can persist independently of the outer test transaction.

### 12.2. Checking Incompatible Isolation

`AbstractPlatformTransactionManager` has a `validateExistingTransaction` property. When enabled, the manager can reject joining an existing transaction if its isolation or read-only attribute is incompatible with the new transaction's requirements. This helps catch cases where a service requests higher isolation yet silently joins a lower-isolation transaction.

Do not assume isolation settings on annotations always take effect when an outer transaction exists. Tests must establish the right transaction boundaries and confirm the manager/database enforces the expected level.

## 13. Transaction Isolation in Test-Managed Transactions

The Spring TestContext Framework can open a transaction for a test method when the class or method is annotated with `@Transactional`:

```java
@SpringBootTest
@Transactional(isolation = Isolation.READ_COMMITTED)
class AccountRepositoryIsolationTest {
    @Autowired
    private AccountRepository accounts;

    @Test
    void readsCommittedAccountState() {
        // Test runs inside a transaction managed by Spring Test.
    }
}
```

The selected transaction manager starts the test transaction with the requested isolation if supported by the manager and database. Test transactions roll back by default after the method.

When multiple transaction managers exist, specify the manager in the test's `@Transactional`. The isolation level is requested for the transaction opened by that manager; it does not automatically configure other managers.

### 13.1. `@Commit`, `@Rollback`, and Isolation

`@Commit` and `@Rollback` control the final outcome of a test-managed transaction, not its isolation level:

```java
@Test
@Transactional(isolation = Isolation.SERIALIZABLE)
@Rollback
void rollsBackSerializableTestTransaction() {
    // Transaction runs at SERIALIZABLE and rolls back after the test.
}
```

If post-commit state must be inspected, use `@Commit` or `TestTransaction.flagForCommit()` and end the transaction. Committed data must be cleaned up so it does not affect other tests.

### 13.2. Flush and Clear Do Not Start a New Transaction

In JPA, `flush()` sends pending changes to the database, while `clear()` evicts managed entities from the persistence context. These operations help inspect SQL and reload data, but they neither change the isolation level nor start a new transaction.

To test visibility between two transactions, you need two genuinely independent transactions, typically running on two connections. Calling two repository methods back-to-back inside the same test transaction is not enough to simulate two concurrent transactions.

## 14. Designing Concurrency Tests to Observe Isolation

Isolation only matters when multiple transactions operate concurrently. A test executing sequentially inside one transaction cannot prove whether dirty reads, non-repeatable reads, or lost updates occur.

A concurrency test typically needs:

1. Two distinct transactions, each with its own connection.
2. Synchronized read/write timing using latches, barriers, or coordination primitives.
3. A deterministic sequence of operations reproducing the anomaly under test.
4. Finite timeouts so tests do not hang if a transaction is blocked on a lock.
5. Data cleanup after both transactions complete.

Do not use `Thread.sleep` to guess when the other transaction has committed. Use `CountDownLatch`, `CyclicBarrier`, `Phaser`, or futures to coordinate steps accurately.

### 14.1. Creating Independent Transactions with `TransactionTemplate`

`TransactionTemplate` lets tests create transactions on a specific manager:

```java
@SpringBootTest
class IsolationIntegrationTest {
    @Autowired
    PlatformTransactionManager transactionManager;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void executesWorkInSeparateTransactions() {
        TransactionTemplate first = new TransactionTemplate(transactionManager);
        TransactionTemplate second = new TransactionTemplate(transactionManager);

        first.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
        second.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);

        first.executeWithoutResult(status -> {
            // First transaction.
        });

        second.executeWithoutResult(status -> {
            // Second transaction.
        });
    }
}
```

This snippet illustrates creating transactions with distinct isolation settings; to observe anomalies, execute them concurrently on different threads and coordinate steps with synchronization primitives. Calling them sequentially as shown has no concurrent contention.

### 14.2. Test-Managed Transactions and Thread Binding

Spring transactions are normally bound to the current thread. A task running in `@Async`, an executor, or another thread does not automatically join the calling thread's test transaction. This is crucial when writing concurrency tests: each worker must open its own transaction via `TransactionTemplate` or a transactional service invoked through a proxy.

Do not pass a managed `EntityManager` or JDBC `Connection` from the test thread to worker threads. Each transaction needs resources bound appropriately to its thread and transaction manager.

### 14.3. Example Coordinating Two Transactions

A skeleton example using latches:

```java
CountDownLatch firstReadDone = new CountDownLatch(1);
CountDownLatch allowFirstToContinue = new CountDownLatch(1);

ExecutorService executor = Executors.newFixedThreadPool(2);
try {
    Future<BigDecimal> first = executor.submit(() ->
            transactionTemplate.execute(status -> {
                BigDecimal initial = readBalance();
                firstReadDone.countDown();
                await(allowFirstToContinue);
                return readBalance();
            }));

    Future<?> second = executor.submit(() -> {
        await(firstReadDone);
        transactionTemplate.executeWithoutResult(status -> updateBalance("150.00"));
    });

    second.get(5, TimeUnit.SECONDS);
    allowFirstToContinue.countDown();
    BigDecimal valueSeenAgain = first.get(5, TimeUnit.SECONDS);
} finally {
    allowFirstToContinue.countDown();
    executor.shutdownNow();
}
```

This is a coordination skeleton; in an actual test, each worker must use a transaction template configured with the right manager and isolation, `await` must handle timeouts/interruptions, and data must be created and cleaned up independently. Expected outcomes depend on the isolation level and database engine. Do not treat this skeleton as a portable assertion across all databases.

## 15. Anomalies to Test

### 15.1. Dirty Read

To test dirty reads, transaction A updates a row without committing; transaction B reads the row in the meantime; then A rolls back. If B sees the uncommitted value, a dirty read occurred.

Most production databases default to at least `READ_COMMITTED` or stronger semantics. When testing `READ_UNCOMMITTED`, verify whether the engine truly supports it or upgrades it to `READ_COMMITTED`.

### 15.2. Non-Repeatable Read

Transaction A reads a row. Transaction B updates the row and commits. Transaction A reads the same row again. Under `READ_COMMITTED`, the second value may differ; under stronger isolation, the database may maintain a snapshot or lock so the value stays unchanged.

The test must ensure both reads by A occur inside the same transaction and B commits in between. If each read opens a new transaction, the test no longer tests non-repeatable reads.

### 15.3. Phantom Read

Transaction A executes a predicate query, such as `status = 'OPEN'`. Transaction B inserts a new row with status `OPEN` and commits. A runs the same query again. If the row set changes, the test observes a phantom.

Some engines use snapshots or range locks to prevent this phenomenon at certain isolation levels. Run the test on the target database and verify its specific semantics.

### 15.4. Lost Update

Two transactions both read balance 100. T1 computes 110, T2 computes 120; both write back values based on the stale snapshot. If T2 writes after T1, the final result might be 120 instead of 130 or another value expected by business rules.

To prevent lost updates, applications can use optimistic locking (`@Version`), pessimistic locking (`SELECT ... FOR UPDATE`), atomic update queries, or appropriate isolation. Tests must run two competing transactions and assert that one is rejected/retried or the final outcome preserves the invariant.

### 15.5. Write Skew

Write skew occurs when two transactions read the same data set, each updates a different row, and both commit, violating a global invariant. For example, a system requires at least one doctor on call. Two transactions both read that two doctors are on call, and each takes one off duty; without protection, zero doctors remain on call.

`REPEATABLE_READ` based on snapshot isolation can still allow write skew in some databases. `SERIALIZABLE`, appropriate constraints, or locking at the right scope can prevent this bug. Tests must model the actual invariant rather than merely verifying two rows were updated.

## 16. Isolation Does Not Replace Optimistic/Pessimistic Locking

Isolation level is a transaction property. Optimistic and pessimistic locking are concurrency coordination mechanisms at the row/entity or query level. They can complement isolation but are not synonymous with it.

### 16.1. Optimistic Locking with `@Version`

JPA supports optimistic locking via `@Version`:

```java
@Entity
class InventoryItem {
    @Id
    private Long id;

    private int quantity;

    @Version
    private long version;
}
```

When two transactions update the same entity concurrently, the provider checks the version. The second writer may receive `OptimisticLockException` or the corresponding Spring-translated exception if the version changed.

Tests need two separate persistence contexts/transactions to confirm the conflict. Two entity references in the same persistence context do not simulate two independent transactions.

### 16.2. Pessimistic Locking

A repository can request a lock:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select i from InventoryItem i where i.id = :id")
Optional<InventoryItem> findForUpdate(@Param("id") Long id);
```

Hibernate generates lock SQL matching the dialect. Lock syntax and behavior vary across databases. Tests should verify the second transaction blocks or fails according to configured timeout/deadlock policies.

Do not use sleep to test locks. Use latches to hold the first transaction open while the second attempts to acquire the lock, and set test timeouts to avoid hanging the suite.

## 17. Database Default Isolation and Actual Configuration

Default isolation can vary by engine and server configuration. For instance, many PostgreSQL setups default to `READ COMMITTED`, while MySQL InnoDB typically defaults to `REPEATABLE READ`. DBAs or connection/session settings can change defaults.

Therefore, tests should not infer isolation solely from the database name. Check:

- Datasource/session isolation configuration.
- `@Transactional(isolation = ...)` on services and tests.
- Selected transaction manager.
- Whether propagation joins an existing transaction or starts a new one.
- Driver and database version.
- Engine-specific settings such as snapshot isolation or row versioning.

If the application relies on a specific isolation level, configure it explicitly on critical transaction boundaries and test on the target database. If the application uses the database default, document that default in operational configuration and re-verify when upgrading the engine version.

## 18. Testing Dialect and Isolation Bugs in CI

A data-layer suite can be divided into groups:

| Group | Goal | How to Run |
|---|---|---|
| Fast repository tests | Verify derived queries and basic mappings | Embedded database can be used once limits are understood |
| Dialect integration | Native SQL, JSON, sequences, collations, and type mappings | Testcontainers with the production engine |
| Migrations | Schema and data after Flyway/Liquibase | Database container matching engine/version |
| Concurrency/isolation | Locking, transaction anomalies, optimistic versioning | Real database, concurrent tests with synchronization |
| Compatibility matrix | Support for multiple engines/versions | Separate CI job per engine/version |

For stable CI:

- Pin image versions instead of using mutable tags.
- Ensure tests clean up data and resources.
- Use timeouts for locks, futures, and latches.
- Avoid depending on test order or leftover data from previous runs.
- Distinguish container-readiness errors from actual SQL failures.
- Run concurrency tests only when the environment has adequate resources and tests use deterministic synchronization.

## 19. Common Errors and How to Handle Them

### Passes on H2 but Fails in Production

Queries may use engine-specific syntax or data types. Run related tests on the exact database engine; prefer Testcontainers for native SQL, migrations, and locking.

### Temporal Data Differs by Milliseconds or Microseconds

The database or driver has different precision than Java. Identify column precision, rounding rules, and time zones; compare according to the actual contract.

### `BigDecimal` Not Equal Despite Identical-Looking Values

`equals` distinguishes scale. Use numeric comparison if scale is not part of the contract, or verify scale explicitly when required.

### Reloaded UUID Differs from Written Format

The database may use native UUID, binary, or strings. Check mappings/drivers and test round-trips on a real engine.

### Queries Sort Strings Differently

Collation affects case sensitivity, accents, and ordering. Use a database with production collation and write assertions reflecting actual search rules.

### Test Transaction Does Not Roll Back Data

Operations may use a different transaction manager, `REQUIRES_NEW` propagation, async threads, or connections outside the test transaction. Identify actual transaction boundaries and managers.

### Isolation Annotation Appears to Have No Effect

The method may be joining an existing transaction with a different isolation level. Start a new transaction or use `REQUIRES_NEW`/`TransactionTemplate` to control boundaries explicitly.

### Concurrency Test Hangs

A thread may be holding a lock or latch that was not released on test failure. Use `try/finally`, finite timeouts, and always release synchronization primitives during cleanup.

### Isolation Outcomes Differ Between Databases

Engines use distinct MVCC, locking, and semantics. Do not claim an anomaly behaves identically across all engines based only on the isolation level name; run tests on the actual engine/version.

## 20. Workflow for Designing Data-Layer Tests

When testing repositories or transactions, follow this sequence:

1. Identify the target production database engine and version to be compatible with.
2. Identify whether queries use JPQL/Criteria or native SQL.
3. List data types at risk of divergence: decimals, UUIDs, JSON, timestamps, booleans, binaries, and collations.
4. Choose an embedded database or a real database based on what needs to be proven.
5. If a real database is needed, launch Testcontainers with the matching image version and keep the configured datasource.
6. Run actual migrations if the test needs to verify the production schema.
7. Call `flush()` and `clear()` when verifying SQL, constraints, and reloaded data.
8. Identify the transaction manager, propagation, and isolation level for each operation.
9. For concurrency, use separate transactions/connections and coordinate via latches/barriers instead of sleep.
10. Assert final outcomes, conflict errors, or rollbacks per contract and clean up any committed data.

Each test should answer one clear question: does this query run on this dialect, does the mapping preserve data properly, do migrations build the right schema, or does isolation protect the invariant? When goals are separated this way, bugs are easy to diagnose and the suite avoids booting heavy databases for every unit test.

## 21. Principles to Remember

- SQL dialects affect syntax, functions, data types, generated keys, collations, and locking.
- Embedded databases do not prove native SQL or transaction behavior matches production.
- Use Testcontainers or a matching engine/version environment when tests depend on dialects, migrations, data types, or isolation.
- Verify round-trips for `BigDecimal`, UUID, JSON, timestamps, binaries, and boolean/null values under actual semantics.
- `flush()` forces synchronization with the database; `clear()` forces reloading through a fresh persistence context, yet neither starts a new transaction.
- Isolation levels determine how transactions observe changes; actual semantics also depend on database engine and version.
- `@Transactional(isolation = ...)` does not upgrade the isolation of an existing transaction that a method joins.
- Test-managed transactions typically roll back after tests, but other transaction managers, `REQUIRES_NEW`, or separate threads can create data that persists independently.
- Concurrency tests need separate transactions and connections, deterministic synchronization, finite timeouts, and reliable cleanup.
- Isolation does not replace optimistic/pessimistic locking or constraints protecting business invariants.

Reliable data-layer testing must reflect the database the application will run against. By choosing the right engine, verifying data types via round-trips, and establishing deliberate transaction boundaries, tests can catch dialect, mapping, and concurrency bugs before they appear in production.
