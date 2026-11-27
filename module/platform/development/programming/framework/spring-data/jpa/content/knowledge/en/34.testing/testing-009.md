# Testing Derived Queries, JPQL, Native SQL, and Specifications

## Objectives

Spring Data JPA supports multiple ways to build queries: derivation from method names (derived queries), JPQL, plain SQL (native SQL), and Specifications for dynamic queries. Each approach has its own rules for property names, syntax, parameter types, pagination, and database engine dependencies. Repository tests must verify business results against the database, not merely verify that a method was called.

After this lesson, you will be able to:

- Set up repository tests using `@DataJpaTest`.
- Create deterministic test data and control the persistence context.
- Test derived queries, JPQL, native SQL, and Specifications.
- Test sorting, pagination, count queries, and projections.
- Understand transaction rollback in tests.
- Choose an appropriate database for native queries and engine-specific behaviors.

## 1. Distinguishing the Four Query Approaches

| Query Approach | Declaration Style | What to Test |
|---|---|---|
| Derived query | Method name such as `findByStatusAndName...` | Property names, operators, ordering, nulls, and results |
| JPQL | `@Query` with entity query language | Entity names, Java properties, joins, parameters, and results |
| Native SQL | `@Query(nativeQuery = true)` | Table/column names, dialect, data types, and mappings |
| Specification | `Predicate` via Criteria API | Dynamic conditions, combinations, joins, sorting, and pagination |

Derived queries and JPQL are generally independent of table names. Native SQL depends on the specific schema and database engine. Specifications construct predicates via the Criteria API, so both present and absent filter cases must be tested.

## 2. Building a Consistent Test Model

Use a small entity to illustrate all four query styles. Examples assume Spring Boot 3, Jakarta Persistence, and Java 17 or later.

Status enum:

~~~java
public enum CustomerStatus {
    ACTIVE,
    INACTIVE
}
~~~

Entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "customer_record")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private CustomerStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(
            String name,
            String email,
            CustomerStatus status,
            Instant createdAt) {
        this.name = name;
        this.email = email;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public CustomerStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

The enum is stored by name via `EnumType.STRING`, so the `status` column holds `ACTIVE` or `INACTIVE`. The timestamp column is mapped to `created_at`. Those column names are used in native SQL; the Java property names are `name`, `email`, `status`, and `createdAt`.

Repository:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {

    List<Customer>
    findByStatusAndNameContainingIgnoreCaseOrderByNameAsc(
        CustomerStatus status,
        String keyword
    );

    @Query("""
        select c
          from Customer c
         where c.status = :status
           and c.createdAt >= :from
         order by c.createdAt desc
        """)
    List<Customer> findByStatusCreatedSince(
        @Param("status") CustomerStatus status,
        @Param("from") Instant from
    );

    @Query(value = """
        select *
          from customer_record
         where status = :status
         order by created_at desc
        """, nativeQuery = true)
    List<Customer> findNativeByStatus(
        @Param("status") String status
    );

    @Query(
        value = """
            select *
              from customer_record
             where status = :status
             order by created_at desc
            """,
        countQuery = """
            select count(*)
              from customer_record
             where status = :status
            """,
        nativeQuery = true
    )
    Page<Customer> findNativePageByStatus(
        @Param("status") String status,
        Pageable pageable
    );
}
~~~

The repository extends `JpaSpecificationExecutor` to support Specifications. Derived queries use Java property names; JPQL uses entity and property names; native SQL uses database table and column names. The two native methods accept `String` because `status` is persisted as a string. Enum binding in native queries can depend on the provider, so choose explicit parameter types.

## 3. Setting Up @DataJpaTest

`@DataJpaTest` builds a test slice for the JPA layer. Spring Boot configures entities, repositories, and related persistence components. When an embedded database is on the classpath, tests normally use the embedded database. Tests run within a transaction and roll back by default after each test method.

Common dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>test</scope>
</dependency>
~~~

Minimal test:

~~~java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerRepositoryTest {
    // repository tests
}
~~~

To use a configured database instead of the embedded database:

~~~java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class CustomerRepositoryIntegrationTest {
}
~~~

Only use this configuration when the test environment supplies a safe database with an appropriate schema and data. Never point tests at a production database. If custom configuration beans are needed, use `@Import`; `@DataJpaTest` does not load all services and components like `@SpringBootTest`.

## 4. Creating Fixtures With Predictable Results

Use fixed timestamps instead of `Instant.now()` so results do not depend on execution time. Use distinct emails to avoid violating unique constraints.

~~~java
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private TestEntityManager entityManager;

    @BeforeEach
    void setUp() {
        entityManager.persist(new Customer(
            "An", "an@example.test", CustomerStatus.ACTIVE,
            Instant.parse("2025-01-01T00:00:00Z")));

        entityManager.persist(new Customer(
            "Anna", "anna@example.test", CustomerStatus.ACTIVE,
            Instant.parse("2025-02-01T00:00:00Z")));

        entityManager.persist(new Customer(
            "Bao", "bao@example.test", CustomerStatus.INACTIVE,
            Instant.parse("2025-03-01T00:00:00Z")));

        entityManager.flush();
        entityManager.clear();
    }
}
~~~

`flush()` forces INSERTs to be sent to the database. `clear()` clears the persistence context, preventing tests from accidentally reading managed entities from memory instead of exercising the actual query behavior.

Because `@DataJpaTest` rolls back the test transaction after each method by default, data created in `setUp` does not persist across tests. If committing explicitly or running multi-transaction tests, design cleanup and isolated data per test.

## 5. Testing Derived Queries

Derived queries are generated by Spring Data from method names. Method names reference Java entity properties, not database column names.

Method:

~~~java
List<Customer>
findByStatusAndNameContainingIgnoreCaseOrderByNameAsc(
    CustomerStatus status,
    String keyword
);
~~~

The method name expresses:

- `findByStatus`: filter by status.
- `AndNameContaining`: `name` contains the search string.
- `IgnoreCase`: case-insensitive comparison as supported by the provider/database.
- `OrderByNameAsc`: sort ascending by `name`.

Test:

~~~java
@Test
void derivedQueryFiltersAndSortsByName() {
    List<Customer> result =
        customerRepository
            .findByStatusAndNameContainingIgnoreCaseOrderByNameAsc(
                CustomerStatus.ACTIVE,
                "an"
            );

    assertThat(result)
        .extracting(Customer::getName)
        .containsExactly("An", "Anna");
}
~~~

The test simultaneously verifies the status filter, case-insensitive substring match, and result order. Checking only that `result` is non-null does not confirm the query filters accurately.

Also test other cases relevant to business rules: no matching records, empty `Optional`, `First` or `Top` limits, `Between`, `Before`, `After`, `In`, `IsNull`, and tie ordering when multiple rows share values. Misspelled property names typically prevent repository initialization; test context startup catches those errors immediately.

## 6. Testing JPQL With @Query

JPQL queries entities and Java properties. In JPQL, use `Customer`, `createdAt`, and `status`—not table name `customer_record` or column name `created_at`.

Declared query:

~~~java
@Query("""
    select c
      from Customer c
     where c.status = :status
       and c.createdAt >= :from
     order by c.createdAt desc
    """)
List<Customer> findByStatusCreatedSince(
    @Param("status") CustomerStatus status,
    @Param("from") Instant from
);
~~~

Test:

~~~java
@Test
void jpqlFiltersByStatusAndCreationTime() {
    List<Customer> result =
        customerRepository.findByStatusCreatedSince(
            CustomerStatus.ACTIVE,
            Instant.parse("2025-02-01T00:00:00Z")
        );

    assertThat(result)
        .extracting(Customer::getName)
        .containsExactly("Anna");
}
~~~

The test checks named parameters, enums, and timestamp filtering. Using a fixed timestamp keeps results consistent across runs.

Common mistakes with JPQL:

- Using table or column names instead of entity/property names.
- Misspelling property names or association paths.
- Omitting `@Param` or using a parameter name differing from the query.
- Using functions or operators unsupported by the provider.
- Returning a type that mismatches the projection.
- Joining collections causing duplicate parent rows when one entity has multiple child records.

If a query joins a collection, check whether `distinct` is needed. When a query returns `Page`, verify both page content and total element count because Spring Data may run a separate count query.

## 7. Testing Native SQL

Native SQL operates directly on the database schema. Table names, column names, data types, SQL functions, and pagination syntax depend on the DBMS.

Query:

~~~sql
select *
from customer_record
where status = :status
order by created_at desc
~~~

Test:

~~~java
@Test
void nativeQueryUsesDatabaseColumnNamesAndOrdering() {
    List<Customer> result =
        customerRepository.findNativeByStatus("ACTIVE");

    assertThat(result)
        .extracting(Customer::getName)
        .containsExactly("Anna", "An");
}
~~~

The test verifies the native query uses the right table/column names and returns the expected order. Because `status` is mapped with `EnumType.STRING`, the `"ACTIVE"` argument matches persisted data.

Points to watch for native queries:

- `SELECT *` is convenient when results match the entity mapping; if joining multiple tables with overlapping column names, select columns and aliases explicitly.
- Entity-returning queries must provide every column required by the mapping.
- Use bind parameters; never concatenate user input into SQL strings.
- Table and column names must match the real schema, including database case-sensitivity rules.
- Date/time functions, JSON, operators, type casts, and pagination syntax vary across PostgreSQL, MySQL, Oracle, and SQL Server.
- Table names, column names, or sort directions cannot be bound as ordinary parameter values; if dynamic SQL is needed, whitelist valid choices.

### 7.1. Paginated Native Queries

For native queries returning `Page`, declare an explicit `countQuery` when Spring Data cannot safely derive a count query:

~~~java
@Query(
    value = """
        select *
          from customer_record
         where status = :status
         order by created_at desc
        """,
    countQuery = """
        select count(*)
          from customer_record
         where status = :status
        """,
    nativeQuery = true
)
Page<Customer> findNativePageByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

Test both page content and total count:

~~~java
@Test
void nativeQueryReturnsCorrectPageAndTotal() {
    Page<Customer> page =
        customerRepository.findNativePageByStatus(
            "ACTIVE",
            PageRequest.of(0, 1)
        );

    assertThat(page.getContent())
        .extracting(Customer::getName)
        .containsExactly("Anna");

    assertThat(page.getTotalElements()).isEqualTo(2);
    assertThat(page.getTotalPages()).isEqualTo(2);
}
~~~

Because the query sorts descending by `created_at`, `Anna` precedes `An`. The test also verifies the count query; if the count query has the wrong filter, content can look right while `totalElements` is wrong.

## 8. Testing Specifications

Specifications use the Criteria API to build dynamic predicates. The repository must extend `JpaSpecificationExecutor`.

Create composable predicates:

~~~java
import java.util.Locale;
import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecifications {

    private CustomerSpecifications() {
    }

    public static Specification<Customer> hasStatus(
            CustomerStatus status) {
        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }

    public static Specification<Customer> nameContains(
            String keyword) {
        return (root, query, cb) -> {
            if (keyword == null || keyword.isBlank()) {
                return cb.conjunction();
            }

            String pattern =
                "%" + keyword.toLowerCase(Locale.ROOT) + "%";

            return cb.like(
                cb.lower(root.<String>get("name")),
                pattern
            );
        };
    }
}
~~~

`cb.conjunction()` returns an always-true predicate, useful when an optional filter is omitted. `nameContains` uses lowercase matching for case-insensitive search. If search strings can contain `%` or `_`, decide clearly how to escape them and write tests for that behavior.

Combining two Specifications:

~~~java
@Test
void specificationCombinesStatusAndNameFilters() {
    Specification<Customer> spec =
        CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE)
            .and(CustomerSpecifications.nameContains("an"));

    List<Customer> result =
        customerRepository.findAll(spec, Sort.by("name").ascending());

    assertThat(result)
        .extracting(Customer::getName)
        .containsExactly("An", "Anna");
}
~~~

The test confirms predicates combine with AND and results are sorted by the entity property.

### 8.1. Optional Filters

In search APIs, each filter may be supplied or left blank. Test meaningful combinations:

~~~java
@Test
void specificationIgnoresMissingOptionalFilters() {
    Specification<Customer> spec =
        CustomerSpecifications.hasStatus(null)
            .and(CustomerSpecifications.nameContains(""));

    List<Customer> result = customerRepository.findAll(spec);

    assertThat(result).hasSize(3);
}
~~~

Beyond the no-filter case, test each filter individually, multiple filters combined, and the empty-result case. This catches predicates where null or blank strings inadvertently build wrong conditions.

### 8.2. Pagination and Counts With Specifications

~~~java
@Test
void specificationSupportsPaginationAndTotalCount() {
    Specification<Customer> spec =
        CustomerSpecifications.hasStatus(CustomerStatus.ACTIVE);

    Page<Customer> page = customerRepository.findAll(
        spec,
        PageRequest.of(0, 1, Sort.by("name").ascending())
    );

    assertThat(page.getContent())
        .extracting(Customer::getName)
        .containsExactly("An");

    assertThat(page.getTotalElements()).isEqualTo(2);
    assertThat(page.getTotalPages()).isEqualTo(2);
}
~~~

When a Specification joins a collection, one entity can appear multiple times in SQL results. `distinct` may be required and the count query must not double-count. Combining a collection fetch join with pagination can force Hibernate to paginate in memory or log warnings; design the query appropriately instead of fetching every association indiscriminately.

## 9. Testing Projections and Aggregate Queries

Not every query needs to return full entities. When a repository returns an interface projection, DTO, or scalar, tests must inspect each field precisely.

Interface projection:

~~~java
public interface CustomerNameView {
    Long getId();
    String getName();
}
~~~

JPQL projection:

~~~java
@Query("""
    select c.id as id, c.name as name
      from Customer c
     where c.status = :status
     order by c.name
    """)
List<CustomerNameView> findNamesByStatus(
    @Param("status") CustomerStatus status
);
~~~

Test:

~~~java
@Test
void jpqlProjectionMapsSelectedFields() {
    List<CustomerNameView> result =
        customerRepository.findNamesByStatus(CustomerStatus.ACTIVE);

    assertThat(result)
        .extracting(CustomerNameView::getName)
        .containsExactly("An", "Anna");

    assertThat(result)
        .extracting(CustomerNameView::getId)
        .doesNotContainNull();
}
~~~

Aliases in JPQL must match the projection's getter names. For DTO constructor expressions, parameter order and types must match the constructor. Projection tests catch alias mismatches, return type bugs, and missing columns that row-count-only checks would miss.

## 10. Transactions and Test Data

Guidelines for reliable repository tests:

- Use `@DataJpaTest` for tests focused on entity mappings and repositories.
- Use `TestEntityManager` or repositories to create fixtures; flush before executing queries under test.
- Clear the persistence context to ensure queries reload data from the database.
- Use fixed timestamps, reference IDs, and constants for repeatable tests.
- Do not rely on return order if the query lacks `ORDER BY`.
- Use AssertJ or JUnit assertions to check values, order, and total element counts.
- Keep every test independent; avoid test execution order dependencies.
- Never use real production data in tests.

Slice tests run inside transactions and roll back after tests by default. If testing commit-dependent behavior such as `AFTER_COMMIT` transaction events, manage transactions explicitly with `TestTransaction` or appropriate test settings. If a test opens multiple transactions, inspect data via `EntityManager` or a fresh transaction after commit.

Do not call `entityManager.clear()` before flushing data that needs to be saved, as unflushed changes can be detached and lost. The usual sequence is persist/save, flush, clear, and then invoke the query.

## 11. When Is a Real Database Needed?

H2 or an embedded database keeps tests fast, yet does not guarantee identical behavior to the production database.

Run integration tests against the same DBMS when queries use:

- Native SQL or database-specific functions.
- JSON, arrays, full-text search, CTEs, or window functions.
- Configuration-dependent collations, case sensitivity, or timezones.
- Specialized data types and casts.
- Locking, isolation, deadlocks, or pagination semantics.
- Generated columns, sequences, identities, and complex constraints.

Testcontainers can provision real databases for integration tests. When using Testcontainers, ensure schemas are built with the same migrations as production; avoid relying solely on Hibernate auto-DDL if the project uses Flyway or Liquibase in production.

## 12. Common Pitfalls

1. Using column names in JPQL. JPQL uses entity and Java property names; native SQL uses table and column names.
2. Not flushing fixtures. Queries may run before test data reaches the database.
3. Not clearing the persistence context when verifying database state. In-memory entities can distort test conclusions.
4. Omitting `ORDER BY` yet asserting order. SQL does not guarantee ordering unless explicitly requested.
5. Asserting only result counts. Two returned items could be the wrong two records; assert IDs or business properties.
6. Neglecting count queries. A `Page` can have the right content while `totalElements` or `totalPages` is wrong.
7. Trusting H2 to prove production native SQL works. Dialects and data types can differ.
8. Mixing Specifications with collection fetch joins and pagination without checking counts. Results can duplicate, miscount, or paginate inefficiently.
9. Creating duplicate unique keys in test data. Fixtures need distinct emails or reference keys per record.
10. Testing only that the repository was called. Repository tests must run real queries and verify database results.

## 13. Checklist Before Completing Repository Tests

- Confirm derived queries reflect exact property names and business filters.
- Check JPQL uses valid entity names, properties, parameters, and return types.
- Check native SQL against the real schema, aliases, parameter types, and database dialect.
- Test individual Specifications, combined Specifications, empty filters, sorting, and pagination.
- Test projections, count queries, and zero-match cases.
- Flush and clear when confirming queries actually execute against the database.
- Use deterministic fixtures independent of test execution order.
- Run native queries, locking, and engine-specific features on a production-matching database.
- Confirm test transaction rollback or commit matches the behavior under test.

A repository test proves its worth when it confirms data returned from the database matches business requirements. Test each query style according to its syntax and dependencies, alongside ordering, pagination, projections, and edge cases the application actually exercises.