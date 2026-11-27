# Why Select Only the Data You Need Instead of Always Loading the Entity

## Objectives

When reading data with Spring Data JPA, the familiar approach is to query and receive an entity. However, many use cases only need a subset of information: a name and email to display a list, a few fields to build a report, or an aggregated value to show statistics. Loading the full entity in those cases can add unnecessary column reads, object creation, state tracking, and association loading overhead.

Spring Data JPA supports projections to query the exact shape of data a use case needs. A projection can be an interface, a DTO/record, a scalar value, or a dynamic result type. When business updates are required, a managed entity remains the appropriate choice.

After this lesson, you can:

- Distinguish between an entity query and a projection query.
- Select only the data to read instead of always loading the entity.
- Use interface projections, DTOs/records, scalar projections, and dynamic projections.
- Combine projections with JPQL, JOINs, and pagination.
- Distinguish projections from EntityGraph and fetch joins.
- Recognize when a projection does not make a query faster.
- Design read/write boundaries and test projection results.

The examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. Why Not Always Load the Entity?

A JPA entity represents a domain object mapped to persistent data. When an entity is loaded into the persistence context, the provider typically tracks its state to support dirty checking, identity management, cascading, and persistence operations.

For example:

```java
Employee employee = employeeRepository.findById(id).orElseThrow();

String name = employee.getFullName();
String email = employee.getEmail();
```

If a screen only displays the name and email, loading the entity may fetch other persistent attributes that the screen does not use. The entity might also reference `Department`, `Address`, or collections. Accessing an association afterward can trigger additional queries.

This does not mean every entity read loads the entire object graph. The JPA fetch strategy determines how associations are loaded; providers may also support lazy basic attributes in some mappings. However, entity queries are generally designed to reconstitute an entity that can participate in the persistence context, whereas projections let you directly represent the data needed for a read use case.

### 1.1. Overhead You Can Avoid

When only a few fields are needed, a projection can help reduce:

- The number of selected columns and amount of data transferred from the database.
- The number of entity objects and proxies created.
- Snapshot/dirty-checking overhead for managed entities.
- The risk of accessing lazy associations outside a transaction.
- Excess data passed to a service or API.
- The chance of accidentally serializing an entity graph or exposing unnecessary fields.

The actual improvement depends on the query, schema, indexes, database, cache, and data volume. A projection does not automatically make every query faster; you should inspect the generated SQL and measure performance.

### 1.2. Comparison Example

An entity with many attributes:

```java
@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;
    private String email;
    private String phone;
    private String address;
    private boolean active;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    // Constructors, getters, and domain methods.
}
```

If a list screen only needs the ID, name, and email, you can use a dedicated result type instead of returning `Employee`:

```java
public record EmployeeListItem(
        Long id,
        String fullName,
        String email
) {
}
```

The projection query specifies only the required fields. The service receives data already shaped for the screen and does not need to convert the entire entity.

## 2. How Entity Queries and Projection Queries Differ

| Criterion | Entity query | Projection query |
|---|---|---|
| Result | Entity mapped by JPA | Interface, DTO, record, scalar, or other type |
| Persistence context | Entity is managed when loaded in the context | Plain DTOs/scalars are not managed |
| Dirty checking | Yes, for managed entities | No, for DTOs/scalars |
| Data read | Follows the entity mapping and fetch plan | Can select only the required attributes |
| Suitable purpose | Business flows that read and then modify an entity | Lists, reports, searches, read-only screens |
| Associations | Can use proxies/fetch plan | Selects only the values or associations needed for the result |
| Lifecycle constraints | Follows the entity lifecycle | No entity lifecycle for plain DTOs |

Entities and projections solve two different problems. If you need to invoke domain methods, enforce invariants, or update state, load a managed entity. If you only need to read data for presentation or calculation, a projection is usually a better fit.

Do not treat a projection as a lightweight entity version for updates. A DTO containing an ID and a few fields does not automatically have dirty checking or optimistic locking like a managed entity.

## 3. Interface Projections

An interface projection is a simple way to declare getters corresponding to the attributes you want to read.

### 3.1. Closed Projections

Declare the interface:

```java
public interface EmployeeSummary {
    Long getId();
    String getFullName();
    String getEmail();
}
```

Repository:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    List<EmployeeSummary> findByActiveTrue();
}
```

Spring Data recognizes the getters corresponding to the attributes of `Employee` and creates projections for the results. This is a closed projection because the required attributes are determined from the interface.

Closed projections can allow Spring Data to optimize the query to fetch only the requested attributes. However, the exact optimization depends on the projection type, query, and provider. Check the actual SQL if column count or performance is a critical requirement.

Calling the repository:

```java
List<EmployeeSummary> employees = repository.findByActiveTrue();

for (EmployeeSummary employee : employees) {
    System.out.println(employee.getFullName());
}
```

Projection interfaces are typically implemented using proxies. Callers use the getters without needing to know the underlying object creation mechanism.

### 3.2. Projections with Associations

You can declare nested projections:

```java
public interface EmployeeWithDepartment {
    Long getId();
    String getFullName();
    DepartmentView getDepartment();

    interface DepartmentView {
        String getName();
    }
}
```

Nested projections are convenient for structured data, but be careful: accessing a nested property may require a JOIN or partially materialize the association depending on how the provider/Spring Data handles it. Do not assume a nested projection always selects only a single column from the related table.

If you need exact control over the SQL and selected columns, a DTO projection with a JPQL constructor expression is usually clearer.

### 3.3. Open Projections

An open projection uses a SpEL expression to compute a value from the target entity:

```java
public interface EmployeeLabel {
    @Value("#{target.fullName + ' <' + target.email + '>'}")
    String getLabel();
}
```

Because the expression can access multiple attributes of the target, Spring Data cannot easily infer the exact minimal set of columns to load. Therefore, open projections can lose part of the optimization benefit of closed projections.

Use open projections when the expression is genuinely convenient and simple. If presentation logic is complex, a DTO/service mapper is usually easier to test and control.

## 4. DTO and Record Projections

A DTO projection creates a dedicated object containing only the data to return. This is a clear choice for API responses, reports, or search results.

### 4.1. Record Projections

Java records are well suited for immutable DTOs:

```java
package com.example.demo.employee;

public record EmployeeListItem(
        Long id,
        String fullName,
        String email
) {
}
```

Spring Data JPA supports class-based projections via a matching constructor. A record has a canonical constructor, which is usually convenient for this case.

A repository can use a derived query:

```java
List<EmployeeListItem> findByActiveTrue();
```

Spring Data needs to determine the constructor and matching properties. If a DTO has multiple constructors, you may need to mark the constructor to use with `@PersistenceCreator` according to Spring Data's rules.

### 4.2. JPQL Constructor Expressions

For custom queries, use `select new`:

```java
@Query("""
       select new com.example.demo.employee.EmployeeListItem(
           e.id,
           e.fullName,
           e.email
       )
       from Employee e
       where e.active = true
       order by e.fullName
       """)
List<EmployeeListItem> findActiveListItems();
```

A JPQL constructor expression requires the fully qualified class name of the DTO. The order and types of the expressions must match the constructor.

Traditional DTO class example:

```java
public class EmployeeListItem {

    private final Long id;
    private final String fullName;
    private final String email;

    public EmployeeListItem(
            Long id,
            String fullName,
            String email
    ) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
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
}
```

Do not put `@Entity` on a DTO just because it is returned from a repository. A DTO is not an entity and does not need table mapping.

### 4.3. Projections with JOINs

A DTO projection can select fields from multiple entities in a single query:

```java
public record EmployeeDepartmentRow(
        Long employeeId,
        String employeeName,
        String departmentName
) {
}
```

```java
@Query("""
       select new com.example.demo.employee.EmployeeDepartmentRow(
           e.id,
           e.fullName,
           d.name
       )
       from Employee e
       join e.department d
       where e.active = true
       """)
List<EmployeeDepartmentRow> findActiveEmployeeDepartmentRows();
```

The query returns only the needed values. There is no need to instantiate the entire `Department` object or pass the entity graph to the API layer just to display the department name.

If the association is optional and you still want to keep `Employee` records without a `Department`, use `left join` instead of `join`; in that case, `departmentName` in the record must accept null.

## 5. Scalar and Aggregate Projections

If you only need a single value, there is no need to create a DTO or load an entity.

Example fetching an email:

```java
@Query("""
       select e.email
       from Employee e
       where e.id = :id
       """)
Optional<String> findEmailById(@Param("id") Long id);
```

Example counting active employees:

```java
@Query("""
       select count(e)
       from Employee e
       where e.active = true
       """)
long countActiveEmployees();
```

Example calculating totals by department:

```java
@Query("""
       select d.id, d.name, count(e)
       from Employee e
       join e.department d
       where e.active = true
       group by d.id, d.name
       order by count(e) desc
       """)
List<Object[]> countActiveEmployeesByDepartment();
```

`Object[]` results require casting by column order and can be hard to maintain. For long-lived queries, create a DTO:

```java
public record DepartmentEmployeeCount(
        Long departmentId,
        String departmentName,
        Long employeeCount
) {
}
```

```java
@Query("""
       select new com.example.demo.employee.DepartmentEmployeeCount(
           d.id,
           d.name,
           count(e)
       )
       from Employee e
       join e.department d
       where e.active = true
       group by d.id, d.name
       order by count(e) desc
       """)
List<DepartmentEmployeeCount> countByDepartment();
```

Aggregate queries let the database perform the computation and return only the aggregated results, instead of loading every entity into Java and counting manually.

## 6. Dynamic Projections

Sometimes the same search criteria are used, but callers need different result shapes. Spring Data supports dynamic projections through a `Class` parameter:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    <T> List<T> findByActiveTrue(Class<T> type);
}
```

The caller chooses the result type:

```java
List<EmployeeSummary> summaries =
        repository.findByActiveTrue(EmployeeSummary.class);

List<EmployeeListItem> items =
        repository.findByActiveTrue(EmployeeListItem.class);

List<Employee> entities =
        repository.findByActiveTrue(Employee.class);
```

Dynamic projections help reuse query criteria while allowing callers to select an entity or an appropriate projection. Avoid overusing them if different use cases have different fetch, join, authorization, or filtering requirements; in those cases, separate repository methods are usually easier to understand.

Spring Data recognizes a `Class` parameter as a dynamic projection when its generic type matches the return type. If you need to pass a `Class` object as an ordinary query parameter, use a different declared type so it is not mistaken for a dynamic projection parameter.

## 7. Selecting Only Needed Data from Associations

Projections are especially useful when display data comes from multiple tables but only a few fields are required.

For example, an order list needs the order number, creation date, customer name, and total amount. It is not necessary to load `Order`, `Customer`, and the entire `OrderLine` collection.

```java
public record OrderListItem(
        Long id,
        String orderNumber,
        Instant createdAt,
        String customerName,
        BigDecimal total
) {
}
```

```java
@Query("""
       select new com.example.demo.order.OrderListItem(
           o.id,
           o.orderNumber,
           o.createdAt,
           c.name,
           o.total
       )
       from Order o
       join o.customer c
       where o.status = :status
       order by o.createdAt desc
       """)
List<OrderListItem> findOrderList(
        @Param("status") OrderStatus status
);
```

The query returns flat data for the list. If you need to sum values from `OrderLine`, you can use an aggregate query or subquery depending on the model; avoid loading the entire collection just to sum values in Java.

Projections do not replace fetch plans in all cases. If a use case needs to operate on the entity graph or invoke domain methods, load the entity and use `@EntityGraph` or a fetch join to control which associations are loaded.

## 8. Projections and Pagination

Projections can be combined with `Pageable` to read data page by page:

```java
@Query("""
       select new com.example.demo.employee.EmployeeListItem(
           e.id,
           e.fullName,
           e.email
       )
       from Employee e
       where e.active = true
       """)
Page<EmployeeListItem> findActiveItems(Pageable pageable);
```

Calling the repository:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "fullName")
);

Page<EmployeeListItem> page =
        repository.findActiveItems(pageable);
```

With JPQL DTO projections, Spring Data can derive a count query for simple queries. For complex queries with JOINs or GROUP BY, declare an explicit `countQuery` and make sure it counts the logical number of elements accurately.

```java
@Query(
    value = """
            select new com.example.demo.employee.EmployeeListItem(
                e.id, e.fullName, e.email
            )
            from Employee e
            where e.department.id = :departmentId
            """,
    countQuery = """
            select count(e)
            from Employee e
            where e.department.id = :departmentId
            """
)
Page<EmployeeListItem> findItemsByDepartment(
        @Param("departmentId") Long departmentId,
        Pageable pageable
);
```

Distinguish between:

- `Page<T>`: includes total element/page metadata; may require a count query.
- `Slice<T>`: indicates whether a next page exists, without requiring the total element count.
- `List<T>` with `Pageable`: retrieves a bounded slice of content, without page metadata.

If the UI only needs a "Load more" button, `Slice` can avoid the cost of counting. For very large datasets and deep pagination, consider keyset/scrolling pagination supported by your Spring Data version instead of a large `OFFSET`.

## 9. Projections Are Not EntityGraph or Fetch Joins

These three techniques serve different purposes:

| Technique | What does it control? | Result |
|---|---|---|
| Projection | The shape of returned data | DTO/interface/scalar or projection type |
| EntityGraph | Which associations should be loaded | Entity |
| JOIN FETCH | Loads an association within the query | Entity |
| DTO constructor query | Specific expressions/columns selected | DTO |

If a use case needs an entity for updates and wants to load `Department` at the same time, `EntityGraph` or a fetch join is appropriate:

```java
@EntityGraph(attributePaths = "department")
Optional<Employee> findById(Long id);
```

If a use case only needs the employee name and department name, a DTO projection may be clearer:

```java
@Query("""
       select new com.example.demo.employee.EmployeeDepartmentRow(
           e.id, e.fullName, d.name
       )
       from Employee e
       join e.department d
       where e.id = :id
       """)
Optional<EmployeeDepartmentRow> findRowById(Long id);
```

A fetch join is not a projection. It changes the entity's fetch plan; a projection changes the returned data type.

## 10. When Should You Still Load the Entity?

Projections are not the default choice for every query. Load a managed entity when:

- The business logic needs to modify entity state.
- You need to call domain methods and enforce invariants.
- Cascading or lifecycle callbacks are required.
- Optimistic locking via `@Version` is needed.
- You need to work with associations as part of the domain model.
- You need to save a new entity or update an existing entity according to JPA rules.

Example of updating state:

```java
@Transactional
public void deactivateEmployee(Long id) {
    Employee employee = repository.findById(id)
            .orElseThrow();

    employee.deactivate();
}
```

Because the entity is managed, changes are dirty-checked on flush. Using a projection containing only the ID and active flag to perform updates will not automatically provide managed entity behavior.

If you only need to update a few columns without domain lifecycle logic, a JPQL bulk update may be suitable, though you must handle the persistence context and optimistic locking separately. That is a different choice from a read projection.

## 11. Do Not Use Entities as Default API Responses

Returning entities directly from a REST controller can cause several issues:

- The API becomes coupled to the persistence/domain model structure.
- Adding an entity attribute can unintentionally change the JSON contract.
- Lazy associations can trigger queries outside a transaction.
- Bidirectional relationships can cause serialization loops.
- Internal fields or data not meant for clients can be exposed.
- Entities can contain proxies or state unsuitable for serialization.

A DTO projection or a DTO mapped in the service ensures the API exposes only the required fields:

```java
public record EmployeeResponse(
        Long id,
        String fullName,
        String email
) {
}
```

Controller:

```java
@RestController
@RequestMapping("/employees")
public class EmployeeController {

    private final EmployeeQueryService queryService;

    public EmployeeController(EmployeeQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping
    public List<EmployeeResponse> list() {
        return queryService.findActiveEmployees();
    }
}
```

A DTO does not replace authorization. The service must still verify access permissions and select only the data the caller is allowed to see.

## 12. Limitations and Trade-Offs to Consider

Projections can reduce transferred data and objects, but they also come with trade-offs:

**More complex queries.** DTO queries may require constructor expressions, JOINs, and count queries. When logic changes, the query must be updated alongside the DTO.

**Nested projections are harder to predict.** Nested interface projections can generate JOINs and load more data than expected. Inspect the actual SQL.

**No dirty checking.** DTOs cannot replace entities in update workflows.

**Constructor mapping is sensitive to order and types.** JPQL constructor expressions must match the constructor exactly.

**Projections do not automatically solve N+1 in all cases.** If a query fetches entities and code accesses lazy associations in a loop, N+1 can still occur. Choose the right projection or fetch plan.

**Native queries depend on schema.** Native projections require accurate column aliases and compatible data types. With DTO classes, mapping native results may require constructor mapping or a dedicated mapping mechanism depending on the query/provider.

**Fewer columns does not always mean a faster query.** Indexes, cardinality, sorting, joins, caching, and execution plans remain critical factors. Measure queries with production-like data.

## 13. Testing Projections

Use `@DataJpaTest` to verify that a query returns the right type and values:

```java
@DataJpaTest
class EmployeeProjectionRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Test
    void returnsOnlyEmployeeSummaryFields() {
        repository.save(new Employee(
                "An Nguyen",
                "an@example.com",
                true
        ));

        List<EmployeeSummary> result =
                repository.findByActiveTrue();

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getFullName()).isEqualTo("An Nguyen");
        assertThat(result.get(0).getEmail()).isEqualTo("an@example.com");
    }
}
```

This test assumes `Employee` has a matching constructor and the repository declares the interface projection as shown in the earlier examples. `@DataJpaTest` typically runs inside a transaction and rolls back after the test.

For DTO constructor queries, verify:

- Element count and result order.
- Each value maps to the right constructor argument.
- Numeric/date/enum types are compatible.
- Optional associations produce null values as expected.
- Page content and count query are consistent.
- Dynamic projections return the requested type.

To verify performance benefits, enable SQL logging or use datasource/query metrics to confirm the column count, query count, and data volume. Test assertions alone do not prove a query is optimized.

## 14. Examples of Choosing a Strategy by Use Case

| Use case | Suitable choice | Reason |
|---|---|---|
| Open a detail page to edit an Employee | Entity | Needs domain behavior and dirty checking |
| Employee list showing only name/email | Interface or DTO projection | Only a few attributes are needed |
| Report of total employees by department | Aggregate DTO projection | Database performs GROUP BY/COUNT |
| API returning a few public fields | DTO projection | Controls the JSON contract |
| Need entity with Department already loaded | EntityGraph/fetch join | Needs to work with the entity graph |
| Caller-selected result type | Dynamic projection | Reuses query conditions |
| Load full data for domain processing | Entity | Needs entity state and behavior |

Practical rule: start from the data the use case needs and the action it performs. If it only reads, choose a lean projection. If it needs to mutate domain objects, load a managed entity. If it needs entity associations, control the fetch plan separately.

## 15. Common Pitfalls

| Symptom | Cause | How to fix |
|---|---|---|
| Projection returns null for a getter | Getter/property name or alias mismatch | Match the Java property name and query alias |
| DTO query fails on constructor | Wrong FQCN, parameter order, or parameter types | Check the constructor or record canonical constructor |
| Interface projection loads too much data | Open projection or nested path hard to optimize | Use a closed projection or explicit DTO query |
| Cannot update from a projection | Projection is not a managed entity | Load the entity in a transaction to update it |
| Page has wrong total count | Count query does not match the projection query | Declare an accurate `countQuery` |
| N+1 still occurs | Accessing lazy associations outside the projection query | Use a DTO join or appropriate fetch plan |
| JSON fails with lazy loading error | Returning an entity/proxy directly from the service | Map to a DTO inside the transaction |
| Native projection does not map | Column alias or type mismatch | Set correct aliases and test on the target database |
| Query is not faster | Bottleneck is in JOINs/indexes/sorting/database | Measure SQL and execution plans instead of guessing |

## 16. Checklist for Selecting Only the Data to Read

- [ ] Identify the exact fields required by the screen or use case.
- [ ] Load a managed entity if domain behavior or updates are needed.
- [ ] Consider an interface, DTO/record, or scalar projection for read-only flows.
- [ ] Use closed interface projections when the structure is simple.
- [ ] Use DTO constructor queries when JOINs or explicit column control are needed.
- [ ] Use aggregate queries when the database can compute results instead of the application.
- [ ] Use dynamic projections when multiple callers genuinely need different result types.
- [ ] Paginate and declare a count query when necessary.
- [ ] Do not confuse projections with `EntityGraph`/fetch joins.
- [ ] Check generated SQL, N+1 queries, indexes, and execution plans.
- [ ] Return DTOs from APIs and enforce authorization.
- [ ] Test mappings, nulls, pagination, and queries on the actual provider/database.

## Conclusion

Not every use case needs a full entity. Entities fit when business logic needs managed state, dirty checking, domain methods, and lifecycle behavior. Projections fit when a use case mainly reads a specific set of fields or aggregated values.

Spring Data JPA provides interface projections, DTO/record projections, scalar results, and dynamic projections. Start from the data needed, choose a query returning that exact shape, and inspect the actual SQL. When updates are required, switch to a managed entity; when associations must be loaded, use `EntityGraph` or a fetch join for that use case. This approach reduces unnecessary data transfer, keeps APIs clear, and makes repositories easier to maintain.
