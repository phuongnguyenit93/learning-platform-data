# Prerequisite Knowledge and Learning Order for Spring Data REST

Spring Data REST publishes Spring Data repositories as HTTP resources by convention. When a repository is exported, the framework can provide endpoints for reading, creating, updating, deleting, searching, and managing links between resources without writing a separate CRUD controller for every entity. Data is typically represented in JSON using HAL, along with links so clients can discover the API.

The goal of this article is to help learners know what prerequisites to master first, understand the processing flow of Spring Data REST, build a small application, and follow a solid learning order to use the framework safely in real projects.

## 1. What is Spring Data REST?

Spring Data REST sits on top of Spring Data's repository abstraction. Applications still define repositories just as when using Spring Data JPA, Spring Data MongoDB, or another Spring Data module. Spring Data REST inspects exported repositories and publishes them as REST resources.

Distinguish these three components:

- **Spring Data** provides abstractions for data access: repositories, query methods, pagination, sorting, and types like `Page`, `Slice`, and `Pageable`.
- **Spring Data JPA** is a Spring Data module that works with JPA and persistence providers such as Hibernate. It manages entity mapping and relational database operations.
- **Spring Data REST** publishes repositories as a REST API and adds conventions for resources, URIs, HAL, search, projections, events, and endpoint configuration.

Spring Data REST does not design the application's entire business logic. It automates the HTTP layer around repositories. Multi-step business workflows, specialized payloads, complex authorization rules, or APIs requiring a custom contract may still require application-written services and controllers.

Key capabilities:

- Exposing collection resources and item resources from repositories.
- Supporting HTTP operations based on repository capabilities.
- Exposing query methods under a `search` path.
- Supporting pagination, sorting, and filtering via query methods.
- Representing links between resources using hypermedia.
- Allowing customization of paths, relation names, and exported repositories or methods.
- Supporting projections, event handlers, validation, and Spring Security integration.

## 2. Required prerequisite knowledge

You do not need to learn all of Spring Framework before getting started. However, learners should have a foundation in the following areas.

### 2.1. Core Java and object-oriented programming

Be comfortable using:

- Classes, objects, interfaces, access modifiers, and packages.
- Constructors, encapsulation, inheritance, and polymorphism.
- Generic types and generic interfaces, such as `Repository<T, ID>`.
- Collections such as `List`, `Set`, and `Map`.
- Exceptions, enums, annotations, and lambdas at a reading/understanding level.
- `Optional` and handling potentially absent values.
- Getter, setter, and no-arg constructor conventions in JPA-managed classes.

Reason: entities and repositories are Java types. Spring Data uses generics and annotations to infer the entity type, primary key type, and query rules.

### 2.2. HTTP, REST, and JSON

This part is essential because Spring Data REST builds an HTTP API. Understand:

- **Resource**: an entity or concept identified by a URI; for example, a book has its own URI.
- **GET** reads a resource; **POST** typically creates a resource in a collection; **PUT** replaces or updates a resource per the endpoint contract; **PATCH** partially updates; **DELETE** deletes a resource or removes a link depending on the endpoint.
- Common status codes: `200`, `201`, `204`, `400`, `401`, `403`, `404`, `409`, and `500`.
- `Content-Type` header describes the request body format; `Accept` describes the format the client wants to receive.
- JSON objects, arrays, strings, numbers, booleans, and `null`.
- Idempotency: whether repeating a request produces the same state or causes additional side effects.
- Query parameters, path variables, request bodies, and response headers.
- Pagination, sorting, and the meaning of `page`, `size`, and `sort`.
- Hypermedia concept: responses carry links so clients can discover next actions and resources.

Spring Data REST typically returns HAL JSON. Therefore, beyond regular JSON, recognize two key properties:

- **_links** contains links such as `self`, `profile`, or links to related resources.
- **_embedded** contains resources embedded in a collection response.

Do not assume every response is just a flat JSON object.

### 2.3. Spring Framework and Spring Boot

Understand these concepts before exploring automatic exports:

- Inversion of Control and Dependency Injection.
- Beans, `ApplicationContext`, component scanning, and annotation-based configuration.
- Spring Boot auto-configuration and starter dependencies.
- Configuring applications via `application.properties` or `application.yml`.
- Basic Spring MVC: `DispatcherServlet`, controllers, request mapping, message converters, and exception handling.
- Profiles, environment-specific configuration, and how to run the application.

You do not need to write a controller for every repository when using Spring Data REST, yet understanding Spring MVC helps read stack traces, configure HTTP, and integrate custom endpoints.

### 2.4. Spring Data and the persistence layer

Before Spring Data REST, know how to create and use repositories directly:

- Repository abstraction and repository interfaces.
- `CrudRepository` for basic CRUD operations.
- `PagingAndSortingRepository` for pagination and sorting.
- `JpaRepository` when using Spring Data JPA.
- Derived query methods by method name, such as `findByTitleContainingIgnoreCase`.
- Basic `@Query` when custom queries are needed.
- `Optional`, `List`, `Page`, `Slice`, `Pageable`, and `Sort`.
- Differences between entity, repository, service, and controller.

If using JPA, also understand:

- `@Entity`, `@Id`, `@GeneratedValue`, `@Column`, and `@Table`.
- `@OneToOne`, `@OneToMany`, `@ManyToOne`, and `@ManyToMany` relationships.
- Owning side of a relationship and `mappedBy`.
- Fetch types `LAZY`/`EAGER`, `cascade`, and `orphanRemoval`.
- Persistence context, dirty checking, and transactions.
- Entity lifecycle and issues when serializing lazy relationships.

These JPA concepts are vital when the REST API allows clients to read or modify associations between entities. If using MongoDB or another store, substitute JPA knowledge with the data model and relationship rules of that store.

### 2.5. Development tools

Prepare:

- A JDK compatible with the project's Spring Boot version.
- Maven or Gradle and an understanding of dependency management.
- An IDE with Java and Spring support.
- A development database such as H2 or the database used by the project.
- `curl`, HTTPie, or Postman to send requests and inspect status codes, headers, and bodies.
- Git for change management.

Always choose compatible Spring Boot and Spring Data versions via the project's dependency management. Do not arbitrarily mix individual Spring Data versions.

## 3. Processing flow to visualize

For a request reading a list of books, the general flow is as follows:

~~~mermaid
flowchart TD
    A[HTTP client] --> B[Spring MVC]
    B --> C[Spring Data REST]
    C --> D[Repository proxy]
    D --> E[Spring Data module]
    E --> F[Database]
    F --> E
    E --> D
    D --> C
    C --> G[HAL JSON response]
    G --> A
~~~

Spring Data REST receives the request, identifies the corresponding repository resource, invokes the repository proxy, and lets the Spring Data module interact with the store. The result is converted into an HTTP response according to representation and hypermedia configuration.

Importantly, the repository remains the data access point. If business logic is needed before or after a save operation, place it in a service or use appropriate event mechanisms; do not cram all domain rules into entity setters or rely on clients calling endpoints in a specific order.

## 4. Building a minimal Spring Data REST application

The example below uses Java 17+, Spring Boot, Spring Data JPA, and H2. Dependencies are managed by the Spring Boot parent or the project's BOM; choose a Spring Boot version compatible with your JDK and ecosystem.

### 4.1. Maven dependencies

Add the following dependencies to the `dependencies` section of `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If using another database, replace H2 with the corresponding driver and datasource configuration. If using a Spring Data module other than JPA, change the storage starter and entity model accordingly.

### 4.2. Startup class

Create `CatalogApplication.java` in the root package of the application:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` enables application configuration, auto-configuration, and component scanning from the package containing this class downward. Place entities and repositories in subpackages so they are detected automatically.

### 4.3. Book entity

Create `Book.java`:

~~~java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    private String author;

    protected Book() {
        // JPA requires a no-arg constructor.
    }

    public Book(String title, String author) {
        this.title = title;
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getAuthor() {
        return author;
    }

    public void setAuthor(String author) {
        this.author = author;
    }
}
~~~

`@Id` marks the primary key. `@GeneratedValue` lets the database/provider generate the `id` value. `@Entity` and `@Table` map the class to a table. The no-arg constructor allows JPA to instantiate the entity; getters and setters allow the framework and application to access properties.

The example uses field access because `@Id` is placed on the field. In real projects, keep field/property access consistent and design `equals`/`hashCode` carefully, especially for entities with auto-generated IDs.

### 4.4. Exported repository

Create `BookRepository.java`:

~~~java
package com.example.catalog;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(collectionResourceRel = "books", path = "books")
public interface BookRepository extends JpaRepository<Book, Long> {

    @RestResource(path = "by-title", rel = "by-title")
    List<Book> findByTitleContainingIgnoreCase(@Param("q") String q);
}
~~~

`JpaRepository` provides repository operations for the `Book` entity with key type `Long`. `@RepositoryRestResource` sets the collection path to `books` and the relation name to `books`. The search method is exposed under `search` with path `by-title`; `@Param` sets the query parameter name to `q`.

With this configuration, Spring Data REST can publish the collection at `/books` and the search resource at `/books/search/by-title`.

### 4.5. H2 configuration

Add to `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:catalog
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
~~~

H2 runs in memory, so data is recreated when the application starts. `create-drop` suits learning examples; do not use this setting for production data. In production, manage schemas with migration tools like Flyway or Liquibase and configure connection credentials via environment variables or a secret manager.

### 4.6. Running the application and trying the API

In the project directory, run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows you can use:

~~~powershell
mvnw.cmd spring-boot:run
~~~

Once the application starts, try these requests:

Read the API root to view published links:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
~~~

Read the book collection:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/books
~~~

Create a book:

~~~cmd
curl -i -X POST http://localhost:8080/books ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/hal+json" ^
  -d "{\"title\":\"Spring in Action\",\"author\":\"Craig Walls\"}"
~~~

The `POST` command sends JSON to the collection. When creation succeeds, the response typically has status `201 Created` and a `Location` header pointing to the newly created item resource. Line-continuation and quote-escaping syntax in `curl` commands depends on your shell; if using Git Bash or Linux/macOS, replace the line continuation character `^` with a backslash.

Read an item using the URI obtained from `Location` or the `self` link:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/books/1
~~~

Search by title:

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/books/search/by-title?q=spring"
~~~

Paginate and sort:

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/books?page=0&size=10&sort=title,asc"
~~~

`page` usually starts at `0`. `size` is the maximum number of items per page. `sort` can specify a property and direction `asc` or `desc`. Check your application's pagination configuration if you want to cap the maximum page size.

A HAL collection response typically contains `_embedded.books` holding the items, `_links` holding the `self` link and related links, and `page` metadata when the endpoint returns paginated results. Actual URIs and content depend on data, configuration, and version; use links returned by the server as the source of truth.

## 5. Resources, HTTP methods, and HAL

When reading an exported API, distinguish the resource types:

- **API root** at `/` usually lists accessible repository resources.
- **Collection resource** at `/books` represents the set of books.
- **Item resource** at `/books/{id}` represents a single book.
- **Search resource** at `/books/search` holds exported query methods.
- **Association resource** at a URI representing a relationship between two entities, such as `/books/{id}/publisher` if the entity has an exposed `publisher` property.

Common operations:

| Goal | Typical request | Meaning |
|---|---|---|
| Read collection | `GET /books` | Retrieve list and pagination metadata |
| Read item | `GET /books/{id}` | Retrieve a single resource |
| Create item | `POST /books` | Create a resource in the collection |
| Full update | `PUT /books/{id}` | Send representation per `PUT` contract |
| Partial update | `PATCH /books/{id}` | Send only the fields to modify |
| Delete item | `DELETE /books/{id}` | Delete resource if permitted |
| Search | `GET /books/search/by-title?q=...` | Invoke an exported query method |

For associations, Spring Data REST can use the `text/uri-list` media type so clients submit URIs of related resources. For example, when linking a book to a publisher, the request to the association endpoint can contain the publisher's URI. `DELETE` on an association endpoint usually removes the link; that does not mean deleting the publisher entity. Read the endpoint's exact semantics before manipulating relational data.

HAL helps clients follow links provided by the server. Clients should read `href` from `_links` rather than assembling URIs from IDs or assuming paths remain fixed. This makes clients less sensitive to path and relation configuration changes.

## 6. Customizing endpoints and representations

### 6.1. Renaming or hiding a repository

`@RepositoryRestResource` lets you customize collection path, relation, and export status. Example:

~~~java
@RepositoryRestResource(
    collectionResourceRel = "catalogItems",
    path = "catalog-items"
)
public interface BookRepository extends JpaRepository<Book, Long> {
}
~~~

When a repository must not appear over REST, use `exported = false`:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

You can use `@RestResource(exported = false)` on a method to hide a specific query method. Hiding endpoints is part of API design; proper security still must be configured for all remaining endpoints.

### 6.2. Customizing the base path

You can set a global base path, for example in `application.properties`:

~~~properties
spring.data.rest.base-path=/api
~~~

Repository resources are then placed under `/api`. After changing the base path, update documentation, client configs, CORS, and integration tests accordingly.

### 6.3. Query methods

Spring Data derives queries from method names in repositories. Methods such as `findByTitle`, `findByAuthorContainingIgnoreCase`, or `findByPublishedAtAfter` can be published under `search` if exported.

Long method names can become hard to read and unsuitable for complex queries. In those cases consider `@Query`, a custom repository implementation, or a dedicated service/controller. Avoid turning every internal query into a public endpoint.

### 6.4. Projections

Projections restrict which properties appear in a representation. Example:

~~~java
package com.example.catalog;

import org.springframework.data.rest.core.config.Projection;

@Projection(name = "summary", types = Book.class)
public interface BookSummary {
    String getTitle();
}
~~~

This projection declares only the `title` field. When the projection is registered and the endpoint supports it, clients can request the representation using query parameter `projection=summary`. Projections help tailor returned data, but do not replace access control: do not put sensitive data into public projections and do not treat projections as an authorization mechanism.

### 6.5. Event handlers and validation

Spring Data REST provides events around the repository lifecycle, such as before/after create, save, delete, and link updates. You can handle these events with `@RepositoryEventHandler` and annotations like `@HandleBeforeCreate` or `@HandleBeforeSave`.

Use event handlers for checks or tasks directly tied to repository operations. For multi-step business logic requiring explicit transactions, calls across multiple repositories, or external system integration, a service layer is usually easier to control.

Validation must be configured and tested for both create and update. You can use Jakarta Bean Validation annotations like `@NotBlank`, `@Size`, and `@Email`, combined with validators via Spring Data REST's validation event mechanism. Never rely solely on UI checks; HTTP requests can be sent directly.

### 6.6. Custom controllers

When you need endpoints with specialized payloads or behavior, you can add controllers. `@RepositoryRestController` integrates with Spring Data REST's base path and configuration; regular `@RestController` suits MVC APIs managed directly by the application.

Choose custom controllers for business logic or HTTP contracts that do not fit automatic repository operations. Avoid creating a custom endpoint that duplicates a repository endpoint without a clear reason.

## 7. Security and API design

Automatic repository export can expose unintended data or write operations if not designed carefully. Before deploying, make sure to:

1. List which repositories are permitted to be exported; hide internal repositories with `exported = false`.
2. Configure Spring Security for each endpoint group and each read/write operation.
3. Enforce user-level and resource-level permissions when required by business rules; successful authentication does not mean a user may edit every entity.
4. Never return passwords, tokens, personal data, or internal properties through entity representations or projections.
5. Audit associations that could allow users to link entities into relationships they have no permission to manage.
6. Restrict CORS to required origins. CORS does not replace authentication or authorization.
7. Use HTTPS and store secrets outside source code.
8. Review API compatibility, data migrations, logging, and auditing before going to production.

A common design pitfall is publishing persistence entities directly as a long-term API contract. When the database schema changes, representations or relationships may change as well. For systems with multiple clients or versioning requirements, consider DTOs and dedicated controllers/services to govern the API contract.

## 8. Testing endpoints

Unit tests for repositories verify queries and persistence, but are not enough to confirm Spring Data REST exported the expected endpoints. Include integration tests that boot the application context and invoke HTTP endpoints via `MockMvc` or an equivalent testing tool.

Example testing the collection resource with `MockMvc`:

~~~java
package com.example.catalog;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BookApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void exposesBooksCollectionAsHal() throws Exception {
        mockMvc.perform(get("/books")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

This is an integration test for the HTTP representation; it requires the `spring-boot-starter-test` dependency in `test` scope. The test does not depend on whether the collection already contains books because it only verifies the endpoint and `self` link. You can expand it to check:

- `POST` creates data and returns the expected status/headers.
- `GET` item returns the expected fields and links.
- Query methods have the right path names and query parameters.
- Pagination, sorting, and maximum page size limits.
- `PUT`/`PATCH` do not drop data unexpectedly.
- Adding/removing associations respects permissions and relationship semantics.
- Sensitive repositories or fields are not exported.
- Unauthenticated or unauthorized callers receive appropriate status codes.
- Validation returns understandable errors on invalid data.

When testing HAL, verify both data and links. Do not check only JSON fields while ignoring the hypermedia contract.

## 9. Recommended learning order

Follow these steps so each stage builds on the previous one:

1. **Java and HTTP/REST:** review interfaces, generics, annotations, JSON, HTTP methods, status codes, headers, and REST resources. Target outcome: explain the request/response flow of a CRUD API on your own.
2. **Spring Boot and Spring MVC:** create an application, configure beans, run the server, and write a simple `GET`/`POST` controller. Target outcome: know how requests enter Spring and how to read logs when an endpoint fails.
3. **Spring Data:** create repositories, query methods, `Page`, `Pageable`, and `Sort`. Target outcome: query data via repositories without REST export yet.
4. **JPA or your chosen storage module:** create entities, relationships, transactions, and schemas. Target outcome: understand how entities are saved and loaded, especially lazy/cascade relationships.
5. **Basic Spring Data REST:** add the starter, export a repository, and call the API root, collection, and item endpoints. Target outcome: explain which endpoints are generated from which repository.
6. **HAL and HTTP operations:** read `_links`, `_embedded`, pagination, create/update/delete, and associations. Target outcome: write a test client driven by links returned by the server.
7. **Customizing and securing the API:** custom path/rel, search, projections, `exported = false`, validation, event handlers, CORS, and Spring Security. Target outcome: expose only the data and operations the application truly permits.
8. **Integration testing and operations:** verify HTTP contracts, errors, permissions, migrations, logging, and client compatibility. Target outcome: be able to evaluate an API before deployment.

Do not jump straight to projections or event handlers before understanding repositories and HAL. Without understanding JPA associations, linking endpoints will be very hard to verify safely.

## 10. Tiered practice exercises

Use the same `Book` application to avoid constantly switching contexts:

- **Level 1:** export `BookRepository` and use `GET` to read the collection and items.
- **Level 2:** create three books with `POST`; inspect status codes, `Location`, and HAL links.
- **Level 3:** add search by `title`; test cases with and without matching records.
- **Level 4:** try `page`, `size`, and `sort`; verify zero-based `page` indexing and sort ordering.
- **Level 5:** create `Publisher` and the `Book–Publisher` relationship; try reading, attaching, and removing the association.
- **Level 6:** create a projection returning only `title`; verify other fields do not appear in that representation.
- **Level 7:** hide an internal repository and protect write operations with Spring Security.
- **Level 8:** write integration tests covering create, read, update, delete, search, associations, and authorization.

After each exercise, inspect live responses with `curl` or Postman, check application logs, and write tests to lock in the expected behavior.

## 11. Common pitfalls and how to avoid them

- **Adding Spring Data JPA but forgetting Spring Data REST:** repositories still work in Java, yet automatic REST endpoints do not appear. Check starters and auto-configuration.
- **Placing repositories outside component scan:** Spring fails to detect repositories. Put the startup class in the root package or configure scanning explicitly.
- **Guessing wrong endpoint names:** paths and relations can be affected by domain names, annotations, and configuration. Inspect the API root and HAL links to determine real URIs.
- **Using the wrong query parameter name:** URL parameter names must match `@Param` or names inferred by Spring Data. Check whether the method is exported.
- **Serializing lazy relationships outside a transaction:** responses may trigger extra queries or fail when accessing a closed proxy. Design representations, fetch plans, and transactions intentionally.
- **Exporting all repositories:** clients may see unexpected data or operations. Export only what belongs to the API contract and test access permissions.
- **Misunderstanding association `DELETE`:** the operation may only unlink the relationship without deleting the entity on the other side. Verify endpoint behavior and database state afterward.
- **Treating projections as security:** projections only shape representations. Authorization must still be enforced in the security and business layers.
- **Putting complex business rules into event handlers:** multi-step flows become hard to read and hard to manage transactionally. Move business logic to appropriate services.
- **Testing only repositories:** repository tests do not prove URIs, HAL, status codes, headers, and authorization are right. Add HTTP integration tests.

## 12. Pre-project readiness checklist

- [ ] Understand Java generics, annotations, and interfaces.
- [ ] Understand HTTP methods, status codes, JSON, and REST resources.
- [ ] Know how to configure and run a Spring Boot application.
- [ ] Have used Spring Data repositories and query methods.
- [ ] Understand entities, transactions, and relationships of the active persistence store.
- [ ] Can read HAL `_links` and `_embedded`.
- [ ] Have identified which repositories are allowed to be exported.
- [ ] Have controlled permissions for read, write, and association updates.
- [ ] Have reviewed validation, projections, and sensitive data.
- [ ] Have integration tests for HTTP contracts and security.

Spring Data REST works effectively when the repository model matches the resource API clients need. Start with a small repository, observe HAL responses, and only then expand into relationships, projections, validation, and security.