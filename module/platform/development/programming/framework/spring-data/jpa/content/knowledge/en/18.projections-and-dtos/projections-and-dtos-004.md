# Nested Projections and the Risk of Unexpected Association Loading in Spring Data JPA

Projections allow a repository to return the data shape the caller needs instead of returning the full entity. With interface projections, Spring Data JPA can create a proxy to expose the properties declared in the interface. Nested projections extend this approach: a getter can return another projection interface representing an association of the root entity.

Nested projections make read APIs concise and well organized, but they do not guarantee that the database reads only a single field at the nested association level. Spring Data JPA can optimize the top-level properties of a projection; a nested property requiring a JOIN may cause the entire related property to be materialized. If the association is a collection, the result can also multiply rows, increase transferred data, and make pagination difficult.

This lesson analyzes the mechanism, illustrates it with `Customer` and `Address`, compares nested projections with flat interface projections and DTOs, and shows how to inspect SQL to detect unexpected data loading.

## 1. What Are Projections and Nested Projections?

Suppose the `Customer` entity has name fields and a relationship to `Address`. A list screen only needs the ID, customer name, and city.

If the repository returns the entity:

~~~java
List<Customer> findByLastName(String lastName);
~~~

the caller receives the `Customer` entity. When reading `customer.getAddress().getCity()`, the provider may have to load the `Address` association. If the caller serializes the entity, other getters or other relationships might also be accessed unintentionally.

An interface projection declares only the required data:

~~~java
public interface CustomerNameView {
    Long getId();
    String getFirstName();
    String getLastName();
}
~~~

A nested projection allows representing a relationship using a child interface:

~~~java
public interface CustomerCard {
    Long getId();
    String getFirstName();
    String getLastName();

    AddressView getAddress();

    interface AddressView {
        String getCity();
    }
}
~~~

The repository can return the projection directly:

~~~java
List<CustomerCard> findByLastName(String lastName);
~~~

Caller usage:

~~~java
for (CustomerCard customer : customers) {
    String name = customer.getFirstName() + " " + customer.getLastName();
    String city = customer.getAddress() == null
            ? null
            : customer.getAddress().getCity();
}
~~~

Nested projections make the Java API easy to read: `CustomerCard` contains `AddressView`. However, the interface structure does not mean the SQL `SELECT` only fetches `address.city`.

## 2. Illustrative Entity Model

Suppose a customer may not have an address yet or has one primary address. The example uses a Many-to-One relationship to focus on association loading behavior; you can replace it with One-to-One depending on the business model.

### 2.1. Address Entity

Create `Address.java`:

~~~java
package com.example.projection;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "addresses")
public class Address {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String street;

    @Column(nullable = false, length = 100)
    private String city;

    @Column(length = 20)
    private String postalCode;

    protected Address() {
    }

    public Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public Long getId() {
        return id;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

### 2.2. Customer Entity

Create `Customer.java`:

~~~java
package com.example.projection;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String firstName;

    @Column(nullable = false, length = 80)
    private String lastName;

    @Column(nullable = false, unique = true, length = 150)
    private String email;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "address_id")
    private Address address;

    protected Customer() {
    }

    public Customer(
            String firstName,
            String lastName,
            String email,
            Address address) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.address = address;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getEmail() {
        return email;
    }

    public Address getAddress() {
        return address;
    }
}
~~~

`Customer.address` is declared `LAZY` so the provider can defer loading the relationship. Remember that `FetchType.LAZY` is a hint according to Jakarta Persistence; providers are allowed to load earlier if needed. Declaring a nested getter on a projection and setting `LAZY` in the entity mapping are related factors, but they are not the same mechanism.

## 3. How Do Nested Interface Projections Work?

### 3.1. Declaring a Nested Projection

Create `CustomerCard.java`:

~~~java
package com.example.projection;

public interface CustomerCard {

    Long getId();

    String getFirstName();

    String getLastName();

    AddressView getAddress();

    interface AddressView {
        String getCity();
    }
}
~~~

Repository declaration:

~~~java
package com.example.projection;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<CustomerCard> findByLastName(String lastName);
}
~~~

Spring Data recognizes the return type as an interface projection. The getter `getAddress()` represents the `address` property; the return type `AddressView` allows further access to the `city` property.

Nested projections can be wrapped recursively. This helps break down the result structure by domain, but it does not guarantee that each nested getter corresponds to an independent `SELECT` column.

### 3.2. Important Limitation: Nested Property Does Not Mean Single-Column Selection

Spring Data JPA can optimize closed interface projections to select only the top-level properties required by the projection. However, when a nested property requires a JOIN to resolve the relationship path, a JPA projection may select/materialize that entire nested property.

In the example above, the projection only declares `AddressView.getCity()`, yet you should not assume the SQL only reads `addresses.city`. Accessing `address` may cause the entire `Address` relationship property to be materialized with more columns than needed, such as `id`, `street`, `city`, and `postalCode`.

Distinguish between:

- **Java shape:** the caller sees only the getters declared in the projection.
- **SQL shape:** the provider decides the JOINs, selected columns, and materialization based on the query and mapping.
- **Loading behavior:** a relationship may be loaded in the initial query or initialized later when the getter is invoked.

Do not infer the number of columns, JOINs, or SQL statements solely from the number of getters in the interface. Inspect the actual SQL.

## 4. Why Can Nested Projections Load More Data Than Expected?

### 4.1. JOINs Can Materialize the Entire Related Property

When a projection accesses `customer.address.city`, Spring Data must resolve the path across the `address` relationship. In JPA, a nested property resolving to a join can cause the entire nested property to be materialized. Thus, a nested getter is not equivalent to a simple column selection.

If `Address` has many columns or other relationships, the SQL may read more data than the screen needs.

### 4.2. Lazy Loading Can Emit SELECTs When Getters Are Called

If the association is still represented by a proxy or lazy object, calling `getAddress()` or an inner property getter may trigger state loading. When iterating over many customers, the number of loads can grow with the number of rows.

Not every nested projection causes N+1 queries. A query might JOIN and fetch the relationship in the same SQL statement. N+1 happens when the provider must load each association separately, such as when a projection relies on an entity/proxy and the caller accesses a lazy relationship row by row. Inspect the logs rather than concluding based on the projection name alone.

### 4.3. Serializing Projections Can Trigger Unexpected Getters

A JSON serializer can invoke getters to build the response. If the response contains a nested projection, the serializer might access deeper fields than the business code explicitly read.

Example controller returning the projection directly:

~~~java
@GetMapping("/customers")
public List<CustomerCard> findCustomers(
        @RequestParam String lastName) {
    return customers.findByLastName(lastName);
}
~~~

Depending on the projection structure and serializer, building JSON may access `address`, then `city`, initializing the lazy relationship during serialization. In that case, SQL is emitted outside the point where someone reading the repository code would easily notice it.

If you need a stable API, explicitly choose the DTO shape, query, and fetched data before returning the response.

## 5. Nested Projections with ToMany Relationships Carry Extra Risks

Nested projections are not limited to ToOne relationships. A projection can declare a nested collection:

~~~java
public interface CustomerWithOrders {
    Long getId();
    String getFirstName();
    List<OrderView> getOrders();

    interface OrderView {
        Long getId();
        String getOrderNumber();
    }
}
~~~

If a customer has many orders, a JOIN can produce multiple SQL rows for the same customer. For example, a customer with 5 orders can appear in 5 joined result rows before the provider/projection processes the results.

Potential consequences:

- Increased intermediate rows and data volume transferred from the database.
- Duplication of root entity data across joined rows.
- Difficulty paginating accurately at the customer level.
- Loading a large collection even if the screen only needs a few orders.
- Firing extra queries when lazy collections are initialized per customer.

Do not assume `Page<CustomerWithOrders>` always paginates accurately and efficiently if the query must materialize a collection. SQL pagination happens on joined rows, which may not correspond to unique customers.

For ToMany relationships, consider fetching the page of customers first, then loading child data for the page's ID set in a separate query, or using a carefully designed DTO query. If the method takes `Pageable`, inspect both the content query and how total customers are counted.

## 6. Solution 1: Flat Interface Projection with Explicit JOIN

If the screen only needs the city name, you can create a flat projection:

~~~java
package com.example.projection;

public interface CustomerCardFlat {
    Long getId();
    String getFirstName();
    String getLastName();
    String getCity();
}
~~~

This is a flat interface projection: fields from `customer` and `address` sit at the same level in the result. The repository writes a query selecting only the required fields:

~~~java
@Query("""
       select c.id as id,
              c.firstName as firstName,
              c.lastName as lastName,
              a.city as city
       from Customer c
       left join c.address a
       where c.lastName = :lastName
       order by c.id
       """)
List<CustomerCardFlat> findFlatCardsByLastName(
        @Param("lastName") String lastName);
~~~

Here:

- `LEFT JOIN` retains customers without an address.
- Only the expressions `c.id`, `c.firstName`, `c.lastName`, and `a.city` appear in `SELECT`.
- Aliases match the getter names of the interface projection.
- The result is a flat projection without accessing a nested association.
- `ORDER BY c.id` ensures a deterministic order.

This is a good option when you want explicit control over selected columns while still using an interface projection. Verify the aliases and result types with your active provider.

## 7. Solution 2: DTO Constructor Expression

If you want an immutable result type and an explicit constructor, use a DTO:

~~~java
package com.example.projection;

public record CustomerCardDto(
        Long id,
        String firstName,
        String lastName,
        String city) {
}
~~~

JPQL constructor expression:

~~~java
@Query("""
       select new com.example.projection.CustomerCardDto(
           c.id,
           c.firstName,
           c.lastName,
           a.city
       )
       from Customer c
       left join c.address a
       where c.lastName = :lastName
       order by c.id
       """)
List<CustomerCardDto> findDtoCardsByLastName(
        @Param("lastName") String lastName);
~~~

The query selects only the expressions passed into the constructor. `CustomerCardDto` is a DTO, not a managed entity; mutating a record or DTO object does not automatically update the database.

Advantages:

- `SELECT` explicitly lists the fields to read.
- Does not return nested proxies for a serializer to access later.
- Constructor and data types are checked when the query runs.
- Easy to use for API responses, reports, and read-only use cases.

Note: the class name in `SELECT NEW` must be the fully qualified class name. Argument order and types must match the constructor. `a.city` can be null because of `LEFT JOIN`, so the `city` field must allow null.

## 8. Solution 3: Closed Projections and Default Methods

A closed projection declares only properties that map directly to properties of the target entity:

~~~java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

Spring Data knows the properties the projection needs. The default method only combines declared getters, preserving closed projection optimization where supported.

If using an open projection with SpEL:

~~~java
public interface CustomerOpenView {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
~~~

This is an open projection because the expression can access the target entity. Spring Data cannot infer with certainty which attributes are needed to compute the result; therefore, it cannot optimize the query in the same way as a closed projection.

Practical guidelines:

- Prefer closed projections if only entity properties are needed.
- Use default methods to combine values from declared getters.
- Only use `@Value`/SpEL when expression logic is truly needed.
- If a result needs a JOIN and only a few nested fields, a flat projection or DTO is usually easier to control than a nested projection.

## 9. Solution 4: EntityGraph When You Actually Need the Entity Graph

If the use case needs the `Customer` entity along with `Address` to run logic inside a transaction, you can use `EntityGraph`:

~~~java
@EntityGraph(attributePaths = "address")
List<Customer> findWithAddressByLastName(String lastName);
~~~

`EntityGraph` instructs the provider to load the `address` relationship according to the fetch plan. It is useful when the caller genuinely needs the entity and association.

However, `EntityGraph` is not a tool for selecting only a couple of columns from a nested entity. When loading `Address` as part of an entity graph, the provider typically has to materialize the `Address` entity according to its mapping. If the goal is only to read `city`, a flat projection or DTO is a better fit.

Do not switch every relationship to `EAGER` to avoid nested lazy loading. Decide the fetch plan per use case.

## 10. Optional and Nullable Relationships

If a customer does not have an address yet, `getAddress()` may return null. The caller must handle it:

~~~java
CustomerCard.AddressView address = card.getAddress();

String city = address == null
        ? "Not provided"
        : address.getCity();
~~~

Spring Data projections also support wrappers such as `Optional` for nullable properties:

~~~java
public interface CustomerOptionalView {
    Long getId();
    Optional<AddressView> getAddress();

    interface AddressView {
        String getCity();
    }
}
~~~

Wrapper types clearly express that data may be absent. However, wrappers do not change the underlying fetch plan: when accessing a nested property, the provider still has to supply data according to the mapping/query.

If using a DTO constructor expression with `LEFT JOIN`, reference types like `String` or `Long` can receive null. Do not use primitives for nullable arguments.

## 11. Testing to Detect Unexpected Loading

A projection test should verify both the returned content and the executed SQL. Simply asserting that `city` is correct is not enough to know whether the query also loaded `street`, `postalCode`, or triggered N+1 queries.

### 11.1. Testing Flat Projection Results

Example with `@DataJpaTest`:

~~~java
@DataJpaTest
class CustomerProjectionTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private CustomerRepository customers;

    @Test
    void flatProjectionReturnsOnlyTheRequiredView() {
        Address address = new Address(
                "12 Nguyen Trai",
                "Ho Chi Minh City",
                "700000"
        );
        entityManager.persist(address);

        Customer customer = new Customer(
                "An",
                "Nguyen",
                "an@example.com",
                address
        );
        entityManager.persist(customer);

        entityManager.flush();
        entityManager.clear();

        List<CustomerCardFlat> result =
                customers.findFlatCardsByLastName("Nguyen");

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getFirstName()).isEqualTo("An");
        assertThat(result.get(0).getCity())
                .isEqualTo("Ho Chi Minh City");
    }
}
~~~

The example assumes the repository has the `findFlatCardsByLastName` method and entity constructors as defined above. `flush()` writes setup data to the database; `clear()` clears the persistence context so the query actually executes and does not rely on managed entity instances.

### 11.2. Comparing Nested and Flat Projections via SQL Logs

In the test profile, you can enable:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
spring.jpa.properties.hibernate.generate_statistics=true
~~~

With Hibernate 6, the `org.hibernate.orm.jdbc.bind` logger lets you observe bound parameter values. Only enable bind logging in development/test environments because logs may contain sensitive data.

Run two separate invocations:

1. Invoke the nested projection and access `getAddress().getCity()`.
2. Invoke the flat projection and read `getCity()`.
3. Compare the number of `SELECT` statements, selected columns, JOINs, and returned rows.
4. Increase the number of customers in the fixture to see whether query count grows per customer.
5. Repeat with a customer without an address and an address with many columns.

Do not expect SQL to be identical between Hibernate and EclipseLink. Verify behavior on the specific provider/version your application supports. If you need to assert query counts, use Hibernate Statistics or an SQL collector in integration tests; query count assertions should be tied to a specific provider and configuration rather than treated as a portable JPA contract.

### 11.3. Testing ToMany and Pagination

For nested collection projections, create a fixture containing:

- A customer with no orders.
- A customer with one order.
- A customer with multiple orders.
- Multiple customers matching the search criteria.

Verify:

- The number of unique customers returned.
- The number of orders per customer.
- Which customers appear on the first and next pages.
- No customer is duplicated or missing due to JOINs.
- Query count does not grow unexpectedly linearly with the number of customers.

If paginating a collection projection does not yield stable results, switch to paginating customers first and then fetching orders for the page's list of IDs.

## 12. How to Identify and Handle N+1

N+1 is the situation where one query loads a list of root entities, and then an additional query is fired for each accessed association.

Conceptual example:

~~~text
SELECT customers ...
SELECT addresses WHERE id = ?   -- customer 1
SELECT addresses WHERE id = ?   -- customer 2
SELECT addresses WHERE id = ?   -- customer 3
...
~~~

Ways to handle it:

1. **Flat projection:** directly select `address.city` using a JOIN and alias.
2. **DTO constructor expression:** explicitly select only the needed columns in JPQL.
3. **EntityGraph:** use when the full entity graph is needed inside a transaction.
4. **Batch fetching:** if many proxies/collections must be initialized, consider provider-level batch fetching.
5. **Split queries for ToMany:** paginate root entities first, then load child data for the batch of IDs.
6. **DTO responses:** prevent serializers from initializing lazy associations.

Do not switch all mappings to `EAGER` to fix N+1. `EAGER` can cause other queries to over-fetch data and still issue multiple extra `SELECT` statements.

## 13. Choosing a Projection Type by Use Case

| Need | Suitable choice | Reason |
|---|---|---|
| Read only a few fields of the root entity | Closed interface projection | Concise declaration and can optimize top-level columns |
| Need a property computed from other getters | Closed projection with default method | Avoids unnecessary SpEL |
| Need a few fields from a nested association | Flat interface projection | Explicit `SELECT` and aliases |
| Need an immutable DTO for APIs/reports | JPQL constructor expression | Controls fields and constructor types |
| Need entity with relationship for business logic | Entity result combined with `EntityGraph`/fetch join | Entity is managed in the persistence context |
| Need large collection child data | Separate query by page IDs or DTO query | Avoids row multiplication and broken pagination |
| Need complex custom expressions | Open projection when justified, or DTO/service mapping | Accepts query optimization limitations |

There is no single best projection type for every situation. Choose based on the number of fields to return, relationship structure, collection sizes, `Pageable` pagination needs, and how responses are serialized.

## 14. Common Pitfalls

| Symptom | Cause | How to fix |
|---|---|---|
| Projection only has `getCity()`, yet SQL fetches many `Address` columns | Nested property resolving to join can materialize the entire nested property | Use a flat projection or DTO query |
| Nested getter fires SQL | Association is lazy-loaded on access | Inspect SQL, fetch data in the query, or use a DTO |
| `SELECT` count grows with customer count | N+1 from separate association initialization | Explicit JOIN, flat projection, or batch fetching |
| Page has duplicate or missing customers | Collection JOIN multiplies rows before pagination | Paginate root IDs first, then load collections separately |
| JSON response fires SQL outside service | Serializer accesses nested getters | Return materialized DTOs |
| Closed projection loses optimization | SpEL accesses `target` arbitrarily | Use getters and default methods |
| `NullPointerException` on `address` | Optional relationship without null check | Use a null check or `Optional` wrapper |
| `EntityGraph` still loads many columns | `EntityGraph` controls association fetching, not column projection | Use a DTO/flat projection if only a few fields are needed |
| Results differ across providers | Proxy, query, and mapping mechanisms are provider-dependent | Test on the exact supported provider/version |

## 15. Checklist Before Using Nested Projections

- [ ] Identify exactly which fields the caller needs on the root entity and nested associations.
- [ ] Check whether the relationship is ToOne or ToMany.
- [ ] Do not assume a nested interface selects only the declared getters.
- [ ] Inspect SQL to see which columns a nested join materializes.
- [ ] Check whether getters initialize lazy associations.
- [ ] Measure `SELECT` counts as the number of root entities increases.
- [ ] Use a flat projection or DTO when exact association column selection is required.
- [ ] Do not use `EntityGraph` expecting to fetch only a single field of a nested entity.
- [ ] Test null associations and empty collections.
- [ ] Test `Pageable` pagination with collection projections.
- [ ] Avoid returning entities/proxies or complex nested projections directly if a serializer can trigger lazy loading.
- [ ] Run integration tests on the real provider and database.

## 16. References

- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html) — closed/open projections, nested projections, interface and class-based projections.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — declaring queries and projections in repositories.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — entity relationships, fetch types, and query semantics.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/6.2/userguide/html_single/) — lazy loading, proxies, fetching, and batch fetching.

Nested projections are useful for organizing results around domain structure, but a concise interface does not guarantee concise SQL. In JPA, a nested property requiring a JOIN may materialize the entire related property; collections can also multiply rows and make pagination inaccurate. When you only need a few fields from a nested association, a flat projection or DTO query usually offers clearer control over `SELECT`. Always verify with SQL logs and integration tests on the real provider.
