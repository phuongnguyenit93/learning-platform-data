# Explicitly Exposing IDs with exposeIdsFor When Needed

## Objectives

Spring Data REST represents resources in a hypermedia-driven manner by default. An entity is typically identified through HAL links such as `_links.self.href`; the entity's ID does not necessarily appear as a regular property in JSON.

When clients need the ID value directly to store state, correlate data with another system, display a reference code, or run an integration workflow, you can configure Spring Data REST to expose IDs using `RepositoryRestConfiguration.exposeIdsFor(...)`.

This configuration allows the IDs of selected domain types to appear as a property in the representation. It does not change the primary key, ID generation strategy, item resource URI, or data access permissions. Enable it only for resource types whose API contract truly needs the ID in the body.

## 1. IDs in Entities and REST Representations

Suppose we have a Person entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;

    // constructors, getters, setters
}
~~~

Repository exported by Spring Data REST:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

With default configuration, an item response typically has a representation similar to:

~~~http
GET /people/42
Accept: application/hal+json
~~~

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

Clients can still identify and navigate to the item via the self link. However, if a client application needs a dedicated ID field to store in state or use in a data table, having the ID only inside the link URL may be inconvenient.

When exposeIdsFor is enabled for Person, the representation can additionally include the ID property:

~~~json
{
  "id": 42,
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Property ordering in JSON is not guaranteed. The example simply illustrates the ID appearing as a regular data property alongside HAL links.

## 2. Configuring exposeIdsFor with RepositoryRestConfigurer

The common approach is to implement RepositoryRestConfigurer and call exposeIdsFor inside configureRepositoryRestConfiguration:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.exposeIdsFor(Person.class);
    }
}
~~~

In the example, Spring Data REST is instructed to expose the ID of the Person domain type. Once the application starts with this configuration, responses for Person resources can include the id property.

You can pass multiple domain types in a single call:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.exposeIdsFor(
            Person.class,
            Order.class,
            Product.class
        );
    }
}
~~~

The method accepts a varargs list of Class<?> domain types. Pass the entity/domain classes managed by repositories, such as Person.class; do not pass repository interfaces or ID Java types such as Long.class.

If the application already has a RepositoryRestConfigurer, add the configuration to the existing implementation or organize configurers according to the project's convention. Avoid creating duplicate configurations that make it hard for maintainers to locate where REST behavior is managed.

## 3. Enable IDs Only for Needed Domain Types

exposeIdsFor is configured per domain type. For instance, if only Person clients need the ID in JSON, enable only Person:

~~~java
config.exposeIdsFor(Person.class);
~~~

That way, there is no need to enable IDs for every domain type in the application. For Order and Product, representations continue following the existing configuration if they are not in the exposed list.

Selection table:

| Need | Suitable Configuration |
|---|---|
| Clients need Person ID in JSON | exposeIdsFor(Person.class) |
| Clients need IDs for multiple entity types | exposeIdsFor(Person.class, Order.class, Product.class) |
| Clients only need to navigate to the resource | Use the HAL self link; no need to expose ID separately |
| Clients need a business code instead of a database ID | Design a business code property or appropriate entity lookup; exposeIdsFor does not change the identifier key |
| Do not want an entity type exposing its ID in the body | Do not add that domain type to exposeIdsFor |

Manage the list of exposed IDs as part of the API contract. When adding a new domain type, determine which clients truly need the ID before adding that class to the configuration.

## 4. Distinguishing the ID Property from HAL Links

The ID in JSON and HAL links solve two different needs:

- The id property provides the identifier value as data. Clients can store this value, display it, or use it to reconcile with another system.
- The _links.self.href link provides the canonical URI for clients to access the resource. This is the hypermedia mechanism for REST navigation and operations.

Example response containing both:

~~~json
{
  "id": 42,
  "firstName": "An",
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42"
    }
  }
}
~~~

When a client needs to read a resource, prefer using the URI in the self link. Avoid parsing URL strings to extract IDs when the API can provide an ID property or structured links.

Conversely, if a client needs an ID value to store in business data, exposeIdsFor lets the client read that value directly. Having the ID in the body does not diminish the role of the self link and does not turn links into an ID field.

## 5. exposeIdsFor Does Not Change Endpoint Identity

Given the repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

The item resource still has a URI of the form:

~~~http
GET /people/42
~~~

After calling exposeIdsFor(Person.class):

- The ID appears in the representation according to configuration.
- Item URIs are still determined by the active entity lookup strategy.
- The repository ID type remains Long.
- @Id in the entity still defines the persistent identifier.
- The findById method still looks up by the repository identifier.
- There are no database schema or ID generation strategy changes merely from enabling exposeIdsFor.

If the goal is to change item URIs to use a business code instead of the primary key, exposeIdsFor does not solve that. Spring Data REST has a dedicated entity lookup mechanism to map URI identifiers to entities. Distinguish exposing an ID in JSON from changing how the server looks up entities from paths.

## 6. When Should Clients Request the ID?

Situations where an ID in the body is useful:

- Frontend data tables need to retain the ID to update or delete an item later.
- An application needs to reconcile an entity with an integrated system using the same identifier.
- Logs or operational screens need to display the ID for lookup.
- A batch process needs to store a list of IDs received from responses.
- Clients need to associate response data with a previously stored local record.

If clients only need REST navigation or operations, HAL links are usually sufficient. Avoid exposing IDs merely to add extra fields to JSON; every returned property becomes part of the API contract that clients may depend on.

## 7. Security and Access Control Implications

Exposing an ID in JSON does not automatically grant permission to read, update, or delete the entity. Calling GET, PUT, PATCH, or DELETE still must adhere to security configuration, authorization rules, and repository exposure.

However, IDs can disclose information about the system:

- Sequential IDs can allow users to infer record counts or creation order.
- Internal IDs can be used to correlate data across systems.
- IDs in responses make it easy for clients to store and resend them in subsequent requests.

Therefore:

- Only expose IDs for domain types with a clear need.
- Do not rely on unpredictable IDs as an authorization mechanism.
- Enforce permissions at the resource and operation levels, even when clients know the ID.
- If an unpredictable public identifier is needed, consider a public identifier/UUID or a domain-appropriate business key.
- Do not embed sensitive information in the ID value itself.
- Treat exposing an ID as a representation change that can affect clients and API documentation.

Sequential IDs are not inherently a vulnerability if authorization is properly implemented. Risk arises when an application relies on users not knowing an ID to protect resources.

## 8. Combining with Projections and Jackson

Spring Data REST can use projections to produce representations tailored to client needs. Projections decide which properties are included in a representation; exposeIdsFor controls whether Spring Data REST exposes the identifier as a regular property for a domain type.

Example projection:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Client request:

~~~http
GET /people/42?projection=personSummary
Accept: application/hal+json
~~~

Do not assume every projection automatically displays the ID just because the domain type is configured with exposeIdsFor. If clients need the ID in a specific projection, inspect the actual representation and adjust the projection/API to match the Spring Data REST version in use.

Jackson annotations, mixins, custom serializers, and application serialization settings can also affect property visibility. If the ID is annotated with @JsonIgnore or handled by a custom serializer, test the actual output rather than assuming exposeIdsFor always overrides all Jackson rules.

Do not use exposeIdsFor to work around a normal JSON field hidden due to serialization settings. This method is specifically for exposing identifiers managed by Spring Data REST.

## 9. Verifying Responses After Enabling exposeIdsFor

After adding the configuration, run the application and send GET to an item with existing data:

~~~http
GET /people/42
Accept: application/hal+json
~~~

Verify:

1. The successful response has the expected status, typically 200 OK.
2. The body contains the id property with the right type and the entity's identifier.
3. _links.self.href still points to the correct item.
4. Other business fields continue to serialize as configured.
5. Unselected domain types do not unexpectedly expose IDs.
6. Projections and custom Jackson serializers produce output matching the API contract.

You can check manually with curl:

~~~bash
curl -i http://localhost:8080/people/42 \
  -H "Accept: application/hal+json"
~~~

Or use MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ExposedIdTests {

    @Autowired
    MockMvc mvc;

    @Test
    void personRepresentationContainsItsId() throws Exception {
        mvc.perform(get("/people/42")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$._links.self.href")
                .value(org.hamcrest.Matchers.endsWith("/people/42")));
    }
}
~~~

This is an integration test skeleton. Create a Person fixture with a known ID or obtain the URI from a POST response; do not rely on auto-generated IDs if test execution order is not fixed.

Also add a test for a domain type not in the exposed list to confirm the configuration affects only selected types. If the application has projections or custom serializers, test those representations separately.

## 10. Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| ID does not appear in JSON | exposeIdsFor was not called for the domain type | Add the right entity class to the configuration |
| Person is exposed, but Order still has no ID | Only Person.class was registered | Add Order.class if clients genuinely need it |
| ID appears, but URL does not change | exposeIdsFor only changes representation | Use an entity lookup strategy if you need to change URI identifiers |
| Client has the ID but still gets 403 | Knowing the ID does not grant access | Check Spring Security and authorization |
| Projection lacks the ID | Projections only expose defined accessors | Check the projection and actual representation |
| ID remains hidden after configuration | Jackson annotations, mixins, or custom serializers affect serialization | Inspect Jackson configuration and write response tests |
| Clients depend on internal IDs | The API contract exposes database identifiers | Consider a stable public ID or business key |
| All entities expose IDs unexpectedly | Overly broad exposure configuration or unintended domain type list | Register only the necessary domain types |

## 11. Checklist Before Exposing IDs

- Verify that clients or use cases genuinely need the ID in JSON.
- Check the exact domain type exported by the repository.
- Use config.exposeIdsFor(Entity.class) inside RepositoryRestConfigurer.
- Pass multiple entity classes when needed; do not pass repository interfaces or ID classes.
- Keep the self link as the canonical URI for navigating to the resource.
- Distinguish the ID in the body from the identifier used in URIs.
- Check projections, Jackson annotations, and custom serializers.
- Test both exposed domain types and non-exposed domain types.
- Evaluate internal ID disclosure and ensure authorization does not rely on ID unpredictability.
- Update API documentation and client contracts if representations change.

## Conclusion

RepositoryRestConfiguration.exposeIdsFor(...) allows Spring Data REST to expose the ID as a regular property in the representations of selected domain types. This configuration is useful when clients need to store or correlate identifiers directly from JSON. The ID in the body complements the HAL self link; it does not alter primary keys, item URIs, entity lookups, or access permissions. Enable it only for resource types that need it, verify projections/Jackson settings, and ensure security is enforced independently of whether a client knows an ID.

## References

- Spring Data REST – RepositoryRestConfiguration API, exposeIdsFor(Class<?>...): https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html
- Spring Data REST – Working with Spring Data Repositories and resource representations: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST – Projections and excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
