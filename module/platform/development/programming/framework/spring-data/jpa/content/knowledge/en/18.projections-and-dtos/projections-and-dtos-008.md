# Dynamic Projections with the Class<T> Parameter

## 1. What Is a Dynamic Projection?

A dynamic projection lets you choose the return type of a repository method at call time. The same query condition can return full Entities, an interface projection, or a DTO class/record depending on the `Class<T>` passed in.

The key point is that the repository only needs to declare a single generic method. Callers decide the shape of data to receive instead of creating a separate method for every projection.

Dynamic projections change the **result shape**. They do not automatically change filtering conditions, sorting, joins, or query business logic. If you need dynamic predicates based on parameters, combine them with Specifications, Querydsl, or an appropriate custom query.

## 2. Repository Structure with Class<T>

Suppose the `Customer` Entity has attributes `id`, `firstName`, `lastName`, `email`, and `status`. The repository can declare:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    <T> List<T> findByLastName(String lastName, Class<T> projectionType);
}
```

Spring Data recognizes the `Class<T>` parameter as a projection selector because the generic type `T` of the `Class` parameter matches the generic type `T` in the `List<T>` return type. When the method is called, the framework uses the passed class to decide how to project the results.

Example of three result types:

```java
List<Customer> entities =
    repository.findByLastName("Nguyen", Customer.class);

List<CustomerNameView> names =
    repository.findByLastName("Nguyen", CustomerNameView.class);

List<CustomerSummary> summaries =
    repository.findByLastName("Nguyen", CustomerSummary.class);
```

All three calls use the same condition `lastName = "Nguyen"`. The difference lies in the requested result type.

## 3. Using Interface Projections

A closed interface projection declares only the required accessors:

```java
public interface CustomerNameView {
    Long getId();
    String getFirstName();
    String getLastName();
}
```

Calling the repository:

```java
List<CustomerNameView> result =
    repository.findByLastName("Nguyen", CustomerNameView.class);

for (CustomerNameView customer : result) {
    System.out.println(customer.getFirstName() + " " + customer.getLastName());
}
```

Spring Data creates a projection matching the interface. Accessors must match the Java property names of the Entity: `getFirstName()` maps to `firstName`, not the physical column name `first_name`.

With closed projections, the framework knows the set of requested properties and can optimize the query to fetch only the required data. Nested projections or open projections with SpEL can reduce this optimization; inspect the actual SQL.

## 4. Using DTO Classes or Records

Dynamic projections can also select a DTO class. The DTO needs a constructor matching the selected data; Java records are a concise choice because of their auto-generated canonical constructor:

```java
public record CustomerSummary(
    Long id,
    String firstName,
    String lastName
) {
}
```

Calling the repository:

```java
List<CustomerSummary> summaries =
    repository.findByLastName("Nguyen", CustomerSummary.class);
```

With regular DTO classes, Spring Data must determine which constructor to use for creating results. If multiple constructors exist, annotate the right constructor with `@PersistenceCreator` as required by Spring Data. Constructor parameters must match the projected properties in count, order, and type.

Do not confuse dynamic projections with automatically mapping any arbitrary class. The passed type must be an Entity or a valid projection for the query; a DTO without a compatible constructor will fail when creating or executing the query.

## 5. Using the Entity as the Result Type

Pass `Customer.class` to receive full Entities:

```java
List<Customer> customers =
    repository.findByLastName("Nguyen", Customer.class);
```

In this case, the results are `Customer` Entities managed according to JPA persistence context rules. Callers can use Entity attributes and relationships, but must account for lazy loading, dirty checking, and avoiding serializing Entities directly to APIs.

When only reading data for lists or responses, interface projections/DTOs usually help restrict data and decouple API contracts from Entities.

## 6. Why Is Generic Class<T> Recognized by the Framework?

The important signature is:

```java
<T> List<T> findByLastName(String lastName, Class<T> projectionType);
```

Spring Data treats `Class<T>` as a dynamic projection parameter when the generic `T` of the `Class` parameter matches the generic type of the query method's return type. The framework uses this value to pick the projection and does not treat it as an ordinary query bind parameter.

Consequently, in a query with named parameters, you cannot assume you can bind the projection selector `Class<T>` itself as `:type` in JPQL or as a value in SpEL. It is reserved for the projection mechanism.

## 7. Distinguishing Class<T> and Class<?>

Sometimes a repository genuinely needs to accept a `Class` object as a query parameter. In that case, you must prevent Spring Data from recognizing it as a dynamic projection selector.

- `Class<T>` whose generic `T` matches the return type `T`: Spring Data can recognize it as a projection parameter.
- `Class<?>` does not bind a generic to the return type in that way: the framework does not treat it as a dynamic projection selector from this parameter alone, so it can be treated as a normal query parameter.

General signature example:

```java
<T> List<T> findByLastNameAndEntityType(
    String lastName,
    Class<?> entityType,
    Class<T> projectionType
);
```

In this example, `projectionType` chooses the result type; `entityType` is a separate `Class` parameter. If binding a `Class` into JPQL/native queries, verify the expression, parameter type, and JPA provider/database support. Not every position in JPQL accepts a `Class` as a value.

Practical rule: use `Class<T>` for dynamic projections; use `Class<?>` when `Class` must be a regular data parameter and the query/provider supports that type.

## 8. Combining with @Query

Dynamic projections are demonstrated most clearly with derived queries. You can use projections with declared repository queries, provided the query and result type are compatible. For JPQL, the query must return the Entity or expressions that the projection can map; for DTO constructor expressions, parameter count, order, and types must match the constructor.

Example query returning the Entity root for the framework to apply projections:

```java
@Query("select c from Customer c where c.lastName = :lastName")
<T> List<T> searchByLastName(
    @Param("lastName") String lastName,
    Class<T> projectionType
);
```

When using native queries, column aliases, data types, and how the provider converts results into interfaces/DTOs must be tested against the real database. Complex native projections may require result-set mappings or a custom repository rather than expecting the framework to infer every mapping.

Do not declare a fixed constructor expression for one DTO and expect the same query to automatically turn into an arbitrary interface or Entity. A constructor expression locks in the result shape; design queries around the projection types actually supported.

## 9. Dynamic Projection Is Not Dynamic Filtering

Two needs are frequently confused:

| Need | Appropriate mechanism |
| --- | --- |
| Same filter, caller chooses Entity, interface, or DTO | Dynamic projection `Class<T>` |
| Optional filters depending on the request | Specification or Querydsl |
| Fixed query conditions, explicit JPQL needed | `@Query` |
| Database-specific SQL | Native query/custom repository |

For example, `findByLastName("Nguyen", CustomerNameView.class)` still filters by last name. It does not allow the caller to pass an arbitrary column name to alter `WHERE`. To change predicates, build separate predicates from validated inputs.

## 10. Combining with Page, Slice, and Other Return Types

Dynamic projections can be combined with compatible repository return types such as `List<T>`, `Collection<T>`, `Page<T>`, or `Slice<T>`:

```java
<T> Page<T> findByStatus(
    CustomerStatus status,
    Class<T> projectionType,
    Pageable pageable
);
```

Callers can request:

```java
Page<CustomerNameView> page = repository.findByStatus(
    CustomerStatus.ACTIVE,
    CustomerNameView.class,
    PageRequest.of(0, 20)
);
```

`Page<T>` provides the total element count and can issue a count query; `Slice<T>` only checks whether a next page exists. If the query uses joins, `distinct`, or `group by`, inspect the count query and pagination. Dynamic projections do not solve collection fetch-join pagination issues.

With `Stream<T>`, pay attention to transactions and closing the stream properly; do not keep repository streams open outside the transaction lifecycle.

## 11. Limitations and Performance Considerations

- Every projection type must be compatible with the Entity/query. You cannot pass an arbitrary class and expect Spring Data to know how to instantiate it.
- Interface projections depend on accessor/property names and aliases when queries return tuples/scalars.
- DTO classes depend on constructors and parameter types.
- Nested projections may fetch additional data via association joins; inspect SQL to verify actual columns.
- Open projections using SpEL can restrict column-selection optimization because the framework does not know exactly which properties will be accessed.
- Queries returning Entities can trigger lazy loading or dirty checking; DTO/interface projections are usually better suited for read-only use cases.
- Selecting the result type at runtime does not make a query inherently faster. Measure SQL, column count, row count, and execution plans.

## 12. Do Not Let Clients Choose Arbitrary Classes

The `Class<T>` parameter should be selected by application code from allowed projections. Do not accept an arbitrary class name from an HTTP request and use reflection to load the class and pass it straight into the repository.

If an API needs to let clients choose the response format, use an enum/string allow-list and map it in the service:

```java
public enum CustomerViewType {
    NAME,
    SUMMARY
}
```

```java
public Object search(String lastName, CustomerViewType viewType) {
    return switch (viewType) {
        case NAME -> repository.findByLastName(
            lastName, CustomerNameView.class
        );
        case SUMMARY -> repository.findByLastName(
            lastName, CustomerSummary.class
        );
    };
}
```

This is an illustrative service snippet; in a real application, you can use a common return type or explicit response wrapper instead of `Object`. An allow-list keeps projection choices within the scope supported by the API.

## 13. Testing Dynamic Projections

Integration tests should verify each projection type against the same dataset:

1. Call the method with `Customer.class`, verifying the Entity and required attributes.
2. Call with a closed interface projection, verifying each accessor returns the right value.
3. Call with a DTO record/class, verifying constructor mapping order and types.
4. Test zero records, multiple records, null values, and duplicate data.
5. If using `Page<T>`, verify content, total count, sorting, and count query.
6. Inspect actual SQL to confirm the projection fetches an appropriate column set.
7. If using `@Query` or native SQL, run tests on the target database/provider.

Tests must not only verify that the repository returns the right number of elements; call the accessors or read DTO components to catch mapping errors.

## 14. Common Pitfalls and How to Fix Them

**`Class<T>` is not recognized as a dynamic projection.** Check whether the generic `T` in the `Class<T>` parameter matches the generic type of the method's return value.

**Tried to bind the projection `Class` in the query, but the parameter does not exist.** The framework consumed `Class<T>` as the projection selector. If you need `Class` as query data, use `Class<?>` and bind it in an expression supported by the provider.

**Interface accessor returns null.** Check that the accessor matches the Java property or projection alias; do not use physical column names instead of property names.

**DTO fails to instantiate.** Check the constructor, parameter count, order, and types; with multiple constructors, mark the selected constructor with `@PersistenceCreator`.

**Native projection fails on another database.** Check aliases, case folding, data types, and result-set mappings.

**Projection returns more data than expected.** Check for nested associations or open projections/SpEL; inspect SQL and consider an explicit DTO query.

**Page total count is inaccurate.** Check the count query, joins, `distinct`, and `group by` independently of the projection type.

## 15. Checklist for Using Class<T>

- Declare generic method `<T> List<T> find...( ..., Class<T> projectionType)`.
- Choose an appropriate Entity, closed interface projection, or DTO class/record.
- Ensure accessors match Java properties; query aliases match projection names.
- For DTOs, ensure a compatible constructor; use `@PersistenceCreator` if disambiguation is needed.
- Use `Class<?>` if `Class` must be a regular query parameter rather than a projection selector.
- Do not confuse choosing result types with changing filter predicates.
- Allow-list projection types when selection originates from an API.
- Test each projection and inspect the actual SQL.

Dynamic projections with `Class<T>` enable a single repository method to serve multiple result shapes while keeping query conditions consistent. Using generics properly, choosing projections intentionally, and testing mappings keep repository callers flexible without blurring data contracts.
