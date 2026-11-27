# Distinguishing Non-Existent Resources, Empty Collections, and Disabled Methods in Spring Data REST

## Objectives

When calling a REST API, three situations can feel similar on the client side: not receiving the expected entity, a collection having no items, or an operation failing to execute. However, they have different meanings:

1. **Non-existent resource:** The URI points to a repository resource or item resource that cannot be found. The typical case is HTTP \`404 Not Found\`.
2. **Empty collection:** The collection resource exists and the GET request succeeds, but there are no matching items. The typical case is HTTP \`200 OK\` with an empty collection representation.
3. **Disabled method:** The resource may exist, but an HTTP method or repository endpoint has been configured not to be exported. Depending on how it is disabled, the request may receive \`405 Method Not Allowed\` or \`404 Not Found\`.

Properly distinguishing these three cases helps clients handle responses accurately, helps developers locate the right configuration layer, and prevents turning routing or authorization errors into incorrect business logic.

## 1. Quick identification table

| Situation | Example | Typical HTTP result | Meaning |
|---|---|---|---|
| Item does not exist | \`GET /api/people/9999\` when no such Person exists | \`404 Not Found\` | Server did not find an item resource at the requested URI. |
| Repository resource not exported or wrong URI | \`GET /api/unknown\` | \`404 Not Found\` | Path does not map to a published resource. |
| Collection exists but has no items | \`GET /api/people\` when repository has no data yet | \`200 OK\` | Valid collection, currently empty content. |
| Search returns no results | \`GET /api/people/search/by-status?status=UNKNOWN\` | \`200 OK\` | Search resource exists and query succeeded, but no items matched. |
| HTTP method not allowed on resource | \`POST /api/people\` when POST is disabled | Typically \`405 Method Not Allowed\` | URI/resource was recognized, but that method is unsupported or disabled. |
| Query method not exported | Calling search URI of a method with \`exported=false\` | Possibly \`404 Not Found\` | Search endpoint is not published so the route may not exist. |
| Request rejected by security | Calling a protected endpoint without sufficient permissions | \`401\` or \`403\` (configuration may mask with \`404\`) | Authentication/authorization issue, not equivalent to an empty resource. |

Status codes are the first diagnostic clue, not the sole proof. In particular, how an endpoint is disabled affects whether the server returns 404 or 405.

## 2. Non-existent resource: HTTP 404

### Item resource has no matching data

Suppose the Person repository is exported:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

If an entity exists with ID 42 but not ID 9999:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

may return the item representation:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "id": 42,
  "firstName": "Ada",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42"
    }
  }
}
~~~

Whereas the request:

~~~http
GET /api/people/9999
Accept: application/hal+json
~~~

typically returns:

~~~http
HTTP/1.1 404 Not Found
~~~

Spring Data REST cannot find an entity to represent as an item resource. Clients should not treat this response as an empty collection, because the URI represents a specific item.

### Repository resource does not exist or is not exported

A request such as:

~~~http
GET /api/unknown
~~~

may return 404 if:

- No repository is exported at that resource path.
- The repository is hidden via \`@RepositoryRestResource(exported = false)\`.
- The base path or collection path in the request is incorrect.
- The repository is not scanned or not registered in the ApplicationContext.
- The actual resource path was customized and the client is using an outdated URL.

In this case, the collection resource was not found. This is an important difference from a valid collection with no items: an empty collection still has a URI and GET succeeds.

### Checks when receiving 404

1. Read links from the API entry point or the most recent HAL response to get the server-published URI.
2. Check the base path in \`spring.data.rest.base-path\` or \`RepositoryRestConfiguration\`.
3. Check \`path\` and \`collectionResourceRel\` on \`@RepositoryRestResource\`.
4. Check whether the repository is scanned, instantiated as a bean, and exported under the current repository detection strategy.
5. If calling an item URI, check whether the identifier exists in the store.
6. Check whether the endpoint is hidden by \`exported = false\` or security configuration.

Do not conclude that the database has no data from a 404 response alone. The request may be hitting the wrong URI or the repository may not be exported.

## 3. Empty collection: HTTP 200 with a valid collection representation

### Collection resource still exists

Suppose the Person repository is exported, but the database does not yet contain any Person records. The request:

~~~http
GET /api/people
Accept: application/hal+json
~~~

still accesses a valid collection resource. The response may look like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/people"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

Depending on the version and representation, an empty collection response may contain \`"_embedded": {"people": []}\` or omit \`_embedded\` when there are no resources to embed. Clients should accept both forms.

The key point is that the collection resource exists and the GET request succeeded. Having no items is not a resource-lookup error.

### Search returns empty

For example, a repository has an exported query method:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByStatus(PersonStatus status);
}
~~~

If the search resource has relation \`byStatus\`, the request:

~~~http
GET /api/people/search/byStatus?status=UNKNOWN
Accept: application/hal+json
~~~

may return an empty collection with status 200 when the query is valid but no matching records are found.

Distinguish between:

- Search resource does not exist because the method is not exported or the URI is wrong: may return 404.
- Search resource exists, query is valid, but has no results: 200 with empty results.
- Query parameter is invalid or cannot be converted: may return 400 Bad Request.
- Request lacks access permissions: may return 401/403 or be masked by security.

### Empty collection vs. out-of-range page

Another easy-to-confuse case is when a client requests a page index beyond the existing number of pages.

For example, the repository has 5 elements and page size is 2, but the client calls:

~~~http
GET /api/people?page=9&size=2
Accept: application/hal+json
~~~

The server may return 200 with empty content for the current page, while metadata indicates the collection actually has data:

~~~json
{
  "page": {
    "size": 2,
    "totalElements": 5,
    "totalPages": 3,
    "number": 9
  }
}
~~~

This is not the same as a completely empty collection:

| Metadata | Collection with no data | Out-of-range page index |
|---|---:|---:|
| \`totalElements\` | 0 | Greater than 0 |
| \`totalPages\` | 0 (for positive page size) | Actual page count greater than 0 |
| Items on current page | 0 | 0 |
| Meaning | No results for collection/query | Collection has data, but the requested page contains no items |

Clients should inspect \`totalElements\` and \`totalPages\`, not just whether the items array is empty.

## 4. Disabled method: resource may exist, but operation is not allowed

Spring Data REST can restrict which HTTP operations clients may perform on a collection or item resource. For example, an application might allow GET while disabling POST, PUT, PATCH, or DELETE.

Suppose collection \`/api/people\` is exported and GET works, but POST has been disabled. The request:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "Ada",
  "lastName": "Lovelace"
}
~~~

may return:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, OPTIONS
~~~

The \`Allow\` header (if sent by the server) indicates the HTTP methods supported at that URI. Status 405 states that the server recognized the resource/URI, but the requested method is not permitted.

### Disabling HTTP methods with ExposureConfiguration

You can configure exposure per domain type and resource type through \`RepositoryRestConfigurer\`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.HttpMethod;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;

@Configuration
class DataRestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getExposureConfiguration()
            .forDomainType(Person.class)
            .withCollectionExposure((metadata, methods) ->
                methods.disable(HttpMethod.POST))
            .withItemExposure((metadata, methods) ->
                methods.disable(
                    HttpMethod.PUT,
                    HttpMethod.PATCH,
                    HttpMethod.DELETE
                ));
    }
}
~~~

Meaning of the configuration:

- \`withCollectionExposure\` adjusts methods on the collection resource, such as \`POST /people\`.
- \`withItemExposure\` adjusts methods on the item resource, such as \`PUT /people/42\`, \`PATCH /people/42\`, \`DELETE /people/42\`.
- GET can remain allowed so clients can read data.
- Disabled methods will not be permitted by the exporter under that configuration.

The API and callback signatures must be compatible with your project's Spring Data REST version. If using an older version, check the corresponding Javadoc before applying the configuration.

### Disabling a query method or resource with exported=false

There is another way to avoid publishing an endpoint: marking the repository or method as not exported.

Hiding a query method:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(exported = false)
    List<Person> findByInternalFlagTrue();
}
~~~

Hiding an entire repository:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalPersonRepository
        extends JpaRepository<InternalPerson, Long> {
}
~~~

These two cases have different scopes:

- \`@RestResource(exported = false)\` on a method hides that query method endpoint.
- \`@RepositoryRestResource(exported = false)\` on a repository hides the repository resource from Spring Data REST.

When an endpoint is not registered, the corresponding search link or resource link may not appear in HAL. Calling that URI directly may return 404 because the route is not exported. This differs from a recognized URI where an HTTP method is disallowed, which usually manifests as 405.

## 5. Distinguishing 404, 405, 401, 403, and 200

| Status | Interpretation | Diagnostic action |
|---|---|---|
| \`200 OK\` | GET succeeded; collection may have items or be empty. | Inspect \`_embedded\` and \`page.totalElements\`. |
| \`204 No Content\` | Request succeeded with no response body, common for some write/delete operations. | Check the method and response contract; do not infer an empty collection. |
| \`400 Bad Request\` | Request or query parameter is invalid, unconvertible, or violates input rules. | Check body, data types, and query parameters. |
| \`401 Unauthorized\` | Unauthenticated or invalid authentication credentials. | Check token, session, or authentication mechanism. |
| \`403 Forbidden\` | Authenticated, but lacks permission to perform the operation. | Check authorization policy and method/resource permissions. |
| \`404 Not Found\` | URI or item resource not found; endpoint may not be exported. | Check URI, repository export, identifier, and security masking. |
| \`405 Method Not Allowed\` | URI recognized, but the HTTP method is not allowed. | Check method exposure and the \`Allow\` header. |
| \`409 Conflict\` | Request conflicts with current state or data constraints. | Check entity state and write rules. |

Do not rely on status codes alone to draw conclusions about access permissions. Some Spring Security configurations intentionally return 404 to conceal the existence of a resource. In that situation, check the security filter chain, logs, and principal authorities.

## 6. Reading HAL to determine whether an endpoint is published

A collection response may provide links:

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

Clients can use links for API discovery:

- \`self\` present: the current collection resource has a published URI.
- \`search\` present: the repository has a published search resource.
- Relations to query methods present: clients can discover specific search endpoints.
- A method's link is missing: the method may not be exported, though you should also inspect profile, configuration, and representation type before concluding.

HAL is an API discovery format, not an authorization mechanism. The absence of a link does not guarantee a client cannot call the URI directly; the server must still enforce export rules and security rules.

### Using OPTIONS and Allow

When suspecting an HTTP method is disabled, you can try:

~~~http
OPTIONS /api/people
~~~

If the server returns an \`Allow\` header, that list helps identify accepted methods at the resource. For POST/PUT/PATCH/DELETE requests returning 405, also capture the \`Allow\` header.

OPTIONS behavior depends on MVC, CORS, servlet container, and security configuration. If OPTIONS does not give a clear answer, use the 405 response and inspect the application's exposure configuration.

## 7. Testing with curl

Fetch the collection:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people
~~~

Fetch an item that may exist:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/42
~~~

Fetch a non-existent item:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/9999
~~~

Call a search resource:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people/search/byStatus?status=UNKNOWN"
~~~

Check methods on the collection:

~~~bash
curl -i -X OPTIONS \
  http://localhost:8080/api/people
~~~

Test a write method in a test environment:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"firstName":"Ada","lastName":"Lovelace"}' \
  http://localhost:8080/api/people
~~~

When testing write operations, only use appropriate test data and environments. The goal here is to observe status, headers, and how the exporter responds according to configuration.

## 8. Diagnostic workflow by response

### Case A: GET returns 404

1. Check whether the URL matches the base path and collection path.
2. Check the \`self\` link or relation from the API entry point.
3. If it is an item, verify whether the identifier exists.
4. If it is a repository/search endpoint, check whether the repository or method is exported.
5. Check whether security is masking the resource with 404.

### Case B: GET returns 200 with no items

1. Determine whether the request called a collection or search endpoint.
2. Check whether \`_embedded\` is empty or omitted.
3. If \`page\` is present, read \`totalElements\`, \`totalPages\`, and \`number\`.
4. Check filter/query parameters and actual data.
5. If \`totalElements > 0\` while the current page has no items, check whether the page index is out of range.

### Case C: POST/PUT/PATCH/DELETE returns 405

1. Confirm whether GET on the same resource works.
2. Read the \`Allow\` header if present.
3. Check the \`ExposureConfiguration\` for the domain type.
4. Check repository detection, export annotations, and method exposure.
5. Verify the request targets the right collection URI or item URI.

### Case D: Endpoint returns 404 after disabling

1. Check whether \`@RestResource(exported = false)\` was placed on the query method.
2. Check whether the repository has \`@RepositoryRestResource(exported = false)\`.
3. Check whether the search/resource URI is still registered in mappings.
4. Distinguish an unpublished route from a route that exists where the method is disallowed.

## 9. Designing clients to handle all three situations properly

Clients should branch based on HTTP status and response structure:

- **200 with item:** parse the entity representation and use the \`self\` link.
- **200 with empty collection:** display a no-results state; do not report a connection error or non-existent resource.
- **200 with empty page but totalElements greater than 0:** indicate the current page has no items or adjust the page index.
- **404:** report that the resource/item was not found, while allowing handling for stale URLs or invalid identifiers.
- **405:** report that the operation is not supported on the resource; do not retry the request with the same method.
- **401/403:** handle authentication or access permissions.
- **400:** display input or query parameter errors.

Do not turn every itemless response into the same UI state. A search page with no matches can be a valid outcome; a non-existent item is a different state; a disallowed operation requires informing the user that the action is unsupported.

## 10. Common misconceptions

1. **Treating 404 as an empty collection.** 404 means the URI or item resource was not found; an empty collection normally returns 200.
2. **Treating 200 without \`_embedded\` as an error.** An empty collection may omit the \`_embedded\` field depending on representation.
3. **Checking only the items array while ignoring page metadata.** An out-of-range page can be empty even though the collection still has data.
4. **Treating 405 the same as 404.** 405 usually indicates the URI was recognized but the method is disallowed; 404 can mean a non-existent or masked route.
5. **Assuming every \`exported=false\` returns 405.** When a method or resource is not registered, direct URIs may return 404.
6. **Treating 403 as a disabled method.** 403 usually relates to authorization; method exposure and security are separate layers.
7. **Relying on HAL links to protect endpoints.** Hiding links does not replace the server rejecting invalid or unauthorized requests.
8. **Ignoring the Allow header.** This header can help identify valid methods at a URI.
9. **Manually constructing URLs and concluding the endpoint does not exist.** Extract hrefs from responses and check actual relations.
10. **Failing to distinguish a query with no results from an unexported query endpoint.** A valid search endpoint can return an empty collection; an unpublished endpoint may have no route.

## 11. Production readiness checklist

- Collection GET returns a stable representation even when there is no data.
- Clients handle both empty \`_embedded\` and omitted \`_embedded\`.
- Non-existent items are handled as 404.
- Searches with no results are handled as empty collections.
- Page metadata is used to distinguish a truly empty collection from an out-of-range page index.
- Unneeded HTTP methods are disabled at the proper collection/item exposure level.
- Non-public query methods or repositories are marked \`exported=false\` where appropriate.
- Security still enforces permissions on the server; hiding links is not treated as protection.
- API documentation describes status codes and supported methods.
- Integration tests verify status codes, headers, and body representations.

## Summary

A non-existent resource typically manifests as 404. A collection resource that exists but has no items is still a successful GET request and typically returns 200 with an empty representation. A disabled method typically returns 405 when the URI is recognized but the HTTP method is disallowed; if an endpoint has been excluded from export via \`exported=false\`, the URI may no longer be registered and may return 404.

When diagnosing, combine the status code, \`Allow\` header, HAL links, \`_embedded\`, page metadata, export configuration, and security configuration. This helps accurately identify whether the client is calling the wrong URI, has no data, is requesting an empty page, or is attempting an operation the API does not expose.

## References

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Configuring the REST URL Path and Exposure](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfiguration.html)
- [Spring Framework — HTTP Status Codes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
