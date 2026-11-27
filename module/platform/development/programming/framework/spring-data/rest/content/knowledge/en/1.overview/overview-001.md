# What is Spring Data REST and the Problem of Automatically Exposing Repositories over HTTP

Spring Data REST is a component of the Spring Data ecosystem that turns repositories into REST resources accessible over HTTP. Instead of manually writing a controller for every create, read, update, and delete (CRUD) operation, an application can declare a repository and let Spring Data REST automatically generate the corresponding endpoints.

This approach fits admin APIs or services with fairly standard CRUD business logic. It reduces boilerplate code, though it also couples the API structure more tightly to repositories and the domain model. Therefore, it is important to understand which resources are exposed and control access permissions before using it in a production environment.

## 1. The problem: exposing data over HTTP

A book management application typically needs the following operations:

- Retrieve a list of books.
- View a single book by ID.
- Create a new book.
- Edit book information.
- Delete a book.
- Search for books by criteria such as title.

When building a REST API manually with Spring MVC, you typically have to write a controller, call a service or repository, convert input/output data, choose HTTP status codes, and handle error cases. Across many resource types, this code can involve significant repetition.

Spring Data REST solves the common CRUD part by reading Spring Data repository metadata and automatically exposing HTTP resources. Developers still define entities, repositories, and business rules; the framework handles mapping repositories to REST resources.

For example, a repository managing `Book` can produce endpoints such as:

| HTTP | Endpoint | Meaning |
|---|---|---|
| GET | `/api/books` | Retrieve a list of books |
| GET | `/api/books/{id}` | Retrieve a single book |
| POST | `/api/books` | Create a book |
| PUT | `/api/books/{id}` | Replace/update a resource |
| PATCH | `/api/books/{id}` | Partially update a resource |
| DELETE | `/api/books/{id}` | Delete a book |

The paths above are the result of the example configuration in this article. If no path is specified, Spring Data REST derives the collection path from the domain type; you can inspect the actual paths through the API root resource.

## 2. How does Spring Data REST work?

Spring Data REST integrates with repositories belonging to corresponding Spring Data modules, such as repositories using JPA. When the application starts, the framework detects repositories allowed to be exposed, reads the domain type and exported methods, and then registers the appropriate HTTP resources.

General processing flow:

1. The client sends an HTTP request to a resource endpoint.
2. Spring Data REST locates the corresponding repository resource.
3. The framework translates the request into a repository operation.
4. The repository interacts with the persistence provider or datastore.
5. The result is formatted as an HTTP representation and returned to the client.

Spring Data REST typically uses HAL (Hypertext Application Language) to represent resources. HAL JSON includes fields such as `_links` to describe links to related resources and `_embedded` to hold embedded resources. Clients can follow these links instead of having to guess every URL.

For example, a collection response may include links to the collection itself, the root resource, and search capabilities. The exact structure depends on the repository, configuration, and actual data.

**Key takeaway:** Spring Data REST exposes repositories that are detected and allowed to be exported. It does not automatically turn every table in the database into an API. Endpoint scope depends on the repository, exported methods, and application configuration.

## 3. Creating a runnable Spring Boot example

The example below uses Java 17+, Spring Boot 3.5.0, Spring Data JPA, Spring Data REST, and an in-memory H2 database. The version in the example is a specific baseline for illustration; real projects should use a maintained Spring Boot patch version compatible with the deployment environment.

Directory structure:

```text
spring-data-rest-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/demo/
        │       ├── DemoApplication.java
        │       ├── Book.java
        │       └── BookRepository.java
        └── resources/
            └── application.properties
```

### 3.1. Declaring dependencies

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-data-rest-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

- `spring-boot-starter-data-rest` provides the capability to expose repositories as REST resources.
- `spring-boot-starter-data-jpa` provides JPA and Hibernate integration.
- H2 is an in-memory database for testing without installing a separate database.

### 3.2. Creating the entity

Create `src/main/java/com/example/demo/Book.java`:

```java
package com.example.demo;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

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
```

The entity describes the stored data. With JPA, `@Entity` marks the class as a persistent entity; `@Id` identifies the primary key, and `@GeneratedValue` instructs the persistence provider to generate key values according to the chosen strategy.

### 3.3. Declaring the repository

Create `src/main/java/com/example/demo/BookRepository.java`:

```java
package com.example.demo;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {

    @RestResource(path = "by-title", rel = "by-title")
    List<Book> findByTitleContainingIgnoreCase(
        @Param("title") String title
    );
}
```

This declaration serves two purposes:

- `JpaRepository<Book, Long>` provides common repository operations for the `Book` entity.
- `@RepositoryRestResource` tells Spring Data REST to expose the repository with collection path `books` and relation name `books`.

The derived query method `findByTitleContainingIgnoreCase` is interpreted by Spring Data JPA as a query searching for titles containing the passed string, case-insensitively. `@RestResource` sets the search path to `by-title`, so the search endpoint is `/api/books/search/by-title`. `@Param("title")` specifies the query parameter name in the URL.

### 3.4. Creating the application startup class

Create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner seedBooks(BookRepository books) {
        return args -> {
            if (books.count() == 0) {
                books.saveAll(List.of(
                    new Book("Clean Code", "Robert C. Martin"),
                    new Book("Effective Java", "Joshua Bloch")
                ));
            }
        };
    }
}
```

The runner adds two sample records when the database has no books yet. This provides data to test the GET and search endpoints immediately after the application starts.

### 3.5. Configuring the application

Create `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:booksdb
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false

spring.data.rest.base-path=/api
```

`spring.data.rest.base-path=/api` sets a common prefix for endpoints generated by Spring Data REST. Therefore, the `books` collection is accessed at `/api/books`.

In-memory H2 only exists for the lifetime of the application. `create-drop` creates the schema on startup and drops it when the application stops; this configuration is convenient for examples but not suitable for long-term data storage in production.

### 3.6. Running the application

In the directory containing `pom.xml`, run:

```bash
mvn spring-boot:run
```

Once the application starts successfully, the server listens on port 8080 by default. Startup logs depend on version and environment, so there is no single fixed stdout to compare against. If port 8080 is already in use, change the port using the `server.port` property.

## 4. Calling the auto-generated endpoints

The examples below assume the application is running at `http://localhost:8080`. The `Accept: application/hal+json` header requests a HAL representation.

### 4.1. Exploring the API from the root resource

```bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api
```

The root resource provides links to exposed repository resources. This is a useful starting point for clients to discover the API and inspect actual relation names.

### 4.2. Retrieving the book list

```bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/books
```

A collection response typically contains pagination information, navigation links, and the list of resources embedded under `_embedded.books`. The relation name `books` comes from the `collectionResourceRel` configuration.

You can paginate and sort using query parameters:

```bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/api/books?page=0&size=10&sort=title,asc"
```

`page` is zero-based. `size` requests the number of items per page; the maximum limit also depends on Spring Data REST configuration.

### 4.3. Retrieving a single book

```bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/books/1
```

The ID `1` is an example ID. In a real application, the client should obtain an item's URI from links in the collection response or from the creation response.

### 4.4. Creating a new book

```bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"title":"Domain-Driven Design","author":"Eric Evans"}' \
  http://localhost:8080/api/books
```

The request sends JSON representing the entity. When creation succeeds, the server returns `201 Created` and the new resource's location via the `Location` header. Whether an additional body is returned depends on Spring Data REST's response body configuration.

### 4.5. Updating and deleting

Use `PUT` when you want to send a representation to replace/update the resource according to the endpoint contract:

```bash
curl -i -X PUT \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"title":"Domain-Driven Design","author":"Eric Evans"}' \
  http://localhost:8080/api/books/1
```

Use `PATCH` when you only want to modify part of the data:

```bash
curl -i -X PATCH \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"author":"Eric Evans"}' \
  http://localhost:8080/api/books/1
```

Delete a resource with:

```bash
curl -i -X DELETE http://localhost:8080/api/books/1
```

Check the response status and representation after each operation. The examples above illustrate common HTTP methods; validation rules, access permissions, and error handling still need to be configured appropriately for the application.

### 4.6. Calling the search endpoint

The declared repository method creates a search resource:

```bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "title=java" \
  http://localhost:8080/api/books/search/by-title
```

Spring Data REST places exported query methods under the `search` branch. The path name and parameter name are controlled by `@RestResource` and `@Param` in the example.

## 5. Customizing exposure scope

Not every repository should become a public API. Spring Data REST provides annotations and configuration options to adjust endpoints.

### 5.1. Changing the path and relation name

```java
@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {
}
```

- `path` determines the URL path segment of the collection.
- `collectionResourceRel` determines the relation name in the HAL representation.

You can change the global base path using the property:

```properties
spring.data.rest.base-path=/api
```

### 5.2. Hiding a repository or method

If you do not want to expose an entire repository, set `exported = false`:

```java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
```

If you only want to hide a single method, override the repository method and annotate it:

```java
@RestResource(exported = false)
@Override
void deleteById(Long id);
```

Determine carefully which methods need to be exposed. Hiding an endpoint narrows the auto-generated API, but it does not replace authentication and authorization mechanisms.

### 5.3. Adding custom business endpoints

Spring Data REST does not force an application to use it for every API. You can combine automatic repository resources with regular controllers/services. Flows such as payment processing, order approval, price calculation, external system calls, or coordinating multiple aggregates often require dedicated endpoints to clearly express business intent, check preconditions, and control transactions.

## 6. When to use it and limitations to understand

Spring Data REST fits well when:

- Resources have relatively standard CRUD operations.
- Repositories and the domain model closely reflect the API the client needs.
- You want pagination, sorting, repository search, and HAL links without writing many controllers.
- The development team accepts an API derived from repositories and has a process for managing API changes.

Consider dedicated controllers/services when:

- A single request needs to coordinate multiple repositories or multiple business steps.
- The API requires dedicated DTOs, multi-step confirmation workflows, or responses that do not map directly to entities.
- Tight control over the API contract is needed independently of persistence structure.
- Endpoints have operation-specific access rules or validation logic.

Some practical limitations:

1. **API is coupled to the repository model:** changing entities, repositories, or query method names can affect representations and endpoints.
2. **Entities are not necessarily a good API contract:** returning entities directly can expose internal fields or couple clients to storage structure.
3. **Does not replace the business layer:** rules such as valid state transitions, inventory checks, or fee calculations should reside in appropriate services/domain objects.
4. **Relationships are represented as links:** clients need to understand HAL and follow relationship URIs; do not assume every association always appears as a nested object.
5. **Performance needs control:** pagination, fetch strategies, search queries, and link counts should be evaluated against realistic data.

## 7. Security before going to production

Exported repositories create an accessible HTTP surface. If the application does not configure proper protection, data can be read or modified unintentionally.

Before deploying, you should:

- Add Spring Security and configure authentication and authorization for endpoints.
- Export only the repositories and methods that are truly necessary.
- Restrict operations by role and data ownership when required by business rules.
- Validate input data and business constraints; do not assume that having entity setters is sufficient to allow updating every field.
- Inspect serialized fields. Use projections or controllers/DTOs when a tailored representation is needed; projections are not an authorization mechanism.
- Configure CORS intentionally if clients run on a different origin.
- Use a durable database, migration/schema management, and proper secrets configuration for production; do not use in-memory H2 with `create-drop` to store real data.

Do not rely on a client not seeing a HAL link to protect a resource. Access permissions must be enforced on the server for every request.

## 8. Common errors

| Symptom | Possible cause | How to check |
|---|---|---|
| `404 Not Found` | Wrong base path, collection path, or repository is not exported | Call the root resource `/api`, check `_links` and annotations |
| `405 Method Not Allowed` | HTTP method is not supported for that resource or endpoint is hidden | Check resource type and export configuration |
| `400 Bad Request` | Malformed JSON, invalid data type, or validation failure | Check request body and returned error details |
| `415 Unsupported Media Type` | Missing or incorrect `Content-Type` | Send `Content-Type: application/json` for a JSON body |
| `406 Not Acceptable` | Server cannot return a representation matching the requested `Accept` | Try `Accept: application/hal+json` |
| Search resource not visible | Query method is not exported or repository was not detected | Check method, annotations, and the `search` resource |
| Expected field missing | Field is not serialized or representation is restricted | Check getters, mappings, projections, and actual response |

When using PowerShell on Windows, the `curl` command may be an alias for `Invoke-WebRequest` in some versions. You can explicitly invoke `curl.exe` to run the actual curl program.

## 9. Conclusion

Spring Data REST automatically exposes Spring Data repositories as REST resources over HTTP. With just an entity and a repository, an application can get CRUD endpoints, search resources, pagination, sorting, and HAL representations. It is a fast way to build APIs for resources with standard CRUD behavior.

The value of Spring Data REST lies in reducing repetitive glue code. To use it properly, choose which repositories to export, understand the generated API, secure endpoints, and move complex business workflows to dedicated services/controllers when needed.
