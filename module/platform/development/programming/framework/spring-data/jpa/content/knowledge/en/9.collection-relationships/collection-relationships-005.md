# Many-to-One Mapping with @ManyToOne and @JoinColumn

## Objectives

In the relational model, a row in one table can reference a row in another table. A many-to-one relationship describes the case where multiple source entities reference a single target entity. For example, many employees belong to the same department, many orders belong to the same customer, or many comments belong to the same post.

In JPA, we use `@ManyToOne` to declare the relationship and `@JoinColumn` to describe the foreign key column in the table of the entity that owns the relationship.

After this lesson, you will be able to:

- Understand the meaning of many-to-one and foreign key placement.
- Map relationships using `@ManyToOne` and `@JoinColumn`.
- Distinguish between unidirectional and bidirectional relationships, and owning side vs. inverse side.
- Choose appropriate values for `fetch`, `optional`, `nullable`, and cascade.
- Load relationships efficiently while avoiding N+1 queries and lazy loading errors.
- Test mappings and troubleshoot common errors.

The examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. What Is a Many-to-One Relationship?

Suppose one department has many employees, while each employee belongs to one department:

- One `Department` can be associated with many `Employee`s.
- Each `Employee` references one `Department`.

In the database, the foreign key is typically placed on the many-side table:

| departments | |
|---|---|
| id (PK) | name |
| 10 | Engineering |
| 20 | Finance |

| employees | | |
|---|---|---:|
| id (PK) | full_name | department_id (FK) |
| 101 | An | 10 |
| 102 | Bình | 10 |
| 103 | Chi | 20 |
| 104 | Dũng | 10 |

Three employees—An, Bình, and Dũng—all reference department ID 10. This is a many-to-one relationship viewed from the Employee side.

In JPA, the relationship is declared on the many-side entity. Each Employee has a Department field; the database stores the Department's ID in the foreign key column of the `employees` table.

### 1.1. Why Does the Foreign Key Live on the Many Side?

A column in the `employees` table can store one department ID per row. Multiple rows in `employees` can store the value 10, but each row holds only one `department_id` value.

Conversely, storing a list of employee IDs in a single column of `departments` would make it difficult to guarantee atomicity and referential integrity. The standard relational model stores the foreign key on the many side.

A many-to-one relationship does not automatically create a collection on the Department side. If the business logic needs to access the list of employees from a department, you can add the reverse side with `@OneToMany`.

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

The Java property name and the database column name can differ. In Java code, you use `employee.getDepartment()`; in SQL, the database stores the foreign key in `employees.department_id`.

### 2.1. Attributes of @ManyToOne

| Attribute | Default | Meaning |
|---|---|---|
| `targetEntity` | Inferred from property type | Specifies the target entity when the type cannot be inferred |
| `cascade` | No cascade | Which operations propagate to the target entity |
| `fetch` | `EAGER` | Strategy for loading the relationship |
| `optional` | `true` | Whether the relationship is allowed to have no target entity |

`@ManyToOne` defaults to `EAGER` fetching. This means the provider must ensure the relationship is loaded when the source entity is accessed under the JPA contract; the provider may perform a join or an additional query.

For applications that need explicit control over relationship loading, it is often better to declare:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

`LAZY` asks the provider to defer loading the target entity until it is needed. However, for `@ManyToOne`, `LAZY` is a JPA fetch hint; the provider may not be able to defer loading in every situation. Hibernate normally supports proxy/lazy loading when the mapping and class structure allow it.

### 2.2. Attributes of @JoinColumn

| Attribute | Meaning |
|---|---|
| `name` | Name of the join/foreign key column on the owning entity's table |
| `referencedColumnName` | Column name on the referenced entity's table; defaults to the primary key column |
| `nullable` | Whether the column allows null in the generated schema |
| `unique` | Requests a unique constraint on the column when generating schema |
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

- `name = "department_id"`: foreign key column in the `employees` table.
- `referencedColumnName = "id"`: references the ID column of `departments`.
- `nullable = false`: the column cannot be null in the generated schema.
- `optional = false`: at the object model level, an Employee must have a Department.
- `foreignKey`: names the constraint so the schema is easier to read and manage.

`referencedColumnName` is usually omitted because it defaults to the primary key. If referencing another column, that column needs suitable uniqueness to serve as a foreign key target and must be supported by the database. Prefer referencing the primary key unless there is a specific requirement.

Do not declare `@Column` on the same property already mapped with `@ManyToOne`; join column properties are configured via `@JoinColumn`.

### 2.3. Column Names and Schema

If `@JoinColumn(name = ...)` is not specified, the JPA provider applies default naming rules based on the property name and referenced key. Hibernate/Spring Boot naming strategies may also convert camelCase to snake_case.

To avoid surprises when working with an existing schema or migrations, declare column names explicitly:

```java
@JoinColumn(name = "department_id")
```

If the schema is managed by Flyway or Liquibase, column names, nullability, and foreign keys in migrations must match the JPA mappings.

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

### 3.2. Employee Entity with a Many-to-One Relationship

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

Spring Data parses `findByDepartmentId` into the property path `department.id`. Database column names do not participate in derived query method names; methods use the Java property names of the entity.

### 3.4. Saving Data in a Service

```java
package com.example.demo.employee;

import com.example.demo.department.Department;
import com.example.demo.department.DepartmentRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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

The service loads an existing `Department` and assigns it to `Employee`. This is the clean approach when `Department` already exists. Within the transaction, the `Department` entity is managed by the persistence context; Hibernate can use its foreign key when inserting `Employee`.

PERSIST cascade from `Employee` to `Department` is not needed here. The `Department` already exists and was loaded from the repository.

## 4. Unidirectional and Bidirectional Relationships

### 4.1. Unidirectional Many-to-One

In the previous example, only `Employee` has a `Department` field. From `Employee`, you can access the department:

```java
Employee employee = employeeRepository.findById(101L).orElseThrow();
String departmentName = employee.getDepartment().getName();
```

`Department` has no list of `Employee`s. This is a unidirectional relationship.

Advantages:

- Simple mapping.
- Lower risk of JSON serialization loops.
- No need to maintain a bidirectional collection.
- Fits well when business operations mostly navigate from the many-side entity to the one-side entity.

If you do not need to access employees from `Department`, unidirectional is usually sufficient.

### 4.2. Bidirectional Many-to-One

If you need to retrieve the list of employees from `Department`, you can add `@OneToMany` on the `Department` side:

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
- `mappedBy` must point to the Java property name on the owning entity, not the database column name.

When adding an employee, you must update the owning side:

```java
department.addEmployee(employee);
```

Adding only to the `department.getEmployees()` collection without updating `employee.setDepartment(department)` will not ensure the foreign key is written properly. JPA relies on the owning side to synchronize the relationship to the database.

### 4.3. Helper Methods to Keep Both Sides in Sync

In bidirectional relationships, encapsulate add/remove operations in helper methods to keep the object graph consistent.

If an `Employee` is transferred from an old department to a new department, the helper can update both collections:

```java
public void addEmployee(Employee employee) {
    if (employee.getDepartment() != null) {
        employee.getDepartment().getEmployees().remove(employee);
    }

    employees.add(employee);
    employee.setDepartment(this);
}
```

This snippet illustrates the idea of synchronizing both sides; in a real application, ensure the collection avoids duplicates, handles nulls, and standardizes entity equality (ID, `equals`/`hashCode`). Do not implement `equals`/`hashCode` using mutable fields or bidirectional associations, as this can cause infinite recursion and break collections.

If the old `Department` is not loaded or its collection is uninitialized, design a transfer method appropriate for the entity state and persistence context. A service can load both sides and perform the operation inside a transaction.

## 5. optional, nullable, and Database Constraints

These two attributes are often used together:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
```

They are related but not identical:

- `optional = false` describes the relationship in the JPA model: `Employee` must have a `Department`.
- `nullable = false` describes the nullability of the join column when the provider generates the schema.

If the relationship is mandatory, reflect this consistently in both the mapping and the database. The database needs NOT NULL and a foreign key to protect data even against operations outside the application.

If the relationship is allowed to be empty:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "department_id", nullable = true)
private Department department;
```

These attributes can be omitted since those are the defaults, though declaring them explicitly clarifies the rule to readers. If `department` is null, the `department_id` column in `employee` can be null.

`optional = false` does not create a `Department` object automatically. When creating an `Employee`, the application must assign a valid `Department`. The database foreign key still needs to be configured to prevent nonexistent IDs.

## 6. Cascade: Should Employee Cascade to Department?

By default, `@ManyToOne` cascades no operations. That means saving an `Employee` does not automatically persist a new `Department` unless cascade is declared.

You can declare:

```java
@ManyToOne(cascade = CascadeType.PERSIST)
@JoinColumn(name = "department_id")
private Department department;
```

However, consider this carefully. A `Department` can be shared by many `Employee`s. Cascading from `Employee` to `Department` can cause saving an `Employee` to trigger saving a `Department`, even though `Department` has its own lifecycle.

In particular, avoid putting `CascadeType.REMOVE` or `CascadeType.ALL` mechanically on `@ManyToOne`. Deleting one `Employee` must not accidentally delete a `Department` that other employees still reference.

Practical guidelines:

- Existing `Department`: load the `Department` and assign it to `Employee`; no persist cascade is needed.
- Separately created `Department`: save the `Department` first, then assign it to `Employee`.
- Only cascade when the target entity truly belongs to the source entity's lifecycle and that behavior fits the business domain.
- Cascade does not replace foreign keys, transactions, or business authorization checks.

In a model where `Department` has many `Employee`s, if an `Employee` should be deleted when removed from the collection, `orphanRemoval` can be considered on the `@OneToMany` side of `Department`. This is a child lifecycle rule; it is not an attribute of `@ManyToOne` and should only be used when `Employee` truly belongs to `Department`'s lifecycle ownership.

## 7. Fetch Strategy and the N+1 Problem

`@ManyToOne` defaults to `FetchType.EAGER`. An EAGER relationship must be loaded when the source entity is accessed under the JPA contract; the provider may use a JOIN or a separate query. Thus, EAGER does not guarantee a single SQL query.

`FetchType.LAZY` allows deferring relationship loading:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
```

In Hibernate, LAZY is usually implemented using a proxy. When code accesses `employee.getDepartment().getName()`, Hibernate can issue a query to load `Department`.

### 7.1. N+1 Queries

Example:

```java
List<Employee> employees = employeeRepository.findAll();

for (Employee employee : employees) {
    System.out.println(employee.getDepartment().getName());
}
```

If the list has N employees and each `Department` has not been loaded yet, accessing the relationship can trigger many additional queries. The result can be one query loading employees plus queries loading departments. The exact query count depends on caching, the provider, batching, and how the data is accessed.

### 7.2. Using JOIN FETCH

When you know a use case needs `Department`, you can load the relationship in the same query:

```java
@Query("""
       select e
       from Employee e
       join fetch e.department
       where e.id = :id
       """)
Optional<Employee> findByIdWithDepartment(@Param("id") Long id);
```

This is JPQL; `Employee` and `department` are Java entity and property names. `join fetch` loads the association in the same query.

### 7.3. Using EntityGraph

You can specify which associations to load using `@EntityGraph`:

```java
@EntityGraph(attributePaths = "department")
Optional<Employee> findByFullName(String fullName);
```

EntityGraph allows selecting a fetch plan per query method without changing the default fetch type of the mapping.

Do not switch all relationships to EAGER to dodge lazy loading. That can cause queries that do not need the association to load unnecessary data. Identify the data needed for each use case and use fetch joins, entity graphs, or DTOs accordingly.

## 8. Lazy Loading, Transactions, and DTOs

When a LAZY relationship has not been loaded, accessing it after the persistence context has closed can throw a `LazyInitializationException` in Hibernate.

Risky example:

```java
public Employee getEmployee(Long id) {
    return employeeRepository.findById(id).orElseThrow();
}

// Elsewhere, after the session has closed:
String name = employee.getDepartment().getName();
```

A better approach is to load the needed data inside the transaction and map it to a DTO before returning from the service:

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

The DTO contains the exact data the use case needs and does not depend on Hibernate proxies. This also prevents accidentally serializing the entire entity graph.

If returning entities directly via REST, bidirectional relationships can cause infinite JSON recursion: `Employee` contains `Department`, `Department` contains `Employees`, each `Employee` references `Department`. DTOs provide a clean way to control the payload.

## 9. Querying by Relationship

Spring Data JPA can derive queries from property paths:

```java
List<Employee> findByDepartmentId(Long departmentId);

List<Employee> findByDepartmentNameIgnoreCase(String name);
```

The method names use Java properties `department.id` and `department.name`, not the SQL column name `department_id`.

When queries become complex or need explicit relationship fetching, use `@Query`:

```java
@Query("""
       select e
       from Employee e
       join fetch e.department
       where e.department.id = :departmentId
       order by e.fullName
       """)
List<Employee> findAllByDepartmentWithDepartment(
        @Param("departmentId") Long departmentId
);
```

For paginated queries with collection fetch joins, be careful because joining a collection can multiply rows and distort pagination. A many-to-one relationship normally does not duplicate an employee across multiple departments, though you should still review the query and real data.

## 10. Testing Many-to-One Relationships

Test both the mapping and database behavior:

- Save `Department`.
- Save `Employee` with an existing `Department`.
- Flush and clear the persistence context to ensure data is read back from the database.
- Load `Employee` and verify the `Department` is correct.
- Test null `Department` if the relationship is optional.
- Test NOT NULL/foreign key enforcement if the relationship is mandatory.
- Test fetch join/entity graph queries when the use case needs `Department`.

Example with `@DataJpaTest`:

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

The test assumes JUnit 5, AssertJ, Spring Boot Test imports, and the corresponding entity/repository classes. `TestEntityManager` is provided in Spring Boot's JPA test slice. `flush()` pushes changes to the database; `clear()` empties the persistence context so the subsequent read does not simply return the already-managed entity from memory.

If you rely on PostgreSQL-specific behavior or want to verify production database constraints, run integration tests against PostgreSQL/Testcontainers. An embedded database can differ in data types and constraint behavior.

## 11. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Entity requires Department, but department is null | Association was not set before saving | Load `Department` and assign it to `Employee` |
| Foreign key constraint violation | `department_id` references a nonexistent ID | Check IDs, transaction, and save ordering |
| `department_id` column not created with expected name | Missing/wrong `@JoinColumn` name or unexpected naming strategy | Specify `name` explicitly and check migration/schema |
| LazyInitializationException | Lazy relationship accessed outside persistence context | Load within transaction, use fetch join/entity graph and DTOs |
| N+1 queries | Lazy relationship accessed inside a loop | Choose a fetch plan suited to the use case |
| Deleting Employee deletes Department | REMOVE/ALL cascade placed inappropriately | Remove remove cascade from the many-to-one side |
| Department collection does not reflect new Employee | Only the inverse side was updated | Update owning side `Employee.department` |
| Infinite JSON recursion | Bidirectional relationship serialized directly | Return DTOs with a clear structure |
| Schema creation fails due to FK | Entity/table/column mapping or migrations out of sync | Check table names, join columns, and migration ordering |

## 12. @ManyToOne Design Checklist

- [ ] Identify the many-side entity and the one-side entity.
- [ ] Place `@ManyToOne` on the many-side entity.
- [ ] Place `@JoinColumn` to describe the foreign key on the many-side table.
- [ ] Choose `optional` and `nullable` consistently with business rules and schema.
- [ ] Consider declaring `fetch = FetchType.LAZY` and loading associations per use case.
- [ ] Do not cascade REMOVE from child to shared parent.
- [ ] If bidirectional, update the owning side and synchronize both sides via helper methods.
- [ ] Check for N+1 queries, lazy loading issues, and entity serialization.
- [ ] Use DTOs to control API response payloads.
- [ ] Test foreign keys, nullability, fetch queries, and transactions.

## Conclusion

`@ManyToOne` describes a relationship from a many-side entity to a one-side entity; `@JoinColumn` specifies the foreign key column on the owning entity's table. In a bidirectional model, the `@ManyToOne` property is the owning side and controls the foreign key value written to the database.

Good design starts with placing foreign keys properly, selecting an appropriate fetch strategy, controlling cascades, and maintaining the owning side. Load data according to each use case's needs, use transactions and DTOs appropriately, and test mappings against a suitable database. These principles keep entity relationships clear, efficient, and less error-prone as the application grows.