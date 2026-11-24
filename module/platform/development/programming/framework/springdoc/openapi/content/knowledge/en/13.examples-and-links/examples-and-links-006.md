# Link Object Describing Relationships Between Operations

An API often has multiple operations connected in a business workflow. The client creates an order first, then fetches the order details using the ID it just received; starts a background job and then queries its status; or reads a resource and then sends an update request based on the retrieved data. The OpenAPI Link Object lets the documentation describe these relationships directly inside the source operation's response.

The Link Object helps readers and tools understand that the result of one operation can supply data needed to invoke another operation. For example, the `201 Created` response of `POST /orders` returns `id`; a link can map that value to the `orderId` path parameter of `GET /orders/{orderId}`.

The Link Object is metadata in the OpenAPI contract. It does not create endpoints on its own, does not automatically send requests, does not make the server add links into JSON or an HTTP `Link` header, and does not replace the application's hypermedia navigation mechanism. The target operation must still exist and be protected under its own runtime policies.

## 1. What problem does the Link Object solve?

When reading only the `paths` list, integrators see each operation in isolation and may not immediately know how to pass the result from one operation into the next request. The Link Object describes the relationship between a source operation's response and a target operation.

Example of an order flow:

1. The client calls `POST /api/orders` to create an order.
2. The server returns `201 Created` with a body containing the order `id`.
3. The documentation attaches a link named `GetCreatedOrder` to the `201` response.
4. The link references operation `getOrderById` and maps `orderId` using the expression `$response.body#/id`.
5. Tools reading OpenAPI can understand that the client uses the `id` value from the response to call `GET /api/orders/{orderId}`.

Flow diagram:

```mermaid
flowchart LR
    A[POST /api/orders] --> B[201 Created]
    B --> C[Response body: id = 42]
    C --> D[Link: GetCreatedOrder]
    D --> E[operationId: getOrderById]
    E --> F[GET /api/orders/42]
    F --> G[200 OrderResponse]
```

A link describes a navigable relationship starting from a response. It is especially useful for APIs with multi-step workflows, asynchronous operations, sub-resources, or pagination.

## 2. Structure of the Link Object

An OpenAPI Link Object has the following main fields:

| Field | Meaning |
|---|---|
| `operationId` | Unique identifier name of the target operation in the OpenAPI document |
| `operationRef` | URI reference pointing directly to the target operation |
| `parameters` | Maps parameter names of the target operation to fixed values or runtime expressions |
| `requestBody` | Request body value for the target operation; can be a literal or runtime expression |
| `description` | Explains the relationship or purpose of the link |
| `server` | Server used to call the target operation if overriding a server declared elsewhere |

A Link Object must identify the target operation using either `operationId` or `operationRef`. These two fields are alternative ways to reference the target; do not declare both on the same link.

`operationId` must be unique within the OpenAPI document. It is usually the more readable and convenient option when operations live in the same document. `operationRef` is useful when you want to point via JSON Pointer to a specific operation or when referencing another document.

`parameters` is an object map: keys are parameter names on the target operation, and values are the values passed into those parameters. Values can be literals or runtime expressions. `requestBody` works similarly, but for the target operation's body.

## 3. Complete OpenAPI example: create an order then fetch details

The document below declares two operations and a link from the `201` response of the create-order operation to the get-order-by-ID operation.

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: 1.0.0
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
          description: Order created.
          headers:
            Location:
              description: URI of the newly created order.
              schema:
                type: string
                format: uri-reference
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
          links:
            GetCreatedOrder:
              operationId: getOrderById
              description: Fetch details of the newly created order.
              parameters:
                orderId: '$response.body#/id'
  /api/orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Get order by ID
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Order details.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Order not found.
components:
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - productId
        - quantity
      properties:
        productId:
          type: integer
          format: int64
        quantity:
          type: integer
          minimum: 1
    OrderResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
        status:
          type: string
```

In response `201`, the Link Object `GetCreatedOrder` references `getOrderById`. The value of the `orderId` path parameter in the target operation is taken from the `id` property of the source response body.

If the server returns:

```json
{
  "id": 42,
  "status": "CREATED"
}
```

the runtime expression `$response.body#/id` evaluates to `42`. Tools capable of processing OpenAPI Links can use this value to populate the path parameter and help integrators understand the next request.

## 4. `operationId` and `operationRef`

### Using `operationId`

This is usually the most readable approach:

```yaml
links:
  GetCreatedOrder:
    operationId: getOrderById
    parameters:
      orderId: '$response.body#/id'
```

The target operation must have the same `operationId`:

```yaml
/api/orders/{orderId}:
  get:
    operationId: getOrderById
```

Declare `operationId` explicitly and keep it stable. Do not rely on Java method names if the `operationId` generation rule might change across refactors or Springdoc configuration. Whenever `operationId` changes, every Link Object referencing the old name must also be updated.

### Using `operationRef`

You can point directly to an operation using a URI reference and JSON Pointer:

```yaml
links:
  GetCreatedOrder:
    operationRef: '#/paths/~1api~1orders~1{orderId}/get'
    parameters:
      orderId: '$response.body#/id'
```

In JSON Pointer, `/` characters inside a path key are escaped as `~1`. Therefore, the path `/api/orders/{orderId}` is represented in the pointer as `~1api~1orders~1{orderId}`. For external documents, `operationRef` can use a URI reference pointing to the corresponding document and operation.

Choose only one of the two referencing approaches per Link Object. Use `operationId` when you want readable links and operations have stable identifiers; use `operationRef` when you need to specify the operation location via URI/JSON Pointer.

## 5. Runtime expressions extracting data from requests and responses

Runtime expressions let you pass data from the current HTTP request or response into the target operation. Expressions are evaluated when an actual request/response occurs, not when Springdoc generates the documentation.

Commonly used expressions:

| Expression | Extracted value |
|---|---|
| `$url` | Current request URL |
| `$method` | HTTP method of the current request |
| `$statusCode` | Status code of the current response |
| `$request.path.orderId` | Path parameter `orderId` in the source request |
| `$request.query.page` | Query parameter `page` in the source request |
| `$request.header.X-Request-Id` | `X-Request-Id` header of the source request |
| `$request.body#/customer/id` | Value of `customer.id` in the source request body |
| `$response.header.Location` | `Location` header of the source response |
| `$response.body#/id` | Property `id` in the source response body |

For JSON bodies, the part after `#` uses JSON Pointer. For instance, `$response.body#/customer/id` accesses the `id` property inside the `customer` object. If a property name contains `/` or `~`, escape them per JSON Pointer: `/` becomes `~1`, and `~` becomes `~0`.

### Extracting a value from a response header

If a resource-creation operation returns a `Location` header, a link can use that header for a parameter of the target operation:

```yaml
links:
  FollowLocation:
    operationId: getOrderById
    parameters:
      orderId: '$response.header.Location'
```

The expression above returns the entire value of the `Location` header. It only fits directly if the target parameter's type and semantics match that URI. If the target operation expects a numeric ID while `Location` is a full URI, choose a cleaner design: extract the ID on the client or return a dedicated ID in the response body and reference `$response.body#/id`.

### Assigning a request body for the target operation

The `requestBody` field can take a literal or a runtime expression:

```yaml
links:
  SubmitPayment:
    operationId: createPayment
    requestBody: '$response.body#/paymentRequest'
```

In this example, the `paymentRequest` object from the source response is used as the request body for the `createPayment` operation. The data type of that value must match the target operation's request body schema.

## 6. Mapping parameters with the right names and types

Keys in `parameters` must match the parameter names declared on the target operation. For example, if the target operation has a path parameter `orderId`, the link must use the key `orderId`, not the source property name or Java field name.

```yaml
parameters:
  orderId: '$response.body#/id'
  expand: details
```

Here:

- `orderId` pulls its dynamic value from the response body.
- `expand` passes the literal value `details`.

The resulting value must fit the target parameter's data type and rules. If the target parameter is an integer while the expression extracts a URI string, the document may be syntactically valid yet the relationship makes no sense at execution time. Validators do not always check the runtime type of every expression; verify via tests or contract review.

Required path parameters of the target operation must be given values to form a valid request. If the target operation also has optional query/header parameters, the link may map them when values are available or let the client supply them.

## 7. Reusing Link Objects via `components.links`

When multiple responses share the same relationship, you can declare the Link Object once under `components.links` and reference it with `$ref`.

```yaml
components:
  links:
    OrderById:
      operationId: getOrderById
      description: Fetch order by the returned ID.
      parameters:
        orderId: '$response.body#/id'
```

Then use it inside a response:

```yaml
paths:
  /api/orders:
    post:
      operationId: createOrder
      responses:
        '201':
          description: Order created.
          links:
            GetCreatedOrder:
              $ref: '#/components/links/OrderById'
```

`components.links` only stores reusable definitions. It does not automatically attach links to every response. To use one, reference the Link Object under `responses.<status>.links` of the source operation.

`OrderById` is the component name; `GetCreatedOrder` is the relationship name in the response's `links` map. You may pick other names as long as they are clear and consistent.

## 8. Declaring Link Objects with Springdoc annotations

Springdoc supports Swagger annotations for describing response links. You can set `operationId` on the target operation and declare the link directly in `@ApiResponse` on the source operation.

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.links.Link;
import io.swagger.v3.oas.annotations.links.LinkParameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    @Operation(operationId = "createOrder", summary = "Create order")
    @ApiResponses({
        @ApiResponse(
            responseCode = "201",
            description = "Order created.",
            links = @Link(
                name = "GetCreatedOrder",
                operationId = "getOrderById",
                description = "Fetch details of the newly created order.",
                parameters = @LinkParameter(
                    name = "orderId",
                    expression = "$response.body#/id"
                )
            )
        )
    })
    ResponseEntity<OrderResponse> create(@RequestBody CreateOrderRequest request) {
        OrderResponse created = orderService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @GetMapping("/{orderId}")
    @Operation(operationId = "getOrderById", summary = "Get order by ID")
    OrderResponse getById(@PathVariable Long orderId) {
        return orderService.getById(orderId);
    }
}
```

In the example:

- `@Operation(operationId = "getOrderById")` assigns an explicit identifier to the target operation.
- `@ApiResponse(links = @Link(...))` attaches the link to the `201` response of the order creation operation.
- `@LinkParameter` maps the target operation's `orderId` parameter from `id` in the response body.
- The `OrderResponse` type and actual payload must have the corresponding `id` property.

Annotation names and attributes should be checked against the version of Swagger annotations pulled in by the Springdoc starter. If the project uses another library version, check the Javadoc of the corresponding artifact and verify `/v3/api-docs` JSON after running the application.

### Using `operationRef` in annotations

When not using `operationId`, you can reference directly via `operationRef`:

```java
@Link(
    name = "GetCreatedOrder",
    operationRef = "#/paths/~1api~1orders~1{orderId}/get",
    parameters = @LinkParameter(
        name = "orderId",
        expression = "$response.body#/id"
    )
)
```

Do not also declare `operationId` inside the same Link Object. The path inside `operationRef` must point to the exact operation generated in the document.

## 9. Link Object is not an HTTP Link header or HATEOAS body

The following three concepts are easy to confuse:

| Concept | Where does it live? | Role |
|---|---|---|
| OpenAPI Link Object | In the OpenAPI document, at `responses.<status>.links` | Describes relationships between source and target operations for tooling |
| HTTP `Link` header | In the HTTP response headers | Server actually sends one or more URI relations in the response |
| Hypermedia links in JSON | In the response body, in a format like HAL or a custom model | Server returns runtime links for the client to navigate based on received data |

Declaring an OpenAPI Link Object does not cause the response to automatically include a `Link` header or `_links`/`links` fields. If the API uses Spring HATEOAS and wants to send real hypermedia links, implement the corresponding representation in the response body. If you want to send an HTTP `Link` header, the controller must produce that header. The OpenAPI Link Object can document supplementary operation relationships, but it does not replace those runtime mechanisms.

## 10. Link Object does not replace authentication and authorization

A link only describes how parameters or a body can be passed to the target operation. It does not transfer access permissions from the source operation to the target operation, nor does it issue tokens.

For instance, `POST /orders` may allow a user to create an order, while `GET /orders/{orderId}` must still verify whether the user has permission to read that order. The target operation may have its own `security` requirements, roles, or scopes.

When designing links:

- Never embed access tokens or API keys in runtime expressions, literal parameters, or sample request bodies.
- Do not assume a caller of the source operation is authorized to call every target operation.
- Document `401`/`403` errors on the target operation where appropriate.
- Enforce resource ownership checks on the server, even when the ID comes directly from an earlier response.

## 11. Practical scenarios for using Link Objects

| Business flow | Source operation | Target operation | Value typically passed |
|---|---|---|---|
| Create then view details | `POST /orders` | `GET /orders/{orderId}` | `$response.body#/id` |
| Submit background job then poll | `POST /exports` | `GET /exports/{jobId}` | `$response.body#/jobId` |
| Create order then pay | `POST /orders` | `POST /orders/{orderId}/payments` | `orderId` from response and an appropriate payment body |
| Read resource then update | `GET /profiles/{id}` | `PATCH /profiles/{id}` | ID from `$request.path.id` or `$response.body#/id` |
| Fetch next page | `GET /items` | `GET /items` | Cursor/next token value if provided by the response |

Link Objects are useful when relationships between operations are a significant part of the contract and can be expressed through parameters or a request body. If you only need to explain a workflow in prose, `description` or guide documentation may suffice; there is no need to create links for every pair of operations.

## 12. Server of the target operation

A Link Object can declare `server` when the target operation needs to use a different server from the one declared on the operation or document. For example, an API may create resources on its main endpoint while providing file download URLs on a dedicated storage server.

```yaml
links:
  DownloadExport:
    operationId: downloadExport
    parameters:
      exportId: '$response.body#/id'
    server:
      url: https://downloads.example.com
      description: File export download server.
```

This server applies only when invoking the target operation via the link. The URL must be a valid server for that operation and should not contain credentials or secrets. If `server` is omitted from the Link Object, the target operation uses the server determined by the document and its operation.

## 13. Verifying Link Objects in Springdoc-generated documentation

After running the application, open `/v3/api-docs` and inspect the source response. For example:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/orders"].post.responses["201"].links'
```

Expected output contains the link with `operationId` and parameter expression:

```json
{
  "GetCreatedOrder": {
    "operationId": "getOrderById",
    "description": "Fetch details of the newly created order.",
    "parameters": {
      "orderId": "$response.body#/id"
    }
  }
}
```

Next, verify that the target operation exists:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/orders/{orderId}"].get.operationId'
```

The result must be `getOrderById`. Also check:

- Parameter names in the link match the target operation exactly.
- Runtime expressions point to real properties or headers on the source request/response.
- Passed data types fit the target parameter or request body.
- `operationRef` points to the right JSON Pointer if using that reference style.
- The link sits under the right response status code.
- Other response statuses do not inadvertently inherit the same link when the relationship does not apply.

## 14. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Link does not appear in `/v3/api-docs` | Annotation placed on wrong response or library version handles config differently than expected | Check `@ApiResponse.links`, imports, and Swagger annotations version |
| `operationId` not found | Typo or `operationId` changed | Declare `operationId` explicitly and check uniqueness |
| Invalid `operationRef` | JSON Pointer path improperly encoded or wrong HTTP method | Escape `/` as `~1` and verify the pointer |
| Link misses a path parameter | Missing key in `parameters` or mismatched name | Cross-check against target operation parameter names |
| Expression evaluates to null or missing | Property/header does not exist in source request/response | Inspect actual payload and JSON Pointer |
| Expression value has wrong type | Source and target parameter are incompatible | Pick the right property or redesign the parameter |
| Swagger UI does not render link actions | Tool does not support or only partially supports Link Objects | Inspect OpenAPI directly; do not rely solely on UI |
| Assumed declaring a link creates HTTP `Link` headers | Confused OpenAPI metadata with runtime responses | Implement the header or hypermedia body yourself if the API requires it |
| Link points to target operation but returns 403 | Target operation has its own security policy | Verify tokens, roles, scopes, and resource permissions |

## 15. Link Object design checklist

- [ ] A genuine business relationship between the source and target operations has been identified.
- [ ] The link is attached to the right response status on the source operation.
- [ ] Either `operationId` or `operationRef` has been chosen, not both.
- [ ] `operationId` is unique and stable if used.
- [ ] `operationRef` is a valid URI reference/JSON Pointer if used.
- [ ] Parameter names in `parameters` match the target operation.
- [ ] Runtime expressions point to real data in the source request/response.
- [ ] Passed values fit the target parameter or request body types.
- [ ] `components.links` is referenced properly if using reusable definitions.
- [ ] `server` is declared only when the target operation requires a different server.
- [ ] OpenAPI Link Objects are not confused with HTTP `Link` headers or HATEOAS bodies.
- [ ] The target operation still has independent authentication, authorization, and tests.
- [ ] `/v3/api-docs` has been inspected and the link verified after Springdoc generates the docs.

The Link Object helps describe how operations connect in a workflow, such as taking an ID from an order-creation response to invoke the order-details operation. `operationId` or `operationRef` identifies the target; `parameters` and `requestBody` pass data via literals or runtime expressions. When links are placed on the right responses and target operations are verified, OpenAPI documentation becomes far more useful for integrators and tools consuming the API contract.

## References

- [OpenAPI Specification – Link Object](https://spec.openapis.org/oas/v3.1.1.html#link-object)
- [OpenAPI Specification – Runtime Expressions](https://spec.openapis.org/oas/v3.1.1.html#runtime-expressions)
- [OpenAPI Specification – Response Object](https://spec.openapis.org/oas/v3.1.1.html#response-object)
- [Swagger Annotations – `@Link`](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/links/Link.html)
- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
