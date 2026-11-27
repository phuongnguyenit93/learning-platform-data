# Preserving Pagination, Projections, Headers, and Security When Implementing Custom Endpoints

## Objectives

When you need to add a custom endpoint to a Spring Data REST application, you may want to query or combine data in ways default repository resources do not support. However, custom endpoints still need to preserve the contracts clients rely on:

- **Pagination:** accept `page`, `size`, `sort` and return consistent metadata/navigation links.
- **Projections:** return only representations suited to the use case, without accidentally exposing the entire entity.
- **HTTP headers:** preserve Content-Type, Location, ETag, Cache-Control, and related headers when needed.
- **Security:** enforce authentication and authorization on custom endpoints, including per-resource or per-tenant access rules.

A handwritten endpoint does not automatically inherit every behavior of a repository resource. Deliberately design and verify every part of the contract.

## 1. Choosing the Right Controller Type

Spring Data REST provides `@RepositoryRestController` for custom controllers operating under the Spring Data REST base path.

For example, if the base path is `/api`, the controller can expose `/api/people/active`:

~~~java
@RepositoryRestController
public class PeopleCustomController {

    @GetMapping("/people/active")
    @ResponseBody
    public String activePeople() {
        return "custom response";
    }
}
~~~

`@RepositoryRestController` enables the controller to participate in Spring Data REST's web configuration and message converters. Methods must declare explicit mappings; use `@ResponseBody` or return `ResponseEntity` to specify the response body.

A regular `@RestController` can also be used for separate APIs. When choosing a controller, decide whether the endpoint belongs to Spring Data REST's base path/representation conventions or is a standalone API. Avoid creating two endpoints with the same path or unintentionally bypassing configured security rules.

## 2. Preserving Pagination with Pageable and Page

Do not load all data and slice the list manually with `subList`. That increases memory usage, bypasses datastore pagination capabilities, and easily produces incorrect metadata.

Accept `Pageable` from the request and let the repository execute paginated queries:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    Page<Person> findByActiveTrue(Pageable pageable);
}
~~~

Custom endpoint:

~~~java
@RepositoryRestController
public class PeopleCustomController {

    private final PersonRepository repository;

    public PeopleCustomController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/active")
    @ResponseBody
    public Page<Person> activePeople(Pageable pageable) {
        return repository.findByActiveTrue(pageable);
    }
}
~~~

Spring Data web support binds query parameters to Pageable:

~~~http
GET /api/people/active?page=0&size=20&sort=lastName,asc
~~~

- `page` is 0-indexed.
- `size` is the maximum number of items per page.
- `sort` specifies the property and sort direction.
- `Page<T>` holds content, page number, page size, total elements, and total pages.

When returning results to clients, choose an appropriate representation. For HAL APIs, Spring HATEOAS is commonly used to construct `PagedModel` and navigation links.

## 3. Returning PagedModel and HAL Navigation Links

Spring HATEOAS provides `PagedResourcesAssembler` to convert `Page<T>` into `PagedModel` containing metadata and navigation links.

Illustrative example:

~~~java
@RepositoryRestController
public class PeopleCustomController {

    private final PersonRepository repository;
    private final PagedResourcesAssembler<Person> pagedAssembler;

    public PeopleCustomController(
            PersonRepository repository,
            PagedResourcesAssembler<Person> pagedAssembler) {
        this.repository = repository;
        this.pagedAssembler = pagedAssembler;
    }

    @GetMapping("/people/active")
    @ResponseBody
    public PagedModel<EntityModel<Person>> activePeople(
            Pageable pageable) {

        Page<Person> page = repository.findByActiveTrue(pageable);
        return pagedAssembler.toModel(page);
    }
}
~~~

PagedModel can contain:

- `_embedded`: items in the current page.
- `_links.self`: link to the current page.
- `_links.first`, `prev`, `next`, `last`: navigation links when applicable.
- `page.size`, `page.totalElements`, `page.totalPages`, `page.number`: page metadata.

The exact shape of links depends on the current request, HATEOAS configuration, and assembler. If you need custom item links or representations, pass an appropriate `RepresentationModelAssembler` to `toModel`.

Do not calculate `totalPages` manually from the number of items on the current page. Use metadata returned by Page/repository; if the repository returns `Slice<T>`, total pages and total elements are not available as in Page.

## 4. Keeping Sorting Deterministic

When paginating, records must have a deterministic order. If a sort key can contain duplicates, add a unique property as the final tie-breaker.

Example:

~~~http
GET /api/people/active?page=0&size=20&sort=lastName,asc&sort=id,asc
~~~

If sorting only by `lastName`, multiple Persons sharing a last name may shift positions across requests. Unstable ordering can cause clients to see duplicate or skipped items while paging, especially when data changes.

Do not allow clients to sort arbitrarily on every internal property. Restrict sort properties according to your API contract and domain model. For complex queries, build a Sort allowlist or map public keys to permitted properties.

## 5. Projections Do Not Automatically Apply to Custom Endpoints

Spring Data REST supports projections on repository resources. For instance, a client can request:

~~~http
GET /api/people/42?projection=summary
~~~

Or a collection resource can use a configured excerpt projection. However, custom controllers do not automatically apply the same projection mechanism simply because the URL has a `projection` query parameter.

If a custom endpoint returns an entity directly, Jackson/HATEOAS may serialize properties per current configuration. This can make the response diverge from the repository endpoint's contract or accidentally expose fields that should stay private.

There are three common approaches:

1. Return an interface-based projection from the repository.
2. Map the entity to a dedicated DTO/response model.
3. Use `RepresentationModelAssembler` to construct representations and links matching the desired contract.

Interface projection example:

~~~java
public interface PersonSummary {

    Long getId();

    String getFirstName();

    String getLastName();
}
~~~

Repository returning a Page of projections:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    Page<PersonSummary> findByActiveTrue(Pageable pageable);
}
~~~

Custom endpoint using that projection:

~~~java
@GetMapping("/people/active")
@ResponseBody
public Page<PersonSummary> activePeople(Pageable pageable) {
    return repository.findByActiveTrue(pageable);
}
~~~

This example focuses on return data types. If HAL pagination links are needed, combine `Page<PersonSummary>` with `PagedResourcesAssembler<PersonSummary>` and an appropriate assembler.

### Supporting a Dynamic projection Parameter

If a custom endpoint accepts a `projection` query parameter, define the contract explicitly:

- Accept only projection names from an allowlist.
- Map each name to a specific DTO/projection.
- Return a clear error when an unsupported name is passed.
- Never accept arbitrary class names from clients for reflection or instantiation.
- Ensure no projection exposes fields outside the principal's read permissions.

Example:

~~~java
switch (projection) {
    case "summary" -> return summaryView(pageable);
    case "contact" -> return contactView(pageable);
    default -> throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST,
        "Unsupported projection"
    );
}
~~~

A projection only shapes the response. It does not replace authorization or write validation.

## 6. Using DTOs When Custom Endpoints Have Their Own Contract

DTOs fit when an endpoint needs to aggregate data, rename fields, or expose only a specific set of fields.

Example:

~~~java
public record PersonSummaryResponse(
        Long id,
        String displayName,
        boolean active
) {
}
~~~

Service or mapper converts domain objects into DTOs:

~~~java
private PersonSummaryResponse toSummary(Person person) {
    return new PersonSummaryResponse(
        person.getId(),
        person.getFirstName() + " " + person.getLastName(),
        person.isActive()
    );
}
~~~

For pagination, preserve Page metadata when mapping content:

~~~java
Page<PersonSummaryResponse> responsePage =
    personPage.map(this::toSummary);
~~~

`Page.map` preserves page information while transforming each element. You can then use an appropriate assembler to build PagedModel. Avoid constructing a new Page manually with a guessed total count or losing sort/page metadata.

Response DTOs also decouple the API contract from persistence entities. If the domain model changes, custom endpoints can keep response shapes stable by updating only the mapper.

## 7. Preserving HTTP Statuses and Headers

When a custom controller returns responses, use `ResponseEntity` to control status, body, and headers.

Example GET HAL response:

~~~java
@GetMapping("/people/active")
public ResponseEntity<PagedModel<EntityModel<PersonSummary>>> activePeople(
        Pageable pageable) {

    Page<PersonSummary> page = repository.findByActiveTrue(pageable);
    PagedModel<EntityModel<PersonSummary>> body =
        pagedAssembler.toModel(page);

    return ResponseEntity.ok()
        .contentType(MediaTypes.HAL_JSON)
        .body(body);
}
~~~

Several headers carry special significance:

| Header | Role | When to Preserve |
|---|---|---|
| `Content-Type` | Describes the response media type | HAL JSON, JSON, or other media types |
| `Location` | URI of the newly created or target resource | POST creating a resource |
| `ETag` | Validator for caching or conditional requests | When the API supports optimistic concurrency |
| `Last-Modified` | Timestamp when representation/resource changed | When the API supports conditional GET |
| `Cache-Control` | Caching policy | Public, private, or sensitive data |
| `Vary` | Request headers affecting representation | Content negotiation or header-dependent responses |
| `Link` | Additional hypermedia relations | When the API uses Link headers |

### POST Needs Location

When a custom endpoint creates a resource, the response should provide the resource URI via `Location`:

~~~java
URI location = linkTo(methodOn(PersonController.class)
        .getPerson(saved.getId()))
        .toUri();

return ResponseEntity.created(location)
        .body(response);
~~~

The example uses Spring HATEOAS link builder; replace the controller and method with your application's actual route. Do not hardcode paths when the base path or resource mappings can change.

### ETag and Conditional Requests

If an endpoint supports conditional updates, return an appropriate ETag and validate `If-Match` before writing. The ETag must correspond to the true representation/version and be generated by the server from a trustworthy source.

Do not fabricate ETags arbitrarily from a field that does not reflect the full resource. Do not ignore `If-Match` merely because a custom endpoint uses a DTO. When using `@Version` at the persistence layer, ensure custom update paths still pass through version checks and handle optimistic locking.

### Cache-Control and Sensitive Data

Do not copy caching policies from public endpoints onto endpoints returning per-user data. For personal or sensitive data, consider `Cache-Control: no-store` or an appropriate private policy.

If responses vary by `Accept`, `Accept-Language`, or other headers, set `Vary` appropriately. Avoid caching responses under a key that fails to distinguish principals when content differs by permission.

## 8. Securing Custom Endpoints

Custom endpoints still sit inside Spring Security's request pipeline when deployed in the same application, but rules must cover the exact paths and HTTP methods.

Example URL-level security:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/people/active")
                .hasAuthority("people:read")
            .requestMatchers(HttpMethod.POST, "/api/people/import")
                .hasAuthority("people:import")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

This is only a matcher example. When using `@RepositoryRestController`, verify the path after applying the Spring Data REST base path and the ordering of `SecurityFilterChain` beans in the application. A mismatched pattern can cause an endpoint to fall into a catch-all or unintended rule.

### Method Security

You can enforce permissions on service or controller methods:

~~~java
@EnableMethodSecurity
@Configuration
public class MethodSecurityConfiguration {
}
~~~

~~~java
@PreAuthorize("hasAuthority('people:read')")
public Page<PersonSummary> findActivePeople(Pageable pageable) {
    return repository.findByActiveTrue(pageable);
}
~~~

`@PreAuthorize` takes effect only when method security is enabled and the method is invoked through its Spring proxy. Do not rely on self-invocation and assume the annotation will still be enforced.

### Per-Resource Permission Checks

Access permissions can depend on owner, tenant, or state:

~~~java
@PreAuthorize("@personAccess.canRead(authentication, #personId)")
public PersonSummaryResponse getPerson(Long personId) {
    // Load and return authorized representation.
    return null;
}
~~~

Method security enables enforcing per-resource policies. Implement the `personAccess` bean with real ownership/tenant verification logic. Never rely on hiding links, projections, or UI buttons to protect an endpoint.

### Do Not Let Custom Endpoints Bypass Policy

If repository endpoints have dedicated security rules, custom endpoints must receive equivalent rules. Check all of the following:

- Collection GET and item GET.
- POST, PUT, PATCH, and DELETE.
- Search/aggregation endpoints.
- Export/import endpoints.
- Association or action endpoints.
- Per-tenant or per-owner requests.

If custom endpoints call shared services, place authorization and critical invariants at the service/domain boundary so other entry points are protected as well.

## 9. Keeping Hypermedia Links Consistent

Spring Data REST encourages clients to discover URIs via links rather than constructing paths manually. Custom endpoints should return clear links when clients need to follow resources or navigate onward.

With PagedModel, `self`, `next`, and `prev` links must preserve the relevant query parameters:

- Current page.
- Page size.
- Sort order.
- Filters or search criteria.
- Other parameters affecting the result set.

If a client moves from `page=0` to `page=1`, the `active=true` filter and sort must be preserved. If links keep only page/size and drop filters, the next page could return a different dataset.

Do not hardcode base URLs in assemblers when the application runs behind a reverse proxy or uses a context path. Use link builders/HATEOAS infrastructure and verify forwarded headers per deployment configuration.

## 10. Content Negotiation and Response Formats

Custom endpoints need to handle `Accept` consistently with the API contract:

~~~http
GET /api/people/active
Accept: application/hal+json
~~~

If an endpoint only returns HAL JSON, set the corresponding content type. If multiple media types are supported, configure converters and mappings explicitly. Avoid returning plain JSON from an endpoint where clients expect HAL links or PagedModel.

Request bodies also require the proper `Content-Type`. When accepting DTOs, validate the body and return errors following the same error response conventions as the rest of the API.

Do not assume `@RepositoryRestController` automatically turns every return value into HAL. Return types, annotations, message converters, and Spring Data REST configuration determine how responses are serialized.

## 11. Workflow for Implementing a Custom Endpoint

When adding an endpoint, follow this sequence:

1. Determine whether the endpoint belongs under the Spring Data REST base path or a separate API.
2. Choose `@RepositoryRestController` or an appropriate controller.
3. Define the response contract: entity, projection, DTO, or resource model.
4. Accept `Pageable` and let the repository handle pagination.
5. Preserve Page metadata; use PagedResourcesAssembler when HAL navigation is needed.
6. Expose only appropriate fields; do not rely on automatic projection query parameters.
7. Set status, Content-Type, Location, ETag, and Cache-Control as needed.
8. Add URL-level and method/resource-level authorization.
9. Preserve filter/sort/page parameters in hypermedia links.
10. Write integration tests for pagination, projections, headers, and security.

## 12. Testing the Custom Endpoint Contract

Test each aspect independently:

- **Paging:** `page`, `size`, `sort` bind properly; totalElements/totalPages and links are accurate.
- **Stable ordering:** two items sharing a sort key have deterministic ordering via a tie-breaker.
- **Projection/DTO:** responses contain only published fields; internal fields do not appear.
- **Content negotiation:** HAL clients receive the expected media type and structure.
- **Headers:** POST includes Location; ETag/Cache-Control/Vary follow the contract.
- **Conditional writes:** stale If-Match values are rejected if the endpoint supports optimistic concurrency.
- **Authorization:** users lacking permission are rejected when calling the URL directly.
- **Resource policy:** users cannot access items belonging to another tenant/owner.
- **Error responses:** validation and business errors maintain consistent statuses/representations.

Use MockMvc or WebTestClient depending on your stack. Test real HTTP responses rather than only unit-testing controller methods.

## 13. Common Pitfalls

- **Custom endpoint returns List and slices pages manually.** Causes heavy data loads and loses metadata; use Pageable and Page.
- **Returns Page when clients need HAL navigation.** Use PagedModel/PagedResourcesAssembler and verify links.
- **Has a projection query parameter and assumes projections run automatically.** Custom controllers must select projections/DTOs and mappings themselves.
- **Serializes entities directly.** Can leak fields or create unstable response contracts; use projections/DTOs when appropriate.
- **Keeps body while omitting headers.** Can lose Location, ETag, or cache semantics.
- **Generates ETags arbitrarily.** Validators must reflect version/representation and conditional writes must be verified.
- **Hides links to secure endpoints.** Clients can call URLs directly; enforce access with Spring Security.
- **Checks permissions only by path.** Per-record/per-tenant permissions require dedicated policies.
- **Paginates without deterministic sorting.** Can cause duplicate or missing items when browsing pages.
- **Next link drops filters.** Subsequent pages may query a different dataset.
- **Assumes @RepositoryRestController produces HAL for every return type.** Verify converters, annotations, and actual media types.

## 14. Key Takeaways

- Custom endpoints must deliberately preserve the contracts provided out of the box by default repository resources.
- Use Pageable and Page for paginated queries; use PagedModel/assembler when HAL navigation is needed.
- Sorting should be deterministic and restricted to exposed properties.
- Repository projections/excerpts do not automatically apply to custom controllers; use explicit projections/DTOs.
- Use ResponseEntity to control statuses and headers such as Content-Type, Location, ETag, and Cache-Control.
- Conditional writes must check If-Match and server-side versions.
- Secure custom endpoints with URL rules, method security, and per-resource permission checks where needed.
- Hypermedia links must preserve page, size, sort, and filters.
- Test pagination, representations, headers, and security using HTTP integration tests.

## References

- [Spring Data REST Reference — Customizing and extending](https://docs.spring.io/spring-data/rest/reference/customizing-and-extending.html)
- [Spring Data REST Reference — Events and repository resources](https://docs.spring.io/spring-data/rest/reference/)
- [Spring HATEOAS Reference — Pagination](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Framework Reference — ResponseEntity and MVC controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
