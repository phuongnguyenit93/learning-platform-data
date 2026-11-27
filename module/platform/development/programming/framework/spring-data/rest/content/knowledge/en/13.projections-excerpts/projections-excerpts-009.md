# Scope of Excerpt Application Across Collections, Relationships, and Single Resources

## Objectives

After this lesson, you can:

- Explain where excerpt projections are applied in Spring Data REST.
- Distinguish representations of collections, association resources, and item resources.
- Configure a default excerpt using **@RepositoryRestResource(excerptProjection = ...)**.
- Explicitly request a projection for a single resource.
- Understand how projections can inline relationship data in the body while HAL still retains navigation links.
- Avoid confusing excerpts with data security mechanisms.

## 1. What problem do projections and excerpts solve?

Spring Data REST can publish an entity along with its properties and links. However, a list screen typically needs only a few concise fields, whereas a detail page needs more information. If every response returns the same full representation, payloads can become large and clients must receive data they do not use.

A **Projection** defines a view of a domain object: which properties are included in the representation. An **Excerpt** is a projection automatically applied by Spring Data REST when embedding items into collections or related resources according to repository configuration.

Example Person entity with multiple properties:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phoneNumber;
    private String internalNote;
}
~~~

A list screen might only need the name, while a detail screen needs email and phone number. Excerpts help establish a leaner default representation wherever lists are displayed.

The key point to remember is that an excerpt controls how an entity is **embedded inside another representation**. It does not automatically become the default representation of every item URL.

## 2. Defining an excerpt projection

Create a projection interface:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();
}
~~~

The projection is named **personExcerpt** and applies to the **Person** domain type. The getters define which properties appear in this view.

Configure it on the repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

The **excerptProjection** attribute selects the projection used when Spring Data REST embeds Persons into collection resources or related resources. The repository still manages the Person entity as before; the annotation only changes the default representation in embedded contexts.

The projection must target the right domain type. Place the interface and annotation in a package discoverable by the application configuration, and ensure the repository is exported by Spring Data REST.

## 3. First scope: collection resources

When a client calls a collection:

~~~http
GET /api/people
Accept: application/hal+json
~~~

Spring Data REST returns a collection representation. Persons embedded inside **_embedded** will use the excerpt projection configured for PersonRepository.

Illustrative example:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "Lan",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/1"
          }
        }
      },
      {
        "firstName": "Minh",
        "lastName": "Tran",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/2"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people"
    }
  }
}
~~~

In this example, the Person items only show `firstName` and `lastName` per `PersonExcerpt`. Other fields of the entity are excluded from this excerpt.

The client still receives the **self** link to open each item. The excerpt does not remove the detail resource and does not change IDs or data stored in the database.

## 4. Second scope: related resources and associations

Excerpt projections are also used when Spring Data REST embeds entities into related resources. This is helpful for relationships between domain objects.

Suppose Person has a relationship to Address:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    @ManyToOne
    private Address address;
}
~~~

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String city;
    private String street;
    private String postalCode;
}
~~~

The Address repository can configure its own excerpt:

~~~java
@Projection(name = "addressExcerpt", types = Address.class)
public interface AddressExcerpt {

    String getCity();

    String getStreet();
}
~~~

~~~java
@RepositoryRestResource(
    path = "addresses",
    excerptProjection = AddressExcerpt.class
)
public interface AddressRepository extends JpaRepository<Address, Long> {
}
~~~

When Address is embedded into a collection or related resource via the excerpt mechanism, Spring Data REST uses the projection of **Address**, i.e., `AddressExcerpt`. The excerpt configurations of `PersonRepository` and `AddressRepository` are tied to the domain type each repository manages; do not confuse the parent entity's projection with the related entity's projection.

For example, a collection/related representation can embed Address in condensed form while still providing a link for navigation:

~~~json
{
  "city": "Ho Chi Minh City",
  "street": "Le Loi",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/addresses/9"
    }
  }
}
~~~

For an association resource, observe which entity type is being embedded. If the resource returns a collection of Addresses, the excerpt configured for Address applies to the embedded Addresses. For single-valued relationships or nested representations, the exact display also depends on the chosen projection and how the association is rendered.

Simply having a relationship property does not automatically inline every related object. By default, Spring Data REST may represent relationships via links; projections can proactively include related data in the body.

## 5. Distinguishing parent entity excerpts from nested relationship projections

There are two separate things:

1. **A repository's excerpt** determines the default view when an item of that domain type is embedded in a collection or related resource.
2. **A relationship getter in a projection** determines whether association data is included inside that projection representation.

For example, if `PersonExcerpt` only has `firstName` and `lastName`, `address` is not added to the view just because the entity has an `address` property.

If you want to print address details together with Person, declare a relationship getter:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    String getLastName();

    Address getAddress();
}
~~~

When this projection is used, Address data can be inlined in the representation according to how Spring Data REST handles projections. HAL can still provide the association link for clients to open the separate resource.

Illustrative representation example:

~~~json
{
  "firstName": "Lan",
  "lastName": "Nguyen",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Le Loi"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/1"
    },
    "address": {
      "href": "http://localhost:8080/api/people/1/address"
    }
  }
}
~~~

A projection can produce a representation that both carries part of the related data and preserves navigation links. Clients avoid making an extra GET just to obtain already-inlined information, while still being able to follow the link if they need the full resource.

If you want to restrict which Address fields are inlined, define a suitable projection for Address and inspect the actual representation. Do not assume a relationship getter will always use the target repository's excerpt in every nested context; inlining depends on the projection and Spring Data REST's rendering mechanism.

## 6. Third scope: item resources do not automatically apply excerpts

This is the most important distinction.

When a client calls an item directly:

~~~http
GET /api/people/1
Accept: application/hal+json
~~~

Spring Data REST does not automatically apply the excerpt projection configured for the collection. The item resource returns the entity's detailed default representation according to standard publishing rules.

The reason is that a collection excerpt is a preview meant for lists. A client accessing an item URL is usually requesting a specific resource and may need a fuller representation.

For example, a collection might contain only:

~~~json
{
  "firstName": "Lan",
  "lastName": "Nguyen"
}
~~~

Whereas the item resource may also contain `email`, `phoneNumber`, and other published properties, along with association links.

Therefore, do not conclude that a field missing from a collection excerpt does not exist or is not provided by the item resource.

## 7. Explicitly requesting a projection for an item resource

If a client wants an item resource to use a specific projection, pass the projection name through the **projection** query parameter:

~~~http
GET /api/people/1?projection=personExcerpt
Accept: application/hal+json
~~~

Spring Data REST can apply the registered projection named **personExcerpt** to the item response.

The projection must be discovered and registered for the right domain type. The name in the query parameter is the **name** attribute of the **@Projection** annotation, not the Java class name or repository name.

Example:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();
}
~~~

Client requests:

~~~text
/api/people/1?projection=personExcerpt
~~~

For collections, clients can also explicitly request a projection when the API and configuration support it. However, `excerptProjection` on the repository already serves as the default choice for items embedded in collections; the query parameter is useful when a client needs to select a different view.

Do not confuse **excerptProjection** with the **projection** query parameter:

- **excerptProjection** configures the default view for embedded items.
- **projection=...** requests a specific projection for the request.

## 8. Comparing application scopes

| Context | Does the default excerpt apply automatically? | How to choose the view |
|---|---|---|
| Collection resource, items inside `_embedded` | Yes, per the item domain type's repository | **excerptProjection** on the repository |
| Related/association resource embedding items | Can apply to embedded items per the excerpt configured for that domain type | Configure excerpt on the related domain type's repository |
| Item resource called directly, e.g. **/people/1** | No | Request **?projection=personExcerpt** if a projection is desired |
| Relationship data inlined via projection | According to the selected projection and rendering mechanism | Declare relationship getter in the projection |
| Link to association resource | Link can still be kept in HAL | Per relation and href published by the server |

How to read the table:

- Ask which entity is being embedded into the representation.
- Find the repository managing that domain type.
- Check whether the repository defines `excerptProjection`.
- If calling an item URL directly, request the projection explicitly when needed.
- If you want relationship data inlined, declare the relationship property in the appropriate projection.

## 9. Combined example

Suppose the application has:

- `PersonRepository` configured with `PersonExcerpt`.
- `AddressRepository` configured with `AddressExcerpt`.
- `Person` having an association to `Address`.

Repositories:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

~~~java
@RepositoryRestResource(
    path = "addresses",
    excerptProjection = AddressExcerpt.class
)
public interface AddressRepository extends JpaRepository<Address, Long> {
}
~~~

Projections:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {
    String getFirstName();
    String getLastName();
}
~~~

~~~java
@Projection(name = "addressExcerpt", types = Address.class)
public interface AddressExcerpt {
    String getCity();
    String getStreet();
}
~~~

Requests:

~~~http
GET /api/people
~~~

The collection embeds Persons using `PersonExcerpt`.

~~~http
GET /api/people/1
~~~

The item resource does not automatically use `PersonExcerpt`; the item's default representation is returned.

~~~http
GET /api/people/1?projection=personExcerpt
~~~

The item resource is requested to use the `personExcerpt` projection.

~~~http
GET /api/addresses
~~~

The collection embeds Addresses using `AddressExcerpt`.

~~~http
GET /api/people/1/address
~~~

The association resource provides the address relationship of Person 1. If the response embeds an Address inside a related resource, Address's excerpt can be used depending on configuration and rendering context.

These URLs are examples using the **/api** base path. Retrieve actual URIs from the application's HAL responses.

## 10. Verifying with curl

Read the collection to inspect the excerpt:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/people
~~~

Read the default item resource:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/1
~~~

Request an explicit projection for the item:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people/1?projection=personExcerpt"
~~~

Read the collection of the related entity:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/addresses
~~~

Compare bodies across responses. Inspect the fields appearing in **_embedded**, fields of the item resource, and links in **_links**. Do not just compare field counts; verify the exact projection name and domain type being applied.

## 11. Common mistakes

### Expecting the excerpt to appear on the item URL

**@RepositoryRestResource(excerptProjection = ...)** does not automatically apply the excerpt to an item resource called directly. Use **?projection=...** when you want to select a projection for an item.

### Using the wrong projection name

The name in the query parameter must match **@Projection(name = "...")**. The Java class name is not necessarily the projection name.

### Attaching the excerpt to the wrong repository

Excerpts are chosen based on the domain type of the item being embedded. If a collection is embedding Address, check the configuration of the repository managing Address rather than only checking `PersonRepository`.

### Thinking excerpts remove relationship links

Projections change the data representation. Hypermedia links can still be provided for clients to navigate to associations or separate item resources.

### Thinking a relationship getter always inlines everything

If a projection does not declare a relationship getter, related data does not appear automatically just because the entity has an association. If inlining is needed, add the property to the projection and check the actual response.

### Using projections to hide sensitive data

Projections are a way to choose representations for clients. They do not replace authorization or data protection policies. If a sensitive field must not be disclosed, control access and design the API on the server; do not rely solely on excerpts.

### Changing the excerpt after the API is published

Excerpts change the default representation of collections and related resources. Clients may already depend on previous fields. When changing a projection, treat it as an API contract change and assess the impact on clients.

## 12. Takeaways

- An excerpt is a projection automatically used when embedding items into collections or related resources.
- **@RepositoryRestResource(excerptProjection = ...)** configures the excerpt per the repository's domain type.
- Collection resources use the excerpt for items inside **_embedded**.
- Related/association resources can use the excerpt of the embedded domain type.
- Item resources called directly do not automatically apply the excerpt.
- Use **?projection=projectionName** to request a specific view for an item.
- Relationship getters in projections can inline related data; HAL can still keep navigation links.
- Projections and excerpts are not authorization or sensitive-data protection mechanisms.

## References

- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — RepositoryRestResource API](https://docs.spring.io/spring-data/rest/reference/5.2-SNAPSHOT/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [Spring Data REST — CollectionResourceMapping API](https://docs.spring.io/spring-data/rest/docs/3.7.11/api/org/springframework/data/rest/core/mapping/CollectionResourceMapping.html)
