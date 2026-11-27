# GET Root Resource and Identifying Exposed Repositories in Spring Data REST

## Objectives

Spring Data REST automatically exports Spring Data repositories as REST resources and defaults to representing responses in HAL (Hypertext Application Language). Clients can begin discovering the API by sending an HTTP GET request to the **root resource (API root)**. The root response contains links leading to next-level resources, typically the collection resources of the exposed repositories.

Instead of knowing every path such as `/employees`, `/orders`, or `/products` in advance, the client reads `_links` in the root response, identifies the relation, and follows the corresponding `href` URL. This is the discoverability mechanism of HATEOAS.

This lesson focuses on how to call the API root, read HAL, identify repository collections, distinguish repository links from metadata links, and handle cases where a repository does not appear in the list.

## 1. The API root is the starting point for discovery

Suppose the application runs at `http://localhost:8080`. Without a custom base path configured, the Spring Data REST root resource is typically located at:

~~~http
GET /
Accept: application/hal+json
~~~

Use curl to inspect both the status code and response headers:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
~~~

If the application configures a base path, for example:

~~~properties
spring.data.rest.base-path=/api
~~~

then call the Spring Data REST root at:

~~~http
GET /api
Accept: application/hal+json
~~~

If the application also configures a servlet context path, such as `server.servlet.context-path=/myapp`, the external URL will include both the context path and the Spring Data REST base path, for example `/myapp/api`.

A typical root response may look like this:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "_links": {
    "employees": {
      "href": "http://localhost:8080/api/employees"
    },
    "orders": {
      "href": "http://localhost:8080/api/orders"
    },
    "profile": {
      "href": "http://localhost:8080/api/alps"
    }
  }
}
~~~

In this example:

- `employees` and `orders` are relations leading to the collection resources of two exposed repositories.
- The `href` value is the collection URL that the client should call next.
- `profile` is a link to ALPS metadata describing the API, not a repository collection.

The number and names of links depend on the actual repositories and the application's export configuration. You should not assume the root always has the exact relations shown in the example.

## 2. Reading the HAL structure in the root response

HAL places links inside the `_links` property. Each key in `_links` is a **link relation (rel)**; the corresponding value is an object containing the URL and possibly additional link metadata.

Example:

~~~json
{
  "_links": {
    "employees": {
      "href": "http://localhost:8080/api/employees"
    }
  }
}
~~~

You can read it as follows:

| Component | Value | Meaning |
| --- | --- | --- |
| `_links` | Object | Collection of HAL links of the root resource. |
| `employees` | Relation | Relation name describing the next collection resource. |
| `href` | URL | Actual address for the client to navigate to the collection. |

**The relation and the path do not necessarily match.** For example, the relation might be `staff`, while the path is `/employees`. Therefore, the client should use the returned `href`, rather than manually concatenating `/api/` with the relation name.

Some responses may include additional links such as `profile`, `curies`, or links for other features. Not every key in `_links` is a repository. Understand relation meanings according to HAL and the API documentation; in Spring Data REST, `profile` is a root-level metadata link.

## 3. Which repositories appear in the root?

Spring Data REST creates a collection resource for an exported repository. By default, the collection name and relation are derived from the simple name of the domain class, lowercased and pluralized according to the framework's naming rules.

Example:

~~~java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

If the repository is detected and exported, the default collection resource can be:

~~~text
/employees
~~~

The path and relation can be customized using `@RepositoryRestResource`:

~~~java
@RepositoryRestResource(
        path = "employees",
        collectionResourceRel = "staff"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

With this configuration, the root may contain:

~~~json
{
  "_links": {
    "staff": {
      "href": "http://localhost:8080/api/employees"
    }
  }
}
~~~

Here `staff` is the relation name; `/api/employees` is the path. The two values are configured separately:

- `path`: the path segment used to access the collection resource.
- `collectionResourceRel`: the relation name used when linking to the collection in HAL.

Therefore, when inspecting an application, record both the rel and the href. Do not infer the Java repository name or path from only one of the two values.

## 4. Following a link from the root to a collection resource

After reading the root, the client calls the URL in the `href` of the desired relation:

~~~http
GET /api/employees
Accept: application/hal+json
~~~

The collection resource returns the entities managed by the repository, along with related links. Example:

~~~json
{
  "_embedded": {
    "employees": [
      {
        "firstName": "Lan",
        "lastName": "Pham",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/employees/12"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/employees?page=0&size=20"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/employees"
    },
    "search": {
      "href": "http://localhost:8080/api/employees/search"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

The links at the collection level have specific meanings:

- `self`: URL of the current collection, which may include pagination parameters.
- `profile`: metadata describing the collection/domain resource.
- `search`: appears if the repository has exposed query methods.

`search` typically appears in the collection response, not in the collection list at the API root. The client proceeds using the `href` of the `search` link, then reads the list of query method resources there.

Similarly, association links such as `department`, `manager`, or `roles` typically appear in the item resource. The root is not the place that lists all items, associations, and query methods of every repository; it is the starting point for exploring each branch.

## 5. Identifying exposed repositories

When inspecting an API, you can compile a list of repository collections from the links in the root:

| Relation in `_links` | Href | Conclusion |
| --- | --- | --- |
| `employees` | `/api/employees` | Collection resource exposed with relation `employees`. |
| `staff` | `/api/employees` | Same `employees` path, but relation customized to `staff`. |
| `orders` | `/api/orders` | Collection resource `orders` is exposed. |
| `profile` | `/api/alps` | ALPS metadata link, not a repository collection. |

A practical workflow:

1. Call the root URL matching the application's base path and context path.
2. Check the status code and content type. With HAL, the response usually has `Content-Type: application/hal+json`.
3. Read the relations in `_links`.
4. Identify repository collection relations and extract their corresponding `href`.
5. Call each `href` to confirm the collection resource and inspect the next-level links.
6. On the collection, check `search` if you need to discover query methods; on an item, check association links.

The list of relations and hrefs obtained from the root is runtime evidence of the collection resources exposed by Spring Data REST at the time of the call. This is a reliable way for clients to discover the API without hardcoding endpoint lists.

## 6. Why does a repository not appear?

Not every repository interface in the source code automatically becomes a link at the API root. Repository detection and export configuration determine which repositories are exposed.

For example, you can hide an entire repository using `exported = false`:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

This repository is not exposed as a collection resource through Spring Data REST, so the client should not expect a corresponding relation in the root.

In addition to annotations, check the following factors when a repository does not appear:

- Whether the repository interface is in a package scanned by Spring Data.
- Whether the repository is detected according to the configured `RepositoryDetectionStrategy`.
- Whether `@RepositoryRestResource(exported = false)` is placed on the repository.
- Whether a custom export configuration excludes the repository from the REST API.
- Whether the application is running with the expected profile, module, and base path configuration.
- Whether Spring Security blocks the root or collection request.

You should also distinguish repository export from individual method export. A repository collection may be detected, yet certain HTTP operations may not be supported if the corresponding underlying method does not exist or has been hidden with `@RestResource(exported = false)`. For example, Spring Data REST documentation specifies that a collection GET requires an exported `findAll(...)` method; otherwise, collection GET may return `405 Method Not Allowed`.

Therefore, seeing a link at the root proves that the collection resource is exposed, but it does not mean every HTTP method on the collection is available.

## 7. Distinguishing link types during discovery

| Where it appears | Common link | Meaning |
| --- | --- | --- |
| API root | Relations like `employees`, `orders` | Navigate to a repository collection resource. |
| API root | `profile` | API-level ALPS metadata. |
| Collection resource | `self` | Current collection, possibly with paging/sorting parameters. |
| Collection resource | `profile` | Metadata for the collection/domain resource. |
| Collection resource | `search` | Page listing exported query methods. |
| Search resource | Relation named after the query method | Navigate to a query method resource. |
| Item resource | `self` | Current item. |
| Item resource | Relation named after the association property | Navigate to an association resource. |

For example, if the root returns `employees`, the client navigates to the collection; the collection returns `search`, the client navigates to search; search returns `byDepartment`, the client continues following that query method's link. Each step relies on the relation and href from the current response.

Do not confuse `profile` with a collection path, `search` with a standalone repository, or an association link with a root repository link.

## 8. Calling the API root with tools and clients

### curl

~~~bash
curl -i   -H "Accept: application/hal+json"   http://localhost:8080/api
~~~

### HTTP client

In Postman, Insomnia, or REST Client:

- Method: `GET`
- URL: `http://localhost:8080/api`
- Header: `Accept: application/hal+json`

Open the response body and locate `_links`. If the tool displays a JSON tree, expand each relation and read the `href` field.

### JavaScript fetch

~~~javascript
const response = await fetch("http://localhost:8080/api", {
  headers: {
    Accept: "application/hal+json"
  }
});

if (!response.ok) {
  throw new Error(`API root returned HTTP ${response.status}`);
}

const root = await response.json();

for (const [rel, link] of Object.entries(root._links ?? {})) {
  console.log(rel, link.href);
}
~~~

The example above only prints relations and URLs for observation. In a real client, you should distinguish relations according to the API contract and the specific link being used, rather than treating every link in the root as a collection.

If a link object has `templated: true`, it is a URI template and the client must expand the template according to URI Template rules before calling it. Do not treat every `href` as a complete URL if HAL marks the link as templated.

## 9. Testing the API root with MockMvc

You can verify the root resource using Spring MVC Test. The example below asserts that the API root returns HTTP 200 and contains the `staff` link relation:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class RepositoryRootResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rootListsExportedEmployeeCollection() throws Exception {
        mockMvc.perform(get("/api")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.staff.href")
                    .value(containsString("/api/employees")));
    }
}
~~~

If using the default relation or another configuration, replace `staff` and the expected path according to your application's `@RepositoryRestResource`.

You can verify that a hidden repository does not appear:

~~~java
mockMvc.perform(get("/api")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.internalAudit").doesNotExist());
~~~

Tests should use the application's actual Spring Data REST configuration, including base path, repository detection strategy, and security. If the endpoint requires authentication, the test must provide an appropriate principal/role.

## 10. Troubleshooting common errors

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| GET `/` returns 404 | Spring Data REST has a different base path or context path | Check `spring.data.rest.base-path` and `server.servlet.context-path`; call the correct root. |
| GET `/api` returns 404 | Base path is not configured or the app does not serve Spring Data REST at that path | Check dependencies, configuration, and runtime mappings. |
| GET root returns 401/403 | Spring Security requires login or lacks permissions | Send credentials and check security rules. |
| Root lacks expected relation | Repository is not scanned, not detected, or marked non-exported | Check package scan, detection strategy, and `exported`. |
| Relation has a different name than expected | `collectionResourceRel` was customized | Read the actual key in `_links` and use `href`. |
| GET collection returns 405 | Collection may be exported, but the `findAll` read method is unavailable or hidden | Check repository methods and `@RestResource(exported = false)`. |
| Wrong host or scheme in links behind a reverse proxy | Proxy headers or forwarded-header configuration is misconfigured | Check proxy configuration and generated absolute URLs. |
| Query method not visible at root | Query methods are listed under the collection's `search` resource | Follow the collection link, then follow `search`. |

## 11. Principles for building HATEOAS clients

1. Start from the root URL provided by the application configuration.
2. Use `Accept: application/hal+json` to request the HAL representation.
3. Rely on the relation to understand the purpose of a link.
4. Follow the exact `href` returned; avoid constructing URLs from class names or relation names.
5. Discover search and associations at their respective resource levels.
6. Handle cases where a link does not exist, a request is rejected, or an endpoint returns an unsuccessful status code.
7. Do not assume fixed relation names, hostnames, ports, or base paths across environments.

This approach reduces the client's coupling to internal repository structures and makes it resilient to path or relation changes while the server maintains the hypermedia contract.

## References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): the “Resource Discoverability” section describes GET root URL, HAL `_links`, collection, item, and search resources.
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): configuring repository exposure and resource mappings.
- [Spring Data REST — Getting Started: Accessing JPA Data with REST](https://spring.io/guides/gs/accessing-data-rest): examples of HAL responses, collection links, and profile/search relations.
- [Spring Data REST — Spring project overview](https://spring.io/projects/spring-data-rest/): overview of repository resources, HAL, ALPS, and discoverability.
