# Selecting a Projection Using the projection Query Parameter in Spring Data REST

By default, Spring Data REST creates representations from the domain model exposed by a repository. In many APIs, clients only need a subset of properties or want to view an association differently depending on the screen. A **Projection** lets you define a view of a resource; the client selects that view using the `projection` query parameter.

For example, the same user can be returned in a summary form containing only first and last name, or in a detailed form including an address. The client selects the projection directly on the GET request without needing a separate endpoint for each presentation format.

## 1. What is a projection?

A projection is an interface that describes the properties that will appear in the representation of a domain object. Spring Data REST builds the projection from the underlying entity when rendering the response.

Suppose the domain model is:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;

    @OneToOne
    private Address address;

    // getters and setters
}
~~~

If the repository is exposed without projections, Spring Data REST uses the default representation of Person according to the serialization and association configuration. Clients may receive data fields along with HAL links to related resources.

Projections let you define alternative representations without modifying the entity or creating new records. They are not separate entities and do not alter data stored in the database.

## 2. Declaring a projection with @Projection

Create a projection interface and annotate it with `@Projection`:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

In this example:

- `name = "personSummary"` is the projection name the client passes in the query parameter.
- `types = Person.class` associates the projection with the Person domain type.
- The getters specify the properties included in the representation.
- The interface name `PersonSummary` is not the value the client sends in the URL.

A projection only declares the view to render. Spring Data REST uses the projection to generate the corresponding response when requested by a client.

### Where to place projections for Spring Data REST discovery

By default, Spring Data REST discovers an interface annotated with `@Projection` if it resides in the same package as the domain type or a sub-package of that package. Projections can also be registered manually through the projection configuration of `RepositoryRestConfiguration`.

Example package structure:

~~~text
com.example.people
├── Person.java
├── Address.java
├── PersonRepository.java
└── projection
    ├── PersonSummary.java
    └── PersonDetails.java
~~~

Here, the projections sit in the `projection` sub-package, so they fall within the package scope Spring Data REST searches for Person.

If a projection is not discovered, check the annotation, `types` attribute, package, and projection registration configuration. Merely placing the interface in an arbitrary package does not guarantee it is automatically exposed.

## 3. Selecting a projection via the projection query parameter

Suppose the repository is exposed at `/people`:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

A client can fetch a Person resource by ID and select a projection:

~~~http
GET /people/42?projection=personSummary
Accept: application/hal+json
~~~

The query parameter value must match `name` in `@Projection`. Therefore, `projection=personSummary` selects the interface declared with `@Projection(name = "personSummary", ...)`.

An illustrative response might look like this:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

The `email` and `address` fields do not appear in this view because the projection does not declare them. The actual HAL structure also depends on the application's associations and configuration.

### Selecting a projection for a collection resource

A projection can also be requested when reading a collection:

~~~http
GET /people?projection=personSummary
Accept: application/hal+json
~~~

Spring Data REST applies the selected projection when rendering items in the collection response. Clients can use the same repository resource while choosing a representation suited to each screen's needs.

For example:

- A list screen only needs `firstName` and `lastName`.
- A detail screen also needs email and address.
- An integration job needs a different representation than the user interface.

There is no need to create separate collection endpoints just to return different sets of properties if projections meet the requirement.

## 4. Declaring multiple projections for the same domain type

You can define multiple projection interfaces for the same entity:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

~~~java
@Projection(name = "personDetails", types = Person.class)
public interface PersonDetails {

    String getFirstName();

    String getLastName();

    String getEmail();

    Address getAddress();
}
~~~

The client chooses the corresponding view:

~~~http
GET /people/42?projection=personSummary
~~~

~~~http
GET /people/42?projection=personDetails
~~~

Both requests read the same Person 42. The difference lies in the returned representation.

When a projection declares a getter returning an association such as `getAddress()`, the association data can be placed directly into the projected representation. If the application also exposes an Address repository, HAL may still provide a link to the Address resource so the client can continue navigating.

## 5. Projections for nested associations

A projection can use another projection for an association to control nested data.

Example:

~~~java
@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {

    String getCity();

    String getStreet();
}
~~~

A Person projection can declare a getter returning AddressSummary:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    String getLastName();

    AddressSummary getAddress();
}
~~~

When the client requests:

~~~http
GET /people/42?projection=personWithAddress
~~~

the representation can include the address data nested inside Person according to the getters of AddressSummary.

This is useful when clients need related data in a single response and want to limit the association's properties. Verify package discovery and how Spring Data REST applies projections to associations in the version you are using.

## 6. Projections creating computed properties with @Value

A projection interface does not only return existing properties. You can create a virtual property using SpEL via the `@Value` annotation.

Example combining first and last names:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personName", types = Person.class)
public interface PersonName {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
~~~

Request:

~~~http
GET /people/42?projection=personName
~~~

The representation may contain:

~~~json
{
  "fullName": "An Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

The `fullName` property is computed from the target object when rendering the response. It is not a new field written to the Person table.

For projections using SpEL, understand which properties the expression accesses and avoid putting complex business logic into representations. If a calculation requires querying data or substantial business rules, a dedicated service or DTO may be more suitable.

## 7. Distinguishing selected projections from excerpt projections

A **projection selected by query parameter** applies per request. The client specifies the view with `?projection=...`.

An **excerpt projection** is a projection configured as the default representation when Spring Data REST embeds an item inside a collection resource or related resource.

Example declaring an excerpt for Person:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

When a client calls:

~~~http
GET /people
~~~

Spring Data REST uses PersonSummary as the default view for Persons embedded in the collection response.

An excerpt projection **is not automatically applied to an individual item resource**. When a projection is needed for an item resource, the client can request it explicitly via the query parameter:

~~~http
GET /people/42?projection=personSummary
~~~

This distinction is critical when inspecting responses: a collection may show the excerpt while a request to the item URI still displays the full representation by default.

### Excerpts can include associations in the response

An excerpt projection can declare a getter for an association:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();

    Address getAddress();
}
~~~

Then configure:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

When the collection is rendered, address data can be embedded into the Person representation. The association link may still be provided so clients can access the standalone Address resource.

Configuring an excerpt changes the default representation of collections and related resources. If the API already has consuming clients, changing the excerpt may alter the response structure those clients depend on. Treat this as an API contract change and verify compatibility before release.

## 8. Discovering supported projections via ALPS

Spring Data REST provides ALPS metadata describing the operations and properties of REST resources. Clients can follow the `profile` link exposed at the root resource and then inspect the metadata for the corresponding resource type.

In the GET operation description, ALPS can list a `projection` descriptor along with the supported projection names. This allows clients to discover projection names instead of guessing from Java interface names.

Discovery workflow:

1. Call the API root resource.
2. Follow the `profile` link in HAL.
3. Open the ALPS metadata for the resource, such as the Person profile.
4. Locate the `projection` descriptor and the list of exposed projections.
5. Pick a valid name and pass it in the `projection` query parameter.

Metadata may vary by repository, configuration, and version. Clients should rely on the profile actually published by the server.

## 9. Projections are not an authorization or data protection mechanism

Projections help choose representations, but they should not be used as a security boundary.

A projection can bring data that was hidden from the default representation back into the response. For example, if a property is marked with `@JsonIgnore`, a projection can still expose that property through a corresponding getter. Therefore, `@JsonIgnore` or omission from a default projection cannot be treated as a guarantee that sensitive data is inaccessible.

Do not expose projections containing passwords, tokens, secrets, or user data that callers are not permitted to view. Use proper authorization, export control, serialization settings, and API design to protect data. Audit all projections registered for a domain type before exposing endpoints externally.

Projections also do not replace DTOs or command objects for write operations. The `projection` query parameter controls how representations are rendered, primarily on read requests. Do not use projections as a way to define the set of fields a client is allowed to POST, PUT, or PATCH.

## 10. Common mistakes when selecting projections

**Request uses the interface name instead of the projection name**

Incorrect example:

~~~http
GET /people/42?projection=PersonSummary
~~~

If the annotation declares `name = "personSummary"`, the client must send that exact value:

~~~http
GET /people/42?projection=personSummary
~~~

**Projection is not discovered**

Verify that the interface has `@Projection`, `types` specifies the right domain type, and the interface sits in the same package or a sub-package. If placed outside that scope, register the projection through appropriate configuration.

**Projection does not display a property**

Only getters declared in the projection (along with nested data they return) are included in that view. Check the getter, property name, return type, and association mapping.

**Excerpt appears in the collection but not on the item resource**

This is by design. Excerpts are the default for items embedded in collections or related resources; to select a projection for a specific item, pass the `projection` query parameter.

**Client cannot find links or fields after switching projections**

Projections alter the representation. Check the JSON data, `_links`, `_embedded`, and nested properties that the client relies on.

**Using projections to hide sensitive data**

Projections are not authorization. Protect sensitive data at the security and serialization layers, and audit registered projections.

## 11. Testing projections over HTTP

You should test real endpoints to confirm projections are discovered and applied correctly.

A basic test suite:

1. Call `GET /people/42` to retrieve the default representation.
2. Call `GET /people/42?projection=personSummary` and confirm only the properties declared by PersonSummary are present.
3. Call `GET /people?projection=personSummary` and verify that items in the collection use the selected projection.
4. Call `GET /people` when the repository has an excerptProjection and confirm the excerpt is applied to embedded items.
5. Call `GET /people/42` to confirm the excerpt is not automatically applied to an individual item resource.
6. Test projections with associations or computed properties.
7. Check the ALPS profile to ensure the expected projection names are published.
8. Verify that no projection inadvertently exposes sensitive data.
9. Test existing clients when changing getters, projection names, or the default excerpt.

Do not check only HTTP status 200. Compare the response structure, data fields, HAL links, and nested data against the contract expected by clients.

## 12. Implementation workflow

1. Identify the representations clients need for each screen or use case.
2. Create a projection interface for each view, annotate it with `@Projection`, and give it a stable name.
3. Place the projection in the domain type's package or sub-package, or register it manually.
4. Use the `projection` query parameter to select the view per GET request.
5. Configure `excerptProjection` only when you want a default for items embedded in collections or related resources.
6. Use nested projections when you need to control associations; use `@Value` for simple computed properties.
7. Inspect ALPS, HAL responses, and authorization to prevent misconfiguration or data exposure.
8. Run integration and contract tests for collections, items, associations, and affected clients.

## 13. Key takeaways

- A projection is a view of a domain object used when Spring Data REST renders a representation.
- Declare projections using an interface annotated with `@Projection(name = "...", types = ...)`.
- The `projection` query parameter accepts the annotation's `name` value, not the Java interface name.
- Projections can be selected for both item resources and collection resources per request.
- Spring Data REST automatically discovers projections in the same package or a sub-package of the domain type; they can also be registered manually.
- Excerpt projections are configured with `@RepositoryRestResource(excerptProjection = ...)` and apply by default to items embedded in collections or related resources.
- Excerpts do not automatically apply to standalone item resources; use `?projection=...` when selecting a projection for an item.
- Projections can nest associations and create virtual properties using `@Value`.
- Projections are not an authorization mechanism and can expose sensitive data if inappropriate getters are declared.
- Test HAL/JSON responses and ALPS to ensure clients receive the expected representation.

## References

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — RepositoryRestResource API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [Spring Data REST — Projection annotation API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/Projection.html)
