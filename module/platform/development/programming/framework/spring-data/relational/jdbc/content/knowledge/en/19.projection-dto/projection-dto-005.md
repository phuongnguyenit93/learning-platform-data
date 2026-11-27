# Dynamic Projections and Method Support Scope

In **Spring Data Relational JDBC**, projections allow a repository to return a data view instead of always returning the full aggregate root. With static projections, the result type is fixed in the method signature. With **dynamic projections**, the caller chooses the result type at invocation time, typically via a `Class<T>` parameter.

For example, the same lookup by last name can return:

- The full `Person` aggregate when the caller passes `Person.class`.
- A projection interface containing only names when the caller passes `PersonName.class`.
- A DTO/record containing selected fields when the caller passes the corresponding DTO type.

This capability is convenient when multiple use cases read the same dataset but need different fields. However, dynamic projections do not turn every repository method into an arbitrary query engine. Spring Data JDBC has specific limits around query derivation, inherited CRUD methods, SQL declared with `@Query`, DTO mapping, and pagination. Understanding the support scope helps you choose proper method signatures and avoid confusing dynamic projections with arbitrary SQL generation.

## 1. Static Projections vs. Dynamic Projections

A projection describes the properties the read side wants to receive. Example aggregate:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("person")
public record Person(
        @Id Long id,
        String firstname,
        String lastname,
        String email,
        String status
) {}
```

Static projection:

```java
public interface PersonName {
    String getFirstname();
    String getLastname();
}
```

The repository can declare a dedicated method returning the projection:

```java
public interface PersonRepository
        extends CrudRepository<Person, Long> {

    List<PersonName> findByLastname(String lastname);
}
```

This method's result type is always `PersonName`. If another screen needs both email and status, you can create another projection and a corresponding method.

With **dynamic projections**, the method uses a generic type `T`:

```java
public interface PersonRepository
        extends CrudRepository<Person, Long> {

    <T> List<T> findByLastname(String lastname, Class<T> projectionType);
}
```

The caller chooses the result type:

```java
List<Person> people =
        repository.findByLastname("Nguyen", Person.class);

List<PersonName> names =
        repository.findByLastname("Nguyen", PersonName.class);
```

Same query method and filter condition, yet the result type varies according to the `Class<T>` argument. That is the main difference: static projections pick the type in the repository declaration; dynamic projections pick the type at call time.

## 2. Dynamic Projection Method Structure

General pattern:

```java
<T> Collection<T> findBySomeProperty(
        PropertyType value,
        Class<T> projectionType
);
```

Components:

- `<T>` declares the generic type parameter for the method.
- `Collection<T>` or `List<T>` is the return type parameterized by the chosen projection.
- `Class<T>` tells Spring Data which type to materialize.
- Parameters preceding `Class<T>` remain ordinary query criteria.

You can use another collection type suited to the query, such as `List<T>` or `Collection<T>`. If the query returns at most one row, a single-result form matching query semantics can be used; when multiple rows may return, a collection makes cardinality clear.

### 2.1. Complete Example

Suppose there are two projections:

```java
public interface PersonName {
    String getFirstname();
    String getLastname();
}

public interface PersonContact {
    Long getId();
    String getEmail();
}
```

Repository:

```java
public interface PersonRepository
        extends CrudRepository<Person, Long> {

    <T> List<T> findByLastname(String lastname, Class<T> projectionType);
}
```

Service:

```java
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PersonQueryService {

    private final PersonRepository repository;

    public PersonQueryService(PersonRepository repository) {
        this.repository = repository;
    }

    public List<PersonName> findNames(String lastname) {
        return repository.findByLastname(lastname, PersonName.class);
    }

    public List<PersonContact> findContacts(String lastname) {
        return repository.findByLastname(lastname, PersonContact.class);
    }

    public List<Person> findAggregates(String lastname) {
        return repository.findByLastname(lastname, Person.class);
    }
}
```

`PersonName.class` and `PersonContact.class` are the requested projection types. When `Person.class` is passed, the method returns the aggregate root as usual. Dynamic projection does not alter the `WHERE lastname = ...` filter condition; it determines the shape of the resulting objects.

## 3. Interface Projections: Proxies and Matching Properties

With interface-based projections, Spring Data generates a proxy at runtime and delegates accessor calls to corresponding values on the target object:

```java
public interface PersonSummary {
    Long getId();
    String getFirstname();
    String getLastname();
}
```

Accessors should match persistent properties on the aggregate root. If the entity property is `firstname`, the JavaBean-convention accessor is `getFirstname()`. Physical SQL column names may differ via `@Column` or a naming strategy; projections reference domain model properties.

Example entity with different column names:

```java
@Table("person")
public record Person(
        @Id Long id,
        @Column("first_name") String firstname,
        @Column("last_name") String lastname,
        String email
) {}
```

The projection still uses `getFirstname()` and `getLastname()`, without changing to `getFirstNameColumn()` or SQL column names.

### 3.1. Projections Must Sit Outside the Entity's Type Hierarchy

A type is treated as a projection when it sits outside the entity's type hierarchy. If the entity itself implements an interface and the repository returns that interface, Spring Data may return the fully materialized entity instead of creating a projection proxy.

Example not to rely on for a projection:

```java
public interface PersonView {
    String getFirstname();
}

public class Person implements PersonView {
    // Entity implementation...
}
```

`PersonView` is an interface implemented by `Person`, so it lies within the entity's type hierarchy. Returning `PersonView` does not imply reading only partial data. Declare a separate projection interface that the entity does not implement.

### 3.2. Closed Projections

An interface projection is a **closed projection** when every accessor maps directly to an aggregate property:

```java
public interface PersonName {
    String getFirstname();
    String getLastname();
}
```

Because the framework knows exactly which properties are used, Spring Data can optimize queries to fetch only the necessary fields when supported by the module and query type. With Spring Data JDBC, verify the actual SQL in your running version before concluding that the column count has been reduced.

### 3.3. Open Projections

An interface projection can compute values with `@Value` and SpEL:

```java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplay {
    @Value("#{target.firstname + ' ' + target.lastname}")
    String getDisplayName();
}
```

This is an **open projection** because the expression can access multiple properties on `target`. Spring Data cannot statically determine all required properties to optimize the query like a closed projection.

For simple calculations, a default method is usually easier to read:

```java
public interface PersonDisplay {
    String getFirstname();
    String getLastname();

    default String getDisplayName() {
        return getFirstname() + " " + getLastname();
    }
}
```

Default methods should rely solely on accessors already present in the projection. Complex business logic belongs in a service or Spring bean rather than stuffed into SpEL expressions.

## 4. Dynamic Projections with DTOs and Records

Dynamic projections can also choose class-based DTOs. Example record:

```java
public record PersonCard(
        Long id,
        String firstname,
        String email
) {}
```

Invocation:

```java
List<PersonCard> cards =
        repository.findByLastname("Nguyen", PersonCard.class);
```

Class-based projections do not use proxies like interface projections. Spring Data constructs the DTO via a constructor matching the input properties. Java records are convenient because they have a single canonical constructor and explicit component names.

If a DTO class has multiple constructors, Spring Data needs to know which constructor to use. You can mark the intended constructor with `@PersistenceCreator`:

```java
import org.springframework.data.annotation.PersistenceCreator;

public class PersonCard {
    private final Long id;
    private final String firstname;

    protected PersonCard() {
        this.id = null;
        this.firstname = null;
    }

    @PersistenceCreator
    public PersonCard(Long id, String firstname) {
        this.id = id;
        this.firstname = firstname;
    }

    public Long getId() {
        return id;
    }

    public String getFirstname() {
        return firstname;
    }
}
```

Class-based DTOs do not support nested projections in the same way interface projections do. If nested structures are required, use nested interface projections or manually map query results to DTOs.

## 5. How Does Spring Data Recognize the `Class<T>` Parameter?

Spring Data inspects `Class`-typed parameters to determine whether one is a dynamic projection parameter. When the generic type of `Class<T>` matches the actual generic return type of the query, that parameter is treated as the **projection selector**, not as a normal query parameter.

Example:

```java
<T> List<T> findByLastname(String lastname, Class<T> projectionType);
```

In this signature, `projectionType` controls the result type. It is not bound to an SQL value and is not available as a query parameter in SpEL.

If the application genuinely needs to pass a `Class` object as a **query filter value**, use a different generic type, such as `Class<?>`, so it is not recognized as a dynamic projection parameter:

```java
List<Person> findByEntityClass(Class<?> entityClass);
```

This example only illustrates how generic signatures are distinguished; whether `Class<?>` can be bound as an SQL value depends on the property, converters, and schema data types. Not every database has a column type capable of storing a Java Class object.

## 6. Query Method Support Scope in Spring Data JDBC

Dynamic projection is a feature of Spring Data's repository/projection infrastructure, yet **the capabilities of each query type are still governed by Spring Data JDBC**.

### 6.1. Derived Queries Only Support Direct Properties of the Aggregate Root

Spring Data JDBC can derive queries from method names:

```java
List<PersonName> findByLastname(String lastname);

<T> List<T> findByLastname(String lastname, Class<T> projectionType);
```

However, query derivation in Spring Data JDBC is limited to simple properties directly on the aggregate root and only supports SELECT queries this way. You cannot assume writing a property path across relationships will make Spring auto-generate JOINs like some ORMs.

For example, if `Person` has an `address` property and `Address` has `city`, do not assume the method:

```java
List<PersonName> findByAddressCity(String city);
```

will generate a JOIN through the address table. JDBC derived queries only support properties usable in WHERE without JOINs. For cross-table queries, use explicit SQL, database views, query DAOs, or a suitable read model.

### 6.2. Do Not Turn Inherited CRUD Methods into Projections by Changing Return Type

Core methods from `CrudRepository` or base repository interfaces have their own contracts. If you redeclare a method like `findAll()` with a projection return type, calls may still be handled as the base method rather than as a new projection query method.

Example to avoid:

```java
// Do not override CRUD method return types to create projections.
List<PersonName> findAll();
```

Define a distinct query method name instead:

```java
List<PersonName> findAllPersonNamesByStatus(String status);

<T> List<T> findByStatus(String status, Class<T> projectionType);
```

A dedicated method name lets Spring Data recognize it as a query method and avoids conflicting with base repository methods. Some store modules support turning overridden methods into queries via `@Query`, but verify Spring Data JDBC's exact support rather than mechanically applying Spring Data JPA rules.

### 6.3. `@Query` Is Application-Controlled SQL

Spring Data JDBC allows declaring SQL via `@Query`:

```java
@Query("""
    SELECT id, firstname, lastname
    FROM person
    WHERE lastname = :lastname
    """)
List<Person> findPeopleByLastname(@Param("lastname") String lastname);
```

String-based SQL queries have their own constraints:

- The query must return columns compatible with mapping the result type.
- For entities, columns used by the constructor must be present in the result; properties set via setters, withers, or field access may be optional if absent from the result.
- Spring Data JDBC uses a default RowMapper to map results; a custom `RowMapper` or `ResultSetExtractor` can be configured when different result types are needed.
- Spring Data JDBC supports named parameters in `@Query`.
- String-based queries do not automatically apply `Pageable`, `Sort`, `PageRequest`, or `Limit` like derived queries; if limits/sorting are needed, write them in SQL and bind appropriate parameters.

Therefore, when using `@Query` for DTOs or custom projections, define result mapping explicitly. Do not assume passing `Class<T>` will automatically rewrite an arbitrary SQL string to match a DTO's column list.

### 6.4. Custom `RowMapper` for Dedicated Read Types

If SQL returns a structure that does not match an entity, a custom mapper provides explicit mapping:

```java
public record PersonCard(Long id, String firstname, String email) {}
```

```java
public class PersonCardRowMapper implements RowMapper<PersonCard> {

    @Override
    public PersonCard mapRow(ResultSet rs, int rowNum) throws SQLException {
        return new PersonCard(
                rs.getLong("id"),
                rs.getString("firstname"),
                rs.getString("email")
        );
    }
}
```

Query method declaration:

```java
@Query(
    value = """
        SELECT id, firstname, email
        FROM person
        WHERE lastname = :lastname
        """,
    rowMapperClass = PersonCardRowMapper.class
)
List<PersonCard> findCardsByLastname(@Param("lastname") String lastname);
```

This is a read query with a fixed result type. It is not automatically a dynamic projection; if multiple DTO shapes are needed, create separate methods, use a query DAO with an application-selected mapper, or use derived dynamic projections within supported limits.

## 7. Can Dynamic Projections Combine with Pagination?

At the repository method level, Spring Data can combine projections with pagination parameters for module-supported query methods. Derived query example:

```java
<T> Page<T> findByLastname(
        String lastname,
        Pageable pageable,
        Class<T> projectionType
);
```

Caller:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.asc("firstname"), Sort.Order.asc("id"))
);

Page<PersonName> page = repository.findByLastname(
        "Nguyen",
        pageable,
        PersonName.class
);
```

`Page<T>` provides total elements and total pages; to build accurate metadata, the framework may execute an additional count query. With `Slice<T>`, the application only needs to know whether a next page exists and can avoid counting total pages. Confirm that the specific query method and Spring Data JDBC version support these return types.

Important note: string-based `@Query` restrictions still apply. Do not pass `Pageable` into a string-based `@Query` expecting Spring to automatically rewrite the SQL to add offset, sort, or limit. Write pagination/sorting clauses in SQL when using custom queries.

## 8. Dynamic Projections Are Not Dynamic SQL

Two concepts are frequently confused:

| Concept | What changes | Example |
| --- | --- | --- |
| Dynamic projection | Java type used to represent results | `Person.class` or `PersonName.class` |
| Dynamic SQL | Structure of SQL generated/changed at runtime | Selecting tables, columns, JOINs, or filters per request |

Dynamic projections do not let callers pass table names or arbitrary SQL fragments. Nor do they automatically add JOINs to fetch data from other aggregates.

Example:

```java
List<PersonName> names =
        repository.findByLastname("Nguyen", PersonName.class);
```

still queries by the `lastname` condition. It only changes how results are represented. If data from multiple tables or a complex aggregation is needed, use a custom query/DAO and dedicated DTO mapping.

## 9. Choosing the Right Projection

| Scenario | Suitable Approach |
| --- | --- |
| One use case always needs the same few properties | Static interface or DTO projection |
| Multiple callers need different views on the same derived query | Dynamic projection with `Class<T>` |
| Full entity needed to execute domain behavior | Return aggregate root |
| JOIN, GROUP BY, or multi-table calculations needed | `@Query` with explicit mapping or `JdbcTemplate`/DAO |
| Querying across nested properties requiring JOINs | Custom SQL/query DAO |
| DTO needs custom result structure and special mapping | DTO + custom `RowMapper`/`ResultSetExtractor` |
| Pagination needed with derived query | `Pageable`/`Page` or `Slice` if supported by method |
| Pagination needed with string-based `@Query` | Write limit/offset/order in SQL and bind parameters |

Do not use dynamic projections just because you can. If screens have very different needs, separate clearly named methods are often easier to understand and optimize than one generic method with many result types.

## 10. Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Returns full entity despite interface declared | Projection interface sits in entity's type hierarchy | Use a separate projection interface not implemented by entity |
| Projection property not found | Accessor does not match Java property | Cross-check property names, getters, and mapping metadata |
| `Class<T>` treated as projection selector instead of filter | Generic type of Class matches return type | Use `Class<?>` or another generic type if genuinely a query argument |
| Overrode `findAll()` return type yet still receives entity | Method collides with base repository method | Create a distinctly named derived query method |
| Derived query rejects property path | Query requires JOIN across relationships | Use custom SQL/DAO; JDBC query derivation supports direct properties only |
| Cannot instantiate DTO | Unsuitable constructor or missing property metadata | Use one clear constructor or `@PersistenceCreator` |
| Custom query lacks data when mapping entity | SQL omits columns required by constructor | Add missing columns or use DTO/custom RowMapper |
| `@Query` ignores sort/page | String-based query does not auto-rewrite for these parameters | Write ORDER BY/LIMIT/OFFSET in SQL |
| Open projection fails to reduce columns | SpEL can access any property | Use closed projection or DTO with explicit column-selecting query |
| Expecting dynamic projection to JOIN other tables | Confusing result type with SQL structure | Use a multi-table query and dedicated mapper |

## 11. Workflow for Implementing Dynamic Projections

When adding dynamic projections to a repository:

1. Identify the aggregate root and the read properties to expose.
2. Create interface/DTO projections outside the entity's type hierarchy.
3. Declare a generic method with return type `T` and parameter `Class<T>`.
4. Ensure derived query criteria use only properties supported by Spring Data JDBC.
5. Invoke the method with the entity class or a specific projection class.
6. If using a DTO, ensure the constructor and input property names map properly.
7. If using `@Query`, control SQL, returned columns, and RowMapper; do not assume dynamic projection alters SQL automatically.
8. If pagination is needed, verify method type/module support; with string-based SQL, write limits and ordering explicitly.
9. Inspect SQL in development to verify whether the projection actually reduces data read.

## 12. Practice Exercises

**Exercise 1 — Two result types.** Create `PersonName` and `PersonContact`. Declare `<T> List<T> findByLastname(String lastname, Class<T> type)`; invoke with both projections and with `Person.class`.

**Exercise 2 — Closed and open projections.** Create a closed projection with only firstname/lastname, then create an open projection using `@Value` to concatenate the name. Observe the difference in query optimization potential.

**Exercise 3 — Dynamic DTO.** Create a `PersonCard` record and pass `PersonCard.class` to the method. Try a DTO with multiple constructors, then mark the right constructor with `@PersistenceCreator`.

**Exercise 4 — Type hierarchy.** Make the entity implement an interface with getters, try returning that interface, and compare it with an independent projection interface. Explain why the first can return a fully materialized entity.

**Exercise 5 — Class parameter.** Compare `Class<T>` and `Class<?>` signatures. Observe which parameter Spring recognizes as a dynamic projection parameter and which can remain a query argument under suitable mapping.

**Exercise 6 — Query limits.** Try a derived query using a direct property and a nested property requiring a JOIN. Then write `@Query` with a JOIN, custom RowMapper, and DTO to compare both query paths.

**Exercise 7 — Pagination.** Combine dynamic projection with `Pageable` on a supported derived query. Compare `Page` and `Slice`; then try a custom string-based `@Query` and identify the ORDER BY/LIMIT/OFFSET clauses that SQL must handle.

### References

- [Spring Data Relational — Projections](https://docs.spring.io/spring-data/relational/reference/repositories/projections.html): interface, DTO, and dynamic projections; `Class<T>` detection rules.
- [Spring Data Relational — JDBC Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query derivation scope, `@Query`, pagination parameters, and custom RowMapper.
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): mapping and repository support in Spring Data JDBC.
