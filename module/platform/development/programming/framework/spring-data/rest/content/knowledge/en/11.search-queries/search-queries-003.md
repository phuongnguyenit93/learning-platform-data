# Naming Query Parameters with @Param

## Objectives

In Spring Data REST, repository query methods are exposed under the `search` resource. Regular method parameters are passed from the query string of an HTTP GET request. The `@Param` annotation lets you assign an explicit name to each parameter in the URL.

For example, the method:

~~~java
List<Person> findByLastName(@Param("lastName") String value);
~~~

is invoked through the query resource with the parameter:

~~~http
GET /api/people/search/findByLastName?lastName=Nguyen
~~~

Here, `lastName` is the query parameter name advertised by `@Param("lastName")`; the Java variable name `value` is not what the client needs to send.

## 1. Query methods are exposed under /search

Spring Data REST automatically creates a search resource for an exported repository when the repository has eligible query methods to expose.

Suppose the `Person` repository is exported at `/api/people`:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

The search resource typically appears at:

~~~http
GET /api/people/search
~~~

The search resource response contains links to the exported query methods. For the example method above, the default link might be:

~~~json
{
  "_links": {
    "findByLastName": {
      "href": "https://api.example.com/api/people/search/findByLastName{?lastName}",
      "templated": true
    }
  }
}
~~~

Clients should read the links advertised by the server instead of guessing URLs. The default path name is derived from the query method, and the query parameter is derived from the method's parameter metadata.

## 2. @Param sets the query parameter name

`@Param` belongs to Spring Data Commons:

~~~java
import org.springframework.data.repository.query.Param;
~~~

Annotate repository method parameters to advertise the name that the query resource accepts from the URL:

~~~java
@RestResource(path = "by-last-name", rel = "byLastName")
List<Person> findPeople(
        @Param("lastName") String value);
~~~

Client calls:

~~~http
GET /api/people/search/by-last-name?lastName=Nguyen
~~~

There are three different names to distinguish:

| Component | Example | Role |
|---|---|---|
| Java method name | `findPeople` | Identifies the query method |
| Query resource path | `by-last-name` | Selects the endpoint under `/search` |
| Query parameter name | `lastName` | Passes the value into the method parameter |

The Java variable name can be `value`, `surname`, or another name. Once `@Param("lastName")` is used, the client sends the exact `lastName` key specified by the annotation.

### Why name parameters explicitly?

- The query parameter name becomes part of the HTTP API contract.
- Refactoring the Java variable name does not alter the URL used by clients.
- Readers of the repository can immediately see the name clients must send.
- The parameter name does not depend on whether the compiler retains parameter name metadata.

Relying on parameter names discovered from bytecode can depend on compiler configuration and the parameter-name discovery mechanism. Using `@Param` explicitly makes the contract clearer and more stable.

## 3. Complete example with multiple parameters

Suppose you need to find `Person` records by last name and active status, while also supporting pagination:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name-and-active", rel = "byLastNameAndActive")
    Page<Person> findByLastNameAndActive(
            @Param("lastName") String lastName,
            @Param("active") boolean active,
            Pageable pageable);
}
~~~

Client calls:

~~~http
GET /api/people/search/by-last-name-and-active?lastName=Nguyen&active=true&page=0&size=20&sort=lastName,asc
Accept: application/hal+json
~~~

Spring Data REST parses the request as follows:

| Query parameter | Value | Bound to |
|---|---|---|
| `lastName` | `Nguyen` | `@Param("lastName") String lastName` |
| `active` | `true` | `@Param("active") boolean active` |
| `page` | `0` | `Pageable` |
| `size` | `20` | `Pageable` |
| `sort` | `lastName,asc` | `Pageable` |

`@Param` names the two domain parameters. `Pageable` is a special parameter recognized by Spring Data for handling pagination and sorting; it does not need `@Param`.

With the request above, the repository method receives `lastName = "Nguyen"`, `active = true`, and a `Pageable` describing the first page, 20 items per page, sorted by `lastName` ascending.

## 4. @Param and Pageable/Sort

Paging and sorting parameters are handled by Spring Data according to their own conventions:

- `Pageable` receives query parameters such as `page`, `size`, and `sort`.
- `Sort` receives sorting information from the `sort` query parameter.
- Other domain parameters are bound using the name declared with `@Param` or the parameter-name discovery mechanism supported by the repository.

Example using only `Sort`:

~~~java
List<Person> findByActive(
        @Param("active") boolean active,
        Sort sort);
~~~

Request:

~~~http
GET /api/people/search/findByActive?active=true&sort=lastName,asc
~~~

If using `Pageable`, multiple sort criteria can be specified by repeating the query parameter:

~~~http
GET /api/people/search/findByLastName?lastName=Nguyen&sort=lastName,asc&sort=firstName,asc&page=0&size=20
~~~

The names `page`, `size`, and `sort` are Spring Data web support conventions. Do not rename them into domain names using `@Param`; reserve `@Param` for the method's query parameters.

## 5. Naming the path and naming parameters are independent

`@RestResource` and `@Param` address two different parts of the URL.

~~~java
@RestResource(path = "by-email", rel = "byEmail")
Optional<Person> findByEmailAddress(
        @Param("email") String emailAddress);
~~~

Request:

~~~http
GET /api/people/search/by-email?email=an%40example.com
~~~

In this example:

- `path = "by-email"` determines the path segment after `/search/`.
- `rel = "byEmail"` determines the relation name in the search resource.
- `@Param("email")` determines the query key name.
- `emailAddress` is the Java variable name in the method.

If you only change `path`, the query key `email` stays the same. If you only change `@Param`, the path `by-email` stays the same. When changing either one, update clients according to the exact part of the contract that changed.

## 6. Using @Param with @Query

In Spring Data JPA, `@Param` also commonly links a method parameter to a named parameter in JPQL:

~~~java
@Query("""
    select p
    from Person p
    where lower(p.lastName) = lower(:lastName)
    """)
List<Person> findMatchingLastName(
        @Param("lastName") String value);
~~~

Two places use the same name `lastName`, serving two related roles:

1. In JPQL, `:lastName` is the named parameter of the query.
2. In Spring Data REST, `@Param("lastName")` advertises the query parameter sent by the HTTP client.

The client invokes the search resource:

~~~http
GET /api/people/search/findMatchingLastName?lastName=Nguyen
~~~

Spring Data REST binds the value `Nguyen` to the method parameter. Spring Data JPA then uses that value for the `:lastName` named parameter in the JPQL query.

If you rename the annotation to `@Param("surname")` while keeping `:lastName` in JPQL, the two names no longer match and named parameter binding may fail. When renaming, synchronize the name in both the annotation and the query.

## 7. Multiple data types and value conversion

HTTP query parameters are always transmitted as text. Spring Data/Spring conversion infrastructure converts the text to the method parameter type when a matching converter is available.

For example:

~~~java
List<Person> findByAgeGreaterThanAndActive(
        @Param("minimumAge") Integer minimumAge,
        @Param("active") Boolean active);
~~~

Request:

~~~http
GET /api/people/search/findByAgeGreaterThanAndActive?minimumAge=18&active=true
~~~

Some commonly used types:

| Java type | Illustrative query string value |
|---|---|
| `String` | `lastName=Nguyen` |
| `Integer` / `Long` | `minimumAge=18` |
| `Boolean` | `active=true` |
| `Enum` | `status=ACTIVE` |
| `LocalDate` | `createdAfter=2026-01-01` |

Date/time, enum, and domain type formats depend on the application's converters and configuration. Use the formats actually supported by the API and test conversion errors with sample requests.

If a required parameter is missing or a value cannot be converted to the Java type, the request may be rejected with a 400 Bad Request error. Do not treat every 400 error as a database query error; inspect the error response and binding logs to pinpoint the cause.

## 8. URL encoding for query values

Values containing spaces, `&`, `+`, Unicode characters, or reserved characters must be properly URL-encoded.

Example of a compound last name:

~~~http
GET /api/people/search/findByLastName?lastName=Van%20Nguyen
~~~

Using curl for automatic encoding:

~~~bash
curl --get \
  --data-urlencode "lastName=Van Nguyen" \
  --data-urlencode "active=true" \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/search/by-last-name-and-active
~~~

Do not concatenate query strings manually without encoding. A value containing `&` can be misinterpreted as the next parameter; a `+` in a query string can also be interpreted as a space under form URL encoding rules.

## 9. The @Param name is part of the API contract

When a client calls a query resource, the key name in the URL must match the name advertised by `@Param`.

For example:

~~~java
List<Person> findByCity(
        @Param("cityName") String city);
~~~

Client uses:

~~~http
GET /api/people/search/findByCity?cityName=Hanoi
~~~

If you change the annotation to:

~~~java
List<Person> findByCity(
        @Param("city") String city);
~~~

the new query key is `city`. Clients still sending `cityName` will need to be updated. Renaming a query parameter is an API contract change even if the Java method name stays unchanged.

To reduce risk:

- Choose short, clear, and consistent names.
- Use the same camelCase convention for query keys if the API uses camelCase.
- Keep names stable when refactoring Java variables.
- When a key must change, consider a compatibility window or versioning for clients.
- Inspect the search resource after exporting to confirm the link template advertises the expected keys.

## 10. Distinguishing @Param from other annotations

| Annotation | Typical placement | Purpose |
|---|---|---|
| `@Param` | Spring Data repository method parameter | Names query parameters, including query parameters advertised by Spring Data REST |
| `@RequestParam` | Spring MVC controller method parameter | Binds an HTTP request parameter to a controller argument |
| `@PathVariable` | Spring MVC controller method parameter | Binds a variable from the URI path |
| `@RestResource` | Repository or query method | Customizes export behavior, path, and relation |
| `@RepositoryRestResource` | Repository interface | Customizes the resource path, relation, and export of the repository |

Do not use `@RequestParam` on a repository query method just because the value comes from a query string. Repository methods belong to Spring Data; `@Param` is the right annotation for repository parameter metadata. `@RequestParam` is for application-written controllers.

## 11. Inspecting the search resource and debugging binding

When a query method does not receive parameters as expected, check in order:

1. Send a GET to the collection search resource, e.g. `/api/people/search`, to verify whether the query method is exported.
2. Follow the exact href of the query method; check whether the path was customized with `@RestResource(path = "...")`.
3. Read the URI template in `_links`; the `{?...}` portion shows the query keys advertised by the server.
4. Match each key against `@Param("...")` on the repository method.
5. Check special `Pageable`/`Sort` parameters; use `page`, `size`, `sort` according to convention.
6. Verify data types and value formats; pay attention to enums, dates/times, booleans, and IDs.
7. Encode values with special characters.
8. Check whether the method was hidden via `@RestResource(exported = false)` or whether repository export was disabled.
9. If using `@Query`, match `@Param` against the named placeholder in JPQL.
10. Read the status code and error body. 404 may indicate a non-existent path/query resource; 405 may indicate an unexported method; 400 is usually related to binding or payload.

Example of a method with two parameters:

~~~java
@RestResource(path = "by-last-name-and-active")
Page<Person> findByLastNameAndActive(
        @Param("lastName") String lastName,
        @Param("active") Boolean active,
        Pageable pageable);
~~~

The search resource should advertise a link template similar to:

~~~text
/api/people/search/by-last-name-and-active{?lastName,active,page,size,sort}
~~~

If the actual link does not contain `lastName` or `active`, inspect the method metadata and export behavior instead of guessing the query keys.

## 12. Key takeaways

- Exported Spring Data REST query methods live under `/search`.
- `@Param("name")` sets the query key that the client sends; the Java variable name can differ.
- `@RestResource(path = "...")` sets the path of the query resource; it does not set query parameter names.
- `Pageable`/`Sort` use their own keys such as `page`, `size`, `sort`; `@Param` is not needed for these special parameters.
- For JPQL `@Query`, the `@Param` name must match the named placeholder.
- Query string data must be encoded and converted to the appropriate type.
- The `@Param` name is part of the API contract; renaming it can impact clients.
- Use the search resource and URI templates advertised by the server to confirm the endpoint and query keys.

## References

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data Commons — Repository query method parameters](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data JPA — Using named parameters](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
