# Documenting a Minimal REST Controller

Springdoc helps a Spring Boot application generate an OpenAPI specification from REST controllers and display that specification with Swagger UI. For a simple controller, you only need to add the right Springdoc starter, declare endpoints using Spring MVC, and run the application. Springdoc automatically reads HTTP mappings, parameters, and data types to generate documentation; OpenAPI annotations are used when clearer descriptions need to be added.

This lesson builds a small book management API with two operations: reading a book by ID and creating a new book. After running the application, you will inspect the REST endpoints, the JSON/YAML documentation, and the Swagger UI.

## 1. Preparing the Spring Boot Application

The example uses Spring Boot 3, Java 17 or later, and Spring MVC. If the project already has `spring-boot-starter-web`, simply add the Springdoc starter compatible with the Spring Boot version in use.

In `pom.xml`, declare the main dependencies:

```xml
<properties>
    <java.version>17</java.version>
    <springdoc.version>2.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

`2.x.y` is a placeholder. Replace it with a specific Springdoc 2.x version compatible with the project's Spring Boot 3 version. The `springdoc-openapi-starter-webmvc-ui` starter integrates OpenAPI specification generation for Spring MVC and Swagger UI. For Spring WebFlux, choose the corresponding WebFlux starter. Spring Boot 2 applications use the Springdoc 1.x line and different artifacts; do not mix dependencies from the two generations.

A simple package structure can look like this:

```text
src/main/java/com/example/books/
├── BooksApplication.java
├── BookController.java
└── dto/
    ├── BookResponse.java
    └── CreateBookRequest.java
```

Place the application class in the root package so Spring Boot can scan controllers and DTOs in subpackages.

## 2. Creating the Application Startup Class

Create `BooksApplication.java`:

```java
package com.example.books;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BooksApplication {

    public static void main(String[] args) {
        SpringApplication.run(BooksApplication.class, args);
    }
}
```

`@SpringBootApplication` enables auto-configuration and component scanning from the `com.example.books` package. Springdoc relies on the beans and endpoint mappings in the application, so the controller must be discovered and registered by Spring.

## 3. Declaring Request and Response DTOs

DTOs describe the data passing through the API. Springdoc can infer schemas from Java types, property names, and certain annotations. The `@Schema` annotation adds descriptions or examples so documentation readers understand the meaning of each field.

Create `dto/CreateBookRequest.java`:

```java
package com.example.books.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Payload sent by the client to create a new book")
public record CreateBookRequest(
    @Schema(description = "Book title", example = "Spring Boot Fundamentals")
    String title
) {}
```

Create `dto/BookResponse.java`:

```java
package com.example.books.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Book information returned to the client")
public record BookResponse(
    @Schema(description = "Book identifier", example = "1")
    long id,

    @Schema(description = "Book title", example = "Spring Boot Fundamentals")
    String title
) {}
```

The two records above use Java record syntax, suitable for Java 17. If the project uses an older Java version, you can replace the record with a class that has a constructor, getters, and corresponding fields. The data types in the DTOs become the basis for Springdoc to generate schemas in the specification.

## 4. Creating the REST Controller and Describing Operations

Create `BookController.java`:

```java
package com.example.books;

import com.example.books.dto.BookResponse;
import com.example.books.dto.CreateBookRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
@Tag(name = "Books", description = "Operations with books")
public class BookController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Get book information by ID",
        description = "Returns book information if the ID exists"
    )
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Book found"),
        @ApiResponse(responseCode = "404", description = "Book not found")
    })
    public ResponseEntity<BookResponse> getById(
            @Parameter(description = "Book identifier", example = "1")
            @PathVariable long id) {

        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(
            new BookResponse(1L, "Spring Boot Fundamentals")
        );
    }

    @PostMapping
    @Operation(
        summary = "Create a new book",
        description = "Receives book data and returns the newly created information"
    )
    @ApiResponses({
        @ApiResponse(responseCode = "201", description = "Book created successfully"),
        @ApiResponse(responseCode = "400", description = "Invalid request data")
    })
    public ResponseEntity<BookResponse> create(
            @RequestBody CreateBookRequest request) {

        BookResponse created = new BookResponse(2L, request.title());
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

This is a controller demonstrating API documentation. The GET endpoint returns a fixed record when `id` equals `1`; the POST endpoint returns mock data with ID `2` without saving to a database. In a real application, the controller usually calls a service to execute business logic and persist data.

Important annotations in the example:

| Annotation | Role in documentation |
| --- | --- |
| `@RestController` | Declares a REST controller so Spring MVC registers the endpoints |
| `@RequestMapping` | Defines the path prefix for the controller |
| `@GetMapping`, `@PostMapping` | Declares the HTTP method and path of the operation |
| `@Tag` | Groups operations under the Books group in the documentation |
| `@Operation` | Adds a short summary and description for the operation |
| `@Parameter` | Describes the `id` path parameter |
| `@ApiResponses`, `@ApiResponse` | Describes key HTTP response codes |
| `@Schema` | Describes structure and examples for DTOs |

Springdoc can automatically infer a lot of information from `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestBody`, return types, and DTOs. There is no need to add annotations for every detail if the inferred data is already accurate. Use OpenAPI annotations to add meaning that the source code cannot fully express.

## 5. Starting and Testing the REST API

Run the application from the project directory:

```bash
./mvnw spring-boot:run
```

On Windows, you can use:

```powershell
.\mvnw.cmd spring-boot:run
```

Once the application starts successfully on the default port `8080`, try calling the GET endpoint:

```bash
curl -i http://localhost:8080/api/books/1
```

A successful response has status code `200` and JSON content similar to:

```json
{
  "id": 1,
  "title": "Spring Boot Fundamentals"
}
```

Call another ID to test the not-found case:

```bash
curl -i http://localhost:8080/api/books/99
```

The response has status code `404`. Next, send a request to create a book:

```bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring Boot Fundamentals"}'
```

The simulated response has status code `201 Created` and a `BookResponse` object. These calls verify the controller's behavior; the OpenAPI documentation is generated separately from the application's metadata.

## 6. Opening the OpenAPI Documentation Generated by Springdoc

With the commonly used default configuration, Springdoc provides the following endpoints:

| URL | Content |
| --- | --- |
| `http://localhost:8080/v3/api-docs` | OpenAPI specification in JSON format |
| `http://localhost:8080/v3/api-docs.yaml` | OpenAPI specification in YAML format |
| `http://localhost:8080/swagger-ui/index.html` | Swagger UI to view and test the API |

Open `/v3/api-docs` to inspect the machine-readable documentation. In the JSON, find `paths` to see `/api/books/{id}` and `/api/books`, then check `components.schemas` to see the `BookResponse` and `CreateBookRequest` schemas. Descriptive information from `@Operation`, `@ApiResponse`, `@Parameter`, and `@Schema` is reflected in the corresponding specification.

Open Swagger UI to view the API under the Books group. Select the GET or POST operation, click **Try it out**, enter the parameter or request body, and execute. Swagger UI sends requests to the server at the address declared in the documentation; therefore, the application must be running and the browser must be able to reach the server.

Swagger UI is only an interface for reading and testing API calls. It does not replace the controller, does not persist data on its own, and does not guarantee that all business behavior matches the description.

## 7. Customizing General API Metadata

When you want the documentation to have a clear title, description, and version, declare an `OpenAPI` bean:

```java
package com.example.books;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI booksApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Books API")
                .description("Demo API for looking up and creating books")
                .version("1.0.0"));
    }
}
```

After adding the bean, reload `/v3/api-docs` to check `info.title`, `info.description`, and `info.version`. The `info.version` value is the published documentation/contract version; it does not automatically version endpoint URLs or dictate backward-compatibility policies.

## 8. Common Configuration Properties

You can customize the documentation and Swagger UI endpoint paths in `application.properties`:

```properties
# Change the path serving the OpenAPI specification
springdoc.api-docs.path=/openapi

# Change the path to access Swagger UI
springdoc.swagger-ui.path=/docs
```

With this configuration, JSON documentation is served at `/openapi`; the UI path is configured at `/docs`. Verify the actual URLs after startup and account for `server.servlet.context-path` if the application has its own context path. When changing paths, the default URLs in the previous table are no longer the corresponding access addresses.

In some environments, a team may disable the documentation or Swagger UI via configuration:

```properties
springdoc.api-docs.enabled=false
springdoc.swagger-ui.enabled=false
```

Only use these properties intentionally per environment. If a documentation endpoint returns `404`, check whether the documentation has been disabled or had its path changed before concluding that the starter is not working.

## 9. Common Issues When Generating Documentation for the First Time

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `/v3/api-docs` returns `404` | Missing Springdoc starter, wrong MVC/WebFlux starter, endpoint path changed, or disabled | Check dependencies and `springdoc.api-docs.*` |
| Controller does not appear in `paths` | Controller not discovered by component scanning or lacks valid Spring mappings | Check the `@SpringBootApplication` package and controller mappings |
| DTO schema missing fields or wrong types | Java types, getters/record components, or serialization configuration not as expected | Check the DTO and the actual JSON returned by the endpoint |
| Swagger UI opens but fails to load the spec | UI pointing to the wrong URL, context path, or proxy misconfiguration | Check the OpenAPI fetch request in the browser's Network tab |
| Swagger UI sends a request and receives `401`/`403` | API is protected by Spring Security or a gateway | Check authentication settings and test environment access permissions |
| Annotation descriptions not visible | Imported Swagger v1 annotations by mistake or annotations placed in the wrong location | Use the `io.swagger.v3.oas.annotations` package and recheck the operation/schema |

If the project uses Spring Security, the `/v3/api-docs` endpoint and Swagger UI may need appropriate access permissions in the development environment. Do not expose internal documentation publicly just to fix access errors; apply security policies appropriate to the deployment environment.

## 10. Lesson Completion Checklist

- [ ] Spring Boot application starts successfully with the right Springdoc starter.
- [ ] Controller is discovered by Spring and GET/POST endpoints work.
- [ ] Request and response DTOs are documented as schemas.
- [ ] `@Tag`, `@Operation`, `@Parameter`, and response metadata appear in the documentation.
- [ ] `/v3/api-docs` returns valid OpenAPI JSON.
- [ ] `/v3/api-docs.yaml` returns the YAML specification.
- [ ] Swagger UI displays the operations and allows testing API calls.
- [ ] The team understands that documentation is generated from controllers/DTOs, while API tests are still needed to verify actual runtime behavior.

After this hands-on lesson, you have a minimal Spring Boot REST controller documented into OpenAPI by Springdoc and displayed via Swagger UI. This is the foundation for continuing to document complex requests/responses, security, documentation groups, and API contract testing.
