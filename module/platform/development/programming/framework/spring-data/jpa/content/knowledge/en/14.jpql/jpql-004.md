# INNER JOIN, LEFT JOIN, and ON Conditions

## Objectives

After this lesson, you will be able to:

- Explain how JPQL joins entities through mapped associations.
- Distinguish the results of `INNER JOIN` and `LEFT JOIN`.
- Use `ON` to place conditions directly in the join clause and understand how it differs from `WHERE`.
- Predict when a left-side record is retained even without a matching right-side record.
- Handle duplicate results caused by collection joins using `DISTINCT` or an appropriate projection.
- Distinguish a join used for filtering/querying from `JOIN FETCH` used for loading associations.
- Write repository queries and integration tests that verify join semantics.

## 1. What is JOIN in JPQL?

JPQL queries entities and Java attributes rather than SQL table and column names directly. When an entity has an association such as `@ManyToOne`, `@OneToMany`, `@OneToOne`, or `@ManyToMany`, JPQL can join across that association path.

Domain example:

- A `Department` has many `Employee`s.
- Each `Employee` belongs to one `Department`.
- `Department` has an `enabled` attribute.
- `Employee` has an `active` attribute.

In Java, the relationship can be mapped as follows:

~~~java
@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private boolean enabled;

    @OneToMany(mappedBy = "department", cascade = CascadeType.PERSIST)
    private List<Employee> employees = new ArrayList<>();

    protected Department() {
    }

    public Department(String name, boolean enabled) {
        this.name = name;
        this.enabled = enabled;
    }

    public void addEmployee(Employee employee) {
        employees.add(employee);
        employee.setDepartment(this);
    }

    public Long getId() {
        return id;
    }
}
~~~

~~~java
@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "department_id", nullable = false)
    private Department department;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private boolean active;

    protected Employee() {
    }

    public Employee(String name, boolean active) {
        this.name = name;
        this.active = active;
    }

    void setDepartment(Department department) {
        this.department = department;
    }
}
~~~

In this mapping, `Employee.department` is the owning side and holds the foreign key `department_id`. `Department.employees` is the inverse side with `mappedBy = "department"`.

A JPQL join navigates through the Java attribute name:

~~~jpql
select d
from Department d
join d.employees e
~~~

- `Department` is the entity name.
- `d` is the identification variable (alias) for `Department`.
- `d.employees` is the association path.
- `e` is the alias for each joined `Employee`.

The table name `departments` and column name `department_id` do not appear in JPQL. The provider relies on the mapping to generate the corresponding SQL.

## 2. INNER JOIN

`INNER JOIN` returns only rows that have matching records on both sides.

~~~jpql
select d, e
from Department d
inner join d.employees e
~~~

The query above returns only Departments that have at least one Employee. Departments without any Employees are excluded from the results.

It can be written concisely:

~~~jpql
select d, e
from Department d
join d.employees e
~~~

In JPQL, `JOIN` without `LEFT` defaults to an inner join.

### Sample Data

Suppose we have the following data:

**departments**

| id | name |
|---:|---|
| 1 | Engineering |
| 2 | Finance |
| 3 | Legal |

**employees**

| id | department_id | name | active |
|---:|---:|---|---|
| 10 | 1 | An | true |
| 11 | 1 | Binh | false |
| 12 | 2 | Chi | true |

Query:

~~~jpql
select d.name, e.name
from Department d
inner join d.employees e
~~~

The result contains these pairs:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Engineering | Binh |
| Finance | Chi |

Legal does not appear because it has no linked Employee.

### When to Use INNER JOIN?

Use inner join when business logic only cares about left-side entities that have matching associations. For example:

- Find orders that have at least one line item.
- Find customers that have at least one transaction.
- Find departments that have employees.
- Filter articles that have a valid author.

If the association is nullable or the collection can be empty, an inner join excludes entities without a corresponding relationship.

## 3. LEFT JOIN

`LEFT JOIN` preserves all rows on the left side. If there is no matching record on the right side, right-side attributes evaluate to null in the result.

~~~jpql
select d, e
from Department d
left join d.employees e
~~~

With the sample data, the result contains:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Engineering | Binh |
| Finance | Chi |
| Legal | null |

Legal still appears even though it has no Employee.

You can write `LEFT OUTER JOIN`; the `OUTER` keyword is optional:

~~~jpql
select d
from Department d
left outer join d.employees e
~~~

### LEFT JOIN with a Single-Valued Association

LEFT JOIN is also useful when joining a nullable single-valued association.

For example, each `PurchaseOrder` may optionally have a `Customer`:

~~~jpql
select o, c
from PurchaseOrder o
left join o.customer c
~~~

Orders are still returned when they have no linked Customer; alias `c` will be null in those rows.

### When to Use LEFT JOIN?

Use left join when you need to preserve all root entities, even when the association does not exist or has no matching records. Common examples:

- List all departments, including those with no employees yet.
- List all customers, including those who have not placed any orders.
- Report all products and sales, including unsold products.
- Fetch parent records along with child details if present, without dropping parents when children do not exist.

## 4. Where Does the ON Condition Go?

Since Jakarta Persistence 2.1, JPQL supports `ON` to add conditions to a join. This condition is evaluated while matching right-side records to the left side.

For example, join only active Employees:

~~~jpql
select d, e
from Department d
left join d.employees e on e.active = true
~~~

With the sample data:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Finance | Chi |
| Legal | null |

Employee Binh is excluded from the match because `active = false`. Department Engineering still appears because LEFT JOIN retains left-side records. Legal also still appears even without an Employee.

### ON Supplements the Relationship Condition

When joining over an association like `d.employees`, the mapping already defines how the two entities relate. The `ON` condition adds filtering criteria for the right-side records; it does not replace the foreign key mapping.

In the Department/Employee example, the base relationship remains:

~~~text
Employee.department_id = Department.id
~~~

The additional condition is:

~~~text
Employee.active = true
~~~

The provider combines both conditions when generating the SQL join.

Parameters can be used:

~~~java
@Query("""
    select d
    from Department d
    left join d.employees e on e.active = :active
    where d.enabled = true
    """)
List<Department> findEnabledDepartmentsWithEmployeeState(
    @Param("active") boolean active
);
~~~

The JPQL parameter name must match `@Param`. An ON condition can reference attributes of the joined alias, attributes of the left side, and query parameters.

## 5. How Does ON Differ from WHERE?

This is the most important point when using LEFT JOIN.

- `ON` decides which right-side records get matched with left-side records.
- `WHERE` filters the resulting rows after the join has been performed.

Compare two queries:

**Query A — condition inside ON**

~~~jpql
select d.name, e.name
from Department d
left join d.employees e on e.active = true
~~~

Results:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Finance | Chi |
| Legal | null |

Engineering still appears despite having an inactive Employee, though only the active Employee is matched. Legal appears with a null `employeeName`.

**Query B — condition inside WHERE**

~~~jpql
select d.name, e.name
from Department d
left join d.employees e
where e.active = true
~~~

Results:

| departmentName | employeeName |
|---|---|
| Engineering | An |
| Finance | Chi |

Legal is eliminated because `e.active` is null on the row produced by LEFT JOIN, and the condition `e.active = true` does not evaluate to true. Engineering retains only An's row.

Placing a right-side condition in WHERE typically causes a LEFT JOIN to behave like an INNER JOIN for that condition. If you want to keep parent rows when no matching child exists, put the right-side condition in ON.

### Left-Side Conditions Can Still Stay in WHERE

For example, fetch only enabled Departments while keeping a department even if it has no active Employees:

~~~jpql
select d, e
from Department d
left join d.employees e on e.active = true
where d.enabled = true
~~~

The `d.enabled` condition filters the left-side entity. The `e.active` condition controls right-side matching.

Not every condition belongs in ON. Classify conditions by business semantics: conditions determining which related records are paired go in ON; conditions determining which final rows are kept go in WHERE.

## 6. Duplicate Results When Joining a Collection

A `Department` can have multiple `Employee`s. When joining a collection, a single `Department` can appear in multiple result rows.

Example:

~~~jpql
select d
from Department d
join d.employees e
~~~

If Engineering has three matching employees, the relational query produces three rows for Engineering. The JPQL result may contain the same `Department` entity multiple times.

If the goal is a list of unique Departments, use:

~~~jpql
select distinct d
from Department d
join d.employees e
~~~

If the goal is to retrieve each Department/Employee pair, do not use DISTINCT as it would collapse detail rows (if projecting entities/pairs appropriately, wait—let's stick strictly to the source sentence: "If the goal is to retrieve each Department/Employee pair, do not use DISTINCT to remove detail rows.").

For count queries, clarify whether you need to count joined rows or parent entities:

~~~jpql
select count(e)
from Department d
join d.employees e
~~~

Counts the number of joined Employees.

~~~jpql
select count(distinct d.id)
from Department d
join d.employees e
~~~

Counts the number of Departments with at least one matching Employee.

When using `Page<T>` with a collection join, the count query must be designed to count the root target accurately, often requiring `count(distinct d.id)`. Do not rely on a default count if the join duplicates rows and skews page totals.

## 7. JOIN for Filtering vs. JOIN FETCH for Loading Associations

A regular JOIN helps query and filter by an association. It does not mean the entity's collection is initialized in the persistence context.

Example:

~~~jpql
select d
from Department d
join d.employees e
where e.active = true
~~~

The query uses `Employee` to determine which `Department`s match. It does not instruct JPA to load all of `d.employees` into the collection.

If you need to load the association along with the entity, use a fetch join:

~~~jpql
select distinct d
from Department d
left join fetch d.employees
where d.enabled = true
~~~

`LEFT JOIN FETCH` loads the collection alongside `Department`, including Departments with no Employees. This serves a different purpose than a projection join or a filtering-only join.

Notes:

- Fetch join is used to initialize associations of the selected entity; do not use it as a regular projection join.
- Portable JPQL fetch joins do not declare an alias and do not take an `ON` condition like regular association joins.
- Collection fetch joins combined with pagination can duplicate rows and force the provider to paginate in memory or emit warnings.
- Avoid fetching multiple large collections simultaneously if it risks producing a Cartesian product or exploding row counts.

If you need to filter by child records while still loading entities, consider splitting queries, using an appropriate EntityGraph, or using a DTO projection. Avoid letting a fetch join leave a collection in memory containing only a subset of items that other code mistakes for the complete collection.

## 8. Projections When Data Is Needed from Both Sides

If a screen only needs Department names and Employee names, loading the entire entity graph is unnecessary. Spring Data JPA supports interface projections with aliases in JPQL.

Projection:

~~~java
public interface DepartmentEmployeeRow {
    Long getDepartmentId();
    String getDepartmentName();
    String getEmployeeName();
}
~~~

Repository:

~~~java
public interface DepartmentRepository
        extends JpaRepository<Department, Long> {

    @Query("""
        select
            d.id as departmentId,
            d.name as departmentName,
            e.name as employeeName
        from Department d
        left join d.employees e on e.active = true
        where d.enabled = true
        order by d.id, e.name
        """)
    List<DepartmentEmployeeRow> findEnabledDepartmentEmployeeRows();
}
~~~

Projection results might include:

| departmentId | departmentName | employeeName |
|---:|---|---|
| 1 | Engineering | An |
| 2 | Finance | Chi |
| 3 | Legal | null |

`employeeName` can be null because LEFT JOIN preserves the Department even when no active Employee exists. A Department with multiple active Employees will produce multiple projection rows.

Projections reduce data loaded and clarify the reporting contract. If nested objects or complex aggregations are needed, use DTO constructor expressions, interface projections, or native queries depending on requirements.

## 9. Joining Across Multiple Associations

JPQL can join across multiple association paths:

~~~jpql
select o, c, a
from PurchaseOrder o
join o.customer c
left join c.address a
where o.status = :status
~~~

In this example:

- Order must have a Customer because an inner join is used.
- Address may not exist, so a left join is used.
- `o.status` filters the root entity.

Each alias represents a part of the query. Choose short yet meaningful aliases, such as `o`, `c`, `a`, `line`, `product`.

When joining multiple collections, row counts can grow by the product of element counts. For example, an Order with 4 lines and 3 payments joined across both collections can produce up to 12 rows for the same Order. This impacts performance, counts, and pagination.

If you only need to check whether an association exists, an `EXISTS` subquery is sometimes preferable to a collection join:

~~~jpql
select d
from Department d
where exists (
    select e.id
    from Employee e
    where e.department = d
      and e.active = true
)
~~~

EXISTS checks for at least one active Employee without forcing the outer query to produce a row per Employee. Choose JOIN or EXISTS based on the required output and database execution plan.

## 10. Integration Test Example

The following test verifies that `LEFT JOIN ON` keeps Departments with no active Employees and matches only active Employees.

~~~java
package com.example.department;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class DepartmentRepositoryTest {

    @Autowired
    DepartmentRepository repository;

    @Test
    void leftJoinOnKeepsDepartmentWithoutActiveEmployee() {
        Department engineering = new Department("Engineering", true);
        engineering.addEmployee(new Employee("An", true));
        engineering.addEmployee(new Employee("Binh", false));

        Department legal = new Department("Legal", true);

        repository.saveAll(List.of(engineering, legal));
        repository.flush();

        List<DepartmentEmployeeRow> rows =
                repository.findEnabledDepartmentEmployeeRows();

        assertEquals(2, rows.size());

        assertEquals("Engineering", rows.get(0).getDepartmentName());
        assertEquals("An", rows.get(0).getEmployeeName());

        assertEquals("Legal", rows.get(1).getDepartmentName());
        assertNull(rows.get(1).getEmployeeName());
    }
}
~~~

The test assumes the two entities and projection/repository are declared as in the previous examples, `Department.employees` has cascade `PERSIST`, and the repository method sorts by department ID. The test database must support the mappings used.

You can write a comparison test with the condition in `WHERE`:

~~~jpql
select d.name, e.name
from Department d
left join d.employees e
where e.active = true
~~~

In that case, Legal will not appear. A comparison test helps catch regressions where a condition is accidentally moved from `ON` to `WHERE` during query refactoring.

## 11. Common Errors

| Symptom | Cause | Solution |
|---|---|---|
| Parent missing when there are no children | Used INNER JOIN or implicit join | Use LEFT JOIN when parent must be kept |
| LEFT JOIN still drops parent without children | Placed right-side condition in WHERE | Move right-side matching condition to ON |
| Parent appears multiple times | Collection join creates multiple rows | Use DISTINCT if only unique parent entities are needed |
| Page count exceeds parent count | Count query counts joined rows instead of parents | Use `count(distinct id)` |
| Join does not load collection | Regular JOIN only participates in the query | Use fetch join or EntityGraph if loading is truly needed |
| Broken pagination or warning when fetching collection | Collection fetch join multiplies rows | Paginate IDs first, then load associations in a batch/second query |
| JPQL rejects table/column names | JPQL uses entity names and Java properties | Write entity names and property paths |
| ON unsupported in old runtime | Older JPA/provider version before ON support | Use a JPA/provider version supporting JPQL ON or redesign the query |
| Row multiplication when joining multiple collections | Collection cardinalities multiply together | Split queries, use EXISTS, or use an appropriate projection |

## 12. Process for Choosing JOIN, LEFT JOIN, and ON

When writing a query, answer in order:

1. Which root entity must always appear in the results?
2. If there is no association, should the root record be excluded?
3. If an association exists but does not satisfy the condition, should the root record be kept?
4. Do you need the root entity, entity pairs, or a projection?
5. Does a collection join produce multiple rows for the same root entity?
6. Does the association need to be loaded into the persistence context, or only used for filtering?
7. If using `Page`, does the count query count the root entity accurately?

Practical rules:

- Use INNER JOIN when only root entities with matching associations are needed.
- Use LEFT JOIN when root entities must be kept even without matching associations.
- Use ON for conditions determining which right-side associations are paired.
- Use WHERE for conditions filtering the final results.
- Use DISTINCT or count distinct when root entity deduplication is required.
- Use FETCH when loading associations; do not confuse fetch joins with projection joins.
- Use EXISTS when only existence needs to be checked without multiplying result rows.

## Pre-Merge Checklist

- [ ] JPQL uses accurate entity names and property paths.
- [ ] Association paths and aliases are clearly defined.
- [ ] INNER JOIN/LEFT JOIN matches whether root entities should be kept or dropped.
- [ ] ON and WHERE conditions are placed with the right semantics.
- [ ] Collection joins have been evaluated for potential row multiplication.
- [ ] DISTINCT and count queries count the intended target objects accurately.
- [ ] Regular JOIN and JOIN FETCH are used for their respective purposes.
- [ ] Pagination is not distorted by collection fetch joins.
- [ ] Projections handle null values on the LEFT JOIN side.
- [ ] Integration tests cover cases with associations, without associations, and with associations failing ON.

## Conclusion

INNER JOIN keeps only root entities with matching associations; LEFT JOIN preserves the entire left side and yields null for the right side when no match exists. ON adds conditions directly to the join pairing, whereas WHERE filters rows after joining. With LEFT JOIN, putting right-side conditions in WHERE eliminates null rows and defeats the purpose of preserving the left side. Clarify the desired result shape, control collection duplicates, distinguish JOIN from JOIN FETCH, and test cases without associations.