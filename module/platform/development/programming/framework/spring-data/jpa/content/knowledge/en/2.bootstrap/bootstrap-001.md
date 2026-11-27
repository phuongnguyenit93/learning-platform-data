# Creating a Spring Boot Application with Spring Data JPA and a JDBC Driver

This lesson guides you through creating a Spring Boot application with a book management API, using Spring Data JPA for data operations and H2 as a sample database via a JDBC driver. The example uses Java 17, Maven, and Spring Boot 3.5.0. Once completed, the application can create, read, update, delete, and search for books by author.

## 1. Understanding the Role of Each Component

The technologies in the application handle different responsibilities:

| Component | Role |
|---|---|
| Spring Boot | Bootstrapping the application, auto-configuration, dependency management, and integrating Spring components |
| Spring Data JPA | Providing repositories and data access operations following the JPA model |
| JPA | The Java specification for mapping objects to relational data and persistence operations |
| Hibernate | The default JPA provider typically configured by Spring Boot; executes JPA operations and generates SQL |
| JDBC | The standard Java API for connecting to and sending SQL commands to a database |
| JDBC driver | A database-specific library that translates JDBC calls into the protocol understood by the database |
| H2 | An embedded relational database used in the example for testing without installing a DB server |

Typical processing flow:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Spring MVC Controller]
    B --> C[Spring Data Repository]
    C --> D[JPA EntityManager]
    D --> E[Hibernate]
    E --> F[JDBC API]
    F --> G[H2 JDBC Driver]
    G --> H[(H2 Database)]
~~~

Spring Data JPA is not a JDBC driver. Repositories work at the object and JPA level; Hibernate translates those operations into SQL; the JDBC driver establishes the connection and communicates with the database. When switching from H2 to MySQL or PostgreSQL, the application replaces the driver and connection configuration accordingly.

## 2. Preparing the Environment

Requirements:

- JDK 17 or higher with the JAVA_HOME environment variable configured.
- Maven 3.6.3 or higher, or the Maven Wrapper included with the project.
- A Java-supported IDE such as IntelliJ IDEA, Eclipse, or VS Code.
- Basic knowledge of Java, Maven, HTTP, and SQL.

Check the environment:

~~~bash
java -version
mvn -version
~~~

The output must show Java 17 or higher and that Maven can run. If using the Maven Wrapper, you can replace the mvn command with ./mvnw on Linux/macOS or mvnw.cmd on Windows.

## 3. Creating the Project Structure

Create a Maven project with the root package com.example.springdatajpa. Minimal structure:

~~~text
spring-data-jpa-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/springdatajpa/
        │       ├── DemoApplication.java
        │       └── book/
        │           ├── Book.java
        │           ├── BookRepository.java
        │           ├── BookRequest.java
        │           └── BookController.java
        └── resources/
            └── application.properties
~~~

You can generate the project using Spring Initializr (start.spring.io): choose Maven, Java, Spring Boot 3.5.x, Java 17, Jar packaging; add Spring Web, Spring Data JPA, Validation, and H2 Database. Then create the packages and files following the structure above.

## 4. Declaring Dependencies in pom.xml

The Spring Data JPA starter provides Spring Data JPA, Hibernate, Spring ORM, Spring JDBC, and transaction support. H2 is the JDBC driver for the H2 database. Spring Web builds the REST API; Validation checks input data.

~~~xml
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
    <artifactId>spring-data-jpa-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>spring-data-jpa-demo</name>
    <description>Demo Spring Boot with Spring Data JPA and H2 JDBC driver</description>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>

        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
~~~

You do not need to declare versions manually for H2 or the starters when using the Spring Boot parent because Spring Boot's dependency management handles compatible versions. You do not need to add spring-boot-starter-jdbc just to make Spring Data JPA work; the JPA starter already pulls in the required JDBC libraries.

## 5. Creating the Spring Boot Entry Point Class

File DemoApplication.java:

~~~java
package com.example.springdatajpa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

@SpringBootApplication combines configuration, auto-configuration, and component scanning. Place this class in the root package so Spring scans classes in the book subpackage, including the controller, repository, and entity.

## 6. Configuring the H2 Connection with the JDBC Driver

File src/main/resources/application.properties:

~~~properties
spring.application.name=spring-data-jpa-demo

spring.datasource.url=jdbc:h2:mem:booksdb;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=update
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.open-in-view=false

spring.h2.console.enabled=true
spring.h2.console.path=/h2-console
~~~

Meaning of the properties:

- spring.datasource.url specifies the DB type, database name, and connection mode. The jdbc:h2: prefix indicates H2 is used.
- spring.datasource.driver-class-name specifies the driver class. For H2, this class is org.h2.Driver. Spring Boot can usually infer the driver from the URL, so this line can be omitted.
- username and password are the credentials for the sample database.
- spring.jpa.hibernate.ddl-auto=update instructs Hibernate to update the schema based on the entities. This mode is convenient for learning; production systems should manage schemas with Flyway or Liquibase and typically set ddl-auto=validate.
- show-sql and format_sql help observe the SQL generated by Hibernate.
- open-in-view=false avoids keeping the EntityManager open throughout web response processing.
- H2 Console allows viewing the database at /h2-console while the application is running.

The URL above creates an in-memory database. Data exists for the lifetime of the current JVM and is lost when the application process terminates. DB_CLOSE_DELAY=-1 keeps the database in memory until the JVM stops, without turning it into a persistent database.

## 7. Creating an Entity Mapped to a Database Table

An entity represents an object stored in the database. File book/Book.java:

~~~java
package com.example.springdatajpa.book;

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

    @Column(nullable = false, length = 150)
    private String title;

    @Column(nullable = false, length = 120)
    private String author;

    protected Book() {
        // JPA requires a no-argument constructor.
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

Important annotations:

- @Entity marks the class as managed by JPA.
- @Table(name = "books") sets the corresponding table name.
- @Id marks the primary key.
- @GeneratedValue(strategy = GenerationType.IDENTITY) delegates primary key generation to the database using the identity mechanism.
- @Column configures the column, length limit, and non-null requirement.
- The no-argument constructor must have at least protected visibility so JPA can instantiate the entity. The other constructor helps the application create new objects.

Table and column names can be generated by Hibernate based on the entity when schema auto-configuration is enabled. Entities should focus on data and domain rules; do not put HTTP logic into an entity.

## 8. Creating a Spring Data Repository

File book/BookRepository.java:

~~~java
package com.example.springdatajpa.book;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByAuthorIgnoreCase(String author);
}
~~~

Extending JpaRepository<Book, Long> provides common operations out of the box, such as:

| Method | Purpose |
|---|---|
| save(entity) | Saves a new entity or updates an existing entity |
| findById(id) | Finds by primary key, returning an Optional |
| findAll() | Retrieves a list of entities |
| existsById(id) | Checks whether a primary key exists |
| deleteById(id) | Deletes by primary key |
| count() | Counts the number of records |

Spring Data generates the implementation for the repository interface at application startup. You do not need to write a CRUD implementation class manually.

The name findByAuthorIgnoreCase is a derived query. Spring Data parses the method name and generates a query to find books by author, case-insensitively. You can define additional methods such as findByTitleContainingIgnoreCase(String keyword) when you need to search by a partial title.

## 9. Creating a DTO for Input Data

File book/BookRequest.java:

~~~java
package com.example.springdatajpa.book;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record BookRequest(
        @NotBlank @Size(max = 150) String title,
        @NotBlank @Size(max = 120) String author
) {
}
~~~

A DTO (Data Transfer Object) defines the data the API receives from clients. Java 17 records are well-suited for immutable DTOs. @NotBlank rejects null values, empty strings, or whitespace-only strings; @Size limits the length to match the entity column configuration. The controller uses @Valid to trigger validation.

## 10. Creating a REST Controller Using the Repository

File book/BookController.java:

~~~java
package com.example.springdatajpa.book;

import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookRepository repository;

    public BookController(BookRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public List<Book> findAll(
            @RequestParam(name = "author", required = false) String author) {
        if (author == null || author.isBlank()) {
            return repository.findAll();
        }
        return repository.findByAuthorIgnoreCase(author);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Book> findById(@PathVariable("id") Long id) {
        return repository.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping
    public ResponseEntity<Book> create(@Valid @RequestBody BookRequest request) {
        Book saved = repository.save(
                new Book(request.title(), request.author()));
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }

    @PutMapping("/{id}")
    public ResponseEntity<Book> update(
            @PathVariable("id") Long id,
            @Valid @RequestBody BookRequest request) {
        return repository.findById(id)
                .map(book -> {
                    book.setTitle(request.title());
                    book.setAuthor(request.author());
                    return ResponseEntity.ok(repository.save(book));
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable("id") Long id) {
        if (!repository.existsById(id)) {
            return ResponseEntity.notFound().build();
        }

        repository.deleteById(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

The controller receives HTTP requests, validates the DTO, calls the repository, and returns an HTTP response. The repository is responsible for persistence. Constructor injection keeps dependencies explicit and easy to test. In larger applications, you should add a service layer to encapsulate business logic, transactions, and coordination across multiple repositories; this example calls the repository directly to focus on the Spring Data JPA flow.

Endpoints:

| HTTP method | URL | Function |
|---|---|---|
| GET | /api/books | Retrieve all books |
| GET | /api/books?author=... | Search books by author |
| GET | /api/books/{id} | Retrieve a book by ID |
| POST | /api/books | Create a book |
| PUT | /api/books/{id} | Update a book |
| DELETE | /api/books/{id} | Delete a book |

## 11. Running the Application

In the directory containing pom.xml, run:

~~~bash
mvn spring-boot:run
~~~

Or package and run the JAR file:

~~~bash
mvn clean package
java -jar target/spring-data-jpa-demo-0.0.1-SNAPSHOT.jar
~~~

Upon successful startup, Spring Boot starts the default web server on port 8080. Hibernate creates or updates the books table in H2 according to the configuration. If port 8080 is already in use, change the port using the server.port property, for example server.port=8081.

## 12. Testing the CRUD API

Use curl or Postman. Example creating a book:

~~~bash
curl -i -X POST http://localhost:8080/api/books   -H "Content-Type: application/json"   -d '{"title":"Clean Code","author":"Robert C. Martin"}'
~~~

Sample response:

~~~http
HTTP/1.1 201
Content-Type: application/json

{"id":1,"title":"Clean Code","author":"Robert C. Martin"}
~~~

Retrieve the list:

~~~bash
curl http://localhost:8080/api/books
~~~

Response after creating one book:

~~~json
[
  {
    "id": 1,
    "title": "Clean Code",
    "author": "Robert C. Martin"
  }
]
~~~

Search by author:

~~~bash
curl "http://localhost:8080/api/books?author=robert%20c.%20martin"
~~~

Retrieve by ID:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Update:

~~~bash
curl -i -X PUT http://localhost:8080/api/books/1   -H "Content-Type: application/json"   -d '{"title":"Clean Code - Updated","author":"Robert C. Martin"}'
~~~

Delete:

~~~bash
curl -i -X DELETE http://localhost:8080/api/books/1
~~~

POST returns HTTP 201 Created; GET returns HTTP 200 OK if found; PUT returns HTTP 200 OK if updated successfully; DELETE returns HTTP 204 No Content if deleted successfully. A non-existent ID returns HTTP 404 Not Found. Invalid input data is rejected with HTTP 400 Bad Request thanks to Bean Validation. When testing in Windows PowerShell, you can call curl.exe to avoid PowerShell's curl alias.

## 13. Inspecting Data in the H2 Console

Open http://localhost:8080/h2-console while the application is running. Enter the following details:

- JDBC URL: jdbc:h2:mem:booksdb
- User Name: sa
- Password: leave blank

Select Connect, then run:

~~~sql
SELECT * FROM BOOKS;
~~~

You can view the saved data and the columns generated by Hibernate. The console should only be enabled in local development environments; do not expose the H2 Console in production.

## 14. Replacing H2 with Another Database

The JDBC driver depends on the database management system. When switching to MySQL, remove the H2 dependency and add MySQL Connector/J:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Create the database first, for example:

~~~sql
CREATE DATABASE books_db;
~~~

Configure the MySQL connection in application.properties:

~~~properties
spring.datasource.url=jdbc:mysql://localhost:3306/books_db
spring.datasource.username=app_user
spring.datasource.password=change-this-secret
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.show-sql=true
~~~

Create an appropriate database account and provide the password via environment variables or a secret manager in deployment environments; do not commit real passwords to Git. With a new schema, you must run migrations before using ddl-auto=validate. If experimenting locally, you can temporarily use update, understanding that Hibernate may alter the schema.

For PostgreSQL, the corresponding runtime dependency is org.postgresql:postgresql and the URL takes the form jdbc:postgresql://localhost:5432/books_db. Username, password, and schema must match the server configuration. Do not use org.h2.Driver for MySQL or PostgreSQL; each database type requires its corresponding driver. When changing the driver and URL, entity and repository code usually do not need to change if only portable JPA features are used.

## 15. Transactions and How Spring Data JPA Persists Data

The read and write methods provided by the repository have appropriate transaction mechanisms. When a business operation consists of multiple steps that must succeed or fail together, place them in a service method annotated with @Transactional:

~~~java
package com.example.springdatajpa.book;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Book renameBook(Long id, String newTitle) {
        Book book = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Book not found: " + id));

        book.setTitle(newTitle);
        return repository.save(book);
    }
}
~~~

@Transactional establishes a transaction boundary for the business operation. If the method completes normally, the transaction is committed; if an appropriate error occurs, the transaction can roll back according to Spring's rollback rules. Within a JPA transaction, a managed entity can be dirty-checked by Hibernate and its changes written on flush/commit; calling save in the example helps make the repository operation explicit.

A transaction should encompass one consistent unit of business work. Avoid keeping a transaction open too long while calling external services or waiting for user input. In real applications, use appropriate exceptions and map errors to meaningful HTTP statuses.

## 16. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
|---|---|---|
| Failed to configure a DataSource | Missing driver or connection URL | Check runtime dependency, spring.datasource.url, and username/password configuration |
| Cannot load driver class | Wrong driver class or missing driver JAR | Match the driver with the DB; H2 uses org.h2.Driver |
| Connection refused | Database server not running or wrong host/port | Check DB service, port, and firewall |
| Access denied | Wrong account, password, or privileges | Check credentials and database access permissions |
| Table not found | Schema not yet created or wrong table name | Check entities, ddl-auto, and migrations |
| Port 8080 already in use | Another application is occupying the port | Stop the process using the port or change server.port |
| API returns 404 | Wrong URL or record does not exist | Check controller mappings and ID |
| API returns 400 | Malformed JSON or validation failure | Check Content-Type, field names, and title/author values |
| H2 data disappears after stopping the app | H2 is running in in-memory mode | Use file-based H2 or a persistent database if data retention is needed |

Read the full log starting from the root cause, typically found in the Caused by lines. Do not handle connection errors by disabling security checks or exposing the database to the public network.

## 17. Guidelines for Moving the Application to Production

- Use an appropriate database server and its official driver; manage the connection pool through Spring Boot configuration.
- Keep credentials out of source code; use environment variables or a secret manager.
- Manage schema changes with Flyway or Liquibase; set Hibernate ddl-auto=validate or none once migrations are controlled.
- Place transaction boundaries in the service layer for multi-step business logic.
- Use DTOs instead of accepting or returning entities directly when APIs become complex; avoid unintentionally exposing internal fields.
- Add validation, exception handling, pagination, and sorting for endpoints returning large lists.
- Write integration tests with a suitable database. H2 is convenient for fast tests, but differs in SQL and behavior from MySQL/PostgreSQL; test with Testcontainers or a corresponding DB environment if relying on database-specific features.
- Disable the H2 Console and detailed SQL logging in production; avoid exposing sensitive information in logs.

## 18. Key Takeaways

1. Spring Boot auto-configures a DataSource when the appropriate dependency and connection properties are present.
2. The JDBC driver is the bridge between the JDBC API and the database management system's protocol.
3. Spring Data JPA provides repositories; Hibernate implements JPA and communicates with the DB via JDBC.
4. Entities map Java classes to tables; repositories provide CRUD and derived queries.
5. DTOs and Bean Validation help control incoming API data.
6. In-memory H2 is suitable for learning and running demos; data is lost when the application exits.
7. When switching databases, replace the driver and connection configuration; re-check the schema, SQL dialect, and migrations.
8. For real-world applications, manage transactions in the service layer and schemas with a migration tool.

## 19. Self-Check Checklist

- [ ] JDK 17+ and Maven are working.
- [ ] pom.xml includes Spring Web, Spring Data JPA, Validation, and H2.
- [ ] Spring Boot starts successfully.
- [ ] H2 DataSource connects and the books table is created.
- [ ] POST creates a book and returns HTTP 201.
- [ ] GET retrieves the list and a single record.
- [ ] Searching by author works case-insensitively.
- [ ] PUT updates a record.
- [ ] DELETE removes a record and returns HTTP 204.
- [ ] Non-existent ID returns HTTP 404; invalid data returns HTTP 400.
- [ ] Understand how to replace the H2 driver with a MySQL or PostgreSQL driver.
