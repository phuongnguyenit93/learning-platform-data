# Paths, Path Item, and Operation Object

In an OpenAPI document, the `paths` section describes the API endpoints that clients can invoke. Each endpoint address is represented by a **Path Item Object**; inside a Path Item, each HTTP method such as `get`, `post`, or `delete` is described by an **Operation Object**. These three levels form the central structure that lets tools understand which endpoints an API exposes, what data each endpoint accepts, and what results it returns.

With `springdoc-openapi`, these structures are generated from Spring controller mappings, method signatures, DTOs, and additional metadata. Understanding the relationship between `Paths`, `Path Item`, and `Operation Object` helps you read generated documentation, spot missing or misdescribed endpoints, and place annotations in the right spots.

## 1. Overview of the `paths` Structure

An OpenAPI document can contain many paths. Each path is a key in the `paths` object; the key's value is a Path Item Object. Inside a Path Item, HTTP method properties point to the corresponding Operation Object.

```yaml
paths:
  /api/orders/{orderId}:
    get:
      summary: Get order details
      operationId: getOrderById
      responses:
        '200':
          description: Order found
    delete:
      summary: Cancel order
      operationId: cancelOrder
      responses:
        '204':
          description: Order canceled
```

In this example:

- `paths` is the collection of published routes.
- `/api/orders/{orderId}` is a path. The `{orderId}` segment is a path variable, substituted with a concrete value when the client sends a request.
- The path's value is a Path Item Object containing two operations: `get` and `delete`.
- Each `get` or `delete` is an Operation Object describing a distinct interaction with the resource.

A single path can have multiple operations. The same address `/api/orders/{orderId}` can support retrieving, updating, or deleting an order via different HTTP methods.

```mermaid
flowchart TD
    A[OpenAPI Document] --> B[paths]
    B --> C[Path: /api/orders/{orderId}]
    C --> D[Path Item Object]
    D --> E[GET Operation Object]
    D --> F[PUT Operation Object]
    D --> G[DELETE Operation Object]
    E --> H[Parameters, Request Body, Responses]
    F --> I[Parameters, Request Body, Responses]
    G --> J[Parameters, Responses]
```

## 2. Paths Object and Path Naming Rules

`Paths Object` maps paths to Path Item Objects. Every path key is a relative path appended to the server URL declared in `servers`. A path must start with a `/` character.

Example:

```yaml
servers:
  - url: https://api.example.com/v1
paths:
  /orders:
    get:
      responses:
        '200':
          description: Order list
```

The address the client calls is formed by combining the server URL and the path, in this example `https://api.example.com/v1/orders`. Do not include the full hostname in `paths` keys when the hostname is already declared in `servers`.

Paths can contain variables inside curly braces:

```yaml
paths:
  /customers/{customerId}/orders/{orderId}:
    get:
      responses:
        '200':
          description: Customer order details
```

When calling the endpoint, the client replaces `customerId` and `orderId` with real values. Every variable in a path must have a matching Path Parameter, and that parameter must have `required: true`. The parameter name must match the variable name in the path exactly.

```yaml
parameters:
  - name: customerId
    in: path
    required: true
    schema:
      type: string
      format: uuid
  - name: orderId
    in: path
    required: true
    schema:
      type: string
      format: uuid
```

Do not use a query parameter in place of a path parameter when the variable is already part of the path template. For example, `/orders/{orderId}` needs a parameter with `in: path`, whereas `/orders?status=PAID` uses query parameter `status`.

Path templates must be designed consistently. Two paths differing only in variable names yet sharing the same structure, such as `/users/{id}` and `/users/{userId}`, are treated as identical path templates in OpenAPI and should not be declared as two separate endpoints. If you need to distinguish resources, design a clearer path structure.

## 3. Path Item Object Describes an API Endpoint Path

A Path Item Object is the value corresponding to a key in `paths`. It groups operations sharing a path and can hold metadata shared across those operations.

Common fields of a Path Item:

| Field | Meaning |
|---|---|
| `$ref` | Reference to a Path Item defined elsewhere |
| `summary` | Summary of the path's purpose |
| `description` | Detailed path description; supports CommonMark |
| `get`, `put`, `post`, `delete`, `options`, `head`, `patch`, `trace` | Operation Objects by HTTP method |
| `servers` | List of servers applicable to operations in this path item |
| `parameters` | Parameters shared across operations in this path item |

Example of a Path Item with description and shared parameter:

```yaml
paths:
  /api/orders/{orderId}:
    summary: Operations on a single order
    description: Endpoint for interacting with an existing order.
    parameters:
      - name: orderId
        in: path
        required: true
        description: Order identifier
        schema:
          type: string
          format: uuid
    get:
      summary: Get order
      responses:
        '200':
          description: Order found
    delete:
      summary: Delete order
      responses:
        '204':
          description: Order deleted
```

In this structure, `orderId` is declared once at the Path Item level and applies to both `get` and `delete`. This organization expresses genuinely shared information. Documents generated by springdoc may place parameters inside each operation depending on analysis and configuration; both Path Item placement and Operation placement represent valid contracts.

A Path Item can also declare `servers` to override servers for all operations under that path. If omitted, operations inherit document-level servers. An operation can further specify its own servers when needed.

## 4. Operation Object Describes an HTTP Operation

An Operation Object describes a specific operation on a path. For example, `GET /api/orders/{orderId}` and `DELETE /api/orders/{orderId}` are two distinct operations that may have different descriptions, security, parameters, and responses.

Important fields:

| Field | Purpose |
|---|---|
| `tags` | Groups operations in documentation and Swagger UI |
| `summary` | Short summary of functionality |
| `description` | Description of usage, rules, and business conditions |
| `externalDocs` | Link to external documentation |
| `operationId` | Unique identifier of the operation within the document |
| `parameters` | Path, query, header, or cookie parameters |
| `requestBody` | Request payload and supported media types |
| `responses` | Possible responses that may be returned |
| `callbacks` | Callbacks associated with the operation, if any |
| `deprecated` | Marks the operation as deprecated |
| `security` | Security requirements applied to the operation |
| `servers` | Dedicated servers for the operation |

In OpenAPI, `responses` is a required field of the Operation Object. The document should describe at least one response, typically including a success response and key error responses. `operationId`, if declared, must be unique across the entire document; client generators commonly use this value to name methods in client code.

A fuller operation example:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      tags:
        - Orders
      summary: Get order details
      description: Returns an order by its identifier.
      operationId: getOrderById
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Order not found
```

## 5. Parameters at Path Item Level and Operation Level

OpenAPI allows declaring parameters at two levels:

- **Path Item level:** parameters shared by all operations belonging to that path.
- **Operation level:** parameters applying only to the specific operation being described.

A parameter is uniquely identified by the pair `name` and `in`. The `in` location can be `path`, `query`, `header`, or `cookie`. If the same `name` and `in` pair appears at both levels, the Operation-level declaration overrides the Path Item declaration. An Operation cannot use this mechanism to remove a parameter declared at the Path Item level.

For example, every operation on `/orders/{orderId}` needs `orderId`, whereas only the GET operation accepts query `includeItems`:

```yaml
paths:
  /orders/{orderId}:
    parameters:
      - name: orderId
        in: path
        required: true
        schema:
          type: string
    get:
      parameters:
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
      responses:
        '200':
          description: OK
    delete:
      responses:
        '204':
          description: No Content
```

When reviewing parameters, note several rules:

- Path parameters are always required (`required: true`).
- Query parameters are commonly used for filters, pagination, sorting, or representation options.
- Header parameters describe custom headers. Standard headers like `Accept`, `Content-Type`, and `Authorization` have dedicated mechanisms in OpenAPI; do not declare them as regular header parameters.
- Cookie parameters are used when the API genuinely receives input via cookies.
- A parameter's `schema` expresses the type, format, value domain, and constraints of the data.

## 6. Request Body and Responses Belonging to an Operation

`requestBody` describes the payload the client sends to an operation. It can have `description`, `required`, and `content`. Inside `content`, keys are media types such as `application/json`, `application/xml`, or `multipart/form-data`; values hold the corresponding schema and examples.

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
```

`responses` maps HTTP status codes or the `default` fallback to Response Objects. Each response has `description` and may have `headers`, `content`, or `links`.

```yaml
responses:
  '201':
    description: Order created
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderResponse'
  '400':
    description: Invalid request
  '409':
    description: Order state conflict
  default:
    description: Unspecified error
```

Do not document a response solely to make the spec look complete; status codes and schemas must match actual application behavior. For `GET`, `HEAD`, and `DELETE`, request body semantics are not clearly defined in HTTP and some tools may ignore or handle them inconsistently. Use a body on those methods only when the system has a specific requirement and all relevant clients explicitly support it.

## 7. Mapping from Spring Controllers to Paths and Operations

Spring MVC defines routes using mapping annotations. Springdoc reads these mappings to produce the corresponding paths and operations.

| Spring Code | OpenAPI Component Typically Generated |
|---|---|
| `@RequestMapping("/api/orders")` on controller | Common path prefix |
| `@GetMapping("/{orderId}")` | `get` operation on `/api/orders/{orderId}` |
| `@PostMapping` | `post` operation on `/api/orders` |
| `@PutMapping("/{orderId}")` | `put` operation on `/api/orders/{orderId}` |
| `@DeleteMapping("/{orderId}")` | `delete` operation on `/api/orders/{orderId}` |
| `@PathVariable` | Parameter with `in: path` |
| `@RequestParam` | Parameter with `in: query` |
| `@RequestHeader` | Parameter with `in: header` |
| `@RequestBody` | Request Body Object |
| Return type and `ResponseEntity` | Response schema inferred from content type |
| `@Operation`, `@ApiResponse` | Metadata for Operation and Responses |

Controller example:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(
        operationId = "getOrderById",
        summary = "Get order details",
        description = "Look up an order by identifier."
    )
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Order found"),
        @ApiResponse(responseCode = "404", description = "Order not found")
    })
    @GetMapping("/{orderId}")
    OrderResponse getById(
            @PathVariable UUID orderId,
            @RequestParam(required = false) Boolean includeItems) {
        // Call service and return actual data.
        throw new UnsupportedOperationException("Illustrative example");
    }

    @Operation(summary = "Create order")
    @ApiResponse(responseCode = "201", description = "Order created")
    @PostMapping
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        // Call service and return newly created order.
        throw new UnsupportedOperationException("Illustrative example");
    }
}
```

From this controller, springdoc can generate two main path operations:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Get order details
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
      responses:
        '200':
          description: Order found
        '404':
          description: Order not found
  /api/orders:
    post:
      summary: Create order
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Order created
```

This is a trimmed output illustrating the relationship between annotations and OpenAPI; full schemas, response content, and other fields depend on DTOs, configuration, springdoc version, and declared annotations.

## 8. Adding Metadata to the Operation Object

Springdoc can infer paths, methods, parameters, and schemas from Spring code. However, business descriptions, `operationId`, error responses, or documentation links often require explicit declarations.

Commonly used annotations:

- `@Operation`: declares summary, description, operationId, tags, and other operation metadata.
- `@Parameter`: adds description, examples, schema, or attributes for a parameter.
- `@ApiResponses` and `@ApiResponse`: describe status codes along with response content.
- OpenAPI's `@RequestBody`: adds description or examples for a request body when needed; distinguish this annotation from `org.springframework.web.bind.annotation.RequestBody` used for request binding in Spring MVC.
- `@Tag`: organizes operations into groups.
- `@SecurityRequirement`: expresses security requirements for an operation or controller.

Example distinguishing the two annotations named `RequestBody`:

```java
@org.springframework.web.bind.annotation.PostMapping("/orders")
@io.swagger.v3.oas.annotations.Operation(summary = "Create order")
public OrderResponse create(
        @jakarta.validation.Valid
        @org.springframework.web.bind.annotation.RequestBody
        CreateOrderRequest request) {
    // Handle order creation.
    throw new UnsupportedOperationException("Illustrative example");
}
```

In production code, use imports to avoid writing fully qualified names as in the example. The Spring annotation handles receiving request data; the OpenAPI annotation enriches the contract documentation.

## 9. Security and Servers at the Operation Level

An Operation can declare its own `security` when an endpoint has authentication requirements that differ from the rest of the document. For example, the top-level document may require a bearer token while a public lookup endpoint requires no authentication. Ensure this metadata matches the active Spring Security configuration.

An Operation can also declare its own `servers`. This is useful when an operation is served from a different host or base path, such as an upload endpoint routed to a dedicated storage service. Without its own configuration, an operation inherits servers from the Path Item level or document level according to OpenAPI precedence.

Do not use `servers` as a substitute for paths. Servers describe base URLs; paths describe the resource path after the base URL. Separating the two lets the same contract be used across multiple environments such as local, staging, and production.

## 10. Checklist When Reviewing Paths and Operations

When reading an OpenAPI document generated by springdoc, you can use the following checklist:

1. **Path:** every published URL starts with `/`, uses consistent path templates, and has no two templates with duplicate structures.
2. **HTTP method:** operations accurately reflect Spring mappings; no missing methods or unexpected methods appear.
3. **Path parameter:** every `{...}` variable has a parameter with the same name, `in: path`, and `required: true`.
4. **Shared parameters:** Path Item parameters apply to the relevant operations; Operation parameters do not accidentally duplicate `name`/`in` pairs.
5. **Operation metadata:** summary, description, tags, and operationId are clear; operationId is not duplicated anywhere in the document.
6. **Request body:** required flag, media types, and schema match the input Spring accepts.
7. **Responses:** `responses` is present, covers key status codes, and schemas match actual payloads.
8. **Security and servers:** authentication requirements and base URLs match the deployment environment and policy.
9. **Reusability:** `$ref` points to valid components and shared schemas introduce no conflicts.
10. **Runtime:** invoke endpoints to verify the contract against actual status codes and payloads.

A document can be syntactically valid yet semantically wrong. For instance, path `/api/orders/{orderId}` missing path parameter `orderId`, duplicate `operationId`, or a response declaring `200` when the controller actually returns `204` are all issues that must be resolved.

## 11. Conclusion

`Paths` defines the API endpoint addresses, `Path Item Object` groups operations and shared metadata on a single address, and `Operation Object` describes each specific HTTP interaction. Springdoc-openapi translates mappings and metadata from Spring controllers into these structures in the OpenAPI document. When you read all three levels accurately, you can trace routes in source code to parameters, request bodies, responses, and security in the contract—catching discrepancies early and keeping API documentation consistent.
