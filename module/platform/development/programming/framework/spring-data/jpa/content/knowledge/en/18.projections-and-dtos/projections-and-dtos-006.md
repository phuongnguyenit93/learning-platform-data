# Constructor-Based DTOs and Constructor Selection with @PersistenceCreator

## 1. What Is a DTO Projection?

In Spring Data JPA, projections allow a repository to return the exact subset of data a use case needs. Instead of loading an entire entity with all its attributes and relationships, the application can receive a DTO containing only an ID, name, email, or a few aggregated values.

Class-based projections (DTO projections) use a constructor to instantiate the result object. The JPA provider or Spring Data takes the values from the query and passes them into the matching constructor. A DTO is typically a read-only object used to transfer data between repositories, services, and APIs; it does not become a managed entity in the persistence context.

For example, a customer list screen only needs IDs and names:

- The `Customer` entity might contain email, address, status, order relationships, and many other attributes.
- The `CustomerSummary` DTO holds only the ID and name.
- The repository returns `CustomerSummary` to reduce loaded data and clarify the response structure.

An important distinction is that a DTO projection constructor is not the constructor Hibernate uses to instantiate a JPA entity. Entities have their own instantiation contract under Jakarta Persistence; DTO projections are instantiated using the constructor selected by the query or Spring Data.

## 2. Basic Class-Based DTO Projections

### 2.1. Creating a DTO with a Matching Constructor

DTO example:

```java
package com.example.customer.dto;

public class CustomerSummary {

    private final Long id;
    private final String name;

    public CustomerSummary(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

A DTO does not need `@Entity`, `@Table`, or ID mapping annotations. It only needs a constructor accepting the values to return and the accessors used by the service/controller.

Fields can be `final` to represent immutable data after creation. A DTO does not require a no-argument constructor as required by the JPA Entity contract. The constructor must accept the exact count, order, and types expected by the projection mechanism.

### 2.2. Using the DTO in a Repository

A derived query can return a DTO:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<CustomerSummary> findByStatus(CustomerStatus status);
}
```

Spring Data JPA recognizes the return type as a class-based DTO projection and uses the DTO's constructor to create results. For derived queries, constructor parameter names are used to identify the properties to fetch from the entity. Therefore, parameter names should match the Java property names of the entity.

For example, if the DTO has constructor `CustomerSummary(Long id, String name)`, the `id` and `name` properties of `Customer` are the required projection attributes.

### 2.3. Retaining Parameter Names During Java Compilation

To allow Spring Data to discover constructor parameter names in Java classes, compile with the `-parameters` flag.

With Gradle:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

With the Maven Compiler Plugin, configure the corresponding compiler option:

```xml
<configuration>
    <parameters>true</parameters>
</configuration>
```

Spring Boot and build plugin versions may already configure some defaults, but verify that your project's bytecode retains parameter names if projections rely on them. If parameter names are not preserved, Spring Data may fail to identify the required properties as expected.

Constructor parameter names are Java property names, not SQL column names. If the entity uses `@Column(name = "customer_name")` for the `name` field, the DTO parameter should still be `name` when the projection is based on entity properties.

## 3. When a DTO Has Multiple Constructors: Using @PersistenceCreator

### 3.1. The Constructor Ambiguity Problem

A DTO may have multiple ways to be constructed:

```java
public class CustomerSummary {

    private final Long id;
    private final String name;

    public CustomerSummary(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public CustomerSummary(Long id, String name, String prefix) {
        this(id, prefix + name);
    }

    // getters
}
```

When multiple constructors exist, Spring Data needs to know which constructor creates the projection. Without a single default constructor or an explicit selection rule, projection creation may fail because no unambiguous matching constructor can be determined.

### 3.2. Marking the Chosen Constructor

Spring Data provides the annotation:

```java
import org.springframework.data.annotation.PersistenceCreator;
```

Annotate the constructor you want Spring Data to use:

```java
package com.example.customer.dto;

import org.springframework.data.annotation.PersistenceCreator;

public class CustomerSummary {

    private final Long id;
    private final String name;

    @PersistenceCreator
    public CustomerSummary(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public CustomerSummary(Long id, String name, String prefix) {
        this(id, prefix + name);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

When a class has multiple constructors, `@PersistenceCreator` indicates the constructor preferred by Spring Data when instantiating objects through Spring Data's mapping mechanism. The selected constructor must still match the properties and values required by the projection.

### 3.3. This Annotation Belongs to Spring Data, Not JPA

Be sure to import the right type:

```java
org.springframework.data.annotation.PersistenceCreator
```

This is a Spring Data Commons annotation. It is not `jakarta.persistence.PersistenceContext`, not `@Entity`, and not a standard annotation to tell Hibernate which constructor to use when instantiating an entity.

Comparison:

| Mechanism | Purpose |
|---|---|
| DTO projection constructor | Instantiates a result object from query values |
| `@PersistenceCreator` | Specifies the constructor or factory method Spring Data should use when instantiating objects via Spring Data mapping |
| Entity no-arg constructor | Allows the JPA provider to instantiate an entity before hydrating data |
| JPQL `select new` | Invokes the constructor whose signature matches the expressions in the constructor expression |

Do not add `@PersistenceCreator` to an entity expecting Hibernate to use it instead of a no-arg constructor under the JPA contract. For DTO projections, the annotation helps Spring Data resolve constructor selection when a class has multiple constructors.

## 4. Constructor Selection Rules

You can apply the following practical rules:

1. If a DTO has only one suitable constructor, Spring Data can usually use that constructor.
2. If a DTO has multiple constructors, mark the desired one with `@PersistenceCreator`.
3. The selected constructor must have parameters corresponding to the properties to project.
4. Keep parameter names clear and matching Java property names when Spring Data needs to infer input properties.
5. When using a `record` with a single canonical constructor, you usually do not need an annotation to select the constructor.
6. When using a JPQL constructor expression, the constructor is selected by the count, order, and types of expressions in `select new`; `@PersistenceCreator` does not replace matching that signature.

Spring Data also supports static factory methods annotated with `@PersistenceCreator` in its object mapping mechanisms. However, JPQL `select new` is a JPA constructor expression and invokes a constructor matching the signature in the query; do not assume the provider will invoke a static factory method.

## 5. JPQL Constructor Expressions with select new

### 5.1. Writing Explicit Constructor Expressions

JPQL supports constructing DTOs using the `select new` syntax:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select new com.example.customer.dto.CustomerSummary(
            c.id,
            c.name
        )
        from Customer c
        where c.status = :status
        order by c.name
        """)
    List<CustomerSummary> findSummariesByStatus(
        @Param("status") CustomerStatus status
    );
}
```

Rules to remember:

- Use the fully qualified class name of the DTO.
- Expression order must match constructor parameter order.
- Expression data types must be compatible with parameter types.
- The DTO must have a matching constructor.
- Do not add aliases to individual expressions inside the constructor expression.

For example, `select new com.example.CustomerSummary(c.id as id, c.name as name)` is not valid JPQL constructor expression syntax. Aliases are typically used for tuple/interface projections; with `select new`, list the expressions directly in constructor order.

### 5.2. What Role Does @PersistenceCreator Play in select new?

With the query:

```sql
select new com.example.customer.dto.CustomerSummary(c.id, c.name)
from Customer c
```

The JPA provider looks for a constructor with two parameters compatible with the types of `c.id` and `c.name`. JPQL constructor resolution relies on the constructor expression and Java signature.

`@PersistenceCreator` primarily helps Spring Data choose a constructor during DTO mapping. It does not make an incompatible constructor valid for JPQL `select new`. When writing an explicit constructor expression, check the constructor signature and parameter order first.

### 5.3. Spring Data JPA Query Rewriting

In certain cases, Spring Data JPA can rewrite JPQL automatically to use a constructor expression when a method returns a class-based DTO projection. For instance, a query originally selecting the entity root or a list of expressions may be transformed into `select new ...`.

However, rewriting depends on the query structure and Spring Data JPA version. If the query already has a constructor expression, the framework does not need to rewrite it. For complex queries, write `select new` explicitly to state the exact DTO to construct and test on your active version.

Do not put unnecessary aliases in the select list if you intend for Spring Data to rewrite it into a constructor expression. Aliases fit tuple-based projections, not `select new` syntax.

## 6. Using Java Records as DTO Projections

Records are a natural fit for immutable DTOs:

```java
package com.example.customer.dto;

public record CustomerSummary(Long id, String name) {
}
```

A record has a canonical constructor matching its record components. With a single canonical constructor, Spring Data can usually resolve the constructor without `@PersistenceCreator`.

Repository:

```java
List<CustomerSummary> findByStatus(CustomerStatus status);
```

Or explicit JPQL:

```java
@Query("""
    select new com.example.customer.dto.CustomerSummary(
        c.id,
        c.name
    )
    from Customer c
    where c.status = :status
    """)
List<CustomerSummary> findSummariesByStatus(
    @Param("status") CustomerStatus status
);
```

Records work well when the DTO only carries data and needs no setters. A record is not a regular JPA entity: records are `final` and follow the canonical constructor model, whereas entities have specific requirements for constructors and proxying.

If a record defines additional secondary constructors, keep the canonical constructor clear and verify how your Spring Data version resolves projections. Do not add annotations out of habit if the record already has a single matching constructor.

## 7. DTO Projections from Derived Queries and @Query

### 7.1. Derived Queries

Example:

```java
List<CustomerSummary> findByStatus(CustomerStatus status);
```

Spring Data relies on the return type and DTO constructor to create the projection. For DTO classes with multiple constructors, use `@PersistenceCreator` to specify the constructor. Constructor parameter names are used to identify the properties to fetch in class-based projections; preserve parameter names and enable `-parameters` when needed.

### 7.2. @Query with Automatic Rewriting

You can declare a query selecting the entity root:

```java
@Query("""
    select c
    from Customer c
    where c.status = :status
    """)
List<CustomerSummary> findSummaries(
    @Param("status") CustomerStatus status
);
```

Spring Data JPA can rewrite the query into a constructor projection when it detects a DTO projection and compatible query structure. Do not rely on this behavior as guaranteed for every JPQL query. If you want to avoid relying on rewriting, write an explicit constructor expression.

### 7.3. @Query with Constructor Expressions

```java
@Query("""
    select new com.example.customer.dto.CustomerSummary(
        c.id,
        c.name
    )
    from Customer c
    where c.status = :status
    """)
List<CustomerSummary> findSummariesExplicitly(
    @Param("status") CustomerStatus status
);
```

This directly shows the attribute list and constructor used. It is particularly useful when a query has joins, complex conditions, or multiple distinct projections.

## 8. Native Queries and Constructor DTOs

Native SQL does not use JPQL `select new` syntax. Mapping SQL results to a DTO depends on column order, JDBC types, and the mapping mechanism.

### 8.1. Direct Mapping When Order and Types Match

In some cases, Spring Data JPA can construct class-based projections from native queries if columns are returned in the exact order and compatible types expected by the DTO constructor.

DTO example:

```java
public record CustomerSummary(Long id, String name) {
}
```

Illustrative native query:

```java
@Query(
    value = """
        select c.id, c.name
        from customer c
        where c.status = :status
        order by c.name
        """,
    nativeQuery = true
)
List<CustomerSummary> findNativeSummaries(
    @Param("status") String status
);
```

Verify actual returned column types and order. For example, the database might return a different numeric type than the Java type expected; incompatible conversions can cause mapping errors.

### 8.2. When @SqlResultSetMapping Is Needed

If column order, aliases, or result types do not match the DTO constructor, you can use `@SqlResultSetMapping` with `@ConstructorResult` and `@ColumnResult` in Jakarta Persistence, or a custom repository for explicit mapping.

Mapping structure example:

```java
@SqlResultSetMapping(
    name = "CustomerSummaryMapping",
    classes = @ConstructorResult(
        targetClass = CustomerSummary.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "customer_name", type = String.class)
        }
    )
)
@Entity
@Table(name = "customer")
public class Customer {
    // Entity mappings and JPA constructor are declared here.
}
```

This shows the annotation structure; the entity still needs a complete ID, constructor, and valid mappings. This mapping specifies which result columns are passed into the DTO constructor. `@PersistenceCreator` does not replace `@SqlResultSetMapping` and does not handle column renaming or type conversion in native SQL.

## 9. Common Limitations and Pitfalls

### 9.1. No Compatible Constructor

If JPQL asks for `new CustomerSummary(Long, String)` but the DTO only has a constructor taking `Customer`, the provider cannot create the projection. Check the parameter count, order, and types.

### 9.2. Multiple Constructors Without Specifying One for Spring Data

With class-based DTO projections, multiple constructors can prevent Spring Data from knowing which constructor to use for mapping. Mark the right constructor with `@PersistenceCreator` or simplify the DTO to have only one suitable constructor.

### 9.3. Parameter Names Do Not Match Properties

With derived class-based projections, Spring Data must determine properties from constructor parameter names. If the entity has `firstName` but the DTO names the parameter `name`, the framework may fail to locate the intended property. Match parameter names to Java properties and keep `-parameters` metadata.

### 9.4. Confusing Column Names with Property Names

Derived projections rely on entity properties. If the database column is `customer_name` while the Java property is `name`, the constructor parameter generally needs to be `name`. With native queries, aliases/columns and result types must match the native mapping mechanism.

### 9.5. Using Primitives for Nullable Values

If a column can be null, avoid constructors accepting primitives like `long` or `int` for that value. Use wrapper types `Long` or `Integer` to represent null safely. Unboxing null can throw a `NullPointerException`.

### 9.6. Mistaking DTOs for Entities

DTO projections are not managed like entities. Modifying fields on a DTO is not dirty-checked and is not automatically persisted to the database. To update data, load a managed entity inside a transaction or use an appropriate update statement.

### 9.7. Lombok Generating Extra Constructors

Annotations like `@AllArgsConstructor`, `@NoArgsConstructor`, or `@Builder` can generate extra constructors and change how Spring Data sees the DTO. When multiple constructors exist, inspect the generated bytecode and place `@PersistenceCreator` on the right constructor if the mapping mechanism needs it.

Do not apply `@Value` mechanically to JPA entities; its final class and fields are unsuitable for regular entities. For DTOs, immutable classes are a reasonable choice when projection constructors are configured properly.

### 9.8. Constructors with Side Effects

A DTO constructor should only assign and perform simple normalization on data. Do not call services, repositories, open transactions, or perform I/O inside a constructor. The provider/Spring Data may instantiate many DTOs when a query returns many rows; side effects in constructors make behavior unpredictable and hard to test.

## 10. Choosing a DTO Projection or an Interface Projection?

| Criterion | Class-based DTO | Interface projection |
|---|---|---|
| Result creation | Invokes constructor | Usually uses a proxy implementing the interface |
| Structure | Class or record | Interface |
| Immutability | Easy to design as immutable | Usually declares getters only |
| Constructor | Requires a matching constructor | No DTO constructor needed |
| Constructor selection | Can use `@PersistenceCreator` | Not applicable |
| Explicit JPQL | Uses `select new` | Usually uses tuple/aliases |
| Transformation logic | Simple logic can live in DTO | Can use default methods or SpEL as supported |
| Best suited for | Well-structured API responses/value objects | Simple getter-based projections |

Choose class-based projections when you want a concrete, immutable return type with an explicit constructor. Choose interface projections when you only need simple getters and want Spring Data to generate projection proxies. For complex business logic or mapping, consider a separate service mapper rather than overloading DTO constructors.

## 11. Testing Constructor Projections

An integration test should verify that the repository instantiates the right DTO with values in the right order:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void mapsCustomerToConstructorProjection() {
        Customer customer = new Customer(
            "An",
            CustomerStatus.ACTIVE
        );
        entityManager.persist(customer);
        entityManager.flush();
        entityManager.clear();

        List<CustomerSummary> result =
            repository.findByStatus(CustomerStatus.ACTIVE);

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getName()).isEqualTo("An");
    }
}
```

The example assumes the `Customer` entity has a constructor and mapping matching the two passed attributes. If the DTO is a record, use the accessor `name()` instead of `getName()`. Tests should verify:

- The right constructor is selected when a DTO has multiple constructors.
- Parameter names match properties for derived projections.
- JPQL constructor expressions have the right FQCN, parameter order, and types.
- Native queries return columns matching the mapping.
- Null values are handled via wrapper types.
- DTOs are not treated as managed entities.
- Queries select only the needed columns when the projection permits it.

For native SQL and database-specific types, run integration tests against the same database type used in production. H2 may differ in data types and result mapping behavior.

## 12. Checklist for Choosing and Configuring Constructors

- [ ] The DTO is a class/record used as a projection result, not confused with an entity.
- [ ] The constructor accepts the exact data to return.
- [ ] The DTO has a single suitable constructor, or the chosen one is marked with `@PersistenceCreator`.
- [ ] Import the right `org.springframework.data.annotation.PersistenceCreator`.
- [ ] Parameter names match Java properties when using derived class-based projections.
- [ ] The build preserves parameter names via `-parameters` when needed.
- [ ] JPQL `select new` uses the fully qualified class name.
- [ ] Expression order and types match the constructor expression.
- [ ] Do not place aliases inside the parameter list of `select new`.
- [ ] Native queries have compatible column order/types or explicit mapping.
- [ ] Nullable columns use appropriate wrapper types.
- [ ] Constructors contain no I/O or side effects.
- [ ] Integration tests cover constructor selection and returned data.

## 13. Conclusion

Class-based DTO projections instantiate result objects using constructors. With a single matching constructor, Spring Data can usually use it directly; when a DTO has multiple constructors, Spring Data's `@PersistenceCreator` identifies the constructor for Spring Data's mapping mechanism. Constructor parameter names must match Java properties when Spring Data infers projection attributes from the DTO.

JPQL `select new` follows its own rules: use the fully qualified class name and a constructor whose parameter count, order, and types match the query expressions. The provider resolves the constructor by the JPQL signature; `@PersistenceCreator` does not replace matching that signature. Records are a concise option for immutable DTOs with a canonical constructor. Native queries require compatible column order and types or mappings such as `@SqlResultSetMapping`.

Keep DTO projections distinct from JPA Entities, mark constructors explicitly when multiple choices exist, preserve parameter names when needed, and test on the real provider and database.
