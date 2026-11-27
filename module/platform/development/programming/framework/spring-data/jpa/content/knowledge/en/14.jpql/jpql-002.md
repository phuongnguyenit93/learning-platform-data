# Declaring Queries with @Query

## Objectives

Spring Data JPA allows declaring queries directly on repository methods using the `@Query` annotation. This approach is useful when a query has multiple conditions, JOINs, projections, pagination, or when a derived query method name becomes long and hard to read.

By default, Spring Data JPA's `@Query` uses JPQL (Jakarta Persistence Query Language). JPQL queries entities and Java attributes; the provider translates the JPQL statement into SQL compatible with the database. When you need SQL targeting specific table/column names, you can set `nativeQuery = true`.

After this lesson, you will be able to:

- Write JPQL using `@Query` and distinguish JPQL from SQL.
- Pass parameters safely by name or position.
- Use JOINs, conditions, sorting, and expressions in JPQL.
- Return entities, `Optional`, DTOs, or interface projections.
- Paginate with `Page` and declare `countQuery`.
- Execute UPDATE/DELETE statements with `@Modifying`.
- Use native SQL appropriately and test queries.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. What is @Query?

With Spring Data JPA, queries can be defined right on repository methods:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("select e from Employee e where e.active = true")
    List<Employee> findAllActive();
}
```

Spring Data reads the annotation when creating the repository proxy and executes the query when the method is called. In the example above:

- `Employee` is the entity name.
- `e` is the entity alias.
- `e.active` is a Java attribute of the entity.
- `findAllActive()` returns the list of entities matching the condition.

JPQL uses entity names and Java attributes, not SQL table and column names. If an entity is declared with `@Entity(name = "StaffMember")`, JPQL references `StaffMember`; the table name in `@Table` does not determine the entity name in JPQL.

### 1.1. When Should You Use @Query?

Use derived queries for simple conditions where the method name stays clear, such as `findByEmailIgnoreCase`. Use `@Query` when:

- You need to JOIN multiple entities or combine complex conditions.
- You need precise control over the JPQL.
- You need projections or aggregate calculations.
- You need to declare UPDATE/DELETE operations.
- The derived query name becomes too long or hard to maintain.
- You need native SQL for database-specific features.

There is no need to write `@Query` for every method. Derived queries are often more concise for simple lookups.

## 2. Declaring Basic JPQL

Suppose we have an `Employee` entity:

```java
package com.example.demo.employee;

import jakarta.persistence.*;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String fullName;

    @Column(nullable = false, unique = true, length = 320)
    private String email;

    @Column(nullable = false)
    private boolean active;

    protected Employee() {
    }

    public Employee(String fullName, String email, boolean active) {
        this.fullName = fullName;
        this.email = email;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Repository:

```java
package com.example.demo.employee;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.active = true
           order by e.fullName asc
           """)
    List<Employee> findActiveEmployees();

    @Query("""
           select e
           from Employee e
           where lower(e.email) = lower(:email)
           """)
    Optional<Employee> findByEmailIgnoreCase(
            @Param("email") String email
    );
}
```

The example uses Java text blocks to write multi-line JPQL. JPQL can be written as a single-line or multi-line string; text blocks make queries easier to read.

### 2.1. SELECT and Aliases

Basic structure:

```text
select <alias>
from <EntityName> <alias>
where <condition>
order by <property>
```

Aliases help reference entities and attributes. For example:

```sql
select e
from Employee e
where e.active = true
```

This is JPQL, not SQL. Do not write `select * from employees` in a regular JPQL query. JPQL selects entities or expressions, while entity and field names come from the Java mapping.

### 2.2. Conditions and Operators

JPQL supports familiar operators:

- Comparison: `=`, `<>`, `>`, `>=`, `<`, `<=`.
- Logical: `AND`, `OR`, `NOT`.
- Null checks: `IS NULL`, `IS NOT NULL`.
- Sets: `IN`, `NOT IN`.
- Ranges: `BETWEEN ... AND ...`.
- Strings: `LIKE`, `NOT LIKE`.
- Existence: `EXISTS`, `NOT EXISTS`.

Example:

```java
@Query("""
       select e
       from Employee e
       where e.active = true
         and e.id between :fromId and :toId
       """)
List<Employee> findActiveBetweenIds(
        @Param("fromId") Long fromId,
        @Param("toId") Long toId
);
```

Conditions can be grouped with parentheses to clarify precedence:

```java
@Query("""
       select e
       from Employee e
       where e.active = true
         and (lower(e.fullName) like lower(:pattern)
              or lower(e.email) like lower(:pattern))
       """)
List<Employee> searchActive(
        @Param("pattern") String pattern
);
```

The value passed to `pattern` must contain wildcard characters if substring matching is desired, such as `%an%`. Never concatenate user input directly into the JPQL string.

## 3. Passing Parameters to a Query

Spring Data JPA supports named parameters and positional parameters.

### 3.1. Named Parameters

Prefix the parameter name with a colon:

```java
@Query("""
       select e
       from Employee e
       where e.email = :email
         and e.active = :active
       """)
List<Employee> findByEmailAndActive(
        @Param("email") String email,
        @Param("active") boolean active
);
```

Advantages of named parameters:

- Parameter names clearly convey intent.
- Less chance of mixing up parameter order when a query has many parameters.
- Easier to read and maintain when adding conditions.

Use `@Param` to explicitly bind the name in the query to the Java parameter. Some configurations can infer parameter names from compiler metadata, but `@Param` keeps the code explicit and less configuration-dependent.

### 3.2. Positional Parameters

Positional parameters use `?1`, `?2` notation:

```java
@Query("""
       select e
       from Employee e
       where e.email = ?1
         and e.active = ?2
       """)
List<Employee> findByEmailAndStatus(
        String email,
        boolean active
);
```

Position numbering starts at 1. If you reorder parameters in the method or query, you must update them to match. With many parameters, named parameters are usually clearer.

Do not mix named parameters and positional parameters in the same query.

### 3.3. Passing a Collection to IN

You can pass a collection into an `IN` condition:

```java
@Query("""
       select e
       from Employee e
       where e.id in :ids
       """)
List<Employee> findAllByIds(@Param("ids") Collection<Long> ids);
```

Decide on the behavior for an empty collection explicitly before calling the repository. How databases/providers handle an `IN` expression with an empty list can vary; in the service layer, you can return an empty list immediately when there are no IDs to look up.

### 3.4. String Searching and LIKE

Example of searching a name by substring:

```java
@Query("""
       select e
       from Employee e
       where lower(e.fullName) like lower(concat('%', :keyword, '%'))
       """)
List<Employee> searchByName(@Param("keyword") String keyword);
```

JPQL supports `CONCAT`. You can also use `LOWER`, `UPPER`, `LENGTH`, `TRIM`, and other standard functions. Some databases/providers support additional proprietary functions; if using a vendor-specific function, verify compatibility before switching databases.

When you need to search literally for strings containing wildcard characters `%` or `_`, escape them using the appropriate `LIKE` escape syntax for the database. Never assume user input is always plain text.

## 4. JOIN and Querying Entity Relationships

JPQL supports JOINs over associations declared in entities.

Suppose `Employee` has a many-to-one relationship to `Department`:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

Querying employees by department name:

```java
@Query("""
       select e
       from Employee e
       join e.department d
       where lower(d.name) = lower(:departmentName)
       """)
List<Employee> findByDepartmentName(
        @Param("departmentName") String departmentName
);
```

`e.department` is the association in the JPA mapping. `d` is the alias for `Department`.

### 4.1. INNER JOIN and LEFT JOIN

- `JOIN` or `INNER JOIN`: returns only entities with a matching association.
- `LEFT JOIN`: retains entities on the left side even if the association does not exist; right-side attributes may be null.

Example:

```java
@Query("""
       select e
       from Employee e
       left join e.department d
       where d is null or d.name = :departmentName
       """)
List<Employee> findWithoutDepartmentOrInDepartment(
        @Param("departmentName") String departmentName
);
```

You can JOIN multiple associations in the same query. Use clear aliases to keep the query readable and avoid incorrect JOIN conditions.

### 4.2. JOIN FETCH

`JOIN FETCH` instructs the provider to load the association at the same time as the root entity:

```java
@Query("""
       select e
       from Employee e
       join fetch e.department
       where e.active = true
       """)
List<Employee> findActiveWithDepartment();
```

Fetch join is useful when the service accesses the association within the same use case, helping avoid N+1 queries. Fetch join does not create a separate DTO; it still returns entities with the association loaded into the persistence context.

With collection fetch joins and pagination, be especially careful because a parent entity can appear across multiple rows after a JOIN, affecting page limits and count results. Inspect the SQL, use an appropriate loading strategy, or split into a paginated ID query followed by loading details.

## 5. Projections: Fetching Only Needed Data

Repositories do not always need to return full entities. Projections let you retrieve just the fields required by the screen or business logic.

### 5.1. Interface Projection

Declare an interface:

```java
public interface EmployeeNameView {
    Long getId();
    String getFullName();
    String getEmail();
}
```

The query must assign aliases matching the projection property names:

```java
@Query("""
       select e.id as id,
              e.fullName as fullName,
              e.email as email
       from Employee e
       where e.active = true
       """)
List<EmployeeNameView> findActiveEmployeeNames();
```

Spring Data maps result columns to the corresponding getters. Aliases are critical; if an alias does not match, the projection may fail to receive the right value.

### 5.2. DTO Projection with Constructor Expressions

Create a DTO with a matching constructor:

```java
package com.example.demo.employee;

public record EmployeeSummary(
        Long id,
        String fullName,
        String email
) {
}
```

JPQL uses a constructor expression:

```java
@Query("""
       select new com.example.demo.employee.EmployeeSummary(
           e.id, e.fullName, e.email
       )
       from Employee e
       where e.active = true
       order by e.fullName
       """)
List<EmployeeSummary> findActiveSummaries();
```

JPQL requires the fully qualified class name in the constructor expression. Parameter order and types must match the constructor or canonical record constructor. DTOs are not entities and are not managed by the persistence context.

Projections reduce the amount of data read and avoid returning unnecessary entity graphs. Choose the projection based on the use case; if business logic needs to update an entity, loading a managed entity is usually preferable.

### 5.3. Aggregate Projections

JPQL supports aggregate functions such as `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX`.

Example counting employees by status:

```java
@Query("""
       select count(e)
       from Employee e
       where e.active = :active
       """)
long countByActive(@Param("active") boolean active);
```

Example grouping by department:

```java
@Query("""
       select d.name, count(e)
       from Employee e
       join e.department d
       group by d.name
       having count(e) >= :minimum
       order by count(e) desc
       """)
List<Object[]> countEmployeesByDepartment(
        @Param("minimum") long minimum
);
```

`Object[]` results can be hard to read and prone to index mistakes. For frequently used aggregate queries, consider DTO projections or interface projections.

## 6. Pagination with @Query

A method accepting a `Pageable` parameter can return `Page<T>`. Spring Data applies limits and sorting to the query.

Example:

```java
@Query("""
       select e
       from Employee e
       where lower(e.fullName) like lower(concat('%', :keyword, '%'))
       """)
Page<Employee> searchByName(
        @Param("keyword") String keyword,
        Pageable pageable
);
```

Calling the repository:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "fullName")
);

Page<Employee> page =
        employeeRepository.searchByName("an", pageable);

List<Employee> content = page.getContent();
long total = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

Page index starts at 0. Property names in `Sort` are entity properties, such as `fullName`, not SQL column names like `full_name`.

### 6.1. countQuery

For simple JPQL, Spring Data can usually derive the count query from the SELECT statement. For complex queries, JOINs, DISTINCT, or special projections, declare `countQuery` explicitly:

```java
@Query(
    value = """
            select e
            from Employee e
            join e.department d
            where d.id = :departmentId
              and e.active = true
            """,
    countQuery = """
            select count(e)
            from Employee e
            join e.department d
            where d.id = :departmentId
              and e.active = true
            """
)
Page<Employee> findActiveByDepartment(
        @Param("departmentId") Long departmentId,
        Pageable pageable
);
```

The count query must count the exact result set of the main query. If the main query uses `DISTINCT` or joins a collection that produces multiple rows per entity, design the count query accordingly, potentially using `count(distinct e.id)`.

### 6.2. Page, Slice, and List

- `Page<T>`: includes content and total element/page metadata; usually requires a count query.
- `Slice<T>`: indicates whether a next page exists without requiring the total element count.
- `List<T>` with `Pageable`: fetches only the limited slice of data; provides no page metadata.

If the UI only needs a "Load more" button, `Slice` can save the cost of a count query. If total page counts are needed, use `Page`.

## 7. UPDATE and DELETE with @Modifying

JPQL SELECT is the default query type. When using `@Query` for UPDATE or DELETE, add `@Modifying` so Spring Data executes the query as a data-modifying operation.

### 7.1. UPDATE

```java
@Modifying
@Query("""
       update Employee e
       set e.active = :active
       where e.id = :id
       """)
int updateActive(
        @Param("id") Long id,
        @Param("active") boolean active
);
```

The return value is the number of affected rows. The method must execute within a transaction, typically annotated with `@Transactional` on the service:

```java
@Service
public class EmployeeService {

    private final EmployeeRepository repository;

    public EmployeeService(EmployeeRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void deactivate(Long id) {
        int updated = repository.updateActive(id, false);

        if (updated == 0) {
            throw new IllegalArgumentException("Employee not found");
        }
    }
}
```

### 7.2. DELETE

```java
@Modifying
@Query("""
       delete from Employee e
       where e.active = false
       """)
int deleteInactiveEmployees();
```

JPQL bulk DELETE operates directly on the database. It does not load each entity to invoke standard lifecycle removal.

### 7.3. Persistence Context After Bulk Update/Delete

Bulk UPDATE/DELETE operations do not automatically synchronize entities already loaded in the persistence context. If an `Employee` is managed before running a bulk update, that object may still retain stale values in memory.

You can use these attributes:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
       update Employee e
       set e.active = false
       where e.department.id = :departmentId
       """)
int deactivateByDepartment(
        @Param("departmentId") Long departmentId
);
```

- `flushAutomatically = true`: flushes pending changes before running the bulk query.
- `clearAutomatically = true`: clears the persistence context after the query runs to prevent further use of stale entity instances.

Clearing detaches all entities in the context, so be mindful if the service still needs to work with managed entities afterward.

Bulk queries bypass dirty checking and per-entity lifecycle callbacks; they do not automatically cascade like individual entity `remove()` calls. They also do not automatically apply optimistic locking/version increments in the way normal entity updates do. If an entity has `@Version`, design version conditions and version increments explicitly when concurrency protection is needed.

## 8. Native SQL with nativeQuery = true

When JPQL cannot express a query or database-specific features are needed, you can use native SQL:

```java
@Query(
    value = """
            select *
            from employees
            where lower(email) = lower(:email)
            """,
    nativeQuery = true
)
Optional<Employee> findByEmailNative(
        @Param("email") String email
);
```

Unlike JPQL:

- Native SQL uses the table name `employees`.
- Native SQL uses the column name `email`.
- Syntax is database-dependent.
- Entity results must be compatible with the entity mapping.
- Schema or database changes may require updating the query.

### 8.1. Paginated Native Queries

For native queries returning `Page`, declare the count query explicitly:

```java
@Query(
    value = """
            select *
            from employees
            where active = true
            order by full_name
            """,
    countQuery = """
            select count(*)
            from employees
            where active = true
            """,
    nativeQuery = true
)
Page<Employee> findActiveNative(Pageable pageable);
```

Automatic query parsing and dynamic sorting for native SQL depend on the Spring Data JPA version and SQL complexity. For complex queries, explicitly declare both the count query and SQL ordering, and test against the actual database.

### 8.2. Native Projections

You can return an interface projection if SQL columns are aliased to match getter names:

```java
public interface EmployeeRow {
    Long getId();
    String getFullName();
}
```

```java
@Query(
    value = """
            select id as id, full_name as fullName
            from employees
            where active = true
            """,
    nativeQuery = true
)
List<EmployeeRow> findActiveRows();
```

Native queries are useful when database-specific SQL is required, though they increase coupling to the schema and database. Only use them with clear justification; for routine business queries, JPQL is easier to maintain and migrate across databases.

## 9. SpEL and entityName

Spring Data JPA allows certain SpEL expressions inside `@Query`. A useful case is `#{#entityName}`, which references the entity name of the repository's domain type:

```java
@NoRepositoryBean
public interface BaseReadRepository<T, ID>
        extends Repository<T, ID> {

    @Query("select e from #{#entityName} e where e.id = :id")
    Optional<T> findOneById(@Param("id") ID id);
}
```

Concrete repositories can extend this base interface. `#entityName` helps reuse queries when entity names vary or multiple entities share a common query structure.

SpEL in queries has its own scope and rules in Spring Data. Only use documented expressions; avoid building dynamic queries by concatenating arbitrary strings from user input.

## 10. Safety and Performance Rules

**Use bind parameters.** Always pass data via `@Param` or positional parameters. Never concatenate user input directly into JPQL/SQL due to injection risks and escaping bugs.

**Fetch only necessary data.** Use DTO/interface projections when the full entity is not needed.

**Control N+1.** Use JOIN FETCH or EntityGraph according to the use case; inspect the generated SQL before changing default fetch types.

**Be careful with collection fetching and pagination.** Collection JOINs can multiply rows, breaking pagination or counts. Design separate queries and count queries when needed.

**Bulk updates/deletes require transactions.** Use `@Modifying` and explicit transactions. Synchronize the persistence context after bulk queries if the service still uses loaded entities.

**Check indexes based on actual queries.** Filter conditions, JOINs, and ORDER BY clauses generally determine which indexes are needed. Inspect execution plans and realistic data before adding indexes.

**Do not assume JPQL supports every SQL function.** JPQL has a standard set of functions; database-specific functions may require native queries or provider-supported functions.

**Keep queries readable.** For long JPQL, use text blocks, concise aliases, and line breaks per condition. If a query grows overly complex, consider a custom repository implementation.

## 11. Testing @Query

Use `@DataJpaTest` to verify queries against a test database:

```java
@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void findsEmployeeByEmailIgnoringCase() {
        repository.save(
                new Employee("An Nguyen", "an@example.com", true)
        );

        Optional<Employee> result =
                repository.findByEmailIgnoreCase("AN@example.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getFullName())
                .isEqualTo("An Nguyen");
    }
}
```

The test assumes the repository declares `findByEmailIgnoreCase` using JPQL as in the earlier example, and that entities and test dependencies are configured. `@DataJpaTest` typically runs inside a transaction and rolls back after each test.

You should test:

- Normal parameters, null if allowed by the query, and strings with special characters.
- No results and multiple results.
- JOINs when associations have or lack data.
- Projection aliases and DTO constructors.
- Page/Slice along with count queries.
- Bulk updates/deletes and affected row counts.
- Native queries against the actual production database type.
- Persistence context state after bulk queries.

For native queries or vendor-specific functions, an embedded database may not be compatible. Use Testcontainers or an equivalent test database to verify actual syntax and behavior.

## 12. Common Errors

| Symptom | Cause | Solution |
|---|---|---|
| Query cannot find entity | Using table name instead of entity name in JPQL | Use entity name according to mapping |
| Unknown path/property | Using SQL column name instead of Java attribute | Verify entity properties and associations |
| Parameter not bound | `@Param` name does not match placeholder | Cross-check `:name` with `@Param("name")` |
| Optional returns multiple results | Query condition is not unique | Return `List` or enforce unique constraint |
| Projection receives null | Alias does not match getter | Set alias to exact projection property name |
| DTO constructor mismatch | Wrong FQCN, parameter order, or parameter types | Check the constructor expression |
| Page has wrong total | Count query does not match main query | Declare an accurate `countQuery` |
| Update/delete does not execute | Missing `@Modifying` or transaction | Add `@Modifying` and appropriate transaction |
| Managed entity holds stale data | Bulk query bypasses persistence context | Use appropriate clear/refresh |
| Native query fails in production | SQL depends on database/schema | Test against the target database |
| Query returns duplicate data | Collection JOIN produces multiple rows | Use DISTINCT or adjust the query |
| SQL injection | Concatenating input into query string | Use bind parameters |

## 13. Pre-Commit Repository Query Checklist

- [ ] JPQL uses accurate entity names and Java properties.
- [ ] Parameters are bound with named or positional parameters.
- [ ] Return type matches expected result cardinality.
- [ ] Projection aliases/DTO constructors match the query.
- [ ] Page has a proper `countQuery` when needed.
- [ ] Bulk UPDATE/DELETE has `@Modifying` and a transaction.
- [ ] Persistence context is synchronized after bulk queries when needed.
- [ ] Native queries use accurate table/column names and are tested on the target database.
- [ ] Query does not concatenate user input directly.
- [ ] SQL and execution plan have been reviewed if the query is performance-critical.

## Conclusion

`@Query` lets you declare queries clearly right on the repository. JPQL queries by entity and Java property, supporting conditions, JOINs, projections, aggregates, and pagination. `@Modifying` extends usage to bulk UPDATE/DELETE; `nativeQuery = true` enables database-specific SQL.

Prefer named parameters, choose the right return type, declare `countQuery` when needed, and manage the persistence context after bulk queries. Keeping queries focused on data retrieval and testing against an appropriate database keeps repositories readable, safe, and reliable.