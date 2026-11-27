# Declaring a @Projection Interface with name and types

Spring Data REST can return multiple different representations for the same entity. A **Projection** lets you define a read-only view using an interface: the interface declares which properties should appear in the response, and Spring Data generates a proxy implementation to read data from the entity.

The **@Projection** annotation binds a projection to one or more domain types and assigns a name so clients can select that view. The two attributes to understand clearly are:

- **`name`**: the identifier name of the projection, used in the **`projection`** query parameter.
- **`types`**: the domain types to which the projection applies, typically entity classes such as **`Person.class`**.

Projections help control REST representations without creating a separate DTO and controller for every display format.

## 1. @Projection declares a view using an interface

The **`@Projection`** annotation belongs to the package:

~~~java
import org.springframework.data.rest.core.config.Projection;
~~~

Example Person entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phone;
    private boolean active;

    // getters and setters
}
~~~

Create a projection interface containing only the getters to expose:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "summary", types = { Person.class })
public interface PersonSummary {

    String getFirstName();

    String getLastName();

    boolean isActive();
}
~~~

In this declaration:

- **`PersonSummary`** is the Java interface name.
- **`name = "summary"`** is the projection name clients use to select the view.
- **`types = { Person.class }`** indicates that the projection applies to the **`Person`** domain type.
- The getters determine which properties are included in the representation.

The interface name and the **`name`** value do not have to be identical. Choose a short, meaningful, and stable name so clients can use it easily.

## 2. Understanding the name attribute

**`name`** is the identifier of the projection in Spring Data REST. For example:

~~~java
@Projection(name = "summary", types = { Person.class })
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
~~~

The client selects the projection using the query parameter:

~~~http
GET /people/1?projection=summary
Accept: application/hal+json
~~~

The response only displays the properties exposed by the projection along with the necessary HAL metadata/links. For example, the data portion might look like this:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/1"
    }
  }
}
~~~

If the projection name is changed to **`compact`**, the client must also use:

~~~http
GET /people/1?projection=compact
~~~

The projection name is part of the contract that clients depend on. When renaming it, update the clients sending the old query parameter.

## 3. Understanding the types attribute

**`types`** specifies the domain types to which the projection applies. It is a class array, so you can declare one or more domain types if the same projection interface fits those types.

Example applying to Person:

~~~java
@Projection(name = "summary", types = { Person.class })
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
~~~

If a projection genuinely works across multiple domain types that share the same readable properties, you can declare:

~~~java
@Projection(
    name = "named",
    types = { Person.class, Employee.class }
)
public interface NamedSummary {
    String getName();
}
~~~

The listed types must have properties compatible with the getters in the projection. If a type lacks a property required by the interface, creating the representation for that type may fail.

Avoid adding multiple classes to **`types`** just to reuse a projection name. Make sure every declared domain type has a matching getter contract.

## 4. Where to place the projection interface

Spring Data REST needs to discover the projection interface when initializing repository configuration. By convention, place the interface annotated with **`@Projection`** in the same package as the domain type or in a subpackage of that package.

Example structure:

~~~text
com.example.demo
├── person
│   ├── Person.java
│   └── PersonSummary.java
└── repository
    └── PersonRepository.java
~~~

If **`Person`** is in the package **`com.example.demo.person`**, the **`PersonSummary`** projection placed in the same package will be discovered by convention.

If the projection is outside the scanned packages, the **`projection=summary`** query parameter might not be recognized as expected. Check the domain type's package, the interface's location, and the application's scan configuration.

## 5. Getters determine the exported properties

A projection interface usually declares getters corresponding to entity properties:

| Getter in projection | Property read |
|---|---|
| **`String getFirstName()`** | **`firstName`** |
| **`String getEmail()`** | **`email`** |
| **`boolean isActive()`** | **`active`** |
| **`AddressSummary getAddress()`** | **`address`** relationship via nested projection |

Declare only the getters that the client needs. For example, if you do not want to expose the phone number, do not add **`getPhone()`** to the projection.

The projection interface does not need manual implementations of the getters. Spring Data creates a proxy to read values from the entity when building the representation.

A projection is a read-only view. It does not modify the entity, does not write data to the database, and does not replace authorization mechanisms. Do not expose a sensitive property simply because a getter can read it.

## 6. Nested projections for relationships

A projection can return another projection to shape the representation of a relationship.

For example, a Person entity has a relationship to Address:

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String city;
    private String street;

    // getters and setters
}
~~~

Create a projection for Address:

~~~java
@Projection(name = "addressSummary", types = { Address.class })
public interface AddressSummary {

    String getCity();
}
~~~

Then use this projection in Person:

~~~java
@Projection(name = "withAddress", types = { Person.class })
public interface PersonWithAddress {

    String getFirstName();

    AddressSummary getAddress();
}
~~~

When the client calls:

~~~http
GET /people/1?projection=withAddress
~~~

the representation can include **firstName** and the address part limited by **AddressSummary**. This avoids exporting all properties of the related object when the client only needs a subset.

Nested projections need to be discovered and have getters compatible with the actual relationship. For a collection association, the getter can return a matching collection or list of projections, such as **`List<RoleSummary> getRoles()`**.

## 7. Computed properties and open projections

In addition to getters mapping directly to properties, a projection interface can provide computed properties.

One approach is using a default method based on other getters:

~~~java
@Projection(name = "nameCard", types = { Person.class })
public interface PersonNameCard {

    String getFirstName();

    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

Another approach is using **`@Value`** with SpEL:

~~~java
import org.springframework.beans.factory.annotation.Value;

@Projection(name = "fullName", types = { Person.class })
public interface PersonFullName {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
~~~

Projections that use SpEL as shown above are typically called open projections. Because the expression can reference many properties of the target, the framework has difficulty determining the exact set of properties to load upfront. Whenever possible, prefer closed projections with direct getters or default methods based on declared getters.

## 8. Selecting a projection when calling the REST API

Once a projection is discovered, clients can select it using the **`projection`** query parameter on resources that support projections.

Example fetching a single item:

~~~http
GET /people/1?projection=summary
Accept: application/hal+json
~~~

Example fetching a collection:

~~~http
GET /people?projection=summary
Accept: application/hal+json
~~~

If **`projection`** is omitted, Spring Data REST returns the default representation of the resource, according to the configuration and excerpt projections if any.

The selected projection only shapes the data portion of the representation. Resource URIs, pagination, HAL links, and access permissions still follow the corresponding endpoint configuration.

## 9. Setting a default excerptProjection for collections

If you want a collection to always use a specific projection when embedding items, you can configure **`excerptProjection`** on **`@RepositoryRestResource`**.

Example:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(excerptProjection = PersonSummary.class)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

When a client calls:

~~~http
GET /people
Accept: application/hal+json
~~~

items embedded in the collection representation can use **`PersonSummary`** as the default excerpt.

Excerpt projections primarily control how items are displayed inside collections. When reading an individual item resource, clients can still select a projection via the query parameter if the projection is exposed.

Specifying **`excerptProjection`** must point to a projection interface compatible with the repository's domain type. If no default excerpt is needed, this attribute can be omitted.

## 10. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| **`projection=summary`** has no effect | Projection is not discovered or the name does not match | Check **`@Projection`**, package, and the **`name`** value |
| Projection does not apply to the entity | **`types`** is missing or declares the wrong domain class | Add the correct class to the **`types`** array |
| Response is missing an expected property | Getter does not match the property or the property is not provided | Check the getter name and entity model |
| Nested projection does not render properly | Getter returns the wrong type or child projection is not discovered | Check the relationship type and child projection interface |
| Collection does not use the expected default excerpt | Repository has not configured **`excerptProjection`** or the class does not match | Check the annotation on the repository |
| Projection exposes sensitive data | Interface has a getter for a property that should not be exposed | Remove unnecessary getters and apply proper authorization |

## 11. Hands-on workflow

You can practice with **Person**:

1. Create a **`Person`** entity with properties **`firstName`**, **`lastName`**, **`email`**, and **`phone`**.
2. Create a **`PersonSummary`** interface with **`@Projection(name = "summary", types = { Person.class })`**.
3. Declare getters only for **`firstName`**, **`lastName`**, and the properties the client needs.
4. Place the interface in a package discovered by Spring Data REST.
5. Start the application and call **`GET /people/1?projection=summary`**.
6. Verify that the response contains the selected properties and omits the excluded properties.
7. If you want the collection to use this view by default, configure **`excerptProjection = PersonSummary.class`** on the repository and call **`GET /people`**.

Complete interface example:

~~~java
package com.example.demo.person;

import org.springframework.data.rest.core.config.Projection;

@Projection(name = "summary", types = { Person.class })
public interface PersonSummary {

    String getFirstName();

    String getLastName();

    boolean isActive();
}
~~~

Example request:

~~~http
GET http://localhost:8080/people/1?projection=summary
Accept: application/hal+json
~~~

Compare the response with the projection against the default response to clearly see how the projection changes the representation.

## 12. API design notes

- Keep **`name`** concise, meaningful, and stable since clients use this name in URLs.
- Declare the exact domain classes in **`types`**; only use multiple types when the getters are genuinely compatible.
- Include in the projection only the getters needed for the use case.
- Use nested projections to control association data.
- Prefer closed projections whenever possible so the framework can determine the properties to read more clearly.
- Use **`excerptProjection`** when you want to set a default view for items embedded in collections.
- Projections only control representations; they do not replace security, validation, or data access restrictions.

Official references:

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Projection annotation API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/Projection.html)
