# Mapping Many-to-One with @ManyToOne and @JoinColumn

## Objectives

In a relational model, a row in one table can reference a row in another table. A many-to-one relationship describes the case where multiple source entities reference the same target entity. For example, many employees belong to the same department, many orders belong to the same customer, or many comments belong to the same post.

In JPA, we use `@ManyToOne` to declare the relationship and `@JoinColumn` to describe the foreign key column on the table of the entity that owns the relationship.

After this lesson, you will be able to:

- Understand the meaning of many-to-one and foreign key placement.
- Map relationships using `@ManyToOne` and `@JoinColumn`.
- Distinguish between unidirectional and bidirectional relationships, owning side and inverse side.
- Choose appropriate values for `fetch`, `optional`, `nullable`, and cascade.
- Load relationships efficiently, avoiding N+1 queries and lazy loading errors.
- Test mappings and troubleshoot common errors.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. What Is a Many-to-One Relationship?

Suppose a department has many employees, while each employee belongs to one department:

- One `Department` can be associated with many `Employee` records.
- Each `Employee` references one `Department`.

In the database, the foreign key is typically placed on the many-side table:

<box>
  <text weight="semibold">Relationship Diagram</text>
  <box border radius="lg" padding={3} gap={2}>
    <row align="center" justify="between">
      **departments**
      <badge color="info">Parent table</badge>
    </row>
    `id (PK)`
    `name`
    <divider color="subtle"/>
    <row align="center" justify="between">
      **employees**
      <badge color="success">Many-side table</badge>
    </row>
    `id (PK)`
    `full_name`
    `department_id (FK)`
    <caption color="secondary">Multiple employees rows can hold the same department_id.</caption>
  </box>
</box>

Sample data:

| departments.id | departments.name |
|---:|---|
| 10 | Engineering |
| 20 | Finance |

| employees.id | employees.full_name | employees.department_id |
|---:|---|---:|
| 101 | An | 10 |
| 102 | Bình | 10 |
| 103 | Chi | 20 |
| 104 | Dũng | 10 |

Three employees—An, Bình, and Dũng—reference the department with ID 10. This is a many-to-one relationship viewed from the Employee side.

In JPA, the relationship is declared on the many-side entity. Each Employee has a Department property; the database stores the Department's ID in a foreign key column in the `employees` table.

## 2. @ManyToOne and @JoinColumn

The two annotations have distinct responsibilities:

- `@ManyToOne`: declares an entity property that references another entity in a many-to-one relationship.
- `@JoinColumn`: describes the join column, typically the foreign key column on the table of the entity owning the relationship.

Example:

```java
@ManyToOne
@JoinColumn(name = "department_id")
private Department department;
```

Here:

- `Employee` is the source entity, the many side.
- `Department` is the referenced entity, the one side.
- `department` is the relationship property in Java.
- `department_id` is the foreign key column name in the `employees` table.

The Java property name and the database column name can differ. In Java code, we use `employee.getDepartment()`; in SQL, the database stores the foreign key in `employees.department_id`.

### 2.1. Attributes of @ManyToOne

Some key attributes:

| Attribute | Default | Meaning |
|---|---|---|
| `targetEntity` | Inferred from property type | Specifies the target entity when the type cannot be inferred |
| `cascade` | No cascade | Which operations propagate to the target entity |
| `fetch` | `EAGER` | Strategy for loading the relationship |
| `optional` | `true` | Whether the relationship is allowed to have no target entity |

`@ManyToOne` defaults to `EAGER` fetching. This means the provider must ensure the relationship is loaded when the source entity is accessed per the JPA contract; the provider may execute a join or additional queries.

For applications that typically need control over relationship loading, it is often better to declare explicitly:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

`LAZY` asks the provider to defer loading the target entity until needed. However, for `@ManyToOne`, `LAZY` is a JPA fetch hint; the provider may not be able to defer loading in every case. Hibernate typically supports proxies/lazy loading when the mapping and class are suitable.

### 2.2. Attributes of @JoinColumn

| Attribute | Meaning |
|---|---|
| `name` | Name of the join/foreign key column in the owning entity's table |
| `referencedColumnName` | Name of the column in the referenced entity's table; defaults to the primary key column |
| `nullable` | Whether the column allows null in the generated schema |
| `unique` | Requests a unique constraint on the column during schema generation |
| `insertable` | Whether the column participates in provider-generated INSERT statements |
| `updatable` | Whether the column participates in provider-generated UPDATE statements |
| `foreignKey` | Allows specifying the name and properties of the foreign key constraint |

Example:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "department_id",
    referencedColumnName = "id",
    nullable = false,
    foreignKey = @ForeignKey(name = "fk_employee_department")
)
private Department department;
```

In this example:

- `name = "department_id"`: the foreign key column in the `employees` table.
- `referencedColumnName = "id"`: references the ID column of `departments`.
- `nullable = false`: the column cannot be null in the generated schema.
- `optional = false`: at the object model level, an Employee must have a Department.
- `foreignKey`: names the constraint to keep the schema readable and manageable.

`referencedColumnName` is usually omitted because it defaults to the primary key. If referencing another column, that column must have appropriate uniqueness to serve as a foreign key target and must be supported by the database. Prefer referencing the primary key unless there is a specific requirement.

Do not declare `@Column` on the same property mapped with `@ManyToOne`; join column settings are configured using `@JoinColumn`.

## 3. Complete Example: Employee and Department

### 3.1. Department Entity

```java
package com.example.demo.department;

import jakarta.persistence.*;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String name;

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

    public void setName(String name) {
        this.name = name;
    }
}
```

### 3.2. Employee Entity with Many-to-One Relationship

```java
package com.example.demo.employee;

import com.example.demo.department.Department;
import jakarta.persistence.*;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "department_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_employee_department")
    )
    private Department department;

    protected Employee() {
    }

    public Employee(String fullName, Department department) {
        this.fullName = fullName;
        this.department = department;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public Department getDepartment() {
        return department;
    }

    public void setDepartment(Department department) {
        this.department = department;
    }
}
```

The `Employee` entity owns the relationship. Hibernate maps the ID value of `department` to the `department_id` column of the `employees` table.

### 3.3. Repositories

```java
package com.example.demo.department;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DepartmentRepository
        extends JpaRepository<Department, Long> {
}
```

```java
package com.example.demo.employee;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    List<Employee> findByDepartmentId(Long departmentId);
}
```

Spring Data parses `findByDepartmentId` into the property path `department.id`. The database column name does not participate in the derived query method name; the method uses the entity's Java property name.

### 3.4. Persisting Data in the Service

```java
@Service
public class EmployeeService {

    private final DepartmentRepository departmentRepository;
    private final EmployeeRepository employeeRepository;

    public EmployeeService(
            DepartmentRepository departmentRepository,
            EmployeeRepository employeeRepository
    ) {
        this.departmentRepository = departmentRepository;
        this.employeeRepository = employeeRepository;
    }

    @Transactional
    public Employee addEmployee(Long departmentId, String fullName) {
        Department department = departmentRepository.findById(departmentId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Department not found")
                );

        Employee employee = new Employee(fullName, department);
        return employeeRepository.save(employee);
    }
}
```

The service loads the existing Department and assigns it to the Employee. This is the clear approach when the Department already exists. Within the transaction, the Department entity is managed by the persistence context; Hibernate can use its foreign key when inserting the Employee.

There is no need to cascade persist from Employee to Department in this case. The Department already exists and is loaded from the repository.

## 4. Unidirectional and Bidirectional Relationships

### 4.1. Unidirectional Many-to-One

In the previous example, only Employee has a Department property. From Employee, you can access the department:

```java
Employee employee = employeeRepository.findById(101L).orElseThrow();
String departmentName = employee.getDepartment().getName();
```

From Department, there is no list of Employees. This is a unidirectional relationship.

Advantages:

- Simple mapping.
- Lower risk of circular references during JSON serialization.
- No need to maintain a bidirectional collection.
- Suitable when business logic mainly navigates from the many-side entity to the one-side entity.

If you do not need to access employees from Department, unidirectional is usually sufficient.

### 4.2. Bidirectional Many-to-One

If you need to retrieve the list of employees from Department, you can add `@OneToMany` on the Department side:

```java
@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @OneToMany(mappedBy = "department")
    private List<Employee> employees = new ArrayList<>();

    protected Department() {
    }

    public Department(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public List<Employee> getEmployees() {
        return employees;
    }

    public void addEmployee(Employee employee) {
        employees.add(employee);
        employee.setDepartment(this);
    }

    public void removeEmployee(Employee employee) {
        employees.remove(employee);
        employee.setDepartment(null);
    }
}
```

In a bidirectional relationship:

- `Employee.department` is the owning side because it contains `@JoinColumn` and controls the foreign key value.
- `Department.employees` is the inverse side, declared with `mappedBy = "department"`.
- `mappedBy` must point to the Java property name on the entity owning the relationship, not the database column name.

When adding an employee, the owning side must be updated:

```java
department.addEmployee(employee);
```

Adding only to the `department.getEmployees()` collection without updating `employee.setDepartment(department)` will not guarantee the foreign key is written properly. JPA relies on the owning side to synchronize the relationship to the database.

### 4.3. Helper Methods to Maintain Both Sides

With bidirectional relationships, encapsulate add/remove operations in helper methods to keep the object graph consistent.

If an Employee is transferred from an old department to a new department, the helper can update both collections:

```java
public void addEmployee(Employee employee) {
    if (employee.getDepartment() != null) {
        employee.getDepartment().getEmployees().remove(employee);
    }

    employees.add(employee);
    employee.setDepartment(this);
}
```

This snippet illustrates the idea of synchronizing both sides; in a real application, ensure the collection avoids duplicates, handles nulls, and uses consistent entity comparison (ID, `equals`/`hashCode`). Do not implement `equals`/`hashCode` based on mutable fields or bidirectional relationships, as this can cause cycles and break collections.

If the old Department is not loaded or its collection is uninitialized, design the transfer method to fit the entity state and persistence context. A service can load both sides and perform the operation within a transaction.

## 5. optional, nullable, and Database Constraints

These two attributes are often used together:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
```

They are related but not completely synonymous:

- `optional = false` describes the relationship in the JPA model: an Employee must reference a Department.
- `nullable = false` describes the nullability of the join column when the provider generates the schema.

If the relationship is mandatory, reflect it consistently in both the mapping and the database. The database needs NOT NULL and a foreign key to protect data even against operations outside the application.

If the relationship is allowed to be empty:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "department_id", nullable = true)
private Department department;
```

These attributes can be omitted since they are the defaults, but declaring them explicitly helps readers understand the rule. If `department` is null, the `department_id` column in `employees` can be null.

`optional = false` does not automatically create a Department object. When creating an Employee, the application must assign a valid Department. A database foreign key still needs to be configured to prevent non-existent IDs.

## 6. Cascade: Should You Cascade from Employee to Department?

By default, `@ManyToOne` does not cascade any operations. This means saving an Employee will not automatically persist a new Department unless cascade is declared.

You can declare:

```java
@ManyToOne(cascade = CascadeType.PERSIST)
@JoinColumn(name = "department_id")
private Department department;
```

However, consider this carefully. A Department can be shared by many Employees. Cascading from Employee to Department may cause an Employee save operation to also save a Department, even though Department has its own lifecycle.

In particular, avoid mechanically placing `CascadeType.REMOVE` or `CascadeType.ALL` on `@ManyToOne`. Deleting one Employee should not accidentally delete a Department still referenced by other employees.

Practical rules:

- Existing Department: load the Department and assign it to the Employee; no cascade persist needed.
- Separately created Department: save the Department first, then assign it to the Employee.
- Only cascade when the target entity truly belongs to the source entity's lifecycle and that behavior fits the business domain.
- Cascade does not replace foreign keys, transactions, or business authorization checks.

In a model where Department has many Employees, if you need to delete an Employee when removing it from the collection, `orphanRemoval` can be considered on the `@OneToMany` relationship on the Department side. This is a child lifecycle rule; it is not an attribute of `@ManyToOne` and should only be used when Employee is truly lifecycle-owned by Department.

## 7. Fetch Strategy and the N+1 Problem

`@ManyToOne` defaults to `FetchType.EAGER`. An EAGER relationship must be loaded when the source entity is accessed per the JPA contract; the provider may use a JOIN or separate queries. Therefore, EAGER does not guarantee a single SQL query.

`FetchType.LAZY` allows deferring relationship loading:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

In Hibernate, LAZY is typically implemented using proxies. When code accesses `employee.getDepartment().getName()`, Hibernate can emit a query to load the Department.

### N+1 Queries

Example:

```java
List<Employee> employees = employeeRepository.findAll();

for (Employee employee : employees) {
    System.out.println(employee.getDepartment().getName());
}
```

If the list has N employees and each Department is not yet loaded, accessing the relationship can trigger many additional queries. The result can be one query loading employees plus additional queries loading departments: the N+1 problem.

The actual query count depends on caching, batching, the provider, and how the data is accessed; however, loops accessing lazy relationships are where you should inspect.

### 7.1. Using JOIN FETCH

When a use case is known to need the Department, you can load the relationship in the same query:

```java
@Query("""
       select e
       from Employee e
       join fetch e.department
       where e.id = :id
       """)
Optional<Employee> findByIdWithDepartment(@Param("id") Long id);
```

This is JPQL; `Employee` and `department` are the Java entity/property names. `join fetch` loads the association in the same query.

### 7.2. Using EntityGraph

You can specify the association to load with `@EntityGraph`:

```java
@EntityGraph(attributePaths = "department")
Optional<Employee> findByFullName(String fullName);
```

EntityGraph allows choosing a fetch plan per query method without changing the default fetch type of the mapping.

Do not switch all relationships to EAGER to avoid lazy loading. Doing so can cause queries that do not need the association to load unnecessary data. Identify the data needed for each use case and use fetch joins, entity graphs, or DTOs accordingly.

## 8. Lazy Loading, Transactions, and DTOs

When a LAZY relationship has not been loaded, accessing it after the persistence context closes can cause a `LazyInitializationException` in Hibernate.

Risky example:

```java
public Employee getEmployee(Long id) {
    return employeeRepository.findById(id).orElseThrow();
}

// Elsewhere, after the session is closed:
String name = employee.getDepartment().getName();
```

A better approach is to load the necessary data within the transaction and map it to a DTO before returning from the service:

```java
public record EmployeeResponse(
        Long id,
        String fullName,
        String departmentName
) {
}
```

```java
@Transactional(readOnly = true)
public EmployeeResponse getEmployee(Long id) {
    Employee employee = employeeRepository.findByIdWithDepartment(id)
            .orElseThrow();

    return new EmployeeResponse(
            employee.getId(),
            employee.getFullName(),
            employee.getDepartment().getName()
    );
}
```

The DTO contains the exact data the use case needs and does not depend on Hibernate proxies. This approach also avoids accidentally serializing the entire entity graph.

If entities are returned directly over REST, bidirectional relationships can cause JSON loops: Employee contains Department, Department contains Employees, and each Employee references Department. DTOs are a clear way to control the payload. JSON annotations such as `@JsonIgnore` can resolve some cases, but they do not replace DTO-based API design.

## 9. Testing Many-to-One Relationships

You should test both the mapping and database behavior:

- Save a Department.
- Save an Employee with an existing Department.
- Flush and clear the persistence context to ensure data is read back from the database.
- Load the Employee and verify the correct Department.
- Test the null Department case if the relationship is optional.
- Test NOT NULL/foreign key enforcement if the relationship is mandatory.
- Test fetch join/entity graph queries when a use case needs the Department.

Example using `@DataJpaTest`:

```java
@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private EmployeeRepository employeeRepository;

    @Autowired
    private DepartmentRepository departmentRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void storesManyToOneForeignKey() {
        Department department =
                departmentRepository.save(new Department("Engineering"));

        Employee employee =
                employeeRepository.save(new Employee("An", department));

        entityManager.flush();
        entityManager.clear();

        Employee loaded =
                employeeRepository.findByIdWithDepartment(employee.getId())
                        .orElseThrow();

        assertThat(loaded.getDepartment().getName())
                .isEqualTo("Engineering");
    }
}
```

The test assumes JUnit 5, AssertJ, Spring Boot Test imports, and the corresponding entities/repositories. `TestEntityManager` is available in Spring Boot's JPA test slice. `flush()` pushes changes to the database; `clear()` empties the persistence context so the next read does not merely retrieve the managed entity from memory.

If you rely on PostgreSQL-specific behavior or need to verify constraints against the production database, run integration tests with PostgreSQL/Testcontainers. Embedded databases may differ in data types and constraint behavior.

## 10. Common Errors

| Symptom | Cause | Solution |
|---|---|---|
| Entity requires Department but department is null | Association not assigned before saving | Load Department and assign it to Employee |
| Foreign key constraint violation | `department_id` references a non-existent ID | Check IDs, transactions, and save order |
| `department_id` column not created with expected name | `@JoinColumn` missing/wrong `name` or unexpected naming strategy | Specify `name` explicitly and check migrations/schema |
| `LazyInitializationException` | Accessing lazy relationship outside persistence context | Load within transaction using fetch join/entity graph and DTO |
| N+1 queries | Accessing lazy relationship inside a loop | Choose a fetch plan suited to the use case |
| Deleting Employee deletes Department | Inappropriate `CascadeType.REMOVE`/`ALL` | Remove cascade remove from the many-to-one side |
| Department collection does not reflect new Employee | Only updated the inverse side | Update the owning side `Employee.department` |
| Infinite JSON loop | Serializing bidirectional relationship directly | Return a DTO with a clear structure |
| Cannot create schema due to FK | Entity/table/column mapping or migrations out of sync | Check table names, join columns, and migration order |

## 11. @ManyToOne Design Checklist

- [ ] Identify the many-side entity and the one-side entity.
- [ ] Place `@ManyToOne` on the many-side entity.
- [ ] Place `@JoinColumn` to describe the foreign key on the many-side table.
- [ ] Choose `optional` and `nullable` consistently with business rules and schema.
- [ ] Consider declaring `fetch = FetchType.LAZY` and loading the association per use case.
- [ ] Do not cascade REMOVE from child to shared parent.
- [ ] If bidirectional, update the owning side and synchronize both sides with helper methods.
- [ ] Check for N+1 queries, lazy loading issues, and entity serialization.
- [ ] Use DTOs to control API response payloads.
- [ ] Test foreign keys, nullability, fetch queries, and transactions.

## Conclusion

`@ManyToOne` describes the relationship from the many-side entity to the one-side entity; `@JoinColumn` specifies the foreign key column in the table of the entity owning the relationship. In a bidirectional model, the `@ManyToOne` property is the owning side and determines the foreign key value written to the database.

Good design starts with placing the foreign key properly, choosing an appropriate fetch strategy, controlling cascade behavior, and maintaining the owning side. Load data according to each use case's needs, use transactions and DTOs appropriately, and test mappings against an appropriate database. These principles keep entity relationships clear, efficient, and less error-prone as the application grows.