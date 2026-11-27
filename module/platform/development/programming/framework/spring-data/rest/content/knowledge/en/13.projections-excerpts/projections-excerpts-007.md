# Excerpt Projections and Configuring excerptProjection on Repositories in Spring Data REST

## Objectives

By default, Spring Data REST represents domain objects using the properties the framework can export. When a client reads a large collection, embedding full details of every entity can make the response heavy; however, returning only association links can also force the client to send many extra requests to fetch frequently used data.

A **Projection** lets you define a view of an entity. An **Excerpt** is a projection automatically applied when Spring Data REST embeds item resources inside collections or related resources. You can select a default excerpt for a repository using the `excerptProjection` attribute of `@RepositoryRestResource`.

This lesson covers how to define projection interfaces, how to register and invoke projections explicitly, how to configure a default excerpt, the difference between collections and item resources, how to embed relationship data, and considerations around API compatibility and security.

## 1. What is a projection?

Suppose the application has a Person entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    @OneToOne
    private Address address;

    // constructors, getters and setters
}
~~~

When exported via Spring Data REST, the default representation may contain the `firstName` and `lastName` properties along with a link to `address`. If Address also has its own repository, the association is typically represented by a link:

~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
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

If the client only needs the name, you can define a projection containing only two getters:

~~~java
@Projection(name = "nameOnly", types = Person.class)
public interface PersonNameOnly {

    String getFirstName();

    String getLastName();
}
~~~

A projection is a Java interface annotated with `@Projection`. The `name` attribute is the public name clients use in the `projection` query parameter; it is not the interface name. The `types` attribute specifies the domain types to which the projection applies.

With the projection above, the response only displays the properties declared in the interface along with links provided by Spring Data REST. The entity and database schema remain unchanged.

## 2. Registering projections for client selection

Spring Data REST automatically discovers a projection interface if it is annotated with `@Projection` and placed in the same package as the domain type or in a sub-package of that package.

Example package structure:

~~~text
com.example.people
  Person.java
  Address.java
  PersonRepository.java
  projection
    PersonNameOnly.java
    PersonWithAddress.java
~~~

If the projection lies outside the discovered package scope, you can register it manually via `RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)`:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getProjectionConfiguration()
                .addProjection(PersonNameOnly.class);
    }
}
~~~

Main imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
~~~

A projection must be registered for Spring Data REST to expose it to clients. If the interface lacks `@Projection` or is not scanned/registered, the projection name may be missing from metadata and requests using that name will not apply as expected.

## 3. Calling a projection explicitly with the query parameter

After the projection is discovered, clients can select the projection using the `projection` query parameter.

Example:

~~~http
GET /api/people/1?projection=nameOnly
Accept: application/hal+json
~~~

The name `nameOnly` comes from `@Projection(name = "nameOnly", ...)`. Clients do not use `PersonNameOnly` unless that is also the annotation value.

A condensed response might look like this:

~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/1{?projection}",
      "templated": true
    },
    "address": {
      "href": "http://localhost:8080/api/people/1/address"
    }
  }
}
~~~

The self link can be a URI template so clients can continue selecting projections. Projections only affect how data is presented; navigation links can still be retained for clients to access related resources.

You can declare multiple projections for the same domain type, such as `nameOnly`, `withAddress`, and `details`. The client picks the view suited to the screen or use case.

## 4. An excerpt is the default projection for embedded items

An excerpt is a projection automatically applied by Spring Data REST when an item resource is embedded in a collection resource or related resource.

For example, a repository can configure an excerpt:

~~~java
@RepositoryRestResource(
        path = "people",
        excerptProjection = PersonNameOnly.class
)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

When a client calls the collection:

~~~http
GET /api/people
Accept: application/hal+json
~~~

items inside `_embedded.people` are represented using `PersonNameOnly`. Illustrative response:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "Frodo",
        "lastName": "Baggins",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/1"
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

The `excerptProjection` attribute takes the projection interface class. It specifies the default view used when Spring Data REST embeds the repository's item resources into collections and related resources. It does not change the entity or how the repository queries data.

## 5. Excerpts do not automatically apply to single item resources

This is the most important difference between an excerpt and an explicitly selected projection.

| Request | How it is applied |
| --- | --- |
| `GET /api/people` | The excerpt is applied to Persons embedded in the collection. |
| `GET /api/people/1` | Single item resource uses the default representation, not automatically the excerpt. |
| `GET /api/people/1?projection=nameOnly` | Projection is explicitly selected for the item. |
| Related collection embedding Person | The Person repository's excerpt is used for embedded Person items. |

An excerpt is designed as a default preview for collections, not the default representation of an item when a client reads that item directly. Item resources usually need a fuller representation so clients have enough information when reading or updating.

If you want an item resource to use a projection, the client must request it via the `projection` query parameter. Do not expect configuring `excerptProjection` to automatically alter every item GET request.

## 6. Embedding relationship data with an excerpt projection

A common case is Person having an Address. If Address is exported as its own repository, the default representation may only provide an association link. If the Person collection frequently needs to display the address, an excerpt can bring the Address data directly into the embedded item.

Define the projection:

~~~java
@Projection(name = "inlineAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    String getLastName();

    Address getAddress();
}
~~~

Configure the repository:

~~~java
@RepositoryRestResource(
        path = "people",
        excerptProjection = PersonWithAddress.class
)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

When calling the collection, the response can contain the address inline:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "Frodo",
        "lastName": "Baggins",
        "address": {
          "street": "Bag End",
          "state": "The Shire",
          "country": "Middle Earth"
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
    ]
  }
}
~~~

Address data is embedded for convenient client reading, while the association link can still be provided so clients can navigate to the standalone Address resource. An excerpt does not turn an association into a different entity and does not remove association endpoints.

Embedding related objects can enlarge the response. Only include in an excerpt the data frequently needed on list screens; avoid creating a deep object graph or loading many nested collections.

## 7. Projections can create computed properties

A projection interface does not only select existing getters. You can create a read-only property using Spring `@Value` and SpEL:

~~~java
@Projection(name = "personCard", types = Person.class)
public interface PersonCard {

    String getFirstName();

    String getLastName();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
~~~

In this example, `getFullName()` does not need a `fullName` field in the entity. Spring evaluates the expression on the target object and returns the combined value in the representation.

A projection can also declare a getter returning a nested projection interface to restrict the view of the related object:

~~~java
@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {

    String getCity();

    String getCountry();
}

@Projection(name = "personCardWithAddress", types = Person.class)
public interface PersonCardWithAddress {

    String getFirstName();

    String getLastName();

    AddressSummary getAddress();
}
~~~

Nested projections help control the level of embedded data instead of exporting every property of the related object. Nested projections must also be properly discovered or registered.

## 8. Projections can expose hidden data

A projection is a serialization boundary, not an authorization mechanism or automatic security filter.

By default, Spring Data REST respects Jackson `@JsonIgnore` when serializing entities. However, a projection can declare a getter for a property that the entity annotated with `@JsonIgnore`, causing that property to appear when the projection is used.

Unsafe example:

~~~java
@Entity
public class User {

    @Id
    private Long id;

    private String username;

    @JsonIgnore
    private String password;
}
~~~

A projection accidentally adds the getter:

~~~java
@Projection(name = "userDetails", types = User.class)
public interface UserDetailsProjection {

    String getUsername();

    String getPassword();
}
~~~

If clients can select this projection, the `password` field risks being included in the response. Spring Data REST cannot automatically know which properties are business-sensitive; the development team must control the exposed projections.

Safety guidelines:

1. Do not create public projections with getters for passwords, tokens, secrets, credentials, or internal data.
2. Inspect every getter and nested projection before registering.
3. Do not use projections in place of authorization; read permissions must still be enforced at the security/service layer.
4. Do not assume `@JsonIgnore` provides absolute protection if another projection actively exposes that property.
5. Use a dedicated DTO/controller if you need a response with an explicit allowlist for sensitive data.

## 9. Excerpts and API contract changes

Configuring `@RepositoryRestResource(excerptProjection = ...)` changes the default representation of items when embedded in collections or related resources. If the API is already used by clients, adding an excerpt can be a breaking change for clients relying on fields that previously appeared in embedded items.

For example, before configuration, an embedded Person might contain `firstName`, `lastName`, `birthDate`, and `address`. After configuring an excerpt with only `firstName` and `lastName`, clients reading `birthDate` from the collection response may no longer see that field.

Before releasing:

- List the clients consuming collections and related resources.
- Compare HAL responses before and after adding the excerpt.
- Confirm that fields omitted from the preview can still be read from the item resource if clients need them.
- Consider versioning or a migration path if the contract is already published.
- Check both the projection parameter and association links.

Projections/excerpts primarily serve read representations. Do not design update forms based on an excerpt because it may lack all properties needed for a replacement or update operation.

## 10. Verifying that a projection is discovered

Spring Data REST publishes ALPS metadata through the `profile` link at the API root. By following the domain resource's profile link, clients can view available projections and descriptions of the properties those projections provide.

Verification workflow:

1. Call the API root and retrieve the `profile` link.
2. Follow the ALPS link for the domain resource, such as `/api/alps/people`.
3. Locate the `projection` descriptor and published projection names.
4. Confirm the name in the descriptor matches `@Projection(name = "...")`.
5. Call the item resource with the `projection` query parameter to verify the representation.

If the projection is registered manually, inspect the Spring context configuration and ensure the configurer bean is actually loaded.

## 11. Testing with MockMvc

You can test excerpts on collections and explicit projections on items separately.

Verify the collection uses the excerpt:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonProjectionTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void collectionUsesConfiguredExcerpt() throws Exception {
        mockMvc.perform(get("/api/people")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._embedded.people[0].firstName")
                    .exists())
            .andExpect(jsonPath("$._embedded.people[0].lastName")
                    .exists());
    }
}
~~~

Verify the item resource with an explicit projection:

~~~java
mockMvc.perform(get("/api/people/{id}", 1)
        .param("projection", "nameOnly")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.firstName").exists())
    .andExpect(jsonPath("$.lastName").exists());
~~~

Verify the item does not automatically receive the excerpt by asserting that a field present only in the default representation still appears (if the entity and test fixture have that field). Do not assert only status 200; verify the exact fields and links in JSON.

For an excerpt with a nested Address, verify both the inline object and the association link:

~~~java
mockMvc.perform(get("/api/people")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.people[0].address.city")
            .exists())
    .andExpect(jsonPath("$._embedded.people[0]._links.address.href")
            .exists());
~~~

Tests need deterministic fixture data and must run against the project's actual Spring Data REST version. Adjust collection relation names, base paths, and projection names according to your application configuration.

## 12. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Projection does not appear in ALPS | Interface lacks `@Projection` or lies outside scanned packages | Place in domain package/sub-package or register manually |
| Query projection has no effect | Used interface name instead of annotation name or projection is not registered | Check `@Projection(name = ...)` value and ALPS descriptor |
| Collection still returns default representation | Repository has not configured `excerptProjection` or configured wrong class | Check `@RepositoryRestResource` on the right repository |
| Item GET does not use excerpt | Excerpt does not automatically apply to single resources | Send `?projection=projectionName` |
| Address remains just a link | Projection did not declare Address getter or nested projection was not applied | Add relationship getter to the excerpt and check serialization |
| Collection response is too large | Excerpt embeds too much relationship data | Reduce getters/nested projections or embed only necessary fields |
| Data exposed despite `@JsonIgnore` | Projection declares a getter for the hidden property | Remove sensitive getters and audit all projections |
| Existing clients break after adding excerpt | Embedded representation changed | Assess compatibility and update contract/clients |

## 13. When to use projection, excerpt, or DTO?

| Solution | When to use | Characteristics |
| --- | --- | --- |
| Explicit projection | Clients need to choose from multiple views on the same entity | Selected via the `projection` query parameter |
| Excerpt projection | Collections need a consistent default preview | Automatically applied when items are embedded |
| Nested projection | Need to restrict data of related objects | Controls deeper representations |
| DTO/custom controller | Need an independent contract, business logic, or explicit data allowlist | Full control over response and authorization |

If you only want to shrink collection payloads while keeping the item endpoint complete, excerpt is a natural choice. If clients need multiple representations depending on context, use explicit projections. If the response requires complex business calculations or strict control over sensitive fields, a DTO/custom controller is usually easier to manage.

## References

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): how to define projections, register, invoke projections, default excerpts, and embed relationship data.
- [Spring Data REST 5.1.2 API — RepositoryRestResource](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html): the `excerptProjection` attribute used when embedding item resources into collections and related resources.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection/item resource structure and hypermedia links.
