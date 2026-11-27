# The Entity.method Naming Convention and Query Lookup Mechanism in Spring Data JPA

Spring Data JPA can look up a query for a repository method by naming convention. For named queries, the query name usually takes the form of the domain class name, a dot, and the repository method name, for example `Employee.findByEmailAddress`. When the repository invokes the corresponding method, Spring Data searches for a predeclared named query; if none is found, the default strategy can parse the method name to generate a derived query.

This mechanism helps separate JPQL statements from repository interfaces, reuse named queries, and explicitly control whether the application must define queries beforehand or is allowed to derive them automatically. This lesson covers the naming convention, declaration via annotations or orm.xml, query lookup order, parameters, return types, examples, and testing.

## 1. What is a named query?

A named query is a query declared in advance with an identifier name. The JPA provider registers that query in the persistence unit so the application can invoke it by name.

Named queries are usually written in JPQL:

~~~java
@NamedQuery(
    name = "Employee.findByEmailAddress",
    query = "select e from Employee e where e.emailAddress = :email"
)
~~~

Where:

- Employee.findByEmailAddress is the identifier name of the query.
- Employee is the entity name in JPQL unless the entity specifies another name with @Entity(name = ...).
- e is the entity alias.
- e.emailAddress is the Java property of the entity.
- :email is the named parameter passed at execution time.

Named queries can be declared with @NamedQuery/@NamedQueries on an entity or in an XML mapping file such as META-INF/orm.xml. Spring Data JPA can look up this query when creating the corresponding repository method.

Named queries fit queries with stable structure, frequent reuse, or a need for explicit naming. For small one-off queries, placing @Query directly on the repository method may be easier to read.

## 2. The Entity.method Naming Convention

Spring Data JPA uses the naming convention:

~~~text
<DomainClassSimpleName>.<RepositoryMethodName>
~~~

Examples:

| Entity class | Repository method | Named query name |
|---|---|---|
| Employee | findByEmailAddress | Employee.findByEmailAddress |
| Employee | findActiveEmployees | Employee.findActiveEmployees |
| PurchaseOrder | findByOrderNumber | PurchaseOrder.findByOrderNumber |
| Product | searchByCategory | Product.searchByCategory |

The part before the dot is the simple name of the domain class managed by the repository; the part after the dot is the exact method name in the repository. Names are case-sensitive, so consistency must be maintained.

Do not use the database table name instead of the domain class name in this convention. For example, if entity Employee maps to table `employees`, the query name still begins with `Employee`, not `employees`.

Also distinguish between two names:

- The named query name uses Spring Data's convention: Employee.findByEmailAddress.
- The entity name in JPQL uses the JPA entity name: Employee by default, though it can be changed with @Entity(name = "StaffMember").

If an entity specifies @Entity(name = "StaffMember"), Spring Data still looks up the named query by the domain class simple name `Employee.findByEmailAddress`; the JPQL inside the query must write `FROM StaffMember e`. Do not confuse the JPQL entity name with the named query identifier name.

## 3. Declaring named queries with @NamedQuery

Example `Employee` entity:

~~~java
package com.example.employee;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.NamedQueries;
import jakarta.persistence.NamedQuery;
import jakarta.persistence.Table;

@Entity
@Table(name = "employees")
@NamedQueries({
    @NamedQuery(
        name = "Employee.findByEmailAddress",
        query = """
                select e
                from Employee e
                where e.emailAddress = :email
                """
    ),
    @NamedQuery(
        name = "Employee.findActiveWithMinimumSalary",
        query = """
                select e
                from Employee e
                where e.active = true
                  and e.salary >= :minimumSalary
                order by e.name asc
                """
    )
})
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false, unique = true, length = 200)
    private String emailAddress;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal salary;

    protected Employee() {
    }

    public Employee(
            String name,
            String emailAddress,
            boolean active,
            BigDecimal salary) {
        this.name = name;
        this.emailAddress = emailAddress;
        this.active = active;
        this.salary = salary;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmailAddress() {
        return emailAddress;
    }

    public boolean isActive() {
        return active;
    }

    public BigDecimal getSalary() {
        return salary;
    }
}
~~~

@NamedQueries is a container holding multiple @NamedQuery declarations. If there is only one query, you can use @NamedQuery directly.

The first query finds an employee by email. The second filters active employees with a minimum salary and sorts by name. The queries use entity names and Java properties; Hibernate translates them into SQL according to the database dialect.

Named queries are registered in the persistence unit. JPQL syntax errors, invalid entity names, or nonexistent properties are typically detected when the JPA provider initializes metadata or when the query is created, depending on the provider and configuration. Therefore, run integration tests and inspect startup logs after changing a named query.

## 4. Calling a named query via a repository method

The repository method must match the part after the dot in the named query:

~~~java
package com.example.employee;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    Optional<Employee> findByEmailAddress(
            @Param("email") String email);

    List<Employee> findActiveWithMinimumSalary(
            @Param("minimumSalary") BigDecimal minimumSalary);
}
~~~

Spring Data looks for:

- Employee.findByEmailAddress for the `findByEmailAddress` method.
- Employee.findActiveWithMinimumSalary for the `findActiveWithMinimumSalary` method.

The method `findActiveWithMinimumSalary` does not follow standard derived query syntax such as `findBy...`, yet it still works when a named query with the same name is declared. This is a useful way to decouple use-case method names from JPQL details.

Example service call:

~~~java
@Service
public class EmployeeService {

    private final EmployeeRepository repository;

    public EmployeeService(EmployeeRepository repository) {
        this.repository = repository;
    }

    public Optional<Employee> findByEmail(String email) {
        return repository.findByEmailAddress(email);
    }

    public List<Employee> findEligibleEmployees(BigDecimal minimumSalary) {
        return repository.findActiveWithMinimumSalary(minimumSalary);
    }
}
~~~

The first named query uses the parameter `:email`, and the method declares `@Param("email")` to bind the Java argument. The second query does the same with `:minimumSalary`. Using `@Param` makes the mapping explicit and independent of whether the compiler retains parameter names.

## 5. Spring Data JPA's query lookup mechanism

Spring Data JPA provides three main QueryLookupStrategy options:

| Strategy | How it works | When appropriate |
|---|---|---|
| CREATE | Always creates queries from method names | Want repository methods to express queries via naming conventions |
| USE_DECLARED_QUERY | Requires finding a declared query; fails if not found | Want every query to be explicitly defined |
| CREATE_IF_NOT_FOUND | Searches for a declared query first; derives from method name if absent | Need to combine named queries, @Query, and derived queries |

CREATE_IF_NOT_FOUND is the default strategy of Spring Data JPA.

The lookup order in default mode can be visualized as follows:

~~~mermaid
flowchart TD
    A[Repository method] --> B{Has @Query on method?}
    B -->|Yes| C[Use @Query]
    B -->|No| D{Has matching named query?}
    D -->|Yes| E[Use named query Entity.method]
    D -->|No| F[Parse method name]
    F --> G[Derived query]
~~~

The diagram illustrates the precedence rule in default mode. A method with `@Query` uses the query declared directly on the method; otherwise, Spring Data searches for a named query by convention. If no declared query is found, `CREATE_IF_NOT_FOUND` falls back to a derived query.

If a method has no `@Query` and no matching named query exists, the method name must be valid under derived query rules. For example, `findByEmailAddress` can be parsed; `findActiveWithMinimumSalary` is typically not a valid derived query if the entity has no matching properties.

## 6. Configuring QueryLookupStrategy

Usually no configuration is needed because `CREATE_IF_NOT_FOUND` is the default. If you want to require every method to have a declared query, configure `USE_DECLARED_QUERY`:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.query.QueryLookupStrategy;

@Configuration
@EnableJpaRepositories(
    queryLookupStrategy = QueryLookupStrategy.Key.USE_DECLARED_QUERY
)
public class RepositoryConfig {
}
~~~

With `USE_DECLARED_QUERY`, each method must have a declared query, such as `@Query` or a properly named named query. If missing, Spring Data reports an error when creating the repository instead of parsing the method name.

To always construct queries from method names, use:

~~~java
@EnableJpaRepositories(
    queryLookupStrategy = QueryLookupStrategy.Key.CREATE
)
~~~

`CREATE` ignores named queries and builds queries from method names. Only choose this when the project intentionally relies on derived queries for those methods.

When using Spring Boot, check existing repository configuration before adding a new `@EnableJpaRepositories`. If repository scanning is already configured, place `queryLookupStrategy` on that configuration to avoid unintentionally changing the scanned packages.

## 7. Named queries in META-INF/orm.xml

Named queries can be placed in an XML file instead of entity annotations. This separates query metadata from entity class code.

Create the file:

~~~text
src/main/resources/META-INF/orm.xml
~~~

Example content:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_1.xsd"
    version="3.1">

    <named-query name="Employee.findActiveWithMinimumSalary">
        <query>
            <![CDATA[
                select e
                from Employee e
                where e.active = true
                  and e.salary >= :minimumSalary
                order by e.name asc
            ]]>
        </query>
    </named-query>

</entity-mappings>
~~~

Spring Boot and the JPA provider usually auto-detect `orm.xml` at the standard `META-INF/orm.xml` location. If the project places mapping files elsewhere, declare the corresponding mapping resources in the persistence configuration.

Do not declare the same named query name in multiple places without an explicit reason. Duplicate query names within a persistence unit can cause conflicts or depend on provider metadata override rules. Pick one clear source of definition for each query.

### Choosing annotations or XML

| Declaration style | Advantages | Limitations |
|---|---|---|
| @NamedQuery on entity | Queries live near the entity, easy to find when few | Entity can become cluttered with annotations and query details |
| META-INF/orm.xml | Separates queries from Java code, centralizes mapping management | XML names and syntax are error-prone, requires tracking a separate file |
| @Query on repository method | Query is right at the call site, easy to read alongside return type | Repository may contain many long JPQL strings |
| Derived query | Minimal code, easy to understand for simple conditions | Hard to express complex queries or multiple joins |

There is no single choice for every project. Use the approach that suits your query size, team conventions, and maintainability.

## 8. Parameters in named queries

JPQL supports named parameters and positional parameters.

Named parameter:

~~~java
@NamedQuery(
    name = "Employee.findByEmailAddress",
    query = "select e from Employee e where e.emailAddress = :email"
)
~~~

Repository:

~~~java
Optional<Employee> findByEmailAddress(
        @Param("email") String email);
~~~

Positional parameter:

~~~java
@NamedQuery(
    name = "Employee.findByEmailAddress",
    query = "select e from Employee e where e.emailAddress = ?1"
)
~~~

Repository:

~~~java
Optional<Employee> findByEmailAddress(String email);
~~~

Named parameters are usually easier to read and less error-prone when a query has many parameters. Positional parameters depend on order, so care is needed when changing method signatures.

Do not mix named parameters and positional parameters in the same query. The name in `@Param` must match the name after the colon in JPQL exactly. Do not include a colon in the `@Param` value.

Bound parameters are for data values. You cannot use bind parameters to substitute entity names, property names, `ORDER BY` keywords, or dynamic table names. If the query structure needs to vary by input, use controlled dynamic queries or the Specification/Criteria API.

## 9. @Query takes precedence over named queries

If a repository method has both `@Query` and a named query with the same name, Spring Data JPA gives priority to the `@Query` declared on the method.

Example:

~~~java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @Query("""
           select e
           from Employee e
           where e.emailAddress = :email
             and e.active = true
           """)
    Optional<Employee> findByEmailAddress(
            @Param("email") String email);
}
~~~

Here the method uses `@Query` on the repository. Even if named query `Employee.findByEmailAddress` exists, it will not be used for this method.

This rule is useful when one repository needs to customize a query without modifying a named query used elsewhere. However, avoid leaving two different definitions around long-term unless the team has a clear reason; they easily cause confusion during maintenance.

## 10. How do named queries and derived queries differ?

| Criterion | Named query | Derived query |
|---|---|---|
| Query source | @NamedQuery or orm.xml | Repository method name |
| Method name | Can be any use-case name if named query matches | Must follow Spring Data syntax |
| JPQL statement | Written explicitly when declaring the query | Generated by the framework |
| Complex queries | Easy to control JPQL, joins, projections | Method names can become overly long or inexpressible |
| Changing conditions | Edit named query definition | Rename method |
| Property name validation | Provider validates declared query | Spring Data parses method name |
| Reusability | Can be called via registered query name | Tied to the repository method |

Derived query example:

~~~java
List<Employee> findByActiveTrueAndSalaryGreaterThanEqualOrderByNameAsc(
        BigDecimal minimumSalary);
~~~

Named query example:

~~~java
List<Employee> findActiveWithMinimumSalary(
        @Param("minimumSalary") BigDecimal minimumSalary);
~~~

Derived queries fit simple conditions with short, clear names. Named queries fit cases where you want control over JPQL or want method names that express the use case.

## 11. Repository method return types

The return type must match the cardinality and structure of the named query's results.

| Return type | When used |
|---|---|
| Entity | Query is expected to return one entity |
| Optional<Entity> | At most one entity, may not be found |
| List<Entity> | May return multiple entities |
| Page<Entity> | Needs pagination and total result count |
| Slice<Entity> | Needs pagination without total count |
| Projection/DTO | Only needs a subset of fields or computed results |
| Scalar such as String, Long, BigDecimal | Query SELECTs a single corresponding expression |

Example query returning an entity:

~~~java
@NamedQuery(
    name = "Employee.findByEmailAddress",
    query = "select e from Employee e where e.emailAddress = :email"
)
~~~

The repository can return `Optional<Employee>` if email is unique. If the query can return multiple rows, use `List<Employee>` or `Page<Employee>`.

Do not declare `Optional` for a query capable of returning more than one row. If the result has multiple rows while the method expects a single result, Spring Data may throw `IncorrectResultSizeDataAccessException` or a corresponding provider exception.

For queries returning scalars or DTOs, the SELECT expressions must match the return type. For example, `select count(e)` returns `Long`; `select e.name` returns `String`. With a constructor expression, argument types and order must match the DTO constructor.

## 12. Named queries returning DTOs

JPQL can use a constructor expression to construct DTOs:

~~~java
package com.example.employee;

public record EmployeeSummary(
        Long id,
        String name,
        String emailAddress
) {
}
~~~

Named query:

~~~java
@NamedQuery(
    name = "Employee.findSummariesByActive",
    query = """
            select new com.example.employee.EmployeeSummary(
                e.id, e.name, e.emailAddress
            )
            from Employee e
            where e.active = :active
            order by e.name
            """
)
~~~

Repository:

~~~java
List<EmployeeSummary> findSummariesByActive(
        @Param("active") boolean active);
~~~

The DTO class name in a JPQL constructor expression must be the fully qualified class name. The constructor must accept the exact types and order of the SELECT expressions. Java records have a canonical constructor, making them a good fit for this example.

DTO projections avoid loading entire entities and unnecessary associations. They are a good choice for reports or APIs that only need partial data.

## 13. Named queries with pagination and sorting

A repository method can accept `Pageable` to paginate results:

~~~java
Page<Employee> findActiveWithMinimumSalary(
        @Param("minimumSalary") BigDecimal minimumSalary,
        Pageable pageable);
~~~

The corresponding named query still uses the name:

~~~text
Employee.findActiveWithMinimumSalary
~~~

The JPQL in the named query should have a deterministic ordering if pagination is used. For example, `order by e.name, e.id` helps keep page ordering stable when multiple employees share the same name.

With declared queries and `Pageable`, Spring Data needs to determine a count query to compute total elements. Depending on the query type and Spring Data version, the framework can derive a count query; if it cannot be derived or the query is complex, you need to provide an appropriate counting mechanism via supported query declaration features. Inspect SQL logs and test total page counts, not just the content list.

If you only need to know whether a next page exists, using `Slice` can avoid running a total count query.

Dynamic sorting with `Sort` must be tested against your query type and version. A named query is a predeclared JPQL statement; do not assume every dynamic `ORDER BY` expression can be safely appended. For fixed ordering, declare `ORDER BY` directly inside the named query.

## 14. Native named queries

JPA also supports named native queries for writing database-specific SQL instead of JPQL. They can be declared with `@NamedNativeQuery` or XML mappings.

Example:

~~~java
@NamedNativeQuery(
    name = "Employee.findByEmailAddressNative",
    query = "select * from employees where email_address = ?1",
    resultClass = Employee.class
)
~~~

Repository method:

~~~java
Optional<Employee> findByEmailAddressNative(String email);
~~~

The query name still follows the convention of domain class simple name plus method name. Native SQL uses physical table/column names such as `employees` and `email_address`; JPQL uses entity names and Java properties.

Native queries depend on the database dialect, schema, and column types. When returning an entity, required columns must map to the entity. For complex results or DTOs, `@SqlResultSetMapping` or an appropriate projection mechanism may be needed. Only use native queries when JPQL cannot express the requirement conveniently or when specific SQL features are needed; test on the real database.

## 15. Name collisions and cases to avoid

Named query names must be unique within a persistence unit. Several situations easily cause conflicts:

- Two entities sharing the same domain class simple name in different packages.
- Multiple repositories for the same domain type having a method with the same name but expecting different queries.
- An overloaded method where different signatures require different queries.
- Both annotations and orm.xml declaring the same query name.
- Renaming a method while forgetting to update the named query name.
- Renaming an entity or property in JPQL without updating the query.

Because a named query name consists only of the domain class simple name and method name, two repositories for the same domain type with the same method name will resolve to the same named query. If two different queries are needed, use distinct method names or declare explicit `@Query` annotations.

Overloaded methods also cannot produce two separate named query keys because the method name portion is identical. Use distinct method names or `@Query` when multiple different signatures are needed.

## 16. Common errors and troubleshooting

| Error | Common cause | Resolution |
|---|---|---|
| Named query not found | Wrong domain class name or method name | Verify exact Entity.method pattern |
| Method has no query and cannot be parsed | CREATE_IF_NOT_FOUND did not find named query and attempted derived query | Declare named query or rename method to a valid derived name |
| JPQL cannot find entity | Used table name or wrong @Entity(name) | Use the JPA entity name in JPQL |
| JPQL cannot find property | Used SQL column name instead of Java property | Check entity properties |
| Parameter is not bound | @Param does not match :parameter name | Align parameter names |
| Query returns too many results | Method declares entity/Optional but query is non-unique | Use List/Page or ensure uniqueness condition |
| DTO projection error | Wrong fully qualified class name or constructor signature | Verify types and order in SELECT |
| XML mapping not loaded | orm.xml in wrong location or wrong namespace/version | Place in META-INF and check JPA configuration |
| Two queries override/conflict | Duplicate name in annotations/XML | Use unique names and a single source of definition |
| Slow paginated query | Expensive count query or joins | Inspect SQL, optimize query/count and indexes |
| Native query behaves differently across environments | Database-dependent SQL | Test on the target database |

## 17. Testing named queries with @DataJpaTest

An integration test should verify that the named query is resolved properly by name and that parameters are bound accurately.

Example:

~~~java
package com.example.employee;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void resolvesNamedQueryByDomainAndMethodName() {
        repository.save(new Employee(
                "An",
                "an@example.com",
                true,
                new BigDecimal("2500.00")));

        repository.save(new Employee(
                "Binh",
                "binh@example.com",
                false,
                new BigDecimal("3000.00")));

        var result = repository.findActiveWithMinimumSalary(
                new BigDecimal("2000.00"));

        assertThat(result)
                .extracting(Employee::getEmailAddress)
                .containsExactly("an@example.com");
    }

    @Test
    void bindsNamedParameterInNamedQuery() {
        repository.save(new Employee(
                "Lan",
                "lan@example.com",
                true,
                new BigDecimal("1800.00")));

        var result = repository.findByEmailAddress("lan@example.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getName()).isEqualTo("Lan");
    }
}
~~~

The first test uses the `findActiveWithMinimumSalary` method, which has no standard derived query syntax. It proves Spring Data locates the named query `Employee.findActiveWithMinimumSalary`. The second test verifies that the named parameter `:email` is bound via `@Param`.

@DataJpaTest typically uses an embedded database if present on the classpath and wraps each test in a transaction. If a named query uses database-specific SQL functions, special types, or native queries, run additional integration tests against the actual production database engine.

## 18. Debugging workflow when repository startup fails

When the application reports an error creating a repository, check in order:

1. Get the exact repository method name.
2. Construct the named query name as `EntitySimpleName.methodName`.
3. Check whether `@NamedQuery` or `orm.xml` declares that exact name.
4. Check entity names and properties in JPQL.
5. Check `:name` parameters and `@Param("name")`.
6. If there is no named query, determine whether the method is a valid derived query.
7. Check whether `QueryLookupStrategy` is configured as `USE_DECLARED_QUERY` or `CREATE`.
8. Read the root cause in the logs, especially JPQL syntax, unknown entity/property, and parameter binding errors.

With `CREATE_IF_NOT_FOUND`, a method that fails to find a named query proceeds to the method-name parsing step. Consequently, the error message might say a property was not found on the entity even when the original intent was to use a named query. Check both the query name and the method name to identify the root cause.

## 19. Practical design principles

- Use the `EntitySimpleName.methodName` convention accurately and consistently.
- Keep named query names unique within the persistence unit.
- Use `@Param` with named parameters for explicit binding.
- Prefer JPQL when possible so queries remain less database-dependent.
- Use `@NamedQuery` for stable queries that need naming or separation from repositories.
- Use `@Query` when you want the query next to the method that uses it.
- Use derived queries for simple, readable conditions.
- Choose `USE_DECLARED_QUERY` when the project requires all queries to be declared explicitly; otherwise, keeping the default `CREATE_IF_NOT_FOUND` is usually more flexible.
- Avoid letting overloaded methods or multiple repositories for the same domain type accidentally share a query name with different meanings.
- Use DTOs for reports and APIs that only need partial data.
- Verify named queries at startup and with `@DataJpaTest`.
- For native queries, verify against the target database and manage schemas via migrations.

## 20. Self-assessment checklist

- [ ] Can explain what a named query is and why queries are named.
- [ ] Write the `EntitySimpleName.methodName` convention correctly.
- [ ] Distinguish domain class simple name from JPA entity name and table name.
- [ ] Declare multiple named queries using `@NamedQueries`.
- [ ] Define named queries in `META-INF/orm.xml`.
- [ ] Create repository methods matching named query names.
- [ ] Explain `CREATE`, `USE_DECLARED_QUERY`, and `CREATE_IF_NOT_FOUND`.
- [ ] Know that `CREATE_IF_NOT_FOUND` is the default strategy.
- [ ] Know that `@Query` on a method takes precedence over a named query.
- [ ] Bind named parameters using `@Param`.
- [ ] Choose appropriate return types: entity, Optional, List, Page, Slice, or DTO.
- [ ] Understand limitations around name collisions and method overloading.
- [ ] Distinguish JPQL named queries from native named queries.
- [ ] Test named query resolution and parameter binding.

## 21. Conclusion

The `EntitySimpleName.methodName` convention is the bridge between named queries and repository methods in Spring Data JPA. When a repository invokes a method, Spring Data can look up a declared query by that name; with `CREATE_IF_NOT_FOUND`, if none is found, the framework attempts to generate a derived query from the method name.

Understanding the lookup order helps you choose between `@NamedQuery`, `orm.xml`, `@Query`, and derived queries. Using unique names, explicit `@Param` annotations, appropriate return types, and testing against your target database keeps repositories readable, maintainable, and less prone to startup failures.