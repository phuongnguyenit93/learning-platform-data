# Reproducing N+1 and Comparing Mitigation Approaches in Spring Data JPA

N+1 is a performance issue that occurs when one query fetches a list of parent entities and the application then issues an additional query per entity to load related data. With N parent entities, the total number of queries is typically 1 + N. Data may still be correct and functional tests still pass, but response times grow rapidly as record counts increase or when the database sits across a network.

This lesson creates a Spring Data JPA example that reproduces N+1 using Hibernate Statistics, then compares mitigation approaches: JPQL `JOIN FETCH`, `@EntityGraph`, DTO projections, and batch fetching. Each approach has pros and cons; choose based on the data you need to read, pagination needs, and result-set size. Examples use Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate 6, JUnit 5, AssertJ, and H2.

## 1. What Is N+1?

Suppose a system has three departments, each with a list of employees. The application needs to display each department's name and employee count.

A commonly seen approach:

```java
List<Department> departments = departmentRepository.findAll();

for (Department department : departments) {
    System.out.println(
        department.getName() + ": " + department.getEmployees().size()
    );
}
```

The first query loads the list of departments. The `employees` relationship is declared `LAZY`, so calling `getEmployees()` causes Hibernate to load the collection for each department if that collection is not yet initialized.

Conceptually, the SQL looks like:

```sql
-- Query 1: fetch departments
select d.id, d.name
from departments d;

-- Query 2: employees of the first department
select e.id, e.name, e.department_id
from employees e
where e.department_id = ?;

-- Query 3: employees of the second department
select e.id, e.name, e.department_id
from employees e
where e.department_id = ?;

-- Query 4: employees of the third department
select e.id, e.name, e.department_id
from employees e
where e.department_id = ?;
```

With three departments, there is one parent query and three child queries: four queries total. With 100 departments, there can be 101 queries. That is N+1.

N+1 is not limited to `@OneToMany`. A `@ManyToOne(fetch = FetchType.LAZY)` or `@OneToOne(fetch = FetchType.LAZY)` relationship can also trigger an extra query per entity when the application accesses the association. `EAGER` relationships do not guarantee a single SQL statement either; providers can still load associations via secondary queries.

## 2. Creating the Entity Model to Reproduce N+1

Use a one-to-many relationship where one department has many employees. `Department` is the inverse side with `mappedBy`; `Employee.department` is the owning side holding the foreign key.

**Department.java**

```java
package com.example.department;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(
        mappedBy = "department",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<Employee> employees = new ArrayList<>();

    protected Department() {
    }

    public Department(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<Employee> getEmployees() {
        return employees;
    }

    public void addEmployee(Employee employee) {
        employees.add(employee);
        employee.setDepartment(this);
    }
}
```

**Employee.java**

```java
package com.example.department;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

    protected Employee() {
    }

    public Employee(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Department getDepartment() {
        return department;
    }

    void setDepartment(Department department) {
        this.department = department;
    }
}
```

Two important points:

- `mappedBy = "department"` points to the Java property in `Employee`, not the column name `department_id`.
- When adding an employee, the `addEmployee()` helper updates both the inverse collection and the owning side. Adding only to `Department.employees` without setting `Employee.department` may fail to persist the foreign key as expected.

## 3. Repository with Query Variants

Start with a normal method to fetch the department list, then declare variants that load associations.

**DepartmentRepository.java**

```java
package com.example.department;

import com.example.department.dto.DepartmentSummary;
import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DepartmentRepository
        extends JpaRepository<Department, Long> {

    List<Department> findAllByOrderByNameAsc();

    @Query("""
        select distinct d
        from Department d
        left join fetch d.employees
        order by d.name
        """)
    List<Department> findAllWithEmployees();

    @EntityGraph(attributePaths = "employees")
    @Query("""
        select d
        from Department d
        order by d.name
        """)
    List<Department> findAllWithEmployeesGraph();

    @Query("""
        select distinct d
        from Department d
        left join fetch d.employees
        where d.id in :ids
        """)
    List<Department> findWithEmployeesByIdIn(@Param("ids") Collection<Long> ids);

    @Query("""
        select new com.example.department.dto.DepartmentSummary(
            d.id, d.name, count(e)
        )
        from Department d
        left join d.employees e
        group by d.id, d.name
        order by d.name
        """)
    List<DepartmentSummary> findDepartmentSummaries();

    @Query(
        value = "select d from Department d order by d.name",
        countQuery = "select count(d) from Department d"
    )
    Page<Department> findDepartmentPage(Pageable pageable);
}
```

Each method targets a different scenario:

- `findAllByOrderByNameAsc()`: baseline to observe N+1.
- `findAllWithEmployees()`: uses a fetch join to load the collection in the same query.
- `findAllWithEmployeesGraph()`: declares a fetch plan using `EntityGraph`.
- `findWithEmployeesByIdIn(...)`: second query by ID list, useful for a two-step pagination strategy.
- `findDepartmentSummaries()`: retrieves only the data needed for a summary screen.
- `findDepartmentPage(...)`: paginates parent entities without fetching the collection.

## 4. Reproducing and Measuring N+1 with Hibernate Statistics

Do not just eyeball logs and guess. Hibernate provides `Statistics` to count prepared statements. Enable statistics in tests:

**application-test.yml**

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

The integration test creates three departments, each with two employees. After flushing and clearing, the test clears statistics, queries the parent list, and accesses the collection.

**DepartmentNPlusOneTest.java**

```java
package com.example.department;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest(properties = {
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
class DepartmentNPlusOneTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private DepartmentRepository repository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @BeforeEach
    void setUp() {
        Department engineering = new Department("Engineering");
        engineering.addEmployee(new Employee("An"));
        engineering.addEmployee(new Employee("Binh"));

        Department finance = new Department("Finance");
        finance.addEmployee(new Employee("Chi"));
        finance.addEmployee(new Employee("Dung"));

        Department sales = new Department("Sales");
        sales.addEmployee(new Employee("Giang"));
        sales.addEmployee(new Employee("Hoa"));

        entityManager.persist(engineering);
        entityManager.persist(finance);
        entityManager.persist(sales);
        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void demonstratesOnePlusNSelects() {
        Statistics statistics = entityManagerFactory
            .unwrap(SessionFactory.class)
            .getStatistics();

        statistics.clear();

        var departments = repository.findAllByOrderByNameAsc();

        // Only the parent table has been queried at this point.
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);

        int employeeCount = departments.stream()
            .mapToInt(department -> department.getEmployees().size())
            .sum();

        assertThat(employeeCount).isEqualTo(6);

        // 1 query to fetch departments + 3 queries to load the 3 collections.
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(4L);
    }
}
```

The test calls `flush()` to write fixture data to the database and `clear()` to evict entities from the persistence context before measuring. Without `clear()`, managed entities or collections might already be initialized, making the measured query count artificially low.

Expected test results:

- After fetching the department list: 1 prepared statement.
- After iterating the three `employees` collections: 4 prepared statements total.
- Total employees counted: 6.

The prepared statement count provides quantitative evidence for this test case. When listeners, filters, or other queries are active, call `statistics.clear()` immediately before the section being measured and avoid running tests sharing `SessionFactory` statistics concurrently.

## 5. Approach 1 — JPQL JOIN FETCH

A fetch join instructs JPA to load the association in the same query as the root entity:

```java
@Query("""
    select distinct d
    from Department d
    left join fetch d.employees
    order by d.name
    """)
List<Department> findAllWithEmployees();
```

- `left join fetch` retains departments even if they have no employees yet.
- `join fetch` (inner join) returns only departments with matching associations.
- `fetch` directs the provider to populate the association in the same query rather than waiting for lazy access.
- `distinct` expresses deduplicated root entities at the JPQL level.

When fetching a collection, SQL can still return multiple rows per department—one row per employee. Hibernate assembles those rows into the entity graph and deduplicates the root entities in the result. Thus, the SQL row count and Java entity count are not necessarily equal.

Testing the fetch join variant:

```java
@Test
void fetchJoinLoadsDepartmentsAndEmployeesInOneStatement() {
    Statistics statistics = entityManagerFactory
        .unwrap(SessionFactory.class)
        .getStatistics();

    statistics.clear();

    var departments = repository.findAllWithEmployees();

    int employeeCount = departments.stream()
        .mapToInt(department -> department.getEmployees().size())
        .sum();

    assertThat(departments).hasSize(3);
    assertThat(employeeCount).isEqualTo(6);
    assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);
}
```

This approach fits when you need entities and associations for a clearly scoped screen or use case. Avoid fetch-joining multiple large collections in a single statement because it can produce a Cartesian product, inflating intermediate rows; with certain bag-mapped collections, Hibernate can also throw `MultipleBagFetchException`.

### Limitations When Combining with Pagination

Do not paginate a collection fetch-join query directly:

```java
@Query("""
    select distinct d
    from Department d
    left join fetch d.employees
    order by d.name
    """)
Page<Department> findAllWithEmployees(Pageable pageable);
```

The database paginates over joined rows, while a single department may span multiple rows. Hibernate may have to apply pagination in memory and log a warning such as `HHH90003004`; this can load excessive data.

When a page is needed, paginate the parent entities first and then load associations for the IDs in that page, or use a DTO projection. Do not trade away memory by fetching entire collections just to avoid one extra query.

## 6. Approach 2 — @EntityGraph

`EntityGraph` declares associations to load for a query without writing fetch joins in JPQL:

```java
@EntityGraph(attributePaths = "employees")
@Query("select d from Department d order by d.name")
List<Department> findAllWithEmployeesGraph();
```

`EntityGraph` is useful when you want readable queries or reusable fetch plans across multiple methods. You can declare a named graph on the entity or use `attributePaths` to build an ad-hoc graph directly on a repository method.

`EntityGraph` defines a fetch plan the provider must satisfy under JPA semantics. The provider chooses the concrete SQL strategy; Hibernate typically uses a join for simple cases, but inspect the actual SQL and statement counts. Do not assume the annotation alone guarantees eliminating N+1.

Example test:

```java
@Test
void entityGraphLoadsTheRequestedAssociation() {
    Statistics statistics = entityManagerFactory
        .unwrap(SessionFactory.class)
        .getStatistics();

    statistics.clear();

    var departments = repository.findAllWithEmployeesGraph();

    int employeeCount = departments.stream()
        .mapToInt(department -> department.getEmployees().size())
        .sum();

    assertThat(employeeCount).isEqualTo(6);
    assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);
}
```

Asserting one statement reflects the expected behavior for Hibernate with the simple association in this example. If you change providers, mappings, or deeper graphs, re-verify the SQL rather than keeping the assumption.

`EntityGraph` fits when fetch plans vary by use case. For instance, a list screen only needs `employees`, while another screen also needs `manager`. You can define separate graphs per repository method instead of switching the association globally to `EAGER`.

## 7. Approach 3 — DTO Projection

If a screen only needs department names and employee counts, there is no need to load entities and entire collections. A DTO projection selects only the required columns and computes the aggregation in the database.

DTO:

**DepartmentSummary.java**

```java
package com.example.department.dto;

public record DepartmentSummary(
    Long id,
    String name,
    Long employeeCount
) {
}
```

Repository using a JPQL constructor expression:

```java
@Query("""
    select new com.example.department.dto.DepartmentSummary(
        d.id, d.name, count(e)
    )
    from Department d
    left join d.employees e
    group by d.id, d.name
    order by d.name
    """)
List<DepartmentSummary> findDepartmentSummaries();
```

Test:

```java
@Test
void projectionReturnsOnlyTheSummaryFields() {
    Statistics statistics = entityManagerFactory
        .unwrap(SessionFactory.class)
        .getStatistics();

    statistics.clear();

    var summaries = repository.findDepartmentSummaries();

    assertThat(summaries).hasSize(3);
    assertThat(summaries)
        .extracting(DepartmentSummary::employeeCount)
        .containsExactly(2L, 2L, 2L);
    assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);
}
```

DTO projections are often the best choice for read models, reports, list views, and API responses needing only a subset of fields. They avoid loading unnecessary entities and prevent entity serialization from triggering lazy loading. On the flip side, DTOs are not managed entities; do not treat a DTO projection like an aggregate inside the persistence context for updates.

For screens needing employee details, you can use a flat DTO projection returning one row per department/employee pair and group them into a response in the service. Consider duplicated department column data and how departments without employees are represented.

## 8. Approach 4 — Batch Fetching

Batch fetching mitigates N+1 by combining multiple uninitialized associations into a single query with an `IN` clause. Instead of one `SELECT` per department, Hibernate loads collections in batches.

Set batch size on the collection:

```java
import org.hibernate.annotations.BatchSize;

@OneToMany(
    mappedBy = "department",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
@BatchSize(size = 20)
private List<Employee> employees = new ArrayList<>();
```

Or configure a global default:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 20
```

With N departments and batch size B, the number of collection queries is approximately `ceil(N / B)`; total statements are roughly `1 + ceil(N / B)` for a collection association. This is an estimate; the actual number depends on uninitialized collections, dialect, bind parameter limits, persistence context state, and the provider.

For example, with 45 departments and batch size 20, instead of 46 queries, there is typically one parent query and roughly three collection queries. Batch fetching is useful when you cannot or do not want to join the full collection, or when entities are loaded through varied paths before their associations are accessed.

Hibernate also provides `@Fetch(FetchMode.SUBSELECT)` for certain collections. When one collection is initialized, the provider can load the same collection across all previously queried parent entities using a subselect. This is a Hibernate-specific feature; inspect the SQL and the volume of data loaded into the persistence context.

Batch fetching reduces round trips, but still loads more columns/entities than a DTO projection. Nor does it guarantee a single query like a simple fetch join.

## 9. Comparing the Approaches

| Approach | How It Reduces N+1 | Pros | Limitations / Best Fit |
|---|---|---|---|
| JPQL `JOIN FETCH` | Loads associations via join in one query | Explicit, clear SQL, good for small graphs | SQL row duplication; use caution with pagination and multiple collections |
| `@EntityGraph` | Declares fetch plan per use case | Minimal JPQL changes, reusable graphs | Provider chooses SQL; must measure in practice |
| DTO projection | Queries exact columns and aggregations needed | Minimal payload, no lazy loading, ideal for read APIs | Does not return managed aggregates for updates |
| Batch fetching | Groups lazy loads into batches | Minimal query changes, fewer round trips | Still issues secondary queries and loads entities; Hibernate-specific |
| Two-step loading | Pages roots first, then fetches associations by ID | Preserves accurate pagination and bounds dataset | Typically requires two queries and restoring page order |

No single mitigation fits every query. Start from what data the use case needs:

- Need an aggregate with one small collection: fetch join or `EntityGraph`.
- Need a list with a few fields and counts: DTO projection.
- Need to preserve lazy loading while reducing round trips across collections: batch fetching.
- Need to paginate parents and display associations: two-step loading or DTO projection.

## 10. Safe Pagination with Collections

A common pattern is fetching a page of parent IDs/entities first, then fetching the collection in a second query.

Service:

```java
@Service
public class DepartmentQueryService {

    private final DepartmentRepository repository;

    public DepartmentQueryService(DepartmentRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Department> findPageWithEmployees(Pageable pageable) {
        Page<Department> page =
            repository.findDepartmentPage(pageable);

        List<Long> ids = page.getContent().stream()
            .map(Department::getId)
            .toList();

        if (ids.isEmpty()) {
            return List.of();
        }

        List<Department> loaded =
            repository.findWithEmployeesByIdIn(ids);

        Map<Long, Department> byId = loaded.stream()
            .collect(Collectors.toMap(Department::getId, Function.identity()));

        // An IN query does not guarantee preserving the input ID order; restore the page order.
        return ids.stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .toList();
    }
}
```

The service requires these imports:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
```

The two queries have distinct roles: the first applies `LIMIT`/`OFFSET` and count to determine the page; the second loads collections for only those selected IDs. Both execute inside a read-only transaction so entities remain managed and associations can be accessed within transaction boundaries.

For large ID sets, watch database bind parameter limits. Small pages rarely encounter issues. If thousands of IDs must be loaded, chunk into batches or switch to an appropriate DTO query.

## 11. N+1 Can Be Masked by Transactions and Open Session in View

`@Transactional(readOnly = true)` sets up a read transaction and can optimize flush behavior, yet by itself does not eliminate N+1. If the service accesses a lazy collection inside a loop, extra queries still run.

Open Session in View (OSIV) keeps the persistence context open through response rendering, allowing lazy loading to keep working after the service returns. That sometimes masks API endpoints triggering queries outside the service. Do not rely on OSIV to work around N+1; define fetch plans per use case or return DTOs constructed inside the transaction.

Do not switch every association to `FetchType.EAGER` to cure N+1. `EAGER` can load unneeded data, still spawn extra queries, and grow the fetched graph uncontrollably. Choose fetch plans per query.

## 12. Detecting N+1 in Logs and Production

You can enable SQL logging in local/test profiles:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Hibernate 6 uses the `org.hibernate.orm.jdbc.bind` category to log bind parameters. Bind logging can expose sensitive data, so avoid enabling it casually in production or writing personal data to logs.

Signs to look for:

- One `SELECT` fetching a list of parent entities.
- Followed by repeating identical `SELECT` patterns filtered by foreign key per entity.
- `SELECT` counts scaling roughly linearly with parent entity count.
- DB/network time dominating endpoint latency.

In production, combine APM/tracing, slow query logs, and database metrics. Hibernate Statistics is helpful in tests or controlled observability environments; do not turn on broad bind logging merely to hunt for N+1.

## 13. Common Mistakes When Fixing N+1

| Mistake | Consequence | Fix |
|---|---|---|
| Adding collection fetch join to a `Pageable` query | Pagination may happen in memory or yield inefficient pages | Page roots first, then fetch by ID or use a DTO |
| Fetching multiple collections in one query | Cartesian product, duplicated rows, or bag fetch exception | Split queries, batch fetch, or use projections |
| Switching all associations to `EAGER` | Over-fetching and still prone to secondary queries | Keep `LAZY` as appropriate; set fetch plans per use case |
| Checking only entity count without counting SQL | Functional tests pass while N+1 persists | Use Hibernate Statistics or an SQL counter |
| Measuring statistics without clearing persistence context | Collections already loaded, yielding artificially low query counts | Flush, clear, then clear statistics before the measured block |
| Returning entities to the API and serializing associations | Serialization triggers lazy loads or fails outside transactions | Map to DTOs inside the service |
| Setting an overly large batch size | Fetches more associations and bind parameters than needed | Measure real data; size batches per use case/database |

## 14. Checklist for Resolving N+1 in a Project

1. Identify the slow endpoint or use case and the parent entity queried.
2. Enable SQL logging in a safe environment or use APM to spot repeated `SELECT` patterns.
3. Identify which associations are accessed in loops or inside mappers/serializers.
4. Write an integration test with multiple parent entities and measure statement counts.
5. Choose fetch join, `EntityGraph`, DTO projection, batch fetching, or two-step pagination based on required data.
6. Re-run tests and compare statement count, row count, latency, and payload size.
7. Check pagination, multiple collections, transaction boundaries, and other associations to avoid turning N+1 into one massive query.
8. Keep regression tests so future query edits do not accidentally reintroduce N+1.

## 15. Testing with Testcontainers and Regression Tests

H2 is suitable for fast test runs, yet it does not fully replicate the dialect, data types, query plans, and limits of a production database. If your application runs PostgreSQL, have at least one integration test using real PostgreSQL via Testcontainers to verify JPQL, fetch plans, and statement counts on the actual DBMS.

Add test dependencies (versions can be managed by Spring Boot dependency management or the Testcontainers BOM):

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Example test slice configured with a PostgreSQL container:

**DepartmentPostgresIT.java**

```java
package com.example.department;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers(disabledWithoutDocker = true)
@DataJpaTest(properties = {
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class DepartmentPostgresIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name",
            postgres::getDriverClassName);
    }

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private DepartmentRepository repository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void fetchJoinKeepsCollectionLoadingToOneStatementOnPostgres() {
        Department department = new Department("Engineering");
        department.addEmployee(new Employee("An"));
        department.addEmployee(new Employee("Binh"));
        entityManager.persistAndFlush(department);
        entityManager.clear();

        Statistics statistics = entityManagerFactory
            .unwrap(SessionFactory.class)
            .getStatistics();
        statistics.clear();

        var result = repository.findAllWithEmployees();
        int employeeCount = result.stream()
            .mapToInt(item -> item.getEmployees().size())
            .sum();

        assertThat(result).hasSize(1);
        assertThat(employeeCount).isEqualTo(2);
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);
    }
}
```

Testcontainers requires Docker or a compatible container runtime. `disabledWithoutDocker = true` lets JUnit skip the test when Docker is unavailable; CI should configure Docker so this test actually runs. With Spring Boot, `@DynamicPropertySource` registers the container URL and credentials before the test context builds the `DataSource`. `replace = NONE` prevents the test slice from replacing the PostgreSQL `DataSource` with an embedded database.

Regression tests should verify observable behavior rather than just checking annotations:

- Baseline lazy loading with three departments must show one parent query and three collection queries in the simple fixture.
- `JOIN FETCH` and DTO projection must keep the statement count at one in the unpaginated example.
- `EntityGraph` must be measured against the real Hibernate/provider; if the goal is one statement, keep the assertion to catch fetch-plan regressions.
- Batch fetching should verify the query count stays bounded by the batch size, e.g., around `1 + ceil(N / B)`, rather than assuming a single query.
- Two-step tests must verify the page contains the right number of departments, collections are loaded, and result order matches the original page.
- Add edge cases for departments with no employees, empty pages, last pages, and datasets large enough to span multiple batches.

When counting SQL statements, flush and clear fixtures before resetting statistics; reset immediately before the query block under test. Do not run tests in parallel if they share `SessionFactory` Hibernate Statistics, because the counters are shared state. Separate fast H2 tests from Testcontainers tests using profiles or tags to retain fast local feedback during development.

## 16. Checklist for Resolving N+1 in a Project

1. Identify the slow endpoint or use case and the parent entity queried.
2. Enable SQL logging in a safe environment or use APM to spot repeated `SELECT` patterns.
3. Identify which associations are accessed in loops or inside mappers/serializers.
4. Write an integration test with multiple parent entities and measure statement counts.
5. Choose fetch join, `EntityGraph`, DTO projection, batch fetching, or two-step pagination based on required data.
6. Re-run tests and compare statement count, row count, latency, and payload size.
7. Check pagination, multiple collections, transaction boundaries, and other associations to avoid turning N+1 into one massive query.
8. Keep regression tests on a production-compatible database so future query edits do not accidentally reintroduce N+1.

N+1 is a database access frequency issue, not merely a mapping annotation issue. Effective remediation starts with reproducing it with metrics, clarifying what data the use case actually needs, and selecting an appropriate fetch plan. Fewer SQL statements do not automatically mean faster execution; compare statement count, returned rows, payload size, and pagination compatibility before finalizing a solution.