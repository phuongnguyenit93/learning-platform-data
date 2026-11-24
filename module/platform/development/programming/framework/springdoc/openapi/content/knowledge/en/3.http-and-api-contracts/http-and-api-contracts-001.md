# Paths, HTTP Methods, and Identifying an Operation

When describing an API with OpenAPI, each operation is identified by a **path** and an **HTTP method**. For example, `GET /api/v1/products/{productId}` is the operation to read a product, while `DELETE /api/v1/products/{productId}` is the operation to delete that product. Two operations that use the same path but different methods are therefore two separate operations.

In a Spring Boot application, controller mappings determine which Java method a request is routed to. Springdoc-openapi reads those mappings and related metadata to generate `paths` along with the operations in the OpenAPI document. Therefore, understanding the relationship between URLs, HTTP methods, Spring mappings, and `operationId` is the foundation for creating a clear, consistent API contract that can be used for client generation tools or contract testing.

## 1. What is an Operation in OpenAPI?

An **operation** is the description of a specific HTTP action on a path. In an OpenAPI document, each path can contain multiple operations corresponding to the supported HTTP methods.

For example, the same product resource can provide:

| HTTP method and path | Meaning |
|---|---|
| `GET /api/v1/products` | List products |
| `POST /api/v1/products` | Create a product |
| `GET /api/v1/products/{productId}` | Get a product |
| `PUT /api/v1/products/{productId}` | Replace product information |
| `PATCH /api/v1/products/{productId}` | Partially update product information |
| `DELETE /api/v1/products/{productId}` | Delete a product |

Here, `/api/v1/products/{productId}` is a single path. The GET, PUT, PATCH, and DELETE operations on this path are distinct operations. There is no need to create a separate URL for each action if the resource and HTTP semantics are already sufficient to distinguish them.

In OpenAPI, the general structure looks like this:

```yaml
openapi: 3.0.3
info:
  title: Product API
  version: 1.0.0
paths:
  /api/v1/products:
    get:
      summary: List products
    post:
      summary: Create a product
  /api/v1/products/{productId}:
    get:
      summary: Get a product
    put:
      summary: Replace a product
    patch:
      summary: Partially update a product
    delete:
      summary: Delete a product
```

`paths` is where paths are declared. Underneath each path are the operations named by the lowercase HTTP method. Fields such as `summary`, `description`, `parameters`, `requestBody`, `responses`, `tags`, and `operationId` describe each operation in detail.

## 2. Designing Resource Paths

The path is the part that identifies the resource or collection of resources that the client wants to interact with. An easy-to-understand design typically uses nouns to represent resources, uses plurals for collections, and nests child resources according to ownership or hierarchy.

For example:

- `/api/v1/customers` represents the collection of customers.
- `/api/v1/customers/{customerId}` represents a single customer.
- `/api/v1/customers/{customerId}/orders` represents the orders of a customer.
- `/api/v1/orders/{orderId}` represents a single order.

Common actions are expressed using HTTP methods. As a result, `/products/42` does not need to be changed to `/getProduct/42`, `/updateProduct/42`, or `/deleteProduct/42`.

### 2.1. Path Parameters and Query Parameters

A path parameter is part of the path, usually used to identify a resource:

`GET /api/v1/products/42`

A query parameter appears after the `?` character, usually used for filtering, sorting, pagination, or adjusting how the query is executed:

`GET /api/v1/products?category=keyboard&page=0&size=20`

The two types of parameters serve different roles:

| Criterion | Path parameter | Query parameter |
|---|---|---|
| Location | Inside the path | After the ? character |
| Common purpose | Identify a resource or sub-resource | Filter, search, sort, paginate |
| Example | `/products/{productId}` | `/products?category=keyboard` |
| In OpenAPI | `in: path` | `in: query` |

A path parameter needs a clear name and must be declared in the documentation. According to OpenAPI, a parameter with `in: path` is always required, so `required` must be `true`. A query parameter can be required or optional depending on the contract.

Declaration example:

```yaml
paths:
  /api/v1/products/{productId}:
    get:
      operationId: getProductById
      parameters:
        - name: productId
          in: path
          required: true
          description: Product identifier
          schema:
            type: integer
            format: int64
        - name: includeDetails
          in: query
          required: false
          description: Whether to include additional details
          schema:
            type: boolean
            default: false
      responses:
        '200':
          description: Product retrieved successfully
```

The placeholder name in the path must match the path parameter name. For instance, if the path uses `{productId}`, the operation must have a `productId` parameter with `in: path`. You should not declare the path as `{productId}` while naming the parameter `id`.

### 2.2. Path Naming Rules

Several principles help keep paths stable and readable:

1. Use nouns to represent resources; use HTTP methods to represent standard operations.
2. Use a consistent convention for lowercase letters, hyphens, and resource names.
3. Give placeholders meaningful names, such as `{orderId}` instead of `{x}`.
4. Use query parameters for filters and pagination instead of creating separate paths for each combination of values.
5. Avoid creating multiple paths that differ only by a trailing slash or letter casing.
6. Choose a consistent way to represent the API version. If you use the version in the path, such as `/api/v1/products`, keep that convention across the entire API.

Paths in URLs are case-sensitive according to URI rules. Trailing slash handling also depends on framework configuration and version. Therefore, you should publish a canonical URL format and use that exact format across controllers, documentation, clients, and tests.

### 2.3. Path Templates Must Be Clear and Unambiguous

OpenAPI allows using expressions inside curly braces to represent variable parts of a path, such as `/users/{userId}`. The two templates `/users/{userId}` and `/users/{name}` have the same path structure; renaming the placeholder does not create two different paths. Do not declare them as two separate paths to distinguish two resources.

If both a concrete path and a templated path match, the concrete path takes precedence according to OpenAPI rules. For example, `/users/me` is more specific than `/users/{userId}`. When designing Spring routes, you should also check the order and mapping conditions to avoid competing or confusing routes.

## 3. Semantics of HTTP Methods

The HTTP method expresses the client's intent toward the resource. Choosing the right method helps readers understand the contract and helps proxies/caches and testing tools apply the proper HTTP semantics.

| Method | Common purpose | Safe | Idempotent |
|---|---|---:|---:|
| `GET` | Read a resource or collection | Yes | Yes |
| `HEAD` | Retrieve metadata similar to GET without a response body | Yes | Yes |
| `POST` | Create a resource in a collection or perform processing | No | Not by default |
| `PUT` | Create or replace resource state at a known URI | No | Yes |
| `PATCH` | Apply partial changes to a resource | No | Not by default |
| `DELETE` | Delete a resource | No | Yes |
| `OPTIONS` | Query supported communication options | Yes | Yes |
| `TRACE` | Diagnose the request path through proxies | Yes | Yes |

**Safe** means the operation is defined as read-only and does not ask the server to alter resource state. **Idempotent** means sending the same request multiple times has the same intended effect on server state as sending it once. Idempotent does not mean every call must return the exact same response: for example, the first DELETE may return 204 while a subsequent call may return 404, yet the final state is still that the resource has been deleted.

### 3.1. GET and HEAD: Reading Data

GET is used to retrieve a representation of a resource. Filtering, sorting, and pagination parameters are usually passed via the query string:

`GET /api/v1/products?category=keyboard&size=20`

GET should not carry the intent to change business state. Avoid designing endpoints where GET creates orders, deducts money, or modifies data. A GET request body has no broadly defined general semantics and may not be supported by some intermediaries; use query parameters or a different request design when you need to pass complex search criteria.

HEAD is similar to GET except that the server does not send a response body. It is useful when the client only needs to check metadata such as headers or resource existence. If the framework automatically supports HEAD through GET, check the actual mapping and generated documentation to ensure the published behavior matches.

### 3.2. POST: Creating or Processing

POST is commonly used to create a new item in a collection:

`POST /api/v1/products`

The request body can contain the data to create:

```json
{
  "name": "Mechanical keyboard",
  "price": 1250000
}
```

If creation succeeds, the API typically returns `201 Created`; the response may include the representation of the new resource or a `Location` header pointing to the resource's URI. POST can also be used for processing operations that do not fit the semantics of GET, PUT, or PATCH.

POST is not idempotent by default. If a client retries a request due to a timeout, the server may create another resource. For business flows that must prevent duplicate creation, you can design an idempotency key mechanism or an appropriate confirmation workflow.

### 3.3. PUT: Replacing Resource State

PUT typically updates or replaces the representation of a resource at a known URI:

`PUT /api/v1/products/42`

The request represents the state that the client wants to set for the resource according to the API contract. PUT has idempotent semantics: resending the same request multiple times does not change the intended state outcome after the first time. You should clearly define whether the API requires the full representation or supports optional fields, so clients do not accidentally lose data by omitting fields.

### 3.4. PATCH: Partial Update

PATCH is used to apply a set of changes to a resource:

`PATCH /api/v1/products/42`

The request payload depends on the patch format the API publishes, such as JSON Merge Patch or JSON Patch, or a dedicated, clearly documented update DTO. You should not assume PATCH always shares the same structure as the creation DTO.

PATCH is not idempotent by default. A patch that sets `price` to a fixed value can be idempotent, whereas an operation that increases the price by 10% on each submission is not idempotent. Define the behavior according to the specific format and business rules.

### 3.5. DELETE: Deleting a Resource

DELETE is used to request deleting the resource at a URI:

`DELETE /api/v1/products/42`

The API typically returns `204 No Content` if deletion succeeds without needing a body, or `200 OK` if it returns a descriptive result. DELETE has idempotent semantics regarding the intended effect, even if responses between calls may differ. Avoid requiring a request body for DELETE because body semantics are not universally defined and intermediary support varies.

### 3.6. OPTIONS and TRACE

OPTIONS allows the client to query supported communication options. It also plays a role in browser CORS preflight flows. TRACE serves to diagnose the request path and is usually disabled in public applications unless there is a clear need.

An OpenAPI Path Item defines operations for GET, PUT, POST, DELETE, OPTIONS, HEAD, PATCH, and TRACE. Not every API needs to expose every method. Only document the operations that the application actually supports and intentionally provides to clients.

## 4. From Spring MVC Mappings to OpenAPI Paths and Operations

In Spring MVC, mappings are usually built from two levels:

- Class-level mapping defines the common prefix or scope of the controller.
- Method-level mapping defines the remaining path, HTTP method, and request acceptance conditions.

Annotations such as `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, and `@DeleteMapping` are shorthand forms of `@RequestMapping` with the corresponding method.

Example:

```java
@RestController
@RequestMapping("/api/v1/products")
@Tag(name = "Products", description = "Product management API")
public class ProductController {

    @GetMapping("/{productId}")
    @Operation(
        operationId = "getProductById",
        summary = "Get product information"
    )
    public ProductResponse getById(
        @PathVariable("productId") Long productId
    ) {
        // Call service to retrieve the product.
        return productService.getById(productId);
    }

    @GetMapping
    @Operation(
        operationId = "listProducts",
        summary = "List products"
    )
    public List<ProductResponse> list(
        @RequestParam(required = false) String category
    ) {
        return productService.findAll(category);
    }

    @PostMapping
    @Operation(
        operationId = "createProduct",
        summary = "Create a product"
    )
    public ProductResponse create(
        @RequestBody CreateProductRequest request
    ) {
        return productService.create(request);
    }
}
```

In the example, the prefix `/api/v1/products` from the class is combined with `/{productId}` on the method, forming the path `/api/v1/products/{productId}`. Method `getById` creates a GET operation. Method `list` creates a GET operation on the collection `/api/v1/products`, while `create` creates a POST operation on the same collection path.

Springdoc collects Spring mappings and OpenAPI metadata to place the operations into the document. The `@Operation` annotation can add `summary`, `description`, `operationId`, `tags`, `deprecated`, and many other descriptive attributes. Annotations `@Parameter`, `@RequestBody`, `@ApiResponse`, and `@Schema` help describe parts of the contract in greater detail.

### 4.1. Additional Mapping Conditions

Spring's `@RequestMapping` can restrict requests using several conditions in addition to path and method:

- `params`: requires a query parameter to be present or have a specific value.
- `headers`: requires an HTTP header to be present or match a value.
- `consumes`: restricts the request's Content-Type.
- `produces`: restricts the response media types that can be produced.

Example:

```java
@PostMapping(
    path = "/imports",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ImportResult importFile(
    @RequestPart("file") MultipartFile file
) {
    return importService.process(file);
}
```

The `consumes` and `produces` conditions directly relate to the media types of the request body and response, so they need to be reflected in OpenAPI's `requestBody.content` or `responses.content`. Springdoc can infer much of this information from parameter types, return types, and annotations, yet business descriptions still need to be reviewed.

An important limitation of OpenAPI is that each **path + HTTP method** pair can only have a single operation. Spring can distinguish multiple handlers sharing the same path and method using `params` or `headers` conditions, but OpenAPI cannot create two independent operations with the same path and method pair. When encountering this situation, consider merging the variants into one operation and documenting the corresponding parameters/responses, or designing separate paths so the contract is unambiguous. Do not rely on `operationId` to distinguish two routes that share the same path + method pair.

### 4.2. Separating Path Parameters from Query Parameters in Controllers

The controller example below clearly demonstrates both types of parameters:

```java
@GetMapping("/{productId}")
public ProductResponse getById(
    @PathVariable("productId") Long productId,
    @RequestParam(defaultValue = "false") boolean includeDetails
) {
    return productService.getById(productId, includeDetails);
}
```

`@PathVariable` binds to the placeholder in the path. `@RequestParam` receives values from the query string. Springdoc can usually recognize the parameter location from Spring annotations; `@Parameter` can be used to add a name, description, example, or schema constraints when needed.

You should explicitly specify the name in `@PathVariable("productId")` if you want the mapping to be explicit and avoid depending on whether the compiler preserves parameter names. The name in OpenAPI must match the path placeholder.

## 5. Identifying an Operation with operationId

In OpenAPI, `operationId` is an optional string used to identify an operation. If provided, this value must be unique across the entire OpenAPI document. It is commonly used by client SDK generation tools as the basis for method naming.

Example:

```yaml
paths:
  /api/v1/products/{productId}:
    get:
      operationId: getProductById
      summary: Get product information
    delete:
      operationId: deleteProduct
      summary: Delete a product
```

Two operations sharing the same path with different methods need different `operationId` values if both are declared. Operations on different paths also must not reuse the same `operationId`.

### 5.1. Naming Conventions for operationId

A practical convention is to use camelCase function names expressing the action and resource:

| Operation | Suggested operationId |
|---|---|
| GET `/products` | `listProducts` |
| GET `/products/{productId}` | `getProductById` |
| POST `/products` | `createProduct` |
| PUT `/products/{productId}` | `replaceProduct` |
| PATCH `/products/{productId}` | `updateProduct` |
| DELETE `/products/{productId}` | `deleteProduct` |

Choose meaningful, stable names that do not depend on controller class names. Some guidelines:

1. Use a uniform naming convention across the entire API.
2. Ensure every operationId is unique within a document, even across different tags or path groups.
3. Avoid overly generic names such as `get`, `save`, or `process`.
4. Do not treat operationId as a URL or route name; changing operationId does not change the HTTP endpoint.
5. Avoid changing operationId arbitrarily after publishing auto-generated SDKs, because clients may depend on the generated method names.

### 5.2. Declaring operationId with Springdoc

It can be declared directly using `@Operation`:

```java
@GetMapping("/{productId}")
@Operation(
    operationId = "getProductById",
    summary = "Get product information",
    description = "Find a product by its identifier."
)
public ProductResponse getById(
    @PathVariable("productId") Long productId
) {
    return productService.getById(productId);
}
```

If not explicitly declared, Springdoc may generate an operationId based on method information depending on the configuration and library version. For public APIs or documents used to generate SDKs, explicit declaration gives better control over stable names. After generating the document, verify there are no duplicate operationIds.

## 6. OpenAPI Document Example for a Group of Operations

The following example combines a collection path, a path item with shared parameters, and multiple HTTP methods:

```yaml
openapi: 3.0.3
info:
  title: Product API
  version: 1.0.0
paths:
  /api/v1/products:
    get:
      operationId: listProducts
      tags:
        - Products
      summary: List products
      parameters:
        - name: category
          in: query
          required: false
          schema:
            type: string
        - name: page
          in: query
          required: false
          schema:
            type: integer
            minimum: 0
            default: 0
      responses:
        '200':
          description: List of products
    post:
      operationId: createProduct
      tags:
        - Products
      summary: Create a product
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        '201':
          description: Product created
        '400':
          description: Invalid data
  /api/v1/products/{productId}:
    parameters:
      - name: productId
        in: path
        required: true
        description: Product identifier
        schema:
          type: integer
          format: int64
    get:
      operationId: getProductById
      tags:
        - Products
      summary: Get product information
      responses:
        '200':
          description: Product found
        '404':
          description: Product not found
    put:
      operationId: replaceProduct
      tags:
        - Products
      summary: Replace product information
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ReplaceProductRequest'
      responses:
        '200':
          description: Product updated
        '404':
          description: Product not found
    delete:
      operationId: deleteProduct
      tags:
        - Products
      summary: Delete a product
      responses:
        '204':
          description: Product deleted
        '404':
          description: Product not found
components:
  schemas:
    CreateProductRequest:
      type: object
      required:
        - name
      properties:
        name:
          type: string
        price:
          type: number
          format: double
    ReplaceProductRequest:
      type: object
      required:
        - name
        - price
      properties:
        name:
          type: string
        price:
          type: number
          format: double
```

In this example, the `productId` parameter is declared at the Path Item level, so it applies to all operations on that path. If an operation needs an additional specific parameter, declare it inside the operation. If a parameter with the same name and same `in` location is declared at both levels, the operation-level parameter can override the path-level parameter according to OpenAPI rules.

Note: the example focuses on path and operation structure, so responses do not yet declare detailed schemas. In an actual document, add `content` and a `$ref` to the response schema so clients know the exact structure of the returned data.

## 7. Common Design and Description Mistakes

| Issue | Consequence | Resolution |
|---|---|---|
| Using GET to mutate data | Caches, crawlers, or clients may accidentally trigger write actions | Choose POST, PUT, PATCH, or DELETE according to semantics |
| Putting verbs in every URL | Long routes that duplicate the meaning of HTTP methods | Use resource nouns and HTTP methods |
| Placeholder does not match parameter | Invalid OpenAPI document or difficult client generation | Synchronize `{productId}` with the `productId` parameter |
| Path parameter lacks `required: true` | Violates path parameter specification requirements | Set `required: true` |
| Two paths differ only by placeholder name | Document has structurally duplicate path templates | Merge into one path and standardize the variable name |
| Two Spring handlers share path and method, differing only by params/headers | OpenAPI has no two separate operations to represent them | Merge into one operation or design separate paths |
| Duplicate operationId | Client generators may error or produce conflicting method names | Set unique operationIds across the entire document |
| Changing operationId after SDK release | Generated client code may change method names | Manage operationId as part of the public contract |
| Paths differing only by trailing / | Clients may call inconsistently; mapping depends on configuration | Publish a single canonical path form |
| Documenting an unimplemented method | Clients calling the operation receive 404/405 or other errors | Reconcile the documentation with actual mappings |

## 8. Distinguishing Path Errors from Method Errors When Calling an API

When a request does not reach the expected handler, check both the path and the HTTP method. Certain HTTP statuses often help narrow down the cause:

- **404 Not Found:** no resource or route matches the path according to how the application handles it. Check whether the application intentionally returns 404 when a resource is not found.
- **405 Method Not Allowed:** the path was recognized, but the submitted HTTP method is not supported for that resource. The response often includes an `Allow` header listing the permitted methods.
- **400 Bad Request:** the request may have matched the route, but parameters or content are invalid, for example failing to convert `productId` to a numeric type.
- **406 Not Acceptable:** the server cannot produce a response matching the media type requested by the client via `Accept`.
- **415 Unsupported Media Type:** the request's `Content-Type` does not match the content accepted by the endpoint.

Not every application maps errors identically; exception handlers, gateways, and security configurations can change the observed response. Check Spring logs, registered mappings, and the OpenAPI document instead of relying solely on status codes.

You can test routes using curl:

```bash
# Read a single product
curl -i -X GET http://localhost:8080/api/v1/products/42

# Send POST to create a product
curl -i -X POST http://localhost:8080/api/v1/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Mechanical keyboard","price":1250000}'

# Send a method not supported by the route to observe the response
curl -i -X PATCH http://localhost:8080/api/v1/products/42
```

The final PATCH request is only meaningful as a test if the actual endpoint does not declare PATCH or requires a body. In real systems, use test data and an appropriate environment.

## 9. Workflow to Reconcile Spring Mappings with the OpenAPI Document

After adding or modifying a controller, check the contract following these steps:

1. **Determine the full path:** combine the class-level mapping with the method-level mapping and verify placeholders.
2. **Identify the method:** clearly note whether the endpoint supports GET, POST, PUT, PATCH, DELETE, or another method.
3. **Classify parameters:** determine whether each parameter resides in path, query, header, or cookie; verify names and requiredness.
4. **Inspect the request body:** determine whether the method accepts a body, which schema, and which media types are supported.
5. **Inspect responses:** document status codes, response bodies, schemas, and meaningful headers.
6. **Set operationId:** ensure uniqueness, clarity, and stability.
7. **Inspect the generated document:** open springdoc's JSON/YAML endpoint, locate the path, and verify each operation.
8. **Test requests:** use Swagger UI or curl to confirm URL, method, parameters, and request payload match application behavior.

For applications using springdoc, the default endpoints are typically `/v3/api-docs` for JSON and `/v3/api-docs.yaml` for YAML. If the project customizes `springdoc.api-docs.path`, use the configured path. Swagger UI makes it easy to inspect operations by tag, yet the raw JSON/YAML document still needs direct inspection when used as input for other tools.

When integrating documentation into CI, you can add automated checks to detect duplicate operationIds, missing path parameters, unexpected method changes, or contract drift. Comparing specifications across versions also helps detect changes that could impact existing clients.

## 10. Key Takeaways

- An operation in OpenAPI is identified by the **path + HTTP method** pair.
- Multiple methods can coexist on one path; each method describes a separate action.
- Path parameters identify resource parts in the URL; query parameters are typically used for filtering, sorting, and pagination.
- GET and HEAD are for read operations; POST usually creates or processes; PUT replaces; PATCH partially updates; DELETE deletes.
- Spring combines class-level and method-level mappings to route requests; Springdoc uses mappings and metadata to generate operations.
- `operationId` is an optional identifier that must be unique within the document if declared; it does not alter the URL.
- The OpenAPI document must accurately reflect the routes, methods, parameters, and actual behavior of the controller.

When designing endpoints for Spring Boot, start from the resource and HTTP contract, then declare the corresponding mappings and OpenAPI metadata. This approach keeps the documentation generated by springdoc readable, stable for clients, and convenient to test throughout the API lifecycle.
