# The /search Resource and Discovery Mechanism for Query Methods in Spring Data REST

## Objectives

Spring Data REST can expose query methods of a Spring Data Repository as discoverable REST endpoints. For an exported repository, clients typically find query endpoints through the \`/search\` resource.

Three related layers need to be understood:

- **Search resource:** the entry point for discovering the exported queries of a repository, typically at the URI \`/people/search\`.
- **Search method resource:** an endpoint representing a specific query method, for example \`/people/search/findByLastName\`.
- **HAL link:** the relation and href advertised by the server so clients can locate the search endpoint and invoke the query without guessing URIs.

The \`/search\` resource does not automatically generate arbitrary queries against the database. It is the place that advertises the query methods that the repository has declared and Spring Data REST allows to be exported. If a repository has no exported query methods, the search resource may have no links to any methods.

This lesson covers how the search resource is created, how a method becomes an endpoint, how parameters are passed, how relation names/paths are customized, how paging and sorting are used, and how clients discover the API via HAL.

## 1. Where does the search resource live?

Suppose a repository is exported:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

With a base path of \`/api\`, the collection resource has the URI:

~~~text
/api/people
~~~

The search resource is placed under the collection resource:

~~~text
/api/people/search
~~~

When a client requests the collection:

~~~http
GET /api/people
Accept: application/hal+json
~~~

the response may contain a \`search\` link:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people"
    },
    "search": {
      "href": "http://localhost:8080/api/people/search"
    }
  }
}
~~~

The \`search\` relation indicates that the repository has a search resource for discovering query endpoints. The client follows this href to read the detailed search links.

Do not hardcode \`/search\` in the client if the API already advertises the relation. The base path, collection path, or URL configuration may change; the HAL link is the URI source advertised by the server.

## 2. Declaring a query method in a repository

Spring Data supports derived query methods based on method names. For example:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

For Spring Data REST to advertise the method as a search endpoint, the method must be a suitable query method and be exported. Typically, the query parameter name should be explicitly declared using \`@Param\`:

~~~java
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("name") String lastName);
}
~~~

With the repository above, Spring Data REST can create a search method resource under the search resource. The default URI is based on the method name, for example:

~~~text
/api/people/search/findByLastName
~~~

Clients invoke the query using a query parameter:

~~~http
GET /api/people/search/findByLastName?name=Lovelace
Accept: application/hal+json
~~~

Spring Data passes the \`name\` value to the method parameter and executes the query. If results are found, the response represents the matching Person entities; if no results are found, the search endpoint still exists and may return an empty collection representation.

### Why use @Param?

\`@Param("name")\` defines the public query parameter name of the endpoint. The Java parameter name such as \`lastName\` is not necessarily the name the client must send. Using \`@Param\` makes the HTTP contract explicit and independent of whether the compiler retains parameter name metadata.

For example:

| Method declaration | Query parameter sent by client |
|---|---|
| \`findByLastName(@Param("name") String lastName)\` | \`?name=Lovelace\` |
| \`findByAgeGreaterThan(@Param("minAge") int age)\` | \`?minAge=30\` |
| \`findByStatus(@Param("status") PersonStatus status)\` | \`?status=ACTIVE\` |

The name in \`@Param\` is part of the API contract. When renaming it, consider the impact on clients calling the endpoint.

## 3. Discovering search methods via HAL

When requesting the search resource:

~~~http
GET /api/people/search
Accept: application/hal+json
~~~

Spring Data REST may return a representation such as:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/search"
    },
    "findByLastName": {
      "href": "http://localhost:8080/api/people/search/findByLastName{?name}",
      "templated": true
    },
    "findByStatus": {
      "href": "http://localhost:8080/api/people/search/findByStatus{?status}",
      "templated": true
    }
  }
}
~~~

This is an illustrative example when a repository exports two query methods. Actual links depend on method names, annotations, and version/configuration.

Key parts:

- \`self\` points to the search resource itself.
- \`findByLastName\` is the relation for a search method.
- \`href\` is a URI template containing query parameter variables.
- \`templated: true\` indicates that the client needs to expand the template before sending the request.

The client does not need to know in advance how many methods the repository has or the URL of each method. It can inspect the list of relations in \`_links\`, choose the appropriate relation, and expand the corresponding href.

### The search resource may be empty

If the repository has no exported query methods, the search resource may not appear or may not have specific method links, depending on configuration and version. Clients should check for the \`search\` link on the collection first, then inspect the actual relations in the search response.

Do not assume every repository has \`findById\`, \`findAll\`, or an arbitrary search method under \`/search\`. Standard CRUD operations have their own resources; the search resource is for advertised query methods.

## 4. Customizing the relation name and URI of a search method

\`@RestResource\` can be used on a query method to customize its path and relation:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastName(@Param("name") String lastName);
}
~~~

With this configuration, the search method endpoint can use the path:

~~~text
/api/people/search/by-last-name?name=Lovelace
~~~

and the search representation advertises the relation:

~~~json
{
  "_links": {
    "byLastName": {
      "href": "http://localhost:8080/api/people/search/by-last-name{?name}",
      "templated": true
    }
  }
}
~~~

The two attributes have different meanings:

| Attribute | Role | Example |
|---|---|---|
| \`path\` | URI segment of the search method endpoint. | \`by-last-name\` |
| \`rel\` | Relation name in HAL used by clients to identify the link. | \`byLastName\` |

Changing \`rel\` does not necessarily change the URL. Changing \`path\` changes the endpoint URI. Hypermedia clients should read the href from the response rather than assuming the relation and path are identical.

### Hiding a query method

If a query method should not be exposed over REST, it can be annotated with:

~~~java
@RestResource(exported = false)
List<Person> findByInternalFlagTrue();
~~~

This method is not exported as a search endpoint. The corresponding relation will not be advertised in the search resource. Hiding an endpoint helps manage the API surface, but it does not replace authorization for other access paths to the data.

## 5. Passing query parameters

Parameters of a search method are passed via the query string. Spring Data REST uses the \`@Param\` name to map request parameters to method arguments.

For example:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("name") String lastName);

    List<Person> findByAgeGreaterThan(
        @Param("minAge") int age
    );

    List<Person> findByStatusAndLastName(
        @Param("status") PersonStatus status,
        @Param("name") String lastName
    );
}
~~~

The corresponding requests:

~~~http
GET /api/people/search/findByLastName?name=Lovelace
~~~

~~~http
GET /api/people/search/findByAgeGreaterThan?minAge=30
~~~

~~~http
GET /api/people/search/findByStatusAndLastName?status=ACTIVE&name=Lovelace
~~~

Spring converts query string values to the Java types of the method arguments. For example, the string \`30\` into \`int\`, or \`ACTIVE\` into the \`PersonStatus\` enum, if a corresponding converter supports it.

If a parameter is missing, malformed, or cannot be converted, the request may fail with a 400 error or a conversion error handled according to the application's exception handling.

### Required and optional parameters

How a method is declared determines how Spring Data handles arguments. If a method needs a value to execute the query, the client should send the corresponding parameter. Do not treat omitting a query parameter as an unrestricted query unless the method signature and query semantics allow it.

With multiple parameters, each \`@Param\` should have a unique name and be clearly documented in the API documentation.

## 6. Combining search with paging and sorting

A query method can return \`Page<T>\` and accept \`Pageable\`:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends JpaRepository<Person, Long> {

    Page<Person> findByLastName(
        @Param("name") String lastName,
        Pageable pageable
    );
}
~~~

Clients can call:

~~~http
GET /api/people/search/findByLastName?name=Lovelace&page=0&size=10&sort=firstName,asc
Accept: application/hal+json
~~~

Commonly used query parameters:

| Parameter | Meaning |
|---|---|
| \`page\` | Page index, usually starting from 0. |
| \`size\` | Maximum number of items per page. |
| \`sort\` | Property and sort direction, for example \`firstName,asc\`. |

When a method returns \`Page<T>\`, the response can contain a collection representation with \`_embedded\`, \`_links\`, and \`page\` metadata, including \`size\`, \`totalElements\`, \`totalPages\`, \`number\`.

If the method returns \`List<T>\`, the response can be a collection of results, though it does not necessarily include the pagination metadata of \`Page\`. Choose the return type based on client needs and query cost.

### Search with empty results

If a query is valid but finds no records, the search endpoint still exists. The response is typically an empty collection with status 200. Clients need to distinguish this case from:

- Search method not exported or wrong URL: may be 404.
- Invalid query parameter: may be 400.
- Insufficient permissions: may be 401/403 or hidden by security.
- Unsupported HTTP method: may be 405.

## 7. Search methods and Spring Data query types

Spring Data REST exports query methods recognized by Spring Data repositories that are eligible to be exposed. Query methods typically come from:

- **Derived queries:** Spring Data infers conditions from the method name, for example \`findByLastName\`, \`findByStatusAndAgeGreaterThan\`.
- **Declared queries:** methods using \`@Query\` to declare JPQL, SQL, or a store-module-specific query.
- **Named queries:** queries defined using the named query mechanism of the store module in use.

Example derived query:

~~~java
List<Person> findByStatusAndAgeGreaterThan(
    @Param("status") PersonStatus status,
    @Param("minAge") int age
);
~~~

Example declared query with JPA:

~~~java
@Query("select p from Person p where lower(p.lastName) = lower(:name)")
List<Person> searchByLastNameIgnoreCase(@Param("name") String name);
~~~

When a query method is exported, Spring Data REST can create the corresponding search endpoint. How the query is executed is handled by the Spring Data repository and store module; Spring Data REST provides the HTTP resource and representation layer.

Not every arbitrary method on the interface becomes an endpoint. The method must be recognized by Spring Data as a valid query method, permitted to be exported, and not hidden by annotations/configuration.

## 8. The search resource is not an arbitrary query API

The search resource is a set of predeclared endpoints. It does not allow clients to send arbitrary table names, column names, or SQL expressions.

For example, a client cannot simply call a hypothetical URI such as:

~~~text
/api/people/search?where=age%3E30
~~~

and expect Spring Data REST to automatically interpret a generic query, unless the application explicitly defines a query method or custom endpoint supporting that syntax.

Designing explicit query methods has benefits:

- The server controls which query conditions are allowed.
- Query parameters have explicit data types and names.
- The API is discoverable via HAL.
- Authorization and validation can be applied per use case.
- Clients do not have to send internal database query structures.

If flexible searching with multiple combined filters is needed, design a custom controller/service or an explicit search model that restricts allowed fields and operators, rather than opening an endpoint that accepts arbitrary queries.

## 9. Discovering and invoking search with curl

Fetch the collection to find the search link:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people
~~~

Fetch the list of search methods:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/search
~~~

Invoke the method searching by last name:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "name=Lovelace" \
  http://localhost:8080/api/people/search/findByLastName
~~~

Invoke the paginated method:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "name=Lovelace" \
  --data-urlencode "page=0" \
  --data-urlencode "size=10" \
  --data-urlencode "sort=firstName,asc" \
  http://localhost:8080/api/people/search/findByLastName
~~~

Using \`--data-urlencode\` helps the client encode special characters in query parameters. When writing a real client, use a URI builder instead of concatenating strings manually.

## 10. From HAL link to request: client workflow

A hypermedia client can follow this sequence:

1. Request the API entry point or collection resource.
2. Locate the \`search\` relation in \`_links\`.
3. Follow the href to open the search resource.
4. Read the relations representing query methods.
5. Select the relation matching the task.
6. Expand the URI template with the corresponding query parameters.
7. Send GET to the expanded href.
8. Read the returned collection, item, or page representation.
9. If the response contains pagination links, follow \`next\` or \`prev\` to continue navigating.

Example search representation with a link:

~~~json
{
  "_links": {
    "findByLastName": {
      "href": "http://localhost:8080/api/people/search/findByLastName{?name}",
      "templated": true
    }
  }
}
~~~

The client expands the \`name\` variable with the value \`Lovelace\` and sends the request. In Java applications, Spring HATEOAS provides abstractions to read links and expand URI templates. For other clients, use an appropriate URI template library or URI builder.

Clients should not assume query methods are always named according to the default convention. The \`@RestResource\` annotation can change the relation/path, so always use the actual relation and href.

## 11. Security and controlling query endpoints

An exported query method can allow clients to read a dataset according to the method's criteria. It is necessary to control which data is exposed:

- Do not export query methods intended only for internal use.
- Use \`@RestResource(exported = false)\` to hide methods that should not be public.
- Use Spring Security to control read permissions by URI, method, and principal.
- Check whether a query could expose sensitive data or permit overly broad scanning.
- Limit page sizes and avoid queries that cause heavy load.
- Use validation for input parameters and data types.
- Do not treat the absence of a link in HAL as a security boundary.

A GET search endpoint can still be called directly if its URI is known. The server must enforce authorization on the actual request, not merely hide the relation in the response.

## 12. Common mistakes

1. **\`search\` link not visible in the collection response.** Check whether the repository is exported, which representation is used, and whether the search resource is exposed.
2. **Search resource exists but has no method links.** Check whether the repository has eligible query methods and whether those methods have \`exported = false\`.
3. **Calling the method name returns 404.** Check for custom relation/path via \`@RestResource\`; the default method name may no longer be the actual URL.
4. **Sending the wrong query parameter name.** Use the name in \`@Param\`, do not guess from the Java variable name.
5. **Unable to convert enum or number.** Check parameter type, query string value, and converters.
6. **Using a URI template incorrectly.** If a link has \`templated: true\`, expand the variables before sending the request.
7. **Confusing a query with no results with a non-existent endpoint.** A valid endpoint can return an empty collection; a non-exported endpoint can return 404.
8. **Missing pagination metadata.** Check whether the method returns \`Page<T>\` or \`List<T>\`, and whether it accepts \`Pageable\`.
9. **Page size too large.** Check the page size limits of the REST exporter and read the response metadata.
10. **Exposing internal query methods.** Check the export configuration and security policy for each method.

## 13. Diagnostic checklist

When a search endpoint does not work, check in order:

1. Is the repository collection resource exported and accessible?
2. Does the collection response have a \`search\` relation?
3. Does \`GET /search\` return the method relations?
4. Is the query method recognized by Spring Data and exported?
5. Is there a \`@RestResource(path=..., rel=...)\` annotation customizing the endpoint?
6. Do the parameter names sent by the client match \`@Param\`?
7. Can the value types be converted to the Java types?
8. Does the method return \`Page\`, \`List\`, or another type?
9. If using \`Pageable\`, is the client sending appropriate page/size/sort values?
10. Does security allow the principal to invoke the search method?
11. Are there any page size or query limits altering the results?

When debugging, capture the request URI, query string, Accept header, status code, response headers, and HAL body. Compare the collection response with the search resource response to determine whether the issue lies in repository export, method export, parameter binding, or query execution.

## Summary

The \`/search\` resource is the discovery point for query methods exported by Spring Data REST for a repository. The collection typically advertises the \`search\` relation; the search resource in turn advertises a relation for each method, with an href that may be a URI template. Clients read the relation, expand the href with query parameters, and send GET to execute the query.

Query methods are defined in the repository and can be derived queries or declared queries. \`@Param\` sets the public parameter name; \`@RestResource\` customizes the relation/path or hides the method with \`exported = false\`. Methods returning \`Page<T>\` can provide pagination metadata and links, while methods returning \`List<T>\` usually represent only the list of results.

Let clients discover endpoints via HAL, explicitly control which query methods are exported, and protect every search request with server-side security and validation.

## References

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Repository Resources and Search](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data Commons — Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
