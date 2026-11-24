# Runtime Expressions in Response Links

An API often consists of multiple interrelated operations. After creating an order, the client needs to use the order ID it just received to call the detail-retrieval endpoint; after generating an invoice, the client can call the corresponding invoice-download endpoint. The OpenAPI Link Object describes this relationship directly inside the source operation's response. Runtime expressions allow extracting values from the current request or response and mapping them into parameters or the request body of the target operation.

With `springdoc-openapi`, you can declare response links using the `@Link` and `@LinkParameter` annotations. When the documentation is generated, clients and OpenAPI-reading tools know which operation can be invoked next and where to pull the data from. Links only describe relationships in the contract; they do not automatically call endpoints, replace authorization, or inject hypermedia links into JSON responses.

## 1. What problem does the Link Object solve?

Suppose an API has two operations:

- `POST /api/orders` creates an order and returns `id`.
- `GET /api/orders/{orderId}` retrieves order details by ID.

The client must read `id` from the order-creation response and then pass that value into the `orderId` path parameter of the GET operation. Looking at the two endpoints in isolation, the client has to deduce this relationship on its own.

The OpenAPI Link Object allows describing this relationship directly in the `201` response of the order-creation operation:

```yaml
paths:
  /api/orders:
    post:
      operationId: createOrder
      responses:
        '201':
          description: Order created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
          links:
            getCreatedOrder:
              operationId: getOrder
              parameters:
                orderId: '$response.body#/id'
  /api/orders/{orderId}:
    get:
      operationId: getOrder
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Order details
```

After receiving the response from `createOrder`, the expression `$response.body#/id` extracts the `id` field from the response body and supplies that value to the `orderId` parameter of the `getOrder` operation.

Links help documentation convey operation flows, reduce guesswork for clients passing data between endpoints, and support tools in building step-by-step API experiences.

## 2. Where does the Link Object live in an OpenAPI document?

A Link Object is declared in the `links` map of a Response Object. Each key in the map is a link name; the value is a Link Object describing the target operation and how data is passed.

Important fields of the Link Object:

| Field | Meaning |
|---|---|
| `operationId` | Identifier name of the target operation |
| `operationRef` | URI reference pointing to the target Operation Object |
| `parameters` | Maps parameter names of the target operation to values or runtime expressions |
| `requestBody` | Value or runtime expression used as the request body of the target operation |
| `description` | Explains the relationship and how to use the link |
| `server` | Server used for the target operation if overriding an inherited server |

A Link Object must specify the target operation using either `operationId` or `operationRef`. Choose only one of the two. `operationId` is usually easier to read and convenient when operations have stable names; `operationRef` is useful when you want to reference an operation's location directly within the document or in an external document.

Minimal Link Object example:

```yaml
links:
  getCreatedOrder:
    operationId: getOrder
    parameters:
      orderId: '$response.body#/id'
```

`getCreatedOrder` is the name of the link in the response; `getOrder` is the target operation. These two names play different roles.

## 3. What is a runtime expression?

A runtime expression is a syntax for referencing information available in the request or response currently being processed. When a client or tool executes a link, the expression is evaluated in the context of the source interaction to retrieve a value to supply to the target operation.

Main data sources:

| Category | Expression | Extracted data |
|---|---|---|
| Request URL | `$url` | Full URL of the source request |
| Request method | `$method` | HTTP method of the source request |
| Response status | `$statusCode` | Status code of the source response |
| Request path | `$request.path.orderId` | Path parameter named `orderId` |
| Request query | `$request.query.page` | Query parameter named `page` |
| Request header | `$request.header.X-Request-Id` | Corresponding request header |
| Request body | `$request.body` | Entire request body |
| Part of request body | `$request.body#/customer/id` | Value at the JSON Pointer inside the request body |
| Response header | `$response.header.Location` | Response header named `Location` |
| Response body | `$response.body` | Entire response body |
| Part of response body | `$response.body#/id` | Value at the JSON Pointer inside the response body |

Expressions are written as strings. In YAML, wrap runtime expressions in quotes to prevent the parser from interpreting special characters according to YAML syntax.

## 4. Extracting values from the response body

This is the most common case when linking resource-creation and resource-reading operations. Suppose the `201` response has the structure:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "CREATED",
  "customer": {
    "id": "cus-100"
  }
}
```

You can extract the top-level ID with:

```text
$response.body#/id
```

Or extract the nested customer ID with:

```text
$response.body#/customer/id
```

Example mapping to the order-details operation:

```yaml
links:
  getCreatedOrder:
    operationId: getOrder
    parameters:
      orderId: '$response.body#/id'
```

The part after `#` is a JSON Pointer relative to the response body. Property names must match the actual JSON structure returned after Jackson serializes the DTO. If the Java DTO has a field `orderId` but Jackson outputs it as `id` in JSON, the expression must reference `#/id`.

When the response body is an array, a JSON Pointer can access an element by index, such as `$response.body#/items/0/id`. However, only use such an expression when the response is guaranteed to have an element at that position; if the array is empty, no value can be extracted along that path.

## 5. JSON Pointer rules in runtime expressions

Runtime expressions can combine JSON Pointers to extract nested properties. JSON Pointer uses `/` to separate each token. Certain characters inside property names must be escaped:

| Character in property name | Written in JSON Pointer |
|---|---|
| `~` | `~0` |
| `/` | `~1` |

Example response:

```json
{
  "metadata": {
    "external/id": "ext-42",
    "display~name": "Sample order"
  }
}
```

Corresponding expressions:

```text
$response.body#/metadata/external~1id
$response.body#/metadata/display~0name
```

Failing to escape `/` or `~` properly can cause the JSON Pointer to point to a different token and fail to retrieve the desired data.

## 6. Extracting values from the source request

Runtime expressions can also pull information that the client sent in the source request. This is useful when the target operation needs to reuse a filter, version, or identifier already present in the preceding request.

For example, an order-search API accepts a `customerId` query parameter and returns results. A link to the get-customer operation can reuse that query parameter:

```yaml
paths:
  /api/orders:
    get:
      operationId: searchOrders
      parameters:
        - name: customerId
          in: query
          required: true
          schema:
            type: string
      responses:
        '200':
          description: List of orders
          links:
            getCustomer:
              operationId: getCustomer
              parameters:
                customerId: '$request.query.customerId'
```

Available request sources:

- `$request.path.{name}` for path parameters.
- `$request.query.{name}` for query parameters.
- `$request.header.{name}` for request headers.
- `$request.body` or `$request.body#/{pointer}` for the request body.

Parameter names in the source expression must match the actual names in the request. For the request body, the JSON Pointer must point to a property present in the submitted payload.

## 7. Extracting values from response headers

Some APIs return the URI of a newly created resource in the `Location` header. A link can use that header as a data source for the next operation.

Example response:

```http
HTTP/1.1 201 Created
Location: https://api.example.com/api/orders/550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json
```

Expression to read the header:

```text
$response.header.Location
```

Inside a Link Object, the expression can be used for a parameter of the target operation if the header value fits that parameter's type. If `Location` holds a full URL while the target parameter accepts only a UUID, you cannot pass the entire URL directly into `orderId`; in that case, also return the ID in the body and use `$response.body#/id`, or design the target operation to accept the URI appropriately.

Example mapping the header into a header parameter of the target operation:

```yaml
links:
  followLocation:
    operationId: getResourceByLocation
    parameters:
      resourceUrl: '$response.header.Location'
```

In this example, the `getResourceByLocation` operation must have a parameter named `resourceUrl` with a matching location and type. A link does not parse a URI to extract a path segment into an ID.

## 8. Passing a request body to the next operation

The Link Object has a `requestBody` field, allowing you to supply a value for the target operation's body. The value can be a runtime expression reading from the source request or response.

For example, a response returns an object containing a normalized payload to send to a confirmation operation:

```yaml
links:
  confirmOrder:
    operationId: confirmOrder
    requestBody: '$response.body#/confirmation'
```

The `confirmOrder` operation needs a request body compatible with the structure at `confirmation`. If an expression selects the entire response body while the target operation accepts only a nested DTO, point to the exact JSON Pointer or adjust the contract so the two structures align.

Do not use `requestBody` to forward secrets or unintended internal data. Links are contract metadata readable by tools and clients; only map data that API consumers are permitted to use.

## 9. Linking operations with `operationId` and `operationRef`

### Using `operationId`

This is the most readable approach:

```yaml
links:
  getCreatedOrder:
    operationId: getOrder
    parameters:
      orderId: '$response.body#/id'
```

The target operation must declare a unique `operationId` within the document:

```yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrder
```

Set `operationId` explicitly via `@Operation(operationId = "...")` instead of relying on default names generated from method names or mappings. Changing an `operationId` can break links in the documentation and affect client generators.

### Using `operationRef`

`operationRef` points directly to an Operation Object via a URI reference. Example of an internal reference to `GET /api/orders/{orderId}`:

```yaml
links:
  getCreatedOrder:
    operationRef: '#/paths/~1api~1orders~1{orderId}/get'
    parameters:
      orderId: '$response.body#/id'
```

In `operationRef`'s JSON Pointer, `/` characters in the path key are escaped as `~1`. `operationRef` is useful when an operation lacks an `operationId` or when referencing a specific operation directly. If referencing an external document, the URI reference must point to a valid document and location, and consuming tools must be able to access that document.

Do not declare both `operationId` and `operationRef` inside the same Link Object. Pick the appropriate referencing style and keep it stable when paths or operation names change.

## 10. Declaring response links with springdoc annotations

Springdoc integrates Swagger annotations to describe Link Objects. You can place `@Link` inside the `links` attribute of `@ApiResponse`; each `@LinkParameter` maps one parameter of the target operation to a runtime expression.

Example of an order-creation controller and order-reading controller:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.links.Link;
import io.swagger.v3.oas.annotations.links.LinkParameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(operationId = "createOrder", summary = "Create order")
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Order created",
            links = {
                @Link(
                    name = "getCreatedOrder",
                    operationId = "getOrder",
                    description = "Get details of the newly created order",
                    parameters = {
                        @LinkParameter(
                            name = "orderId",
                            expression = "$response.body#/id"
                        )
                    }
                )
            }
        )
    })
    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }

    @Operation(operationId = "getOrder", summary = "Get order details")
    @GetMapping("/{orderId}")
    OrderResponse getById(@PathVariable UUID orderId) {
        return orderService.getById(orderId);
    }
}
```

`CreateOrderRequest`, `OrderResponse`, and `orderService` are illustrative application types/components. Important annotation parts include:

- `@ApiResponse(responseCode = "201")` attaches the link to the success response.
- `@Link(name = "getCreatedOrder")` names the link in the response.
- `operationId = "getOrder"` identifies the target operation.
- `@LinkParameter(name = "orderId", expression = "$response.body#/id")` pulls the ID from the response body and passes it to the `orderId` parameter.
- `@Operation(operationId = "getOrder")` ensures the target operation has the exact ID referenced by the link.

After starting the application, inspect `/v3/api-docs` or `/v3/api-docs.yaml` to confirm `links` is generated under the right response code. Annotation syntax must be compatible with the version of `swagger-annotations` used by springdoc.

## 11. Complete YAML example: create an order then view details

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: '1.0'
paths:
  /api/orders:
    post:
      operationId: createOrder
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
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
          links:
            getCreatedOrder:
              operationId: getOrder
              description: Use the ID in the response to fetch the newly created order
              parameters:
                orderId: '$response.body#/id'
        '400':
          description: Invalid order creation data
  /api/orders/{orderId}:
    get:
      operationId: getOrder
      summary: Get order details
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Order details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Order not found
components:
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - customerId
      properties:
        customerId:
          type: string
          format: uuid
    OrderResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
```

Exchange flow:

1. The client calls `POST /api/orders` with `CreateOrderRequest`.
2. The server returns `201` with `OrderResponse` containing the `id` property.
3. The `getCreatedOrder` link extracts `id` using `$response.body#/id`.
4. Tools understand that value is passed into `orderId` of the `getOrder` operation.
5. The client can perform `GET /api/orders/{orderId}` to read the order.

Links do not modify the response body. If the API also wants the client to receive a related URL in JSON, the application still must return that URL as a dedicated property or implement an appropriate hypermedia format.

## 12. Link Object differs from HTTP `Link` header and hypermedia body

These concepts have similar names but operate at different layers:

| Mechanism | Location | Purpose |
|---|---|---|
| OpenAPI Link Object | In the OpenAPI document, under `responses.<code>.links` | Describes the next operation and how to extract parameters/body from the source request/response |
| HTTP `Link` header | HTTP response header | Provides link relationships between resources, typically using URI reference and relation syntax |
| Hypermedia in JSON (e.g., HAL `_links`) | Inside the response body | Returns actual URLs or links for clients to discover resources |
| OpenAPI Callback Object | In the OpenAPI document, under an operation | Describes requests a provider can send back to a callback URL supplied by the client |

Declaring an OpenAPI Link does not automatically add a `Link` header, generate `_links` in JSON, or create a callback endpoint. If the API uses hypermedia, implement the corresponding payload or header at runtime; OpenAPI Links can supplementally describe those relationships in the contract.

## 13. When are links evaluated and who executes them?

Runtime expressions are evaluated against the source operation's request/response when a tool or client uses the Link Object. The server does not automatically invoke the target operation merely because the documentation contains a link.

For example, after a `201` response, a tool supporting OpenAPI Links can:

1. Read the `getCreatedOrder` Link Object.
2. Identify the target operation `getOrder`.
3. Evaluate `$response.body#/id` from the response just received.
4. Populate the value into the `orderId` parameter.
5. Allow the user or client to invoke the target operation.

Whether a tool automatically executes the request or only displays a suggestion depends on the tool's support and policy. Do not assume every Swagger UI version or client generator executes all types of Link Objects.

If an expression fails to extract a value—for example, the response body lacks an `id` property—the target operation cannot be invoked properly. Design compatible response schemas, runtime expressions, and target parameters, then verify against actual responses.

## 14. Limitations and considerations when designing runtime expressions

- Expressions must reference the right data source on the current operation: request or response.
- Path/query/header parameter names must match the actual request.
- JSON Pointers must point to real properties and escape `~`/`/` according to the rules.
- Extracted values must be compatible with the type and location of the target operation's parameter or request body.
- Do not assume Link Objects automatically parse URLs, split out IDs, or convert data types.
- Do not assume every response has a body; `204` responses normally have no body to use with `$response.body`.
- For responses with multiple media types, body expressions must fit the representation actually returned.
- If `operationId` changes, update all links referencing it.
- If using `operationRef`, path or document structure changes can invalidate the URI reference.
- Do not map tokens, passwords, or sensitive data into the target operation unnecessarily.

Links only describe how operations connect. They do not guarantee the caller has permission to run the target operation; authorization is still checked independently on the target endpoint.

## 15. Verifying response links in the generated documentation

After adding annotations or link configuration, verify both the OpenAPI structure and runtime data:

1. Start the application with the active springdoc configuration.
2. Open `/v3/api-docs` or `/v3/api-docs.yaml`.
3. Find the source operation and the response code carrying the link, such as `POST /api/orders` with response `201`.
4. Inspect the link key, `operationId` or `operationRef`, `parameters`, and `requestBody`.
5. Confirm the target operation exists and parameter names are mapped accurately.
6. Call the source operation and inspect the actual response body/headers.
7. Manually evaluate each runtime expression against the real payload to confirm the value exists.
8. Use Swagger UI or an OpenAPI Link-capable tool to inspect how the link is rendered; do not assume the UI executes it automatically.
9. Run an OpenAPI validator to catch invalid link structures or broken references.
10. Test authorization of the target operation independently of the link.

For instance, if the response schema documents `id` while the actual serializer renames it to `order_id`, the expression `$response.body#/id` will fail to retrieve the right data. Keep Jackson metadata, OpenAPI schemas, and runtime expressions synchronized with the emitted JSON field names.

## 16. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Link does not appear in `/v3/api-docs` | Annotation placed on wrong response or library version handles it differently than expected | Check `@ApiResponse.links` and Swagger Annotations dependency |
| Target operation not found | Wrong or non-unique `operationId` | Set `@Operation(operationId = ...)` explicitly and update links |
| `operationRef` fails to resolve | Wrong URI reference or JSON Pointer path | Escape `/` as `~1` and verify the actual path |
| Target parameter receives null/no value | Runtime expression points to wrong body/header or data does not exist | Cross-check runtime response and JSON Pointer |
| Expression points to wrong nested property | Wrong token used or `~`/`/` not escaped | Verify JSON Pointer against actual JSON structure |
| Link passes full URL into an ID parameter | Confused `$response.header.Location` with a path ID value | Return a separate ID in the body or design the parameter to accept a URI |
| Swagger UI does not auto-call next operation | UI does not support or auto-execute that kind of link | Test with a Link Object-capable tool; do not treat links as server commands |
| Link breaks after changing DTO/Jackson | JSON field name in response changed | Update expressions and schemas together |
| Client gets `403` calling target operation | Links do not grant access permissions | Check authentication/authorization on the target endpoint |

## 17. Design principles

- Use Link Objects to describe relationships between a source response and the next operation.
- Prefer stable, unique, explicitly declared `operationId` values.
- Use `operationRef` when you need to reference an operation directly within the document.
- Use `$response.body#/...` to extract data from the response body and `$response.header.*` for response headers.
- Use `$request.path.*`, `$request.query.*`, `$request.header.*`, or `$request.body#/...` when reusing source request data.
- Ensure target parameter names and value types are mapped compatibly.
- Verify JSON Pointers, especially for nested properties and names containing `~` or `/`.
- Place `@Link` and `@LinkParameter` on the right springdoc response annotation.
- Distinguish OpenAPI Links from HTTP `Link` headers, hypermedia bodies, and Callback Objects.
- Never treat Link Objects as an automatic API-invocation or permission-granting mechanism.
- Verify generated documentation alongside actual responses after changing DTOs, serializers, or `operationId`s.

## Conclusion

The OpenAPI Link Object describes the next operation that can be called from a response, and runtime expressions specify what data to extract from the source request or response. Expressions such as `$response.body#/id`, `$request.path.orderId`, and `$response.header.Location` connect data across operations without repeating rules in external docs. In Spring Boot, `springdoc-openapi` can generate these links from `@Link` and `@LinkParameter`. Keep `operationId`s stable, verify JSON Pointers, and ensure expressions match real payloads; executing the operation and checking permissions remain the responsibility of the client and target endpoint.
