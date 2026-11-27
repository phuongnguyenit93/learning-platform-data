# Combining EntityGraph with Appropriate Query Methods in Spring Data JPA

In Spring Data JPA, the query method determines which entities are selected, while the fetch plan determines which associations are loaded alongside those entities. If all associations are left LAZY, the application can encounter N+1 queries when reading many entities and then accessing relationships. If EAGER is set broadly, queries that do not need related data may still load too much.

EntityGraph lets you declare a fetch plan per use case. You can attach a graph to a derived query method or a method using @Query in a repository. As a result, the same entity can be loaded with different associations depending on the screen or operation.

This lesson covers named entity graphs, dynamic graphs via attributePaths, FETCH and LOAD semantics, nested subgraphs, how to combine them with different repository method types, limitations with projections/native queries/collection pagination, and how to test fetch plans.

## 1. What Problem Does EntityGraph Solve?

Suppose an Employee entity has a to-one relationship to Department and a to-many relationship to Assignment. Assignment in turn references Project.

A query that only needs employee names may not need to load Department, Assignment, or Project. However, an employee profile page may need Department along with the corresponding Assignments and Projects.

If all associations are always loaded, simple queries can become heavy. If they are always LAZY, code reading the profile can trigger many extra queries.

EntityGraph describes which attributes need to be fetched for a specific query:

- Query A: Employee with Department.
- Query B: Employee with Department, Assignments, and the Project of each Assignment.
- Query C: only Employee, with no additional associations needed.

The fetch plan is selected at the repository method or when creating a query with EntityManager. EntityGraph does not alter the WHERE condition, ordering, or business semantics of the filter.

## 2. Distinguishing Predicate and Fetch Plan

A repository query has multiple independent dimensions:

| Dimension | Question to Answer | Tool |
|---|---|---|
| Predicate | Which Employees to select? | Derived query, JPQL, Criteria, Specification |
| Fetch plan | Which Department/Assignments/Project to load? | EntityGraph, fetch join, batch fetching |
| Projection | Which fields to return? | DTO or interface projection |
| Pagination | Which page to fetch and what is the total count? | Pageable, Page/Slice, count query |

Example:

~~~java
@Query("""
       select e
       from Employee e
       where e.active = true
         and e.department.name = :departmentName
       """)
List<Employee> findActiveByDepartmentName(
        @Param("departmentName") String departmentName);
~~~

The query above selects active employees belonging to a department. If you need to load Department together with Employee, you can attach an EntityGraph to the method. The predicate remains unchanged; the graph only adds association-loading requirements.

Do not use EntityGraph as a way to write filtering conditions. A graph cannot replace WHERE, JOIN predicates, or EXISTS.

## 3. Entity Model Used in This Lesson

The following examples use the same model in the com.example.employee package. Employee has a Department and a list of Assignment; each Assignment references a Project.

Department entity:

~~~java
package com.example.employee;

import jakarta.persistence.*;

@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
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
}
~~~

Project entity:

~~~java
package com.example.employee;

import jakarta.persistence.*;

@Entity
@Table(name = "projects")
public class Project {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    protected Project() {
    }

    public Project(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Assignment entity as a collection element:

~~~java
package com.example.employee;

import jakarta.persistence.*;

@Entity
@Table(name = "assignments")
public class Assignment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "employee_id", nullable = false)
    private Employee employee;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    @Column(nullable = false, length = 80)
    private String role;

    protected Assignment() {
    }

    public Assignment(Employee employee, Project project, String role) {
        this.employee = employee;
        this.project = project;
        this.role = role;
    }

    public Long getId() {
        return id;
    }

    public Employee getEmployee() {
        return employee;
    }

    public Project getProject() {
        return project;
    }

    public String getRole() {
        return role;
    }
}
~~~

Employee entity declaring named graphs:

~~~java
package com.example.employee;

import java.util.ArrayList;
import java.util.List;

import jakarta.persistence.*;

@Entity
@Table(name = "employees")
@NamedEntityGraphs({
    @NamedEntityGraph(
        name = "Employee.withDepartment",
        attributeNodes = @NamedAttributeNode("department")
    ),
    @NamedEntityGraph(
        name = "Employee.detail",
        attributeNodes = {
            @NamedAttributeNode("department"),
            @NamedAttributeNode(
                value = "assignments",
                subgraph = "assignment-project"
            )
        },
        subgraphs = @NamedSubgraph(
            name = "assignment-project",
            attributeNodes = @NamedAttributeNode("project")
        )
    )
})
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false, unique = true, length = 200)
    private String email;

    @Column(nullable = false)
    private boolean active;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    @OneToMany(mappedBy = "employee", fetch = FetchType.LAZY)
    private List<Assignment> assignments = new ArrayList<>();

    protected Employee() {
    }

    public Employee(
            String name,
            String email,
            boolean active,
            Department department) {
        this.name = name;
        this.email = email;
        this.active = active;
        this.department = department;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }

    public Department getDepartment() {
        return department;
    }

    public List<Assignment> getAssignments() {
        return assignments;
    }
}
~~~

The associations are declared LAZY to express per-query loading needs. The EntityGraph on Employee provides two named graphs: one that loads only Department and one that loads Department together with Assignments/Project.

In a real application, you should add bidirectional association management methods if the domain needs to add/remove Assignments. The read examples below only need the declared mappings and getters.

Note: LAZY on a to-one relationship is a hint to the provider under JPA; the provider may load it eagerly in some cases. To-many relationships default to LAZY. EntityGraph helps specify the minimum data that must be loaded for an operation, but it is not a guarantee that SQL will only fetch the listed columns/associations.

## 4. What Is a Named EntityGraph?

A Named EntityGraph is a pre-declared fetch plan defined using the @NamedEntityGraph annotation on an entity or via XML metadata.

Simple graph example:

~~~java
@NamedEntityGraph(
    name = "Employee.withDepartment",
    attributeNodes = @NamedAttributeNode("department")
)
~~~

The graph name is Employee.withDepartment. The attribute node department references the Java property name in the entity, not the column name department_id.

The detail graph adds a collection and a nested subgraph:

~~~java
@NamedEntityGraph(
    name = "Employee.detail",
    attributeNodes = {
        @NamedAttributeNode("department"),
        @NamedAttributeNode(
            value = "assignments",
            subgraph = "assignment-project"
        )
    },
    subgraphs = @NamedSubgraph(
        name = "assignment-project",
        attributeNodes = @NamedAttributeNode("project")
    )
)
~~~

How to read it:

1. Load Employee.
2. Load Employee's Department.
3. Load the assignments collection.
4. For each Assignment, load Project.

Subgraphs allow declaring deeper paths on associations or embedded attributes. If you need to load multi-level nested properties, you can declare additional nested subgraphs accordingly.

Named graphs are registered in the persistence unit and can be reused across multiple repository methods or EntityManager queries. Graph names must be unique within the persistence unit.

## 5. Attribute Nodes and Subgraphs

An attribute node identifies a property to fetch directly from the root entity. For a to-one association, the node loads the related entity; for a collection, the node loads the collection and its elements according to the graph.

A subgraph describes the further graph for the target type of the association:

~~~java
@NamedAttributeNode(
    value = "assignments",
    subgraph = "assignment-project"
)
~~~

The name assignment-project points to:

~~~java
@NamedSubgraph(
    name = "assignment-project",
    attributeNodes = @NamedAttributeNode("project")
)
~~~

Inside Assignment's subgraph, project is a property of Assignment. Do not write the path assignments.project inside @NamedSubgraph; the subgraph already establishes the Assignment entity context.

Node names must match the persistent properties of their respective entities. Invalid names are typically detected when the provider initializes or uses the graph.

You do not need to add every association to a graph. An overly broad graph can load many collections, generate large SQL, increase memory usage, and cause unnecessary hydration overhead.

## 6. FETCH Graph and LOAD Graph

JPA defines two types of EntityGraph:

- **FETCH graph:** attributes specified in the graph are treated as EAGER for this load; attributes not specified are treated as LAZY.
- **LOAD graph:** attributes specified are treated as EAGER; attributes not specified retain the entity's configured fetch mapping.

In both cases, the provider may still load additional data outside the graph if needed to execute the query or due to implementation requirements. A graph specifies what must be fetched, not a guarantee that SQL will load only the listed attributes.

FETCH example:

~~~java
@EntityGraph(
    value = "Employee.withDepartment",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<Employee> findByEmail(String email);
~~~

FETCH is suitable when a method needs a specific fetch plan for a use case and wants other attributes to be treated as LAZY for that load.

LOAD example:

~~~java
@EntityGraph(
    value = "Employee.withDepartment",
    type = EntityGraph.EntityGraphType.LOAD
)
Optional<Employee> findByEmail(String email);
~~~

LOAD adds Department to the fetch plan, while other attributes continue following the entity's fetch type mapping. If an association is mapped as EAGER, a LOAD graph does not turn it into LAZY just because the graph omits it.

In Spring Data JPA, EntityGraphType defaults to FETCH if type is not specified. Specify type explicitly when you want readers to clearly see the fetch plan's intent.

## 7. Attaching a Named Graph to a Derived Query Method

Spring Data JPA provides the org.springframework.data.jpa.repository.EntityGraph annotation for repository methods.

Repository:

~~~java
package com.example.employee;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @EntityGraph(
        value = "Employee.withDepartment",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<Employee> findByEmail(String email);

    @EntityGraph(
        value = "Employee.detail",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<Employee> findDetailedById(Long id);

    @EntityGraph(
        value = "Employee.withDepartment",
        type = EntityGraph.EntityGraphType.LOAD
    )
    List<Employee> findByActiveTrue();
}
~~~

The findByEmail method is a derived query. Spring Data generates the predicate from the method name while applying the named graph Employee.withDepartment as the fetch plan.

findDetailedById uses the detail named graph. findByActiveTrue finds Employees with active = true and applies the Department graph with LOAD semantics.

EntityGraph does not change the condition values. If you remove the annotation from findByEmail, the query still finds the same Employee, though the fetch plan may differ.

## 8. Using a Dynamic Graph via attributePaths

If you only need a graph for a single method, you do not have to declare a named graph on the entity. You can use attributePaths:

~~~java
@EntityGraph(attributePaths = {"department"})
Optional<Employee> findByEmail(String email);
~~~

With nested paths:

~~~java
@EntityGraph(attributePaths = {
    "department",
    "assignments.project"
})
Optional<Employee> findDetailedById(Long id);
~~~

Spring Data builds an ad hoc entity graph from the declared attribute paths. This form is commonly called a dynamic EntityGraph in the context of repository methods.

When attributePaths is provided, Spring Data treats it as a dynamically created graph; the named graph name in value is no longer the graph source used. Therefore, choose one approach clearly:

- Use value to reference an already-declared named graph.
- Use attributePaths to create a graph dedicated to that method.

Do not declare both value and attributePaths expecting the two graphs to be merged.

Paths use Java property names. For example, assignments.project navigates from Employee to the assignments collection, and then to the project property of Assignment.

## 9. Nested Attribute Paths and Path Limits

With dynamic graphs, Spring Data supports dot-notation paths to represent nested associations:

~~~java
@EntityGraph(attributePaths = {
    "department",
    "assignments.project"
})
List<Employee> findByDepartment_Name(String departmentName);
~~~

This method illustrates combining a predicate traversing Department with a fetch graph loading Department and the Project of each Assignment.

Paths must be valid according to the entity model. If a property is an embedded object, you can use the corresponding nested path. For collection associations, consider collection sizes and graph depth.

A multi-level graph can produce multiple SQL joins or additional subqueries depending on the provider. Do not assume every graph always corresponds to a single SQL statement.

## 10. Combining EntityGraph with @Query

EntityGraph can also be attached to a repository method annotated with @Query. JPQL handles filtering, and the graph handles association loading.

~~~java
@Query("""
       select e
       from Employee e
       where e.active = true
         and e.department.name = :departmentName
       """)
@EntityGraph(
    value = "Employee.withDepartment",
    type = EntityGraph.EntityGraphType.FETCH
)
List<Employee> findActiveByDepartmentName(
        @Param("departmentName") String departmentName);
~~~

The JPQL does not need to write join fetch e.department because the graph already describes the fetch plan. The predicate can still reference e.department.name to filter by department.

If the query needs a JOIN for filtering but does not want to load the association, you can write a regular JOIN in JPQL and omit the association from the graph. If loading is needed, the graph can supply the fetch plan.

Avoid writing join fetch e.department in JPQL while also declaring a graph for the same association just to fetch the same data twice. Such redundant combinations can make queries harder to read and provider-dependent.

## 11. EntityGraph Does Not Replace JOIN or EXISTS for Filtering

Graph example:

~~~java
@EntityGraph(attributePaths = {"department"})
List<Employee> findByActiveTrue();
~~~

The graph does not mean "only return Employees that have a Department." It instructs JPA to load Department for the Employees found. An Employee with a null department can still be returned if the predicate does not exclude it.

If you want only Employees belonging to the Engineering department, you must have a predicate:

~~~java
List<Employee> findByActiveTrueAndDepartment_Name(String name);
~~~

Or use @Query with the corresponding WHERE condition.

Similarly, if you want to find Employees that have at least one Assignment for a specific Project, you need a predicate using join/exists/Specification. Putting assignments.project in the graph only loads the related data; it does not filter Employees by Project.

## 12. EntityGraph and Repository Return Types

EntityGraph works best with methods returning an entity or a collection of entities:

| Return Type | Usage |
|---|---|
| Optional<Employee> | Loads at most one Employee with associations |
| Employee | Loads one Employee per the method contract |
| List<Employee> | Loads a list of Employees with the graph |
| Page<Employee> | Can use a graph; be especially careful if the graph contains a collection |
| Slice<Employee> | Can use a graph; still must watch out for the impact of collection fetches |
| DTO projection | Graph is usually unnecessary because the query only selects the projection |
| Scalar value | EntityGraph has no root entity associations to load |

With projections, select only the needed fields. Do not rely on EntityGraph to force-load associations for a DTO constructor expression or scalar query; a fetch plan makes the most sense when the result is an entity.

With native queries, how graphs are applied and how results are mapped can depend on the provider. Do not assume EntityGraph will automatically rewrite native SQL or hydrate collections; if native SQL is needed, check provider support and test the actual mapping.

## 13. EntityGraph with Page and Pageable

You can attach a graph to a method returning Page:

~~~java
@EntityGraph(attributePaths = {"department"})
Page<Employee> findByActiveTrue(Pageable pageable);
~~~

Department is a to-one relationship, so it typically does not multiply Employee rows if cardinality is mapped accurately. This case is generally suitable for pagination.

Be careful when the graph contains a collection:

~~~java
@EntityGraph(attributePaths = {"assignments"})
Page<Employee> findByActiveTrue(Pageable pageable);
~~~

The provider may fetch the collection using a JOIN. One Employee with multiple Assignments produces multiple SQL rows; database-level result limits may no longer correspond to the number of Employees. Hibernate may have to paginate in memory or log a warning depending on version/configuration.

EntityGraph does not guarantee safe collection pagination. If you need a Page of Employees along with all Assignments, consider:

1. Paginating Employee IDs first.
2. Loading Employees with Assignments for that set of IDs in a separate query without Pageable.
3. Restoring the page's ID order.

If the UI only needs the Assignment count, use a DTO projection with a count aggregate instead of fetching the whole collection.

## 14. EntityGraph and Count Queries

Page<T> may require both a content query and a count query. The count query only needs to count matching root entities; it does not need to load Department, Assignment, or Project.

EntityGraph is a fetch plan for reading entities. Do not add association fetches into the count query by writing JPQL fetch joins inside countQuery. For paginated queries with collection graphs, inspect the content SQL and count SQL separately.

If the content query filters over a collection, the count query must preserve an equivalent predicate. For example, finding Employees with at least one Assignment for a Project:

~~~java
@Query(
    value = """
            select e
            from Employee e
            where exists (
                select a.id
                from Assignment a
                where a.employee = e
                  and a.project.id = :projectId
            )
            """,
    countQuery = """
            select count(e)
            from Employee e
            where exists (
                select a.id
                from Assignment a
                where a.employee = e
                  and a.project.id = :projectId
            )
            """
)
Page<Employee> findPageByProject(
        @Param("projectId") Long projectId,
        Pageable pageable);
~~~

You can attach a Department graph to the method if Department needs to be loaded for content entities. The EXISTS predicate remains intact, and the count query counts Employees under the same condition.

## 15. EntityGraph with To-One and To-Many

To-one relationships:

- @ManyToOne
- @OneToOne

Usually each root entity links to at most one target entity. To-one fetch graphs carry a lower risk of multiplying root rows.

To-many relationships:

- @OneToMany
- @ManyToMany

One root can have many related elements. Collection fetch graphs can generate multiple SQL rows for a single root and increase data transfer/hydration cost.

If a graph loads multiple collections, the cost can grow with the Cartesian product of element counts. Hibernate can also throw MultipleBagFetchException when fetching multiple bag collections simultaneously in a single query.

Do not add every collection to a detail graph just because you can. Design graphs around screen needs and consider batch fetching or separate queries.

## 16. EntityGraph and N+1

N+1 happens when the application loads N root entities and then issues an extra query for each entity when accessing a LAZY association.

Example:

~~~java
List<Employee> employees = repository.findByActiveTrue();

for (Employee employee : employees) {
    System.out.println(employee.getDepartment().getName());
}
~~~

If Department has not been loaded and the provider cannot batch the queries, the loop can generate many additional SQL statements.

Using EntityGraph:

~~~java
@EntityGraph(attributePaths = "department")
List<Employee> findByActiveTrue();
~~~

The graph requires Department to be loaded in the query's fetch plan. The provider may use a join or another strategy, but the application no longer waits until each Department is accessed to load it.

EntityGraph helps control the fetch plan for specified associations; it does not guarantee that all N+1 issues disappear. If the loop also accesses assignments.project while the graph only includes Department, the remaining associations can still trigger extra queries.

Inspect actual SQL and statement counts to verify effectiveness.

## 17. EntityGraph vs. JOIN FETCH

| Criterion | EntityGraph | JOIN FETCH |
|---|---|---|
| Purpose | Declare a fetch plan | Declare fetching in JPQL |
| Location | Annotation, named graph, or EntityManager hint | JPQL query |
| Separated from predicate | Yes; the graph does not filter data on its own | JOIN FETCH lives inside the query |
| Reusability | Named graphs can be reused across multiple queries | Typically tied to a specific JPQL query |
| Nested associations | Attribute nodes and subgraphs | Multiple fetch joins |
| Actual SQL | Provider decides execution strategy | Provider translates fetch join to corresponding SQL join |
| Pagination with collections | Can still encounter row multiplication | Explicit risk of row multiplication |
| DTO projection | Usually does not need a graph | Constructor projections can combine regular joins |

EntityGraph often clarifies the separation between predicates and fetch plans. JOIN FETCH fits when a specific query needs to make the fetched association explicit directly in JPQL.

There is no rule that EntityGraph is always faster than JOIN FETCH. Both should be verified against actual SQL and real data.

## 18. Named Graphs in XML

In addition to annotations, JPA allows declaring named entity graphs in orm.xml. The named graph is placed inside the mapping section of the corresponding entity.

Example src/main/resources/META-INF/orm.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_1.xsd"
    version="3.1">

    <entity class="com.example.employee.Employee">
        <named-entity-graph name="Employee.withDepartment">
            <named-attribute-node name="department"/>
        </named-entity-graph>
    </entity>
</entity-mappings>
~~~

If the same graph name is declared in both annotations and XML, XML metadata can override annotation metadata according to mapping rules. Choose a single clear source of definition for each graph and verify the mapping file is loaded by the provider.

If the project uses Jakarta Persistence 3.0, 3.1, or 3.2, use the corresponding namespace and XSD version. Spring Boot 3 projects typically use jakarta.persistence; older projects using javax.persistence have older schemas/namespaces.

## 19. Using EntityGraph Directly with EntityManager

JPA's EntityManager supports creating dynamic graphs and passing graphs via query hints.

Example:

~~~java
EntityGraph<Employee> graph =
        entityManager.createEntityGraph(Employee.class);

graph.addAttributeNodes("department");

TypedQuery<Employee> query = entityManager.createQuery(
        "select e from Employee e where e.active = true",
        Employee.class
);

query.setHint("jakarta.persistence.fetchgraph", graph);

List<Employee> employees = query.getResultList();
~~~

You can retrieve a declared named graph:

~~~java
EntityGraph<?> graph =
        entityManager.getEntityGraph("Employee.detail");

TypedQuery<Employee> query = entityManager.createQuery(
        "select e from Employee e where e.id = :id",
        Employee.class
);

query.setParameter("id", id);
query.setHint("jakarta.persistence.fetchgraph", graph);
~~~

Two standard hints:

- jakarta.persistence.fetchgraph: applies FETCH graph semantics.
- jakarta.persistence.loadgraph: applies LOAD graph semantics.

In JPA 2.x use the javax.persistence namespace; with Jakarta Persistence 3.x use jakarta.persistence. Spring Boot 3 and later typically use the Jakarta namespace. Check your project's version before copying code.

## 20. EntityGraph and Repository Methods Combine Flexibly

A repository can have multiple methods for different use cases:

~~~java
package com.example.employee;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {

    @EntityGraph(
        value = "Employee.withDepartment",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<Employee> findByEmail(String email);

    @EntityGraph(
        value = "Employee.detail",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<Employee> findDetailedById(Long id);

    @EntityGraph(attributePaths = {"department"})
    List<Employee> findByActiveTrue();

    @EntityGraph(attributePaths = {"department"})
    Page<Employee> findByDepartment_Name(
            String departmentName,
            Pageable pageable);

    @Query("""
           select e
           from Employee e
           where e.active = true
             and e.department.id = :departmentId
           """)
    @EntityGraph(attributePaths = {"department"})
    List<Employee> findActiveByDepartmentId(
            @Param("departmentId") Long departmentId);
}
~~~

This is an interface consolidating the illustrative methods; each method has its own predicate and can choose a named graph or dynamic graph as needed.

Note that if the repository already inherits a method with the same signature, overriding it to attach an annotation must be done intentionally. Do not declare methods with identical signatures expecting different fetch plans; Java does not allow overloading solely by annotations.

## 21. Testing EntityGraph with PersistenceUnitUtil

You should not merely assert on association values after calling a repository, because invoking getters can trigger lazy loading inside the transaction. You can use PersistenceUnitUtil.isLoaded() to verify that the association was already loaded right after the query.

Test example:

~~~java
package com.example.employee;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnitUtil;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class EmployeeEntityGraphTest {

    @Autowired
    private EmployeeRepository repository;

    @Autowired
    private TestEntityManager testEntityManager;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void namedGraphLoadsDepartment() {
        Department department = new Department("Engineering");
        testEntityManager.persist(department);

        Employee employee = new Employee(
                "Ada",
                "ada@example.com",
                true,
                department
        );
        testEntityManager.persist(employee);

        testEntityManager.flush();
        testEntityManager.clear();

        Employee found = repository.findByEmail("ada@example.com")
                .orElseThrow();

        PersistenceUnitUtil util =
                entityManagerFactory.getPersistenceUnitUtil();

        assertThat(util.isLoaded(found, "department")).isTrue();
        assertThat(found.getDepartment().getName())
                .isEqualTo("Engineering");
    }

    @Test
    void nestedGraphLoadsAssignmentsAndProjects() {
        Department department = new Department("Engineering");
        Project project = new Project("Migration");

        testEntityManager.persist(department);
        testEntityManager.persist(project);

        Employee employee = new Employee(
                "Ada",
                "ada@example.com",
                true,
                department
        );
        testEntityManager.persist(employee);

        Assignment assignment =
                new Assignment(employee, project, "Developer");
        testEntityManager.persist(assignment);

        testEntityManager.flush();
        Long employeeId = employee.getId();
        testEntityManager.clear();

        Employee found = repository.findDetailedById(employeeId)
                .orElseThrow();

        PersistenceUnitUtil util =
                entityManagerFactory.getPersistenceUnitUtil();

        assertThat(util.isLoaded(found, "assignments")).isTrue();
        Assignment loadedAssignment = found.getAssignments().get(0);
        assertThat(util.isLoaded(loadedAssignment, "project")).isTrue();
        assertThat(loadedAssignment.getProject().getName())
                .isEqualTo("Migration");
    }
}
~~~

The first test uses the named graph Employee.withDepartment on findByEmail. After clear(), the entity is no longer in the previous persistence context. isLoaded verifies that the association was loaded by the query.

The second test uses the detail graph to verify that the assignments collection and nested project are loaded. The test needs to run inside the persistence context of @DataJpaTest so it can inspect association state and read the Project name.

If you want to test SQL statement counts, use a datasource proxy or Hibernate statistics to verify the query count, because isLoaded only checks association state and does not prove the query is optimal.

## 22. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Named graph not found | Wrong graph name or metadata not loaded | Check name and mapping |
| Attribute node throws error | Used SQL column name instead of Java property | Use persistent property name |
| Nested subgraph does not work | Subgraph declares wrong target entity or wrong path name | Check association and target type |
| EntityGraph does not filter results | Graph only specifies the fetch plan | Add WHERE/JOIN/EXISTS predicate |
| N+1 still occurs | Graph omits an accessed association | Add the required path or use batch fetching |
| Query loads too much data | Graph includes many collections or levels | Narrow the graph to the use case |
| Page is slow with collection graph | Collection fetch multiplies rows or paginates in memory | Page IDs first, then fetch separately |
| Count query affected by join | To-many JOIN predicate multiplies root rows | Use EXISTS or count distinct root |
| DTO does not use graph as expected | Projection does not return root entity graph | Choose an appropriate projection; do not rely on a graph |
| Duplicate EntityGraph and JOIN FETCH | Same association declared twice | Choose one clear fetch strategy |
| MultipleBagFetchException | Fetching multiple bag collections in the same query | Split queries or use batch fetching |
| LazyInitializationException | Accessing association outside transaction | Load within transaction or return a DTO |
| LOAD graph still loads unlisted associations | Association mapping is EAGER | Understand the difference between LOAD and FETCH |
| FETCH graph still loads extra fields | Provider may fetch more outside the graph | Graph is not an absolute minimal-SQL guarantee |

## 23. Practical Design Principles

- Set associations to LAZY as a sensible default and choose fetch plans per use case.
- Use named graphs when a fetch plan is reused across multiple repository methods.
- Use attributePaths for small graphs specific to a single method.
- Use FETCH when you want attributes outside the graph treated as LAZY for that load; use LOAD when you want to preserve mapping fetch types for unlisted attributes.
- Keep predicates in derived queries, @Query, Specifications, or Criteria; graphs only manage fetch plans.
- Attach graphs to methods returning entities when associations are genuinely needed.
- Do not add collections to every detail graph.
- Check SQL and N+1 rather than assuming a graph always generates a single JOIN.
- Be careful with Page/Slice when the graph contains a collection.
- Separate ID pagination and collection fetching if you need a page of roots with full collections.
- Use DTO projections if you only need a few fields or aggregate numbers.
- Avoid declaring the same association in both EntityGraph and JOIN FETCH unnecessarily.
- Test loaded associations with PersistenceUnitUtil and measure query counts.
- Verify Jakarta/Javax namespaces according to the project's JPA version.

## 24. Self-Assessment Checklist

- [ ] Can explain the difference between a predicate and a fetch plan.
- [ ] Can declare a named graph using @NamedEntityGraph.
- [ ] Can use @NamedAttributeNode for root attributes.
- [ ] Can use @NamedSubgraph for nested associations.
- [ ] Can distinguish FETCH graph and LOAD graph.
- [ ] Can use @EntityGraph(value = ...) to reference a named graph.
- [ ] Can use attributePaths to create a dynamic graph.
- [ ] Understand that attributePaths takes precedence when declared and the graph name is no longer the graph source.
- [ ] Can combine EntityGraph with derived queries.
- [ ] Can combine EntityGraph with @Query.
- [ ] Understand that graphs do not automatically add filtering predicates.
- [ ] Can choose appropriate graphs for to-one and to-many relationships.
- [ ] Can recognize the risks of collection fetching with Page/Slice.
- [ ] Can distinguish EntityGraph and JOIN FETCH.
- [ ] Know how to use EntityManager fetchgraph/loadgraph hints.
- [ ] Can verify loaded associations using PersistenceUnitUtil.isLoaded().
- [ ] Can measure SQL/query counts to detect N+1.
- [ ] Can use DTO projections or batch fetching when appropriate.

## 25. Conclusion

EntityGraph helps Spring Data JPA select fetch plans per query method. Named graphs suit reusable fetch plans; attributePaths suits small graphs declared right on the repository method. FETCH and LOAD differ in how they treat attributes not listed in the graph.

When combining EntityGraph with derived queries or @Query, keep roles clear: the query determines which entities match, and the graph determines which associations to load. Be especially careful with collections in Page/Slice because graphs do not eliminate row multiplication or in-memory pagination. Inspect SQL, association state, and query counts against realistic data to pick a just-enough fetch plan.