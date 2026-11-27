# Exposing Derived Query Methods as Read-Only Resources

## Objectives

Spring Data REST can automatically expose repository query methods as search resources. For a derived query method, Spring Data parses the method name to build a query from property names and conditions. Spring Data REST provides an HTTP `GET` endpoint so clients can invoke that query without writing a separate Controller.

A search resource is a read-only resource: clients send criteria via query parameters and receive the query results. Exposing a search method does not automatically create write endpoints for that method. However, the repository can still have collection and item resources with POST, PUT, PATCH, or DELETE operations if the corresponding CRUD operations are exported.

## 1. What is a derived query method?

A derived query method is a repository method whose name follows Spring Data conventions. Spring parses the method name to determine the properties, operators, and sort order to use.

For example:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);

    List<Person> findByActiveTrue();

    List<Person> findByAgeGreaterThan(int age);

    Optional<Person> findByEmailIgnoreCase(String email);
}
~~~

Spring Data infers the corresponding conditions:

- `findByLastName`: matches the `lastName` property.
- `findByActiveTrue`: retrieves only entities with `active = true`.
- `findByAgeGreaterThan`: filters entities whose `age` is greater than the supplied value.
- `findByEmailIgnoreCase`: matches email case-insensitively.

These method names are Spring Data query rules, not necessarily the URLs clients must call. Spring Data REST builds the search URI based on the repository and the method's export configuration.

## 2. Spring Data REST exposes search resources

When a query method is exported, Spring Data REST places it under the `search` path of the collection resource. For example, if a repository has the collection path `people`, the search resource has the form:

~~~text
/people/search/{search-method}
~~~

If declared as:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

Spring Data REST can expose the method with a default path based on the method name, such as:

~~~http
GET /people/search/findByLastName?lastName=Nguyen
~~~

This request invokes the `findByLastName` finder and returns the matching list of `Person` entities. The endpoint is invoked with HTTP GET, so the client does not send an entity update command through the search resource.

Exported finders also appear under the `search` link of the HAL collection representation. Clients should discover the links returned by the server rather than constructing URLs by assumption:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "search": {
      "href": "http://localhost:8080/people/search"
    }
  }
}
~~~

When issuing a GET to the search resource, the server provides links to each exported finder and URI templates for the parameters the method requires.

## 3. Naming the URL and relation with @RestResource

`@RestResource` can be used on a query method to give the path and relation clearer, more stable names than the Java method name:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "by-last-name")
    List<Person> findByLastName(
        @Param("lastName") String lastName);
}
~~~

Client calls:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
Accept: application/hal+json
~~~

The two attributes have distinct meanings:

- `path`: the path segment of the search endpoint.
- `rel`: the relation name advertised in the HAL link of the search resource.

Using business-oriented names for paths makes the API easier to read and reduces coupling to Java method naming. If the method is renamed while keeping `path` and `rel` unchanged, clients can continue using the same endpoint.

Do not set a search path that collides with an item path or another search method in the same repository. Keep finders under the `/search` namespace and choose unique, meaningful paths.

## 4. Naming query parameters with @Param

Use `@Param` to define the parameter name that clients send in the URL:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "by-last-name")
    List<Person> findByLastName(
        @Param("lastName") String value);
}
~~~

The method uses the Java variable name `value`, but the public name on the URL is `lastName` because it is declared in `@Param`.

Request:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
~~~

When there are multiple parameters:

~~~java
@RestResource(path = "by-name-and-status", rel = "by-name-and-status")
List<Person> findByLastNameAndActive(
    @Param("lastName") String lastName,
    @Param("active") boolean active);
~~~

The client sends both parameters:

~~~http
GET /people/search/by-name-and-status?lastName=Nguyen&active=true
~~~

The parameter names in the request must match the advertised names. Values in the URL are converted to the corresponding Java types; if a value is invalid for the target type, the request may fail during the conversion step.

## 5. Paging and sorting for search resources

If a finder returns `Page<T>` and accepts `Pageable`, clients can use standard Spring Data REST paging and sort parameters:

~~~java
@RestResource(path = "by-last-name", rel = "by-last-name")
Page<Person> findByLastNameIgnoreCase(
    @Param("lastName") String lastName,
    Pageable pageable);
~~~

Request:

~~~http
GET /people/search/by-last-name?lastName=nguyen&page=0&size=20&sort=firstName,asc
Accept: application/hal+json
~~~

Commonly used parameters:

- `page`: page number, starting from 0.
- `size`: requested number of items per page.
- `sort`: property name and sort direction, for example `firstName,asc` or `createdAt,desc`.

Multiple sort criteria can be passed by repeating the `sort` parameter. Default page size and maximum limits can be adjusted in Spring Data REST configuration. Clients should respect the limits enforced by the server.

If pagination metadata is not needed, the finder can return `List<T>`. Choose the return type according to API needs: `Page<T>` is useful when clients need page information and total element count; `List<T>` is suitable for small result sets or when pagination is unnecessary.

## 6. Common return types

A derived query method can return a variety of result types supported by Spring Data:

| Return type | Meaning |
|---|---|
| `List<Person>` or `Collection<Person>` | List of results |
| `Page<Person>` | Results with pagination and metadata |
| `Slice<Person>` | A slice of data, useful when total element count is not needed |
| `Optional<Person>` | Zero or one result |
| `Person` | A single result, if the query guarantees at most one result |
| `long` or `boolean` | Aggregate count or existence check, depending on the query method |

Choose a return type matching the number of results the query condition can produce. If a method can return multiple entities, do not declare a single-result type that can throw an error when multiple results exist. For large datasets, prefer pagination instead of returning the entire list.

## 7. Exposing only necessary finders

By default, Spring Data REST can export eligible query methods on a repository. You can change a method's path/rel or disable exporting a specific finder using `@RestResource(exported = false)`:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "by-last-name")
    List<Person> findByLastName(
        @Param("lastName") String lastName);

    @RestResource(exported = false)
    List<Person> findByInternalReviewStatus(String status);
}
~~~

In this example:

- `findByLastName` is exposed under `/people/search/by-last-name`.
- `findByInternalReviewStatus` is not exposed as a search endpoint.

Hiding a finder is useful when the method is strictly for internal use, contains criteria not meant for clients, or is not yet part of the API contract. After disabling export, the application can still call that method from Java services/repositories as usual.

You can disable exporting the entire repository with `@RepositoryRestResource(exported = false)`, but then the resources and finders belonging to the repository are no longer exposed in the standard way either. Only use this option when the goal is to hide the entire repository.

## 8. Why are search resources read-only?

Spring Data REST exposes query methods as search operations over HTTP GET. Clients supply query criteria via path/query parameters; the server executes the finder and returns the results. A search URI is not an endpoint to create, replace, or delete entities.

For example:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
~~~

The request only reads results. It is not equivalent to:

- `POST /people`: creates a new entity.
- `PUT /people/42`: replaces an item's state.
- `PATCH /people/42`: partially updates an item.
- `DELETE /people/42`: deletes an item.

A query method used for searching should genuinely be a read query. Do not design a finder with side effects or data mutations and expose it as a GET search resource. By HTTP semantics, GET must be safe so clients, proxies, and caches can repeat calls without expecting server state changes.

**Understand the read-only scope accurately:** finder endpoints are GET-only, but that does not automatically make the entire repository read-only. If `PersonRepository` still exports CRUD methods, the collection/item resources can still allow writes. When writes must be locked down at the repository level, configure exposure for write HTTP methods or hide the corresponding CRUD operations, while also enforcing authorization at the security layer.

## 9. Restricting access permissions and returned data

An exposed search endpoint does not mean every user should be allowed to call it. If results contain sensitive data or are intended only for a specific group of users:

- Use Spring Security to require authentication and authorization for the endpoint.
- Export only the finders clients actually need.
- Use projections or serialization configuration to limit returned fields.
- Validate input data and limit pagination to prevent overly broad queries.
- Do not treat using HTTP GET or `exported = false` as a substitute for authorization.

If you want to restrict a repository to read-only, you can configure exposure for collection and item resources. Illustrative example disabling write methods:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getExposureConfiguration()
            .withCollectionExposure((metadata, methods) ->
                methods.disable(HttpMethod.POST));

        config.getExposureConfiguration()
            .withItemExposure((metadata, methods) ->
                methods.disable(
                    HttpMethod.PUT,
                    HttpMethod.PATCH,
                    HttpMethod.DELETE));
    }
}
~~~

The configuration snippet above applies collection/item exposure across all repositories in that configuration. If you only want to restrict a single domain type, use the `forDomainType(Person.class)` API according to the Spring Data REST version in use. Verify the API signature of your actual dependency before applying; authorization still needs to be configured separately.

## 10. Testing search resources

MockMvc can be used to test an exported finder endpoint and verify it works with GET:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonSearchResourceTests {

    @Autowired
    MockMvc mvc;

    @Test
    void searchByLastNameReturnsHalCollection() throws Exception {
        mvc.perform(get("/people/search/by-last-name")
                .param("lastName", "Nguyen")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON));
    }

    @Test
    void searchEndpointDoesNotAcceptPost() throws Exception {
        mvc.perform(post("/people/search/by-last-name")
                .param("lastName", "Nguyen"))
            .andExpect(status().isMethodNotAllowed());
    }
}
~~~

This is an integration test skeleton; you need to prepare test data, repository export configuration, and verify status codes appropriate to the application. Add assertions for the result content and HAL links to ensure the finder returns the right data.

Also check:

- Whether the search link appears in the collection representation.
- Whether the custom path and `rel` relation match the configuration.
- Whether query parameters have the right names and types.
- That finders marked `exported = false` are no longer exposed.
- That POST/PUT/PATCH/DELETE requests to the search URI are not handled as write operations.
- That other CRUD endpoints of the repository still follow the expected exposure policy.

## 11. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Search link not visible | Finder is not exported or repository is not exported | Check repository annotations and `exported` on the method |
| Default search URL is hard to read | Path is generated from the Java method name | Set `@RestResource(path = "...", rel = "...")` |
| Query parameter does not receive value | Missing or mismatched `@Param` name | Use explicit parameter names and send the matching key in the URL |
| Request with wrong type returns error | Query parameter value cannot be converted | Check the Java type and URL format |
| Finder returns too much data | Using List/Collection without pagination | Use `Page<T>` and `Pageable` |
| Client POST to search URI is rejected | Search resource only exposes GET | Use GET for queries; use collection/item endpoints for appropriate writes |
| Finder hidden but client can still access data | Another finder or CRUD endpoint is still exported | Audit all search links and repository exposure |
| Search returns data that should not be public | Missing authorization or projection does not restrict fields | Configure Spring Security and appropriate representations |

## 12. Checklist for exposing derived query methods

- Choose method names following Spring Data derived query rules.
- Only expose finders intended for reading and free of side effects.
- Use `@RestResource(path = "...", rel = "...")` for clear URLs and relations.
- Use `@Param` for public query parameter names.
- Choose an appropriate return type: List, Page, Slice, or Optional.
- Use Pageable/Sort when paging and sorting are needed.
- Hide internal finders with `@RestResource(exported = false)`.
- Inspect search links in HAL and test actual GET requests.
- Distinguish GET-only finders from the write policy of collection/item resources.
- Apply authorization and field restrictions if data is not meant for all clients.

## Conclusion

Spring Data REST can expose derived query methods as read-only search resources under `/{collection}/search/{path}`. Spring Data derives the query from the method name; `@RestResource` sets the path and relation, while `@Param` defines the parameter name on the URL. Clients call the finder using GET and can use Pageable/Sort if the method supports them. Use `exported = false` to hide finders not intended for clients. Search endpoints are GET-only, but the repository can still have separate write endpoints; to make the entire resource read-only, configure exposure and authorization accordingly.

## References

- Spring Data REST – Defining repository resources and query methods: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data Commons – Query method keywords: https://docs.spring.io/spring-data/commons/reference/repositories/query-keywords-reference.html
- Spring Data Commons – Repository query return types: https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html
- Spring Data REST – Projections and excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
