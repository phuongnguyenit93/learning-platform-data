# Dynamic Projections and Result Type Selection

In Spring Data R2DBC, a query can return a full entity or only a subset of data needed for a screen, report, or API. Selecting only a subset of an entity's properties is called a **projection**. When the result type is fixed in the repository declaration, it is a static projection; when the caller passes the result type at invocation time, it is a **dynamic projection**.

Projections help separate the persistence model from the read model. A service may need the full `Customer` to execute business logic, whereas a list screen needs only the name and email. Returning an appropriate result type ensures the API reflects the exact data needed and can reduce the amount of data read, converted, and passed across layers.

## 1. What Is a Projection?

Suppose the `Customer` entity has multiple properties:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName,
    String email,
    String phone,
    Boolean active,
    @Version Long version
) {}
~~~

A list page may only need name and email. If the application always queries the full `Customer`, it receives `phone`, `active`, and `version` even though the screen never uses them.

A projection describes the subset of data to return:

~~~java
public interface CustomerNameView {
    String getFullName();
    String getEmail();
}
~~~

Or using a DTO:

~~~java
public record CustomerSummary(
    String fullName,
    String email
) {}
~~~

When a query returns a projection, Spring Data maps the results into that type using the mechanism suited to the interface or constructor. Projection property names must correspond to entity properties or result column aliases in custom SQL queries.

Projections are generally useful for read cases. If you need to update an aggregate, check `version`, or invoke domain methods on the full entity, query the entity instead of using a projection containing only a subset of properties.

## 2. Types of Projections

Spring Data offers several ways to represent projections. In Spring Data R2DBC applications, the most common are interface-based projections, DTO/class-based projections, and dynamic projections.

### 2.1. Interface-Based Projections

An interface projection declares accessors for the properties to retrieve:

~~~java
public interface CustomerNameView {
    String getFullName();
    String getEmail();
}
~~~

The repository can return the interface directly:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<CustomerNameView> findByActiveTrue();
}
~~~

Callers see only the declared accessors:

~~~java
Flux<CustomerNameView> customers =
    repository.findByActiveTrue();

return customers.map(view ->
    view.getFullName() + " <" + view.getEmail() + ">"
);
~~~

Interface projections are suitable when:

- Only a few properties need to be read.
- You want to keep the result type concise and expressive.
- A DTO object with custom business logic is not needed.
- Accessor names map directly to entity properties.

An interface projection is a read-only data type. Do not treat it as a full entity to call `save` or mutate the aggregate.

### 2.2. Closed Projections

A closed projection is an interface that declares only accessors corresponding to properties of the target entity. Spring Data knows the exact properties requested.

Example:

~~~java
public interface CustomerContact {
    String getFullName();
    String getEmail();
}
~~~

Because the accessors map directly to properties, the framework knows the required property set and can optimize data retrieval if supported by the store and query type. Whether the columns are actually restricted in SQL depends on how the repository builds the query, the module, driver, and version. When performance matters, inspect the emitted SQL rather than assuming every projection automatically generates a SELECT with strictly two columns.

### 2.3. Open Projections

An open projection is an interface that can use SpEL expressions to compute values from the target object, for example:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerLabel {

    @Value("#{target.fullName + ' <' + target.email + '>'}")
    String getLabel();
}
~~~

Open projections are flexible because return values can be computed from multiple properties. However, it is difficult for the framework to determine the exact set of columns to read from the expression alone. Furthermore, projection support and optimization behavior can vary across Spring Data modules and versions.

With Spring Data R2DBC, prefer closed projections or DTOs with clear constructors for queries requiring predictable mapping and SQL. Only use SpEL projections after confirming that your module/version supports that exact case.

### 2.4. DTO/Class-Based Projections

DTO projections use a class or record as the result type. Spring Data instantiates it via a constructor whose parameters match the properties to retrieve.

Example record:

~~~java
public record CustomerSummary(
    String fullName,
    String email
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<CustomerSummary> findByActiveTrue();
}
~~~

DTOs are suitable when:

- You want a concrete result type independent of the entity.
- You want to use records for immutability and minimal boilerplate.
- You need to return a read model to a service or API.
- You do not need an interface projection proxy.

For classes with multiple constructors, designate the persistence constructor using `@PersistenceCreator`. Constructor parameter names must match the properties Spring Data needs to map; ensure parameter name metadata is preserved during compilation when the mapping mechanism relies on it.

## 3. What Is a Dynamic Projection?

With a static projection, the result type is fixed in the method declaration:

~~~java
Flux<CustomerNameView> findByActiveTrue();
~~~

If one use case needs `CustomerNameView` while another needs `CustomerSummary` or the full `Customer`, separate methods could be created. Dynamic projections let the caller choose the result type using a `Class<T>` parameter at invocation time.

Example:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    <T> Flux<T> findByActiveTrue(Class<T> resultType);
}
~~~

The same method can be called with multiple result types:

~~~java
Flux<Customer> entities =
    repository.findByActiveTrue(Customer.class);

Flux<CustomerNameView> names =
    repository.findByActiveTrue(CustomerNameView.class);

Flux<CustomerSummary> summaries =
    repository.findByActiveTrue(CustomerSummary.class);
~~~

When the caller passes `Customer.class`, the repository returns the full entity. When passing `CustomerNameView.class`, it returns the interface projection. When passing `CustomerSummary.class`, it returns the DTO projection.

Dynamic projections are useful when the query criteria are identical but different callers need different data shapes.

### 3.1. How the `Class<T>` Parameter Is Recognized

Spring Data recognizes a dynamic projection parameter when the method has a `Class<T>` parameter matching the generic type `T` of the return type.

~~~java
<T> Flux<T> findByActiveTrue(Class<T> resultType);
~~~

In this case, `resultType` is used to determine the projection. It is not treated as a regular query predicate value.

If you need to pass a `Class` object as an actual data parameter to a query, use a type that does not match the generic projection parameter, such as `Class<?>` per Spring Data rules, and declare the corresponding binding. Check how the method parser recognizes parameters in the version you are using.

### 3.2. Dynamic Projections Do Not Change Filter Conditions

Example:

~~~java
<T> Flux<T> findByFullNameContainingIgnoreCase(
    String fragment,
    Class<T> resultType
);
~~~

`fragment` remains the search filter value. `resultType` determines the returned data type.

Calls:

~~~java
Flux<Customer> allData =
    repository.findByFullNameContainingIgnoreCase(
        "An",
        Customer.class
    );

Flux<CustomerNameView> namesOnly =
    repository.findByFullNameContainingIgnoreCase(
        "An",
        CustomerNameView.class
    );
~~~

both find customers whose name contains `"An"`, but return two different data shapes.

### 3.3. Dynamic Projections Have Query-Type Limitations

Dynamic projections work best with derived queries that Spring Data can parse from the method signature. With `@Query` containing prewritten SQL, do not assume the framework will automatically rewrite every SELECT list based on `Class<T>`.

If using custom SQL queries, ensure the SQL selects the required columns and aliases match the result types. When each projection requires a different column set or join structure, use separate methods, a custom repository fragment, `R2dbcEntityTemplate`, or `DatabaseClient`.

## 4. Choosing the Result Type in a Repository

A repository's return type expresses two concerns:

1. **Data shape**: entity, interface projection, DTO, scalar, or other result type.
2. **Result cardinality and emission**: zero/one result or multiple results in a reactive stream.

These two concerns are independent. For example, `Flux<CustomerSummary>` is a stream that can emit multiple DTOs; `Mono<CustomerNameView>` is a single interface projection result that may be absent.

### 4.1. Returning Full Entities

~~~java
Mono<Customer> findById(Long id);

Flux<Customer> findByActiveTrue();
~~~

Use entities when the caller needs full persistent state, ID/version, and the aggregate model.

### 4.2. Returning Interface Projections

~~~java
Flux<CustomerNameView> findByActiveTrue();
~~~

Use interfaces when the caller needs only a small set of accessors and does not need a standalone DTO.

### 4.3. Returning DTOs or Records

~~~java
Flux<CustomerSummary> findByActiveTrue();
~~~

Use DTOs when a concrete read data type is needed that is easy to pass across layers or return from an API.

### 4.4. Returning One Result or Many Results

| Reactive Type | Common Meaning |
|---|---|
| `Mono<T>` | Zero or at most one result |
| `Flux<T>` | Zero, one, or many results |
| `Mono<Long>` | A count value |
| `Mono<Boolean>` | An existence/condition check value |
| `Mono<Void>` | Only cares about completion, no result data needed |

If a method returns `Mono<T>` but the actual query returns multiple rows, the operation may fail due to an incompatible result count. Use `Flux<T>` when the criteria can match multiple rows.

Do not call `block()` just to convert a `Mono` or `Flux` into a synchronous type inside a reactive service. Compose publishers with `map`, `flatMap`, `filter`, or return the publisher to the controller.

## 5. Complete Example with Interface and DTO Projections

Suppose the `Customer` entity has many properties, but a list page needs only name and email.

Interface projection:

~~~java
public interface CustomerContactView {
    String getFullName();
    String getEmail();
}
~~~

DTO projection:

~~~java
public record CustomerContactDto(
    String fullName,
    String email
) {}
~~~

The repository can declare both return types:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<CustomerContactView> findByActiveTrue();

    Flux<CustomerContactDto> findDtoByActiveTrue();
}
~~~

Method naming must avoid Java signature collisions. The example above uses `findByActiveTrue` for the interface and `findDtoByActiveTrue` for the DTO; the predicate part parsed by Spring Data must conform to your version's conventions. If method naming causes parser ambiguity, use a clearer method name with `@Query` or a custom fragment.

In the service:

~~~java
public Flux<CustomerContactDto> listContacts() {
    return repository.findDtoByActiveTrue();
}
~~~

The service emits only the data type required by the use case. Upper layers do not need to know that `Customer` has other fields such as `phone` or `version`.

## 6. Dynamic Projection Example in a Repository

Declare a generic method:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    <T> Flux<T> findByActiveTrue(Class<T> projectionType);

    <T> Flux<T> findByFullNameContainingIgnoreCase(
        String fragment,
        Class<T> projectionType
    );
}
~~~

Call with an entity:

~~~java
Flux<Customer> customers =
    repository.findByActiveTrue(Customer.class);
~~~

Call with an interface:

~~~java
Flux<CustomerContactView> contacts =
    repository.findByActiveTrue(CustomerContactView.class);
~~~

Call with a DTO:

~~~java
Flux<CustomerContactDto> summaries =
    repository.findByActiveTrue(CustomerContactDto.class);
~~~

Here are the main differences between static and dynamic projections:

| Criterion | Static projection | Dynamic projection |
|---|---|---|
| Result type | Fixed in the method signature | Caller passes `Class<T>` |
| Methods | May require separate methods per type | One method can serve multiple types |
| API readability | Return type is clear at declaration | Flexible, concrete type visible at call site |
| Complexity | Simple | Generic method and `Class<T>` must be understood properly |
| When to use | Use case with a fixed read model | Same criteria, but multiple callers need different result types |

Do not use dynamic projections just to reduce method counts if the projections have different business meanings or require different SQL queries. Separating methods can make the repository API easier to understand.

## 7. DTO Constructor Mapping and Column Names

With derived queries, Spring Data can use entity metadata and the DTO constructor to map the required properties.

Example:

~~~java
public record CustomerContactDto(
    String fullName,
    String email
) {}
~~~

The Java properties are `fullName` and `email`. If the entity maps `fullName` to column `full_name` via `@Column`, Spring Data uses mapping metadata to associate the property with the column.

With `@Query`, the SQL is written by the application, so ensure column names/aliases match the DTO properties:

~~~java
import org.springframework.data.r2dbc.repository.Query;
import reactor.core.publisher.Flux;

@Query("""
    SELECT full_name AS full_name,
           email AS email
    FROM customer
    WHERE active = TRUE
    """)
Flux<CustomerContactDto> findActiveContacts();
~~~

Aliases give the result clear column names for mapping. Alias names must align with converter and database rules for identifier casing.

If a DTO has multiple constructors, mark the persistence constructor with `@PersistenceCreator`. When using a Java class instead of a record, ensure constructor parameter names are discoverable and match the properties.

## 8. Projections and Selected SQL

One goal of projections is reading only needed columns. Closed projections help Spring Data determine required properties, though the level of SELECT optimization depends on query type and module capabilities.

With derived queries, the framework may optimize selected fields based on projection metadata when supported. With `@Query` containing fixed SQL, the column list is determined by the SQL statement. Dynamic projections do not automatically guarantee that custom SQL will be rewritten per projection.

Distinguish between:

- **Projection mapping**: transforming query data into the result type.
- **Column selection**: deciding which columns the database returns.
- **Query execution**: the database executing SQL and returning rows.

Successful projection mapping does not necessarily mean the SQL selected only the needed columns. If performance depends on column reduction, inspect SQL logs or execution traces.

## 9. Choosing Projections with `R2dbcEntityTemplate`

`R2dbcEntityTemplate` is commonly used when dynamic entity-level `Query` construction is needed:

~~~java
Query query = Query.query(
    Criteria.where("active").is(true)
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

The entity-typed select API fits when results should be mapped to the `Customer` entity. If you want an entirely different read model or need custom column selection, joins, and calculations, consider `DatabaseClient` to define the SQL and map `Row` directly.

Example DTO with `DatabaseClient`:

~~~java
public record CustomerContactDto(
    String fullName,
    String email
) {}

Flux<CustomerContactDto> contacts =
    databaseClient.sql("""
            SELECT full_name, email
            FROM customer
            WHERE active = :active
            """)
        .bind("active", true)
        .map((row, metadata) ->
            new CustomerContactDto(
                row.get("full_name", String.class),
                row.get("email", String.class)
            )
        )
        .all();
~~~

Here, the result type is chosen directly in the `map` callback. This approach fits when SQL and DTO structure require explicit control.

## 10. Projections Are Not Update Entities

A projection may lack IDs, `version`, or properties needed for an update operation. Do not take a DTO containing only name and email and treat it as a full `Customer`.

Example:

~~~java
CustomerContactDto contact =
    new CustomerContactDto("Nguyen An", "an@example.com");
~~~

This DTO has no ID or `version`. It cannot safely represent a `Customer` aggregate for calling `save`.

If an update is needed, use the ID to load the full entity, apply domain changes, and save the entity:

~~~java
Mono<Customer> rename(
        Long customerId,
        String newName) {

    return repository.findById(customerId)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Customer not found")
        ))
        .map(customer -> new Customer(
            customer.id(),
            newName,
            customer.email(),
            customer.phone(),
            customer.active(),
            customer.version()
        ))
        .flatMap(repository::save);
}
~~~

This example uses an immutable record. The repository returns the saved entity; continue using the value emitted by `save` to obtain updated ID/`version` values if any.

## 11. Selecting the Result Type by Use Case

| Need | Result Type to Consider | Reason |
|---|---|---|
| Read and process full aggregate | Entity | Contains all state needed for business logic |
| List page displaying only a few fields | Closed interface projection | Declares exact accessors to read |
| API needing a clear read model | DTO/record | Result type independent of the entity |
| Same criteria but multiple callers need different structures | Dynamic projection | Choose `Class<T>` at call site |
| Report with joins and calculations | DTO via `@Query` or `DatabaseClient` | Control SQL and result columns |
| Dynamic query at entity level | `R2dbcEntityTemplate` | Uses `Criteria` and Spring Data mapping |
| Need only a count | `Mono<Long>` | No need to load full entities |
| Need only to check existence | `Mono<Boolean>` | Returns existence result |
| Multiple rows possible | `Flux<T>` | Emits multiple reactive results |
| At most one row | `Mono<T>` | Represents 0 or 1 result |

Choose the return type to match cardinality. A projection DTO does not determine whether a query returns one or many rows; that is why `Mono` and `Flux` still must be chosen separately.

## 12. Limitations and Edge Cases Requiring Care

### 12.1. Nested Projections Do Not Automatically Generate Joins

A nested accessor does not mean Spring Data R2DBC will automatically create joins or load another aggregate. Spring Data Relational does not behave like an ORM that automatically lazy-loads an object graph.

If data from another table is needed, write an appropriate join query using `@Query` or `DatabaseClient`, or execute separate queries and combine publishers in the service.

### 12.2. Open Projections Are Hard to Column-Optimize

SpEL expressions can reference multiple properties, making it difficult for the framework to determine the exact set of columns to read. Closed projections and DTOs with explicit constructors are usually more predictable.

### 12.3. Dynamic Projections Do Not Replace Query Design

`Class<T>` only selects the result type. It does not simplify a complex query, create automatic joins, or add filter conditions.

If two result types require substantially different SQL, split the query methods or use a custom repository fragment.

### 12.4. Constructor Mapping Depends on Property Names

DTO projections require constructor parameters matching properties/aliases. Mismatched names or insufficient data can cause mapping errors or missing values.

How to handle: verify Java properties, column names, and SQL aliases; for classes with multiple constructors, designate the persistence constructor.

### 12.5. Partial Projections Do Not Carry Full Persistence State

A DTO may omit IDs or `version`. Use it on the read path; if writes are needed, load the full entity or execute a dedicated update statement with explicit conditions.

### 12.6. Not All Query Methods Optimize SELECT the Same Way

Derived queries, `@Query`, and custom repositories follow different SQL generation paths. Inspect the actual SQL if ensuring only needed columns are selected is required.

## 13. Common Mistakes

**Using the wrong `Class` type in dynamic projections**

The method requires a matching generic type:

~~~java
<T> Flux<T> findByActiveTrue(Class<T> type);
~~~

If the `Class` type does not match the generic return type, Spring Data may not recognize it as a projection parameter.

**DTO names not matching properties**

A DTO has component `name` while the entity property is `fullName`; the converter may not map as expected. Rename the component or use an appropriate SQL alias.

**Projection missing columns needed by the constructor**

If a DTO constructor requires three properties but the query returns only two columns, mapping may fail. Select sufficient data or adjust the DTO accordingly.

**Using a projection to save**

Projections do not necessarily include ID/`version` or aggregate state. Do not treat them as full entities.

**Assuming interface projections always reduce column counts**

A projection describes the result type; actual SQL depends on the query path and module. Inspect SQL statements if column optimization is a requirement.

**Using `Mono` for multi-row queries**

If a query can return multiple rows, use `Flux`. `Mono` represents at most one element.

**Using dynamic projections for distinct queries**

If each result type needs different joins or conditions, a single generic method no longer makes the API clear. Separate the methods or use a custom repository.

## 14. Design Principles

- Use full entities for business operations requiring aggregate state.
- Use closed interface projections for small, simple read views.
- Use DTOs/records when you want an independent read model type.
- Use dynamic projections when identical query criteria genuinely serve multiple result types.
- Name accessors and constructor parameters to match properties or aliases.
- With `@Query`, explicitly control the SELECT list and aliases.
- Do not assume nested projections automatically generate joins.
- Do not use partial projections to update entities.
- Choose `Mono` for at most one result and `Flux` for multiple results.
- Inspect actual SQL if column optimization needs verification.
- Use `DatabaseClient` for joins, aggregates, and custom mappings.
- Keep result type selection in repository/service contracts clear; avoid over-generalizing solely to reduce method counts.

## 15. Key Takeaways

Projections determine the shape of data returned by a query. Interface projections describe needed accessors; DTO/record projections construct concrete result types via constructors; dynamic projections allow passing `Class<T>` to choose the result type when calling the repository.

Dynamic projections are useful when the same search condition serves multiple callers with different read models. They do not automatically create joins, alter filter criteria, or guarantee that custom SQL selects the right columns for every result type. Use derived queries or `@Query` for fixed queries; use `R2dbcEntityTemplate` for dynamic entity-level criteria; use `DatabaseClient` for custom SQL and projections. Choosing the right result type and `Mono`/`Flux` ensures the repository contract expresses the exact data each use case requires.
