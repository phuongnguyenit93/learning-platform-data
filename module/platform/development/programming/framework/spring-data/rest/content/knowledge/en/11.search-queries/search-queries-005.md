# Exposing @Query Queries and Keeping Query Logic in the Repository Layer

## 1. Objectives

Spring Data REST can expose query methods of a Spring Data repository as search resources. Clients invoke the search endpoint using HTTP GET and pass the required parameters. When you want to write an explicit or complex query, you can place the query logic in the repository using the @Query annotation.

This organization keeps queries close to the data access layer:

- The repository defines the query and the result type.
- Spring Data executes the query through the repository mechanism.
- Spring Data REST exposes the query method as a search link if the method is exported.
- The client discovers the link in HAL and sends a GET request with query parameters.

This lesson uses Spring Data JPA to illustrate @Query. With other Spring Data modules, the annotation and query language may differ, but Spring Data REST still relies on repository metadata and export configuration to expose query methods.

## 2. Query methods are exposed as search resources

Suppose the application has a repository:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        List<Customer> findByCity(String city);
    }

Spring Data REST can expose the query method under the collection's search resource. The typical discovery flow:

1. GET the API root to find the collection link.
2. Follow the collection link, for example the customers rel.
3. Read the collection's search link.
4. GET the search resource to view the exposed finders.
5. Follow a finder link and supply query parameters.

Illustrative search resource example:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/search"
        },
        "findByCity": {
          "href": "http://localhost:8080/customers/search/findByCity{?city}",
          "templated": true
        }
      }
    }

In the example, findByCity is the finder's relation. templated=true indicates that href is a URI template with a city parameter.

The default path and rel names are usually derived from the method name. They can be customized with @RestResource(path = ..., rel = ...). Always inspect the actual search resource instead of assuming a URL or relation.

## 3. Placing the query in the repository with @Query

@Query allows declaring a query directly on a method. With Spring Data JPA, the default query language is JPQL.

Example entity:

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
        private String email;
        private String city;
    }

The repository defines a query to find customers by a partial name match:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        @Query("""
            select c
            from Customer c
            where lower(c.name) like lower(concat('%', :keyword, '%'))
            """)
        List<Customer> searchByName(
            @Param("keyword") String keyword
        );
    }

In this query:

- Customer is the entity name in JPQL, not necessarily the table name.
- c.name is a Java property of the entity.
- :keyword is a named parameter.
- @Param("keyword") binds the method parameter to the parameter name in the query.

JPQL operates on entities and properties, not directly on table and column names like SQL. If writing native SQL, you must explicitly specify nativeQuery = true.

The text block """ in the example requires Java 15 or newer. For older Java versions, use a single-line string or normal string concatenation.

## 4. Passing parameters with @Param

You should declare @Param explicitly when the query uses named parameters. For example:

    @Query("select c from Customer c where c.city = :city")
    List<Customer> searchByCity(
        @Param("city") String city
    );

The method parameter city is bound to :city in JPQL.

Spring Data JPA can also infer parameter names from compiled metadata in certain configurations, but @Param clarifies the contract between the method and the query, avoiding reliance on whether the compiler retains parameter names.

When called over REST, the query parameter name normally corresponds to the name declared with @Param:

    GET /customers/search/searchByCity?city=Hanoi

If the method uses @RestResource(path = "by-city"), the finder path changes to /customers/search/by-city?city=Hanoi in the example. The parameter name remains city.

Values containing spaces, &, ?, or Unicode characters must be URL-encoded. Clients should use a URL library or URI template to encode parameters rather than concatenating query strings by hand.

## 5. Customizing the rel and path of a query method

You can use @RestResource on the method to assign clearer relation and path names:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        @Query("""
            select c
            from Customer c
            where lower(c.name) like lower(concat('%', :keyword, '%'))
            """)
        @RestResource(
            path = "by-name",
            rel = "byName"
        )
        List<Customer> searchByName(
            @Param("keyword") String keyword
        );
    }

The search resource can advertise the link under the byName rel, with a template href containing the keyword parameter. Clients should read that link from the response:

    {
      "_links": {
        "byName": {
          "href": "http://localhost:8080/customers/search/by-name{?keyword}",
          "templated": true
        }
      }
    }

To call the finder, expand the URI template with the search value. The following example URL illustrates the expanded result:

    GET /customers/search/by-name?keyword=an

path controls the URL segment of the finder; rel controls the relation name in HAL. The two values serve different purposes.

## 6. Pagination for queries returning many results

If a query can return many records, you can use Page<T> and accept Pageable:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        @Query("""
            select c
            from Customer c
            where c.city = :city
            """)
        Page<Customer> searchByCity(
            @Param("city") String city,
            Pageable pageable
        );
    }

Spring Data REST supports pagination parameters for eligible query methods. Illustrative request:

    GET /customers/search/searchByCity?city=Hanoi&page=0&size=10

The collection response typically includes information in page and navigation links such as next when additional pages exist.

Do not manually increment the page number if the server already provides a next link. The client can follow that link's href to continue fetching pages.

The return type and method signature determine pagination capabilities. If List<T> is used instead of Page<T>, the client will not receive the full total-page metadata in the same way. Choose the result type suited to the API's needs.

## 7. Using native SQL only when genuinely needed

Spring Data JPA's @Query also supports native SQL via nativeQuery = true:

    @Query(
        value = "select * from customers where city = :city",
        countQuery = "select count(*) from customers where city = :city",
        nativeQuery = true
    )
    Page<Customer> searchByCityNative(
        @Param("city") String city,
        Pageable pageable
    );

In a native query, customers is the table name and city must be the column name in the actual schema. countQuery supplies the counting query so Spring Data can compute the total number of elements when returning Page.

Native SQL is useful when database-specific features are needed or when a query does not fit JPQL well. However, it couples the repository more tightly to a specific schema and dialect. Prefer JPQL when the query can be expressed clearly through the entity model.

## 8. Hiding a query method from the REST API

Not every internal query method should become a public endpoint. You can place @RestResource(exported = false) on the method:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        @Query("select c from Customer c where c.email = :email")
        @RestResource(exported = false)
        List<Customer> findInternalByEmail(
            @Param("email") String email
        );
    }

The method can still be used inside the application via the repository, but Spring Data REST will not expose that finder as a search resource.

Distinguish between:

- @RestResource(exported = false) on a method hides that query method or association.
- @RepositoryRestResource(exported = false) on a repository hides the repository resource according to the export configuration.
- @Query only defines the query; it does not replace authentication or authorization mechanisms.

Hiding one finder is not equivalent to securing the entire API. Other repository methods can still be exposed. Configure Spring Security for endpoints and sensitive data according to application requirements.

## 9. Discovering and invoking query resources from a client

Clients should discover finders via HAL rather than constructing URLs. For example, read the collection response, then follow the search link:

    const collection = await fetch(collectionUrl, {
      headers: { Accept: "application/hal+json" }
    }).then(response => response.json());

    const searchHref = collection._links?.search?.href;

    if (!searchHref) {
      throw new Error("Collection does not expose a search resource");
    }

    const searchUrl = new URL(searchHref, collectionUrl);

    const searchResponse = await fetch(searchUrl, {
      headers: { Accept: "application/hal+json" }
    });

    if (!searchResponse.ok) {
      throw new Error("Unable to read search resource");
    }

    const searchResource = await searchResponse.json();

The search resource may return:

    {
      "_links": {
        "byName": {
          "href": "http://localhost:8080/customers/search/by-name{?keyword}",
          "templated": true
        }
      }
    }

If the link is a URI template, expand the template using an appropriate URI template or hypermedia library. Example expanded URL:

    GET /customers/search/by-name?keyword=An

Clients should not construct the /customers/search/by-name path themselves when the server already provides href. Relying on rel allows the client to keep working if the server changes the path while preserving the relation in the hypermedia contract.

## 10. Testing query methods with curl

You can inspect the search resource:

    curl -i \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers/search

After reading the finder's href from the response, call the finder URL with valid parameters. For example:

    curl -i \
      -H "Accept: application/hal+json" \
      "http://localhost:8080/customers/search/by-name?keyword=An"

The URLs above illustrate the path = "by-name" configuration. When testing the real application, use the href from the search resource and encode query parameters properly.

Check the following points:

1. Does the search resource advertise the desired finder rel?
2. Does href have the right path and mark templated when it contains a URI template?
3. Does the query parameter name match @Param?
4. Do the results match the expected entities or collection?
5. If the method returns Page, does the response include appropriate pagination metadata and links?
6. Is a method marked exported = false absent from the search resource?

## 11. Common errors

**Confusing JPQL with SQL**

JPQL uses Java entities and properties; native SQL uses database tables and columns. Using the wrong names can cause the query to fail at runtime.

**Parameter name mismatch**

If the query uses :keyword but the method binds @Param("name"), Spring Data cannot bind the parameter properly. The name in @Param must match the query placeholder.

**Finder does not appear**

Check whether the method is inside an exported repository, whether it is marked exported = false, and whether Spring Data REST exposes query methods for that repository. Use the search resource to view the actual list of finders.

**Path or rel not as expected**

@RestResource(path = ..., rel = ...) can customize both values. Do not infer rel from path or vice versa; inspect _links in HAL.

**Paginated native query missing count query**

For a native query returning Page, ensure Spring Data can determine the total record count. Provide an explicit countQuery when needed, especially for complex queries.

**Exposing sensitive data**

An exported query method can become an externally callable endpoint. Do not include sensitive data in the response and do not rely on obscure URLs to protect endpoints. Use exported = false when a finder should not be public and configure appropriate authorization.

## 12. Hands-on exercise

Given a Customer entity with name, email, and city:

1. Create CustomerRepository extending JpaRepository<Customer, Long>.
2. Write a JPQL query to find customers by a partial name match using @Query.
3. Use @Param("keyword") to bind the named parameter.
4. Customize the finder path to by-name and rel to byName.
5. Start the application, follow the search link from the collection, and verify the finder is exposed.
6. Call the finder with a keyword containing spaces or special characters to test URL encoding.
7. Create another query method with @RestResource(exported = false) and confirm it does not appear in the search resource.
8. Create a finder returning Page<Customer>, pass Pageable, and follow the next link if present.

Self-check questions:

- In which layer does @Query keep query logic?
- How does JPQL differ from native SQL in referencing entities and tables?
- Which placeholder does @Param link a method argument to?
- How do path and rel differ?
- How do you hide a query method from Spring Data REST?
- Why does a query method exposed to the REST API still require authorization?

## 13. Key takeaways

- Repository query methods can be exposed by Spring Data REST under the search resource.
- @Query places the query inside the repository; JPQL is the default in Spring Data JPA.
- @Param explicitly binds named parameters between the method and the query.
- @RestResource(path, rel) customizes the finder path and relation in HAL.
- Page<T> together with Pageable supports paginated queries.
- nativeQuery = true uses database SQL; consider a count query when returning Page.
- @RestResource(exported = false) hides a query method from REST export.
- Exposing a finder does not replace authentication and authorization.

## References

- Spring Data JPA Reference — Declaring query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data REST Reference — Exposing repository resources: https://docs.spring.io/spring-data/rest/reference/
- Spring Data Commons — Query method and repository abstractions: https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html
