# The Relationship Between Spring Data REST, Spring Data, Spring MVC, and Spring HATEOAS

These four components belong to different parts of the Spring ecosystem. They work together to create a data-driven REST API, yet each component addresses a distinct responsibility:

- **Spring Data** provides the data access model and abstractions such as `Repository`.
- **Spring Data REST** exports Spring Data Repositories as REST resources, allowing CRUD endpoints to be created without writing a controller for every repository.
- **Spring MVC** receives and processes HTTP requests in a Servlet application: mapping URLs, invoking handlers, converting requests/responses, and handling errors.
- **Spring HATEOAS** supports hypermedia-driven resource representations, especially navigation links and the HAL format.

You can remember the main relationship as follows: Spring Data describes how the application accesses data; Spring Data REST exposes repositories over HTTP; Spring MVC provides the web infrastructure for that HTTP flow; Spring HATEOAS adds links that help clients discover the API.

## 1. Role of each component

### Spring Data: the data access layer

Spring Data is a family of projects, not a REST framework. It provides shared abstractions for working with various kinds of data stores. Specific modules implement those abstractions for each technology, such as:

- Spring Data JPA: works with relational databases via JPA.
- Spring Data JDBC: accesses relational databases using the JDBC model.
- Spring Data MongoDB: works with MongoDB.
- Spring Data Redis: works with Redis.
- Spring Data Elasticsearch: works with Elasticsearch.

A repository is typically an interface describing data operations:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {
    List<Person> findByNameContainingIgnoreCase(String name);
}
~~~

When the application starts, Spring Data generates an appropriate implementation for the repository based on the active module and configuration. In the example above, Spring Data JPA provides an implementation that uses JPA to query the database.

With Spring Data alone, the application can inject the repository into a service or controller and call it from Java. A repository **does not automatically become an HTTP endpoint** simply because it extends `JpaRepository`.

### Spring Data REST: exporting repositories as REST resources

Spring Data REST builds on top of Spring Data Repositories and automatically exports repositories allowed to be exported as REST resources. It provides the mapping from repository operations to HTTP endpoints, resource management, associations, pagination, sorting, search resources, and hypermedia representations.

For example, a repository managing `Person` can provide:

- Collection endpoints to list and create `Person` instances.
- Item endpoints to read, update, or delete a `Person`.
- Search endpoints for exported query methods.
- Links to associations between domain objects.

Spring Data REST reduces boilerplate for CRUD APIs whose structure closely mirrors repositories. It does not design the application's business logic: complex business rules, multi-step workflows, external system integrations, and specialized API contracts still require appropriate services and controllers.

### Spring MVC: HTTP processing infrastructure

Spring MVC is part of Spring Framework and implements the Servlet web model. Its central component is `DispatcherServlet`. An incoming request enters the application and is mapped to the appropriate handler; other components handle arguments, data conversion, validation, exceptions, and responses.

In a Spring Data REST configuration using WebMVC, Spring Data REST integrates into the Spring MVC infrastructure to receive requests and serve repository resources. Therefore:

- Spring MVC is responsible for the HTTP processing flow of the Servlet application.
- Spring Data REST provides the handlers and rules for repositories to become REST resources.
- Spring MVC does not decide whether data is stored in JPA, MongoDB, or Redis.
- Spring Data REST does not replace all of Spring MVC. Both mechanisms can coexist in the same application.

An application-written controller can still use Spring MVC:

~~~java
@RestController
@RequestMapping("/reports")
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping
    public List<ReportDto> getReports() {
        return reportService.findAll();
    }
}
~~~

This controller serves an endpoint designed by the application. It does not automatically become a Spring Data REST repository resource.

### Spring HATEOAS: hypermedia representations and links

HATEOAS stands for Hypermedia as the Engine of Application State. In a hypermedia API, responses contain links describing the next actions or related resources a client can access. Clients can discover the API from links in responses rather than assembling every URL from internal server conventions.

Spring HATEOAS provides data types and utilities to build such representations, for example:

- **Link**: a link with a relation and a target URI.
- **EntityModel**: wraps a domain object or DTO and attaches links.
- **CollectionModel**: wraps a collection of resources and collection links.
- **PagedModel**: represents a paginated collection.
- **RepresentationModelAssembler**: converts a domain object into a representation model.

Spring Data REST uses Spring HATEOAS's hypermedia capabilities to return resources with links. A common format is HAL JSON, with fields such as **_links** and **_embedded**.

Spring HATEOAS does not query databases and does not generate CRUD endpoints on its own. It focuses on how resources are represented and how clients navigate between resources.

## 2. How the components work together

In a Spring Boot application using Spring Data JPA and Spring Data REST on the Servlet stack, the high-level flow is as follows:

~~~mermaid
flowchart TD
    C["HTTP client"] --> M["Spring MVC"]
    M --> R["Spring Data REST"]
    R --> D["Spring Data Repository"]
    D --> S["Spring Data JPA"]
    S --> J["JPA provider"]
    J --> DB[("Database")]
    R -. "builds representation and links using" .-> H["Spring HATEOAS / HAL"]
    H -. "serialized into HTTP response by" .-> M
~~~

Walking through a `GET` request to `/people`:

1. The client sends an HTTP request to the application.
2. Spring MVC's `DispatcherServlet` receives the request and routes it to the corresponding handler.
3. Spring Data REST recognizes the exported resource and identifies the repository to invoke.
4. The Spring Data Repository performs the operation. For a repository based on `JpaRepository`, the Spring Data JPA implementation runs the query via the JPA provider.
5. Spring Data REST receives the result and constructs the resource representation. Spring HATEOAS helps add the `self` link and links to collections, searches, or associations.
6. Spring MVC converts the representation into an HTTP response and sends it back to the client.

Each layer answers a distinct question:

| Component | Question it answers |
|---|---|
| Spring Data | Through which abstraction does the application access data? |
| Spring Data REST | Which repositories are exported as REST resources and which endpoints are provided? |
| Spring MVC | How are HTTP requests received, routed, and returned as responses? |
| Spring HATEOAS | In what hypermedia structure do responses include data and navigation links? |
| Spring Data JPA (example) | How is the repository executed against a relational database using JPA? |

## 3. Example: exposing `PersonRepository` as a REST API

The example below uses Spring Boot, Spring Data JPA, Spring Data REST, and H2 for illustration. The code snippets are separate files within the same Spring Boot application containing a startup class annotated with `@SpringBootApplication`.

### 3.1. Declaring dependencies

With Gradle and Spring Boot dependency management, add the following dependencies to the existing `dependencies` block:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-data-rest'
    runtimeOnly 'com.h2database:h2'
}
~~~

Spring Boot starters manage compatible versions. You should not manually pick disparate versions of Spring Data REST, Spring Data JPA, and Spring HATEOAS when the project already uses Spring Boot dependency management.

### 3.2. Domain entity

File `Person.java`:

~~~java
package example.people;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Person() {
        // Constructor required by JPA.
    }

    public Person(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

The example uses Jakarta Persistence as in Spring Boot 3+ applications. Older Spring Boot 2 projects use the `javax.persistence` namespace.

### 3.3. Repository and REST resource configuration

File `PersonRepository.java`:

~~~java
package example.people;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people",
    itemResourceRel = "person"
)
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    List<Person> findByNameContainingIgnoreCase(@Param("name") String name);
}
~~~

Meaning of the annotations:

- **@RepositoryRestResource** marks the repository to be exported by Spring Data REST. **path = "people"** sets the collection path; **collectionResourceRel = "people"** sets the relation used when embedding the collection in HAL; **itemResourceRel = "person"** sets the relation for individual items.
- **@RestResource** customizes the path and relation of the query method.
- **@Param("name")** names the query parameter that clients pass to the search endpoint.

Because the repository is exported, there is no need to write a separate CRUD controller for `Person` just to invoke basic repository methods.

### 3.4. Database configuration for the example

File `application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:people
spring.jpa.hibernate.ddl-auto=create-drop
spring.h2.console.enabled=true
~~~

The configuration above creates an in-memory H2 database for the application run. This is an illustrative configuration; real applications need database, migration, transaction, and schema policies suited to the deployment environment.

Run the application using the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows you can use:

~~~powershell
.\gradlew.bat bootRun
~~~

### 3.5. Provided endpoints

With the repository above and the default base path, typical requests are:

| HTTP method | Endpoint | Meaning |
|---|---|---|
| GET | `/people` | Retrieve the Person collection |
| POST | `/people` | Create a new Person |
| GET | `/people/{id}` | Retrieve a single Person |
| PUT | `/people/{id}` | Replace a Person representation |
| PATCH | `/people/{id}` | Partially update a Person |
| DELETE | `/people/{id}` | Delete a Person |
| GET | `/people/search/by-name?name=ada` | Search for Person by name |

Specific available operations also depend on the exported repository, Spring Data REST configuration, and request permissions.

Example creating a `Person`:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"name":"Ada Lovelace"}' \
  http://localhost:8080/people
~~~

Example reading the collection:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/people
~~~

Example calling the search resource:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/people/search/by-name?name=ada"
~~~

### 3.6. Reading the HAL response

A collection response may have an illustrative structure like the following (actual URIs and counts depend on live data):

~~~json
{
  "_embedded": {
    "people": [
      {
        "name": "Ada Lovelace",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/1"
          },
          "person": {
            "href": "http://localhost:8080/people/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "profile": {
      "href": "http://localhost:8080/profile/people"
    },
    "search": {
      "href": "http://localhost:8080/people/search"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

Notable parts:

- **_embedded.people** contains items in the collection under the configured relation.
- **_links.self** points to the current resource itself.
- **_links.person** is the link to the item under the configured relation.
- **_links.search** indicates the search resource discoverable from the collection.
- **page** describes pagination information.

HAL is not just JSON containing data. Links indicate where the client can go next. A hypermedia client should read links by relation rather than assuming every URI always follows a fixed structure.

## 4. When to use Spring Data REST and when to write custom controllers?

Spring Data REST works well when a resource aligns closely with a repository and the API primarily provides standard data operations. For example: an internal admin application needing CRUD for several entities, or a service exposing repository resources with pagination, search, and hypermedia links.

Consider custom-designed services/controllers when an endpoint represents a business action rather than an entity. For example:

- Placing an order requires checking inventory, calculating prices, applying discount codes, recording payment, and publishing events.
- A single request must coordinate multiple repositories or call external systems.
- A public API requires dedicated DTOs, versioning rules, validation, and a contract-stable response structure.
- Read/write permissions vary by data field or by business state.
- You do not want clients interacting directly with internal entities and repositories.

Both approaches can coexist. Use Spring Data REST for simple repository resources, and use services and Spring MVC controllers for business use cases. Keeping business logic in services lets both custom controllers and other flows reuse the same rules.

## 5. Customizing and controlling exports

Spring Data REST offers common extension points:

- **@RepositoryRestResource(path = "...")** changes the resource path; **exported = false** can be set to disable exporting a repository.
- **@RestResource(path = "...", rel = "...")** customizes a search method or association; **exported = false** can be set to hide a method from the REST API.
- **RepositoryRestConfigurer** customizes global settings such as base path, export behavior, and certain representation rules.
- **Projections** and excerpt projections let you select which properties appear in representations.
- Spring Data REST validation and event mechanisms can participate in the repository operation lifecycle.

Projections only adjust the represented data; they do not replace access control. If the API handles sensitive data, you must configure authorization and verify permissions at the endpoint, repository/service, and operation levels.

Exporting a repository can also expose write operations. Before publishing an API, clearly determine which repositories are accessible, which methods are allowed to be called, and who is permitted to read or modify data. Do not treat Spring Data REST's automatic endpoint generation as a security policy.

## 6. Common misconceptions

1. **Spring Data does not equal Spring Data REST.** Spring Data provides data access abstractions; Spring Data REST is an optional component that exports repositories as REST resources.
2. **Spring MVC is not the persistence layer.** MVC handles HTTP requests/responses; Spring Data and store-specific modules handle data access.
3. **Spring Data REST is not a repository implementation.** It invokes repositories created by Spring Data and provides a way to access repositories over HTTP.
4. **Spring HATEOAS is not a REST controller or ORM.** It assists in building hypermedia representations and links.
5. **Having a repository does not mean it must be exported.** A repository can be used strictly internally by services.
6. **Having a link does not mean the client is authorized to access it.** Authorization must still be checked when the client calls the target endpoint.
7. **Do not assume every association is embedded as a full object.** Spring Data REST typically provides links to association resources; the exact representation depends on configuration, projections, and access patterns.
8. **Do not couple clients to hand-built URIs if the API already provides links.** Using relations in HAL keeps clients less dependent on internal URL structures.

## 7. Cheat sheet

| Component | Primary responsibility | Easily recognizable examples |
|---|---|---|
| Spring Data | Data access abstraction | `JpaRepository`, `CrudRepository` |
| Spring Data REST | Exporting repositories as REST resources | `@RepositoryRestResource`, `/people` |
| Spring MVC | Handling requests/responses on the Servlet stack | `DispatcherServlet`, `@RestController`, `@GetMapping` |
| Spring HATEOAS | Creating representations with hypermedia links | `Link`, `EntityModel`, `CollectionModel`, HAL |
| Spring Data JPA | Executing repositories on JPA | `JpaRepository`, entity mapping |

When reading a Spring application, trace requests from the controller or Spring Data REST handler, to the service/repository, and then to the storage module. When reading a HAL response, distinguish domain data in the body from links provided by Spring HATEOAS. Viewing the system through these responsibilities helps pinpoint where to add endpoints, business rules, data queries, or navigation links.

## 8. Official documentation

- Spring Data REST: https://docs.spring.io/spring-data/rest/reference/
- Spring Data Repository abstraction: https://docs.spring.io/spring-data/commons/reference/repositories.html
- Spring Framework — Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring HATEOAS: https://docs.spring.io/spring-hateoas/docs/current/reference/html/
- Spring Boot — Spring Data REST: https://docs.spring.io/spring-boot/reference/data/nosql.html
