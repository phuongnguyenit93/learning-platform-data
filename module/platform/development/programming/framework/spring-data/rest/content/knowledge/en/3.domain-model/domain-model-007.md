# One-to-One, One-to-Many, and Many-to-Many Relationships in JPA Examples

JPA maps relationships between Java entities to foreign keys or join tables in a relational database. The three common patterns are one-to-one (`@OneToOne`), one-to-many (`@OneToMany` paired with `@ManyToOne`), and many-to-many (`@ManyToMany`).

When using Spring Data REST, these relationships are also exposed as association links on HAL resources. Therefore, you need to understand both layers: how JPA stores the relationship in the database, and how Spring Data REST lets clients read and update links between resources over HTTP.

The example below uses Java 17+, Spring Boot with Spring Data JPA, and Spring Data REST. The imports use `jakarta.persistence.*`, suitable for Spring Boot 3 and later. Keep your project's existing Spring Boot version and let the parent/BOM manage compatible Spring Data versions.

## 1. Domain Model Used in the Example

Consider an employee management system:

- An `Employee` has at most one `EmployeeProfile`; a profile belongs to at most one employee.
- A `Department` has many `Employee`s; each employee belongs to at most one department.
- An `Employee` has many `Skill`s; a skill can be held by many employees.

Relationship diagram:

~~~mermaid
erDiagram
    EMPLOYEE ||--o| EMPLOYEE_PROFILE : has
    DEPARTMENT ||--o{ EMPLOYEE : contains
    EMPLOYEE }o--o{ SKILL : has
    EMPLOYEE {
        bigint id PK
        string name
        bigint profile_id FK
        bigint department_id FK
    }
    EMPLOYEE_PROFILE {
        bigint id PK
        string biography
    }
    DEPARTMENT {
        bigint id PK
        string name
    }
    SKILL {
        bigint id PK
        string name
    }
    EMPLOYEE_SKILL {
        bigint employee_id FK
        bigint skill_id FK
    }
~~~

The `employee` table holds foreign keys to profile and department. The `employee_skill` table is a join table containing the pair of foreign keys for employee and skill. The unique constraint on `employee.profile_id` ensures a profile cannot be assigned to multiple employees.

| Relationship Type | Common Mapping | Link Storage Location |
| --- | --- | --- |
| One-to-one | `@OneToOne` | A foreign key with a UNIQUE constraint, or shared primary key/join table |
| One-to-many | `@OneToMany` and `@ManyToOne` | Foreign key resides on the many-side table |
| Many-to-many | `@ManyToMany` | Join table containing foreign keys of both entities |

Cardinality describes how many objects can be linked. It does not yet specify which side writes the relationship to the database. In bidirectional relationships, JPA also distinguishes the **owning side** and the **inverse side**.

## 2. Owning Side and `mappedBy` Rules

Every bidirectional relationship has one owning side. Changes on the owning side determine what link is written to the database. The inverse side uses `mappedBy` to point to the relationship attribute name on the owning side.

- `@JoinColumn` declares the foreign key column on the owning side of a foreign-key-based relationship.
- `@JoinTable` declares the join table for a many-to-many relationship (or certain other mapping styles).
- `mappedBy` takes the **Java attribute name** on the owning side, not the database column name and not the table name.
- Do not declare `@JoinColumn` or `@JoinTable` on the inverse side of a standard bidirectional relationship.

In this model, choose the owning sides as follows:

| Relationship | Owning Side | Inverse Side |
| --- | --- | --- |
| Employee — EmployeeProfile | `Employee.profile` with `@JoinColumn` | `EmployeeProfile.employee` with `mappedBy = "profile"` |
| Department — Employee | `Employee.department` with `@JoinColumn` and `@ManyToOne` | `Department.employees` with `mappedBy = "department"` |
| Employee — Skill | `Employee.skills` with `@JoinTable` | `Skill.employees` with `mappedBy = "skills"` |

In particular, for a bidirectional one-to-many relationship, the many side (`@ManyToOne`) is the owning side. Merely adding an employee to the `Department.employees` collection without updating `Employee.department` may cause the change not to be persisted. For many-to-many, either side can be chosen as the owner, but only one side declares the join table; the other references it with `mappedBy`.

## 3. Declaring the Entities

Place the classes below in the same package, such as `com.example.demo.domain`. Each entity has a no-arg constructor for JPA and the necessary getters/setters. The example intentionally avoids Lombok `@Data`, because generated equals/hashCode and toString on bidirectional relationships can easily cause infinite recursion or unintended data loading.

### 3.1. Employee and One-to-One Relationship with EmployeeProfile

`Employee` is the owning side. The `profile_id` foreign key resides in the `employee` table; `unique = true` guarantees each profile is referenced by at most one employee.

**Employee.java**

~~~java
package com.example.demo.domain;

import jakarta.persistence.*;
import java.util.LinkedHashSet;
import java.util.Set;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "profile_id", unique = true)
    private EmployeeProfile profile;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    @ManyToMany(fetch = FetchType.LAZY)
    @JoinTable(
        name = "employee_skill",
        joinColumns = @JoinColumn(name = "employee_id"),
        inverseJoinColumns = @JoinColumn(name = "skill_id")
    )
    private Set<Skill> skills = new LinkedHashSet<>();

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

    public void setName(String name) {
        this.name = name;
    }

    public EmployeeProfile getProfile() {
        return profile;
    }

    public void setProfile(EmployeeProfile profile) {
        if (this.profile == profile) {
            return;
        }

        EmployeeProfile previous = this.profile;
        this.profile = profile;

        if (previous != null) {
            previous.setEmployeeReference(null);
        }
        if (profile != null) {
            profile.setEmployeeReference(this);
        }
    }

    public Department getDepartment() {
        return department;
    }

    public void setDepartment(Department department) {
        if (this.department == department) {
            return;
        }

        Department previous = this.department;
        this.department = department;

        if (previous != null) {
            previous.removeEmployeeReference(this);
        }
        if (department != null) {
            department.addEmployeeReference(this);
        }
    }

    public Set<Skill> getSkills() {
        return skills;
    }

    public void addSkill(Skill skill) {
        if (skills.add(skill)) {
            skill.addEmployeeReference(this);
        }
    }

    public void removeSkill(Skill skill) {
        if (skills.remove(skill)) {
            skill.removeEmployeeReference(this);
        }
    }
}
~~~

**EmployeeProfile.java**

~~~java
package com.example.demo.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "employee_profiles")
public class EmployeeProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(length = 1000)
    private String biography;

    @OneToOne(mappedBy = "profile", fetch = FetchType.LAZY)
    private Employee employee;

    protected EmployeeProfile() {
    }

    public EmployeeProfile(String biography) {
        this.biography = biography;
    }

    public Long getId() {
        return id;
    }

    public String getBiography() {
        return biography;
    }

    public void setBiography(String biography) {
        this.biography = biography;
    }

    public Employee getEmployee() {
        return employee;
    }

    void setEmployeeReference(Employee employee) {
        this.employee = employee;
    }
}
~~~

`mappedBy = "profile"` points to the `profile` field in `Employee`. Do not place `@JoinColumn` on `EmployeeProfile.employee`, because it is the inverse side.

### 3.2. Department and One-to-Many Relationship with Employee

A department can have many employees. Each employee holds the `department_id` foreign key, so `Employee.department` is the owning side. The `Department.employees` collection is the inverse side.

**Department.java**

~~~java
package com.example.demo.domain;

import jakarta.persistence.*;
import java.util.LinkedHashSet;
import java.util.Set;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    private Set<Employee> employees = new LinkedHashSet<>();

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

    public Set<Employee> getEmployees() {
        return employees;
    }

    public void addEmployee(Employee employee) {
        employee.setDepartment(this);
    }

    public void removeEmployee(Employee employee) {
        if (employee.getDepartment() == this) {
            employee.setDepartment(null);
        }
    }

    void addEmployeeReference(Employee employee) {
        employees.add(employee);
    }

    void removeEmployeeReference(Employee employee) {
        employees.remove(employee);
    }
}
~~~

In `Employee.setDepartment`, the owning side is updated first; then the collections on the two affected departments are synchronized in memory. The `addEmployee` and `removeEmployee` methods call this setter to avoid mutating only one side of the relationship.

If an employee must always belong to a department, consider `@ManyToOne(optional = false)` and `@JoinColumn(nullable = false)`, and disallow unlinking via the API. The current example keeps the relationship optional to demonstrate transferring or unassigning an employee from a department.

### 3.3. Skill and Many-to-Many Relationship with Employee

An employee has many skills and a skill can belong to many employees. The database needs a join table `employee_skill` instead of placing a column containing a list of IDs inside the `employee` or `skill` table.

**Skill.java**

~~~java
package com.example.demo.domain;

import jakarta.persistence.*;
import java.util.LinkedHashSet;
import java.util.Set;

@Entity
@Table(name = "skills")
public class Skill {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String name;

    @ManyToMany(mappedBy = "skills", fetch = FetchType.LAZY)
    private Set<Employee> employees = new LinkedHashSet<>();

    protected Skill() {
    }

    public Skill(String name) {
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

    public Set<Employee> getEmployees() {
        return employees;
    }

    void addEmployeeReference(Employee employee) {
        employees.add(employee);
    }

    void removeEmployeeReference(Employee employee) {
        employees.remove(employee);
    }
}
~~~

`Employee.skills` is the owning side because it declares `@JoinTable`. `Skill.employees` uses `mappedBy = "skills"`. Both collections are kept in sync by `addSkill` and `removeSkill` on Employee. Do not add `CascadeType.REMOVE` from Employee to Skill: skills are shared data, and deleting an employee should not delete skills belonging to other employees.

### 3.4. Repositories to Export the Entities

Each repository below is exported by Spring Data REST as a collection resource. Place the interfaces in the same package or sub-package scanned by the Spring Boot application.

~~~java
package com.example.demo.repository;

import com.example.demo.domain.Employee;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "employees")
public interface EmployeeRepository extends JpaRepository<Employee, Long> {
}
~~~

~~~java
package com.example.demo.repository;

import com.example.demo.domain.Department;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "departments")
public interface DepartmentRepository extends JpaRepository<Department, Long> {
}
~~~

~~~java
package com.example.demo.repository;

import com.example.demo.domain.EmployeeProfile;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "profiles")
public interface EmployeeProfileRepository
        extends JpaRepository<EmployeeProfile, Long> {
}
~~~

~~~java
package com.example.demo.repository;

import com.example.demo.domain.Skill;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "skills")
public interface SkillRepository extends JpaRepository<Skill, Long> {
}
~~~

The minimal dependencies for the example are Spring Data REST, Spring Data JPA, and a JDBC driver. With H2 for testing:

**Maven**

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-rest</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

**Gradle**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-rest'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
}
~~~

Dependency versions are managed by the Spring Boot parent/BOM. Do not assign separate versions to individual starters when the BOM already manages them.

Database configuration in `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:people;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.data.rest.base-path=/api
~~~

`create-drop` is only suitable for examples using an in-memory database. Real applications should use migrations such as Flyway or Liquibase and a schema policy appropriate for the deployment environment.

## 4. Observing the Schema and Data

With the mappings above, the main relational structure looks like:

~~~text
employees
  id
  name
  profile_id     -> employee_profiles.id (UNIQUE)
  department_id  -> departments.id

employee_profiles
  id
  biography

departments
  id
  name

skills
  id
  name

employee_skill
  employee_id -> employees.id
  skill_id    -> skills.id
  PRIMARY KEY (employee_id, skill_id)
~~~

- One-to-one uses the foreign key in `employees.profile_id`; the UNIQUE constraint turns the foreign key relationship into one-to-one.
- One-to-many uses `employees.department_id`; many employee rows can point to the same department.
- Many-to-many uses two foreign keys in `employee_skill`; each employee/skill pair represents a link.

Column names, table names, and ID types may vary depending on your project's naming strategy or configuration. What matters is understanding where foreign keys and join tables live.

## 5. Spring Data REST Exposes Association Links

When accessing an item resource, Spring Data REST adds links for relationship properties. Default link names match the Java property names; they can be customized using `@RestResource` on the relationship property.

With `spring.data.rest.base-path=/api`, the main resources have the form:

| Resource | Meaning |
| --- | --- |
| `/api/employees/{id}` | An employee |
| `/api/employees/{id}/profile` | One-to-one association to profile |
| `/api/employees/{id}/department` | Many-to-one association to department |
| `/api/employees/{id}/skills` | Many-to-many association to skills |
| `/api/departments/{id}/employees` | Collection of employees in the department |
| `/api/skills/{id}/employees` | Collection of employees having the skill |

Association resources are discovered from entity relationships. They support `GET`, `PUT`, `POST`, and `DELETE` depending on the relationship type. HAL payloads typically represent relationships via links under `_links`; clients should discover links from responses rather than assembling URLs manually in real applications.

### 5.1. Reading a Relationship

Fetch an employee:

~~~bash
curl -i -H "Accept: application/hal+json"   http://localhost:8080/api/employees/1
~~~

The HAL response may contain links similar to:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/employees/1"
    },
    "profile": {
      "href": "http://localhost:8080/api/employees/1/profile"
    },
    "department": {
      "href": "http://localhost:8080/api/employees/1/department"
    },
    "skills": {
      "href": "http://localhost:8080/api/employees/1/skills"
    }
  }
}
~~~

Specific IDs and links depend on created data and configuration. Read the profile or skill list through the association links:

~~~bash
curl -i -H "Accept: application/hal+json"   http://localhost:8080/api/employees/1/profile

curl -i -H "Accept: application/hal+json"   http://localhost:8080/api/employees/1/skills

curl -i -H "Accept: application/hal+json"   http://localhost:8080/api/departments/1/employees
~~~

### 5.2. Assigning a One-to-One Relationship

First create the profile and employee via their respective collection resources, or obtain the URIs of two existing resources. Then send the profile URI to the Employee's association resource:

~~~bash
curl -i -X PUT   -H "Content-Type: text/uri-list"   --data "http://localhost:8080/api/profiles/10"   http://localhost:8080/api/employees/1/profile
~~~

`PUT` binds the resource indicated by the URI to the association. For a to-one relationship, send only a single URI; sending multiple URIs will be rejected. Because `Employee.profile` is the owning side, this is the association to update so JPA writes the `profile_id` foreign key.

To unlink, send `DELETE` to the association resource if the relationship is optional. If the association is declared non-optional, Spring Data REST may reject the unlink operation.

### 5.3. Assigning a One-to-Many Relationship

In JPA, `Employee.department` is the owning side of the Department–Employee relationship. Therefore, the write operation is performed on the employee's association:

~~~bash
curl -i -X PUT   -H "Content-Type: text/uri-list"   --data "http://localhost:8080/api/departments/3"   http://localhost:8080/api/employees/1/department
~~~

After the link is updated, read `/api/departments/3/employees` to view the department's employee collection. Do not merely modify the `Department.employees` collection in code while ignoring `Employee.department`; updating the inverse side alone does not guarantee the foreign key is updated.

To move an employee to another department, send `PUT` with the new department's URI to `/employees/{id}/department`. If the business requires an employee to always belong to a department, enforce that across mappings, validation, and API.

### 5.4. Adding a Many-to-Many Relationship

For collection-valued associations, Spring Data REST supports `POST` to append an item. Send the skill URI to the association resource on the owning side Employee:

~~~bash
curl -i -X POST   -H "Content-Type: text/uri-list"   --data "http://localhost:8080/api/skills/5"   http://localhost:8080/api/employees/1/skills
~~~

Multiple URIs can be POSTed in a `text/uri-list` body, one URI per line. Spring Data REST adds those elements to the collection association. `GET /api/employees/1/skills` to confirm the link appears.

`DELETE` on an association resource removes the association. For collections, check the exact endpoint and business rules before using it. Do not use association DELETE as a way to delete a Skill entity from the database: unlinking a relationship and deleting an entity are two different operations.

## 6. Cascade, Orphan Removal, and Entity Lifecycle

Relationship annotations describe cardinality and mapping structure. Cascade and orphan removal control entity lifecycle, not cardinality.

- **No cascade by default:** The example declares no cascades; Profile, Department, Skill, and Employee are created through their own repositories and linked via association URIs. This keeps each resource's lifecycle distinct.
- **Cascade PERSIST/MERGE:** Use only when saving a parent entity and saving the related entity genuinely belong to the same business operation.
- **Cascade REMOVE:** Be cautious with shared entities. Do not cascade remove from Employee to Skill because multiple employees can share a single Skill.
- **orphanRemoval:** Suitable when a child entity belongs exclusively to a parent and removing the link means deleting the child. Do not enable it arbitrarily for shared Profile, Department, or Skill; removing an association does not necessarily mean deleting the target entity.

If a relationship carries its own business data, such as an employee's skill proficiency level, certification date, or start date, replace `@ManyToMany` with a join entity such as `EmployeeSkill`. This entity has two `@ManyToOne` relationships to Employee and Skill, plus its own attributes. That gives you control over lifecycle, auditing, and validation of the link.

## 7. Fetching, Serialization, and Performance

- `@OneToOne` and `@ManyToOne` default to EAGER; `@OneToMany` and `@ManyToMany` default to LAZY. The example explicitly sets `fetch = FetchType.LAZY` on all relationships. For to-one relationships, LAZY is a request/hint that the provider must support; verify the actual provider behavior.
- Do not access LAZY collections after the persistence context closes unless the required data has been loaded. A common error in Hibernate is `LazyInitializationException`.
- Fetching many associations simultaneously can cause N+1 queries or duplicate rows in join results. Use appropriate queries, projections, pagination, or `@EntityGraph` when you have a specific need.
- Do not automatically serialize an entire bidirectional object graph by invoking nested getters. Employee → Department → Employees → Employee can create a loop. Spring Data REST exposes associations as HAL links by default; if custom payloads are needed, use projections or appropriate DTOs.
- Avoid Lombok `@Data` on entities with bidirectional relationships. Generated equals/hashCode and toString can recurse across associations or make collections behave inconsistently. If equals/hashCode is needed, choose a strategy based on a stable identity and test with transient/proxy entities.
- With `Set`, understand how entity equals/hashCode affects deduplication. If a relationship has its own attributes or requires ordering, consider a join entity or an ordered collection.

## 8. Common Pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| Adding an element to a collection does not change the database | Only the inverse side with `mappedBy` was modified | Update the owning side; use helper methods to synchronize both sides |
| `mappedBy` is not recognized | Value is a column or table name instead of the Java property name | Use the exact field name on the owning side, e.g., `mappedBy = "department"` |
| One-to-one still allows multiple rows pointing to the same profile | Missing UNIQUE constraint on the foreign key or mapping does not reflect cardinality | Use `@OneToOne` and an appropriate unique foreign key |
| No association link appears in HAL | Repository is not exported, relationship property is unrecognized, or serialization/configuration is customized | Check repositories, entity mappings, and HAL responses |
| PUT association returns 400 | Multiple URIs sent for a to-one relationship | Send only a single target URI |
| POST association fails to add a link | Using POST for to-one, invalid URI, or Content-Type is not `text/uri-list` | Use PUT for to-one; POST for collections and send valid URIs |
| Deleting one Skill wipes shared data | Cascade REMOVE on a many-to-many relationship | Remove cascade remove; only unlink the association |
| JSON loops infinitely or response is huge | Serializing bidirectional object graphs or loading unbounded associations | Use HAL links, projections/DTOs, and bound data |

## 9. Relationship Design Checklist

- [ ] Domain cardinality accurately reflects business rules.
- [ ] The owning side is identified for every bidirectional relationship.
- [ ] `mappedBy` points to the exact Java attribute name on the owning side.
- [ ] Foreign keys, UNIQUE constraints, and join tables reflect the cardinality.
- [ ] Helper methods synchronize both owning and inverse sides in memory.
- [ ] Cascade and orphan removal are chosen according to entity lifecycle ownership.
- [ ] Many-to-many relationships with their own attributes are modeled as join entities.
- [ ] Repositories exported via Spring Data REST are reviewed for security and data scope.
- [ ] Association links and GET/PUT/POST/DELETE operations are verified over HTTP.
- [ ] Lazy loading, N+1 queries, serialization cycles, and pagination are reviewed.

## Official References

- [Spring Data REST — Repository Resources and Association Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Jakarta Persistence — Entity Relationships](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2)
- [Jakarta Persistence API — OneToOne](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/OneToOne.html)
- [Jakarta Persistence API — OneToMany](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/OneToMany.html)
- [Jakarta Persistence API — ManyToMany](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/ManyToMany.html)
- [Jakarta Persistence API — JoinTable](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/JoinTable.html)