# Package Scanning Mechanism and Explicit Projection Registration in Spring Data REST

## Objectives

Spring Data REST lets you define projections to alter the set of properties returned when representing a domain object. A projection is typically an interface annotated with \`@Projection\`, declaring the getters visible to clients.

For a projection to be usable through the REST API, Spring Data REST must locate and register that definition. There are two main approaches:

1. **Automatic package scanning:** place the projection interface annotated with \`@Projection\` in the same package as the domain type or in a sub-package of that package.
2. **Explicit registration:** call \`RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)\` in Spring Data REST configuration, typically via \`RepositoryRestConfigurer\`.

Both approaches require the projection interface to have the \`@Projection\` annotation. The difference lies in how Spring Data REST finds and adds the projection to the registry. This lesson explains package rules, source code organization, manual registration, how to verify exposed projections, and common mistakes.

## 1. What is a projection?

Suppose a Person domain type has multiple properties:

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

    @ManyToOne
    private Address address;

    // getters/setters
}
~~~

Repository exported by Spring Data REST:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

By default, a Person representation may contain domain properties and links to associations. However, a client may only need Person's name, without email, phoneNumber, or address.

A projection describes a selective view:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Once the projection is registered, clients can request:

~~~http
GET /api/people/42?projection=personSummary
Accept: application/hal+json
~~~

Illustrative response:

~~~json
{
  "firstName": "Ada",
  "lastName": "Lovelace",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42{?projection}",
      "templated": true
    }
  }
}
~~~

The name passed in the \`projection\` query parameter is the value of the \`name\` attribute in \`@Projection\`, which here is \`personSummary\`. It is not automatically the interface name \`PersonSummary\`.

A projection is a way to change the representation of a resource. It does not create a new repository, does not create new CRUD endpoints, and does not modify the entity in the database.

## 2. Automatic package scanning rules

Spring Data REST discovers projection definitions based on the domain type's package:

- An interface annotated with \`@Projection\` located in **the same package as the domain type** is registered.
- An interface located in **a sub-package** of the domain type's package is also registered.
- An interface located outside that package tree must be registered explicitly if Spring Data REST is to use it.

Example structure:

~~~text
com.example.people
├── Person.java
├── PersonRepository.java
└── projection
    ├── PersonSummary.java
    └── PersonWithAddress.java
~~~

With \`Person\` in the \`com.example.people\` package, interfaces in \`com.example.people\` and \`com.example.people.projection\` fall within the package discovery scope described above.

Example projection in a sub-package:

~~~java
package com.example.people.projection;

import com.example.people.Person;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Spring Data REST can discover this interface according to the package rules of the Person domain type. No separate bean is needed for the projection just to register it via package scanning.

### Packages are resolved relative to the domain type

The anchor of the rule is the package containing the entity/domain type, not an arbitrary application package. For example:

~~~text
com.example.domain.people.Person
com.example.api.projections.PersonSummary
~~~

In this layout, \`com.example.api.projections\` is neither Person's package nor a sub-package of \`com.example.domain.people\`. Simply placing the interface in a package scanned by Spring component scan does not guarantee that Spring Data REST will automatically recognize it as a projection.

If you want to keep projections in a shared package such as \`com.example.api.projections\`, register them explicitly using projection configuration.

### Package rules do not depend on the interface name

The interface name can be \`PersonSummary\`, \`PersonListView\`, or another name. Discovery is based on package location and the \`@Projection\` annotation, not on a \`Projection\` suffix in the class name.

Likewise, the public name of the projection is the \`name\` attribute:

~~~java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
~~~

The client calls \`?projection=summary\`, even though the interface name remains \`PersonSummary\`.

## 3. The @Projection annotation determines which domain types a projection applies to

A projection interface must have \`@Projection\`:

~~~java
@Projection(
    name = "personSummary",
    types = { Person.class }
)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Two key attributes:

| Attribute | Role |
|---|---|
| \`name\` | The projection name that clients use in the \`projection\` query parameter. |
| \`types\` | The domain types to which the projection is allowed to apply. |

The projection interface declares getters for the properties to include in the view. You can declare getters for nested properties or associations, provided the return types and projection semantics match.

Example projection for a Person with an address:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    String getLastName();

    AddressView getAddress();

    interface AddressView {
        String getCity();
        String getCountry();
    }
}
~~~

Projections can be nested to select the required fields of related objects. This lets clients receive a representation tailored to their use case without always loading the entire domain graph.

If a projection applies to multiple domain types, declare the appropriate source types in \`types\`. Do not register a projection for a domain type that is incompatible with its getters.

## 4. When is explicit projection registration needed?

Explicit registration is useful when:

- Projections live in a shared package outside the domain type's package and its sub-packages.
- The project wants to group projections into a dedicated API module.
- Package layout is organized by bounded context or module, making it inconvenient to place interfaces next to entities.
- The application wants explicit control over which projections are added to the Spring Data REST registry.
- Projections need to be registered from another module or library not covered by the domain type's package scan rules.

Manual registration does not bypass the annotation requirement. The projection interface must still carry \`@Projection\`; the registry needs the metadata to determine the corresponding name and source types.

## 5. Explicit registration with RepositoryRestConfigurer

Spring Data REST provides \`RepositoryRestConfiguration.getProjectionConfiguration()\`. Call \`addProjection(...)\` to register a projection:

~~~java
package com.example.config;

import com.example.api.projections.PersonSummary;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestProjectionConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getProjectionConfiguration()
              .addProjection(PersonSummary.class);
    }
}
~~~

Here:

- \`RepositoryRestConfigurer\` is the extension point for customizing Spring Data REST.
- \`configureRepositoryRestConfiguration\` receives the exporter configuration.
- \`getProjectionConfiguration()\` returns the registry managing projection definitions.
- \`addProjection(PersonSummary.class)\` registers the projection interface for Spring Data REST lookup.

The projection interface still carries the annotation:

~~~java
package com.example.api.projections;

import com.example.domain.people.Person;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

This example places the projection in \`com.example.api.projections\`, outside the \`com.example.domain.people\` package. Explicit registration enables Spring Data REST to find the projection even though the package is outside the auto-scan scope.

### Registering with explicit source types

The projection configuration also provides an overload accepting source types:

~~~java
config.getProjectionConfiguration()
      .addProjection(PersonSummary.class, Person.class);
~~~

This overload lets you explicitly specify the domain type to which the projection applies. The API also has an overload accepting a projection name and source types:

~~~java
config.getProjectionConfiguration()
      .addProjection(
          PersonSummary.class,
          "personSummary",
          Person.class
      );
~~~

When \`name\` and \`types\` are already declared in \`@Projection\`, calling \`addProjection(PersonSummary.class)\` is usually sufficient. Use the overloads with source type or name when you want to configure the mapping explicitly according to the Spring Data REST version in use. Avoid registering the same projection multiple times through multiple mechanisms unless there is a necessary reason.

## 6. Combining package scanning and explicit registration

An application can use both approaches, for example:

~~~text
com.example
├── domain
│   └── people
│       ├── Person.java
│       └── projection
│           └── PersonListView.java
├── api
│   └── projections
│       └── PersonSummary.java
└── config
    └── RestProjectionConfiguration.java
~~~

- \`PersonListView\` is in a sub-package of the domain type, so it can be discovered automatically.
- \`PersonSummary\` is in a shared API package, so it is registered explicitly via \`RepositoryRestConfigurer\`.

This organization works well when some projections are local to the domain while others are managed in a separate API layer or module.

However, the projection list must be managed clearly. If a projection is both auto-scanned and manually added to the registry, do not rely on duplicate-registration behavior across versions. Choose one consistent registration method per projection and verify the result via API metadata.

## 7. Using a projection after registration

Suppose the Person repository is exported at \`/api/people\`, and the projection is named \`personSummary\`.

Reading a single item:

~~~http
GET /api/people/42?projection=personSummary
Accept: application/hal+json
~~~

Reading a collection:

~~~http
GET /api/people?projection=personSummary
Accept: application/hal+json
~~~

In both cases, Spring Data REST uses the registered projection to build the appropriate representation. The specific response structure depends on the projection's getters and the requested resource.

If a client sends a projection name that is not registered or does not apply to the resource's source type, the server cannot apply that view. Check the name in \`@Projection(name = ...)\`, the source type in \`types\`, and registration before debugging the JSON body.

### Query parameter name

By default, the query parameter name used to select a projection is \`projection\`. The projection registry allows configuring the parameter name, so if the application changes this setting, clients must use the actual name published by the API.

Do not use the interface name as the query parameter unless it matches the \`name\` attribute in the annotation.

## 8. Projections and excerpt projections

Regular projections are selected by the client via a query parameter. An excerpt projection is a projection applied by default when Spring Data REST embeds a resource inside a collection or related resource.

You can specify an excerpt projection on the repository:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

When the \`/api/people\` collection embeds Persons, Spring Data REST uses \`PersonSummary\` as the default preview for embedded items.

An excerpt projection does not automatically apply to a request for a single item such as \`GET /api/people/42\`. To use a projection for an item resource, the client must request it explicitly using the projection query parameter.

If the excerpt projection lies outside Person's discovery package, register it explicitly so the registry knows about it. The \`excerptProjection\` attribute on the repository references the projection class; it does not replace the \`@Projection\` annotation on the interface.

## 9. Discovering projections via profile and ALPS

Spring Data REST publishes metadata to help clients inspect representations. The root resource usually provides a \`profile\` relation. From the resource's profile, clients can locate ALPS metadata and projection options.

Example of an illustrative ALPS snippet:

~~~json
{
  "descriptors": [
    {
      "name": "projection",
      "type": "SEMANTIC",
      "descriptors": [
        {
          "name": "personSummary",
          "type": "SEMANTIC",
          "descriptors": [
            {
              "name": "firstName",
              "type": "SEMANTIC"
            },
            {
              "name": "lastName",
              "type": "SEMANTIC"
            }
          ]
        }
      ]
    }
  ]
}
~~~

The snippet above illustrates a projection named \`personSummary\` and the properties that the view exposes. Actual ALPS responses contain additional descriptors and metadata.

You can verify this following the flow:

1. Call the API root or collection resource.
2. Read the \`profile\` relation in \`_links\`.
3. Follow the resource's profile URI.
4. Locate the \`projection\` descriptor in ALPS.
5. Check the projection name and property descriptors.
6. Use the exact projection name in the query parameter.

This confirms that the projection is published at the API level. There is no need to rely on Java file names or guess from packages.

## 10. Distinguishing package discovery errors from projection mapping errors

When a projection does not appear or cannot be used, determine which of the following categories the error belongs to:

| Symptom | Possible cause | Check |
|---|---|---|
| Interface has \`@Projection\` but is missing in the API | Located outside the domain package and not manually registered. | Domain type package, projection package, \`addProjection\`. |
| Projection is discovered but does not apply to Person | \`types\` points to a different domain type. | \`@Projection(types = ...)\` or the source type overload. |
| Sending \`?projection=PersonSummary\` does not return the expected view | Using the interface name instead of the annotation name. | \`@Projection(name = ...)\`. |
| Projection is not registered despite being in the right package | Missing \`@Projection\`, wrong import, or invalid source type. | Annotation \`org.springframework.data.rest.core.config.Projection\`. |
| Collection has excerpt but item does not | Excerpt applies automatically only to embedded resources. | Call the item with the projection query parameter if needed. |
| Registry is configured but client sees no option | Configuration class is not picked up as a Spring bean or callback is not invoked. | \`RepositoryRestConfigurer\` bean, ApplicationContext, and startup logs. |
| Multiple projections exist for the same purpose | Scattered registration configuration or inconsistent names. | Registry, projection names, and package layout. |

Do not confuse projection package discovery with repository scanning. Repositories are discovered according to the repository detection strategy; projections are found according to the domain type package rules or added to the projection configuration.

## 11. Common pitfalls

1. **Placing a projection in an API package and expecting auto-discovery.** The default rule is based on the domain type's package and its sub-packages.
2. **Placing a projection in a sub-package but forgetting the annotation.** The interface must have \`@Projection\` even when the package is within the scan scope.
3. **Confusing the repository package with the entity package.** Use the domain type's package as the reference point when locating projections.
4. **Using the interface name in the query parameter.** The value sent by the client must match \`@Projection(name = ...)\`.
5. **Missing source type.** A projection must declare the domain types it applies to.
6. **Using explicit registration without creating a configurer bean.** Ensure the configuration class is managed by Spring in the ApplicationContext.
7. **Assuming component scan replaces the projection registry.** Placing an interface in a component-scanned package does not automatically guarantee Spring Data REST registered it.
8. **Assuming an excerpt projection always applies to item resources.** Excerpts are the default for resources embedded in collections or related resources.
9. **Registering a projection for the wrong domain type.** Check \`types\` and the source type passed to \`addProjection\`.
10. **Not inspecting API metadata.** Follow profile/ALPS to confirm the published projection name.
11. **Using projections to protect sensitive data.** A projection selects representations; it is not an authorization boundary.
12. **Failing to control projections that can expose hidden data.** Getters in a projection can reveal properties hidden by the default representation, including some properties marked with \`@JsonIgnore\`. Do not create projections for sensitive fields and still enforce security on the server.

## 12. Implementation checklist

- The projection interface has \`@Projection\`.
- \`name\` is set stably and is the name used by clients.
- \`types\` points to the correct domain types.
- If using package scanning, the interface is in the same package or a sub-package of the domain type.
- If located outside that package tree, \`getProjectionConfiguration().addProjection(...)\` has been called.
- The \`RepositoryRestConfigurer\` class is registered in the ApplicationContext.
- The same projection is not unnecessarily registered through multiple mechanisms.
- Query parameters are sent using the configured projection name.
- Excerpt projection is declared on the right repository if a default preview is needed.
- Clients do not assume the excerpt automatically applies to item resources.
- Profile/ALPS exposes the projection as expected.
- Projections do not expose sensitive data.
- Security still verifies access permissions independently of projections.

## Summary

Spring Data REST locates projections based on the domain type's package: interfaces annotated with \`@Projection\` in the same package or a sub-package are automatically registered. If a projection resides outside that package tree, the application can register it explicitly via \`RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)\`, typically inside a \`RepositoryRestConfigurer\` callback.

In both cases, the projection interface must carry \`@Projection\`, declaring its name and source types. Clients select a projection using the query parameter defaulting to \`projection\`, with a value matching the \`name\` attribute. ALPS/profile helps discover exposed projections. Excerpt projections can serve as the default view for items embedded in collections, but do not automatically apply to standalone item resources.

Choose your package layout intentionally, explicitly register projections outside the scan scope, and inspect API metadata. Projections determine the returned representation; they do not replace authorization and should not be used to conceal sensitive data.

## References

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Data REST — ProjectionDefinitionConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/ProjectionDefinitionConfiguration.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html)
