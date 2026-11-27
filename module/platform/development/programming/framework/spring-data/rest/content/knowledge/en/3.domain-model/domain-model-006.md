# Impact of Having a Separate Repository on Relationship Representation

## Objectives

After this lesson, you will be able to explain why a relationship property in Spring Data REST sometimes appears as a HAL link and sometimes appears as a nested object in JSON; build examples with and without a repository for the related entity; read and update association resources; and choose an appropriate representation using projections, excerpt projections, or export configuration.

## 1. Two Concepts to Separate

In a domain model, an entity can reference another entity. For example, Person has an address attribute of type Address. With JPA, this relationship can be mapped using @OneToOne, @ManyToOne, @OneToMany, or @ManyToMany.

Spring Data REST uses repositories to decide which domain types are published as REST resources. Therefore, distinguish between:

- **Relationship mapping** describes how objects are linked and persisted, such as @OneToOne or @ManyToOne.
- **Repository** indicates whether a domain type has its own data access gateway.
- **Repository export** determines whether Spring Data REST exposes that repository as collection/item resources for HTTP clients.

Having a JPA relationship annotation alone does not automatically create an independent REST endpoint for the referenced entity. Conversely, having a separate repository for the related entity can change how Spring Data REST represents the relationship property in HAL.

## 2. Person and Address Domain Example

Suppose an application has two entities. The snippets below focus on the relevant parts; constructors, getters, setters, and imports are omitted:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;

    @OneToOne
    private Address address;
}
~~~

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String street;
    private String country;
}
~~~

Person's repository:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

Suppose the data has a person named Frodo and address Bag End. We will vary only the presence or absence of AddressRepository to observe the outcome.

## 3. Case Without a Separate Repository for Address

If the application only has PersonRepository, Spring Data REST has no dedicated repository resource for managing Address. Under the default representation, Address data is included directly inside Person's representation.

Abbreviated HAL response from GET /persons/1:

~~~json
{
  "firstName": "Frodo",
  "address": {
    "street": "Bag End",
    "country": "Middle Earth"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/persons/1"
    }
  }
}
~~~

In this case:

- Clients receive the Address fields directly in Person's response.
- No /addresses collection resource is created from an AddressRepository.
- Clients cannot rely on Spring Data REST to navigate to an independent Address item resource in the usual way.
- To read or update address data, clients work through Person's representation and endpoint, following the data structure accepted by the API.

This approach fits when Address is merely dependent data of Person and does not need to be queried, referenced, or managed as an independent resource.

## 4. Case With a Separate Repository for Address

Add a repository for Address:

~~~java
public interface AddressRepository
        extends CrudRepository<Address, Long> {
}
~~~

Spring Data REST can now publish both resource types:

- A collection resource for Person, defaulting to /persons.
- A collection resource for Address, defaulting to /addresses.

A Person item is still accessed at /persons/1. However, in Person's representation, the address property is expressed as an association link instead of embedding all Address fields inline.

Abbreviated HAL example:

~~~json
{
  "firstName": "Frodo",
  "_links": {
    "self": {
      "href": "http://localhost:8080/persons/1"
    },
    "address": {
      "href": "http://localhost:8080/persons/1/address"
    }
  }
}
~~~

The important detail is that the address link in this example points to the **association resource** /persons/1/address. It represents the address relationship of that Person. A separate repository for Address also makes the Address collection and item resources discoverable from the API root, such as /addresses and /addresses/5.

You can read the relationship via the provided link:

~~~http
GET /persons/1/address
Accept: application/hal+json
~~~

The association resource returns the current state of the relationship. When binding an existing Address to Person, the client sends the Address resource's URI to the association resource.

For a one-to-one or many-to-one relationship, such as linking Address 5:

~~~http
PUT /persons/1/address
Content-Type: text/uri-list

http://localhost:8080/addresses/5
~~~

For collection-valued associations, POST to the association resource to add an element. DELETE removes the link; whether unlinking is allowed also depends on whether the relationship is nullable. PUT for a one-to-one relationship does not accept multiple URIs at once.

Link-based representation is useful when the related entity has its own lifecycle or access path, is referenced by multiple entities, or may hold substantial data. Clients can load related data on demand rather than always receiving the full nested object.

## 5. Direct Comparison

| Aspect | Without AddressRepository | With Exported AddressRepository |
|---|---|---|
| Representation of address in Person | Nested object in JSON | Relationship link in _links |
| Address data in default Person response | Address fields sent inline | Full address fields not sent by default |
| Resource /addresses | Not created from a repository | Exposed |
| Accessing the relationship | Through Person's payload | Via association link, e.g., /persons/1/address |
| Independent Address management via Spring Data REST | No dedicated repository resource | Can access Address collection/item resources |
| Person response size | Can be larger when related object has many fields | Usually smaller; client may need an extra request |

This is the default representation behavior. Projections, excerpt projections, Jackson configuration, and other customizations can alter response contents.

## 6. Having a Separate Repository Does Not Always Mean Returning Links

You may want a separate repository so Address has an independent endpoint, while still returning certain address fields alongside Person's response. Spring Data REST supports projections to customize representations.

### 6.1. Projections to Select Returned Fields

Example projection returning only the name without including address in the payload:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();
}
~~~

This representation can be requested via a query parameter:

~~~http
GET /persons/1?projection=personSummary
Accept: application/hal+json
~~~

The projection specifies which attributes are included in the representation. Association links provided by Spring Data REST may still be present for clients to discover relationships.

For a projection to be auto-detected, place the interface in the same package as the domain type or a sub-package; if needed, register it manually via RepositoryRestConfiguration.

### 6.2. Excerpt Projections to Embed Commonly Used Data

If clients frequently need to read the address alongside Person, you can define a projection containing getAddress():

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    Address getAddress();
}
~~~

Then attach it as the excerpt projection on the repository:

~~~java
@RepositoryRestResource(excerptProjection = PersonWithAddress.class)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

An excerpt projection is used when Spring Data REST embeds Person in collections or related resources. The representation can then both contain the address object inline and preserve the association link for clients to continue navigating to the Address resource.

An excerpt projection is not automatically applied to every response of a single item resource. When a specific projection is needed for an item, request it explicitly via ?projection=personWithAddress.

### 6.3. Renaming or Hiding Association Links

You can rename the relation and path using @RestResource on the property:

~~~java
@OneToOne
@RestResource(path = "location", rel = "location")
private Address address;
~~~

The relationship link now uses the configured location relation/path.

If you do not want to publish the association property, you can place @RestResource(exported = false) on the property:

~~~java
@OneToOne
@RestResource(exported = false)
private Address address;
~~~

If you want to hide the entire REST repository of a domain type, you can put @RepositoryRestResource(exported = false) on the repository. The repository can still be used inside the application via Spring Data, but Spring Data REST will not expose it as a REST resource.

Hiding an association and hiding a repository are decisions at two different scopes. Test the actual API after configuration, especially if clients depend on legacy links or endpoints.

## 7. Choosing an Appropriate Design

Use a separate repository for a related entity when:

- The entity has an independent identity and lifecycle.
- Multiple other entities reference that entity.
- Clients need to search, paginate, update, or delete the related entity independently.
- You want the API to provide clear HATEOAS links for navigating between resources.

A separate repository is not necessarily needed when:

- The object is merely a dependent component, always read and updated alongside the parent aggregate.
- No standalone endpoint is needed for the object.
- Returning nested object fields aligns with the API contract.

When choosing a representation, weigh the number of fields, number of relationships, how frequently clients need related data, and the cost of extra requests. For large objects or multi-level relationships, links and projections usually control response size better. For small, stable objects typically used together with the parent entity, inline representation can be more convenient.

Do not decide whether to create a repository solely based on wanting shorter or longer JSON. Repositories also affect discoverability, routing, and resource operations. Design repository boundaries around how the domain needs to be accessed and managed.

## 8. Common Pitfalls

1. **Assuming @OneToOne automatically creates an endpoint for Address.** JPA annotations describe persistence relationships; for Address to have collection/item resources in Spring Data REST, an exported repository is required.
2. **Confusing an association link with a direct item link.** In the example, _links.address points to /persons/1/address, which is the association endpoint on Person. The Address item has its own URI, such as /addresses/5.
3. **Thinking a separate repository prevents embedding related data.** Projections or excerpt projections can inline needed fields while keeping links.
4. **Using exported = false at the wrong scope.** Placing it on an association property hides that relationship; placing it on a repository hides the repository resource. The two settings have different effects.
5. **Sending a JSON object when an association endpoint expects a URI.** Association binding operations use text/uri-list with the target resource's URI.
6. **Failing to verify API contract changes.** Switching from an inline object to a link changes the response structure clients must parse. Update and test consumers before releasing.
7. **Letting projections return excessive data.** Projections can bloat responses and increase retrieval cost. Only include fields clients actually need in the representation.

## 9. Verification Workflow in the Application

1. Create PersonRepository and run the application; call GET /persons/1 to observe the representation before adding AddressRepository.
2. Add AddressRepository, restart, and call the same endpoint again. Compare inline address with _links.address.
3. Follow the association link in the response via GET /persons/1/address.
4. Try binding an existing Address using PUT and Content-Type: text/uri-list.
5. Add a projection or excerpt projection, call the corresponding endpoint, and verify both inline data and links.
6. Inspect the API root, endpoints, and access permissions to ensure only intended repositories and associations are exposed.

## 10. References

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Repository Resources and Association Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing the JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html)
- [Spring Data REST — Hiding Repositories, Query Methods, and Fields](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)

Representation examples are abbreviated to highlight the difference between inline data and association links. Actual URIs depend on context path, @RepositoryRestResource, @RestResource, and the application's export configuration.