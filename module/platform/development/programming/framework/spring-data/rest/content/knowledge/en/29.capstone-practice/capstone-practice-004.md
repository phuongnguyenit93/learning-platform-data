# Adding Search, Paging, Sorting, and Projections in Spring Data REST

> Scope: Spring Data REST exports repositories as REST resources using Spring MVC and HAL. Examples use Spring Data JPA with `JpaRepository`; replace entities, packages, and repositories to match your project. Check the Spring Boot/Spring Data version managed by your BOM before applying configuration APIs.

## 1. Objective and API Discovery Flow

A practical collection API typically requires four capabilities working together:

- **Search**: filtering by business criteria and publishing appropriate query methods.
- **Paging**: returning a subset of results to avoid loading the entire dataset.
- **Sorting**: establishing a deterministic order when navigating across pages.
- **Projections**: selecting the shape of returned data for specific read needs.

Spring Data REST exposes a collection resource for a repository, such as `/people`, item resources like `/people/{id}`, and a search resource `/people/search` if the repository has exported query methods. Responses use HAL by default. Clients start from the root URL, follow relations in `_links`, then follow the `search` link and query method links. When a link is a URI template, clients populate the published variables rather than guessing URLs or constructing paths manually.

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
curl -i -H "Accept: application/hal+json" http://localhost:8080/people
curl -i -H "Accept: application/hal+json" http://localhost:8080/people/search
```

The `/people` path in the example depends on repository configuration. `@RepositoryRestResource(path=..., collectionResourceRel=...)` can customize the path and relation; the base path can also be configured. Use `self`, `search`, and server-returned links to keep clients compatible when paths change.

## 2. Declaring Searchable Query Methods

### 2.1. Repository and Finder Method

Spring Data REST creates a search resource from public exported query methods on the repository. Use derived queries when criteria are clear enough; method names must match domain type properties and query keywords supported by the store.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "people", collectionResourceRel = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "byLastName", rel = "byLastName")
    Page<Person> findByLastNameContainingIgnoreCase(
            @Param("q") String q, Pageable pageable);
}
```

With the repository above, the search resource publishes the `byLastName` relation, typically at `/people/search/byLastName`. `@Param("q")` names the query parameter `q`, so a sample request is:

```bash
curl -G "http://localhost:8080/people/search/byLastName" \
  -H "Accept: application/hal+json" \
  --data-urlencode "q=son" \
  --data-urlencode "page=0" \
  --data-urlencode "size=10" \
  --data-urlencode "sort=lastName,asc" \
  --data-urlencode "sort=id,asc"
```

`@RestResource` allows customizing the `path` and `rel` of a query method. If a method should not be published, mark it with `@RestResource(exported = false)`. Do not add finders purely for internal querying convenience if those methods should not become part of the public API.

### 2.2. Choosing the Appropriate Return Type

| Return Type | Meaning | When to Use |
| --- | --- | --- |
| `Page<T>` | Page content along with total element/page counts | UI needs total pages or total result count |
| `Slice<T>` | Page content and whether a next page exists | Forward-only pagination without needing totals |
| `List<T>` | List of results | Result set is already tightly bounded; no page metadata needed |

For query methods that require paging under the Spring Data REST contract, declare a `Pageable` parameter and return `Page` or `Slice`. `Page` typically triggers an additional count query to compute `totalElements` and `totalPages`; count queries can be expensive for complex queries. `Slice` only checks whether more data follows and usually avoids the count query. Do not return a large `List` expecting the server to paginate it automatically.

Examples of supported Spring Data method signatures:

```java
Page<Person> findByLastName(String lastName, Pageable pageable);
Slice<Person> findByCity(String city, Pageable pageable);
List<Person> findByLastName(String lastName, Sort sort);
```

Use only one corresponding special parameter per method. `Pageable` already includes sorting and page size, so do not declare `Sort` or `Limit` alongside `Pageable` in the same method.

## 3. Paging Collection and Search Results

Spring Data REST accepts default query parameters:

| Parameter | Meaning | Default |
| --- | --- | --- |
| `page` | Zero-based page number | `0` |
| `size` | Maximum items per page | `20` |
| `sort` | Property and sort direction | No explicit sort required |

Example first page of 5 items: `GET /people?page=0&size=5`. Second page: `GET /people?page=1&size=5`. The same parameters apply to query methods that support `Pageable`.

A paginated HAL response contains `_embedded` with the current page's resources, `_links.self`, and where applicable `_links.next`/`_links.prev`. The `page` object provides `size`, `totalElements`, `totalPages`, and `number`. `number` is also zero-based. The first page omits `prev`; the last page omits `next`.

Condensed example:

```json
{
  "_links": {
    "self": { "href": "http://localhost:8080/people{&sort,page,size}", "templated": true },
    "next": { "href": "http://localhost:8080/people?page=1&size=5{&sort}", "templated": true }
  },
  "_embedded": { "people": [ { "firstName": "An", "lastName": "Nguyen" } ] },
  "page": {
    "size": 5,
    "totalElements": 50,
    "totalPages": 10,
    "number": 0
  }
}
```

Clients should follow `next` and `prev` links to navigate instead of incrementing `page` and constructing URLs manually. When a user changes filters or sorting, restart from page `0`; previous/next links from the old query no longer represent the new criteria.

### 3.1. Limiting Page Size

Prevent clients from requesting overly large pages. You can configure default and maximum page sizes in `RepositoryRestConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestRepositoryConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config, CorsRegistry cors) {
        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
    }
}
```

Values `25` and `100` are examples only. Choose limits based on payload size, projection complexity, database load, and client constraints. Verify behavior when `size` exceeds the threshold with an integration test on your active version.

Offset-based pagination can become slow for very high `page` values because the database still has to skip many rows. For large tables requiring deep scrolling, consider store-appropriate keyset/scrolling strategies or a dedicated API; do not assume Spring Data REST's `page` query parameter automatically translates into cursor pagination.

## 4. Sorting by One or More Properties

The `sort` parameter uses the form `sort=property,direction`, where direction is `asc` or `desc`. Repeat the parameter to sort by multiple criteria; query string order determines priority:

```bash
curl "http://localhost:8080/people?sort=lastName,asc&sort=firstName,asc&sort=id,asc"
```

The example above sorts by last name, then first name, and finally ID. Adding a unique property as a tie-breaker such as `id` keeps ordering deterministic when multiple rows share the same first and last name. This is especially important when combined with paging to prevent records from shifting between pages due to non-deterministic order.

You can sort by top-level properties or nested properties using property path notation, if supported by the store. Sorting by an association exported as a link to a top-level resource is not directly supported. Property names must match the domain model, not arbitrary database column names.

Example using dynamic sorting in Spring Data code:

```java
Sort sort = Sort.by(Sort.Order.asc("lastName"))
        .and(Sort.by(Sort.Order.asc("firstName")))
        .and(Sort.by(Sort.Order.asc("id")));

Pageable pageable = PageRequest.of(0, 25, sort);
Page<Person> result = personRepository.findByLastNameContainingIgnoreCase("son", pageable);
```

`Pageable` already carries sort information. If a repository method encodes static ordering in its name such as `findByStatusOrderByCreatedAtDesc`, verify how static ordering interacts with dynamic sorting in your specific store; avoid making the API depend on two competing sort sources with unpredictable precedence.

## 5. Projections and Excerpts

### 5.1. Per-Request Projections

By default, Spring Data REST renders domain objects using the default representation. A projection is an interface annotated with `@Projection` declaring getters only for the properties to include in the response. Example:

```java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "summary", types = Person.class)
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
```

Place the interface in the same package as the domain type or a sub-package so Spring Data REST discovers it automatically. If needed, register it manually via `RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)`. The query parameter value is the `name` specified in `@Projection`, not the interface name.

Once the server publishes the projection, clients can request an item resource as follows:

```bash
curl -H "Accept: application/hal+json" \
  "http://localhost:8080/people/42?projection=summary"
```

A resource's `self` link may be rendered as a URI template containing the `projection` variable. The root ALPS `profile` link and the resource's ALPS descriptor also help clients discover available projections. Prefer server-returned metadata and links to determine available projection names.

### 5.2. Excerpt Projections for Collections

You can set a default projection for resources embedded in collections using `excerptProjection`:

```java
@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        excerptProjection = PersonSummary.class)
public interface PersonRepository extends JpaRepository<Person, Long> {
    // Query methods...
}
```

An excerpt projection is applied automatically to resource representations inside collections or related resources. It is not applied automatically when an item resource is fetched directly. When reading `/people/42`, the client must pass `?projection=summary` if it wants that projection. Consequently, the two access paths can produce different representations.

Excerpts keep collection previews concise and can inline select related data into the response. If a projection includes an association getter such as `Address getAddress()`, the address content can be embedded in the JSON while the association link remains available for navigation.

### 5.3. Projections Are Not a Security Boundary

Projections alter representations; they do not replace authorization. Spring Data REST warns that projections can expose data that would otherwise be hidden—for example, a getter in a projection can expose a property even if the entity marks it with `@JsonIgnore`. Therefore:

- Do not create projections containing passwords, tokens, secrets, internal flags, or personal data not meant for clients.
- Audit all getters, nested projections, and SpEL `@Value` expressions before exporting.
- Check collection excerpts, item projections, and search result projections alike.
- Use Spring Security and access policies at the appropriate layer to decide who may read a resource.
- Treat adding `excerptProjection` to an already released API as a representation change that can affect existing clients.

Projections only control which fields are serialized. They do not guarantee that the database query loads only those fields in every store, nor do they automatically prevent N+1 queries when getters traverse lazy associations. Profile SQL and test performance with representative data before assuming projections optimize queries.

## 6. Combining Search, Paging, Sorting, and Projections

A search request can combine business query parameters, paging, sorting, and projections:

```bash
curl -G "http://localhost:8080/people/search/byLastName" \
  -H "Accept: application/hal+json" \
  --data-urlencode "q=son" \
  --data-urlencode "page=0" \
  --data-urlencode "size=20" \
  --data-urlencode "sort=lastName,asc" \
  --data-urlencode "sort=id,asc" \
  --data-urlencode "projection=summary"
```

Only supply the `projection` variable if the query method resource publishes it in its URI template. Inspect the link from `/people/search` or the query method link instead of assuming every query method accepts every variable. When the response includes `_links.next`, follow that link to preserve required parameters for the next page.

A complete repository configuration can combine an excerpt and a finder as follows:

```java
@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        excerptProjection = PersonSummary.class)
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "byLastName", rel = "byLastName")
    Page<Person> findByLastNameContainingIgnoreCase(
            @Param("q") String q, Pageable pageable);
}
```

Here, the excerpt controls the default collection representation; the query method provides the filtered result set; `Pageable` handles page/size/sort; and the `projection` query parameter can select another representation if the endpoint's URI template advertises that variable.

## 7. Testing the HTTP Contract with MockMvc

Test at the HTTP layer to verify that repository methods are actually exported, HAL links are present, query parameters bind properly, and representations match expectations. The example below assumes three `Person` fixtures, a repository mapped at `/people`, collection relation `people`, and an entity with a matching constructor:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PersonRepositoryRestTest {

    @Autowired MockMvc mockMvc;
    @Autowired PersonRepository people;

    @BeforeEach
    void seed() {
        people.deleteAll();
        people.saveAll(List.of(
                new Person("An", "Nguyen"),
                new Person("Binh", "Nguyen"),
                new Person("Chi", "Tran")));
    }

    @Test
    void collectionSupportsPagingAndStableSorting() throws Exception {
        mockMvc.perform(get("/people")
                .param("page", "0")
                .param("size", "2")
                .param("sort", "lastName,asc")
                .param("sort", "id,asc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$._embedded.people").isArray())
            .andExpect(jsonPath("$._links.next.href").exists());
    }

    @Test
    void searchMethodBindsQueryAndPageable() throws Exception {
        mockMvc.perform(get("/people/search/byLastName")
                .param("q", "nguyen")
                .param("page", "0")
                .param("size", "1")
                .param("sort", "lastName,asc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.size").value(1))
            .andExpect(jsonPath("$._embedded.people").isArray());
    }

    @Test
    void itemCanSelectProjection() throws Exception {
        Person person = people.findAll().stream()
                .filter(p -> p.getFirstName().equals("An"))
                .findFirst().orElseThrow();

        mockMvc.perform(get("/people/{id}", person.getId())
                .param("projection", "summary")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.firstName").value("An"))
            .andExpect(jsonPath("$.lastName").value("Nguyen"));
    }
}
```

Add imports for `MockMvc`, `MediaTypes`, `BeforeEach`, `SpringBootTest`, `AutoConfigureMockMvc`, and the corresponding MockMvc/JSONPath/JUnit static imports. Adjust constructors, fixtures, paths, and relations to match your real model. If a test verifies an excerpt, call `GET /people` and assert `PersonSummary` fields in `$._embedded.people[0]`; when testing an item, pass the `projection` query parameter explicitly.

Tests should cover:

- Root resource publishes collection relations; collections publish `search` when query methods exist.
- Search resource lists exported query methods accurately; methods with `exported = false` do not appear.
- `page` is zero-based, `size` is bounded, and metadata plus `next`/`prev` update properly at the beginning/end of results.
- Multiple `sort` parameters establish the expected ordering; tie-breakers keep results stable across pages.
- Query methods bind `@Param` correctly and accept `Pageable`; results contain only matching records.
- Item projections and collection excerpts return expected fields without exposing sensitive fields.
- Changing `excerptProjection` does not inadvertently break response contracts relied upon by clients.

## 8. Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Missing `search` relation | Repository has no exported query methods or methods are hidden | Check public methods, `@RestResource(exported = false)`, and repository export config |
| `GET /people/search` returns `404` | Search resource has no available query methods | Check repository declaration and exported finders |
| Query method URL is wrong | Path/relation was customized or base path differs | Follow link from collection `search`, check `@RestResource(path, rel)`, and base path |
| Query returns all data or lacks page metadata | Method returns `List` or lacks `Pageable` | Use `Page<T>`/`Slice<T>` with a `Pageable` parameter |
| Page starts at the second set of results | Client sent `page=1` when page index is zero-based | Use `page=0` for the first page |
| Large `size` requests overload the database | No max page size set or client requests huge pages | Set `setMaxPageSize`, pick sensible defaults, and measure real load |
| Sort is not applied | Wrong property name, wrong direction, or sorting by association link | Use entity property names, `asc`/`desc`, and queryable sort fields |
| Records duplicate or disappear across pages | Non-deterministic sort when multiple records share values | Add a unique key as the final sort criterion; consider concurrent data mutations |
| Projection is not recognized | Interface missing `@Projection` or outside package scan | Place in domain package/sub-package or register manually |
| Excerpt does not appear on GET item | Excerpt only applies automatically to collections/related resources | Pass `?projection=<name>` on the item resource |
| Sensitive field appears in JSON | Projection getter exported an otherwise hidden field | Audit projections, nested getters, SpEL, and authorization |
| Paged query is slow despite fetching few rows | Count query, deep offset, joins, or N+1 during projection serialization | Profile SQL; consider `Slice`, indexes, fetch strategy, or a dedicated query API |

When debugging, check in this order: root HAL links → collection `search` link → query method URI template → query parameters and response metadata → SQL/query plan → projection representation. This separates discoverability, binding, paging, and serialization issues.

## 9. Official References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, search, and query method resources, HTTP methods, and parameters.
- [Spring Data REST — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): page/size/sort, `Pageable`, HAL `next`/`prev` links, and page metadata.
- [Spring Data REST — Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): `@Projection`, projection discovery, ALPS, excerpts, and item resource scope limits.
- [Spring Data REST — Getting started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): base path and configuration properties such as default/max page size.
- [RepositoryRestConfiguration Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html): `setDefaultPageSize`, `setMaxPageSize`, and exporter configuration.
- [Spring Data Commons — Defining query methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): derived queries, `Page`, `Slice`, `Pageable`, `Sort`, count queries, and offset limits.
- [Spring Data Commons — Paging, iterating, sorting and limiting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters): special parameters and choosing return types for large queries.