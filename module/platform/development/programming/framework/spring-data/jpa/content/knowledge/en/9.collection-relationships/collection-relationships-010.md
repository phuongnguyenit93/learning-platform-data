# Adding, Removing, and Replacing Elements While Keeping Both Sides Consistent

## Objectives

In a bidirectional relationship in Spring Data JPA, one entity holds a reference to a related entity while the other entity holds a collection containing it. For example, `Department.employees` is the list of employees, while `Employee.department` is each employee's department.

The database has only one relationship mapping controlled by the owning side. Therefore, adding, removing, transferring, or replacing elements must update the owning-side reference so the foreign key is written accurately. At the same time, code should synchronize the inverse-side collection so the in-memory object graph reflects the same state.

This lesson shows how to design helper methods for `add`, `remove`, `transfer`, and `replace`, how to choose cascade/orphan removal, and provides a runnable Java 17+ example with Spring Boot and H2.

## 1. The Two Sides of a Bidirectional Relationship

Consider a department with many employees:

```java
@Entity
public class Department {
    @OneToMany(mappedBy = "department")
    private List<Employee> employees = new ArrayList<>();
}

@Entity
public class Employee {
    @ManyToOne
    @JoinColumn(name = "department_id")
    private Department department;
}
```

- `Employee.department` is the **owning side** because it declares `@JoinColumn` and controls the `department_id` foreign key column.
- `Department.employees` is the **inverse side** because `mappedBy = "department"` points to the owning-side property.

On flush, the JPA provider relies on `Employee.department` to determine `employee.department_id`. The `Department.employees` collection does not write the foreign key simply by containing an element.

## 2. Why Must Both Sides Be Updated?

Suppose code adds an employee via:

```java
department.getEmployees().add(employee);
```

The in-memory collection now contains the employee, yet `employee.getDepartment()` is still `null`. Because the collection is the inverse side, JPA does not use this change to update the FK. The database may still store `department_id = NULL` or fail a constraint if the column disallows nulls.

Conversely, if you only call:

```java
employee.setDepartment(department);
```

the owning side has the information to write the FK, yet `department.getEmployees()` may still omit the employee. Subsequent code reading the collection could observe stale state.

Therefore, every relationship mutation should perform two actions:

1. Update the owning side so JPA writes the database correctly.
2. Update the inverse side so the in-memory object graph stays consistent.

## 3. Designing Helper Methods for add and remove

Encapsulate bidirectional synchronization logic on the entity or an appropriate domain method, rather than scattering `collection.add()` and `setDepartment()` calls across Services.

Example on `Department`:

```java
public void addEmployee(Employee employee) {
    Objects.requireNonNull(employee, "employee must not be null");

    Department previous = employee.getDepartment();
    if (previous != null && previous != this) {
        previous.detachEmployee(employee);
    }

    if (!employees.contains(employee)) {
        employees.add(employee);
    }
    employee.setDepartment(this);
}

private void detachEmployee(Employee employee) {
    employees.remove(employee);
}

public boolean removeEmployee(Employee employee) {
    Objects.requireNonNull(employee, "employee must not be null");
    boolean removed = employees.remove(employee);

    if (employee.getDepartment() == this) {
        employee.setDepartment(null);
    }
    return removed;
}
```

`addEmployee` also handles transferring an employee from another department: it detaches the employee from the old collection, adds them to the new collection, and updates the owning side. `removeEmployee` removes from the collection and sets the owning reference to null.

This example uses `List` without overriding `equals()`/`hashCode()` on the entity, so `contains` and `remove` use default object identity. If your entity has custom equality based on ID or mutable attributes, design it carefully to avoid failing to locate elements in a collection after the ID changes or before the entity is persisted.

### Preventing Direct Collection Mutation

You can return an unmodifiable view from the getter:

```java
public List<Employee> getEmployees() {
    return Collections.unmodifiableList(employees);
}
```

This prevents callers from arbitrarily adding or removing elements while bypassing helper methods. Hibernate continues to manage the internal collection; do not replace the persistent collection field with a `new ArrayList` via a setter after the entity is managed.

## 4. Transferring an Element Between Two Parents

Moving an employee from `Engineering` to `Support` requires updating three points:

1. Remove the employee from `Engineering.employees`.
2. Add the employee to `Support.employees`.
3. Set `Employee.department = Support`.

The `Support.addEmployee(employee)` helper above performs all three steps: it reads the previous department, calls `detachEmployee` on the old department, and sets the owning side to the new department.

Do not call `removeEmployee` on the old department before `addEmployee` when the helper already handles the transfer. Calling remove first can set `employee.department` to null; in a model with orphan removal, that could also mark the entity as an orphan for deletion.

### Boundaries of orphanRemoval

If the relationship represents strict lifecycle ownership, you can declare:

```java
@OneToMany(mappedBy = "department",
           cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<Employee> employees = new ArrayList<>();
```

When an employee is removed from the collection, JPA deletes the orphan entity per orphan removal rules. This fits when an employee only exists as part of a department and cannot be transferred to another parent.

If business rules allow transferring employees between departments, do not combine a transfer flow with turning the employee into an orphan. Consider disabling orphan removal or designing the transfer operation around a suitable lifecycle model. Jakarta Persistence does not guarantee moving an entity already marked as an orphan to another parent within the same transaction.

## 5. Replacing the Entire Collection

Replacing a collection means turning the current set of elements into a new set. The safe way is to compute the diff and use helper methods:

- Elements already present and still in the new set: keep unchanged.
- Elements currently present but missing from the new set: call `removeEmployee`.
- New elements: call `addEmployee`.
- Elements belonging to another parent: `addEmployee` detaches them from the old collection and attaches them to the current parent.

Example:

```java
public void replaceEmployees(Collection<Employee> replacement) {
    Objects.requireNonNull(replacement, "replacement must not be null");
    List<Employee> requested = new ArrayList<>(replacement);

    Set<Employee> seen = Collections.newSetFromMap(new IdentityHashMap<>());
    for (Employee employee : requested) {
        Objects.requireNonNull(employee, "replacement contains null");
        if (!seen.add(employee)) {
            throw new IllegalArgumentException("Duplicate employee instance");
        }
    }

    for (Employee current : new ArrayList<>(employees)) {
        if (!seen.contains(current)) {
            removeEmployee(current);
        }
    }

    for (Employee employee : requested) {
        addEmployee(employee);
    }
}
```

`IdentityHashMap` builds a duplicate-checking set based on object reference identity, avoiding reliance on custom entity `equals()`. If the application receives a list of IDs from an API, the Service should load the entities by ID, check permissions and validity, and then invoke the domain method; do not fabricate dummy entities containing only an ID and assign them directly to the collection.

### Why Not Assign a New Collection Directly to the Field?

Do not do the following on a managed entity:

```java
department.setEmployees(new ArrayList<>(replacement));
```

Replacing the collection instance can discard the collection wrapper Hibernate uses to track changes, complicate orphan removal tracking, and fail to update the owning side on individual employees. Diffing plus helper methods preserves the managed collection and synchronizes both sides.

## 6. Cascade and orphanRemoval Differ from Bidirectional Synchronization

`cascade` controls whether JPA operations propagate from one entity to related entities:

- `PERSIST`: persists related entities when the parent is persisted.
- `MERGE`: merges related entities when the parent is merged.
- `REMOVE`: propagates remove operations.
- `ALL`: includes all of the cascade types above.

`orphanRemoval = true` indicates that a child entity is deleted when it is no longer linked to the parent through that relationship. This is a lifecycle rule, not an ownership rule.

Regardless of which cascade is used, `mappedBy` still defines the inverse side and the owning side still controls the FK. Cascading does not make `Department.employees` the owning side.

## 7. Notes on List, Set, and equals/hashCode

The collection type affects how Java detects duplicates and how Hibernate manages ordering:

- `List` preserves order and allows duplicate elements. If order matters in the database, declare an explicit ordering mapping such as `@OrderColumn` or sort by an attribute.
- `Set` prevents duplicates using `equals()`/`hashCode()`. Entities whose IDs are generated on persist need an equality strategy that stays consistent before and after ID assignment.
- Never include mutable properties in `hashCode()` if those properties can change while the entity is inside a `HashSet`.
- Helper methods must still update the owning side regardless of whether `List` or `Set` is used.

For ordered collections, `@OrderBy` sorts by a property when reading; `@OrderColumn` stores positions in the database. These two annotations have different semantics and different update costs.

## 8. Runnable Example with Java 17+, Spring Boot, and H2

This example demonstrates adding, transferring, removing, and replacing employees across two departments. The relationship allows employees to temporarily belong to no department, so `department_id` is nullable. Orphan removal is disabled to support transferring employees between parents.

### Project Structure

```text
collection-sync/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/collectionsync/
        │   ├── CollectionSyncApplication.java
        │   ├── Department.java
        │   ├── Employee.java
        │   ├── DepartmentRepository.java
        │   ├── EmployeeRepository.java
        │   └── DepartmentService.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>collection-sync</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:collectiondb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Department.java`

```java
package com.example.collectionsync;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "departments")
public class Department {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(mappedBy = "department",
               cascade = {CascadeType.PERSIST, CascadeType.MERGE})
    private List<Employee> employees = new ArrayList<>();

    protected Department() {
    }

    public Department(String name) {
        this.name = name;
    }

    public void addEmployee(Employee employee) {
        Objects.requireNonNull(employee, "employee must not be null");

        Department previous = employee.getDepartment();
        if (previous != null && previous != this) {
            previous.detachEmployee(employee);
        }

        if (!employees.contains(employee)) {
            employees.add(employee);
        }
        employee.setDepartment(this);
    }

    private void detachEmployee(Employee employee) {
        employees.remove(employee);
    }

    public boolean removeEmployee(Employee employee) {
        Objects.requireNonNull(employee, "employee must not be null");
        boolean removed = employees.remove(employee);
        if (employee.getDepartment() == this) {
            employee.setDepartment(null);
        }
        return removed;
    }

    public void replaceEmployees(Collection<Employee> replacement) {
        Objects.requireNonNull(replacement, "replacement must not be null");
        List<Employee> requested = new ArrayList<>(replacement);
        Set<Employee> seen = Collections.newSetFromMap(new IdentityHashMap<>());

        for (Employee employee : requested) {
            Objects.requireNonNull(employee, "replacement contains null");
            if (!seen.add(employee)) {
                throw new IllegalArgumentException("Duplicate employee instance");
            }
        }

        for (Employee current : new ArrayList<>(employees)) {
            if (!seen.contains(current)) {
                removeEmployee(current);
            }
        }

        for (Employee employee : requested) {
            addEmployee(employee);
        }
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<Employee> getEmployees() {
        return Collections.unmodifiableList(employees);
    }
}
```

### `Employee.java`

```java
package com.example.collectionsync;

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

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    protected Employee() {
    }

    public Employee(String name) {
        this.name = name;
    }

    Department getDepartment() {
        return department;
    }

    void setDepartment(Department department) {
        this.department = department;
    }

    public String getName() {
        return name;
    }
}
```

### `DepartmentRepository.java`

```java
package com.example.collectionsync;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DepartmentRepository extends JpaRepository<Department, Long> {
}
```

### `EmployeeRepository.java`

```java
package com.example.collectionsync;

import org.springframework.data.jpa.repository.JpaRepository;

public interface EmployeeRepository extends JpaRepository<Employee, Long> {
    long countByDepartmentIsNull();
}
```

### `DepartmentService.java`

```java
package com.example.collectionsync;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DepartmentService {
    private final DepartmentRepository departmentRepository;
    private final EmployeeRepository employeeRepository;

    @PersistenceContext
    private EntityManager entityManager;

    public DepartmentService(DepartmentRepository departmentRepository,
                             EmployeeRepository employeeRepository) {
        this.departmentRepository = departmentRepository;
        this.employeeRepository = employeeRepository;
    }

    @Transactional
    public String demonstrateCollectionChanges() {
        Department engineering = new Department("Engineering");
        Department support = new Department("Support");
        Employee an = new Employee("An");
        Employee binh = new Employee("Binh");

        engineering.addEmployee(an);
        engineering.addEmployee(binh);
        departmentRepository.save(engineering);
        departmentRepository.save(support);

        // Transfer Binh: detach from Engineering and attach to Support.
        support.addEmployee(binh);

        // Remove An from the department; the employee row remains unassigned.
        engineering.removeEmployee(an);

        // Replace Engineering's remaining members with a new collection.
        engineering.replaceEmployees(List.of(new Employee("Cuong")));

        entityManager.flush();
        Long engineeringId = engineering.getId();
        Long supportId = support.getId();
        entityManager.clear();

        Department loadedEngineering = departmentRepository.findById(engineeringId)
                .orElseThrow();
        Department loadedSupport = departmentRepository.findById(supportId)
                .orElseThrow();

        String engineeringNames = loadedEngineering.getEmployees().stream()
                .map(Employee::getName)
                .sorted()
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
        String supportNames = loadedSupport.getEmployees().stream()
                .map(Employee::getName)
                .sorted()
                .reduce((left, right) -> left + ", " + right)
                .orElse("");

        long unassigned = employeeRepository.countByDepartmentIsNull();
        return loadedEngineering.getName() + ": " + engineeringNames
                + "\n" + loadedSupport.getName() + ": " + supportNames
                + "\nUnassigned employees: " + unassigned;
    }
}
```

In this example, `Department.employees` uses PERSIST/MERGE cascade to save new employees added to a managed parent. REMOVE cascade and orphan removal are disabled because business rules allow transferring employees between departments and retaining removed employees as unassigned.

### `CollectionSyncApplication.java`

```java
package com.example.collectionsync;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CollectionSyncApplication {
    public static void main(String[] args) {
        SpringApplication.run(CollectionSyncApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DepartmentService service) {
        return args -> System.out.println(service.demonstrateCollectionChanges());
    }
}
```

### Running the Application

```bash
mvn spring-boot:run
```

The output printed by the application:

```text
Engineering: Cuong
Support: Binh
Unassigned employees: 1
```

The output shows that `Binh` was transferred to Support, `An` was removed from Engineering while keeping the employee record, and Engineering's list was replaced with `Cuong`. Changes are verified after `flush()` and `clear()` inside the same transaction.

## 9. Understanding the SQL for Adding, Removing, and Transferring Elements

With `Employee.department` as the owning side, operations can generate corresponding SQL:

- Adding an employee to Engineering: INSERT employee with `department_id` equal to Engineering's ID.
- Transferring Binh to Support: UPDATE employee setting `department_id` to Support's ID.
- Removing An from Engineering: UPDATE employee setting `department_id` to NULL in this example model.
- Replacing Engineering's collection and adding Cuong: INSERT new employee with Engineering's `department_id`.

Actual SQL depends on the ID generation strategy, flush order, and Hibernate version. The statements above describe data effects without guaranteeing an exact statement order.

If `department_id` is `NOT NULL`, a remove operation that sets null will fail. In that case, the domain must clearly decide: disallow removal, require assigning to another parent, or delete the employee per lifecycle rules.

## 10. When Should You Use orphanRemoval?

`orphanRemoval = true` fits when the child entity belongs to the parent's lifecycle ownership. For example, an invoice line item only exists as part of an invoice; removing the line from the invoice means deleting that line.

```java
@OneToMany(mappedBy = "order",
           cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<OrderLine> lines = new ArrayList<>();
```

When an `OrderLine` is removed from the collection, the provider deletes the orphan when synchronizing the persistence context. Do not use orphan removal on relationships where a child can move between multiple parents; Jakarta Persistence does not guarantee re-attaching an entity already marked as an orphan within the same transaction.

## 11. Testing and Best Practices

- Test adding elements and verify the FK is written properly.
- Test removal and verify behavior matches nullability or orphan removal rules.
- Test transferring an element between two parents and verify both collections and the owning reference.
- Test replacing with an empty collection, retained elements, new elements, and elements belonging to another parent.
- Use integration tests with `flush()` and `clear()` before reloading to avoid verifying only data cached in the persistence context.
- Never replace a Hibernate-managed collection with a new instance through a setter.
- Choose cascades based on entity lifecycles; cascade does not replace updating the owning side.
- Design `equals()`/`hashCode()` carefully when entities are kept in a `Set` or when IDs are generated upon persist.

Key takeaway: **Every bidirectional relationship mutation must update the owning side so the database writes the correct foreign key, and the inverse side so the object graph stays consistent. With `mappedBy`, the collection is only the reverse view; helper methods are the central place for add, remove, transfer, and replace logic.**