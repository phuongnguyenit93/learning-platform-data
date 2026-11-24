# Code-First, Design-First Approaches and the Scope of Springdoc

When building APIs with Spring Boot, the development team needs to agree on an API contract: which endpoints exist, what data clients send, what data the server returns, how errors are represented, and how security mechanisms work. OpenAPI is a popular specification format for expressing that contract. From an OpenAPI specification, the team can generate developer documentation, configure testing tools, or generate client code.

`springdoc-openapi` connects Spring Boot applications with OpenAPI. The library reads information published by the application through controllers, data types, annotations, and configuration to generate an OpenAPI document; it also integrates Swagger UI so humans can view and try calling the API. Therefore, when choosing between a code-first or design-first approach, it is important to determine where the **source of truth for the API contract** resides and what part Springdoc plays in the workflow.

## 1. The OpenAPI Contract and Springdoc's Place

An OpenAPI document describes an API in a machine-readable structure. Common sections include:

- `info`: the API's title, version, and description.
- `servers`: base URLs that clients can use.
- `paths` and `operations`: paths, HTTP methods, parameters, request bodies, and responses.
- `components.schemas`: reusable data structures.
- `components.securitySchemes` and `security`: authentication and authorization mechanisms advertised to clients.
- `tags`: grouping of operations by function or business domain.

In a Spring Boot application, Springdoc collects information from supported Spring MVC or WebFlux mappings, parameter and return types, and OpenAPI annotations such as `@Operation`, `@Parameter`, `@Schema`, `@ApiResponse`, and `@SecurityScheme`. From that data, the library generates the OpenAPI document at application runtime.

With commonly used default settings, the key addresses are:

| Address | Purpose |
| --- | --- |
| `/v3/api-docs` | OpenAPI document in JSON format |
| `/v3/api-docs.yaml` | OpenAPI document in YAML format |
| `/swagger-ui/index.html` | Swagger UI interface for viewing and trying the API |

Paths can be changed via configuration. If the application has multiple documentation groups, Springdoc also provides documentation per group, typically in the form `/v3/api-docs/{group}`. These endpoints are documentation outputs; they do not replace the application's business endpoints.

## 2. Code-First: Starting from Spring Boot Source Code

Code-first treats the application source code as the primary place where the API is described. Developers declare controllers, request DTOs, response DTOs, and processing rules in Spring. Springdoc reads those declarations to generate the OpenAPI specification. When needing to add meaning that Java types or Spring annotations cannot fully express, developers add OpenAPI annotations or centralized configuration.

The workflow typically looks like this:

1. Design or implement controllers and DTOs in the application.
2. Use OpenAPI annotations to add descriptions, examples, responses, and required security information.
3. Start the application and open `/v3/api-docs` to inspect the generated specification.
4. Open Swagger UI to review the documentation and try calling appropriate endpoints.
5. Add specification structure checks and contract testing into the CI pipeline when the project requires it.

The following example illustrates an endpoint that reads book information. Business logic is omitted to focus on how the contract is described:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
@Tag(name = "Books", description = "Book management API")
class BookController {

    @GetMapping("/{id}")
    @Operation(summary = "Get book information by ID")
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Book found"),
        @ApiResponse(responseCode = "404", description = "Book not found")
    })
    BookResponse getById(
            @Parameter(description = "Book ID", example = "42")
            @PathVariable long id) {
        // Call the service and return the application's actual data.
        throw new UnsupportedOperationException("Illustrative example");
    }
}

@Schema(description = "Book information returned to the client")
record BookResponse(
    @Schema(description = "Book ID", example = "42")
    long id,

    @Schema(description = "Book title", example = "Spring in Action")
    String title
) {}
```

Springdoc can infer a great deal from method signatures, Spring annotations, and data types. `@Operation` adds meaning to the operation; `@ApiResponses` declares important response codes; `@Parameter` explains parameters; `@Schema` describes data structure and examples. For simple endpoints, there is no need to repeat everything Springdoc already infers accurately. Add annotations only when needed to clarify semantics, examples, error cases, or rules not clearly expressed by the code.

### Adding API-Level Metadata

General information such as title, description, and document version can be configured with an `OpenAPI` bean:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfig {

    @Bean
    OpenAPI serviceApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Book Service API")
                .description("API for searching and managing books")
                .version("1.0.0"));
    }
}
```

This example describes the version of the API document. It does not automatically decide the backward compatibility strategy or how endpoint versioning is implemented; the development team must still define those policies.

### Describing Security

If the API uses Bearer tokens, you can declare a security scheme so OpenAPI and Swagger UI understand how clients provide authentication credentials:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class ApiSecurityDocumentationConfig {}
```

Operations that need to show an authentication requirement can attach `@SecurityRequirement(name = "bearerAuth")`. This declaration helps document the security mechanism and supports entering tokens in Swagger UI. It **does not configure Spring Security**, does not issue tokens, and does not protect endpoints. Actual access permissions are still determined by the application's security mechanisms.

### Splitting Documentation into Multiple Groups

An application may serve multiple user groups, such as internal APIs, partner APIs, and public APIs. `GroupedOpenApi` lets you create separate documentation sets based on packages or paths:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupsConfig {

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partners/**")
            .build();
    }
}
```

With the illustrative configuration above, documentation for the `partner` group can be accessed at `/v3/api-docs/partner`. Specific APIs and paths in a project need to be adjusted to the actual structure. The import example above suits the Springdoc 2.x line; packages or configuration APIs may differ between major versions, so consult the documentation for the library version in use.

## 3. Design-First: Starting from the OpenAPI Contract

Design-first treats the OpenAPI document as the source of truth for the contract. The team agrees on endpoints, requests, responses, error codes, schemas, and security before finishing the implementation. Afterward, backend and frontend work from the approved contract.

The workflow typically includes:

1. Analyzing requirements and agreeing on API behavior with stakeholders.
2. Writing the OpenAPI specification in YAML or JSON, optionally using specialized design tools.
3. Reviewing and managing changes to the specification in a version control system.
4. Using the specification as the basis for server implementation, mocking, or client generation if the project workflow uses those tools.
5. Verifying whether the implementation satisfies the agreed contract.
6. Distributing the same contract version to backend, frontend, QA, and partners.

Condensed example of a book-reading contract:

```yaml
openapi: 3.0.3
info:
  title: Book Service API
  version: 1.0.0
  description: API for looking up book information
paths:
  /api/books/{id}:
    get:
      tags:
        - Books
      summary: Get book information by ID
      parameters:
        - name: id
          in: path
          required: true
          description: Book ID
          schema:
            type: integer
            format: int64
          example: 42
      responses:
        '200':
          description: Book found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BookResponse'
        '404':
          description: Book not found
components:
  schemas:
    BookResponse:
      type: object
      required:
        - id
        - title
      properties:
        id:
          type: integer
          format: int64
          example: 42
        title:
          type: string
          example: Spring in Action
```

In design-first, Springdoc is neither a contract design tool nor a code generation tool from OpenAPI. Springdoc's primary role is generating documentation from a Spring application and integrating Swagger UI. However, Swagger UI can display a pre-prepared static OpenAPI document. For example, place the file at `src/main/resources/static/contracts/openapi.yaml` so Spring Boot serves it at `/contracts/openapi.yaml`, then configure:

```properties
springdoc.swagger-ui.url=/contracts/openapi.yaml
```

Swagger UI will load the specification at the configured URL. Verify that the URL is reachable from the browser and configure static resources appropriately for how the application is packaged. If the Springdoc OpenAPI endpoint generated from controllers is also enabled, make clear which document is the canonical contract so users do not pick the wrong one between the design spec and the implementation reflection.

In a design-first workflow, teams often need separate tools or CI steps to check syntax, linting rules, version compatibility, code generation, and implementation-versus-contract verification. Swagger UI only renders the specification; rendering successfully does not prove the server implements every rule in the YAML.

## 4. Comparing Code-First and Design-First

| Criterion | Code-First | Design-First |
| --- | --- | --- |
| Source of truth | Controller, DTO, and configuration source code | Reviewed OpenAPI file |
| When contract exists | Formed alongside or after implementation | Agreed upon before implementation |
| How docs are created | Springdoc infers from the application, then metadata is added | Specification is written and managed independently; Swagger UI can display that file |
| Strengths | Close to implementation, convenient for services with existing code | Parties agree on the interface early, convenient for parallel development |
| Common risks | Docs reflect defects in code or lack business descriptions | Specification and implementation can drift without verification |
| Best suited when | Service already exists, backend team owns design and implementation | Multiple teams consume the API or contract must be approved upfront |

No single approach fits every project. A small internal service may favor code-first to reduce documentation maintenance overhead. A public API integrated by many partners often needs design-first so parties agree on changes before release. The deciding criteria should be coordination cost, contract stability, and drift control, rather than tool preference alone.

## 5. Combining Both Approaches

Many teams use a hybrid model. They design the contract clearly enough for stakeholders to align, then implement it in Spring Boot and use Springdoc to generate documentation reflecting the actual running application. A hybrid workflow can look like this:

1. Create an initial OpenAPI spec to align on endpoints, schemas, responses, and security rules.
2. Implement controllers and DTOs following the contract.
3. Use Springdoc to generate documentation from the running application.
4. Compare the generated document against the canonical contract using automated checks or controlled reviews.
5. When the contract changes, update the specification, implementation, and client examples within the same release process.

In this model, clearly define who is allowed to modify the contract and when changes are accepted. If the team picks the YAML file as the canonical source, do not silently treat code-generated docs as a replacement. If the team picks code as the canonical source, review annotation and DTO changes as part of API changes.

## 6. Scope of Springdoc: What It Can Do and What Other Tools Are Needed

Springdoc focuses on generating and serving OpenAPI documentation within the Spring Boot ecosystem. Its scope can be viewed across these responsibility areas:

| Need | Role of Springdoc |
| --- | --- |
| Endpoint and HTTP method discovery | Reads supported controller mappings in the Spring application |
| Describing requests and responses | Infers from parameters, data types, and annotations; allows adding metadata |
| Describing schemas | Generates schemas from data types and supports customization via OpenAPI annotations |
| Describing security | Includes security schemes and security requirements in the specification |
| Grouping documentation | Creates multiple OpenAPI groups according to configuration |
| Viewing and trying APIs | Integrates Swagger UI to read the spec and send test requests when the environment allows |
| Exporting documentation | Serves OpenAPI documentation as JSON or YAML via endpoints |

Springdoc does not replace the following responsibilities:

- **Business design:** the team must still decide resources, rules, processing flows, error codes, and the meaning of each data field.
- **Actual security:** security annotations in documentation do not replace Spring Security, authentication, authorization, or network configuration.
- **Contract testing:** generated documentation does not prove actual responses match schemas, status codes are right, or every error case is handled. Separate API and contract tests are required.
- **API lifecycle management:** Springdoc does not automatically determine backward compatibility policies, deprecation timelines, version bump rules, or client notification processes.
- **Code generation and API governance:** generating SDKs, creating mock servers, linting standards, diffing breaking changes, publishing portals, or managing documentation access permissions may require other tools and workflows.
- **Business content quality:** the library can infer Java types, yet cannot automatically know full semantics such as units of measure, constraint rules, state transition conditions, or why an error can occur.

For example, if a method returns `ResponseEntity<BookResponse>`, Springdoc can use the return type to build the response schema. However, it does not execute the method to verify every branch returns the right schema, nor does it know whether a `404` status is emitted properly in all cases. Those must be guaranteed at the implementation and testing layers.

## 7. Document Groups, API Versions, and Specification Versions

Three concepts must be distinguished:

- **API version:** the contract version clients use, typically expressed via paths such as `/api/v1/...`, headers, or another system convention.
- **Document version:** the `info.version` value in OpenAPI, set by the team to identify the published contract version.
- **Springdoc group:** a set of endpoints bundled into a separate document, such as `public`, `internal`, or `partner`.

A group only partitions document scope per configuration; it does not create API versions, guarantee compatibility, or enforce access permissions. If internal documentation contains sensitive information, protect the documentation endpoint with proper security configuration or do not expose it to public environments.

When changing an API, the team must evaluate the impact on existing clients. Adding an optional response field usually has a different impact than renaming a required field, changing a data type, deleting an endpoint, or altering error code semantics. Springdoc helps reflect the resulting changes in the specification; classifying breaking changes and making release decisions still belong to the team's API management process.

## 8. Choosing an Approach for a Spring Boot Project

You can use these questions to decide:

1. **Who needs to approve the contract?** If frontend, QA, partners, or multiple teams must align before the backend is finished, design-first is usually a better fit.
2. **Where does the current source of truth live?** If the service already has stable controllers and DTOs, code-first with Springdoc can be a practical starting point.
3. **What is the impact level of changes?** Public APIs or APIs with many clients require stricter contract management, versioning, and breaking-change checks.
4. **Does the team verify drift?** Whichever approach you choose, include a step to verify documentation against the implementation and test actual behavior.
5. **How is documentation distributed?** Determine whether documentation endpoints are accessible in production, who can view them, and which version is published to clients.

For a new Spring Boot service, a reasonable start is identifying key operations and schemas first, then deciding whether they are managed directly in code or in an OpenAPI file. If choosing code-first, use Springdoc to generate documentation and add annotations selectively. If choosing design-first, manage YAML/JSON as part of the contract, use Swagger UI to render it when appropriate, and add implementation verification steps. If combining both, clearly document the canonical source and synchronization mechanism.

## 9. Checklist When Adopting Springdoc in a Project

- Choose a Springdoc version compatible with the Spring Boot line and project dependencies.
- Clearly decide whether code or an OpenAPI file is the contract's source of truth.
- Verify `/v3/api-docs` and `/v3/api-docs.yaml` in the development environment.
- Add descriptions for operations, parameters, schemas, error responses, and security where needed.
- Verify that examples and data types reflect the actual contract clients need to use.
- If there are multiple API groups, configure groups and identify the corresponding documentation endpoints.
- Decide whether Swagger UI and documentation endpoints are enabled in each environment; protect internal documentation when necessary.
- Integrate specification checks and contract tests into CI according to API criticality.
- Manage contract changes, versioning, and client notifications in the release process.

Springdoc works best when the team already has clear conventions for API contracts. It automates translating information from a Spring Boot application into OpenAPI and provides an interface for reading documentation, reducing manual updates. Contract quality still depends on design decisions, declared metadata, testing, and the team's change management process.
