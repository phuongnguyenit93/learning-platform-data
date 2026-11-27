# How RepositoryRestHandlerMapping Selects a Request Handler

## 1. Role of RepositoryRestHandlerMapping

In Spring MVC, `DispatcherServlet` does not guess which controller should run. It queries `HandlerMapping` objects in the configured priority order. Each `HandlerMapping` checks whether a request falls within its scope:

- Matching handler found: returns the handler (usually a `HandlerMethod`).
- No matching handler found: returns `null`, letting `DispatcherServlet` try the next `HandlerMapping`.

`RepositoryRestHandlerMapping` is the `HandlerMapping` dedicated to Spring Data REST. It extends `BasePathAwareHandlerMapping`, which is built on Spring MVC's `RequestMappingHandlerMapping`. Its job is to find an internal Spring Data REST controller method matching the URL and accept the request only if the repository segment in the URL corresponds to an exported repository.

A distinction to keep in mind: this class selects the **controller method that handles the HTTP request**. It does not directly invoke `findById()`, `save()`, or a repository query method. Resolving the repository and executing the data operation happen in subsequent steps.

## 2. Two layers of conditions to accept a request

The selection process can be understood through two consecutive layers of checks.

### Layer 1 — Does the request match a Spring Data REST handler method?

During application initialization, the inherited mechanism from `RequestMappingHandlerMapping` scans controller beans and registers methods with suitable mappings. Specifically, `RepositoryRestHandlerMapping` restricts the types of controllers considered handlers: the current implementation checks for the `@RepositoryRestController` annotation (via `AnnotatedElementUtils.hasAnnotation`).

Because of this, internal controllers such as `RepositoryEntityController`, `RepositorySearchController`, and `RepositoryPropertyReferenceController` can participate in handling their corresponding URL groups. Methods are registered using Spring MVC annotations such as `@RequestMapping`, `@GetMapping`, `@PostMapping`, etc.

When a request arrives, the inherited logic searches for a matching mapping based on `RequestMappingInfo` conditions, typically including:

- The URL path and method pattern.
- HTTP method: GET, POST, PUT, PATCH, DELETE, ...
- Query parameters or headers declared in the mapping.
- `consumes` and `produces` conditions, which relate to `Content-Type` and `Accept`.

If no method matches, the result is `null`.

### Layer 2 — Is the repository segment in the URL exported?

Even when a `HandlerMethod` is found, `RepositoryRestHandlerMapping` still verifies whether the URL actually belongs to an exported repository.

In the current implementation, the main logic inside `lookupHandlerMethod` proceeds as follows:

1. Call `super.lookupHandlerMethod(lookupPath, request)` to find a method using Spring MVC's mapping mechanism.
2. If no method is found, return `null`.
3. Use `RepositoryRestConfiguration.getBasePath()` to strip the base path from the URL and obtain the repository lookup path.
4. If the request is for the root resource (no repository segment), keep the matched handler. For example, a request to the base path `/api` can be handled by the controller serving the root resource and API discovery links.
5. If there is a repository segment, extract the first segment of the repository lookup path. For example, `/people/search/byLastName` has `people` as its first segment.
6. Call `ResourceMappings.exportsTopLevelResourceFor(repositoryBasePath)`. If that segment is not a currently exported top-level resource, return `null`; otherwise, accept the `HandlerMethod`.

This check prevents a generic Spring Data REST route from mistakenly claiming a URL merely because the URL resembles a repository route. `ResourceMappings` is the metadata source indicating which paths represent exported repository resources.

## 3. Example: a search request in a repository

Suppose the application has the following repository:

```java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends CrudRepository<Person, Long> {

    @RestResource(path = "byLastName")
    List<Person> findByLastName(@Param("lastName") String lastName);
}
```

The application configures the base path as `/api`. The client sends:

```http
GET /api/people/search/byLastName?lastName=Nguyen
Accept: application/hal+json
```

The handler selection flow can be read as follows:

| Step | Value or check | Result |
|---|---|---|
| Base path | `/api` | Stripped from the path used to identify the repository |
| Repository lookup path | `/people/search/byLastName` | Remaining path |
| Repository base path | `people` | First segment |
| ResourceMappings | `exportsTopLevelResourceFor("people")` | Must return `true` |
| Request mapping | Search pattern and HTTP method GET | Selects the matching method in `RepositorySearchController` |
| Result | `HandlerMethod` | Proceeds to the handler execution step |

At the mapping step, Spring Data REST chooses the generic method on `RepositorySearchController` to handle search requests. Afterward, Spring Data REST argument resolvers and processing components use the repository metadata to identify the `people` resource, locate the `byLastName` search resource, bind the `lastName` parameter, and invoke the corresponding query method.

In other words, `RepositoryRestHandlerMapping` identifies **the endpoint type and controller method**; it has not yet executed `PersonRepository.findByLastName("Nguyen")`.

## 4. When a repository is not exported

Suppose the URL is:

```http
GET /api/people/42
```

If `people` is an exported repository, the request can match the item retrieval method in `RepositoryEntityController`, and then pass the `ResourceMappings` check.

If the repository's path is changed to `persons`, or export is disabled, then `exportsTopLevelResourceFor("people")` returns `false`. Even though a generic pattern might match the URL shape, `RepositoryRestHandlerMapping` still returns `null`. `DispatcherServlet` continues trying the remaining `HandlerMapping` instances; another Spring MVC controller can handle that URL if it has a matching mapping.

This is why two outcomes must be distinguished:

- **No method mapping found:** no controller method matches the request path and conditions.
- **Method mapping matched, but repository is not exported:** a method matches the shape, but Spring Data REST declines the URL because the repository segment is invalid or not exported.

Both cases can cause this mapping to return `null`. The final response (for example 404) also depends on other `HandlerMapping` instances and the application's error-handling configuration.

## 5. Configurations affecting the result

| Configuration or metadata | Effect |
|---|---|
| `spring.data.rest.base-path` or `RepositoryRestConfiguration` | Defines the API prefix, for example `/api` |
| `@RepositoryRestResource(path = "people")` | Defines the public segment of the collection resource |
| `@RepositoryRestResource(exported = false)` | Disables exporting the repository; the segment is not accepted as a top-level resource |
| Repository detection strategy | Affects which repositories are discovered and exported |
| `@RestResource(path = "byLastName")` | Sets the path for the search resource corresponding to the query method |
| `@RestResource(exported = false)` on a method | Hides the search resource; that search URL is not exposed as a public endpoint |
| `@RepositoryRestController` | Marks a custom controller as falling within Spring Data REST's mapping scope |
| HTTP method, `Accept`, `Content-Type`, and mapping conditions | Affects which method matches the request |

When a method does not declare its own `produces`, `RepositoryRestHandlerMapping` also customizes media type conditions using the configured default media type and media types supported by Spring Data REST, including HAL JSON and JSON. Therefore, the `Accept` header can also affect mapping selection.

The order among `HandlerMapping` instances is determined by their `order` property. When two mappings in an application have overlapping URLs, inspect the actual order and mapping conditions instead of looking only at controller names.

## 6. Distinguishing components in the processing flow

| Component | Responsibility |
|---|---|
| `DispatcherServlet` | Dispatches requests and queries `HandlerMapping` instances in order |
| `RepositoryRestHandlerMapping` | Finds a Spring Data REST `HandlerMethod` and confirms the repository path is exported |
| `ResourceMappings` | Provides metadata about resource paths and export status |
| `HandlerAdapter` | Invokes the selected `HandlerMethod` |
| Spring Data REST argument resolvers | Resolves repository, resource, ID, and method parameter information |
| Controller and repository invoker | Handles the endpoint and performs the operation on the repository |

One way to read the overall flow:

```text
HTTP request
    |
    v
DispatcherServlet
    |
    v
RepositoryRestHandlerMapping
    |
    +-- Find HandlerMethod by RequestMappingInfo
    |       |
    |       +-- No match ------------------------> return null
    |
    +-- Strip base path, extract repository segment
            |
            +-- No repository segment -----------> accept root handler
            |
            +-- Repository not exported ---------> return null
            |
            +-- Repository exported -------------> return HandlerMethod
                                                     |
                                                     v
                                                HandlerAdapter
                                                     |
                                                     v
                                          Argument resolvers / Controller
                                                     |
                                                     v
                                              Repository operation
```

## 7. How to trace routing errors

When a Spring Data REST URL does not reach the expected controller, check in order:

1. Confirm whether the request goes through the right `DispatcherServlet` and the right base path.
2. Confirm whether the internal or custom controller falls under `@RepositoryRestController` scope and whether the method mapping is registered.
3. Compare the request's HTTP method, path, query parameters, headers, `consumes`, and `produces` against the mapping.
4. Extract the first segment after the base path and verify whether a repository is exported under that exact path.
5. Check `@RepositoryRestResource`, `@RestResource`, and the repository detection strategy if an endpoint or search resource is hidden.
6. If another Spring MVC controller uses the same prefix, check the `order` of the `HandlerMapping` instances and the specific mappings on that controller.

You can enable DEBUG/TRACE logging for Spring MVC mapping classes to inspect registered request mappings and handler lookup. In development environments, the Actuator `/actuator/mappings` endpoint (if enabled and properly secured) also helps inspect active mappings.

## 8. Conclusion

`RepositoryRestHandlerMapping` selects a handler based on two questions: **does a Spring Data REST controller method match the request, and is the repository in the first segment after the base path actually exported?** Only when both conditions hold does the mapping return a `HandlerMethod`. Resolving the concrete repository and executing the query or CRUD operation occur afterward.

## References

- [Javadoc — RepositoryRestHandlerMapping](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestHandlerMapping.html)
- [Source code — RepositoryRestHandlerMapping.java](https://github.com/spring-projects/spring-data-rest/blob/main/spring-data-rest-webmvc/src/main/java/org/springframework/data/rest/webmvc/RepositoryRestHandlerMapping.java)
- [Spring Data REST — Adding Spring Data REST to an Existing Spring MVC Application](https://docs.spring.io/spring-data/rest/reference/customizing/adding-sdr-to-spring-mvc-app.html)