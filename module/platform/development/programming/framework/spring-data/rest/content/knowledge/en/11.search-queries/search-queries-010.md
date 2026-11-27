# Limits of Automatic Filtering from Query Parameters and Choosing Explicit Queries

Spring Data REST provides two common ways to filter data when reading a collection resource:

1. **Dynamic property filtering with Querydsl**: the client passes property names and values in the query string; Spring Data REST converts those parameters into a predicate if the repository supports Querydsl.
2. **Choosing explicit queries through the search resource**: the repository declares individual query methods; the client calls the advertised method and supplies the parameters that the method accepts.

These two approaches solve different needs. Dynamic filtering fits simple conditions on permitted properties. Explicit query methods fit when business logic needs a named query with a stable set of conditions and contract. Do not assume that any arbitrary query parameter automatically becomes a filter condition.

## 1. Default query parameters of a collection resource

A Spring Data REST collection resource is typically accessed via:

~~~http
GET /products
Accept: application/hal+json
~~~

If the repository supports pagination, the collection resource accepts standard parameters:

| Parameter | Meaning |
|---|---|
| **`page`** | Page number, zero-based |
| **`size`** | Number of items in a page |
| **`sort`** | Property and sort direction, for example **`name,asc`** |

Example:

~~~http
GET /products?page=0&size=10&sort=name,asc
~~~

These parameters control pagination and sorting. They do not automatically filter on every property of the entity. Sending **`?status=ACTIVE`** to a collection resource whose repository has not enabled a matching filtering mechanism should not be expected to cause Spring Data REST to automatically infer **`status = ACTIVE`**.

To filter a collection using properties in the query string, the repository can integrate Querydsl.

## 2. Dynamic property filtering with Querydsl

Querydsl allows Spring Data REST to construct a predicate from query parameters and apply that predicate when reading a collection resource.

The repository must implement **`QuerydslPredicateExecutor<T>`**. For example:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                QuerydslPredicateExecutor<Product> {
}
~~~

You must add the Querydsl dependency compatible with the Spring Data version in use and configure annotation processing to generate Q-classes, such as **`QProduct`**. Dependency names and configurations may vary by Querydsl version and persistence module.

Once integrated, clients can filter directly on the collection:

~~~http
GET /products?name=Keyboard&status=ACTIVE
~~~

Property conditions are combined into a predicate. Conceptually, the example above corresponds to:

~~~text
name = "Keyboard" AND status = "ACTIVE"
~~~

Filtering can be combined with pagination and sorting:

~~~http
GET /products?status=ACTIVE&category=OFFICE&page=0&size=10&sort=name,asc
~~~

For nested properties, property paths can be used according to the syntax supported by the binder, for example:

~~~http
GET /stores?address.city=York
~~~

Querydsl is a type-safe predicate-building mechanism, not a parser for an arbitrary SQL query language sent by clients.

## 3. Default binding rules and limitations

The Querydsl binder has common default rules:

| Property kind | Default binding behavior |
|---|---|
| Simple property | Equality comparison (**`eq`**) |
| Collection property | Membership check (**`contains`**) |
| Multiple values for a simple property | Set membership comparison (**`in`**) |

Example query string with two simple properties:

~~~http
GET /users?firstname=Dave&lastname=Matthews
~~~

The generated predicate takes the form:

~~~text
firstname = "Dave" AND lastname = "Matthews"
~~~

Several limitations must be understood:

- Values must be convertible to the corresponding Java types. Malformed dates, numbers, enums, or IDs can cause the request to be rejected.
- Parameter names are tied to property paths permitted by the binder; they are not arbitrary parameter names for an SQL statement.
- Default query parameter conditions do not provide full syntax for all comparison operators, nested OR expressions, condition grouping, aggregations, or complex business queries.
- Filtering on associations or nested properties depends on binder capabilities, the domain model, and the persistence module.
- Do not expose every property just because Querydsl can build predicates for them. Internal or sensitive properties should be excluded from binding.
- Dynamic filtering does not replace authorization. Clients must never be allowed to decide their own tenant scope, ownership, or which data a user is authorized to view.

If specialized comparisons or search rules beyond the defaults are needed, customize the binding or switch to explicitly declared queries.

## 4. Customizing Querydsl binding

You can implement **`QuerydslBinderCustomizer`** on the repository to change how query parameters are turned into predicates.

For example, search product names by case-insensitive substring match while preventing clients from filtering on an internal code:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                QuerydslPredicateExecutor<Product>,
                QuerydslBinderCustomizer<QProduct> {

    @Override
    default void customize(QuerydslBindings bindings, QProduct product) {
        bindings.bind(product.name)
                .first((path, value) -> path.containsIgnoreCase(value));

        bindings.excluding(product.internalCode);
    }
}
~~~

In this example:

- **`name`** uses case-insensitive substring matching.
- **`internalCode`** cannot be used as a query parameter to create a predicate.
- Other bindings continue using default rules unless customized.

Additional bindings can be customized per property or per data type. Prefer allow-listing the fields actually needed for searching when the API has security or query-restriction requirements.

Excluding a property from Querydsl binding only stops clients from using that property as a filter condition through this mechanism. It does not replace security configuration for the returned data.

## 5. Choosing explicit queries via the search resource

When you do not want clients choosing property paths themselves, the repository can define dedicated query methods. Spring Data REST exposes eligible methods under the **`search`** resource.

For example:

~~~java
import java.util.List;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends CrudRepository<Person, Long> {

    List<Person> findByLastname(@Param("name") String lastname);
}
~~~

Spring Data REST creates the search resource at:

~~~http
GET /people/search
Accept: application/hal+json
~~~

The search resource returns links to the exposed query methods. The method above can be invoked with:

~~~http
GET /people/search/findByLastname?name=Baggins
~~~

The query parameter name **`name`** comes from **`@Param("name")`**. The path and rel of the query method can be customized with **`@RestResource`**:

~~~java
@RestResource(path = "by-lastname", rel = "by-lastname")
List<Person> findByLastname(@Param("name") String lastname);
~~~

Then the client calls:

~~~http
GET /people/search/by-lastname?name=Baggins
~~~

Use the links returned from **`/people/search`** to discover endpoints instead of making clients guess method names or URLs.

## 6. Using @Query when explicit business conditions are needed

Derived method names fit simple conditions such as **`findByStatus`**, **`findByLastnameAndActiveTrue`**, or **`findByPriceGreaterThan`**. When a method name gets too long or conditions are hard to express via naming conventions, JPQL can be declared with **`@Query`**.

For example, finding only active people in a city who meet a minimum age:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RestResource;

public interface PersonRepository extends JpaRepository<Person, Long> {

    @Query("select p from Person p " +
           "where p.active = true " +
           "and p.city = :city " +
           "and p.age >= :minAge")
    @RestResource(path = "active-by-city")
    Page<Person> findActiveByCityAndMinimumAge(
            @Param("city") String city,
            @Param("minAge") int minAge,
            Pageable pageable);
}
~~~

The client invokes the chosen query method:

~~~http
GET /people/search/active-by-city?city=Da%20Nang&minAge=18&page=0&size=20
~~~

The query conditions are defined by the repository. The client only passes values for the declared parameters. With a **`Page`** return type and **`Pageable`** parameter, the response can contain pagination metadata and links.

Query method resources are read-only resources invoked with GET. If an internal query method should not be exposed as an API endpoint, **`@RestResource(exported = false)`** can be placed on that method.

## 7. Choosing between dynamic filtering and explicit queries

| Need | Suitable approach |
|---|---|
| Filtering a collection by a few simple properties | Querydsl property binding |
| Allowing combinations of multiple independent filters | Querydsl with controlled bindings |
| Searching by a clearly named business rule | Explicit query method |
| Using joins, complex conditions, or expressions | **`@Query`** or custom query |
| Restricting clients to choosing from a predefined set of queries | Search resource |
| Needing dynamic logic beyond binder capabilities | Custom controller/service using Specification, Criteria, or Querydsl |

Dynamic filtering reduces the number of methods to declare, but the query scope depends on the exposed property paths and bindings. Explicit query methods require declaring more methods, in return giving each endpoint a concrete contract that is easier to document and control.

Both approaches can coexist on a single repository. For instance, the collection resource supports dynamic filtering for safe fields while **`/people/search`** advertises key business queries.

## 8. When should you build a dedicated search endpoint?

Consider a custom controller or service if the query requires:

- Combining multiple parenthesized AND/OR condition groups with complex precedence.
- Optional conditions with null rules, value ranges, or multiple comparison operators.
- Joining multiple aggregates, statistical queries, aggregations, or results that do not map directly to an entity.
- Strict control over allowed filter fields by role, tenant, or data policy.
- A stable search contract decoupled from entity structure and property names.

In a custom Spring MVC controller, **`@QuerydslPredicate`** can convert query parameters into a Querydsl Predicate and execute it via **`QuerydslPredicateExecutor`**. This is web support integration for controllers; it must be declared on the controller parameter and does not mean every controller or every query parameter is automatically filtered.

## 9. Verifying search endpoints

After configuring, verify each mechanism independently.

**Testing dynamic filtering:**

~~~http
GET /products?name=key&status=ACTIVE&page=0&size=10
Accept: application/hal+json
~~~

Confirm only products matching the configured bindings appear, and check the pagination metadata.

**Testing the search resource:**

~~~http
GET /people/search
Accept: application/hal+json
~~~

Verify the links to the exposed query methods.

**Testing a specific query method:**

~~~http
GET /people/search/active-by-city?city=Da%20Nang&minAge=18
Accept: application/hal+json
~~~

Cross-check results against the declared JPQL conditions. Test invalid values, missing parameters, and subsequent pages to understand the endpoint's actual contract.

## 10. Security and operational considerations

- Allow filtering only on necessary properties; exclude sensitive fields from binding.
- Do not treat query parameters as an authorization mechanism. Always enforce authorization and data scoping on the server.
- Limit page sizes and consider database indexes for frequently filtered or sorted fields.
- Avoid exposing filters that can trigger overly expensive queries or leak information through results.
- Verify type conversion and how the binder handles repeated values, nested properties, nulls, and empty strings.
- Use HAL to discover the search resource and URI templates advertised by the server.
- Querydsl and annotation processing configurations must be compatible with the application's Spring Data, Querydsl, and persistence provider versions.

Official references:

- [Spring Data REST — Repository resources and search resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Project features, including dynamic filtering](https://spring.io/projects/spring-data-rest/)
- [Spring Data JPA — Querydsl extension and web support](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html)
- [Spring Guide — Accessing JPA Data with REST](https://spring.io/guides/gs/accessing-data-rest)
