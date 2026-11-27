# Using Java Records as DTO Projections in Spring Data JPA

## 1. What Is a DTO Projection?

In Spring Data JPA, repositories typically return entities mapped from database tables. Entities fit when the application needs to work with data managed by the persistence context, update attributes, track relationships, and save changes.

Many screens or APIs only need a subset of data. For instance, a customer list page only needs the ID, display name, and email; a revenue report only needs the customer ID and total amount. Loading the full entity along with unnecessary relationships can read extra columns, generate additional JOINs, hold many objects in the persistence context, and increase memory overhead.

A **DTO projection** allows a repository to return a type containing only the fields the query needs. A DTO (Data Transfer Object) is commonly used for read results or reports. In Java 16 and later, a `record` is a strong fit because it concisely provides a constructor, accessors, and standard value-based methods.

Example:

~~~java
package com.example.customer.dto;

public record CustomerSummary(
    Long id,
    String fullName,
    String email
) {}
~~~

The record above defines a DTO with three components. Java automatically generates the canonical constructor, accessors `id()`, `fullName()`, `email()`, plus `equals()`, `hashCode()`, and `toString()`.

Record DTOs help:

- Carry only the fields required by the use case.
- Provide immutability at the component-reference level.
- Reduce boilerplate compared to a traditional DTO class.
- Clarify the repository's return structure with a concrete Java type.
- Decouple the returned data model from persistence entities.

Records are best suited for read results. They do not replace entities and do not participate in JPA dirty checking.

## 2. How Do Records Differ from Entities?

A JPA entity represents data managed by the persistence provider. An entity has identity, a lifecycle, and managed, detached, or removed states. A record DTO is simply a Java object holding result data.

| Criterion | JPA entity | Record DTO |
|---|---|---|
| Purpose | Data model managed by the persistence context | Carries data for a use case or query result |
| JPA identity | Has `@Id` | Does not need `@Id` |
| Data changes | Can be dirty-checked when managed | Not tracked by JPA |
| Entity relationships | Can map `@OneToMany`, `@ManyToOne`, etc. | Typically holds scalars or selected data types |
| Constructor | Must satisfy JPA entity requirements | Uses the record's canonical constructor |
| Mutability | Usually has setters or state-mutating methods | Record components are `final` |
| `save()` | Can persist/merge if mapped properly | Not an object for repositories to save as an entity |

Java records are `final` types and do not meet the standard requirements of a JPA entity class. Do not annotate a record DTO with `@Entity` or add `@Id` expecting JPA to manage it as an entity. Use records as projection result types.

Record immutability is shallow: references to each component cannot be reassigned after construction, but if a component is a mutable object such as a `List`, the inner object can still be mutated. For DTOs returned by APIs, consider appropriate data types and defensive copying for collections.

## 3. Class-Based Projections with Records

Spring Data JPA supports class-based projections, also known as DTO projections. A record can serve as the return type of a repository method if its constructor matches the queried data.

Entity example:

~~~java
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;
    private String email;
    private CustomerStatus status;

    protected Customer() {}

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public CustomerStatus getStatus() {
        return status;
    }
}
~~~

Record DTO:

~~~java
package com.example.customer.dto;

public record CustomerSummary(
    Long id,
    String fullName,
    String email
) {}
~~~

The repository can declare a derived query:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<CustomerSummary> findByStatus(CustomerStatus status);
}
~~~

Spring Data JPA recognizes the `CustomerSummary` return type as a DTO projection. For derived queries, the framework can select only the required attributes based on the DTO's constructor/components and entity mapping. Record component names must match the entity property names required by the projection; constructor parameter types and order must also match the results.

This example belongs to the Spring Data JPA layer and requires entities, enums, repositories, dependencies, and an application datasource. It is not a standalone Java program runnable with `javac` alone.

## 4. Using JPQL Constructor Expressions

When you want explicit control over selected fields, you can use a JPQL constructor expression with `SELECT NEW`.

Example:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select new com.example.customer.dto.CustomerSummary(
            c.id,
            c.fullName,
            c.email
        )
        from Customer c
        where c.status = :status
        order by c.fullName
    """)
    List<CustomerSummary> findSummariesByStatus(
        @Param("status") CustomerStatus status
    );
}
~~~

JPQL will invoke the matching record constructor with the values in exact order:

1. `c.id` maps to the `id` component.
2. `c.fullName` maps to the `fullName` component.
3. `c.email` maps to the `email` component.

Rules to remember:

- Use the **fully qualified class name** of the DTO in `new`, including the package.
- Expression order in the constructor expression must match the canonical constructor parameter order.
- Each expression's result type must be compatible with the record component type.
- Do not add `AS` aliases to individual arguments inside the constructor expression.
- JPQL uses entity names and Java property names, not SQL table/column names directly.

Invalid example if class name or type order does not match:

~~~java
select new CustomerSummary(c.fullName, c.id, c.email)
from Customer c
~~~

The expression above does not match the `(Long id, String fullName, String email)` constructor. Reorder them properly or define a record matching the query.

## 5. Canonical Constructors and Record Component Names

Every record has a canonical constructor matching its declared component list:

~~~java
public record CustomerSummary(
    Long id,
    String fullName,
    String email
) {}
~~~

Semantically equivalent to a constructor taking `Long`, `String`, `String` in that order. Java generates this constructor automatically if you do not declare one explicitly.

Spring Data JPA uses constructor metadata to determine which attributes to select for class-based projections. With a standard record having only a canonical constructor, this structure is straightforward.

If you use a regular DTO class with multiple constructors, Spring Data may not know which constructor to use. In that case, mark the desired constructor with `@PersistenceCreator`. With records, the canonical constructor is normally the natural choice; just watch out if you add secondary constructors or alter the record structure.

Do not name record components arbitrarily if you want Spring Data to infer projections from derived queries. For instance, if the entity has `fullName` but the record declares `name`, the property names no longer match for the framework to infer the field to fetch. In that case, use an explicit JPQL constructor expression or match the property name.

## 6. Projections from Aggregate Queries

Records are especially useful when queries return computed values such as `COUNT`, `SUM`, `AVG`, or grouped data.

Example record for revenue by customer:

~~~java
package com.example.order.dto;

import java.math.BigDecimal;

public record CustomerRevenue(
    Long customerId,
    BigDecimal totalRevenue
) {}
~~~

Repository:

~~~java
@Query("""
    select new com.example.order.dto.CustomerRevenue(
        o.customer.id,
        sum(o.totalAmount)
    )
    from PurchaseOrder o
    where o.status = :status
    group by o.customer.id
    order by o.customer.id
""")
List<CustomerRevenue> summarizeRevenue(
    @Param("status") OrderStatus status
);
~~~

The query groups by customer and creates one record per group. `SUM` over a `BigDecimal` attribute typically returns the corresponding type per JPQL/provider rules; verify the return type of aggregate expressions against your actual mapping.

Key notes:

- `COUNT(...)` in JPQL returns `Long`; the record component receiving this value should be `Long`.
- `AVG(...)` has its own return type rules; do not assume it always matches the source column type.
- `SUM(...)` has a return type depending on the expression's numeric type per the JPQL specification.
- Groups with no matching rows do not produce a record with total 0; they do not appear in `GROUP BY` results.
- `SUM` can return `NULL` when there are no matching values; choose a reference type or handle with `COALESCE` according to business requirements.

Example using `COALESCE` if you want to replace NULL results with 0 using a compatible type:

~~~java
@Query("""
    select new com.example.order.dto.CustomerRevenue(
        o.customer.id,
        coalesce(sum(o.totalAmount), 0)
    )
    from PurchaseOrder o
    group by o.customer.id
""")
List<CustomerRevenue> summarizeAllRevenue();
~~~

Verify the type of literal `0` and `totalAmount` on your active provider. For monetary values, prefer `BigDecimal` and test precision/scale.

## 7. Record Projections vs. Interface Projections

Spring Data JPA has two common projection forms:

- **Interface-based projection:** declares an interface with getters; Spring Data usually creates a proxy to supply values.
- **Class-based projection:** uses a class or record with a constructor; the result is a DTO instance.

Interface example:

~~~java
public interface CustomerNameView {
    String getFullName();
    String getEmail();
}
~~~

Repository:

~~~java
List<CustomerNameView> findByStatus(CustomerStatus status);
~~~

Record example:

~~~java
public record CustomerNameDto(
    String fullName,
    String email
) {}
~~~

Repository:

~~~java
List<CustomerNameDto> findByStatus(CustomerStatus status);
~~~

Comparison:

| Criterion | Interface projection | Record DTO projection |
|---|---|---|
| Declaration | Interface and getters | Record components |
| Instance | Usually a proxy | Concrete record instance |
| Constructor | No DTO constructor needed | Needs a matching constructor |
| Immutability | Depends on accessor/proxy implementation | Record components are `final` |
| JPQL expression | Can project by property | Can use `SELECT NEW` |
| Best suited for | Simple views, nested projections when supported | Strongly typed DTOs, read models, aggregate results |

Choose interfaces when you need a simple view or supported nested projections. Choose records when you want a concrete DTO type that is immutable at the component level and easy to pass across layers.

Class-based projections do not support nested projections in the same way interface projections do. If you need nested structures, consider multiple queries, appropriate constructor expressions, or assembling DTOs in the service from queried data.

## 8. Dynamic Projections with Records

A repository method can accept `Class<T>` so the caller selects the projection type at call time:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    <T> List<T> findByStatus(
        CustomerStatus status,
        Class<T> projectionType
    );
}
~~~

Calling with a record:

~~~java
List<CustomerSummary> summaries =
    repository.findByStatus(
        CustomerStatus.ACTIVE,
        CustomerSummary.class
    );
~~~

The same query condition can return entities, interface projections, or record DTOs depending on the passed type, provided the projection type is compatible with the entity properties and Spring Data's projection mechanism.

Dynamic projections are useful when multiple use cases share the same filter conditions but need different field sets. However, do not overuse them to the point that repositories become hard to read. If each use case has different logic or JOINs, separate clearly named methods can be easier to maintain.

Spring Data recognizes a matching `Class<T>` parameter as a dynamic projection parameter. If you want to use a `Class` parameter as an ordinary query value, declare a different parameter type or design the method appropriately so Spring Data does not treat it as a projection selector.

## 9. Native SQL and Record DTOs

Native queries can return DTO classes/records in some scenarios, but you must pay attention to column order and data types.

Example native SQL selecting columns in the exact order of the canonical constructor:

~~~java
@Query(
    value = """
        select c.id, c.full_name, c.email
        from customer c
        where c.status = :status
        order by c.full_name
    """,
    nativeQuery = true
)
List<CustomerSummary> findNativeSummaries(
    @Param("status") String status
);
~~~

With class-based native projections, column order and JDBC types must match constructor parameter order and types. Column aliases can make queries easier to read, but do not assume aliases automatically resolve every difference between column names and record component names.

If a native query returns complex expressions, vendor-specific types, or an order that does not match the constructor, use `@SqlResultSetMapping` combined with `@ConstructorResult`, or a custom repository calling `EntityManager.createNativeQuery(sql, mappingName)`.

Standard JPA mapping example:

~~~java
@SqlResultSetMapping(
    name = "CustomerSummaryMapping",
    classes = @ConstructorResult(
        targetClass = CustomerSummary.class,
        columns = {
            @ColumnResult(name = "id", type = Long.class),
            @ColumnResult(name = "full_name", type = String.class),
            @ColumnResult(name = "email", type = String.class)
        }
    )
)
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    private Long id;
}
~~~

A custom repository can invoke the mapping:

~~~java
@SuppressWarnings("unchecked")
public List<CustomerSummary> findSummariesNative(String status) {
    return entityManager
        .createNativeQuery(
            "select id, full_name, email from customer where status = :status",
            "CustomerSummaryMapping"
        )
        .setParameter("status", status)
        .getResultList();
}
~~~

The mapping example must be placed where the JPA provider scans metadata; entity fields and packages must match the application. With native SQL, enum, UUID, timestamp, numeric types, and column aliases can vary across JDBC drivers and databases, so integration tests on the real DBMS are essential.

## 10. Pagination with Record DTOs

You can return `Page<RecordDto>` when you want to paginate projected data.

~~~java
@Query(
    value = """
        select new com.example.customer.dto.CustomerSummary(
            c.id,
            c.fullName,
            c.email
        )
        from Customer c
        where c.status = :status
        order by c.fullName
    """,
    countQuery = """
        select count(c)
        from Customer c
        where c.status = :status
    """
)
Page<CustomerSummary> findSummaryPage(
    @Param("status") CustomerStatus status,
    Pageable pageable
);
~~~

The content query constructs a record per customer. `countQuery` counts matching entities so Spring Data can build page metadata.

If the main query has a one-to-many JOIN and `DISTINCT`, the count query must count the exact element type returned by the page, typically `count(distinct c.id)` when the goal is unique customers. With `GROUP BY`, review pagination semantics and you may need a separate, more complex count query.

If you only need page data and whether a next page exists, `Slice<CustomerSummary>` can avoid fetching the total element count. Choose `Page` when total pages or total record count are genuinely needed.

## 11. Can Record DTOs Update Entities?

Record projections are generally used for read flows. Returned record instances are not managed by the persistence context, so:

- Changing source data in the database does not automatically update already-returned records.
- Dirty checking cannot be used on records.
- Repository `save()` will not persist a record as an entity because a record is not a valid entity.
- To update data, load a managed entity inside a transaction, modify the entity, and let JPA flush.

Proper update example:

~~~java
@Transactional
public void updateCustomerEmail(Long id, String newEmail) {
    Customer customer = customerRepository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Customer not found"));

    customer.changeEmail(newEmail);
}
~~~

Afterward, if you need to return a DTO, map the entity to a record:

~~~java
@Transactional
public CustomerSummary updateAndReturn(
        Long id,
        String newEmail) {

    Customer customer = customerRepository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Customer not found"));

    customer.changeEmail(newEmail);

    return new CustomerSummary(
        customer.getId(),
        customer.getFullName(),
        customer.getEmail()
    );
}
~~~

The service snippet illustrates the pattern: the entity is managed within the transaction, while the record serves purely as returned data. The `changeEmail` method is domain logic on the example entity and needs to be defined in the `Customer` class.

## 12. Performance Benefits and Limitations

DTO projections can reduce the amount of data read and the number of entity objects instantiated. When selecting only the needed scalars, the provider can avoid loading unused columns or relationships.

Common benefits:

- Less data transferred from the database to the application.
- Fewer entities materialized and tracked in the persistence context.
- Lower risk of accidentally accessing lazy relationships in the presentation layer.
- Return types express the exact data the use case requires.

However, DTO projections do not automatically guarantee faster queries. Performance also depends on:

- JOINs and filter predicates.
- Indexes and execution plans.
- Number of rows returned.
- Aggregations, sorting, and pagination.
- How the provider generates SQL.
- Whether the DTO requires multiple relationships or computed expressions.

If a record projection uses a relationship such as `c.address.city`, the provider may generate a JOIN to fetch that field. Inspect the generated SQL rather than judging solely by the number of components in the record.

A DTO query also does not automatically prevent N+1 in all cases. If a service calls another repository per record or executes other queries in a loop, N+1 can still occur.

## 13. Common Pitfalls When Using Record Projections

### 13.1. Wrong Package in SELECT NEW

A JPQL constructor expression requires the fully qualified class name of the DTO:

~~~java
select new com.example.customer.dto.CustomerSummary(
    c.id, c.fullName, c.email
)
~~~

If you only write `new CustomerSummary(...)` and the provider cannot resolve the class name, the query will fail. Check the exact package and class name.

### 13.2. Wrong Constructor Argument Order

If the record is `(Long id, String fullName, String email)`, the query must select expressions in that matching order and type. Swapping `id` and `fullName` will cause a constructor mismatch.

### 13.3. Data Type Mismatches

Aggregate expressions, enums, timestamps, UUIDs, or numeric types can return types different from the declared record component types. Check the JPQL spec, JDBC driver, and provider. Use wrappers like `Long` when values can be `NULL`; do not use primitives if the query can return `NULL`.

### 13.4. Component Names Do Not Match Entity Properties

With derived class-based projections, record component names help Spring Data identify which properties to fetch. If names differ from entity properties, use a JPQL constructor expression or align component names accordingly.

### 13.5. Treating Record DTOs as Entities

Do not annotate a record with `@Entity` to use it with `save()`. Keep entities for persistence and records for projection data.

### 13.6. Native Queries Returning Columns in the Wrong Order

When mapping native queries directly to records, column order and result types must match the constructor. If mapping is complex, use `@SqlResultSetMapping` or map manually in a custom repository.

### 13.7. Forgetting an Accurate Count Query When Paginating

A DTO page may display accurate content while reporting the wrong total element count if `countQuery` does not correspond to the main query. Check JOINs, `DISTINCT`, and `GROUP BY` in both queries.

## 14. Testing Record Projections

Use `@DataJpaTest` or integration tests with an appropriate database to verify queries and constructor mapping.

Example:

~~~java
@DataJpaTest
class CustomerProjectionRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void returnsCustomerSummary() {
        Customer customer = new Customer(
            "An Nguyen",
            "an@example.com",
            CustomerStatus.ACTIVE
        );
        repository.saveAndFlush(customer);

        List<CustomerSummary> result =
            repository.findByStatus(CustomerStatus.ACTIVE);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).fullName()).isEqualTo("An Nguyen");
        assertThat(result.get(0).email()).isEqualTo("an@example.com");
    }
}
~~~

This is a Spring Data JPA layer test example; entity constructors, repository methods, enums, imports, and test dependencies must match your project. There is no standalone Java stdout because the test runs inside the Spring test context.

You should also verify:

1. Does the record have the right constructor order and types?
2. Does the query select only the needed fields?
3. When no records match, does the repository return an empty list or empty `Optional` as expected?
4. Are nullable fields mapped safely?
5. Do aggregates return the expected types and values?
6. Do page content and total count match?
7. Does the native query run on the actual production database?
8. Does the SQL load unnecessary relationships or create unneeded JOINs?

For native projections or dialect-dependent queries, prefer Testcontainers or a test database equivalent to production rather than relying solely on H2.

## 15. Process for Choosing and Implementing Record DTO Projections

When building a data-reading use case:

1. Identify the exact fields needed by the screen, API, or report.
2. Create a record DTO with clear components, data types, and order.
3. Choose a derived query if projection properties are simple and component names match entity properties.
4. Choose JPQL `SELECT NEW` if you need explicit control over fields, conditions, JOINs, or expressions.
5. Choose native SQL when database-specific features are required; verify column order, JDBC types, and result mapping.
6. If using `Page`, declare or verify the corresponding count query.
7. Treat the record as read-only data; perform updates via managed entities inside a transaction.
8. Inspect generated SQL and write integration tests covering constructor mapping, `NULL`s, aggregates, and pagination.

## 16. Key Takeaways

- Java records (Java 16+) are a great fit for class-based DTO projections in Spring Data JPA.
- Record DTOs are not JPA entities and are not managed by the persistence context.
- Derived DTO projections require a constructor/components compatible with entity properties.
- JPQL `SELECT NEW` must use the fully qualified class name and pass arguments in canonical constructor order.
- Records allow concise DTO declarations, though immutability of components is shallow.
- DTO projections can select fewer columns than entity queries; performance still depends on SQL, JOINs, indexes, and execution plans.
- Records can be used for aggregate results, `Page<T>`, and dynamic projections when query types are compatible.
- Native queries require attention to column order and JDBC types; complex mappings may need `@SqlResultSetMapping`.
- To update data, load and modify a managed entity; do not pass record DTOs to `save()`.
- Test queries on the target database, especially with native SQL and specialized data types.

Using Java records as DTO projections helps repositories return the exact data a use case needs with clear type structure and minimal boilerplate. Keep records in the read-data role, let entities handle the persistence lifecycle, and verify constructors, result types, and actual SQL with integration tests.
