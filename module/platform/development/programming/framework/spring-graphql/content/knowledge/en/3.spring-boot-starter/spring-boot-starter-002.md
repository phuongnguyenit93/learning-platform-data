# Starter for Spring MVC

## 1. What Is the Spring MVC Starter?

In Spring Boot, the dependency commonly used to build Spring MVC applications is `spring-boot-starter-web`. It is a *starter*: a curated dependency bundle selected by Spring Boot to bring in the libraries typically needed for a set of capabilities. When a starter is added, Maven or Gradle resolves the related dependencies using versions managed by Spring Boot.

`spring-boot-starter-web` provides a web foundation based on the Servlet and Spring MVC model. In its common configuration, this starter brings in Spring Web MVC, core web components, JSON conversion support, and an embedded Servlet server such as Tomcat. As a result, the application can start as a standalone Java process without needing to package and deploy it onto an external application server.

Spring MVC handles HTTP requests using a request-response model. Controllers receive requests, call the business layer, and return responses. Annotations such as `@Controller`, `@RestController`, `@GetMapping`, and `@PostMapping` map URLs and HTTP methods to Java methods.

In the Spring for GraphQL module, `spring-boot-starter-web` provides the Servlet-based HTTP foundation for the application to receive GraphQL requests. This starter does not define the GraphQL schema or write resolvers by itself. Those capabilities belong to Spring for GraphQL and GraphQL Java.

## 2. Distinguishing Starters in a Spring GraphQL Application

A GraphQL application running on Spring MVC typically needs two dependency groups with distinct responsibilities:

| Dependency | Primary Responsibility |
| --- | --- |
| `spring-boot-starter-graphql` | Integrates Spring for GraphQL, GraphQL Java, schema handling, and operation execution |
| `spring-boot-starter-web` | Provides Spring MVC and the Servlet HTTP transport so clients can send GraphQL requests over HTTP |

The separation can be illustrated as follows:

```mermaid
flowchart TD
    A[GraphQL client] -->|HTTP request| B[Spring MVC / Servlet stack]
    B --> C[Spring for GraphQL]
    C --> D[GraphQL schema and execution engine]
    D --> E[@QueryMapping / @MutationMapping / @SchemaMapping]
    E --> F[Services and Repositories]
    F --> G[Database or other systems]
    G --> F
    F --> E
    E --> D
    D --> C
    C --> B
    B -->|HTTP JSON response| A
```

`spring-boot-starter-web` handles the web layer of the application. `spring-boot-starter-graphql` handles the GraphQL layer. When combined, Spring Boot can auto-configure the GraphQL endpoint on top of the Servlet platform based on the dependencies present in the application.

If only `spring-boot-starter-web` is added, the project has Spring MVC but lacks a GraphQL schema and execution engine. If only `spring-boot-starter-graphql` is added, the project has GraphQL integration but still needs an appropriate transport to receive client requests over HTTP. For an application using Spring MVC, that transport is provided by `spring-boot-starter-web`.

## 3. Adding the Dependencies to Your Project

### Maven

Add both dependencies to the `dependencies` section of `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

### Gradle Kotlin DSL

If the project uses Gradle with Kotlin DSL, declare them in `build.gradle.kts`:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

### Gradle Groovy DSL

With `build.gradle`, the equivalent syntax is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Normally, you do not need to specify a separate version for each starter. Use the Spring Boot parent or Spring Boot's dependency management/plugin mechanism so that libraries in the same ecosystem are versioned consistently. Pinning incompatible versions of Spring Framework, Spring GraphQL, or GraphQL Java manually can cause compile-time or startup errors.

## 4. How Does Spring MVC Handle the HTTP Layer?

When using `spring-boot-starter-web`, the application runs on the Servlet stack. In the common default setup, Spring Boot starts an embedded server and registers the Spring MVC infrastructure. `DispatcherServlet` is the central component that dispatches requests to the appropriate handler.

A single application can expose multiple types of HTTP endpoints simultaneously:

- REST endpoints mapped with `@RestController`, `@GetMapping`, `@PostMapping`, and other MVC annotations.
- The GraphQL endpoint registered on the web stack by the Spring for GraphQL integration.
- Static resources such as CSS, JavaScript, or image files if the application is configured to serve them.

For GraphQL, clients typically send an HTTP POST to the `/graphql` endpoint. The body contains the operation, variables, and optionally an operation name. Spring MVC receives the HTTP request; the Spring for GraphQL integration passes the request payload to the GraphQL engine to validate against the schema, select resolvers, and execute the requested fields. The result is returned as JSON.

High-level flow:

1. The client sends an HTTP request to the GraphQL endpoint.
2. The Servlet container receives the request and routes it into the application's web stack.
3. Spring for GraphQL reads the GraphQL request and creates the execution input.
4. The GraphQL engine validates the operation against the schema and executes the relevant resolvers.
5. Resolvers call services or repositories to retrieve and mutate data according to business logic.
6. The GraphQL result and errors are packaged into a JSON response sent back to the client.

The key point is that GraphQL operations are not mapped to custom `@PostMapping` methods written individually for each query. Spring for GraphQL provides the shared HTTP endpoint; `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` methods handle field resolution inside a GraphQL operation.

## 5. Example GraphQL Application Running on Spring MVC

Suppose a library application needs to provide a query to look up a book by ID. A minimal structure might look like:

```text
src/main/
├── java/com/example/library/
│   ├── LibraryApplication.java
│   └── BookGraphQlController.java
└── resources/
    └── graphql/
        └── schema.graphqls
```

### Declaring the SDL Schema

Create `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

The schema defines a root field `bookById`. The `id` argument is required, while the `Book` result can be `null` if no book is found. The `id` and `title` fields of a Book object must have non-null values.

In Spring Boot's default configuration, schemas can be placed in `src/main/resources/graphql/` with `.graphqls` or `.gqls` extensions. If you change the location, update the schema location configuration accordingly.

### Writing the GraphQL Controller

Create a controller using Spring for GraphQL annotations:

```java
package com.example.library;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

`@Controller` lets Spring detect the component containing GraphQL handlers. `@QueryMapping` binds the method to the field with the same name in the root `Query` type; `@Argument` extracts the `id` argument from the GraphQL request. `BookService` is the business layer provided by the application.

Example return model:

```java
public record Book(String id, String title) {
}
```

The GraphQL controller does not need to declare `@PostMapping("/graphql")`. The HTTP endpoint is configured by the Spring GraphQL integration. The `bookById` method only handles the corresponding field after the operation has been parsed by the GraphQL engine.

### Configuring the Endpoint

The default HTTP endpoint of Spring for GraphQL in Spring Boot is usually `/graphql`. You can explicitly declare the path in `application.yml`:

```yaml
spring:
  graphql:
    path: /graphql

server:
  port: 8080
```

If you change `path`, clients must send requests to the new path. The `server.port` property configures the HTTP port of the embedded server.

### Sending Requests from the Client

GraphQL operation:

```graphql
query BookById($id: ID!) {
    bookById(id: $id) {
        id
        title
    }
}
```

JSON request sent to `http://localhost:8080/graphql`:

```json
{
  "query": "query BookById($id: ID!) { bookById(id: $id) { id title } }",
  "operationName": "BookById",
  "variables": {
    "id": "42"
  }
}
```

You can quickly test it with curl:

```bash
curl -X POST http://localhost:8080/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"query BookById($id: ID!) { bookById(id: $id) { id title } }","variables":{"id":"42"}}'
```

If the book is found, the response looks like:

```json
{
  "data": {
    "bookById": {
      "id": "42",
      "title": "GraphQL with Spring"
    }
  }
}
```

This example illustrates that Spring MVC provides the HTTP transport, while the GraphQL schema and resolvers determine the operation structure and returned data.

## 6. Combining REST and GraphQL in the Same MVC Application

Spring MVC and Spring for GraphQL can coexist in the same application. This is useful when a system already has a REST API, yet certain screens or clients need more flexible combined data queries.

Example REST controller:

```java
@RestController
@RequestMapping("/api/books")
public class BookRestController {

    private final BookService bookService;

    public BookRestController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping("/{id}")
    public Book findById(@PathVariable String id) {
        return bookService.findById(id).orElseThrow();
    }
}
```

The REST endpoint can be `GET /api/books/42`, while the GraphQL endpoint remains `POST /graphql`. Both controllers can call the same `BookService`, so business rules do not have to be duplicated per API style.

Avoid placing all business logic inside controllers. Both REST and GraphQL controllers should simply adapt input data, invoke services, and shape the output to fit their respective protocols.

## 7. When Should You Choose Spring MVC for GraphQL?

Spring for GraphQL supports both the Servlet model based on Spring MVC and the reactive model based on Spring WebFlux. The GraphQL schema and mapping annotations are largely independent of which web stack you choose.

Choose `spring-boot-starter-web` when:

- The application already uses Spring MVC or needs compatibility with the Servlet ecosystem.
- The business layer primarily uses JDBC, JPA, or synchronous/blocking libraries.
- The system needs to combine REST controllers and a GraphQL endpoint on the same web stack.
- The team already has experience operating Spring MVC, Servlet filters, and related components.

Choose `spring-boot-starter-webflux` when the application is designed around the reactive model and needs non-blocking I/O across all layers. Simply switching to WebFlux does not automatically make blocking database queries non-blocking; you also need to consider drivers, HTTP clients, and how business logic is structured.

Normally, choose one web stack as your primary foundation. Do not add both `spring-boot-starter-web` and `spring-boot-starter-webflux` just to experiment without understanding how Spring Boot selects and configures the application type, as this can cause confusion at startup and in operations.

## 8. Configuration, Security, and Error Considerations

### GraphQL Path and MVC Paths

`spring.graphql.path` adjusts the GraphQL endpoint. MVC routes such as `/api/books` are still declared separately with `@RequestMapping` or corresponding annotations. Avoid overlapping route configurations and ensure clients use the right endpoint.

### HTTP Security and Field Security

Spring Security can protect requests to `/graphql` through the Servlet application's security filter chain. However, allowing a request to reach the endpoint does not mean the user is permitted to read every field or modify every object.

Business rules should be checked in resolvers or services based on the current user, permissions, data ownership, and tenant. Because multiple operations share a single URL, relying solely on URL-based authorization rules is usually insufficient to control access down to individual fields.

### MVC Error Handling and GraphQL Error Handling

REST controllers commonly use Spring MVC exception handling mechanisms such as `@ExceptionHandler` or `@ControllerAdvice`. For errors occurring during GraphQL field resolution, Spring for GraphQL provides mechanisms such as `DataFetcherExceptionResolver` to map exceptions into entries in the `errors` array of the GraphQL response.

Both API types can share services and business rules, but error responses must be shaped according to each protocol. Never include stack traces, SQL statements, tokens, or internal details in responses sent to clients.

### Do Not Confuse Endpoint Issues with Resolver Issues

If `POST /graphql` returns 404, check the web stack dependency, endpoint configuration, and application startup status. If the endpoint accepts the request but the response reports a validation error or missing field, check the schema, operation name, and resolver mappings. These are two distinct classes of issues.

## 9. Common Issues When Adding the Spring MVC Starter

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `/graphql` returns 404 | Missing matching HTTP transport, endpoint path was changed, or the GraphQL handler was not registered | Check `spring-boot-starter-web`, `spring-boot-starter-graphql`, startup logs, and `spring.graphql.path` |
| Application has REST but no GraphQL | Only `spring-boot-starter-web` was added | Add `spring-boot-starter-graphql` and the SDL schema |
| Schema is not recognized | Schema file is in the wrong directory, has an unsupported extension, or location configuration is incorrect | Check `src/main/resources/graphql/` and `.graphqls`/`.gqls` file names |
| Field is not resolved | Field name and mapping do not match, or controller was not detected by Spring | Compare root fields in SDL with `@QueryMapping`/`@MutationMapping` and package scanning |
| Library compatibility errors | Spring Boot/Spring Framework/Spring GraphQL dependencies are pinned to mismatched versions | Use Spring Boot dependency management and inspect the dependency tree |
| REST and GraphQL return different error formats | The two protocols have separate error formats and exception mapping mechanisms | Check MVC handlers and `DataFetcherExceptionResolver` accordingly |

## 10. Application Setup Checklist

- [ ] The project uses dependency management from a consistent Spring Boot version.
- [ ] `spring-boot-starter-graphql` is added to provide schema handling and GraphQL execution.
- [ ] `spring-boot-starter-web` is added when choosing Spring MVC as the HTTP stack.
- [ ] SDL schemas reside in a location scanned by Spring Boot or in a configured schema location.
- [ ] GraphQL controllers are detected by Spring and mappings match schema fields.
- [ ] Clients send requests to the right GraphQL path with valid payloads.
- [ ] The security filter chain protects the HTTP endpoint and services/resolvers enforce data-level permissions.
- [ ] REST and GraphQL have error-handling strategies suited to each protocol.

## Conclusion

`spring-boot-starter-web` is the standard choice for building Spring MVC applications on the Servlet platform. In a Spring for GraphQL application, this starter provides the HTTP layer for clients to send queries and mutations to the server; `spring-boot-starter-graphql` provides the schema, execution engine, and mechanism for mapping fields to resolvers.

Once you understand each starter's responsibilities, configuration becomes straightforward to control: choose the web stack that fits your application's I/O model, let Spring Boot manage dependency versions, place schemas in the proper location, and implement resolvers using Spring for GraphQL annotations. A single application can expose both REST and GraphQL simultaneously, as long as controllers focus on the protocol while business logic lives in the service layer.
