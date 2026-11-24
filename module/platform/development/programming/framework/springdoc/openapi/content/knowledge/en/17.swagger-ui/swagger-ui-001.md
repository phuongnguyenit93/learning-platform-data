# Role of Swagger UI as an API Reading and Try-It-Out Tool

Swagger UI is a web interface that helps developers read OpenAPI specifications and send test requests to an API. When integrated with springdoc-openapi in Spring Boot, the application can automatically generate the specification from controllers, DTOs, and annotations, then provide that specification to Swagger UI for display. Users can view endpoints, parameters, request bodies, responses, and execute requests directly in the browser.

Swagger UI makes exploring and testing HTTP contracts more convenient. It does not replace the OpenAPI specification, does not implement endpoints, and does not itself guarantee that the API works properly. Requests are sent over the network to a real server, so results also depend on the target URL, authentication, access permissions, CORS, and application state.

## 1. Distinguishing OpenAPI, springdoc-openapi, and Swagger UI

These three components often appear together but perform three different roles:

| Component | Role | Result |
|---|---|---|
| OpenAPI Specification | Standard format for describing HTTP contracts | JSON or YAML document |
| springdoc-openapi | Reads Spring Boot structure and generates the OpenAPI specification | Endpoint serving the API documentation |
| Swagger UI | Reads the specification and renders an interactive interface | Web page for viewing and testing operations |

For example, a controller has the endpoint <code>GET /products/{productId}</code>. springdoc-openapi reads the mapping, parameter types, and DTOs to create the corresponding operation in the document. Swagger UI loads that document, displays the operation, and provides a form for the user to enter <code>productId</code>, click Execute, and inspect the response.

General flow:

~~~mermaid
flowchart LR
    A["Spring Controllers and DTOs"] --> B["springdoc-openapi"]
    B --> C["OpenAPI JSON or YAML"]
    C --> D["Swagger UI"]
    D --> E["User selects operation"]
    E --> F["Try it out / Execute"]
    F --> G["HTTP request to API"]
    G --> H["HTTP response"]
    H --> D
~~~

Swagger UI does not automatically scan every URL on the server to find endpoints. It displays the operations present in the OpenAPI document it is configured to load.

## 2. Installing Swagger UI with springdoc-openapi

For a Spring MVC application, add the UI starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Set the version in Maven properties or dependency management to a version compatible with the project's Spring Boot version. Do not copy an arbitrary version while ignoring the compatibility matrix.

For a Spring WebFlux application, use the corresponding artifact:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

If the application only needs to export the specification for an API Portal or other tools, you can choose the corresponding API starter. The API starter provides the OpenAPI document without packaging the Swagger UI interface. When you want to view and test the API in a browser, choose the UI starter.

After adding the dependency and starting the application, the commonly used default paths are:

| Path | Content |
|---|---|
| <code>/v3/api-docs</code> | OpenAPI specification in JSON format |
| <code>/v3/api-docs.yaml</code> | OpenAPI specification in YAML format |
| <code>/swagger-ui.html</code> | Swagger UI entry point, typically redirecting to UI resources |
| <code>/swagger-ui/**</code> | Static resources for the Swagger UI interface |

Paths may vary depending on configuration, context path, or reverse proxy. If the project has customized <code>springdoc.api-docs.path</code> or <code>springdoc.swagger-ui.path</code>, use the actual configured URL.

## 3. Controller example for Swagger UI display

Consider a product management API:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
class ProductController {

    @Operation(
        operationId = "getProductById",
        summary = "Get product by ID"
    )
    @GetMapping("/{productId}")
    ProductResponse getById(
            @Parameter(description = "Product ID")
            @PathVariable("productId") String productId) {
        return new ProductResponse(productId, "Wireless Mouse", 299000);
    }

    @Operation(
        operationId = "createProduct",
        summary = "Create a new product"
    )
    @PostMapping
    ResponseEntity<ProductResponse> create(
            @RequestBody CreateProductRequest request) {
        ProductResponse response = new ProductResponse(
            "SKU-200",
            request.name(),
            request.price()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}

record CreateProductRequest(
    @Schema(example = "Mechanical Keyboard")
    String name,
    @Schema(example = "1599000")
    Integer price
) {}

record ProductResponse(
    String productId,
    String name,
    Integer price
) {}
~~~

springdoc-openapi uses the mappings and data types above to generate two operations. <code>@Operation</code> adds an identifier and summary; <code>@Parameter</code> adds a parameter description; <code>@Schema</code> adds examples for DTO properties.

A portion of the JSON document might look similar to:

~~~yaml
paths:
  /products/{productId}:
    get:
      operationId: getProductById
      summary: Get product by ID
      parameters:
        - name: productId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
  /products:
    post:
      operationId: createProduct
      summary: Create a new product
      requestBody:
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateProductRequest"
      responses:
        "201":
          description: Created
~~~

Swagger UI does not directly read the Java code in the example. It reads the operations and schemas that springdoc-openapi has placed into the document.

## 4. Reading documentation in Swagger UI

When opening Swagger UI, users typically see tag groups and a list of operations. Each operation can be expanded to inspect:

- HTTP method and path.
- <code>summary</code>, <code>description</code>, <code>operationId</code>, and tags.
- Path, query, header, or cookie parameters.
- Request body and supported media types.
- Schemas, enums, constraints, and examples.
- Response codes, headers, and response bodies.
- Security details if the specification declares security schemes.

Readers can use the schema section to understand data structures before calling the API. If an operation includes request or response examples, Swagger UI can display those examples for users to select and reference.

This is a contract-reading interface: the displayed content depends on the quality of the specification. If a controller lacks descriptions, has inaccurate response schemas, or omits examples, Swagger UI cannot infer the missing business semantics on its own.

## 5. Using Try it out to test APIs

For operations supporting interaction, Swagger UI has a **Try it out** button. When this mode is enabled, users can input parameters, edit the request body, choose a content type, and execute the request using **Execute**.

Typical workflow:

1. Open the tag group containing the endpoint to test.
2. Open the operation, for example <code>GET /products/{productId}</code>.
3. Click Try it out.
4. Enter a value for <code>productId</code>.
5. Click Execute to send the request.
6. Read the request URL, sample curl, HTTP status, response headers, and response body displayed by the UI.

For <code>POST /products</code>, the user can enter JSON:

~~~json
{
  "name": "Mechanical Keyboard",
  "price": 1599000
}
~~~

Swagger UI constructs the request based on the operation and schema in OpenAPI. The request is then sent from the browser to the server URL selected in the document. The server processes the request through controllers, filters, security, validation, and business logic just like any other HTTP client.

Clicking Execute sends a real request. For <code>POST</code>, <code>PUT</code>, <code>PATCH</code>, or <code>DELETE</code>, the action may create, modify, or delete data. State-mutating operations should be tested on local, development, or staging environments with test data.

## 6. Server URL determines where requests go

OpenAPI can declare one or more servers. Swagger UI uses the selected server URL to build the target request URL:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "http://localhost:8080",
            description = "Local environment"
        ),
        @Server(
            url = "https://api.example.com",
            description = "Staging API"
        )
    }
)
class OpenApiServerConfiguration {
}
~~~

Swagger UI can display a list of servers for users to choose from. Make sure the server URL matches the current environment and actual base path.

Do not let production documentation accidentally point to the viewer's localhost. Likewise, do not publish a production server as the default choice in documentation meant for development environments if Try it out could submit real write operations.

When an application runs behind a reverse proxy or gateway, the public URL may differ from the internal address seen by Spring Boot. Configure forwarded headers, context path, and server URL so Swagger UI builds requests with the right host, scheme, and prefix.

## 7. Authentication in Swagger UI

Swagger UI can display an **Authorize** button when the OpenAPI document declares security schemes. HTTP Bearer example:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class ApiSecurityDocumentation {
}
~~~

An operation or controller can require that scheme:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@RestController
@RequestMapping("/profile")
@SecurityRequirement(name = "bearerAuth")
class ProfileController {
    // Operations requiring a Bearer token
}
~~~

When the user enters a token in the Authorize dialog, Swagger UI can attach the <code>Authorization: Bearer ...</code> header to requests covered by the described security scope. How the interface stores and uses credentials depends on Swagger UI configuration.

A security scheme only describes the mechanism for documentation readers. It does not enable authentication in Spring Security and does not grant permissions to requests. The application must still configure authentication, authorization, and server-side permission checks. If the token is invalid, the server may return <code>401</code>; if the user is authenticated but lacks permissions, the server may return <code>403</code>.

Only use test tokens in appropriate environments. Do not enter production credentials on shared computers or share screenshots containing tokens.

## 8. CORS when Swagger UI and the API have different origins

Browsers enforce the Same-Origin Policy. If Swagger UI is served from one origin while the API resides on another origin, requests may be blocked by CORS unless the server allows the corresponding origin, methods, and headers.

Example:

- Swagger UI: <code>https://docs.example.com</code>
- API: <code>https://api.example.com</code>

The two hosts differ, making these two different origins. When Swagger UI calls the API, the API server must return appropriate CORS headers. With Bearer tokens, preflight requests may need to allow the <code>Authorization</code> header.

If Swagger UI is served from the same origin as the API, CORS issues are usually simpler because requests share the same origin. Even so, a proxy or domain alias can still cause the browser to treat them as different origins.

Do not resolve CORS errors by opening up all origins in production. Only allow trusted documentation origins and the methods/headers genuinely needed.

## 9. Configuring Swagger UI and OpenAPI paths

Default paths can be changed in <code>application.yml</code>:

~~~yaml
springdoc:
  api-docs:
    path: /openapi
  swagger-ui:
    path: /docs
~~~

With this configuration, the JSON document uses path <code>/openapi</code>; the Swagger UI interface uses <code>/docs</code>. The YAML version is accessible via the corresponding document path if the YAML endpoint is enabled.

Several other properties can adjust the interface:

~~~yaml
springdoc:
  swagger-ui:
    operationsSorter: method
    tagsSorter: alpha
    displayRequestDuration: true
    docExpansion: none
~~~

These properties modify how operations are presented and sorted. They do not change controller mappings or the HTTP contract. Configuration names and values should be checked against the springdoc version in use.

## 10. Limitations of Swagger UI

Swagger UI is helpful for reading and testing, but its limitations must be clearly understood:

| What Swagger UI can do | What Swagger UI does not do automatically |
|---|---|
| Display operations according to OpenAPI | Automatically discover endpoints missing from the document |
| Display schemas, parameters, and examples | Guarantee that schemas match runtime behavior |
| Build sample requests and send them via browser | Replace automated testing or contract tests |
| Display status, headers, and response body | Fix backend bugs or data issues |
| Attach credentials according to security schemes | Configure Spring Security or grant permissions |
| Help users test APIs | Replace Postman, curl, test suites, or monitoring in every scenario |

Swagger UI is also affected by the browser, network, TLS certificates, DNS, proxies, and CORS. A failed request in the UI is not enough to conclude that an endpoint is broken; inspect the request URL, browser console/network tab, and server logs.

## 11. Securing and operating Swagger UI

API documentation can expose endpoint structures, field names, business flows, and internal responses. Before enabling Swagger UI in a shared environment, determine who is permitted to access it:

- Development environments may be open to the development team.
- Staging may require login or restrict access via an internal network.
- Production may disable the UI, restrict permissions, or serve only approved documentation.

Spring Security can be used to protect documentation and UI paths according to system policy. Consider <code>/swagger-ui/**</code>, the <code>/swagger-ui.html</code> entry point or custom path, <code>/v3/api-docs</code>, and the YAML endpoint. If only the UI page is protected while the JSON document remains public, users can still download the specification directly.

Do not treat hiding the Swagger UI button as an API security measure. Business endpoints must be protected independently via authentication and authorization.

## 12. Common issues

**Swagger UI does not open.** Check whether the appropriate UI starter for MVC/WebFlux is used, whether the application started successfully, and whether the context path and <code>springdoc.swagger-ui.path</code> are correct. If only the API starter is installed, no UI interface is included.

**The page opens but has no operations.** Check the document URL loaded by the UI, the <code>/v3/api-docs</code> response, group configurations, and whether controllers are scanned by springdoc.

**Try it out sends requests to the wrong host or path.** Check <code>servers</code>, context path, reverse proxy, forwarded headers, and the server URL currently selected in the interface.

**Requests return 401 or 403.** Check the token, security scheme, security requirement, and Spring Security policy. Authorize in Swagger UI does not grant permissions on its own.

**Browser reports CORS errors.** Check the UI page origin, the API's CORS policy, preflight requests, and allowed headers.

**Request succeeds but response differs from documentation.** Cross-check the controller, DTO, Jackson serializer/deserializer, exception handler, and the generated schema at <code>/v3/api-docs</code>.

**Execute modifies data.** That is the behavior of the invoked HTTP operation. Use an appropriate environment and test data, especially for write or delete operations.

## 13. Workflow for testing an API with Swagger UI

1. Start Spring Boot with the UI starter and verify the OpenAPI JSON endpoint.
2. Open Swagger UI at the configured path.
3. Confirm the interface loads the right document and right server URL.
4. Pick a read operation first and inspect path/query/header parameters.
5. Use Try it out, enter valid values, and click Execute.
6. Read the request URL, status, response headers, and body.
7. Try invalid input to observe the validation response if the environment allows it.
8. For operations requiring authentication, use a test token and verify that the server enforces permissions properly.
9. For data-mutating operations, use test resources and verify the state after the request.
10. Record discrepancies between documentation, actual responses, and business rules to update the contract or implementation.

## 14. Checklist before sharing Swagger UI

- [ ] Application uses the right UI starter for Spring MVC or WebFlux.
- [ ] <code>/v3/api-docs</code> or the custom docs path returns valid OpenAPI.
- [ ] Swagger UI loads the right document and displays expected operations.
- [ ] Server URL points to the right environment.
- [ ] Security schemes and requirements match the actual security configuration.
- [ ] CORS allows the proper origin if the UI and API are on different origins.
- [ ] Write/delete operations are tested in an appropriate environment.
- [ ] Access controls are defined for both the UI and the JSON/YAML endpoints.
- [ ] Actual responses are cross-checked against schemas and examples.

## References

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html): dependencies and default endpoints for OpenAPI and Swagger UI.
- [springdoc-openapi – Properties](https://springdoc.org/properties.html): configuring documentation and UI paths.
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): how to configure the Swagger UI interface.
- [OpenAPI Specification – Server Object](https://spec.openapis.org/oas/latest.html#server-object): declaring server URLs in the specification.
- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object): describing authentication mechanisms and security requirements.
- [MDN – CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): how browsers control cross-origin requests.
