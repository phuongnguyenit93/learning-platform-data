# Building Repository Links with RepositoryEntityLinks in Spring Data REST

## Objectives

When writing custom controllers or adding hypermedia links to responses, applications often need to generate URLs pointing to collection, item, paginated, or search resources exported by Spring Data REST.

You could concatenate strings like `/api/people/42`, but that breaks easily when a repository changes its path, collection relation, base path, paging parameter names, or identifier conversion. Spring Data REST provides `RepositoryEntityLinks` to build links based on exported repository metadata.

Common use cases:

- Creating a link to a domain type's collection resource.
- Creating a link to an item resource by identifier.
- Creating a link to a collection with Pageable.
- Retrieving all search links of a repository.
- Creating a link to a specific query method by relation.
- Adding these links to Spring HATEOAS `EntityModel` or `CollectionModel`.

This lesson covers the `RepositoryEntityLinks` API, injecting the bean, using overloads for paging/sorting, integrating with HAL and custom controllers, and limitations to keep in mind.

## 1. Why Shouldn't You Concatenate URLs Manually?

Suppose a repository is declared as:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

With base path `/api`, the collection resource may be:

~~~text
/api/people
~~~

An item with ID 42 may be:

~~~text
/api/people/42
~~~

If the team later changes:

- The base path from `/api` to `/v1`.
- The collection path from `people` to `persons`.
- The collection relation via `collectionResourceRel`.
- Pagination or sort parameter names.
- How backend identifiers are represented via a converter.

Hardcoded URL strings in custom controllers may no longer match the resources produced by the exporter.

Example of error-prone URL concatenation:

~~~java
String href = "/api/people/" + person.getId();
~~~

This snippet assumes the base path, collection path, and identifier format. It does not read repository metadata from Spring Data REST.

`RepositoryEntityLinks` is designed to create links to exported resources. It uses Spring Data REST configuration and resource mappings to construct links, so custom code does not have to duplicate the exporter's URL rules.

## 2. What Is RepositoryEntityLinks?

`RepositoryEntityLinks` is in package:

~~~java
import org.springframework.data.rest.webmvc.support.RepositoryEntityLinks;
~~~

It is the Spring Data HATEOAS `EntityLinks` implementation specialized in creating links for domain types managed by Spring Data REST.

Its Javadoc describes it as capable of creating `Link` instances for domain classes managed by Spring Data REST. The current API includes these main method groups:

| Method | Result | Purpose |
| --- | --- | --- |
| `linkToCollectionResource(type)` | `Link` | Link to the collection resource |
| `linkToItemResource(type, id)` | `Link` | Link to an item resource |
| `linkToPagedResource(type, pageable)` | `Link` | Link to a collection with pagination info |
| `linksToSearchResources(type)` | `Links` | All links to exported search resources |
| `linksToSearchResources(type, pageable)` | `Links` | Search links expandable with Pageable |
| `linksToSearchResources(type, sort)` | `Links` | Search links expandable with Sort |
| `linkToSearchResource(type, relation)` | `Link` or null | Link to a query method by relation |
| `linkToSearchResource(type, relation, pageable)` | `Link` or null | Search link with Pageable |
| `linkToSearchResource(type, relation, sort)` | `Link` | Search link with Sort |
| `linkFor(type)` | `LinkBuilder` | Low-level API for further path customization |

Typed link creation methods such as collection, item, page, and search should be preferred. Only use `linkFor(...)` when you need to build a custom path not covered by the specialized API.

## 3. Injecting RepositoryEntityLinks via Constructor

Spring Data REST registers `RepositoryEntityLinks` in the ApplicationContext. You can inject this bean into a custom controller or service:

~~~java
@RepositoryRestController
public class PersonNavigationController {

    private final RepositoryEntityLinks entityLinks;

    public PersonNavigationController(RepositoryEntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }
}
~~~

Or inject it into a representation-handling component:

~~~java
@Component
public class PersonLinkFactory {

    private final RepositoryEntityLinks entityLinks;

    public PersonLinkFactory(RepositoryEntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }
}
~~~

Constructor injection makes dependencies explicit and easy to replace with mocks in unit tests.

You do not need to instantiate `new RepositoryEntityLinks(...)` manually. The implementation's constructor requires many internal components such as repository metadata, resource mappings, REST configuration, paging template variables, and backend ID converters. Use the bean provided by Spring Data REST.

If Spring cannot find the bean, check that Spring Data REST dependencies and auto-configuration are loaded. Do not create a manual instance with incomplete configuration because links may not reflect the application's actual resource mappings.

## 4. Creating Links to Collection Resources

Use `linkToCollectionResource` when you need the collection URL for a domain type:

~~~java
Link peopleLink =
        entityLinks.linkToCollectionResource(Person.class);
~~~

Example returning the link in a response:

~~~java
@GetMapping("/navigation/people")
ResponseEntity<EntityModel<Map<String, String>>> peopleNavigation() {

    Link people = entityLinks
            .linkToCollectionResource(Person.class)
            .withRel("people");

    EntityModel<Map<String, String>> model =
            EntityModel.of(Map.of("description", "List of users"), people);

    return ResponseEntity.ok(model);
}
~~~

In this example:

- `Person.class` identifies the domain type.
- Spring Data REST resolves the corresponding repository/resource mapping.
- The link is built using the exported collection path.
- `withRel("people")` attaches the appropriate relation for the custom response being built.

If the repository changes its path via `@RepositoryRestResource(path = "persons")`, the code still requests the link for `Person.class`; there is no need to edit URL strings in the controller.

Note: `RepositoryEntityLinks` only supports domain types with a corresponding repository resource managed by Spring Data REST. An arbitrary DTO class does not become a repository resource just by passing that class to a method.

## 5. Creating Links to Item Resources

Use `linkToItemResource` to create a link to a single item:

~~~java
Link personLink =
        entityLinks.linkToItemResource(Person.class, 42L);
~~~

In a custom controller, you can use the ID retrieved from an entity:

~~~java
@GetMapping("/people/{id}/navigation")
ResponseEntity<EntityModel<PersonNavigation>> navigation(
        @PathVariable Long id) {

    Person person = personRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));

    Link itemLink = entityLinks
            .linkToItemResource(Person.class, person.getId());

    Link collectionLink = entityLinks
            .linkToCollectionResource(Person.class)
            .withRel("people");

    EntityModel<PersonNavigation> model =
            EntityModel.of(
                    new PersonNavigation(person.getId(), person.getDisplayName()),
                    itemLink,
                    collectionLink);

    return ResponseEntity.ok(model);
}
~~~

Response record:

~~~java
public record PersonNavigation(Long id, String displayName) {
}
~~~

`linkToItemResource` takes the domain type and an identifier. The identifier must match the repository/backend ID mapping for that domain type. Let Spring Data REST and backend converters handle URL encoding/identifier mapping; do not manually URL-encode the ID into a string before passing it in.

Do not confuse link creation with entity loading. `linkToItemResource` builds a URI from metadata and an ID; it does not replace `findById`, does not verify that the entity exists, and does not check user access permissions.

If you need to ensure the resource exists, perform a repository lookup and authorization check before including the link in the response.

## 6. Creating Links to Paginated Collections

When you want to create a link for a collection with a specific `Pageable`, use `linkToPagedResource`:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "lastName"));

Link firstPage = entityLinks
        .linkToPagedResource(Person.class, pageable);
~~~

Imports:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
~~~

The method accepting `Pageable` can expand paging/sorting template variables using the provided values. If there is no Pageable, you can pass `null` to create an unexpanded paginated collection link.

Example creating a link to the second page:

~~~java
Pageable secondPage = PageRequest.of(
        1,
        20,
        Sort.by("lastName").ascending());

Link pageLink = entityLinks
        .linkToPagedResource(Person.class, secondPage);
~~~

Page numbers start at 0, so `PageRequest.of(1, 20)` refers to the second page.

The query parameter names used in the link follow Spring Data REST's paging configuration. If the application renames `page`, `size`, or `sort` in `RepositoryRestConfiguration`, let `RepositoryEntityLinks` generate links instead of assembling query strings manually.

A page link only describes a URL; it does not execute a query. To retrieve data, you still need to call the repository or follow that link over HTTP.

## 7. Retrieving All Search Links of a Repository

If a repository exports multiple query methods, you can retrieve all search links:

~~~java
Links searchLinks =
        entityLinks.linksToSearchResources(Person.class);
~~~

Example repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastNameIgnoreCase(
            @Param("lastName") String lastName);

    @RestResource(path = "active", rel = "activePeople")
    Page<Person> findByActiveTrue(Pageable pageable);
}
~~~

The repository's search resource advertises finder links according to the configured mappings. `linksToSearchResources` returns a `Links` collection, which can be added directly to a representation:

~~~java
CollectionModel<EntityModel<Person>> model =
        CollectionModel.of(personModels);

for (Link searchLink :
        entityLinks.linksToSearchResources(Person.class)) {
    model.add(searchLink);
}
~~~

Not every repository has a search resource. If no query methods are exported, the link collection may be empty. Having a method in the Java interface is not enough; the method must be discovered and exported by Spring Data REST, and not hidden with `@RestResource(exported = false)`.

## 8. Creating a Link to a Specific Query Method

If you only need a single finder link, use `linkToSearchResource` with the domain type and relation:

~~~java
Link byLastName = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("byLastName"));
~~~

Import:

~~~java
import org.springframework.hateoas.LinkRelation;
~~~

The relation must match the relation exported for the query method:

~~~java
@RestResource(
    path = "by-last-name",
    rel = "byLastName"
)
List<Person> findByLastNameIgnoreCase(
        @Param("lastName") String lastName);
~~~

There are three distinct names to keep apart:

| Element | Example | Role |
| --- | --- | --- |
| Java method | `findByLastNameIgnoreCase` | Method name in the repository |
| Search path | `by-last-name` | Path segment of the query endpoint |
| Relation | `byLastName` | Relation name appearing in HAL |

The current API takes `LinkRelation`, so you can construct it with `LinkRelation.of("byLastName")`. Do not mistakenly pass the path `by-last-name` or the Java method name if the relation was customized to another value.

`linkToSearchResource` can return `null` if no matching search link exists. Handle this case:

~~~java
Link searchLink = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("byLastName"));

if (searchLink != null) {
    model.add(searchLink);
}
~~~

Do not dereference the result immediately without checking for null, especially when repositories may vary their export configuration across profiles or modules.

## 9. Creating Search Links with Pageable or Sort

Search link overloads support paging and sorting:

~~~java
Pageable pageable = PageRequest.of(
        0,
        25,
        Sort.by("lastName").ascending());

Link searchPage = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("activePeople"),
        pageable);
~~~

Or pass only Sort:

~~~java
Link sortedSearch = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("byLastName"),
        Sort.by(Sort.Direction.DESC, "createdAt"));
~~~

If you want to retrieve all search links expanded with Pageable:

~~~java
Links expandedSearchLinks =
        entityLinks.linksToSearchResources(Person.class, pageable);
~~~

Or with Sort:

~~~java
Links sortedSearchLinks =
        entityLinks.linksToSearchResources(
                Person.class,
                Sort.by("lastName").ascending());
~~~

Template expansion populates the link with the supplied paging/sorting values. Business parameters of the query method, such as `lastName`, may still need to be supplied when the client invokes the endpoint. Do not assume that passing Pageable automatically fills every finder business parameter.

When a query method takes a Pageable parameter, the server uses page/size/sort parameter names per the current Spring Data REST configuration. Inspect the returned link to see the URI template and remaining variables to supply.

## 10. Combining RepositoryEntityLinks with Spring HATEOAS Models

Spring HATEOAS provides models to represent resources and collections with links:

- `EntityModel<T>`: single content/resource with links.
- `CollectionModel<T>`: collection of resources with links.
- `RepresentationModel<T>`: base type for hypermedia representations.

Example building an item representation:

~~~java
Person person = personRepository.findById(id).orElseThrow();

EntityModel<Person> model = EntityModel.of(
        person,
        entityLinks.linkToItemResource(Person.class, person.getId()),
        entityLinks.linkToCollectionResource(Person.class)
                .withRel("people"));
~~~

Example building a collection representation:

~~~java
List<EntityModel<Person>> people = personRepository.findAll()
        .stream()
        .map(person -> EntityModel.of(
                person,
                entityLinks.linkToItemResource(Person.class, person.getId())))
        .toList();

CollectionModel<EntityModel<Person>> model =
        CollectionModel.of(
                people,
                entityLinks.linkToCollectionResource(Person.class));

for (Link link : entityLinks.linksToSearchResources(Person.class)) {
    model.add(link);
}
~~~

In this example:

- Each Person has a link to its own item resource.
- The CollectionModel has the collection link.
- Search links are added so clients can discover query endpoints.

If a collection contains large datasets, do not call `findAll()` to assemble lists manually. Use repository pagination or a query method accepting Pageable, then build a representation appropriate for Page/Slice. `RepositoryEntityLinks` builds links; it does not optimize queries or paginate collections automatically.

## 11. Combining with Custom Controllers

A custom controller can use `RepositoryEntityLinks` to provide navigation responses or attach links to repository resources in business responses.

~~~java
@RepositoryRestController
public class PersonNavigationController {

    private final RepositoryEntityLinks entityLinks;
    private final PersonRepository repository;

    public PersonNavigationController(
            RepositoryEntityLinks entityLinks,
            PersonRepository repository) {
        this.entityLinks = entityLinks;
        this.repository = repository;
    }

    @GetMapping("/people/{id}/navigation")
    ResponseEntity<EntityModel<PersonNavigation>> navigation(
            @PathVariable Long id) {

        Person person = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));

        EntityModel<PersonNavigation> model = EntityModel.of(
                new PersonNavigation(person.getId(), person.getDisplayName()),
                entityLinks.linkToItemResource(Person.class, person.getId()),
                entityLinks.linkToCollectionResource(Person.class)
                        .withRel("people"));

        Link byLastName = entityLinks.linkToSearchResource(
                Person.class,
                LinkRelation.of("byLastName"));

        if (byLastName != null) {
            model.add(byLastName);
        }

        return ResponseEntity.ok(model);
    }
}
~~~

With `@RepositoryRestController`, routes sit within Spring Data REST's URI space and base path. If you use a regular MVC `@RestController`, you can still inject `RepositoryEntityLinks` to create links to repository resources, though the controller's own mappings belong to Spring MVC and require their own route configuration.

When building links to a custom MVC controller, Spring HATEOAS `linkTo(methodOn(...))` is the better fit. `RepositoryEntityLinks` is intended for resources exported by Spring Data REST.

## 12. RepositoryEntityLinks and Custom Resource Mappings

Spring Data REST lets you change the collection path and relation:

~~~java
@RepositoryRestResource(
    path = "persons",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

When using `RepositoryEntityLinks`:

~~~java
Link collection =
        entityLinks.linkToCollectionResource(Person.class);
~~~

The link is generated using the repository's mapping instead of forcing the default pluralized class name.

This is especially useful when an application has:

- A collection path different from the domain type name.
- Custom relations.
- Different base paths across environments.
- Renamed paging parameters.
- Custom backend ID converters.

Do not infer URLs from Java class names or relation names. Let Spring Data REST metadata determine the path and use the returned links.

If a repository is hidden with `@RepositoryRestResource(exported = false)`, there is no public collection resource to link to as a repository endpoint. Verify that a repository is actually exported before building navigation to it.

## 13. Identifiers and Custom ID Mapping

`linkToItemResource` accepts a domain type and an ID object:

~~~java
Link item = entityLinks.linkToItemResource(Person.class, personId);
~~~

For repositories with `Long` IDs, pass a Long value. For `UUID` IDs, pass the corresponding UUID. Do not prepend slashes, URL-encode, or convert the value into a path string beforehand.

Spring Data REST uses backend ID conversion and resource mapping to build item URIs. When the application uses custom ID mapping, such as `BackendIdConverter` or `EntityLookup`, make sure the passed identifier conforms to the rules used by the repository/exporter.

Distinguish between:

- Database primary key: the ID stored in the datastore.
- Backend ID: the value the repository/store uses to identify an entity.
- Public item URI identifier: the identifier segment exposed in URIs published by the REST exporter.

By default, these values usually align. If you have customized the URI identifier, do not assume they are always identical. Verify generated links and corresponding GET item URLs in integration tests.

## 14. When to Use linkFor Instead of Typed Methods?

`RepositoryEntityLinks` also provides:

~~~java
LinkBuilder builder = entityLinks.linkFor(Person.class);
~~~

`linkFor` returns the low-level `LinkBuilder` API. You can append path segments or parameters when needed:

~~~java
Link searchRoot = entityLinks.linkFor(Person.class)
        .slash("search")
        .withRel("search");
~~~

However, if your goal is to create standard collection/item/page/search resource links, prefer the typed methods:

~~~java
entityLinks.linkToCollectionResource(Person.class);
entityLinks.linkToItemResource(Person.class, id);
entityLinks.linkToPagedResource(Person.class, pageable);
entityLinks.linkToSearchResource(
        Person.class, LinkRelation.of("byLastName"));
~~~

Specialized methods express intent clearly and leverage resource mappings. Use `linkFor` when you need a custom path without a corresponding method; do not recreate collection or item URLs by appending paths when a typed API already exists.

For custom MVC routes, use:

~~~java
linkTo(methodOn(PersonNavigationController.class)
        .navigation(id))
        .withRel("navigation");
~~~

Spring HATEOAS `linkTo(methodOn(...))` fits linking to controller methods. `RepositoryEntityLinks` fits linking to repository resources.

## 15. Checking Whether a Domain Type Is Supported

`RepositoryEntityLinks` implements the `Plugin<Class<?>>` interface and provides:

~~~java
boolean supported = entityLinks.supports(Person.class);
~~~

You can use this check in code handling multiple domain types:

~~~java
if (!entityLinks.supports(Person.class)) {
    throw new IllegalStateException(
            "Person does not have a supported repository resource");
}
~~~

This is a metadata-level repository support check; it does not confirm that a specific item exists. To verify an item, a repository lookup is still required.

Do not use `supports` as a substitute for authorization or runtime exposure checks on individual endpoints. It only indicates whether `RepositoryEntityLinks` can build links for a domain type.

## 16. Testing Links with MockMvc

Verify that generated links match the actual base path and repository mappings. For example:

~~~java
@SpringBootTest(properties = "spring.data.rest.base-path=/api")
@AutoConfigureMockMvc
class RepositoryEntityLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void customNavigationContainsRepositoryLinks() throws Exception {

        mockMvc.perform(get("/api/people/42/navigation")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.people.href")
                    .value(containsString("/api/people")));
    }
}
~~~

The test above assumes the custom controller returns a self link and a collection link with relation `people`, and that a Person fixture with ID 42 exists.

You can check item links:

~~~java
Link itemLink =
        entityLinks.linkToItemResource(Person.class, 42L);

assertThat(itemLink.getHref())
        .contains("/api/people/42");
~~~

If the repository uses a custom path:

~~~java
@RepositoryRestResource(
    path = "persons",
    collectionResourceRel = "people"
)
interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

then assertions must reflect the path `persons`, not the default `people`.

Check search relations:

~~~java
Link searchLink = entityLinks.linkToSearchResource(
        Person.class,
        LinkRelation.of("byLastName"));

assertThat(searchLink).isNotNull();
~~~

If a query method is not exported or the relation does not match, the link can be null. Tests should verify both presence and absence of search links if repository exposure can vary by profile.

Additionally, test:

- Custom collection paths.
- Item identifiers and custom ID mappings.
- Base paths per profile.
- Configured paging and sort parameter names.
- Search links with custom relations.
- Repositories with `exported = false`.
- That clients can successfully GET generated links.
- Custom controllers do not hardcode host, port, or base path.

## 17. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cannot inject RepositoryEntityLinks | Spring Data REST auto-configuration not loaded or missing dependency | Check dependencies and ApplicationContext |
| Cannot create link for domain type | Type has no exported repository resource | Check repository scanning and exported flag |
| Link has default path instead of custom path | Concatenating URLs manually or passing wrong domain type | Use RepositoryEntityLinks with the right domain class |
| Search link returns null | Relation does not exist, query method is not exported, or rel is misspelled | Check @RestResource(rel = ...) and search metadata |
| Using Java method name fails to find link | API looks up by LinkRelation/rel, not necessarily method name | Use the actual published relation |
| Item link has wrong ID | Passing wrong identifier type or value | Pass ID matching repository/backend mapping |
| URL has duplicated base path | Custom code prepends /api while exporter already manages base path | Use links generated by RepositoryEntityLinks |
| Search link lacks paging parameters | Pageable/Sort not passed or link remains a template | Use the appropriate overload and inspect the URI template |
| Collection link is right but GET returns 404 | Resource path is right, but repository/item is unexported or blocked by security | Check exporter mapping and authorization |
| Using RepositoryEntityLinks for a custom MVC method | It links to repository resources, not arbitrary controller mappings | Use Spring HATEOAS linkTo(methodOn(...)) |
| Link exists but item does not exist | Link generation performs no repository lookup | Look up entity and check permissions before returning links |
| Collection response is too large | Calling findAll to build all EntityModels manually | Use Pageable/Page/Slice and build a paged representation |

## 18. Adoption Workflow

1. Identify domain types that have repositories exported by Spring Data REST.
2. Inject `RepositoryEntityLinks` via constructor.
3. Use `linkToCollectionResource` for collections and `linkToItemResource` for items.
4. Use `linkToPagedResource` when needing page links with Pageable.
5. Use `linksToSearchResources` to discover all finder links.
6. Use `linkToSearchResource` with the exact LinkRelation to retrieve a single finder link.
7. Handle null results from search link lookups.
8. Add links to EntityModel/CollectionModel.
9. Use `linkTo(methodOn(...))` for custom MVC controller routes.
10. Test paths, relations, base path, ID mappings, and actual link GET requests.

## References

- [Spring Data REST — Integration: Programmatic Links](https://docs.spring.io/spring-data/rest/reference/integration.html): examples injecting RepositoryEntityLinks and building collection, item, page, and search resource links.
- [Spring Data REST 5.1.2 API — RepositoryEntityLinks](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/RepositoryEntityLinks.html): current method signatures, Pageable/Sort overloads, LinkRelation, and Link/Links return types.
- [Spring HATEOAS — EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html): representing a single resource with hypermedia links.
- [Spring HATEOAS — CollectionModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html): representing a collection resource with links.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, search resources and resource path/rel customization.
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): configuring repository mappings, base path, and item resource URIs.
