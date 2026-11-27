# Missing Parameters, Invalid Values, and Empty Results in Spring Data REST Queries

## Objectives

After this lesson, you will be able to read and invoke Spring Data REST search resources properly; distinguish required parameters from optional parameters; recognize type conversion errors and invalid input data; and tell apart a query that succeeds with no matching records from a non-existent endpoint.

## 1. Search resource and query method resource

When a repository has query methods exported by Spring Data REST, the API exposes a search resource at the `/search` path. The search resource returns links to each query method resource. Clients should discover these links from HAL instead of guessing URLs.

Example repository:

```java
public interface PersonRepository
        extends PagingAndSortingRepository<Person, Long> {

    List<Person> findByName(String name);

    List<Person> findByAgeGreaterThan(Integer age);
}
```

For a repository with collection path `/people`, query methods are typically exposed under:

- `GET /people/search`: lists links to query methods.
- `GET /people/search/findByName?name=Ada`: runs the query by name.
- `GET /people/search/findByAgeGreaterThan?age=18`: runs the query by age.

The search resource only supports `GET`; query method resources are also read-only resources supporting only `GET`. If a method is not exported or is hidden with `@RestResource(exported = false)`, its link will not appear in the search resource listing.

You can customize the path and relation name of a query method:

```java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends CrudRepository<Person, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    List<Person> findByName(@Param("name") String name);
}
```

In this example, the query method is exposed at `/people/search/by-name`, with the parameter `name`. `path` changes the URL segment; `rel` changes the relation name in HAL. Use the links returned by the server to determine the actual URLs and parameter names.

## 2. Passing query parameters properly

Parameters of a query method are passed in the URL query string. Parameter names must match the names advertised by Spring Data REST for the method.

For example:

```http
GET /people/search/findByName?name=Ada
Accept: application/hal+json
```

For a method with multiple conditions:

```java
List<Person> findByNameAndActive(
        @Param("name") String name,
        @Param("active") Boolean active);
```

The request can be:

```http
GET /people/search/findByNameAndActive?name=Ada&active=true
```

Query string values start as text. Spring Data REST needs to convert them to the Java parameter types required by the method, such as `String`, `Integer`, `Boolean`, `UUID`, dates/times, or enums. For values containing spaces, plus signs, `&`, Vietnamese diacritics, or special characters, URL-encode them properly. When using curl, you can use `--get` and `--data-urlencode` to avoid constructing query strings incorrectly:

```bash
curl --get http://localhost:8080/people/search/findByName \
  --data-urlencode "name=Ada Lovelace" \
  -H "Accept: application/hal+json"
```

If a method uses `@Query` with named parameters in Spring Data JPA, `@Param("name")` also links the Java parameter to the bind variable name in the JPQL query. That is query binding functionality; the public name and URI of the query method should still be verified via the search resource links.

## 3. Missing parameters: required or optional?

Not every query parameter follows the same policy when omitted by a client. Behavior depends on the parameter type, nullability, and how the method is defined.

Example of a method accepting a non-nullable parameter:

```java
List<Person> findByName(String name);
```

The client should send `name` in the request. If the parameter is omitted, the framework may have no value to pass to the method; if `null` is passed to the repository method, Spring Data's nullability rules determine whether it is accepted or rejected. Primitive parameter types such as `int` and `long` also cannot represent `null`.

If you want to allow omitting a parameter, explicitly declare that intent in the repository, for instance by using a reference type with `@Nullable`:

```java
@Nullable
List<Person> findByName(@Nullable String name);
```

Allowing null does not mean Spring Data automatically ignores the filter condition. With a derived query method, `findByName(null)` can be interpreted as searching for records where `name IS NULL`, depending on query derivation and the store. It does not automatically become `findAll()`.

If business logic needs a genuinely optional filter, define the behavior explicitly. With Spring Data JPA, you can write a conditional query:

```java
@Query("""
    select p from Person p
    where (:name is null or p.name = :name)
    """)
List<Person> searchByOptionalName(@Param("name") @Nullable String name);
```

When `name` is omitted and bound to null, the name condition is bypassed. For multiple optional filters, you can use Specification, Querydsl, or a custom repository to avoid an overly complex query. Check the semantics of the store in use.

For public APIs, clearly document which parameters are required, which are optional, and any default values. Do not rely on clients guessing that omitting a parameter means "no filter".

## 4. Invalid values and type conversion errors

A query parameter may have the right name, yet its value cannot be converted to the required Java type.

Example repository accepting a numeric age:

```java
List<Person> findByAgeGreaterThan(Integer age);
```

Valid request:

```http
GET /people/search/findByAgeGreaterThan?age=18
```

Request with an invalid value:

```http
GET /people/search/findByAgeGreaterThan?age=eighteen
```

The string `eighteen` cannot be converted to `Integer`. Spring Data Core has the `QueryMethodParameterConversionException` exception to represent failing to convert a source value to the query method's parameter type. When conversion fails, the repository method cannot run with the intended value; the request is handled as an input error. The specific HTTP status code may depend on the version and the application's exception handling, so inspect both the status code and the response body.

Additional examples:

| Java type | Sent value | Issue |
| --- | --- | --- |
| `Integer` | `age=abc` | Not an integer |
| `Boolean` | `active=perhaps` | Not a valid boolean value |
| `UUID` | `id=123` | Invalid UUID format |
| `LocalDate` | `date=31-31-2025` | Does not match a valid format/calendar date |
| Enum `Status` | `status=UNKNOWN_VALUE` | No matching enum constant |

For dates/times, enums, or custom domain types, valid formats depend on the application's converters and configuration. If the API needs a custom format, register an appropriate converter and document the format in the API documentation.

Beyond conversion errors, a value may be convertible yet invalid under business rules. For instance, `age=-5` is a syntactically valid integer that may violate domain rules. Query methods do not automatically enforce every Bean Validation constraint on query parameters. If restrictions such as non-negative age, valid date ranges, or allowed statuses are required, validate them in a custom repository/service or custom controller before executing the query.

## 5. Distinguishing parameter errors from valid queries with no data

This is an important distinction when reading responses:

- **Request error:** wrong URL, required parameter missing under the contract, unconvertible value, or query cannot execute. The request does not complete as a valid query.
- **No matching data:** parameters are valid and the query executes successfully, but no records satisfy the condition. This is a valid query outcome.

For example, `GET /people/search/findByName?name=NoSuchPerson` can succeed and return an empty list. That does not mean the search endpoint failed or the resource does not exist.

The repository return type affects how an empty result is represented:

| Return type | When not found |
| --- | --- |
| `List<Person>`, `Collection<Person>`, `Iterable<Person>` | Returns an empty collection, not `null` |
| `Page<Person>` | Empty page content and metadata indicating zero elements/pages |
| `Optional<Person>` | Returns `Optional.empty()` |
| `Person` or single entity type | May return `null` if allowed by the method; if declared non-null, Spring Data may throw an exception when no result exists |

For single-entity return types, the query must guarantee at most one result. If multiple records are returned while the method requires a single entity, Spring Data can throw `IncorrectResultSizeDataAccessException`. Choose `List`, `Page`, `Optional`, or another return type suited to the query's cardinality.

Do not equate "no records found" with HTTP 404. 404 usually indicates a URI/resource was not found, such as calling a wrong query method path or a non-existent item resource. A query method that exists, succeeds, and returns an empty collection is a different situation.

## 6. Pagination and sorting also have parameters to check

If a query method accepts `Pageable` and returns `Page` or `Slice`, Spring Data REST can advertise pagination parameters in the URI template:

- `page`: page number, zero-based; defaults to 0.
- `size`: items per page; typically defaults to 20.
- `sort`: property and sort direction, e.g. `sort=name,asc`.

For example:

```http
GET /people/search/findByName?name=Ada&page=0&size=10&sort=name,asc
```

Multiple sort criteria can be sent via multiple `sort` parameters:

```http
GET /people?sort=lastname,asc&sort=firstname,asc
```

Spring Data REST has a configurable maximum page size limit. If a client requests a page size larger than the limit, the value is handled according to the application's max page size configuration; do not assume clients can request arbitrary page sizes. Check properties such as `spring.data.rest.default-page-size` and `spring.data.rest.max-page-size` in Spring Boot when adjusting this behavior.

Invalid `page`, `size`, or sort property values can cause binding or query errors depending on the version, resolver, and datastore. Use valid sortable property names; inspect the response and logs when errors occur. Do not sort by a field name solely because it appears in a JSON projection: the property must match the domain model and the store's sorting capabilities.

## 7. Reading status codes and responses accurately

When debugging, do not draw conclusions from an empty response body alone. Check in sequence:

1. **HTTP status:** did the request succeed or did the server return an error?
2. **Content-Type:** is the response HAL JSON or another JSON format?
3. **HAL links:** does the search resource advertise the query method being called?
4. **Query string:** are parameter names, encoding, and value types correct?
5. **Body and metadata:** is it an empty collection, a page with `totalElements = 0`, or is the body omitted due to configuration?
6. **Server logs:** are there conversion, nullability, query creation, SQL, or datastore errors?

Common situations:

| Symptom | Possibilities to check |
| --- | --- |
| `404 Not Found` at `/people/search` | Search resource does not exist, repository exports no query methods, or wrong URL/base path. HEAD on search resource returns 404 when no query method resources exist. |
| `404 Not Found` at a query path | Wrong path, method is hidden, or query method is not exported. |
| `405 Method Not Allowed` | An unsupported HTTP method was used; search and query method resources only support GET. |
| `400 Bad Request` | Could be a missing/unconvertible parameter or another request error; read the response and logs to identify the exact cause. |
| `200 OK` with empty collection | Query ran successfully with no matching records, or filters are too restrictive. |
| `200 OK` with empty page | The current page has no elements; check `page`, `size`, and `totalElements`. |

The table above is a diagnostic guide, not a rigid mapping for every exception. Actual status codes also depend on the versions of Spring Data REST, Spring Framework, datastore, and any exception handlers registered by the application.

## 8. Scenario-by-scenario verification examples

Suppose the repository has:

```java
public interface PersonRepository
        extends PagingAndSortingRepository<Person, Long> {

    List<Person> findByName(@Param("name") String name);

    List<Person> findByAgeGreaterThan(@Param("age") Integer age);

    Page<Person> findByActive(
            @Param("active") Boolean active,
            Pageable pageable);
}
```

**Case 1 — valid parameter, data present**

```bash
curl -i "http://localhost:8080/people/search/findByName?name=Ada"
```

Verify whether the response contains the matching person.

**Case 2 — valid parameter, no data**

```bash
curl -i "http://localhost:8080/people/search/findByName?name=NoSuchPerson"
```

If the response succeeds with an empty collection, this is a valid query result. Verify the search criteria and the data in the datastore.

**Case 3 — wrong parameter type**

```bash
curl -i "http://localhost:8080/people/search/findByAgeGreaterThan?age=abc"
```

The value `abc` cannot be converted to `Integer`. Inspect the status, error body, and logs to find details about the offending parameter.

**Case 4 — pagination parameters**

```bash
curl -i "http://localhost:8080/people/search/findByActive?active=true&page=0&size=10"
```

Verify `page`, `size`, total elements, and navigation links in HAL.

## 9. How to design easy-to-use query methods

- Name methods to clearly reflect search criteria; use `@RestResource(path = "...", rel = "...")` if default names are overly long or unclear.
- Use explicit `@Param` for named parameters, especially with `@Query`; ensure parameter names sent by clients match the advertised links/URI templates.
- Allow omitting parameters only when business logic clearly defines the meaning of missing or null values.
- Distinguish between null, empty string, and default values. These three cases do not automatically share the same semantics.
- Use appropriate Java types to catch invalid data early; add converters for custom formats when needed.
- Use `Page` or `Slice` for large datasets; configure maximum page sizes to prevent overly heavy requests.
- Use single return types such as `Optional<T>` when the query expects at most one entity; use collections when multiple results are possible.
- Do not turn an empty result into an error merely because a client expects data. If business rules require a result to exist, enforce that condition in a dedicated service or controller.

## Summary

- `GET /{repository}/search` lists query method links; `GET /{repository}/search/{method}` executes the query method.
- The query string must have names and formats compatible with the Java parameters.
- Missing/null parameters are handled according to data type and nullability; truly optional filters must define explicit semantics.
- Unconvertible values cause parameter errors; convertible values that violate business rules require separate validation.
- Collections with no results usually return an empty collection; `Optional` represents an empty single result with `Optional.empty()`.
- 404 for a non-existent URI/resource differs from a valid query returning 0 records.
- Always inspect status, Content-Type, HAL links, response metadata, and server logs when investigating issues.

## References

- [Spring Data REST — Repository resources, search resource and query method resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data Commons — Defining query methods and return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data JPA — Null handling of repository methods](https://docs.spring.io/spring-data/jpa/reference/repositories/null-handling.html)
- [QueryMethodParameterConversionException — Spring Data API](https://docs.spring.io/spring-data/keyvalue/reference/data-commons/api/java/org/springframework/data/repository/support/QueryMethodParameterConversionException.html)
