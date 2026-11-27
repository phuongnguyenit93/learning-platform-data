# Collection, Item, Association, and Search Resource Processors in Spring Data REST

## Objective

Spring Data REST automatically exports Spring Data repositories as REST APIs. Each response is typically a HAL hypermedia model: data is placed in the main body or `_embedded`, while navigable paths are placed in `_links`.

When you need to add a link, adjust a representation, or provide a path to custom functionality, you can register a Spring HATEOAS **RepresentationModelProcessor**. The processor receives the model built by Spring Data REST, processes it, and returns it before the response is serialized.

This article distinguishes four extension points: collection resources, item resources, association resources, and search resources. Examples use the modern APIs `RepresentationModelProcessor`, `EntityModel`, and `CollectionModel`. In older projects, API names may differ; the final section includes a migration note.

## 1. Four exported resource types

Suppose the application manages `Person`, where each person has one `Department` and multiple `Role` entities. The repository can be declared as follows:

~~~java
@RepositoryRestResource(path = "people", collectionResourceRel = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    Page<Person> findByLastNameContainingIgnoreCase(
            @Param("lastName") String lastName,
            Pageable pageable);
}
~~~

If Spring Data REST's base path is `/api`, typical URLs are:

| Resource type | Example URL | Meaning |
| --- | --- | --- |
| Collection | `GET /api/people` | List of people; supports pagination and sorting. `POST` creates a new person. |
| Item | `GET /api/people/42` | A specific person. Typically supports `GET`, `PUT`, `PATCH`, `DELETE`. |
| Association | `GET /api/people/42/department` | Follows a relationship from a person to a department. |
| Collection association | `GET /api/people/42/roles` | Follows a multi-valued relationship. |
| Search | `GET /api/people/search` | List of links to exported query methods. |
| Query method | `GET /api/people/search/by-last-name?lastName=Nguyen` | Executes a specific query. |

These resources are discovered via links. For example, the root resource has a link to `people`; the collection resource has a `search` link if the repository has query methods; an item resource has links named after relationship properties. Clients should follow the HAL links received instead of manually constructing URLs by convention.

A collection response might look like this in simplified form:

~~~json
{
  "_links": {
    "self": { "href": "http://localhost:8080/api/people" },
    "search": { "href": "http://localhost:8080/api/people/search" }
  },
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": { "href": "http://localhost:8080/api/people/42" },
          "department": {
            "href": "http://localhost:8080/api/people/42/department"
          }
        }
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

## 2. How does RepresentationModelProcessor work?

`org.springframework.hateoas.server.RepresentationModelProcessor<T>` is an extension point for processing a `RepresentationModel`. The `process(T model)` method receives the existing model, can add links or modify content appropriately, and must return the model.

Spring detects processors registered as beans, for example via `@Component` or `@Bean`. The generic type `T` indicates which kind of model the processor targets. Therefore, choose the exact model type returned by the endpoint:

- `EntityModel<T>`: model for a single entity.
- `CollectionModel<T>`: model for a collection of entities.
- `PagedModel<T>`: collection model with pagination metadata; this is a kind of collection model.
- `RepositorySearchesResource`: a dedicated model used by Spring Data REST for the page listing query methods.

Spring Data REST uses `PersistentEntityResource` to represent a repository entity. This type extends `EntityModel` while holding persistent entity metadata. Therefore, a processor for `EntityModel<Person>` is a common way to extend item resources.

A processor should only perform representation-layer work: adding links, appending affordances, or adjusting the output model. If you need to build a representation completely from scratch inside a controller, look at `RepresentationModelAssembler`; if you need to change queries or business logic, handle that in the corresponding repository/service/controller.

## 3. Processing item resources

An item resource is typically `EntityModel<Person>` (internally in Spring Data REST it may be `PersistentEntityResource`). The processor below adds an `export` link to every `Person` representation:

~~~java
@Component
public class PersonItemProcessor
        implements RepresentationModelProcessor<EntityModel<Person>> {

    @Override
    public EntityModel<Person> process(EntityModel<Person> model) {
        model.add(Link.of("/api/people/export").withRel("export"));
        return model;
    }
}
~~~

In a real application, the `/api/people/export` endpoint must exist and be protected according to the application's access policy. Prefer generating links with `WebMvcLinkBuilder.linkTo(methodOn(...))` or an appropriate link API when you need to avoid hard-coding host and path. If the application configures a base path, verify that the generated link includes that base path.

A processor can be scoped by entity type using generics as shown above. This avoids adding `Person`-specific links to representations of other domain types.

## 4. Processing collection resources

Collection resources are represented by `CollectionModel`; paginated results typically use `PagedModel`, which extends the collection model. You can add a collection-level link with the following processor:

~~~java
@Component
public class PeopleCollectionProcessor
        implements RepresentationModelProcessor<
                CollectionModel<PersistentEntityResource>> {

    @Override
    public CollectionModel<PersistentEntityResource> process(
            CollectionModel<PersistentEntityResource> model) {

        boolean containsPerson = model.getContent().stream()
                .anyMatch(resource -> resource.getPersistentEntity()
                        .getType().equals(Person.class));

        if (containsPerson) {
            model.add(Link.of("/api/people/summary").withRel("summary"));
        }

        return model;
    }
}
~~~

Here the processor inspects element metadata to add the link only when the collection contains `Person`. Because the check relies on elements, an empty collection cannot be identified this way. If you also need to handle empty pages, rely on the `self` link/configured mapping to identify the collection, or place custom logic in the corresponding endpoint.

Links added to the collection model sit at the collection level; they are not automatically added to each item. If you want each `Person` to have its own link, use the `EntityModel<Person>` processor from the previous section.

## 5. Processing association resources

An association is a sub-resource created from an entity's relationship property. For example:

~~~java
@Entity
public class Person {

    @ManyToOne
    @RestResource(path = "department", rel = "department")
    private Department department;

    @ManyToMany
    @RestResource(path = "roles", rel = "roles")
    private Set<Role> roles = new HashSet<>();
}
~~~

The path name and relation default to the property name; `@RestResource` on the property allows renaming them or setting `exported = false` to prevent exporting that association.

A one-to-one or many-to-one association returns a single-entity representation; a one-to-many or many-to-many association returns a collection representation. Consequently, processors handling associations typically still use the model types already covered:

- Single association: processor for `EntityModel<Department>` or the corresponding target entity type.
- Collection association: processor for `CollectionModel<PersistentEntityResource>` or the appropriate collection type.

**There is no separate public type named `AssociationResource` to use as a generic for all associations in the modern API.** Association representations reuse entity/collection models. Therefore, a processor targeting the target entity type can run for both that entity's item endpoint and an association endpoint returning that entity. If you need to distinguish by the exact association URL, rely on the self link/mapping or create a custom endpoint with dedicated logic; do not assume the generic type automatically distinguishes the two routes.

Association operations also differ by cardinality. `GET` reads the relationship; `PUT` binds the URI of the target resource; `POST` applies only to collection associations to add an item; `DELETE` removes the link. For `PUT` and `POST`, the standard payload is `text/uri-list`. A single-valued association cannot receive multiple URIs in the same `PUT` request.

If the goal is simply to rename the relationship link on the `Person` representation, configuring `@RestResource` on the property is usually clearer than writing a processor. Use a processor when you need representation behavior beyond the default metadata mapping.

## 6. Processing search resources

`GET /people/search` returns links to exported query methods. This is the search index page, not the result of a specific query. Spring Data REST uses `RepositorySearchesResource` for this representation.

You can register a dedicated processor and check the domain type via `getDomainType()`:

~~~java
@Component
public class PersonSearchProcessor
        implements RepresentationModelProcessor<RepositorySearchesResource> {

    @Override
    public RepositorySearchesResource process(
            RepositorySearchesResource model) {

        if (model.getDomainType().equals(Person.class)) {
            model.add(Link.of("/api/people/search/recent{?days}")
                    .withRel("recent"));
        }

        return model;
    }
}
~~~

The `/api/people/search/recent` path in the example must point to an actual custom search endpoint. In an application with a different base path, generate the URL from the controller mapping or corresponding configuration instead of keeping a hard-coded string.

For query methods declared directly on the repository, you usually do not need to add links manually: use `@RestResource(path = "by-last-name", rel = "byLastName")` to customize the path and relation. A search processor is useful when you want to advertise an additional link to custom search functionality, such as an endpoint implemented with `@BasePathAwareController`.

A processor for `RepositorySearchesResource` only processes the `/search` index page. The result of a query method can be an entity or a collection; in that case, the corresponding entity/collection processor is the place to add links to the results.

## 7. Registering multiple processors and scoping

Multiple processors can be registered in the same application context. Each processor should have a clear generic type and modify only the part of the representation it owns.

Some practical guidelines:

1. Use specific generics such as `EntityModel<Person>` or `RepositorySearchesResource` whenever possible; avoid overly broad processors that alter every response.
2. If using a general collection processor, filter by entity metadata or self link. Remember to handle empty collections.
3. Choose stable, unique relation names that are meaningful to clients. Do not override `self`, `search`, or default relations without a clear reason.
4. Only add links to endpoints that actually exist. Hypermedia links aid API discovery, but do not replace authorization checks on the endpoint.
5. Avoid expensive per-item database queries inside a processor. If needed data is unavailable, consider an assembler or a dedicated endpoint.
6. Test collection, item, single association, collection association, search index, and query result responses. The same representation type may be used across multiple routes.

## 8. Testing

You can use Spring MVC Test/MockMvc to call endpoints and verify the HAL JSON. Key assertions to verify:

- `GET /api/people`: collection-level links appear with the right relations; pagination metadata remains intact.
- `GET /api/people/42`: links added by the item processor appear in `_links`.
- `GET /api/people/42/department` and `GET /api/people/42/roles`: association representations remain in the right entity or collection shape and do not lose default links.
- `GET /api/people/search`: custom links appear only for the `Person` domain type.
- `GET /api/people/search/by-last-name`: the query method still accepts the expected parameters and returns the expected results.
- When changing the base path, custom links still point to the right endpoints.

Example verifying a relation with JSONPath:

~~~java
mockMvc.perform(get("/api/people/42")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.export.href").exists());
~~~

Test the content and status code of the target endpoint separately. A link appearing in JSON does not prove the endpoint is implemented or that the caller has permission to access it.

## 9. Legacy API vs. modern API

Older Spring Data REST/Spring HATEOAS projects may use the following type names:

| Legacy API | Modern API |
| --- | --- |
| `ResourceProcessor<T>` | `RepresentationModelProcessor<T>` |
| `Resource<T>` | `EntityModel<T>` |
| `Resources<T>` | `CollectionModel<T>` |
| `PagedResources<T>` | `PagedModel<T>` |
| `ResourceSupport` | `RepresentationModel<?>` |

Use the imports and generic types matching the Spring Boot/Spring Data version managed by your project. Do not mix legacy and modern APIs in the same example. When upgrading, check package imports, controller return types, and processor generic types.

## References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): describes collection, item, association, search, and query method resources.
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): customizing repository exposure and HTTP method exposure.
- [Spring Data REST — Integration](https://docs.spring.io/spring-data/rest/reference/integration.html): building links to collection, item, and search resources using `RepositoryEntityLinks`.
- [Spring Data REST API — RepositorySearchesResource](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RepositorySearchesResource.html): representation type for the search resource.
- [Spring HATEOAS API — RepresentationModelProcessor](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelProcessor.html): the `process(model)` contract for processing a representation model.