# Closed Interface Projections and Property Name Mapping

## 1. What Is an Interface Projection?

Spring Data JPA allows a repository to return an interface instead of the full Entity. The framework creates a projection instance based on the query data and exposes values through the interface's accessors. This is useful when a screen or API only needs a subset of an Entity's information.

For example, the `Customer` Entity has many fields such as `id`, `firstName`, `lastName`, `email`, `phone`, `address`, `createdAt`, and `status`, while a customer list only needs the name and email. You can define an interface:

```java
public interface CustomerListView {
    Long getId();
    String getFirstName();
    String getLastName();
    String getEmail();
}
```

The repository returns the projection:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<CustomerListView> findByStatus(CustomerStatus status);
}
```

Spring Data recognizes the return type as a projection interface and creates objects implementing that interface. Callers see only the declared accessors and do not receive the full Entity.

## 2. What Is a Closed Projection?

A projection is considered **closed** when all accessors of the interface correspond to actual properties on the aggregate root (the Entity or root object being queried). The framework knows exactly which properties are needed and can optimize the query to select only the relevant columns.

For example:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();
}
```

The two accessors map to `Customer.firstName` and `Customer.lastName`. If a query returns `CustomerNameView`, Spring Data can restrict the selected data instead of loading all columns of `Customer`.

Closed projections help:

- Reduce the amount of data read and transferred from the database.
- Reduce the data materialized in the application when only a few properties are needed.
- Clarify the data contract of a read use case.
- Prevent the API layer from depending on the entire Entity structure.

Actual optimization also depends on the query type, provider, mapping, and how the projection is used. Inspect the generated SQL rather than assuming every projection always selects only the getter columns.

## 3. Mapping Accessor Names to Java Properties

Spring Data relies on the property names of the root object, not the physical column names in the database.

| Accessor in interface | Java property in Entity | Possible physical column |
| --- | --- | --- |
| `getFirstName()` | `firstName` | `first_name` |
| `getLastName()` | `lastName` | `last_name` |
| `getEmail()` | `email` | `email_address` |
| `getCreatedAt()` | `createdAt` | `created_at` |

If the Entity declares `private String firstName;` with `@Column(name = "first_name")`, the projection must still use `getFirstName()`. Do not name it `getFirst_name()` just because the column name is snake_case.

The JavaBean accessor `getFirstName()` represents the property `firstName`. For booleans, the accessor is usually `isActive()` or `getActive()` depending on the type and bean convention. Keeping property names clear and consistent helps avoid subtle mapping errors.

## 4. Using Projections with Derived Queries

Entity example:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private CustomerStatus status;

    @Column(name = "created_at")
    private Instant createdAt;
}
```

Projection interface:

```java
public interface CustomerListView {
    Long getId();
    String getFirstName();
    String getLastName();
    String getEmail();
}
```

Repository:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<CustomerListView> findByStatus(CustomerStatus status);
}
```

Query derivation still uses the Java property `status`. The interface projection return type specifies the fields to read. There is no need to declare `@Query` if the condition is simple.

## 5. Using @Query and Aliases for Interface Projections

When writing explicit JPQL, assign aliases to each expression matching the properties expected by the projection:

```java
public interface CustomerCardView {
    Long getId();
    String getFirstName();
    String getLastName();
}
```

```java
@Query("""
    select c.id as id,
           c.firstName as firstName,
           c.lastName as lastName
    from Customer c
    where c.status = :status
    """)
List<CustomerCardView> findCardsByStatus(
    @Param("status") CustomerStatus status
);
```

JPQL uses Entity names and Java properties. The alias `firstName` must match the property represented by `getFirstName()`; the alias `lastName` matches `getLastName()`. If an alias is wrong or missing, the projection may receive null values or fail mapping depending on the provider and query type.

For interface projections from queries returning scalars/tuples, aliases are the contract between the query and the accessors. Use clear aliases and test each getter to avoid a projection succeeding while data is not mapped as intended.

## 6. Interface Projections with Native SQL

Native queries use physical table and column names. Aliases should translate database column names into the exact property names required by the interface:

```java
@Query(
    value = """
        select c.id as id,
               c.first_name as firstName,
               c.last_name as lastName
        from customer c
        where c.status = ?1
        """,
    nativeQuery = true
)
List<CustomerCardView> findCardsNative(CustomerStatus status);
```

In the example, `first_name` and `last_name` are column names; `firstName` and `lastName` are aliases for the projection. Positional parameter `?1` is often a more portable choice for native queries across providers. Check the enum type expected for `status` by the driver/database; if the mapping stores enums as strings or ordinals, the bound value must be schema-compatible.

Case sensitivity rules and how drivers return column labels can differ across databases. For native projections, verify actual aliases and test on the target database. Do not assume camelCase aliases are preserved if a dialect automatically folds unquoted identifiers.

## 7. Nested Projections

A projection can declare a nested interface to represent a nested property:

```java
public interface AddressView {
    String getCity();
    String getPostalCode();
}
```

```java
public interface CustomerDetailView {
    String getFirstName();
    String getLastName();
    AddressView getAddress();
}
```

If `Customer.address` is an association or nested property, Spring Data can create a nested projection for `address`. This is convenient for simple read object graphs.

However, nested projections do not guarantee that the query selects only the inner leaf properties. For nested properties resolved through a join, Spring Data JPA may materialize the entire joined property rather than only the subfields declared in the nested interface. If you need exact control over columns and joins, use a JPQL DTO constructor expression or a query returning a DTO.

Avoid deep nested projections and circular references between interfaces. Keep the structure small and tailored to the required response.

## 8. Default Methods in Closed Projections

A projection interface can add default methods to compute values from the declared accessors:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
```

A default method does not require a new property from the Entity; it combines data already retrieved via accessors. Therefore, the projection can still be considered closed if all data-fetching accessors map to properties of the aggregate root.

If computation logic requires a service, another query, or external data beyond the projection, do not place business dependencies in a default method. Move that processing to a service or mapper.

## 9. Distinguishing Closed and Open Projections

An open projection uses `@Value` with SpEL to compute values from the target or other beans:

```java
public interface CustomerDisplayView {
    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

Because the expression can access multiple properties of the target, Spring Data cannot determine with certainty which properties are needed from the accessors alone. As a result, open projections usually cannot optimize column selection like closed projections.

If you only need to concatenate two properties, a default method on a closed projection is clearer and easier to optimize. Use `@Value` when you genuinely need SpEL or expression logic that a default method cannot handle.

| Characteristic | Closed projection | Open projection |
| --- | --- | --- |
| Accessors | Map clearly to properties | Can use SpEL `@Value` |
| Framework knows property set | Determinable | Cannot be determined with certainty |
| Column selection optimization | Can be optimized | Usually restricted |
| Best suited for | Simple read views, well-defined fields | Computed expressions needing target/bean access |

## 10. Nullable Wrappers and Missing Property Values

A projection can use `Optional` for properties that may be null:

```java
public interface CustomerContactView {
    Long getId();
    String getEmail();
    Optional<String> getPhone();
}
```

If `phone` is null, the accessor returns `Optional.empty()` instead of null. Spring Data supports several common nullable wrappers; `java.util.Optional` is the familiar choice in Java.

A wrapper does not replace validation or business rules. If a property is required, constraints are still needed at the domain/validation/schema layers. When using projections, check how the provider maps nulls and actual data types.

## 11. How Interface Projections Differ from DTO Classes

| Criterion | Interface projection | DTO class/record |
| --- | --- | --- |
| Definition | Interface with accessors | Constructor or record components |
| Result creation | Spring Data creates a proxy/implementation | Provider creates an instance via constructor query or mapper |
| Aliases | Important for tuple/scalar queries | Constructor expression relies on argument order and types |
| Computation | Default methods or SpEL | Constructor, methods, or mapper |
| Best suited for | Simple read views, clear properties | Independent structured responses or complex mapping |

JPQL DTO projections commonly use constructor expressions:

```java
public record CustomerCard(Long id, String firstName, String email) {
}
```

```java
@Query("""
    select new com.example.customer.CustomerCard(
        c.id, c.firstName, c.email
    )
    from Customer c
    where c.status = :status
    """)
List<CustomerCard> findCards(
    @Param("status") CustomerStatus status
);
```

Constructor expressions do not use aliases for individual constructor arguments; the order, count, and types of expressions must match the constructor. Choose interface projections when you want a concise accessor contract; choose DTOs when you need a result object independent of the Entity with explicit mapping control.

## 12. Projections and Pagination

Interface projections can be combined with `Pageable`:

```java
@Query("""
    select c.id as id,
           c.firstName as firstName,
           c.lastName as lastName
    from Customer c
    where c.status = :status
    """)
Page<CustomerNameView> findPageByStatus(
    @Param("status") CustomerStatus status,
    Pageable pageable
);
```

Spring Data applies pagination and may need a count query to calculate the total. For simple JPQL queries, the framework can usually derive the count query; for complex distinct, group, or join queries, declare an explicit `countQuery` and verify the total element count.

Projections do not automatically eliminate pagination issues when joining collections. If a query joins a collection that multiplies rows, check `distinct`, the count, and page ordering; consider a two-step query or an appropriate DTO.

## 13. Common Pitfalls and How to Diagnose Them

**Accessor returns null even though the Entity has data.** Check the property name in the interface, the `@Query` alias, and the native SQL column label. `getFirstName()` maps to property `firstName`, not `first_name`.

**Alias not found or projection mismatch.** Set the JPQL/native alias to match the projection property name; check database/driver case folding.

**Renaming an Entity property breaks the projection.** Update the accessor, query alias, derived method, and tests. Projection names depend on Java properties.

**Native projection works on dev machine but fails in production.** Check physical column names, returned aliases, data types, and the real provider/database.

**Nested projection still fetches too much data.** Nested properties via associations can cause joins to materialize the entire related property; switch to a DTO query if exact column selection is required.

**Closed projection is not optimized as expected.** Check whether `@Value`/SpEL or nested associations are present, then inspect the actual SQL.

**Page total count is wrong.** Check the count query, joins, `distinct`, and `group by`.

**Need to access a method not in the interface.** Projections expose only declared accessors; if you need full Entity operations or data updates, query the full Entity or use an appropriate service/DTO.

## 14. Closed Interface Projection Design Checklist

- Every getter maps to an actual Java property of the Entity.
- Use camelCase property names, not snake_case column names, in accessors.
- With `@Query`, set aliases matching the projection property names.
- With native SQL, alias physical columns to projection names and test on the target database.
- Keep the projection closed: avoid `@Value`/SpEL if column selection optimization is needed.
- Use default methods for simple calculations based on existing accessors.
- Be cautious with nested projections because joins may materialize more data than expected.
- Choose DTO constructor projections when explicit control over results and mapping is required.
- Test nulls, pagination, count queries, and generated SQL.

Closed interface projections let repositories return the exact data view a use case needs. Accessor names must follow Java properties; for explicit queries, aliases must match the projection contract. Keeping the interface closed and inspecting the actual SQL helps leverage optimization while maintaining control over returned data.
