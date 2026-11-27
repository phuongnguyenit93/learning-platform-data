# Declaring an Entity, Repository, and Running Your First API

Spring Data REST can automatically publish a Spring Data repository as a REST API. To run your first API, the application needs three main pieces: an entity describing the data, a repository declaring how to access it, and a Spring Boot application to bootstrap those components. Once you add database configuration and a base path, Spring Data REST generates HTTP endpoints automatically without writing a CRUD controller.

This lesson builds a small book-management API using Java 17+, Spring Boot 3.5.0, Spring Data JPA, and H2. After starting the application, you will call the API over HTTP to list books and create a new book.

## 1. Three Required Components

### Entity

An entity is a Java class mapped to data stored in a database. With JPA, the class is marked with `@Entity`, and one field is marked with `@Id` as the primary key. `@GeneratedValue` configures how keys are generated when inserting new records.

For example, a `Book` entity can have `id`, `title`, and `author` properties. An entity does not create REST endpoints on its own; it describes the data structure that the repository operates on.

### Repository

A repository is an interface defining how the application accesses data. By extending `JpaRepository<Book, Long>`, the repository inherits built-in operations such as `save`, `findById`, `findAll`, and `deleteById`, along with pagination and sorting support.

Spring Data generates the implementation for this interface at application startup. You do not need to write basic CRUD implementation classes manually.

### Spring Data REST

Spring Data REST detects exported repositories and creates corresponding REST resources. For a repository managing `Book`, the framework can provide a collection endpoint, an item endpoint, and HTTP CRUD operations. `@RepositoryRestResource` lets you customize the collection path and HAL relation name.

Basic flow:

1. The client sends an HTTP request to an endpoint.
2. Spring Data REST maps the endpoint to the repository.
3. The repository performs the operation on the entity via JPA.
4. Spring Data REST converts the result into an HTTP response, typically using HAL JSON.

## 2. Creating the Project Structure

Create a Maven project with the following structure. Place the application entry point, entity, and repository in the same package or subpackages of the package containing the entry point so Spring Boot can discover them automatically.

```text
spring-data-rest-first-api/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/books/
        │       ├── BookApiApplication.java
        │       ├── Book.java
        │       └── BookRepository.java
        └── resources/
            └── application.properties
```

## 3. Declaring Maven Dependencies

Create `pom.xml` in the root directory:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-data-rest-first-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

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

Role of each dependency:

- `spring-boot-starter-data-rest`: integrates Spring Data REST and automatically publishes repositories as REST resources.
- `spring-boot-starter-data-jpa`: integrates Spring Data JPA and Hibernate for interacting with relational databases.
- `h2`: lightweight in-memory database suitable for hands-on exercises without installing an external database.

The Spring Boot parent manages compatible library versions. You do not need to declare individual versions for the dependencies above. Version `3.5.0` is pinned so the example is reproducible; when starting a new project, choose a maintained Spring Boot version compatible with your environment.

## 4. Creating the `Book` Entity

Create `src/main/java/com/example/books/Book.java`:

```java
package com.example.books;

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

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 120)
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

Explanation of annotations and members:

- `@Entity` marks the class as a JPA-managed entity.
- `@Table(name = "books")` specifies the database table name. If omitted, JPA derives a table name using its naming strategy.
- `@Id` identifies the primary key field.
- `@GeneratedValue(strategy = GenerationType.IDENTITY)` uses the database's identity mechanism to generate primary keys on insert.
- `@Column(nullable = false, length = ...)` declares schema-level column constraints. This does not replace complete input validation at the API layer.
- The no-arg constructor has `protected` visibility so JPA can instantiate the entity. The other constructor makes it convenient to create new objects in Java code.

Getters allow the framework to read properties when building JSON representations; setters allow updating properties in this example. In a real application, decide explicitly which fields clients are allowed to modify.

## 5. Declaring `BookRepository`

Create `src/main/java/com/example/books/BookRepository.java`:

```java
package com.example.books;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {
}
```

Breaking down this declaration:

- `BookRepository` is the repository managing the `Book` entity.
- The first type argument of `JpaRepository` is the entity type.
- The second type argument is the primary key type; in this example, `Long`.
- `path = "books"` sets the collection URL to `/books` before applying the base path.
- `collectionResourceRel = "books"` sets the collection relation name in HAL representations.

You do not need to create a `BookRepositoryImpl` class for standard CRUD operations. Spring Data generates the implementation at startup. Exported repositories can be published by Spring Data REST by default; the annotation here makes the URL and relation explicit.

## 6. Creating the Spring Boot Application Class

Create `src/main/java/com/example/books/BookApiApplication.java`:

```java
package com.example.books;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookApiApplication.class, args);
    }
}
```

`@SpringBootApplication` enables auto-configuration and component scanning from the `com.example.books` package downward. This lets Spring Boot locate the entity and repository in the project structure above and configure Spring Data JPA and Spring Data REST components based on the declared dependencies.

The `main` method calls `SpringApplication.run` to start the application context and embedded web server. You do not need to write a `@RestController` for `BookRepository` CRUD endpoints.

## 7. Configuring the Database and REST Base Path

Create `src/main/resources/application.properties`:

```properties
spring.application.name=spring-data-rest-first-api

spring.datasource.url=jdbc:h2:mem:booksdb
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false

spring.data.rest.base-path=/api
```

Meaning:

- `spring.datasource.url` creates an in-memory H2 database named `booksdb`.
- `spring.datasource.username` and `spring.datasource.password` are example credentials for local H2.
- `spring.jpa.hibernate.ddl-auto=create-drop` tells Hibernate to create the schema on startup and drop it on shutdown.
- `spring.jpa.open-in-view=false` disables Open EntityManager in View to avoid implicit database queries during response rendering.
- `spring.data.rest.base-path=/api` adds the `/api` prefix to endpoints published by Spring Data REST.

With this configuration, the collection path `/books` becomes `/api/books`. In-memory H2 does not preserve data after the application stops; this choice is intended for hands-on practice. In real deployments, configure a persistent database, manage schemas with migrations, and never use example passwords.

## 8. Running the Application for the First Time

Open a terminal in the directory containing `pom.xml`, then run:

```bash
mvn clean package
mvn spring-boot:run
```

If your project includes the Maven Wrapper, you can run:

```bash
./mvnw clean package
./mvnw spring-boot:run
```

On Windows, use `mvnw.cmd` instead of `./mvnw`.

Once started, Spring Boot runs its embedded web server on port `8080` by default. If another program is using that port, add the following property to `application.properties` to change the port:

```properties
server.port=8081
```

In that case, replace `localhost:8080` with `localhost:8081` in the HTTP commands below.

## 9. Testing Your First API

### 9.1. Discovering the API Root

Send a request to the base path:

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
```

Spring Data REST returns the root resource with links to exported repository resources. This is how clients discover the collections published by the server.

### 9.2. Reading the `books` Collection

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/books
```

Right after startup, the database has no data yet, so the collection is empty. The HAL response may contain pagination metadata and links in `_links`; when items exist, collection elements typically appear under `_embedded.books`.

Things to observe:

- HTTP status is `200 OK` when the read request succeeds.
- `Content-Type` indicates the response format.
- `_links` contains URIs for further navigation.
- `page` describes pagination details if the collection response includes it.

### 9.3. Creating a Book

Send a POST request to the collection endpoint:

```bash
curl -i -X POST ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/hal+json" ^
  -d "{\"title\":\"Effective Java\",\"author\":\"Joshua Bloch\"}" ^
  http://localhost:8080/api/books
```

The command above uses Windows Command Prompt line-continuation syntax. On macOS/Linux or Git Bash, use backslashes for line continuation:

```bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"title":"Effective Java","author":"Joshua Bloch"}' \
  http://localhost:8080/api/books
```

The request includes:

- Method `POST` to create an element in the collection.
- Header `Content-Type: application/json` indicating a JSON request body.
- Header `Accept: application/hal+json` requesting a HAL JSON response.
- A JSON body providing the properties accepted by the entity.

When creation succeeds, the server typically returns `201 Created` and a `Location` header pointing to the URI of the new item. A response body may or may not be returned depending on Spring Data REST's return-body configuration. Read the `Location` value to see the URI and the actual ID generated by the database.

### 9.4. Reading Back the Created Resource

Use the URI from the `Location` header to send a GET request. For example, if the header shows the item ID is `1`:

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/books/1
```

A successful response returns `200 OK` and a representation containing the saved book data. The ID in this example is illustrative; do not assume the database always assigns IDs starting from 1.

### 9.5. Reading the Collection Again

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/books
```

Now the collection should contain the newly created book under the `books` relation. With just an entity, a repository, and configuration, you have built and called your first API without writing a CRUD controller.

## 10. Basic Generated Endpoints

With `BookRepository` exported, Spring Data REST provides standard resource operations. The paths below reflect the base path and collection path from this example:

| HTTP method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/books` | Read collection |
| POST | `/api/books` | Create a book |
| GET | `/api/books/{id}` | Read a single book |
| PUT | `/api/books/{id}` | Send a full representation to update/replace |
| PATCH | `/api/books/{id}` | Partially update properties |
| DELETE | `/api/books/{id}` | Delete a book |

Not every request will succeed just because an endpoint exists. Missing IDs in the database, malformed JSON, database constraints, or security settings can all cause requests to fail. When testing, inspect the status code, headers, and response body together.

## 11. Common Setup Errors

| Symptom | Common Cause | How to Check |
|---|---|---|
| Application fails to start | Maven could not download dependencies, wrong JDK, or invalid configuration | Check `java -version`, `mvn -version`, and the top of the stack trace |
| Entity/table not found | Entity is outside package scan scope or missing `@Entity` | Place entity in a subpackage of the application package and check annotations |
| Repository is not published | Repository not detected by Spring Data or configured with `exported = false` | Check package, repository interface, and export annotations |
| Wrong URL returns 404 | Forgot base path or wrong collection path | Check `spring.data.rest.base-path`, `@RepositoryRestResource(path=...)`, and the API root |
| POST returns 400 | Invalid JSON or mismatched data types | Check the JSON body and error response |
| POST returns 415 | Missing or wrong `Content-Type` | Send `Content-Type: application/json` |
| GET returns 406 | `Accept` header requests an unsupported media type | Try `Accept: application/hal+json` |
| Cannot connect to port 8080 | Server not running or port already in use | Check startup logs and `server.port` |

In PowerShell, `curl` may be an alias for `Invoke-WebRequest`. Call `curl.exe` to ensure you use the actual curl executable. PowerShell line-continuation and quoting syntax also differ from Command Prompt; if you hit quoting errors, run the request on a single line or use the syntax of your active shell.

## 12. Notes Before Using in Real Applications

This example focuses on getting an API running, so it does not configure Spring Security, business validation, or a production database. When developing a real application:

- Export only the repositories and operations that clients need.
- Protect endpoints with server-side authentication and authorization. Omitting a link from HAL does not mean the resource is protected.
- Use Bean Validation and proper error handling to validate input data; database column constraints like `nullable = false` do not replace API-level validation.
- Consider DTOs or projections when entities contain internal fields that should not be exposed.
- Keep business rules in services/domain objects. Repository REST works well for standard CRUD; multi-step workflows may require dedicated business endpoints.
- Use a durable database and migrations instead of in-memory H2 with `create-drop` when data must be retained.
- Test APIs and access controls before deploying to a public network.

## 13. Conclusion

To run your first API with Spring Data REST, declare an entity with JPA, create a repository extending `JpaRepository`, add the Spring Data REST dependency, and configure your Spring Boot application. Spring Data REST detects exported repositories and generates REST resources automatically. In the `Book` example, the collection endpoint is `/api/books`; clients can use GET to read and POST to create books.

Once you understand the roles of the entity, repository, base path, and HTTP methods, you can bootstrap small CRUD APIs on your own and know where to inspect if an endpoint is not yet working.