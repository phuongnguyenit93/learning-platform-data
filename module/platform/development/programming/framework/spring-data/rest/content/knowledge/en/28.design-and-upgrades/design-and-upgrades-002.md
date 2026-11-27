# Reducing Coupling Between Entity Structure and HTTP Contracts in Spring Data REST

## Objectives

Spring Data REST can directly export repositories and render entities as JSON/HAL. While this helps build APIs quickly, it also makes it easy for the domain or persistence structure to become part of the HTTP contract that clients rely on.

When renaming attributes, splitting entities, changing relationships, or adding internal fields, API responses can change accordingly. To reduce coupling, choose the right level of abstraction for each endpoint: projections when only read shaping needs adjustment, resource configuration when paths and relations need stability, or DTOs with dedicated controllers/services when an HTTP contract independent of entities is required.

After this lesson, you will be able to:

- Recognize the risks of exposing entities directly.
- Use projections to control read representations.
- Stabilize Spring Data REST paths and relation names.
- Separate request/response DTOs from entities for APIs needing dedicated contracts.
- Choose how to export repositories and test compatibility.

## 1. Why Do Entities and HTTP Contracts Easily Become Tightly Coupled?

Suppose the domain model has an entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;

    private String internalNote;

    // constructors, getters, and setters
}
~~~

When the repository is exported by Spring Data REST, clients can read the representation of Person directly. The properties emitted by the serializer can become something that frontends, mobile apps, or integrating systems depend on.

This creates several risks:

- Renaming **firstName** to **givenName** can prevent clients from reading the old field.
- Merging **firstName** and **lastName** into a single **fullName** property can alter the JSON schema.
- Splitting one entity into multiple entities or changing JPA relationships can alter how associations are represented.
- Adding an internal field can accidentally expose data not meant for clients in responses.
- Renaming a repository path or finder relation can invalidate URLs that clients are calling.

Two models must be distinguished:

- **Domain/persistence model:** reflects business concepts, relationships, and how the application stores data.
- **HTTP contract:** reflects the data, operations, URLs, statuses, and media types that clients are permitted to rely on.

The two models may look similar in a small application, but you should not assume they must always remain identical. The HTTP contract should be managed as a public interface with its own lifecycle.

## 2. Using Projections to Control Read Representations

Spring Data REST supports projections to limit or shape the properties displayed in a representation. This is a suitable option when you still want to use repository resources but only need a specific read view.

Example creating a projection for Person:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(
    name = "personSummary",
    types = Person.class
)
public interface PersonSummary {

    Long getId();

    String getFirstName();

    String getLastName();
}
~~~

The projection above exposes only the properties needed for a list view. The **email** and **internalNote** fields are not included in this representation.

Register the projection as the default excerpt for the collection resource:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Clients can also request a projection by name if Spring Data REST detects it:

~~~http
GET /people/42?projection=personSummary
Accept: application/hal+json
~~~

Key points to understand:

- A **Projection** shapes the returned representation; it does not change the entity or database schema.
- **excerptProjection** selects the default projection for elements within a collection representation.
- The **projection** query parameter lets clients choose an exported projection.
- The projection name is part of the API if clients invoke it directly, so it should remain stable or have a transition plan.

Projections help reduce client dependency on the entire entity, but they do not completely decouple the HTTP contract from the domain model. The interface still references the Person type and its property names. When the entity changes structure, the projection may need updating.

Projections are also not an authorization boundary. Do not rely on a projection omitting a field as a replacement for server-side authorization. Sensitive data must be protected by appropriate access policies and tested across all endpoints that could return that data.

## 3. Stabilizing Paths, Relations, and Endpoint Names

Beyond JSON representations, URLs and relation names are also part of the HTTP contract.

Spring Data REST lets you customize the path and collection relation on a repository:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

You can customize the path and relation of a finder method:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    @RestResource(
        path = "by-email",
        rel = "byEmail"
    )
    Optional<Person> findByEmail(String email);
}
~~~

The finder can be accessed via the corresponding search resource, for example:

~~~http
GET /people/search/by-email?email=person@example.com
Accept: application/hal+json
~~~

Using stable relation names allows clients to discover links through HAL instead of constructing URLs from Java class or method names.

However, customizing paths and relations only stabilizes resource identification. It does not automatically decouple the entity representation from the JSON contract. If domain properties are exported directly, property changes can still affect responses.

When changing a path or relation currently used by clients, treat it as an API change requiring a compatibility roadmap. Where possible, keep the old link during a transition period or publish the new endpoint before removing the old one.

## 4. Using DTOs and Separate Controllers When an Independent Contract Is Needed

If an API needs custom field names, nested structures, validation, or specific write rules, create request/response DTOs. The controller accepts DTOs, calls a service, and maps to the domain model. Clients do not need to know how entities are stored.

Example response DTO:

~~~java
public record PersonResponse(
        Long id,
        String fullName
) {
}
~~~

Request DTO:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record CreatePersonRequest(
        @NotBlank String firstName,
        @NotBlank String lastName,
        @Email String email
) {
}
~~~

Illustrative controller:

~~~java
@RestController
@RequestMapping("/api/v1/people")
public class PersonApiController {

    private final PersonService personService;

    public PersonApiController(PersonService personService) {
        this.personService = personService;
    }

    @GetMapping("/{id}")
    public PersonResponse getById(@PathVariable Long id) {
        return personService.getResponse(id);
    }

    @PostMapping
    public ResponseEntity<PersonResponse> create(
            @Valid @RequestBody CreatePersonRequest request) {

        PersonResponse created = personService.create(request);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(created);
    }
}
~~~

The service is responsible for business orchestration, accessing the repository, and mapping entities to DTOs. The controller does not need to expose entities directly:

~~~text
HTTP request
    |
    v
CreatePersonRequest
    |
    v
Controller
    |
    v
Application service
    |
    +--> Business validation
    +--> Repository / domain model
    +--> Mapping
    |
    v
PersonResponse
    |
    v
HTTP response
~~~

In the example, the client receives **fullName** even though the entity still stores **firstName** and **lastName** separately. Later, the domain can change how names are stored while keeping the response DTO unchanged if the business meaning remains the same.

To prevent Spring Data REST from simultaneously exporting the repository with the entity representation, you can hide the repository from REST export:

~~~java
@RepositoryRestResource(exported = false)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

The repository remains a Spring bean for services to inject and use; setting **exported = false** prevents Spring Data REST from publishing the corresponding repository resource. Check related endpoints and associations to ensure no unintended access paths remain.

If you still need Spring Data REST for other resources, you can keep them and only build custom controllers for contracts that need independence. There is no need to convert the entire application to a single API style.

## 5. Controlling Write Data and Associations

Putting an entity directly in the request body can make clients depend on persistence attributes and accidentally allow updating fields that the business does not want exposed.

A creation request DTO should contain only the data the client is allowed to submit. For updates, a separate DTO can be used with only the modifiable fields. The service determines which entity is modified, checks permissions, applies business rules, and saves the changes.

For example, clients are allowed to send **firstName**, **lastName**, and **email**, but must not send **internalNote**, **createdAt**, or internal moderation statuses. An allowlist DTO clearly restricts the input contract.

Similarly, do not assume every JPA relationship should be exposed as an association resource. An association may be a domain implementation detail. Relationships not intended for clients can be hidden with appropriate export configuration/annotations, for example:

~~~java
@ManyToOne
@RestResource(exported = false)
private InternalProfile internalProfile;
~~~

When the API needs to manipulate relationships, explicitly decide whether clients should link an existing resource, send an identifier, or execute a business use case. Separate DTOs and services let you design operations in business terms rather than forcing clients to manipulate the entity graph directly.

Do not use DTOs to bypass permission checks. The service must still verify that the caller is authorized to read or modify the specific entity and association.

## 6. Choosing a Solution Based on Need

| Need | Suitable Approach | Limitations to Remember |
|---|---|---|
| Only want to hide some fields when reading | Projection | Still coupled to domain type and property names |
| Want collections to have a default representation | excerptProjection | Primarily shapes collection excerpts |
| Want stable URLs and relations | @RepositoryRestResource, @RestResource | Does not automatically decouple JSON schema from entity |
| Want input with allowlist and custom validation | Request DTO + controller/service | Must manage mapping and HTTP behavior manually |
| Want responses unchanged when entities are refactored | Response DTO + controller/service | Requires contract testing and version maintenance |
| Want to stop exporting a repository directly | exported = false | Clients must use another published API |

You can apply these incrementally. Start with projections if the goal is solely read representation. When you need control over write contracts, business rules, or independent response structures, move that use case to dedicated DTOs and controllers/services.

## 7. Managing HTTP Contract Changes

A stable contract does not mean the API never changes. What matters is that changes are intentional and compatible.

Practical principles:

- **Prefer additive changes:** adding optional fields or adding links is usually less disruptive than renaming or removing fields in use.
- **Do not reuse old names for new meanings:** older clients may misinterpret the data.
- **Provide a deprecation period:** when a field or endpoint must change, announce the replacement and maintain the old path for an appropriate transition window.
- **Version on breaking changes:** use URI versioning or a consistent system versioning strategy, such as **/api/v1/** and **/api/v2/**.
- **Preserve HTTP semantics:** clearly define status codes, media types, validation errors, and behavior when a resource does not exist.
- **Prefer HAL links:** clients should follow server-provided links rather than constructing URLs from class structures or repository names.
- **Do not leak internal data:** check items, collections, projections, associations, and custom endpoints.

Do not bump the API version just because an internal entity is refactored. If DTOs and external contracts do not change, clients do not need to know that persistence details have changed.

## 8. Testing Contracts Instead of Only Testing Entities

When entities and HTTP contracts are separated, you must directly test the responses clients receive. Service unit tests remain useful, but they do not replace integration tests for HTTP endpoints.

Example testing a response DTO:

~~~java
@Test
void getPersonReturnsStableResponseContract() throws Exception {
    mockMvc.perform(get("/api/v1/people/42")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.fullName").value("An Nguyen"))
        .andExpect(jsonPath("$.internalNote").doesNotExist());
}
~~~

Example testing an input contract rejecting a missing required field:

~~~java
@Test
void createPersonRejectsBlankFirstName() throws Exception {
    mockMvc.perform(post("/api/v1/people")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "firstName": " ",
                  "lastName": "Nguyen",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

These are illustrative examples; tests need to prepare data and configure MockMvc according to the real application.

Additionally, verify that:

1. Projections return the exact set of published fields.
2. Collection resources use the desired excerpt projection.
3. Repositories marked **exported = false** no longer have public Spring Data REST endpoints.
4. Custom endpoints preserve JSON fields, statuses, and validation behavior after entity changes.
5. Clients can follow HAL links without guessing paths.
6. Internal fields do not appear through other item, collection, or association endpoints.

## Key Takeaways

Exposing entities directly speeds up API creation but causes domain structures to easily become the HTTP contract. Use projections to control read representations, use annotations to stabilize paths and relations, and use DTOs with dedicated controllers/services when independent inputs, outputs, or API lifecycles are needed. Maintain contract tests so entity refactoring does not accidentally break clients using the API.