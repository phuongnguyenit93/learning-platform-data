# Verifying Queries, Mappings, Constraints, and Exceptions

The data layer translates between the application's object model and stored data. A repository may be created successfully by Spring and an EntityManager may be injected properly, yet a query still returns the wrong records; an entity may be saved in memory while its column mapping is wrong; a constraint violation may only surface when SQL is actually sent to the database; and errors from JDBC or JPA may be translated into different exception types at the Spring boundary.

Data-layer testing needs to verify several distinct behaviors:

- **Queries:** are filter conditions, joins, sorting, pagination, and returned results correct?
- **Mappings:** is data between tables/columns and entities/objects converted accurately?
- **Constraints:** does the database enforce primary keys, foreign keys, unique, not-null, and schema conditions?
- **Exceptions:** how are query errors, data errors, or connection errors detected and translated?

Spring Boot provides test slices such as **@DataJpaTest**, **@JdbcTest**, and **@DataJdbcTest** to create a test scope focused on persistence. The Spring Framework TestContext provides the context, test transactions, **@Sql**, and other utilities. When choosing the right scope and the right database, tests can catch repository and mapping bugs before they appear in broader business flows.

## 1. Distinguishing Data-Layer Test Types

Not every test involving a repository checks the same thing. Define the question before choosing the tool.

| Goal | Scope to Run | Common Tools |
|---|---|---|
| Business rules calling repositories correctly | Application service | Plain JUnit with fake/mock repository |
| Derived queries, JPQL, native queries | Spring Data JPA repository | @DataJpaTest |
| Entities, relationships, converters, and persistence | JPA provider + database | @DataJpaTest, TestEntityManager |
| SQL via JdbcTemplate | JDBC layer | @JdbcTest |
| Spring Data JDBC repositories | Spring Data JDBC | @DataJdbcTest |
| Production migrations and schema | Database with matching engine | Testcontainers + migration tool |
| Transactions across multiple components | Application context and database | @SpringBootTest or appropriately scoped integration test |

A unit test using a mock repository can verify that a service calls findById() or save() according to contract. It does not execute SQL and does not prove the query is correct. To test queries, mappings, or constraints, the test must go through the persistence adapter and an actually running database.

### @DataJpaTest

@DataJpaTest is Spring Boot's test slice for JPA. It typically configures:

- Entity scanning.
- Spring Data JPA repositories.
- EntityManager and JPA provider.
- DataSource and appropriate transaction manager.
- JPA-related configurations within the slice scope.
- TestEntityManager to support persistence testing.

Tests usually run in a transaction and roll back after each method. By default, Spring Boot may replace the configured DataSource with an embedded database if one is on the classpath. This makes tests fast, but can cause results to differ from the production database.

### @JdbcTest

@JdbcTest creates a slice focused on JDBC, typically configuring DataSource, JdbcTemplate, and a transaction manager without loading all application services or the web layer.

Use it when you need to test SQL executed via JdbcTemplate, RowMapper, NamedParameterJdbcTemplate, or related JDBC components.

### @DataJdbcTest

@DataJdbcTest is dedicated to Spring Data JDBC. It tests aggregate mappings and repositories following the Spring Data JDBC model, which differs from JPA/Hibernate. Do not use @DataJpaTest merely because the project has Spring Data in its name; choose the slice matching the actual persistence technology.

## 2. Testing Repositories with @DataJpaTest

Suppose an application manages customers:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, unique = true)
    private String email;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByDisplayNameContainingIgnoreCase(
            String keyword
    );
}
~~~

Test slice:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerByEmail() {
        Customer saved = repository.save(
                new Customer("lan@example.test", "Lan Nguyen")
        );

        Optional<Customer> actual =
                repository.findByEmail("lan@example.test");

        assertTrue(actual.isPresent());
        assertEquals(saved.getId(), actual.orElseThrow().getId());
    }
}
~~~

This test creates a context focused on JPA, saves a record, and executes the derived query generated by Spring Data JPA. If the method name, property path, or mapping is wrong, errors may appear when initializing the repository or when the query executes.

Do not assert only that the Optional is non-null. Check the right record, key fields, and the not-found case:

~~~java
@Test
void returnsEmptyWhenEmailDoesNotExist() {
    assertTrue(repository.findByEmail("missing@example.test").isEmpty());
}
~~~

Tests with missing or empty input data are often helpful to guard repository semantics, especially when queries involve filter conditions or joins.

### When a Repository Needs Additional Configuration

@DataJpaTest does not load the full component scan like @SpringBootTest. If a repository depends on a converter, custom repository implementation, or dedicated configuration, you can import the required configuration:

~~~java
@DataJpaTest
@Import(CustomerJpaTestConfiguration.class)
class CustomerRepositoryTest {
    // Repository tests
}
~~~

Import only the relevant configuration. If all services, web servers, and multiple infrastructure layers are needed simultaneously, that indicates a need for a broader integration test.

## 3. Creating Intentional Test Data

Query tests are only valuable when data distinguishes the conditions being tested. A test filtering by status needs records across multiple statuses; a sorting test needs data with differing sort values; a pagination test needs enough records to cross page boundaries.

Example repository:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);

    Page<Order> findByCustomerId(
            Long customerId,
            Pageable pageable
    );
}
~~~

The test can set up explicit fixtures:

~~~java
@Test
void filtersAndSortsOrdersByStatus() {
    repository.save(new Order(
            10L, OrderStatus.PENDING,
            Instant.parse("2026-01-01T10:00:00Z")
    ));
    repository.save(new Order(
            10L, OrderStatus.PAID,
            Instant.parse("2026-01-02T10:00:00Z")
    ));
    repository.save(new Order(
            10L, OrderStatus.PENDING,
            Instant.parse("2026-01-03T10:00:00Z")
    ));

    List<Order> actual =
            repository.findByStatusOrderByCreatedAtDesc(
                    OrderStatus.PENDING
            );

    assertEquals(2, actual.size());
    assertEquals(
            Instant.parse("2026-01-03T10:00:00Z"),
            actual.get(0).getCreatedAt()
    );
    assertEquals(
            Instant.parse("2026-01-01T10:00:00Z"),
            actual.get(1).getCreatedAt()
    );
}
~~~

Principles for creating fixtures:

- Use fixed, meaningful, and readable values.
- Create both matching and non-matching records.
- Create boundary data for date ranges, quantities, statuses, and nulls.
- Do not rely on auto-generated IDs unless IDs are what is being tested.
- Do not assume return order if the query does not declare ORDER BY.
- Each test should prepare its own data or use a repeatable fixture script.

If multiple tests share a fixture helper, the helper should create fresh data for each test or ensure data is rolled back/cleaned up. Avoid static mutable fixtures or execution-order dependencies.

## 4. Verifying Derived Queries and JPQL

Spring Data JPA can generate queries from method names. Tests should verify the method expresses the right property paths and intended conditions.

Example:

~~~java
List<Customer> findByStatusAndCreatedAtAfter(
        CustomerStatus status,
        Instant createdAt
);
~~~

Tests should include records that are:

- Matching status and after the cutoff timestamp.
- Matching status but before the cutoff timestamp.
- Wrong status but after the cutoff timestamp.
- Matching status and exactly equal to the cutoff timestamp if boundary semantics matter.

This helps catch confusion between After and GreaterThanEqual, or wrong property paths in the method name.

### Testing JPQL

With explicitly written queries:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
        select o
        from Order o
        where o.customerId = :customerId
          and o.status = :status
        order by o.createdAt desc
        """)
    List<Order> findRecentOrders(
            @Param("customerId") Long customerId,
            @Param("status") OrderStatus status
    );
}
~~~

Tests must verify both the predicate and the result ordering. A query may compile yet still be logically wrong, such as using the wrong attribute, missing a condition, joining incorrectly, or sorting by another column.

### Queries with Joins and Entity Relationships

When a query traverses a relationship:

~~~java
@Query("""
    select o
    from Order o
    join o.customer c
    where c.email = :email
    """)
List<Order> findByCustomerEmail(@Param("email") String email);
~~~

Create multiple customers and orders to verify results contain only orders belonging to the specified customer. If using left join, test both cases with and without a related record. If using distinct, test to verify there are no duplicate records when joining a collection.

With OneToMany or ManyToMany relationships, joins can produce multiple SQL rows for the same entity. Object results and how Hibernate handles duplicates depend on the query and mapping. Test data must be rich enough to expose such issues.

## 5. Verifying Native Queries, Projections, and Pagination

### Native SQL Queries

Native queries execute SQL directly on the database:

~~~java
@Query(
    value = """
        select *
        from orders
        where customer_id = :customerId
          and status = :status
        order by created_at desc
        """,
    nativeQuery = true
)
List<Order> findNativeOrders(
        @Param("customerId") Long customerId,
        @Param("status") String status
);
~~~

Native queries can depend on dialect, table/column names, data types, and database-specific functions. Passing on H2 does not automatically prove the SQL statement works on PostgreSQL or MySQL. For critical native queries, run against the exact target database engine or a version compatible with production.

### Projections

Spring Data projections can return an interface or DTO instead of the full entity. Tests need to verify that column aliases match properties, data types are converted properly, and selected fields are not swapped.

~~~java
public interface CustomerSummary {
    String getEmail();
    String getDisplayName();
}
~~~

~~~java
@Query("""
    select c.email as email,
           c.displayName as displayName
    from Customer c
    where c.id = :id
    """)
Optional<CustomerSummary> findSummaryById(@Param("id") Long id);
~~~

Assertions should check each field of the projection. Merely checking that the projection is present can miss alias bugs or swapped return values.

### Pagination and Sorting

Example:

~~~java
Page<Order> findByCustomerId(Long customerId, Pageable pageable);
~~~

A test can verify:

~~~java
Page<Order> page = repository.findByCustomerId(
        customerId,
        PageRequest.of(0, 2, Sort.by("createdAt").descending())
);

assertEquals(2, page.getContent().size());
assertEquals(3, page.getTotalElements());
assertEquals(2, page.getTotalPages());
assertTrue(page.getContent().get(0).getCreatedAt()
        .isAfter(page.getContent().get(1).getCreatedAt()));
~~~

Create more records than the page size to test pagination. With complex queries, verify the count query is right; an incorrect total count can cause totalElements and totalPages to be wrong even when the first page's content looks right.

If using Pageable in a native query, you may need to declare a separate countQuery so Spring Data can compute the total record count. Tests should cover multiple pages, the last page, and the empty-result case.

## 6. Entity and Column Mappings

An entity instantiated properly in Java does not prove database mapping is accurate. Mappings are only verified when data is written to the database and read back.

Aspects that commonly need verification:

- Table and column names.
- Data types and lengths.
- Auto-generated IDs and generation strategies.
- Enums stored as string vs. ordinal.
- Embedded objects and attribute overrides.
- ManyToOne, OneToMany, OneToOne, and ManyToMany relationships.
- Cascade, orphan removal, and fetch behavior.
- Converters for custom types.
- Version columns for optimistic locking.
- Nullability and default values.

### Using Flush and Clear to Verify Data Is Actually Persisted

In JPA, an entity may still reside in the persistence context. If a test saves and immediately reads back the same ID, EntityManager may return the managed object without querying the database.

To verify round-trip mapping:

~~~java
@DataJpaTest
class CustomerMappingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void persistsAndReloadsCustomerFields() {
        Customer customer =
                new Customer("lan@example.test", "Lan Nguyen");

        entityManager.persist(customer);
        entityManager.flush();

        Long id = customer.getId();

        entityManager.clear();

        Customer reloaded = entityManager.find(Customer.class, id);

        assertEquals("lan@example.test", reloaded.getEmail());
        assertEquals("Lan Nguyen", reloaded.getDisplayName());
    }
}
~~~

flush() forces JPA to synchronize the persistence context with the database. clear() detaches managed entities from the persistence context. The subsequent find() must fetch data again through the persistence layer, helping the test verify read/write mappings more thoroughly.

TestEntityManager can be used for persist, flush, clear, and find operations. For tests not using Spring Boot's JPA slice, you can inject EntityManager or use EntityManagerFactory per the test configuration.

### Testing Enums

If an enum is stored by ordinal, changing the order of enum constants can corrupt existing data. Using @Enumerated(EnumType.STRING) is usually more readable and less vulnerable to reordering, though column length and valid values still need verification.

Tests should persist an enum, flush/clear, and read it back. To confirm the physical value stored in the column, JdbcTemplate or a native query can be used to inspect actual stored contents.

### Testing Converters

With AttributeConverter, tests must verify conversion in both directions:

~~~java
@Converter
public class MoneyConverter
        implements AttributeConverter<Money, BigDecimal> {

    @Override
    public BigDecimal convertToDatabaseColumn(Money money) {
        return money == null ? null : money.amount();
    }

    @Override
    public Money convertToEntityAttribute(BigDecimal value) {
        return value == null ? null : new Money(value);
    }
}
~~~

Round-trip tests should cover normal values, zero, null if permitted, and boundary values. If the converter has rounding or scale rules, assertions must verify that exact policy.

### Testing Relationships and Cascades

Suppose Order has multiple OrderLines. Tests should verify:

- Whether saving an order cascades persist to lines.
- Whether deleting an order cascades remove to lines if required by the mapping.
- Whether removing a line from the collection triggers orphan removal.
- Whether foreign keys are set properly.
- Whether the owning side of the relationship is updated properly.

JPA only persists relationships based on the owning side. If a test modifies only the inverse side, data may not update as expected. Check the entity mapping and how both sides of the relationship are maintained.

## 7. Testing Constraints at Two Layers: Bean Validation and Database

A common mistake is confusing validation annotations with schema constraints.

~~~java
@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    @Column(name = "email", nullable = false)
    private String email;
}
~~~

There are two separate mechanisms:

- @NotBlank is a Bean Validation constraint. It validates string contents and may execute before JPA writes the entity if Bean Validation is integrated.
- nullable = false and @UniqueConstraint describe schema metadata for the JPA provider when the schema is generated from mappings. Actual constraints must exist in the running database.

In production environments, schemas are typically managed via Flyway, Liquibase, or SQL migrations. In that case, tests must verify that migrations created the real constraints. Entity annotations alone do not prove the production schema enforces the same constraints.

### Testing Bean Validation

If the goal is to verify Bean Validation:

~~~java
@Test
void rejectsBlankEmailBeforePersistence() {
    Customer customer = new Customer(" ", "Lan");

    assertThrows(
            jakarta.validation.ConstraintViolationException.class,
            () -> validator.validate(customer)
    );
}
~~~

This example uses jakarta.validation.ConstraintViolationException thrown by Bean Validation. It does not prove the database has a NOT NULL constraint.

If the goal is to verify a database NOT NULL constraint, SQL must be sent or the entity flushed to a database whose schema actually enforces the constraint. The exception then originates from the JDBC driver/JPA provider and may be translated by Spring into DataIntegrityViolationException at the repository layer.

### Testing Unique Constraints

Tests need to create a first record and then attempt to write a second record violating the same unique key:

~~~java
@Test
void rejectsDuplicateEmail() {
    repository.saveAndFlush(
            new Customer("lan@example.test", "Lan")
    );

    assertThrows(
            DataIntegrityViolationException.class,
            () -> repository.saveAndFlush(
                    new Customer("lan@example.test", "Lan Two")
            )
    );
}
~~~

saveAndFlush() is helpful because it forces SQL to be sent while the test is executing. If only save() is called, the unique violation might only appear during automatic flush or transaction commit, which could happen outside the assertion lambda.

The exact exception name and deeper cause depend on the persistence provider, driver, and exception translation mechanism. With Spring Data repositories, integrity errors are usually translated into DataIntegrityViolationException. Inspect the cause chain if you need to distinguish unique, foreign key, or not-null violations.

### Testing Foreign Key and Check Constraints

To test a foreign key, create an entity referencing a nonexistent parent record or use JDBC to insert an invalid value. Ensure the test schema has real foreign key constraints. If Hibernate generates a schema missing a constraint, tests may pass even when production migrations enforce different rules.

For databases supporting CHECK constraints, you can verify invalid values are rejected, such as requiring quantity greater than 0. If constraints are created by migrations, tests should initialize the schema from migrations to verify the exact deployed DDL.

## 8. Distinguishing Exceptions from Bean Validation, JPA, Hibernate, and Spring

Multiple layers can raise exceptions with similar names or meanings. Determine where the failure occurred.

| Layer | Example Exceptions | Meaning |
|---|---|---|
| Jakarta Bean Validation | jakarta.validation.ConstraintViolationException | Object violates validation constraints |
| JPA | jakarta.persistence.PersistenceException, EntityExistsException, OptimisticLockException | Persistence contract failure |
| Hibernate | org.hibernate.exception.ConstraintViolationException | Database constraint violated via Hibernate |
| Spring DAO translation | DataIntegrityViolationException, DuplicateKeyException | Persistence error translated into DataAccessException |
| JDBC | SQLException and subclasses | Driver reports SQL or connection error |

Note that two classes share the simple name ConstraintViolationException:

- jakarta.validation.ConstraintViolationException belongs to Bean Validation.
- org.hibernate.exception.ConstraintViolationException belongs to Hibernate and describes a database constraint failure.

When writing imports or reading stack traces, check the full package name.

### Spring Exception Translation

Spring provides a mechanism to translate persistence-API-specific exceptions into a consistent hierarchy under DataAccessException. With Spring Data repositories, the repository proxy typically applies the appropriate translation mechanism. With JDBC, JdbcTemplate also translates SQLException into DataAccessException.

This keeps services from depending directly on Hibernate or JDBC driver exceptions. For example, duplicate keys may be represented by DuplicateKeyException, while other integrity violations usually go through DataIntegrityViolationException.

Do not assert entire driver error messages because messages can vary across database versions, locales, or drivers. If the application contract specifies a Spring exception type, assert that exception type and, when needed, inspect the cause or constraint name in the least environment-dependent way.

## 9. Testing Exceptions at the Exact Moment SQL Executes

With JPA, calling save() may not send SQL immediately. Hibernate may defer writes until flush. Therefore, constraint tests must flush explicitly.

Three common ways:

~~~java
repository.save(entity);
entityManager.flush();
~~~

Or:

~~~java
repository.saveAndFlush(entity);
~~~

Or:

~~~java
entityManager.persist(entity);
entityManager.flush();
~~~

Place the flush inside the assertThrows lambda so the assertion catches the exception properly:

~~~java
assertThrows(
        DataIntegrityViolationException.class,
        () -> {
            repository.save(entity);
            entityManager.flush();
        }
);
~~~

If a flush fails, the current transaction may be marked rollback-only or become unusable depending on provider/database. Do not continue performing additional persistence operations in the same transaction after a constraint failure and expect normal state. Let the test finish and roll back, or use separate test methods per error case.

With JDBC, SQL statements typically execute immediately when calling update() or execute(), so exceptions usually appear directly at that call:

~~~java
assertThrows(
        DataIntegrityViolationException.class,
        () -> jdbcTemplate.update(
                "insert into customers(email, display_name) values (?, ?)",
                "lan@example.test",
                "Duplicate"
        )
);
~~~

Tests should isolate the exact operation expected to fail rather than wrapping a long setup block inside a broad lambda, which could cause the assertion to catch an accidental exception from data setup.

## 10. Testing Exception Translation with JdbcTemplate

JdbcTemplate translates SQLException into Spring's exception hierarchy. Example repository:

~~~java
@Repository
public class CustomerJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    public CustomerJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public CustomerRow findByEmail(String email) {
        return jdbcTemplate.queryForObject(
                """
                select id, email, display_name
                from customers
                where email = ?
                """,
                (rs, rowNum) -> new CustomerRow(
                        rs.getLong("id"),
                        rs.getString("email"),
                        rs.getString("display_name")
                ),
                email
        );
    }
}
~~~

If the query returns no records, queryForObject() typically throws EmptyResultDataAccessException. If the query returns multiple rows when the API expects a single row, IncorrectResultSizeDataAccessException may be thrown.

A test can verify the contract:

~~~java
@Test
void reportsMissingCustomer() {
    assertThrows(
            EmptyResultDataAccessException.class,
            () -> repository.findByEmail("missing@example.test")
    );
}
~~~

If the repository is designed to return Optional<Customer>, verify that it returns Optional.empty() rather than letting an exception leak. Tests must reflect the contract the repository actually advertises.

### Distinguishing Data Errors from Infrastructure Errors

Other error categories include:

- DataIntegrityViolationException: data violates a constraint.
- DuplicateKeyException: duplicate key error specifically identified.
- QueryTimeoutException: query exceeded time limit reported by driver/database.
- CannotAcquireLockException: failed to acquire lock for data operation.
- DataAccessResourceFailureException: failure accessing the data resource.
- TransientDataAccessException: potentially temporary failure, eligible for retry depending on policy.

Do not write tests that intentionally break the production database or real network. Use a test database, controlled timeout configuration, or fake adapters for retry logic; testing actual infrastructure failures requires an isolated environment.

## 11. Testing @JdbcTest and RowMapper

When code uses JdbcTemplate, tests must verify SQL, parameter binding, and ResultSet mapping.

~~~java
@Repository
public class ProductJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    public ProductJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<ProductRow> findBySku(String sku) {
        return jdbcTemplate.query(
                """
                select sku, product_name, unit_price
                from products
                where sku = ?
                """,
                (rs, rowNum) -> new ProductRow(
                        rs.getString("sku"),
                        rs.getString("product_name"),
                        rs.getBigDecimal("unit_price")
                ),
                sku
        ).stream().findFirst();
    }
}
~~~

Test:

~~~java
@JdbcTest
@Import(ProductJdbcRepository.class)
class ProductJdbcRepositoryTest {

    @Autowired
    private ProductJdbcRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void mapsSelectedColumnsToProductRow() {
        jdbcTemplate.update(
                """
                insert into products(sku, product_name, unit_price)
                values (?, ?, ?)
                """,
                "SKU-01",
                "Keyboard",
                new BigDecimal("125000.00")
        );

        ProductRow actual =
                repository.findBySku("SKU-01").orElseThrow();

        assertEquals("SKU-01", actual.sku());
        assertEquals("Keyboard", actual.name());
        assertEquals(new BigDecimal("125000.00"), actual.unitPrice());
    }
}
~~~

@JdbcTest does not necessarily scan every repository component in the application. If the class under test is not automatically included in the slice, use @Import to register it.

What to verify in JDBC tests:

- SQL uses the correct tables and columns.
- Parameters are bound in the right order or with the right names.
- RowMapper reads the right column labels.
- Data types are converted accurately.
- Nulls are handled properly.
- Empty and multi-result queries behave according to contract.
- Batch updates or generated keys are read properly if used.

Do not merely check that a query runs without checking column values. A RowMapper could swap two columns of the same type and a test asserting only object existence would miss the bug.

## 12. Using @Sql to Prepare and Clean Up Data

Spring TestContext supports @Sql to execute SQL scripts before or after a test method. This is useful when fixtures involve multiple tables, relational data, or states where entity creation does not faithfully reflect the database structure.

Example:

~~~java
@DataJpaTest
@Sql(
    scripts = "/sql/customer-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class CustomerSearchRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerCreatedBySqlFixture() {
        assertTrue(
                repository.findByEmail("fixture@example.test").isPresent()
        );
    }
}
~~~

SQL files live in the test classpath, such as src/test/resources/sql/customer-test-data.sql.

@Sql can be applied at class or method level. Method level fits when each test needs a different data set. Class level fits shared data, though transaction and cleanup implications must be considered.

### @SqlConfig and Transaction Modes

@SqlConfig allows customizing how Spring executes scripts, such as:

- Which DataSource or transaction manager is used.
- Statement separator.
- Encoding.
- Error mode.
- Transaction mode.

With test-managed transactions, scripts usually participate in the test's transaction by default. If a script needs to run in its own transaction, transaction mode ISOLATED can be used. In that case, data committed by the script persists outside the test transaction and requires explicit cleanup.

Do not use ISOLATED arbitrarily because it can prevent fixture data from rolling back with the test. Be clear about which transaction setup scripts belong to and who is responsible for data cleanup.

## 13. Testing Transactions, Rollback, and Committed Data

@DataJpaTest usually runs test methods in a transaction and rolls back when finished. This keeps tests independent and avoids accumulating data. However, rollback can hide issues related to commits.

For instance, to test behavior that only occurs when a transaction commits, a test can use TestTransaction:

~~~java
@DataJpaTest
class CustomerCommitTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void commitsThenReadsCustomer() {
        repository.save(new Customer("commit@example.test", "Commit"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertTrue(repository.findByEmail("commit@example.test").isPresent());

        TestTransaction.start();
    }
}
~~~

After committing the first transaction, the test can start a new transaction for subsequent steps. If no second transaction is needed, calling start() is unnecessary.

Committed data must be cleaned up. If the test runs again, the persisted record could cause a duplicate key error or alter results. You can use unique IDs, explicit cleanup, or a dedicated test database/schema.

If you need to test transaction isolation or locking between two concurrent transactions, a single test with one test-managed transaction is not enough. You must create two independent transactions, control execution order, and use a database with appropriate semantics.

## 14. Embedded Database or Production-Like Database?

An embedded database like H2 usually makes tests fast and easy to run locally. However, it can differ from PostgreSQL, MySQL, or SQL Server in:

- SQL dialect and native query syntax.
- Data types, numeric precision, and time zones.
- Case sensitivity, collation, and string comparisons.
- Sequences, identity columns, and generated keys.
- JSON, arrays, enums, and specialized data types.
- Locking, isolation, and transaction behavior.
- Constraints, indexes, and error reporting.
- SQL functions, stored procedures, and execution plans.

If the application uses simple JPQL and only basic mappings need checking, an embedded database may suffice for part of the suite. If queries depend on database-specific SQL or the production schema, test on the corresponding database engine.

### Not Replacing the Configured Database

In Spring Boot test slices, you can request keeping the configured DataSource instead of replacing it with an embedded database:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class PostgreSqlRepositoryTest {
}
~~~

Then the test uses the database supplied by the test configuration. Ensure the endpoint is an isolated test database, not production or an unintended shared database.

### Using Testcontainers

Testcontainers can spin up a production-compatible database in the test environment:

~~~java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class PostgreSqlCustomerRepositoryTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

The example requires matching Testcontainers PostgreSQL and JUnit Jupiter dependencies. The image tag should be pinned to the version the project targets rather than using a floating tag.

With Spring Boot versions supporting service connections, @ServiceConnection can be used so Boot automatically retrieves connection details from the container. With @DynamicPropertySource, properties are registered via suppliers to read runtime values such as host and port.

Testcontainers enables checking SQL, migrations, constraints, and behavior against a more realistic database. It does not automatically guarantee clean test data; schema, fixtures, transactions, and cleanup still need management.

With context caching, the container lifecycle must align with the ApplicationContext lifecycle. If a context is reused after a container has stopped, the DataSource may retain a dead endpoint. Manage containers at a scope compatible with the tests sharing that context.

## 15. Testing Migrations and Actual Schemas

Entity annotations and the production schema can drift apart. For example, an entity has @Column(nullable = false) while an older migration omitted NOT NULL; or a migration creates a unique index while the entity does not declare unique = true.

If the application uses Flyway or Liquibase, integration tests should start with an empty database and run real migrations. Then run repository tests against the schema created by those migrations.

What to check:

- Migrations run in the right order.
- Constraints and indexes are created.
- Table/column names match mappings.
- Data types match entities.
- Foreign key and cascade behaviors are right.
- Migrating from a prior version upgrades cleanly to the new schema.
- Native queries and stored procedures continue to work.

Do not rely solely on Hibernate ddl-auto=create-drop to conclude production migrations are valid. Hibernate can generate a schema from entities and mask errors in migration files. If the goal is verifying migrations, let the migration tool create the schema.

## 16. Testing Optimistic Locking and Concurrency

Entities can use a version field:

~~~java
@Entity
class Inventory {

    @Id
    private Long id;

    private int quantity;

    @Version
    private long version;
}
~~~

@Version enables detecting concurrent updates based on version numbers. Optimistic locking tests need two independent persistence contexts or transactions:

1. Read the same record from two transactions.
2. First transaction updates and commits.
3. Second transaction attempts to update with the stale version.
4. Assert the second transaction receives an optimistic locking failure.

A test using the same EntityManager or persistence context cannot simulate two independent reads. You must flush and clear, or use two EntityManagers/transactions to create real contention.

The exception may appear as OptimisticLockException in JPA or ObjectOptimisticLockingFailureException in Spring depending on the call path and exception translation layer. Tests should assert the exception type at the API boundary the application exposes.

Pessimistic locking, deadlocks, and timeouts depend on the database engine and transaction coordination. These tests should run on a production-compatible database with bounded timeouts and isolated data.

## 17. Testing Query Failures and Result-Size Errors

A repository method can have different contracts when no record is found:

- Return Optional.empty().
- Return an empty collection.
- Return null if a legacy API or custom implementation allows it.
- Throw an exception if the query requires exactly one result.

Tests must verify the chosen contract.

For example, with JdbcTemplate.queryForObject, zero rows usually leads to EmptyResultDataAccessException. With Spring Data JPA, a method returning Optional can return empty. With a custom query returning a single entity, behavior for zero or multiple results depends on the method signature and provider.

Do not catch generic exceptions broadly and treat them as valid outcomes. Assert the specific exception type and keep the throwing call inside a small lambda:

~~~java
assertThrows(
        IncorrectResultSizeDataAccessException.class,
        () -> repository.findUniqueCustomerByDomain("example.test")
);
~~~

The example exception type must match the actual API. If the query returns Optional, check for empty instead of expecting an exception.

## 18. Common Mistakes When Testing the Data Layer

### Mocking the Repository and Concluding the Query Is Right

Mocks do not execute SQL or JPQL. Use @DataJpaTest or @JdbcTest to verify real queries.

### Calling Save Without Flushing

Constraints or SQL errors may not surface yet. Use saveAndFlush() or EntityManager.flush() when catching errors in tests.

### Reloading an Entity from the Same Persistence Context

EntityManager may return the managed object in memory. Use clear() before reloading to verify round-trip mapping.

### Using H2 When Production Is PostgreSQL

Native queries, types, locking, and constraint behavior may differ. Run production-compatibility tests with Testcontainers when those differences matter.

### Using Entity Schema Generation Instead of Production Migrations

Tests may pass even if migrations are broken. When verifying deployment schemas, run real migrations on an empty test database.

### Over-Asserting Detailed Driver Exception Messages

Driver messages vary by database and version. Prefer asserting exception types, SQL states, or stable and meaningful constraint names.

### Combining Multiple Failure Cases into One Test

If one test checks unique, foreign key, not-null, and query timeout together, pinpointing the failure cause is hard. Separate by behavior and constraint type.

### Order-Dependent Test Data

One test committing data can break another test. Use default transaction rollback, unique IDs, separate schemas/databases, or explicit cleanup.

### Test Transactions Hiding Commit Bugs

Rollback tests do not verify everything that happens on commit. For commit requirements or cross-transaction visibility, use TestTransaction or independent transactions.

### Failing to Verify Pagination Count Queries

The first page may return right content while totalElements is wrong. Test multiple pages and verify the count.

### Failing to Assert Ordering When a Query Requires Ordering

Databases do not guarantee order without ORDER BY. If ordering is part of the contract, declare order in the query and assert it explicitly.

## 19. Workflow for Designing a Repository Test Suite

Tests can be built following these steps:

1. Define repository contracts: inputs, filter conditions, outputs, ordering, and empty-data behavior.
2. Choose the slice matching the technology: @DataJpaTest, @JdbcTest, or @DataJdbcTest.
3. Decide on the database: embedded for fast tests or Testcontainers for compatibility.
4. Prepare fixtures with matching, non-matching, and boundary data.
5. Verify queries with assertions on actual values and ordering.
6. Verify mappings via persist/flush/clear/reload.
7. Verify constraints by forcing SQL execution and asserting the right exceptions.
8. Verify migrations on schemas generated by the migration tool if that is a risk to guard against.
9. Verify transaction rollback/commit according to the test goal.
10. Re-run tests individually and within the full suite to ensure no order dependency.

Not every repository needs to test every item. A simple query does not need locking tests; a converter does not need a web server; a PostgreSQL-dependent native query needs the right database. Choose tests based on risk and actual contracts.

## 20. Criteria for Choosing the Right Evidence per Behavior

| Behavior to Prove | Appropriate Evidence |
|---|---|
| Derived query filters accurately | Call repository against database with discriminating data and assert results |
| JPQL join works properly | Create relational data and verify the result set |
| Native query is compatible | Run on the matching database/dialect |
| Pagination works properly | Check content, totalElements, totalPages, and multiple pages |
| Read/write mapping is accurate | Persist, flush, clear, reload, and compare fields |
| Bean Validation works | Invoke Validator or trigger validation at the right lifecycle |
| Database constraint is enforced | Execute SQL/flush on a schema with real constraints |
| Spring exception translation works | Call via repository/JdbcTemplate and assert the right DataAccessException |
| Migration is valid | Initialize an empty database and run real migrations |
| Optimistic locking works | Two independent transactions/persistence contexts contend on the same record |
| Commit visibility works | Commit the first transaction, then read from another transaction |
| Test rollback works | Verify data is gone after the test transaction ends |

Data-layer testing is valuable when it exercises the exact component responsible for the behavior. Mocking repositories protects how services interact with repositories; test slices and databases protect queries, mappings, and constraints; migration tests protect deployed schemas; transaction tests protect commits, rollbacks, and concurrency. When creating purposeful fixtures, flushing at the right moment, reloading after clearing the persistence context, and choosing a production-compatible database, tests catch bugs that pure unit tests cannot observe.

