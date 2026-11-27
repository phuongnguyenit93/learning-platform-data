# Constructor Expressions for Returning DTOs in JPQL and Spring Data JPA

A JPQL constructor expression lets a query instantiate a DTO directly from values retrieved from the database. Instead of loading an entire entity and manually copying each field into a DTO in Java, the query selects only the required attributes and invokes the result class's constructor.

The core syntax is `SELECT NEW some.package.Dto(arg1, arg2, ...)`. The class name must be fully qualified with its package, and argument order and types must match the constructor. This approach works well for list views, reports, read-only APIs, and aggregate queries.

## 1. What is a Constructor Expression?

A regular JPQL query can return entities:

~~~java
select e
from Employee e
where e.active = true
~~~

The result consists of `Employee` entities managed by JPA in the persistence context. If a screen only needs the ID, employee name, and department name, loading the entire entity can fetch more data than necessary.

A constructor expression builds the DTO directly in the query result:

~~~java
select new com.example.report.EmployeeSummary(
    e.id,
    e.name,
    d.name
)
from Employee e
join e.department d
where e.active = true
~~~

Each result row is converted into an `EmployeeSummary` object. The provider retrieves the values of the SELECT expressions and invokes the matching constructor.

Key benefits:

- Selects only the columns needed for the use case.
- Avoids returning entities or proxies directly from APIs.
- Eliminates repetitive manual mapping in the service layer.
- Combines naturally with joins, filters, expressions, and aggregates.
- Resulting DTOs fit read-only queries and reports cleanly.

Constructor expressions are JPQL syntax. They are not raw SQL syntax; entity and attribute names in the query are mapped Java names, not necessarily physical table/column names.

## 2. Syntax and Mandatory Rules

General form:

~~~sql
SELECT NEW fully.qualified.DtoClass(expression1, expression2, ...)
FROM EntityName alias
...
~~~

Rules to remember:

1. The `NEW` keyword must precede the DTO class name.
2. The class name must be a fully qualified class name, such as `com.example.report.EmployeeSummary`.
3. Argument order in the constructor expression must match the constructor's parameter order.
4. The Java type of each expression must be compatible with the corresponding parameter type.
5. The DTO needs a matching constructor; the examples below use a `public` constructor for broad compatibility.
6. Do not place aliases such as `e.name AS employeeName` inside the constructor expression's argument list. Parameter variable names in the DTO are determined by the constructor.
7. JPQL uses entity names and Java attributes, such as `Employee e`, `e.name`, `e.department`; do not use SQL table/column names like `employees` or `employee_name` directly unless those happen to be the mapped entity/attribute names.
8. The `NEW` expression must point to a class that the provider can instantiate via the matching constructor.

Valid example:

~~~java
select new com.example.report.EmployeeSummary(
    e.id,
    e.name,
    d.name,
    e.salary
)
from Employee e
join e.department d
~~~

Invalid example if the DTO lacks a constructor with that exact order and types:

~~~java
select new com.example.report.EmployeeSummary(
    e.name,
    e.id,
    e.salary,
    d.name
)
from Employee e
join e.department d
~~~

Parameter names in Java do not have to match entity attribute names. What matters is the order and types of values passed to the constructor.

## 3. Complete Example: Returning an Employee and Department DTO

Suppose the model has two entities:

- `Employee`: `id` of type `Long`, `name` of type `String`, `salary` of type `BigDecimal`, and a `department` association.
- `Department`: `id` of type `Long` and `name` of type `String`.

The relationship from employee to department is `@ManyToOne`. We need a DTO displaying employee details without returning the whole entity.

### 3.1. Creating the DTO

Create `src/main/java/com/example/report/EmployeeSummary.java`:

~~~java
package com.example.report;

import java.math.BigDecimal;

public class EmployeeSummary {

    private final Long employeeId;
    private final String employeeName;
    private final String departmentName;
    private final BigDecimal salary;

    public EmployeeSummary(
            Long employeeId,
            String employeeName,
            String departmentName,
            BigDecimal salary) {
        this.employeeId = employeeId;
        this.employeeName = employeeName;
        this.departmentName = departmentName;
        this.salary = salary;
    }

    public Long getEmployeeId() {
        return employeeId;
    }

    public String getEmployeeName() {
        return employeeName;
    }

    public String getDepartmentName() {
        return departmentName;
    }

    public BigDecimal getSalary() {
        return salary;
    }
}
~~~

The DTO holds only the data the use case requires. It does not need `@Entity`, `@Table`, or `@Id` because it does not represent a database-persisted entity.

Fields are declared `final` so the result object remains immutable after construction. The constructor takes four arguments in the exact order JPQL passes them.

### 3.2. Declaring the Repository with @Query

Create or add the method to `EmployeeRepository.java`:

~~~java
package com.example.repository;

import com.example.report.EmployeeSummary;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select new com.example.report.EmployeeSummary(
               e.id,
               e.name,
               d.name,
               e.salary
           )
           from Employee e
           join e.department d
           where d.id = :departmentId
             and e.active = true
           order by e.name
           """)
    List<EmployeeSummary> findActiveSummariesByDepartment(
            @Param("departmentId") Long departmentId);
}
~~~

This snippet assumes entity `Employee` has attributes `id`, `name`, `salary`, `active`, and `department`; entity `Department` has `id` and `name`.

Query breakdown:

- `e.id` passes into the first parameter of type `Long`.
- `e.name` passes into the second parameter of type `String`.
- `d.name` passes into the third parameter of type `String`.
- `e.salary` passes into the fourth parameter of type `BigDecimal`.
- `join e.department d` joins the relationship declared on the entity.
- `:departmentId` is a named parameter bound via `@Param`.
- `order by e.name` sorts by the entity attribute.

When invoked:

~~~java
List<EmployeeSummary> summaries =
        employeeRepository.findActiveSummariesByDepartment(5L);
~~~

Spring Data JPA executes the JPQL, the provider instantiates each `EmployeeSummary`, and returns the DTO list to the caller.

### 3.3. Why Is a Fully Qualified Class Name Required?

In JPQL, the class name in a constructor expression is resolved like a Java class name. The query does not infer packages from imports in the repository or DTO file.

If the DTO has package:

~~~java
package com.example.report;
~~~

the query must write:

~~~java
select new com.example.report.EmployeeSummary(...)
~~~

You cannot simply write `new EmployeeSummary(...)` and expect JPQL to reuse the repository file's imports. Java imports apply only to Java code, not inside JPQL strings.

## 4. Data Types of Constructors and JPQL Expressions

A common error is getting the class name right while constructor parameter types do not match the SELECT expression types.

Entity example:

~~~java
@Id
private Long id;

@Column(nullable = false)
private BigDecimal salary;

private String name;
~~~

The DTO constructor must be compatible:

~~~java
public EmployeeSummary(
        Long id,
        String name,
        BigDecimal salary) {
    // ...
}
~~~

Do not change `Long` to `Integer` or `BigDecimal` to `Double` simply because sample data looks small enough. The provider resolves expression types from the mapping and JPQL rules, not from runtime sample values.

### 4.1. Aggregate Return Types

Aggregate functions have defined return types:

| JPQL Expression | Typical Spec Result Type |
|---|---|
| `COUNT(...)` | `Long` |
| `AVG(...)` | `Double` |
| `SUM(...)` on integer types | `Long` |
| `SUM(...)` on `BigInteger` | `BigInteger` |
| `SUM(...)` on `BigDecimal` | `BigDecimal` |
| `MIN(...)` / `MAX(...)` | Type of input expression |

When using aggregates in constructor expressions, declare constructor parameters using the function's result type, not merely the entity field's type.

For example, `COUNT(e)` returns `Long`:

~~~java
public DepartmentStats(
        Long departmentId,
        String departmentName,
        Long employeeCount) {
    // ...
}
~~~

If the constructor takes `Integer employeeCount`, the provider may fail to locate a matching constructor.

### 4.2. Null Values and LEFT JOIN

With `LEFT JOIN`, attributes from the unmatched right side can be `null`. The DTO constructor must accept null if the query allows it.

Example:

~~~java
select new com.example.report.EmployeeSummary(
    e.id,
    e.name,
    d.name,
    e.salary
)
from Employee e
left join e.department d
~~~

If an employee has no assigned department, `d.name` can be null. The `departmentName` field in the DTO must allow null, or the query must use `COALESCE` to provide a fallback value:

~~~java
coalesce(d.name, 'Uncategorized')
~~~

Do not use primitive types like `long` or `double` for parameters that can receive null. Use wrappers like `Long`, `Double`, or an appropriate reference type.

### 4.3. BigDecimal and Monetary Values

If an entity uses `BigDecimal` for salary, the DTO should accept `BigDecimal` as well. Do not convert to `double` purely for display, as floating-point precision errors can occur.

When asserting in tests, use `isEqualByComparingTo` or `compareTo` to avoid false mismatches over scale differences such as `100.0` vs. `100.00`.

## 5. Constructor Expressions with GROUP BY and Aggregate Functions

DTOs fit aggregate reports naturally. Suppose we need employee counts and total salary per department.

### 5.1. DepartmentPayroll DTO

Create `DepartmentPayroll.java`:

~~~java
package com.example.report;

import java.math.BigDecimal;

public class DepartmentPayroll {

    private final Long departmentId;
    private final String departmentName;
    private final Long employeeCount;
    private final BigDecimal totalSalary;

    public DepartmentPayroll(
            Long departmentId,
            String departmentName,
            Long employeeCount,
            BigDecimal totalSalary) {
        this.departmentId = departmentId;
        this.departmentName = departmentName;
        this.employeeCount = employeeCount;
        this.totalSalary = totalSalary;
    }

    public Long getDepartmentId() {
        return departmentId;
    }

    public String getDepartmentName() {
        return departmentName;
    }

    public Long getEmployeeCount() {
        return employeeCount;
    }

    public BigDecimal getTotalSalary() {
        return totalSalary;
    }
}
~~~

### 5.2. JPQL Aggregate Query

Suppose `Department` has an `employees` collection mapped with `@OneToMany(mappedBy = "department")`:

~~~java
@Query("""
       select new com.example.report.DepartmentPayroll(
           d.id,
           d.name,
           count(e),
           sum(e.salary)
       )
       from Department d
       left join d.employees e
       group by d.id, d.name
       order by d.name
       """)
List<DepartmentPayroll> summarizePayroll();
~~~

Query behavior:

- Starts from `Department` so departments with zero employees are still included.
- Uses `LEFT JOIN` to keep departments without employees.
- `count(e)` counts employees; for an empty department, the result is 0.
- `sum(e.salary)` sums salaries; for groups with no non-null values, the result can be null.
- `group by d.id, d.name` forms one group per department.
- `order by d.name` sorts the output.

Because `totalSalary` can be null for an empty department, the DTO should accept null or normalize it inside the constructor:

~~~java
this.totalSalary = totalSalary == null
        ? BigDecimal.ZERO
        : totalSalary;
~~~

Do not change the constructor parameter type to `Double` when `SUM` operates on `BigDecimal`.

### 5.3. HAVING to Filter Groups

You can filter departments with at least a minimum number of employees:

~~~java
@Query("""
       select new com.example.report.DepartmentPayroll(
           d.id,
           d.name,
           count(e),
           sum(e.salary)
       )
       from Department d
       left join d.employees e
       group by d.id, d.name
       having count(e) >= :minimumEmployees
       """)
List<DepartmentPayroll> summarizePayroll(
        @Param("minimumEmployees") long minimumEmployees);
~~~

`WHERE` filters rows before grouping; `HAVING` filters groups after `GROUP BY`. When using aggregates in group-level conditions, place the condition in `HAVING`.

## 6. Paginating DTO Results

Spring Data JPA can return `Page<DTO>` from a constructor expression. Example:

~~~java
@Query(
    value = """
            select new com.example.report.EmployeeSummary(
                e.id,
                e.name,
                d.name,
                e.salary
            )
            from Employee e
            join e.department d
            where d.id = :departmentId
            """,
    countQuery = """
                 select count(e)
                 from Employee e
                 join e.department d
                 where d.id = :departmentId
                 """
)
Page<EmployeeSummary> findSummaries(
        @Param("departmentId") Long departmentId,
        Pageable pageable);
~~~

`value` fetches the page content. `countQuery` counts total matching entities to build `Page` metadata.

Important points:

- The count query must preserve the same filtering conditions as the content query.
- If the content query contains joins that multiply entities, consider `count(distinct e.id)` and `select distinct new ...` according to the intended semantics.
- For queries with `GROUP BY`, counting can be trickier; write an explicit count query and test total group counts.
- If the UI only needs to know whether a next page exists, consider `Slice<DTO>` to avoid counting total results.
- `Pageable` limits and sorts results; inspect the SQL generated by the provider for your actual query.

Calling example:

~~~java
Page<EmployeeSummary> page =
        employeeRepository.findSummaries(
                5L,
                PageRequest.of(0, 20)
        );

List<EmployeeSummary> content = page.getContent();
long total = page.getTotalElements();
int pages = page.getTotalPages();
~~~

## 7. Comparing Constructor Expressions with Other Projection Types

Spring Data JPA supports multiple ways to return data. Pick the approach suited to query complexity and purpose.

| Approach | Declaration | Best Fit |
|---|---|---|
| Entity result | `select e from Employee e` | Need managed entities to run business logic or perform updates |
| Constructor expression | `select new package.Dto(...)` | Want an explicit DTO, many fields, or aggregate results |
| Interface projection | Getter interface with aliases in SELECT | Simple read DTOs where Spring Data maps by property name |
| Native query mapping | Raw SQL with result set mapping or a matching projection mechanism | Need database-specific SQL |

Interface projection example:

~~~java
public interface EmployeeNameView {
    Long getEmployeeId();
    String getEmployeeName();
}
~~~

~~~java
@Query("""
       select e.id as employeeId,
              e.name as employeeName
       from Employee e
       where e.active = true
       """)
List<EmployeeNameView> findActiveNames();
~~~

With interface projections, aliases in `SELECT` must match getter names per Spring Data's mapping rules. With constructor expressions, argument order and types determine which constructor is invoked; aliases do not replace positional matching.

Constructor expressions are often easier to control when DTOs have explicit constructors or when queries include aggregates. Interface projections can be more concise for flat results with few fields.

## 8. Common Limitations and Errors

### 8.1. Forgetting the Fully Qualified Class Name

Incorrect:

~~~java
select new EmployeeSummary(e.id, e.name)
from Employee e
~~~

Correct:

~~~java
select new com.example.report.EmployeeSummary(e.id, e.name)
from Employee e
~~~

JPQL does not use repository imports to locate DTO classes.

### 8.2. Constructor Order or Type Mismatch

If a query passes `(Long, String, BigDecimal)`, the DTO must have a constructor accepting those exact types in that order. Verify both aggregate return types and nullable types.

### 8.3. DTO Missing a Matching Constructor

A DTO with only a default constructor or only setters is insufficient for a constructor expression passing arguments. Add a public constructor with the matching signature.

When using Lombok, constructor-generating annotations must produce the exact parameter order and types required by the query. Do not rely on IDE displays if the actual build does not generate that constructor.

### 8.4. Placing Aliases Inside the Constructor Expression

Do not write:

~~~java
select new com.example.report.EmployeeSummary(
    e.id as employeeId,
    e.name as employeeName
)
from Employee e
~~~

Remove the aliases:

~~~java
select new com.example.report.EmployeeSummary(
    e.id,
    e.name
)
from Employee e
~~~

Aliases belong in interface projections or ordinary SELECT items. Constructor expressions pass arguments positionally.

### 8.5. Confusing Entity Names with Table Names

If an entity is declared `@Entity(name = "Employee")`, JPQL uses `Employee`. The physical table name might be `employees`, which cannot replace the entity name in JPQL.

Likewise, `e.department.name` is a Java property path. Even if the physical column is `department_name`, the query still uses the entity's mapped attribute.

### 8.6. Using Constructor Expressions in Native SQL

`SELECT NEW` syntax belongs to JPQL, not SQL. For native queries, use result set mappings such as `@SqlResultSetMapping`/`@ConstructorResult` or a Spring Data-supported projection mechanism.

### 8.7. LEFT JOIN Returning Null

For optional relationships, fields from the right side can be null. DTOs must use reference types and handle null safely. With aggregates, `SUM` can return null in groups with no values.

### 8.8. Unnecessary Fetch Joins

Constructor expressions only read values to build a DTO. When selecting `d.name` or `e.salary` in `SELECT`, you do not need `JOIN FETCH` to load an entity graph. Use a regular join to combine and filter data.

### 8.9. Mistaking a DTO for a Managed Entity

A DTO instantiated via constructor expression is a query result object, not an `Employee` entity managed by the persistence context. Mutating the DTO does not automatically update the database. To persist changes, load a managed entity inside a transaction and update it there.

### 8.10. Query Returns Multiple Rows While Method Declares Optional

If a query can return multiple rows, declare `List<DTO>` or `Page<DTO>`. Use `Optional<DTO>` only when query conditions guarantee at most one row, such as filtering by a unique key. If a query returns multiple rows for a single-result method, the provider throws a non-unique result exception.

## 9. Testing Constructor Expressions

A repository test should verify both returned data and that the constructor populated the right fields.

Illustrative example with `@DataJpaTest`:

~~~java
@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private EmployeeRepository employees;

    @Test
    void returnsEmployeeSummaryDto() {
        Department department = new Department("Engineering");
        entityManager.persist(department);

        Employee employee = new Employee(
                "An",
                new BigDecimal("1250.00"),
                true,
                department
        );
        entityManager.persist(employee);
        entityManager.flush();
        entityManager.clear();

        List<EmployeeSummary> result =
                employees.findActiveSummariesByDepartment(
                        department.getId());

        assertThat(result).hasSize(1);

        EmployeeSummary summary = result.get(0);
        assertThat(summary.getEmployeeId()).isEqualTo(employee.getId());
        assertThat(summary.getEmployeeName()).isEqualTo("An");
        assertThat(summary.getDepartmentName()).isEqualTo("Engineering");
        assertThat(summary.getSalary())
                .isEqualByComparingTo("1250.00");
    }
}
~~~

This test assumes `Department` has a constructor taking a name and `Employee` has a constructor taking name, salary, active flag, and department. Adjust constructors to match your project's entity model.

`flush()` sends setup data to the database before querying; `clear()` clears the persistence context so the test does not accidentally rely on managed entity instances. The DTO query then executes like a normal database query.

When testing aggregates, include empty-group cases if using `LEFT JOIN` and verify how the DTO handles null `SUM` values. For pagination, assert `getContent()`, `getTotalElements()`, and count query criteria.

## 10. When Should You Use Constructor Expressions?

Use them when:

- Results are read-only and no entity updates are needed.
- An API or screen needs only a specific subset of fields.
- Data from multiple entities must be combined.
- Reports need `COUNT`, `SUM`, `AVG`, or grouped results.
- You want data-packing logic encapsulated in a DTO with an explicit constructor.
- You want to avoid leaking entities/proxies out of the service layer.

Prefer entity results when you need to mutate managed entities within a transaction. Prefer interface projections for flat results with few fields. For native SQL or database-specific queries, pick an appropriate result set mapping or projection.

## 11. Pre-Query Checklist

- [ ] DTO resides in a clear package and the query uses its fully qualified class name.
- [ ] DTO has a constructor matching the argument count.
- [ ] Constructor parameter order matches the SELECT expression order.
- [ ] Java types are compatible with JPQL expressions and aggregate return types.
- [ ] Null values from `LEFT JOIN` or `SUM` are handled.
- [ ] JPQL uses entity names and Java attributes.
- [ ] No aliases are placed inside the constructor expression argument list.
- [ ] `SELECT NEW` is not used inside native SQL.
- [ ] `List`, `Optional`, `Page`, or `Slice` matches expected result cardinality.
- [ ] An accurate `countQuery` is provided when using `Page` with complex queries.
- [ ] Repository tests verify DTO contents and edge cases.

## 12. References

- [Jakarta Persistence 3.1 Specification](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.pdf) — JPQL grammar, constructor expressions, aggregates, and result types.
- [Spring Data JPA Reference Documentation](https://docs.spring.io/spring-data/jpa/reference/) — query declarations, DTO projections, interface projections, and pagination.
- [Spring Data JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — using `@Query` and declared queries.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/6.2/userguide/html_single/) — JPQL/HQL execution and projections.

Constructor expressions let JPQL return the exact data shape callers need. Keep DTOs independent of entities, use fully qualified class names, ensure constructor order and types match `SELECT`, and test nulls, aggregates, and pagination. Following these rules enables repositories to deliver clean read models without loading large entity graphs or writing manual post-query mapping steps.