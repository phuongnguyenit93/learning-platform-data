# Reading the Specification at /v3/api-docs

When integrating springdoc-openapi into a Spring Boot application, the **/v3/api-docs** endpoint is where the application publishes the OpenAPI specification in JSON format. This specification describes the HTTP paths, methods, parameters, request bodies, responses, data schemas, and security mechanisms declared by the application. Tools such as Swagger UI, API gateways, client generators, and contract testing pipelines can all read this same document.

The key point is that **/v3/api-docs returns a description of the API**, not the business execution of each endpoint. For example, calling `/api/orders/42` might return order number 42; calling `/v3/api-docs` returns the structure describing that the API has a `/api/orders/{id}` path, accepts an `id` parameter, and can return an order schema.

## 1. How Is the /v3/api-docs Endpoint Generated?

Springdoc reads Spring components registered in the ApplicationContext, especially Spring MVC or Spring WebFlux controllers and HTTP mappings. From that information, the library builds an OpenAPI model and serializes it into JSON to return at the documentation endpoint.

Inferred information typically includes:

- Paths and HTTP methods from mapping annotations such as `@GetMapping`, `@PostMapping`, `@PutMapping`, and `@DeleteMapping`.
- Path variables, query parameters, headers, and cookie parameters from method signatures and Spring annotations.
- Request bodies from parameter types annotated with `@RequestBody`.
- Responses from return types, `ResponseEntity`, and declared response metadata.
- Schemas from DTOs, records, generic types, enums, and schema description annotations.
- Additional metadata from OpenAPI annotations such as `@Operation`, `@ApiResponse`, `@Parameter`, `@Schema`, and `@SecurityRequirement`.

Springdoc combines inferred information with metadata declared by the developer. Therefore, a controller can appear in the documentation even before many OpenAPI annotations are written; however, business descriptions, error responses, data constraints, and security requirements usually need to be added explicitly.

Documentation generation takes place inside the running application. When a controller or OpenAPI configuration changes and the application restarts or reloads its configuration, the document content is generated from the corresponding application state. The endpoint does not read source code directly from Git, nor does it pull contracts from an external YAML file unless the project intentionally implements another mechanism.

## 2. Calling the Endpoint and Saving JSON

With the default configuration, the application serves the documentation at:

```text
GET http://localhost:8080/v3/api-docs
```

Use curl to view the response:

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs
```

If you only want to save the JSON content to a file:

```bash
curl -sS -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs \
  -o openapi.json
```

On Windows PowerShell, you can explicitly invoke `curl.exe` to avoid the PowerShell alias:

```powershell
curl.exe -i -H "Accept: application/json" http://localhost:8080/v3/api-docs
curl.exe -sS -H "Accept: application/json" http://localhost:8080/v3/api-docs -o openapi.json
```

A successful response usually has HTTP status **200 OK** and a JSON Content-Type. If the application has a context path, such as `server.servlet.context-path=/shop`, the actual URL will include the context path:

```text
http://localhost:8080/shop/v3/api-docs
```

If `springdoc.api-docs.path` has been changed, use the new path instead of the default. The endpoint can also be blocked by Spring Security or a reverse proxy.

## 3. Identifying the Structure of an OpenAPI Document

The response is a JSON object following the OpenAPI structure. The abbreviated example below illustrates commonly seen sections; the application name, paths, and schemas are illustrative only:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Order API",
    "description": "Order management API",
    "version": "v1"
  },
  "servers": [
    {
      "url": "http://localhost:8080",
      "description": "Generated server url"
    }
  ],
  "paths": {
    "/api/orders/{id}": {
      "get": {
        "tags": ["orders"],
        "operationId": "getOrder",
        "summary": "Get order information",
        "parameters": [
          {
            "name": "id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Order found",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/OrderResponse"
                }
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "OrderResponse": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "status": { "type": "string" }
        }
      }
    }
  }
}
```

Key fields to recognize:

| Field | Meaning |
|---|---|
| `openapi` | The OpenAPI specification version used to represent the document, such as 3.1.0. This is not the Spring Boot or springdoc version. |
| `info` | API information such as title, description, version, and contact or license information if present. |
| `servers` | Base URLs that clients can use to call the API. |
| `tags` | Labels that group operations so the documentation is easier to navigate. |
| `paths` | Endpoints and their corresponding operations such as GET, POST, PUT, PATCH, or DELETE. |
| `components` | Reusable components, typically including schemas, parameters, responses, requestBodies, and securitySchemes. |
| `security` | Security requirements applied at the document or operation level. |

In `paths`, each path item can contain multiple operations. An operation typically has `operationId`, `summary`, `description`, `parameters`, `requestBody`, `responses`, `tags`, and `security`. Not every operation has all of these fields.

## 4. Reading paths, parameters, and requestBody

To understand a specific API, start from the key in `paths`, then inspect the HTTP method underneath.

Example:

```json
{
  "/api/orders": {
    "post": {
      "summary": "Create an order",
      "requestBody": {
        "required": true,
        "content": {
          "application/json": {
            "schema": {
              "$ref": "#/components/schemas/CreateOrderRequest"
            }
          }
        }
      },
      "responses": {
        "201": {
          "description": "Order created"
        },
        "400": {
          "description": "Invalid data"
        }
      }
    }
  }
}
```

The `parameters` section describes data passed through the URL or headers. The `in` field indicates the location:

- `path`: part of the path, e.g., `/orders/{id}`.
- `query`: query parameter, e.g., `?page=0&size=20`.
- `header`: HTTP header, e.g., `X-Request-Id`.
- `cookie`: cookie sent with the request.

A path parameter must be marked as required in OpenAPI. A query parameter can be required or optional depending on the method signature and metadata.

The `requestBody` section describes content sent in the body. `required` indicates whether the body is mandatory; `content` lists media types such as `application/json`; `schema` describes the payload structure. An endpoint can accept multiple media types, each with its corresponding schema.

The `responses` section describes outcomes by HTTP status code, such as `200`, `201`, `204`, `400`, `401`, `403`, or `404`. A response can have `description`, `headers`, `content`, and a schema. Check both success and error responses; if only the 200 response is documented, API consumers may not know the contract when sending invalid data or lacking permissions.

## 5. Understanding components and $ref

Reused schemas are typically placed in `components.schemas`. Instead of repeating the entire definition of a DTO in every operation, the document can reference it with `$ref`:

```json
{
  "schema": {
    "$ref": "#/components/schemas/OrderResponse"
  }
}
```

The path `#/components/schemas/OrderResponse` is a JSON Pointer targeting the schema named `OrderResponse` within the current document. When reading an operation, if you encounter `$ref`, open the corresponding entry in `components` to understand its fields, data types, required properties, enums, formats, and constraints.

DTO example:

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "OrderResponse", description = "Order information")
public record OrderResponse(
    @Schema(description = "Order code", example = "ORD-1001")
    String id,

    @Schema(description = "Order status", example = "CONFIRMED")
    String status
) {}
```

A schema reflects the data structure that the library can analyze. Complex business rules such as “customers can only cancel an order within 15 minutes” cannot be inferred from Java types alone; they need to be expressed in descriptions or appropriate business documentation.

## 6. Adding Metadata to Make the Specification Meaningful

The following controller example illustrates combining Spring mappings with OpenAPI annotations:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Get order information",
        description = "Look up an order by its identifier."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Order found",
        content = @Content(
            schema = @Schema(implementation = OrderResponse.class)
        )
    )
    @ApiResponse(responseCode = "404", description = "Order not found")
    ResponseEntity<OrderResponse> getOrder(
        @Parameter(description = "Order code", example = "ORD-1001")
        @PathVariable String id
    ) {
        // Call the service and return the actual result.
        return ResponseEntity.notFound().build();
    }
}
```

This example focuses on illustrating metadata. In a real application, the 200 return branch must correspond to actual service logic. The `@ApiResponse` annotation adds a response description to the contract; it does not generate that response on its own and does not alter the controller's HTTP behavior.

Some commonly used annotations:

| Annotation | Role |
|---|---|
| `@Operation` | Describes an operation, including summary, description, operationId, and tags. |
| `@Parameter` | Describes a parameter, example, location, and constraints. |
| `@ApiResponse` / `@ApiResponses` | Describes response codes and corresponding content. |
| `@Schema` | Describes a schema, field, type, example, enum, and constraints. |
| `@OpenAPIDefinition` | Declares document-level metadata such as info, servers, tags, and security. |
| `@SecurityScheme` | Defines a reusable authentication mechanism. |
| `@Hidden` | Hides an operation or component from the documentation within its applied scope. |

There is no need to annotate every field if Java types already describe it accurately. Add annotations when names, meanings, examples, or constraints are not clear from the source code.

## 7. Quick JSON Inspection with jq

If jq is installed on the machine, you can read key fields without opening the entire file:

```bash
# OpenAPI version and metadata
jq '{openapi, info, servers}' openapi.json

# List all paths
jq -r '.paths | keys[]' openapi.json

# List HTTP methods under each path
jq -r '
  .paths
  | to_entries[]
  | .key as $path
  | .value
  | to_entries[]
  | select(.key | IN("get","post","put","patch","delete","options","head","trace"))
  | "\(.key | ascii_upcase) \($path)"
' openapi.json

# List reusable schemas
jq -r '.components.schemas // {} | keys[]' openapi.json
```

If jq is not available, you can open the JSON in an IDE or JSON formatter. For large documents, search by path, operationId, or schema name rather than reading from start to finish.

Useful questions when reviewing:

- Does the expected path appear in `paths`?
- Is the HTTP method correct?
- Do path/query parameters have the right names, types, and required flags?
- Does the request body have the right media types and schema?
- Do responses cover all necessary status codes and content?
- Do schemas have the right required fields, enums, formats, and descriptions?
- Do operations requiring authentication have appropriate security requirements?

## 8. YAML Path, Swagger UI, and Endpoint Configuration

Besides JSON, springdoc commonly provides YAML documentation at:

```text
GET /v3/api-docs.yaml
```

Swagger UI is the interface for reading and testing documentation, usually accessed at:

```text
/swagger-ui.html
```

These three URLs serve different purposes:

| Default URL | Content |
|---|---|
| `/v3/api-docs` | OpenAPI specification in JSON format. |
| `/v3/api-docs.yaml` | OpenAPI specification in YAML format. |
| `/swagger-ui.html` | Swagger UI page. |

The JSON path can be changed via configuration:

```properties
springdoc.api-docs.path=/openapi
```

After this change, the JSON endpoint is served at `/openapi`. The YAML and Swagger UI paths have their own configuration properties; check the exact properties for the springdoc version in use if all URLs need to be customized.

The documentation endpoint can be disabled with:

```properties
springdoc.api-docs.enabled=false
```

When this property is disabled, requests to the default documentation endpoint will no longer return the specification. Check profile-specific configurations, such as `application-dev.yml` and `application-prod.yml`, to know which environments enable or disable the documentation.

## 9. Limiting Endpoint Scope and Grouping Documentation

An application may have many controllers, or need to provide separate documentation for each API group. Springdoc supports filtering by package and path, for example:

```properties
springdoc.packages-to-scan=com.example.shop.api
springdoc.paths-to-match=/api/**
springdoc.paths-to-exclude=/api/internal/**
```

Filter properties help limit which handlers are included in the default documentation. If an endpoint does not appear, check package scan, path filters, hidden annotations, and whether the controller is actually registered by Spring.

For grouped documentation, you can declare `GroupedOpenApi`:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
```

After declaring groups, each group's documentation can be accessed in the form:

```text
/v3/api-docs/public
/v3/api-docs/admin
```

The group name is part of the URL. If a group has no matching paths or is not registered, the group endpoint may return an error or an empty document depending on configuration and version. Verify each group directly.

## 10. Security and Documentation Access Permissions

The `/v3/api-docs` endpoint is an HTTP endpoint of the application. Therefore, Spring Security, gateways, and reverse proxies can apply access policies just like for any other endpoint. When calling from a browser or pipeline, determine whether the documentation should be publicly accessible or require authentication.

The example below permits access to documentation URLs in a Spring Security configuration; apply it only when the system policy allows:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        "/v3/api-docs/**",
        "/swagger-ui/**",
        "/swagger-ui.html"
    ).permitAll()
    .anyRequest().authenticated()
);
```

If the documentation is for internal use only, protect the endpoint with an appropriate authentication mechanism. Do not enable `permitAll` out of habit, because the documentation can reveal endpoint structures, operation names, and internal data models. Even though OpenAPI contains no actual business data, its contents can still be useful for anyone probing the API surface.

When using OAuth2, JWT, or HTTP Basic, security components must be described in OpenAPI using security schemes and security requirements. Simply being able to open the JSON endpoint does not prove the documentation accurately describes the authentication mechanism.

## 11. Verifying the Contract Instead of Just HTTP 200

A 200 response from `/v3/api-docs` proves the documentation endpoint is reachable. It does not prove the documentation is complete or matches the contract expected by the development team.

At least three layers should be checked:

1. **Availability:** does the endpoint return valid JSON with the right Content-Type and status code?
2. **Completeness:** do the necessary paths, methods, requests, responses, schemas, and security requirements appear?
3. **Accuracy:** do field names, data types, required flags, enums, response codes, and descriptions match API behavior?

The specification can be saved as an artifact in CI and compared against an approved baseline. If the contract changes, the team should treat it as an API change that could affect clients. OpenAPI linters/validators can catch structural errors, naming conventions, or breaking changes; integration tests are still required to verify runtime behavior.

A simple verification workflow:

```bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
jq -e '.openapi and .info.title and (.paths | type == "object")' openapi.json
```

The second command checks a few basic fields. For deeper contract checks, add assertions for key paths and schemas of the system, or use an OpenAPI validator in the pipeline.

## 12. Common Troubleshooting

| Symptom | Causes to Check |
|---|---|
| `404 Not Found` at `/v3/api-docs` | `springdoc.api-docs.path` changed, context path configured, `springdoc.api-docs.enabled` disabled, or request routed through a proxy with a different prefix. |
| `401 Unauthorized` or `403 Forbidden` | Spring Security, gateway, or proxy requires authentication or blocks documentation URLs. |
| JSON returns 200 but `paths` is empty or missing endpoints | Controller not registered, package/path filter excluding endpoints, endpoints hidden, or application did not load the intended configuration. |
| Path appears but lacks parameters or schemas | Data types, mapping annotations, parameter name metadata, or generic types not clear enough. |
| Swagger UI does not display the documentation | Check the JSON URL the UI is calling, group name, context path, CORS, and access permissions. |
| `servers` field contains the wrong URL when running behind a proxy | Check forwarded headers, proxy configuration, and how the application determines the base URL. |
| 500 error while generating documentation | Check the stack trace to identify unhandled data types or configuration; check the dependency tree and springdoc/Spring Boot version compatibility. |

When investigating, call the JSON endpoint directly with curl first. If curl also gets an error, focus on the application, security, and routing. If the JSON returns properly but Swagger UI fails, inspect the browser request sent to the documentation endpoint, including URL, group, and authentication headers.

## 13. Checklist for Reading /v3/api-docs in a Project

- [ ] Called the right URL, including context path and custom path if any.
- [ ] Response has the proper status code and JSON Content-Type.
- [ ] `openapi` and `info` fields have accurate values.
- [ ] Important paths and HTTP methods are present.
- [ ] Parameters and requestBody have accurate names, types, required flags, and media types.
- [ ] Responses describe all necessary status codes and schemas.
- [ ] Schemas referenced via `$ref` are defined in components.
- [ ] Security schemes and security requirements accurately reflect policy.
- [ ] Group endpoints, if present, return the expected set of APIs.
- [ ] Documentation has been verified with a validator or assertions in CI.

## 14. Reference Sources

- [Official springdoc-openapi documentation](https://springdoc.org/)
- [springdoc-openapi – FAQ and configuration properties](https://springdoc.org/#properties)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Swagger – OpenAPI Specification overview](https://swagger.io/specification/)

Default paths and configuration properties may change across springdoc versions. When upgrading the library, consult the documentation for the exact version line and re-verify the endpoint in the running application.
