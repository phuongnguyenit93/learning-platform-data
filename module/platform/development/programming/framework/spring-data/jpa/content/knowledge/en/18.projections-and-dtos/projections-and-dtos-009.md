# Projections for Derived Queries, JPQL, and Native SQL in Spring Data JPA

## Objectives

After this lesson, you can choose the right projection type when a repository needs to return partial data; declare interface projections and class/record DTOs for derived queries; write projections with JPQL `@Query`; map native SQL results using aliases or constructor mappings; use closed, open, nested, and dynamic projections; and evaluate the limitations, performance, and compatibility of each approach.

The examples use Java 17+, Spring Boot 3+, Spring Data JPA, and Jakarta Persistence (`jakarta.persistence.*`). The snippets belong to the same illustrative package; if your project already has a corresponding entity or repository, add the projections and methods to your existing structure rather than creating duplicate classes.

## 1. What Is a Projection and When Should You Use It?

An entity typically holds many attributes and may have relationships to several other entities. Yet a list screen, report, or API often needs only a few fields. Always loading the full entity can fetch more data than necessary, pulling in joins, object hydration, and unneeded memory overhead.

A **projection** defines the shape of data a query should return. Instead of returning `Customer` with all its persistent state, a repository can return `id`, `firstName`, `lastName`, and `email` as a view or DTO.

Projections are useful when:

- Displaying list tables or summary cards needing only a few fields.
- Returning read data for REST APIs without exposing entities.
- Building reports, statistics, or aggregated query results.
- Reducing the volume of data transferred from the database to the application.
- Keeping a use case's data contract independent of persistence entities.

Projections do not replace entities in every case. When you need to mutate state, use dirty checking, cascading, or navigate domain relationships, entities are usually more appropriate. DTOs/projections primarily serve reading data in a specific shape.

## 2. Example Model Used Throughout the Lesson

The `Customer` entity has many fields, while a customer name list needs only a subset:

```java
package com.example.learning.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "first_name", nullable = false)
    private String firstName;

    @Column(name = "last_name", nullable = false)
    private String lastName;

    @Column(nullable = false)
    private String email;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {
    }

    public Customer(String firstName, String lastName, String email, boolean active) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.active = active;
    }

    public Long getId() { return id; }
    public String getFirstName() { return firstName; }
    public String getLastName() { return lastName; }
    public String getEmail() { return email; }
    public boolean isActive() { return active; }
}
```

Suppose the `customers` table has columns `id`, `first_name`, `last_name`, `email`, and `active`. The Java property name is `firstName`, while the SQL column name is `first_name`; JPQL uses property names, while native SQL uses column names.

## 3. Interface Projections

An interface projection is a simple way to describe the getters a result must provide. Spring Data JPA creates a proxy implementing that interface during querying.

```java
package com.example.learning.customer;

public interface CustomerNameView {
    Long getId();
    String getFirstName();
    String getLastName();
    String getEmail();
}
```

The repository can return this interface from a derived query:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<CustomerNameView> findByActiveTrueOrderByLastNameAscFirstNameAsc();
}
```

The method name is parsed like a normal derived query: filter `active = true`, sort by `lastName` then `firstName`. The `CustomerNameView` return type asks Spring Data to supply the attributes declared by the interface.

### 3.1. Closed Projections

A closed projection declares only accessors corresponding to attributes of the aggregate/entity:

```java
public interface CustomerNameView {
    Long getId();
    String getFirstName();
    String getLastName();
}
```

Spring Data knows the exact properties requested and can optimize data selection for compatible queries. Actual optimization also depends on the query, provider, mapping, and accessed relationships; inspect the generated SQL if reducing columns is an important performance requirement.

Closed projections fit small views with stable shapes. When you add a getter, you change the data requested by the projection and may cause the query to require more columns or joins.

### 3.2. Default Methods to Combine Data

If you need to compute a value from existing accessors, you can use a default method:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
```

Default methods do not require querying an extra `displayName` column; they compute from the projection's getters. This works well for simple display logic. Complex business rules should live in a service or a dedicated component.

### 3.3. Open Projections with @Value

An open projection uses SpEL to compute a value from the target entity:

```java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerOpenView {
    Long getId();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

Because the expression can access the entire `target`, Spring Data cannot know for sure which properties are needed. Open projections can cause the full entity to be loaded, losing part of a projection's column-optimization benefit.

Only use `@Value` when SpEL expressions are genuinely needed. For simple concatenation, a default method on a closed projection is usually clearer and easier to optimize.

## 4. Nested Projections for Relationships

A projection can declare another projection for a relationship attribute. For example, a customer has a relationship to `Address`:

```java
public interface AddressView {
    String getCity();
    String getCountry();
}

public interface CustomerWithAddressView {
    Long getId();
    String getFirstName();
    AddressView getAddress();
}
```

Nested projections give read APIs a structured object graph. However, do not assume a nested projection always loads only a few columns at every level. Spring Data may need to join the relationship and materialize the nested property more broadly than expected.

If a nested view requires exact control over column count, joins, aggregation, or pagination, consider a JPQL DTO constructor expression or a native query projection with an explicit select list. Inspect the generated SQL to verify the actual query.

## 5. Class-Based Projections and DTOs

Class-based projections return a DTO object instantiated via a constructor instead of an interface proxy. DTOs fit when you want a concrete data type that can be passed across services/APIs without relying on proxies.

Example using a Java record:

```java
package com.example.learning.customer;

public record CustomerNameDto(
    Long id,
    String firstName,
    String lastName
) {
}
```

Records have a canonical constructor and clear component names. You can use a regular class if you need additional behavior or compatibility with a codebase not yet using records:

```java
public class CustomerNameDto {
    private final Long id;
    private final String firstName;
    private final String lastName;

    public CustomerNameDto(Long id, String firstName, String lastName) {
        this.id = id;
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public Long getId() { return id; }
    public String getFirstName() { return firstName; }
    public String getLastName() { return lastName; }
}
```

Spring Data must determine which constructor creates the DTO. For classes with multiple constructors, provide a single matching constructor or mark the intended constructor with `@PersistenceCreator`. With records, the canonical constructor usually makes this selection clear.

### 5.1. DTOs from Derived Queries

A derived query can return a class-based projection if the DTO has a constructor matching the properties Spring Data infers from constructor parameters:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<CustomerNameDto> findByActiveTrueOrderByLastNameAscFirstNameAsc();
}
```

For DTO classes/records, constructor parameter names must correspond to entity properties so Spring Data can identify which data to fetch. If a constructor has extra parameters or mismatched names, projection creation can fail at query initialization time.

Class-based projections do not support nested projections like interface projections. If a DTO needs a nested structure, write explicit queries and mappings or assemble DTOs in the service layer.

## 6. Projections with JPQL @Query

JPQL queries entities and Java properties. With interface projections, you can assign aliases to each expression to match getters:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("""
        select c.id as id,
               c.firstName as firstName,
               c.lastName as lastName,
               c.email as email
        from Customer c
        where c.active = :active
        order by c.lastName asc, c.firstName asc
        """)
    List<CustomerNameView> findNameViewsByActive(
        @Param("active") boolean active
    );
}
```

The aliases `id`, `firstName`, `lastName`, and `email` match the accessors of `CustomerNameView`. JPQL uses `Customer`, `firstName`, and `lastName` as entity/property names; do not use `customers` or `first_name` in JPQL expressions.

### 6.1. DTO Constructor Expressions in JPQL

For class-based projections, JPQL uses the `select new` constructor expression with the fully qualified class name:

```java
@Query("""
    select new com.example.learning.customer.CustomerNameDto(
        c.id, c.firstName, c.lastName
    )
    from Customer c
    where c.active = :active
    order by c.lastName asc, c.firstName asc
    """)
List<CustomerNameDto> findNameDtosByActive(
    @Param("active") boolean active
);
```

The order and types of expressions must match the constructor of `CustomerNameDto`. The class name in the constructor expression must be the fully qualified class name; JPQL does not allow `new CustomerNameDto(...)` without the full package name.

Constructor expressions are explicit, easy to review, and portable in JPQL. Spring Data JPA can rewrite some JPQL queries to create constructor expressions for DTOs, but you should not rely on rewriting when the query already has complex select expressions or incompatible aliases.

### 6.2. Aggregations and Computed Expressions

DTO projections are especially useful when queries return aggregated results that do not correspond to an entity:

```java
public record CustomerCountByActive(boolean active, Long total) {
}
```

```java
@Query("""
    select new com.example.learning.customer.CustomerCountByActive(
        c.active, count(c)
    )
    from Customer c
    group by c.active
    """)
List<CustomerCountByActive> countCustomersByActive();
```

The results are aggregated rows by `active` status. This is read data, not a managed entity. Do not pass aggregated DTOs to `save()` or expect JPA to synchronize them back to the table.

## 7. Projections with Native SQL

Native SQL uses physical table and column names. With interface projections, result aliases should match the projection property names:

```java
@Query(
    value = """
        select c.id as id,
               c.first_name as firstName,
               c.last_name as lastName,
               c.email as email
        from customers c
        where c.active = ?1
        order by c.last_name, c.first_name
        """,
    nativeQuery = true
)
List<CustomerNameView> findNativeNameViewsByActive(boolean active);
```

In the example, `?1` is a positional parameter. The native SQL alias `firstName` must preserve the exact column label required by the projection. Some databases fold unquoted identifiers to lowercase or uppercase; if aliases are altered, quote the alias according to your dialect (for example, PostgreSQL uses double quotes) or adjust the alias/mapping. Always verify on the real database.

Native queries fit when database-specific SQL is needed, but projections depend more tightly on column names, aliases, and returned types. Schema changes can break queries even when entity properties remain unchanged.

### 7.1. DTOs from Native SQL

Class-based DTOs can receive native query results directly when column count, column order, and returned data types match the DTO constructor:

```java
@Query(
    value = """
        select c.id, c.first_name, c.last_name
        from customers c
        where c.active = ?1
        order by c.last_name, c.first_name
        """,
    nativeQuery = true
)
List<CustomerNameDto> findNativeNameDtosByActive(boolean active);
```

Here, the select order is `id`, `first_name`, `last_name`, matching the constructor `CustomerNameDto(Long, String, String)`. Check the JDBC types returned by the database/provider; a numeric or timestamp type might not match the expected constructor type exactly.

If column order, data types, or result structure do not match the DTO directly, use an explicit mapping instead of relying on implicit conversion.

### 7.2. @SqlResultSetMapping for Complex Results

Jakarta Persistence supports `@SqlResultSetMapping` and `@ConstructorResult` to map column labels to a DTO constructor:

```java
import jakarta.persistence.ColumnResult;
import jakarta.persistence.ConstructorResult;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.SqlResultSetMapping;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SqlResultSetMapping(
    name = "CustomerNameMapping",
    classes = @ConstructorResult(
        targetClass = CustomerNameDto.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "given_name", type = String.class),
            @ColumnResult(name = "family_name", type = String.class)
        }
    )
)
public class Customer {
    @Id
    private Long id;

    protected Customer() {
    }
}
```

On Spring Data JPA 3.4+, `@NativeQuery` has a `sqlResultSetMapping` attribute to reference a declared mapping:

```java
import org.springframework.data.jpa.repository.NativeQuery;

@NativeQuery(
    value = """
        select c.id as customer_id,
               c.first_name as given_name,
               c.last_name as family_name
        from customers c
        where c.active = ?1
        """,
    sqlResultSetMapping = "CustomerNameMapping"
)
List<CustomerNameDto> findNativeDtosWithMapping(boolean active);
```

Column labels in SQL must match `@ColumnResult`; order and types must fit the constructor. `@NativeQuery` was introduced in Spring Data JPA 3.4.0. On older versions, you can call `EntityManager.createNativeQuery(sql, "CustomerNameMapping")` in a custom repository or use a compatible mapping mechanism.

## 8. Dynamic Projections

Dynamic projections allow callers to choose the result type when calling a method instead of declaring a separate method for every projection:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    <T> List<T> findByActiveTrue(Class<T> projectionType);
}
```

Calling the same repository method with multiple types:

```java
List<CustomerNameView> views =
    repository.findByActiveTrue(CustomerNameView.class);

List<CustomerNameDto> dtos =
    repository.findByActiveTrue(CustomerNameDto.class);

List<Customer> entities =
    repository.findByActiveTrue(Customer.class);
```

Spring Data recognizes the `Class<T>` parameter as a projection selector when its generic type matches the return type. If you use `Class<?>` or a type not recognized as a dynamic projection, the parameter may be treated as a regular query parameter.

Dynamic projections are useful when the same filter serves multiple callers. However, do not create excessive projection types arbitrarily; each projection remains a data contract that must be maintained and tested.

## 9. Comparing Projections by Query Type

| Query approach | Interface projection | Class/record DTO |
| --- | --- | --- |
| Derived query | Returns interface projection directly; getters define needed properties | Can return DTO if constructor parameters match entity properties |
| JPQL `@Query` | Select expressions with aliases matching getters | Uses `select new fully.qualified.Dto(...)` |
| Native SQL | Select columns and aliases matching accessors; check database alias handling | Columns must match constructor order/types or use `@SqlResultSetMapping` |

No single projection type is optimal for every query. Interface projections are convenient for small views and nested accessors; DTOs fit API contracts, computations, or aggregations; native SQL DTOs require more careful mapping since the provider lacks JPQL metadata to infer structure.

## 10. Are Projections Always Faster Than Entities?

Projections can reduce selected data and instantiated objects, but they do not automatically guarantee faster queries. Effectiveness depends on the actual SQL:

- Closed interface projections and DTO constructor queries can select only the required columns.
- Open projections with SpEL accessing `target` may need to load the full entity.
- Nested projections can generate joins and load extra association data.
- A native query can be fast or slow depending on indexes, joins, filters, and execution plans.
- If a projection only trims a few columns while the query still joins many tables or performs a full table scan, the benefit may be small.

Inspect generated SQL, row counts, column counts, query counts, and execution plans. Measure on production-like data rather than concluding solely from the Java return type.

### 10.1. Projections Are Not Entity Update Mechanisms

Interface projections or DTOs are normally read data. Changing a value on a DTO does not automatically update the entity or database. When writes are needed:

1. Load the entity to modify inside a transaction.
2. Apply changes through business methods.
3. Commit the transaction so JPA flushes the managed entity.

For bulk updates, use appropriate write queries and manage the persistence context according to their rules; projections do not replace transactions or dirty checking.

## 11. Integration Tests for Interfaces and DTOs

The test below verifies that derived queries return interface projections and DTOs with accurate data. It assumes the `Customer` entity, `CustomerNameDto` record, and repository are declared as in the examples above, and that the project includes `spring-boot-starter-test`, `spring-boot-starter-data-jpa`, and a test database such as H2.

```java
package com.example.learning.customer;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerProjectionTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void returnsInterfaceAndDtoProjections() {
        customers.saveAll(List.of(
            new Customer("Ada", "Lovelace", "ada@example.test", true),
            new Customer("Grace", "Hopper", "grace@example.test", false)
        ));
        customers.flush();

        List<CustomerNameView> views =
            customers.findByActiveTrueOrderByLastNameAscFirstNameAsc();

        assertThat(views)
            .extracting(CustomerNameView::getEmail)
            .containsExactly("ada@example.test");

        List<CustomerNameDto> dtos = customers.findByActiveFalse();

        assertThat(dtos)
            .extracting(CustomerNameDto::email)
            .containsExactly("grace@example.test");
    }
}
```

Record accessors use component names, so the test calls `CustomerNameDto::email`. Interface projections use the getter method reference `CustomerNameView::getEmail`. `flush()` forces new entities to synchronize to the database before repository queries run.

To test JPQL/native projections, invoke the corresponding repository methods and verify every field. Native queries should run against a database compatible with the syntax and aliases the query uses; H2 is not a complete substitute for testing on PostgreSQL, MySQL, SQL Server, or Oracle.

## 12. Common Pitfalls

- **Projection getter does not match property.** Check getter names, JavaBeans properties, and query aliases.
- **JPQL uses SQL column names.** JPQL must use entity/property names; only native SQL uses physical table/column names.
- **JPQL DTO missing fully qualified class name.** Constructor expressions require the full class name and parameter order/types matching the constructor.
- **DTO with multiple constructors has an ambiguous selection.** Provide a single matching constructor or mark one with `@PersistenceCreator`.
- **Native interface projection aliases change case.** Quote aliases according to your dialect and verify actual column labels.
- **Native DTO selects wrong column order or types.** Align the select list with the constructor or use `@SqlResultSetMapping`.
- **Using an open projection just to concatenate two strings.** Prefer default methods to keep the projection closed.
- **Assuming nested projections always load only a few columns.** Check joins and actual SQL.
- **Using projections to update the database.** Load a managed entity and update it inside a transaction.
- **Exposing entities directly in APIs for convenience.** Use DTOs/projections to control exposed data and avoid coupling to the persistence model.
- **Not testing native SQL on the real dialect.** Aliases, data types, and syntax can vary across database systems.

## 13. Process for Choosing a Projection

1. Identify which fields the use case needs to read and whether a managed entity is required.
2. For simple derived queries, try an interface projection or matching DTO constructor.
3. For JPQL, use aliases matching getters for interfaces or `select new` for DTOs.
4. For native SQL, select physical columns explicitly; alias interface projections carefully; check DTO constructor order and types.
5. Use `@SqlResultSetMapping` when native result sets are complex or do not match a constructor directly.
6. Use dynamic projections when the same query genuinely needs multiple result shapes.
7. Inspect generated SQL, joins, column counts, row counts, and execution plans.
8. Write integration tests for normal data, nulls, joins, and aggregate results if applicable.

## 14. Quick Selection Table

| Need | Recommended choice |
| --- | --- |
| Small list, simple getters | Closed interface projection |
| Combine a few fields from existing accessors | Closed projection with default method |
| SpEL expression depending on target entity | Open projection, used intentionally |
| Read data needing a concrete, immutable type | Record DTO |
| JPQL returning DTOs or aggregated results | Constructor expression `select new` |
| Native SQL returning a few columns | Interface projection with exact aliases |
| Native SQL returning a simple DTO | Constructor DTO when column order/types match |
| Native SQL with complex mapping | `@SqlResultSetMapping` or custom repository |
| Same filter conditions, multiple result shapes | Dynamic projection |

## Conclusion

Projections let repositories return the exact data shape a use case requires. Interface projections are convenient with getters and derived queries; DTOs/records provide concrete types; JPQL uses aliases or constructor expressions; native SQL requires exact aliases and result mappings. Choose projections based on read goals, inspect the real SQL, and keep entities for state-changing operations. With native queries, always verify aliases, column order, and types on the target database.
