# PersistentEntityResourceAssembler for Consistent Entity Representations

## Objectives

After this lesson, you will be able to:

- Explain what resource type PersistentEntityResourceAssembler produces and why Spring Data REST provides it.
- Use the assembler in a custom controller to return entities in a hypermedia format consistent with repository endpoints.
- Distinguish converting an entity into a representation from querying or saving an entity.
- Know when to use the assembler, when to use EntityModel/DTOs, and when to add business links.
- Inspect responses to detect cases where custom endpoints lose metadata or HAL links.

## 1. The Problem When Writing Custom Endpoints

Spring Data REST automatically publishes repositories as REST resources. An item endpoint such as GET /people/42 typically returns a representation containing entity data along with hypermedia links, such as self and association links.

In practice, applications often need custom endpoints to add business logic: returning an aggregated view, running a specialized query, or performing a processing step before returning results. If the controller returns the entity directly or builds JSON manually, the response may no longer be consistent with resources produced by Spring Data REST:

- Missing self links or association links that clients rely on for API discovery.
- Not following metadata and mappings configured in Spring Data REST for the entity.
- Differing from the repository endpoint's representation, forcing clients to handle two response shapes for the same entity type.
- Risking hardcoded string-concatenated URLs that break when the base path or resource path changes.

PersistentEntityResourceAssembler handles turning an entity into a representation using Spring Data REST's resource mechanism. The custom controller still decides querying and business logic; the assembler handles packaging the entity as a resource.

## 2. What Is PersistentEntityResourceAssembler?

PersistentEntityResourceAssembler resides in package org.springframework.data.rest.webmvc. It is a RepresentationModelAssembler<Object, PersistentEntityResource>, meaning it accepts a domain object and produces a PersistentEntityResource.

The commonly used method is:

~~~java
PersistentEntityResource resource = assembler.toModel(person);
~~~

PersistentEntityResource is a subclass of Spring HATEOAS EntityModel<Object>. In addition to entity content and links, it holds the PersistentEntity metadata for the represented entity. This metadata enables Spring Data REST to process the representation according to its persistent entity model.

The assembler is built upon infrastructure components such as:

- PersistentEntities: looks up metadata for persistent entities.
- Projector: handles projection mechanisms when building representations.
- Associations: provides association information and how associations are represented.
- SelfLinkProvider: provides the self link for an entity.

You do not need to instantiate these dependencies yourself or call the constructor manually in a typical controller. Spring Data REST supplies the appropriate assembler for a request through controller argument resolution.

Clearly distinguish these three responsibilities:

| Component | Responsibility |
|---|---|
| Repository | Finds, creates, updates, or deletes entities according to data logic |
| Controller/service | Coordinates requests, checks permissions, applies business rules, and decides the response |
| PersistentEntityResourceAssembler | Converts an existing entity into a PersistentEntityResource using Spring Data REST metadata and representation mechanics |

Calling the assembler does not execute repository queries, call save, or write data to the database. It simply builds a representation from the object you pass in.

## 3. Using the Assembler in a Repository REST Controller

To have a custom handler participate in Spring Data REST's endpoint space, use @RepositoryRestController. This annotation lets the controller use the API base path and Spring Data REST settings such as message converters, exception handling, and related configuration.

For example, suppose an application has a Person entity and repository:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;

    protected Person() {
    }

    public Person(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }
}
~~~

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Suppose we want to create a custom endpoint to return a Person after applying additional business logic:

~~~java
@RepositoryRestController
public class PersonDetailsController {

    private final PersonRepository personRepository;

    public PersonDetailsController(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @GetMapping("/people/{id}/details")
    public ResponseEntity<PersistentEntityResource> getDetails(
            @PathVariable Long id,
            PersistentEntityResourceAssembler assembler) {

        return personRepository.findById(id)
                .map(person -> {
                    // Perform validation or business processing here.
                    PersistentEntityResource resource =
                            assembler.toModel(person);

                    return ResponseEntity.ok(resource);
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Key points to understand:

1. The controller receives PersonRepository via constructor injection to query entities.
2. PersistentEntityResourceAssembler is declared directly as a method parameter. Spring Data REST registers an argument resolver to supply the assembler to handler methods.
3. findById(id) is responsible for finding the entity. If not found, the controller returns 404 Not Found.
4. assembler.toModel(person) creates a PersistentEntityResource from the located entity.
5. ResponseEntity.ok(resource) returns the resource through the message conversion mechanism configured by Spring Data REST.

Custom paths are written relative to the API base path. For example, if the base path is /api, the full endpoint will be /api/people/{id}/details. The actual path also depends on application configuration and repository mappings.

## 4. How Is the Response Different When Using the Assembler?

The response below only illustrates the structure you may encounter; actual relation names, URIs, and properties depend on entity mappings, repository configuration, projections, and application serialization settings.

~~~json
{
  "id": 42,
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42"
    }
  }
}
~~~

For entities with associations published by Spring Data REST, the representation can also contain links corresponding to those associations. Clients can use the self link to return to the item resource and association links to discover related resources.

The assembler helps custom endpoints use the same entity representation mechanism as Spring Data REST. However, do not assume every response has a fixed set of links. Which links appear depends on metadata, association exposure, mappings, access permissions, and application configuration.

This is especially useful when a custom endpoint returns the exact entity managed by repository endpoints. Clients can continue using familiar hypermedia navigation rather than learning a completely different response structure.

## 5. toModel and toFullResource

PersistentEntityResourceAssembler provides two notable methods:

- toModel(instance): the standard RepresentationModelAssembler method, creating a PersistentEntityResource for the passed object.
- toFullResource(instance): creates a PersistentEntityResource representing the full object using the Projector inside the assembler.

In most custom handlers, start with toModel. Only choose toFullResource when the response genuinely requires a full object representation per API semantics and you have checked its impact on projections, serialization, and publicly exposed fields.

Do not use toFullResource as a way to bypass data controls. Projection and serialization configuration can directly affect which fields clients see. Inspect actual responses with corresponding requests.

## 6. Handling Collections

The assembler also implements RepresentationModelAssembler, so you can use the collection-model creation capability inherited from Spring HATEOAS.

Example:

~~~java
@GetMapping("/people/active")
public ResponseEntity<CollectionModel<PersistentEntityResource>> getActivePeople(
        PersistentEntityResourceAssembler assembler) {

    List<Person> people = personRepository.findByActiveTrue();

    CollectionModel<PersistentEntityResource> resources =
            assembler.toCollectionModel(people);

    return ResponseEntity.ok(resources);
}
~~~

The example above assumes the repository has a findByActiveTrue method matching the entity. If the method does not yet exist, declare it in the repository or replace it with your application's actual query.

The key point is that every entity in the collection is converted into a PersistentEntityResource through the same assembler. This keeps each item's representation consistent with single-entity representations.

For collections with pagination, sorting, or custom metadata, choose a collection response approach matching the endpoint's contract. Do not drop page metadata or pagination links if clients depend on them.

## 7. Adding Links for Custom Business Actions

The assembler focuses on persistent entity representations and links managed by Spring Data REST. It does not automatically know every business action defined by your application.

For example, an endpoint might need to add a link to view a Person's transaction history. You can add the link after the assembler builds the resource:

~~~java
PersistentEntityResource resource = assembler.toModel(person);

resource.add(
    linkTo(methodOn(PersonDetailsController.class)
        .getHistory(person.getId()))
        .withRel("history")
);

return ResponseEntity.ok(resource);
~~~

This snippet assumes the controller has a getHistory(Long id) method with a corresponding mapping. Add the Spring HATEOAS imports:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

The history link is an application-added business link. It does not appear automatically just because the assembler received the entity.

If you need to add or transform links centrally across all responses of an entity type, consider an extension point such as ResourceProcessor. If you only need to add a link for one specific custom handler, adding the link to the representation in the controller can be clearer.

## 8. When Should You Use PersistentEntityResourceAssembler?

| Requirement | Appropriate Approach |
|---|---|
| Custom endpoint returning a Spring Data REST-managed entity | PersistentEntityResourceAssembler.toModel |
| Custom endpoint returning multiple entities of the same resource type | assembler.toCollectionModel |
| Response is a DTO with a custom structure, not a persistent entity representation | EntityModel<YourDto> or a plain DTO |
| Need to design all links and the representation manually | Spring HATEOAS RepresentationModel/EntityModel and a custom assembler |
| Want to add business links to an entity resource | Build the resource with the assembler, then add links |
| Want to centrally add links/metadata across multiple responses | Consider ResourceProcessor |

Do not use PersistentEntityResourceAssembler just because a controller has a Java object. It fits when the object belongs to a persistent entity model managed by Spring Data REST and you want to preserve Spring Data REST's hypermedia contract.

If an API needs a public schema different from the internal entity, create a DTO. Do not let database structure dictate the entire API contract solely because the assembler can convert entities into resources.

## 9. Common Pitfalls

- **Returning the entity directly:** the response may lack resource links or bypass Spring Data REST's representation mechanism. Use the assembler when an endpoint needs to return a persistent entity resource.
- **Instantiating the assembler via constructor:** the constructor requires multiple internal dependencies such as PersistentEntities, Projector, Associations, and SelfLinkProvider. Accept the framework-provided assembler in the handler method instead.
- **Using @RestController for Spring Data REST endpoints:** standard controllers may sit outside Spring Data REST's processing scope, leading to different base paths, message converters, and exception handling. Use @RepositoryRestController for handlers in the repository space.
- **Thinking the assembler saves the entity:** the assembler only builds representations. To modify data, execute business logic and call the appropriate repository/service.
- **Assuming every custom action automatically gets a link:** the assembler does not infer custom business actions. Add links using Spring HATEOAS or use ResourceProcessor when appropriate.
- **Using the assembler as a replacement for DTOs:** PersistentEntityResource still represents a persistent entity. If you need to hide or reshape fields, design an appropriate projection or DTO.
- **Skipping data access controls:** the assembler does not replace authorization. Enforce access checks in the controller/service and confirm that publicly serialized fields are safe.
- **Assuming responses have fixed links:** self links, association links, and relation names depend on actual configuration. Verify the responses produced by the application.

## 10. How to Test Custom Endpoints

When testing an endpoint that uses PersistentEntityResourceAssembler, verify both data and hypermedia:

1. Send GET to the custom endpoint with Accept: application/hal+json.
2. Verify status code, Content-Type, and expected properties.
3. Verify the self link has a URI pointing to the right item resource.
4. For entities with exposed associations, verify relation links match configuration.
5. Verify the base path when spring.data.rest.base-path is enabled.
6. Test requests with the projection parameter if the endpoint supports projections.
7. Test the non-existent entity case and verify the controller returns 404.
8. Verify authorization and ensure sensitive data does not appear unexpectedly.

Do not only check that the JSON contains an id field. The purpose of the assembler is to build a consistent resource, so tests must verify the links and hypermedia contract that clients actually rely on.

## 11. Self-Check Exercise

A custom handler finds a Person with id = 42. You need to return that entity with resource links following Spring Data REST's mechanism.

**Question 1.** Which method of PersistentEntityResourceAssembler is normally called to build the representation?

**Question 2.** Why should you accept the assembler as a method parameter instead of calling its constructor manually?

**Question 3.** If the repository returns Optional.empty(), what should the controller return?

**Question 4.** Does the assembler call save() or write the entity to the database?

**Question 5.** If you need to add a history link pointing to a custom action, does the assembler generate that link automatically?

**Answers:**

1. Call assembler.toModel(person).
2. Spring Data REST provides an assembler preconfigured with the system's metadata, projector, association handling, and self-link provider.
3. Return 404 Not Found.
4. No. The assembler only converts objects into representations.
5. No. The controller or a ResourceProcessor must add business links using Spring HATEOAS.

## 12. Key Takeaways

- PersistentEntityResourceAssembler is a RepresentationModelAssembler specialized in creating PersistentEntityResource from domain objects.
- PersistentEntityResource extends EntityModel and holds PersistentEntity metadata.
- Accept the assembler as a handler method parameter inside a custom @RepositoryRestController.
- Use toModel for typical representations; consider toFullResource when the full object is genuinely required.
- The assembler does not query, save, or mutate entities.
- Use EntityModel/DTOs when the API needs a separate contract; add business links using Spring HATEOAS or ResourceProcessor.
- Verify status, media type, self link, association links, projections, and authorization against actual responses.

## References

- Spring Data REST API — PersistentEntityResourceAssembler: https://www.springframework.org/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/PersistentEntityResourceAssembler.html
- Spring Data REST API — PersistentEntityResource: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/PersistentEntityResource.html
- Spring Data REST Reference — Overriding Spring Data REST Response Handlers: https://www.springframework.org/spring-data/rest/reference/5.0/customizing/overriding-sdr-response-handlers.html
