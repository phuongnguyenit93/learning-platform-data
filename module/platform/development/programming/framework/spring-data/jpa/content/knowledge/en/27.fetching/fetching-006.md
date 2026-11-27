# Combining EntityGraph with the Right Query Methods in Spring Data JPA

In Spring Data JPA, a query method decides which entities are selected, while a fetch plan decides which associations are loaded along with those entities. If every association is left LAZY, the application can suffer from N+1 queries when reading many entities and accessing relationships. If EAGER is placed everywhere, queries that do not need related data may still over-fetch.

`EntityGraph` allows declaring a fetch plan per use case. You can attach a graph to derived query methods or methods using `@Query` in a repository. As a result, the same entity can be loaded with different associations depending on the screen or operation.

This lesson covers named entity graphs, dynamic graphs via `attributePaths`, `FETCH` and `LOAD` semantics, nested subgraphs, how to combine them with different repository method types, limitations with projections/native queries/collection pagination, and how to test fetch plans.

## 1. What Problem Does EntityGraph Solve?

Suppose an `Employee` entity has a to-one relationship to `Department` and a to-many relationship to `Assignment`. `Assignment` in turn references `Project`.

A query needing only employee names may not need to load `Department`, `Assignment`, or `Project`. However, an employee profile page may need `Department` along with the corresponding `Assignment`s and `Project`s.

Always loading every association can make even simple queries heavy. Always leaving everything LAZY can cause profile-reading code to issue many extra queries.

`EntityGraph` describes which attributes should be fetched for a specific query:

- Query A: `Employee` with `Department`.
- Query B: `Employee` with `Department`, `Assignments`, and each `Assignment`'s `Project`.
- Query C: only `Employee`, with no extra associations.

The fetch plan is chosen on the repository method or when building a query via `EntityManager`. `EntityGraph` does not alter `WHERE` conditions, ordering, or the business meaning of filters.

## 2. Distinguishing Predicates and Fetch Plans

A repository query has two independent aspects:

| Component | Question to Answer | Tool |
|---|---|---|
| Predicate | Which `Employee`s to select? | Derived query, JPQL, Criteria, Specification |
| Fetch plan | Which `Department`/`Assignments`/`Project` to load? | EntityGraph, fetch join, batch fetching |
| Projection | Which fields to return? | DTO or interface projection |
| Pagination | Which page and total count? | Pageable, Page/Slice, count query |

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

This query selects active employees belonging to a department. If `Department` needs to be loaded along with `Employee`, an `EntityGraph` can be attached to the method. The predicate stays unchanged; the graph only adds the association loading requirement.

Do not use `EntityGraph` as a way to write filter conditions. A graph cannot replace `WHERE`, JOIN predicates, or `EXISTS`.

## 3. Entity Model Used in This Lesson

The following examples share one model in package `com.example.employee`. `Employee` has a `Department` and a list of `Assignment`s; each `Assignment` references a `Project`.

`Department` entity:

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

`Project` entity:

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

`Assignment` entity as a collection element:

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

`Employee` entity declaring named graphs:

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

Associations are declared LAZY to express per-query loading needs. The `EntityGraph` definitions on `Employee` provide two named graphs: one loading only `Department` and one loading `Department` together with `Assignments`/`Project`.

In a real application, add helper methods to manage both sides of the association if the domain adds/removes `Assignment`s. The read examples below only need the declared mappings and getters.

## 4. What Is a Named EntityGraph?

A Named `EntityGraph` is a fetch plan declared ahead of time via the `@NamedEntityGraph` annotation on an entity or via XML metadata.

Simple graph example:

~~~java
@NamedEntityGraph(
    name = "Employee.withDepartment",
    attributeNodes = @NamedAttributeNode("department")
)
~~~

The graph name is `Employee.withDepartment`. The `department` attribute node references the Java property name in the entity, not the `department_id` column name.

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

1. Load `Employee`.
2. Load `Employee`'s `Department`.
3. Load the `assignments` collection.
4. For each `Assignment`, load `Project`.

Subgraphs allow declaring deeper properties on associations or embedded attributes. If multi-level nested properties need to be loaded, corresponding chained subgraphs can be declared.

Named graphs are registered in the persistence unit and can be reused across multiple repository methods or `EntityManager` queries.

## 5. Attribute Nodes and Subgraphs

An attribute node identifies a property to fetch directly from the root entity. For to-one associations, the node loads the related entity; for collections, it loads the collection and elements according to the graph.

A subgraph describes the next graph for the association's target type:

~~~java
@NamedAttributeNode(
    value = "assignments",
    subgraph = "assignment-project"
)
~~~

The name `assignment-project` points to:

~~~java
@NamedSubgraph(
    name = "assignment-project",
    attributeNodes = @NamedAttributeNode("project")
)
~~~

Inside `Assignment`'s subgraph, `project` is an attribute of `Assignment`. Do not write the path `assignments.project` inside `@NamedSubgraph`; the subgraph already establishes the `Assignment` entity context.

Node names must match persistent attributes of the corresponding entity. Invalid names are typically caught when the provider initializes or uses the graph.

Do not put every association into a graph. Overly broad graphs can load multiple collections, produce large SQL, increase memory usage, and cause unnecessary hydration overhead.

## 6. FETCH Graph vs. LOAD Graph

JPA defines two types of `EntityGraph`:

- FETCH graph: attributes specified in the graph are treated as EAGER for this load; unspecified attributes are treated as LAZY.
- LOAD graph: attributes specified in the graph are treated as EAGER; unspecified attributes follow the entity's fetch mapping.

In both cases, the provider may still load extra data outside the graph if needed to execute the query or per implementation behavior; a graph specifies the minimum fetch plan to satisfy, not a guarantee that the SQL loads strictly those attributes alone.

Example:

~~~java
@EntityGraph(
    value = "Employee.withDepartment",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<Employee> findByEmail(String email);
~~~

`FETCH` fits when a method needs a specific fetch plan for a use case and wants other attributes treated as LAZY for that load.

`LOAD` example:

~~~java
@EntityGraph(
    value = "Employee.withDepartment",
    type = EntityGraph.EntityGraphType.LOAD
)
Optional<Employee> findByEmail(String email);
~~~

`LOAD` adds `Department` to the fetch plan while other attributes continue following the entity's fetch type mappings. If an association is mapped EAGER, a `LOAD` graph does not turn it into LAZY just because the graph omits it.

In Spring Data JPA, `EntityGraphType` defaults to `FETCH` if `type` is omitted. Specify `type` explicitly when you want readers to see the fetch plan intent clearly.

## 7. Attaching a Named Graph to a Derived Query Method

Spring Data JPA provides the `org.springframework.data.jpa.repository.EntityGraph` annotation for repository methods.

Repository:

~~~java
package com.example.employee;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
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

    @EntityGraph(
        value = "Employee.withDepartment",
        type = EntityGraph.EntityGraphType.LOAD
    )
    List<Employee> findByActiveTrue();
}
~~~

`findByEmail` is a derived query. Spring Data generates the predicate from the method name while applying the named graph `Employee.withDepartment` as the fetch plan.

`findDetailedById` uses the `detail` named graph. `findByActiveTrue` finds `Employee`s with `active = true` and applies the `Department` graph with `LOAD` semantics.

`EntityGraph` does not change filter criteria. Removing the annotation from `findByEmail` still finds the same `Employee`, though the fetch plan may differ.

## 8. Using Dynamic Graphs via attributePaths

If you only need a graph for a single method, declaring a named graph on the entity is unnecessary. You can use `attributePaths`:

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

Spring Data constructs an ad hoc entity graph from the declared attribute paths. This form is commonly called a dynamic `EntityGraph` in the context of repository methods.

When `attributePaths` is provided, Spring Data treats it as a dynamically created graph; the named graph name in `value` is no longer the graph source used. Therefore, pick one clear approach:

- Use `value` to reference a declared named graph.
- Use `attributePaths` to create a method-specific graph.

Do not declare both `value` and `attributePaths` expecting the two graphs to be merged.

Paths use Java property names. For example, `assignments.project` navigates from `Employee` to the `assignments` collection, then to `Assignment`'s `project` property.

## 9. Nested Attribute Paths and Path Limits

With dynamic graphs, Spring Data supports dot-notation paths to express nested associations:

~~~java
@EntityGraph(attributePaths = {
    "department",
    "assignments.project"
})
List<Employee> findByDepartment_Name(String departmentName);
~~~

This method illustrates combining a predicate traversing `Department` with a fetch graph loading `Department` and each `Assignment`'s `Project`.

Paths must be valid in the entity model. For embedded objects, corresponding nested paths can be used. For collection associations, consider collection sizes and graph depth.

A multi-level graph may generate multiple SQL joins or supplementary queries depending on the provider. Do not assume every graph translates to a single SQL statement.

## 10. Combining EntityGraph with @Query

`EntityGraph` can also be attached to repository methods with `@Query`. JPQL handles filtering, while the graph handles association loading.

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

JPQL does not need `join fetch e.department` because the graph already specifies the fetch plan. The predicate can still reference `e.department.name` to filter by department.

If a query needs a `JOIN` for filtering without loading the association, write a regular `JOIN` in JPQL and omit the association from the graph. If loading is needed, the graph can supply the fetch plan.

Avoid writing both `join fetch e.department` in JPQL and declaring the same association in a graph just to load the same data twice. Redundant combinations make queries harder to read and provider-dependent.

## 11. EntityGraph Does Not Replace JOIN or EXISTS for Filtering

Graph example:

~~~java
@EntityGraph(attributePaths = {"department"})
List<Employee> findByActiveTrue();
~~~

The graph does not mean "fetch only `Employee`s that have a `Department`". It requests loading `Department` for the `Employee`s found. An `Employee` with a null `department` can still be returned if the predicate does not exclude it.

If you want only `Employee`s belonging to the `Engineering` department, you must include a predicate:

~~~java
List<Employee> findByActiveTrueAndDepartment_Name(String name);
~~~

Or use `@Query` with the corresponding `WHERE` condition.

Similarly, if you want `Employee`s with at least one `Assignment` for a specific `Project`, you need a predicate via join/`exists`/Specification. Putting `assignments.project` in the graph only loads related data; it does not filter `Employee`s by `Project`.

## 12. EntityGraph and Repository Return Types

`EntityGraph` fits best with methods returning entities or collections of entities:

| Return Type | Usage |
|---|---|
| Optional<Employee> | Loads at most one Employee with associations |
| Employee | Loads one Employee per method contract |
| List<Employee> | Loads a list of Employees with the graph |
| Page<Employee> | Can use a graph; take special care if the graph contains a collection |
| Slice<Employee> | Can use a graph; still evaluate collection-fetch impact |
| DTO projection | Graph usually unnecessary since query selects a projection |
| Scalar value | EntityGraph has no root entity association to load |

For projections, select only the needed fields. Do not rely on `EntityGraph` to force-load associations for a DTO constructor expression or scalar query; fetch plans have clear meaning when the result is an entity.

## 13. EntityGraph with Page and Pageable

A graph can be attached to a method returning `Page`:

~~~java
@EntityGraph(attributePaths = {"department"})
Page<Employee> findByActiveTrue(Pageable pageable);
~~~

`Department` is a to-one relationship, so it typically does not multiply `Employee` rows when mapping cardinality is right. This is usually suitable for pagination.

Be careful when the graph includes a collection:

~~~java
@EntityGraph(attributePaths = {"assignments"})
Page<Employee> findByActiveTrue(Pageable pageable);
~~~

The provider may load the collection via a `JOIN`. One `Employee` with multiple `Assignment`s produces multiple SQL rows; database result limits may no longer match the number of `Employee`s. Hibernate may have to paginate in memory or emit warnings depending on version/configuration.

`EntityGraph` does not guarantee safe collection pagination. If you need a `Page` of `Employee`s with all `Assignment`s, consider:

1. Paginating `Employee` IDs first.
2. Loading `Employee`s with `Assignment`s for that set of IDs via a separate query without `Pageable`.
3. Restoring the page's ID order.

If the UI only needs the `Assignment` count, use a DTO projection with a `count` aggregate instead of fetching the whole collection.

## 14. EntityGraph and Count Queries

`Page<T>` may require both a content query and a count query. The count query only needs to count matching root entities; it does not need to load `Department`, `Assignment`, or `Project`.

`EntityGraph` is a fetch plan for reading entities. Do not add association fetches to a count query by writing JPQL fetch joins inside `countQuery`. For paginated queries with collection graphs, inspect the content SQL and count SQL separately.

If the content query filters over a collection, the count query must preserve an equivalent predicate. For example, finding `Employee`s with at least one `Assignment` for a `Project`:

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

You can attach a `Department` graph to the method if you need `Department` loaded for the content entities. The `EXISTS` predicate stays intact and the count query counts `Employee`s under the same condition.

## 15. EntityGraph with To-One and To-Many

To-one relationships:

- `@ManyToOne`
- `@OneToOne`

Typically each root entity links to at most one target entity. To-one fetch graphs carry less risk of multiplying root rows.

To-many relationships:

- `@OneToMany`
- `@ManyToMany`

One root can have many related elements. Collection fetch graphs can generate multiple SQL rows per root and increase data transfer/hydration overhead.

If a graph loads multiple collections, cost can grow as the product of element counts. Hibernate can also hit `MultipleBagFetchException` when simultaneously fetching multiple bag collections in a single query.

Do not add every collection to a detail graph just because you can. Design graphs per screen needs and consider batch fetching or separate queries.

## 16. EntityGraph and N+1

N+1 happens when an application loads N root entities and then triggers an additional query per entity when accessing a LAZY association.

Example:

~~~java
List<Employee> employees = repository.findByActiveTrue();

for (Employee employee : employees) {
    System.out.println(employee.getDepartment().getName());
}
~~~

If `Department` is unloaded and the provider cannot batch queries, the loop can generate many additional SQL statements.

Using `EntityGraph`:

~~~java
@EntityGraph(attributePaths = "department")
List<Employee> findByActiveTrue();
~~~

The graph requests `Department` to be loaded in the query's fetch plan. The provider may use a join or another strategy, but the application no longer relies on per-entity access to load each `Department`.

`EntityGraph` helps control the fetch plan for specified associations; it does not guarantee all N+1 disappears. If the loop also accesses `assignments.project` while the graph only covers `Department`, the remaining associations can still trigger additional queries.

Check the actual SQL and statement counts to confirm effectiveness.

## 17. EntityGraph Compared to JOIN FETCH

| Criterion | EntityGraph | JOIN FETCH |
|---|---|---|
| Purpose | Declare fetch plan | Declare fetch inside JPQL |
| Location | Annotation, named graph, or EntityManager hint | JPQL query |
| Decoupled from predicate | Yes; graph does not filter data | JOIN FETCH lives inside the query |
| Reusability | Named graph usable across multiple queries | Typically tied to a specific JPQL query |
| Nested associations | Attribute nodes and subgraphs | Multiple fetch joins |
| Actual SQL | Provider decides execution strategy | Provider translates fetch join to corresponding SQL join |
| Pagination with collections | Can still encounter row multiplication | Explicit row multiplication risk |
| DTO projection | Usually no graph needed | Constructor projection can pair with regular joins |

`EntityGraph` often clarifies the separation between predicate and fetch plan. `JOIN FETCH` fits when a specific query needs to show fetched associations directly in JPQL.

There is no rule that `EntityGraph` is always more efficient than `JOIN FETCH`. Both should be verified with SQL and realistic data.

## 18. Named Graphs in XML

Besides annotations, JPA allows declaring named entity graphs in `orm.xml`. This is useful when a team wants to separate mapping/fetch metadata from entity code.

Example file `src/main/resources/META-INF/orm.xml`:

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

If the same graph name is declared in both annotations and XML, avoid metadata conflicts. Choose one clear definition source per graph and verify the mapping file is loaded by the provider.

## 19. Using EntityGraph Directly with EntityManager

JPA `EntityManager` supports building dynamic graphs and passing them via query hints.

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

- `jakarta.persistence.fetchgraph`: applies `FETCH` graph semantics.
- `jakarta.persistence.loadgraph`: applies `LOAD` graph semantics.

JPA 2.x uses the `javax.persistence` namespace; Jakarta Persistence 3.x uses `jakarta.persistence`. Spring Boot 3+ generally uses the Jakarta namespace. Check your project's version before copying code.

## 20. Combining EntityGraph and Repository Methods Flexibly

One repository can have multiple methods for different use cases:

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

This interface brings together illustrative methods; each method has its own predicate while choosing a named graph or dynamic graph as needed.

Note that if a repository overrides an inherited method with the same signature to attach an annotation, do so intentionally. Do not declare methods with identical signatures hoping to define different fetch plans; Java does not allow overloading based solely on annotations.

## 21. Testing EntityGraph with PersistenceUnitUtil

Do not assert only on association values after calling a repository, because calling getters can trigger lazy loading inside the test transaction. Use `PersistenceUnitUtil.isLoaded()` to verify that the association was already loaded immediately after the query.

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
}
~~~

The test uses the named graph `Employee.withDepartment` on `findByEmail`. After `clear()`, the entity is no longer in the previous persistence context. `isLoaded` verifies the association was loaded by the query.

For the detail graph, you can assert:

~~~java
assertThat(util.isLoaded(found, "assignments")).isTrue();
~~~

And for each `Assignment`:

~~~java
assertThat(util.isLoaded(assignment, "project")).isTrue();
~~~

Checking nested associations must be done while the persistence context is still open. If you want to test SQL statement counts, use a datasource proxy or Hibernate statistics to verify query counts, because `isLoaded` only checks association state and does not prove query optimality.

## 22. Common Mistakes

| Symptom | Cause | Solution |
|---|---|---|
| Named graph not found | Wrong graph name or metadata not loaded | Check name and mapping |
| Attribute node error | Used SQL column name instead of Java property | Use persistent property name |
| Nested subgraph does not work | Subgraph declared wrong target entity or wrong path name | Check association and target type |
| EntityGraph does not filter results | Graph only controls the fetch plan | Add WHERE/JOIN/EXISTS predicate |
| N+1 still occurs | Graph missed an accessed association | Add needed paths or batch fetching |
| Query loads too much data | Graph includes multiple collections or too many levels | Narrow graph to the use case |
| Page is slow with collection graph | Collection fetch multiplies rows or paginates in memory | Paginate IDs first then fetch separately |
| Count query affected by joins | To-many JOIN predicate multiplies roots | Use EXISTS or count distinct roots |
| DTO does not use graph as expected | Projection does not return root entity graph | Choose proper projection, do not rely on graph |
| Duplicate EntityGraph and JOIN FETCH | Same association declared twice | Pick one clear fetch strategy |
| MultipleBagFetchException | Fetching multiple bag collections in one query | Split queries or batch fetch |
| LazyInitializationException | Accessing association outside transaction | Load inside transaction or return DTO |
| LOAD graph still loads unlisted association | Association mapping is EAGER | Understand LOAD vs. FETCH difference |
| FETCH graph still shows extra fields loaded | Provider may fetch extra outside graph | Graph is not an absolute minimal SQL guarantee |

## 23. Practical Design Principles

- Keep associations LAZY as a sensible default and select fetch plans per use case.
- Use named graphs when a fetch plan is reused across multiple repository methods.
- Use `attributePaths` for small graphs specific to one method.
- Use `FETCH` when you want unlisted attributes treated as LAZY for that load; use `LOAD` when you want to retain mapping fetch types for unlisted attributes.
- Keep predicates in derived queries, `@Query`, Specifications, or Criteria; graphs manage only the fetch plan.
- Attach graphs to methods returning entities when associations are genuinely needed.
- Do not include collections in every detail graph.
- Inspect SQL and N+1 rather than assuming a graph always emits a single JOIN.
- Be cautious with `Page`/`Slice` when a graph includes collections.
- Separate ID pagination and collection fetching if you need a page of roots with full collections.
- Use DTO projections if only a few fields or aggregated values are needed.
- Avoid declaring the same association in both `EntityGraph` and `JOIN FETCH` unnecessarily.
- Test loaded associations with `PersistenceUnitUtil` and measure query counts.
- Verify Jakarta/Javax namespaces against your project's JPA version.

## 24. Self-Assessment Checklist

- [ ] Can explain the difference between a predicate and a fetch plan.
- [ ] Can declare a named graph with `@NamedEntityGraph`.
- [ ] Can use `@NamedAttributeNode` for root attributes.
- [ ] Can use `@NamedSubgraph` for nested associations.
- [ ] Can distinguish `FETCH` graph and `LOAD` graph.
- [ ] Can use `@EntityGraph(value = ...)` to reference a named graph.
- [ ] Can use `attributePaths` to create a dynamic graph.
- [ ] Understands `attributePaths` takes precedence when declared and the graph name is no longer the graph source.
- [ ] Can combine `EntityGraph` with derived queries.
- [ ] Can combine `EntityGraph` with `@Query`.
- [ ] Understands graphs do not add filter predicates automatically.
- [ ] Can choose appropriate graphs for to-one and to-many.
- [ ] Recognizes risks of collection fetching with `Page`/`Slice`.
- [ ] Can distinguish `EntityGraph` from `JOIN FETCH`.
- [ ] Knows how to use `EntityManager` `fetchgraph`/`loadgraph` hints.
- [ ] Can verify associations using `PersistenceUnitUtil.isLoaded()`.
- [ ] Measures SQL/query counts to detect N+1.
- [ ] Uses DTO projections or batch fetching when appropriate.

## 25. Conclusion

`EntityGraph` allows Spring Data JPA to select a fetch plan per query method. Named graphs suit reusable fetch plans; `attributePaths` suits small graphs declared directly on a repository method. `FETCH` and `LOAD` differ in how they handle attributes not listed in the graph.

When combining `EntityGraph` with derived queries or `@Query`, keep roles distinct: the query determines which entities match, and the graph determines which associations to load. Be especially careful with collections in `Page`/`Slice` because a graph does not eliminate row multiplication or in-memory pagination. Inspect SQL, association states, and query counts on realistic data to choose a right-sized fetch plan.