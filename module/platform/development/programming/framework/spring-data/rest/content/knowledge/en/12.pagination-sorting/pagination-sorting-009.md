# Sorting Nested Properties and Limitations with Link-Represented Associations

## 1. Objectives

Spring Data REST supports paginating and sorting collection resources via request parameters. With simple data, clients can sort by direct properties such as name or createdAt. With models containing associations, clients may need to sort by a property of a related entity, such as the city of an address linked to a person.

One important distinction is between an **association link in HAL** and a **property path used for sorting**:

- An association link is a hypermedia relation in the response, having a rel and an href so clients can access the related resource.
- A property path is an attribute path in the persistent entity model that Spring Data uses to construct a Sort.

If an association is represented by a link, that does not mean the client should sort by the link's href or URL. The client sends a property path that the repository understands; the server executes the query and returns the sorted collection.

This lesson covers how to sort nested properties, how to handle single-valued and collection associations, how to cap page sizes, and key considerations for performance and security.

## 2. Illustrative Data Model

Suppose an application manages Person and Address:

    @Entity
    public class Person {

        @Id
        @GeneratedValue
        private Long id;

        private String firstName;
        private String lastName;

        @ManyToOne
        private Address address;
    }

    @Entity
    public class Address {

        @Id
        @GeneratedValue
        private Long id;

        private String city;
        private String postalCode;
    }

Repository:

    public interface PersonRepository
            extends JpaRepository<Person, Long> {
    }

A Person can be linked to an Address. When Spring Data REST returns a Person resource, the association may be represented as a link rather than embedding the full Address:

    {
      "firstName": "An",
      "lastName": "Nguyen",
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "address": {
          "href": "http://localhost:8080/people/42/address"
        }
      }
    }

The client follows the address link if it wants to read the Address. However, when sorting the Person collection by city, the property path must reflect the entity model: address.city. The rel name address and the link's href are not Sort values.

## 3. Sort Syntax in Spring Data REST

Spring Data REST uses the sort query parameter with the format:

    sort=property,direction

Where:

- property is the name of the persistent property to sort by.
- direction is asc or desc.
- asc means ascending; desc means descending.

Example sorting Person by last name ascending:

    GET /people?sort=lastName,asc

Sorting by creation time descending:

    GET /people?sort=createdAt,desc

If direction is omitted, Spring Data usually uses ascending order. To make requests clear and avoid relying on defaults, specify asc or desc explicitly.

Do not confuse sort with a link relation name. Sort takes a domain model property path, not an association URL.

## 4. Sorting by Nested Properties of a Single-Valued Association

For single-valued associations such as ManyToOne or OneToOne, nested property paths can be expressed with dot notation. In the model above, Person has the property address and Address has the property city. Example request:

    GET /people?sort=address.city,asc

This instructs Spring Data to sort Person by the city value of the associated Address.

It can be combined with pagination:

    GET /people?sort=address.city,asc&page=0&size=20

Another example, sorting by postal code descending:

    GET /people?sort=address.postalCode,desc&page=0&size=20

The path must match the property name in the persistent model. If the Java property is billingAddress while the HAL rel is customized to billing, the property path is still billingAddress.city. Do not use the rel billing.city simply because that key appears in _links.

Nested property sorting capability also depends on the store module, mappings, and how the repository builds queries. With JPA, the query may need to join the association. Test against the real repository and inspect the generated SQL or execution plan if the collection is large.

## 5. Link-Represented Associations: rel/href Differ from Property Paths

HAL example with an association:

    {
      "firstName": "An",
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "homeAddress": {
          "href": "http://localhost:8080/people/42/address"
        }
      }
    }

Suppose the Java association on the entity is still named address, while the relation in HAL is customized to homeAddress. When sorting by city, the property path can still be:

    GET /people?sort=address.city,asc

Not:

    GET /people?sort=homeAddress.city,asc

and also not sorting by the URL in href.

Reason: the HAL rel is for clients to discover links; Sort is for the server to access properties in the repository model. The two names may match by default, but they can differ when using @RestResource(rel = ...).

The workflow should be:

1. Use HAL links to discover and call the association resource when you need to read the related entity.
2. Rely on the domain model / API contract to know which persistent properties are allowed for sorting.
3. Send that property path in the sort parameter.
4. Let the server build the query and return the collection in the requested order.

The client does not need to GET every Address and sort all Person records on the client side. Doing so wastes requests, increases data transfer, and can only sort the current page rather than the entire result set.

## 6. Multiple Sort Criteria and Stable Ordering

You can pass multiple sort parameters to sort by multiple criteria. For example, sorting by last name ascending, then first name ascending:

    GET /people?sort=lastName,asc&sort=firstName,asc

With a nested property:

    GET /people?sort=address.city,asc&sort=lastName,asc

The order of sort parameters indicates priority: the first criterion is applied first; subsequent criteria break ties among records with equal values in preceding criteria.

When combining with pagination, add a unique key as the final criterion so the order is stable:

    GET /people?sort=lastName,asc&sort=id,asc&page=0&size=20

If multiple Person records share the same lastName without a tie-breaker, the order among those records may change between queries. This can cause users to see duplicate or skipped items when moving across pages, especially when data is updated concurrently.

The tie-breaker key should be a unique, stable property that the repository supports sorting on.

## 7. Limiting the Number of Returned Records

Common pagination parameters:

- page: page index, starting from 0 by default.
- size: number of items requested on a page.
- sort: sorting criteria.

Example:

    GET /people?page=0&size=20&sort=lastName,asc

This request asks for the first page, at most 20 items, sorted by lastName ascending.

Clients should not request an excessively large size to load all data in one request. Smaller pages limit memory usage, processing time, network transfer, and database load. For large datasets, follow the pagination links returned by the server.

## 8. Configuring Default Page Size and Max Page Size

You can configure the default page size and maximum limit using RepositoryRestConfigurer:

    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
    import org.springframework.web.servlet.config.annotation.CorsRegistry;

    @Configuration
    public class RepositoryRestConfig
            implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.setDefaultPageSize(20);
            config.setMaxPageSize(100);
        }
    }

In this example:

- default page size is 20 if the client does not pass size.
- max page size is 100, capping the size a client can request.

Pagination and sorting parameter names can also be customized via RepositoryRestConfiguration, such as the page parameter, limit/size parameter, and sort parameter. If renamed, clients must use the configured names and rely on the API contract of the environment being called.

Configuring default page size does not replace the maximum limit. If you only set a default size, a client can still send a larger size unless the server has a suitable max page size.

## 9. When Does Sorting Across a Collection Association Become Ambiguous?

A nested property via a single-valued association like address.city usually has one value per Person and can produce a clear ordering.

Conversely, a collection association such as Person having many Orders does not have a single orders.createdAt value to sort Person by. A Person may have many order creation dates. The server needs to know whether to use the earliest date, the latest date, the newest order, or another rule.

Do not assume that:

    GET /people?sort=orders.createdAt,desc

will have a consistent meaning across every repository or database. Sorting across a collection-valued association may be unsupported, produce complex joins, duplicate result rows, or make pagination inaccurate if the query is not properly designed.

If business logic needs to sort Person by the most recent Order creation date, define the rule explicitly in the repository, such as a query using MAX(createdAt) aggregation, a subquery, or an appropriate projection. That way the sort result has one deterministic value per Person.

Illustrative JPQL idea:

    @Query("""
        select p
        from Person p
        left join p.orders o
        group by p
        order by max(o.createdAt) desc
        """)
    List<Person> findPeopleByLatestOrderDate();

This illustrates the query concept; the actual query must be adapted to your entity mapping, database, and return type. If pagination is needed, ensure the count query and results are not duplicated by joins.

## 10. Using @Query and Pageable When Explicit Rules Are Needed

When sorting by complex associations or restricting the set of allowed sort properties, you can define a query method in the repository:

    public interface PersonRepository
            extends JpaRepository<Person, Long> {

        @Query("""
            select p
            from Person p
            left join p.address a
            where a.city = :city
            """)
        Page<Person> findByAddressCity(
            @Param("city") String city,
            Pageable pageable
        );
    }

The client passes Pageable through the corresponding query parameters. The repository handles the business condition and Spring Data applies pagination/sorting according to what the query supports.

For complex queries, verify how the framework applies dynamic Sort. Some queries have aliases or expressions that prevent ordinary property sorts from applying as expected. When a fixed order is needed, define ORDER BY in the query; when letting clients choose the order, only allow cases the query explicitly supports.

Do not arbitrarily expose every entity property as a sort criterion if doing so could leak data or create expensive queries. You can build dedicated endpoints or repository methods with an explicit allowlist of sort fields.

## 11. Following Pagination Links Instead of Building URLs Manually

Spring Data REST collection responses usually include links like self, first, prev, next, and last when appropriate. Illustrative example:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/people?page=0&size=20&sort=lastName,asc"
        },
        "next": {
          "href": "http://localhost:8080/people?page=1&size=20&sort=lastName,asc"
        }
      },
      "page": {
        "size": 20,
        "totalElements": 45,
        "totalPages": 3,
        "number": 0
      }
    }

Clients should follow the href of next to fetch the next page. The server preserves sort criteria and page size in the published link. Do not build URLs manually by incrementing the page number when the API already provides navigation links.

JavaScript example:

    const nextHref = collection._links?.next?.href;

    if (nextHref) {
      const nextUrl = new URL(nextHref, collectionResponse.url);
      const nextResponse = await fetch(nextUrl, {
        headers: { Accept: "application/hal+json" }
      });

      if (!nextResponse.ok) {
        throw new Error("Unable to load the next page");
      }

      const nextPage = await nextResponse.json();
    }

If there is no next link, treat the response as not advertising a next page. Do not infer that more data exists solely from the item count on the current page.

## 12. Performance, Security, and Correctness

**Sorting nested properties may require a JOIN**

When sorting by address.city, the database may have to join the Address table. Check indexes on filtered and sorted columns, and inspect the execution plan if the dataset is large.

**Not every property should be publicly sortable**

Sorting by sensitive fields can indirectly leak information through the order of results. Only expose fields appropriate for the API and the caller's permissions.

**Collection associations can cause expensive queries**

Sorting by a property of a multi-valued relationship requires an explicit aggregation rule. Avoid letting clients send arbitrary property paths that cause large or hard-to-control queries.

**Pagination needs stable ordering**

Add a unique key as the final criterion to reduce items shifting positions between pages when sort values tie.

**Data changing during page traversal**

Offset pagination can produce duplicate or missing items if data is inserted or deleted between requests. A tie-breaker makes ordering more deterministic, though it does not create a consistent snapshot. If the business case requires traversing large datasets under continuous updates, consider cursor/keyset pagination in a dedicated endpoint.

## 13. Hands-On Exercise

Given Person with firstName, lastName, and an Address association with city, postalCode:

1. Call the collection endpoint with page=0 and size=10.
2. Sort by lastName ascending.
3. Add firstName and id criteria for a stable order.
4. Try sorting by address.city and observe the result.
5. Inspect the Person HAL response; identify the address link and distinguish that link from the property path address.city.
6. Customize the association rel to homeAddress, then verify that the property path used for sorting is still based on the persistent property name.
7. Set default page size to 20 and max page size to 100; try a request with a size exceeding the limit and observe actual behavior.
8. Try sorting by a collection association like orders.createdAt; identify why an explicit business rule is needed rather than assuming a single value.
9. Follow the next link to move to the next page and confirm the server preserves sort and size.

Self-check questions:

- Does sort=address.city,asc refer to a rel, an href, or a property path?
- Why does customizing the rel in HAL not necessarily change the property name used in Sort?
- Why is sorting by a single-valued association more deterministic than sorting by a collection association?
- Why should id be added as the final sort criterion when paginating?
- Which two different problems do defaultPageSize and maxPageSize solve?

## 14. Key Takeaways

- Spring Data REST accepts sort by property paths of the persistent model.
- Nested properties through single-valued associations can be expressed with dot notation, e.g., address.city.
- HAL rel/href are for discovering associations; they are not Sort property paths.
- Multiple sort parameters can be passed to specify priority order.
- Add a unique key as a tie-breaker for more stable pagination.
- Use page and size for pagination; configure default page size and max page size on the server.
- Sorting across collection associations requires explicit aggregation rules.
- Restrict allowed sort fields and follow server-provided pagination links.

## References

- Spring Data REST Reference — Paging and sorting: https://docs.spring.io/spring-data/rest/reference/
- Spring Data Commons Reference — Paging and sorting: https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html
- Spring Data JPA Reference — Query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html