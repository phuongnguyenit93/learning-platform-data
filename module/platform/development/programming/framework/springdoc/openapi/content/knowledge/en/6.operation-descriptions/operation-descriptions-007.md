# Describing Multiple HTTP Methods or Multiple Mappings on One Handler

In Spring Boot, a single handler method can be bound to multiple HTTP methods or multiple paths using `@RequestMapping`. This declaration style is useful when maintaining backward-compatible endpoints, providing multiple URL aliases, or sharing one implementation for requests with the same meaning. When generating OpenAPI, remember that an operation is identified by the pair of **path and HTTP method**. Therefore, one Spring handler can correspond to multiple operations in the document.

springdoc-openapi reads Spring's mappings and converts them into OpenAPI's `paths` structure. Each path can contain operations such as `get`, `post`, `put`, `delete`, `patch`, `head`, `options`, or `trace`. If a handler is mapped to multiple path/method pairs, the documentation must represent each pair clearly so clients know which requests are supported.

## 1. Distinguishing Handler Method, Mapping, and OpenAPI Operation

These three concepts are related but not identical:

| Concept | Meaning | Example |
| --- | --- | --- |
| Handler method | Java method that handles requests in a controller | `searchOrders(...)` |
| Spring request mapping | Set of conditions for Spring to select a handler: path, HTTP method, params, headers, consumes, produces | `/api/orders/search`, `GET` or `POST` |
| OpenAPI operation | Describes a specific HTTP action at a path | `GET /api/orders/search` |

In OpenAPI, a Path Item can contain at most one operation per HTTP method. For example, the same path `/api/orders` can have `get` to list orders, `post` to create an order, and `delete` to remove a resource if the API design allows it. Two operations might invoke the same Spring handler in special cases, yet remain two distinct operations in the contract.

A handler can also be registered at multiple paths. In that case, each path must appear as a Path Item in OpenAPI. For instance, `/api/orders/{id}` and `/legacy/orders/{id}` may be handled by one Java method, while clients see two separate URLs.

## 2. One Handler Serving Multiple HTTP Methods

`@RequestMapping` supports a `method` attribute accepting one or more `RequestMethod` values. The following example illustrates a legacy search endpoint accepting both GET and POST for compatibility with two client groups. Both methods use the same query parameter and return the same result:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderSearchController {

    @Operation(
        summary = "Search orders by customer",
        description = "Legacy compatibility endpoint accepting GET and POST with the same customerId parameter."
    )
    @RequestMapping(
        path = "/search",
        method = { RequestMethod.GET, RequestMethod.POST },
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public List<OrderSummary> search(
            @Parameter(description = "Customer ID", example = "CUS-100")
            @RequestParam("customerId") String customerId) {
        return orderService.searchByCustomer(customerId);
    }
}
```

With the mapping above, Spring registers two HTTP methods for the same handler and the same path. Structurally, OpenAPI represents two separate operations:

```yaml
paths:
  /api/orders/search:
    get:
      summary: Search orders by customer
      description: Legacy compatibility endpoint accepting GET and POST with the same customerId parameter.
      parameters:
        - name: customerId
          in: query
          required: true
          schema:
            type: string
    post:
      summary: Search orders by customer
      description: Legacy compatibility endpoint accepting GET and POST with the same customerId parameter.
      parameters:
        - name: customerId
          in: query
          required: true
          schema:
            type: string
```

The YAML snippet above omits responses and other metadata to focus on the two operations. Metadata placed on a shared handler can be applied to each corresponding operation. Therefore, only use a single multi-method handler when the methods share the same purpose, input mechanism, outcome, and security policy.

If GET and POST have different semantics—for example, GET reads data while POST creates or updates data—split them into two handlers:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Get order by ID"
    )
    public OrderResponse getById(@PathVariable long id) {
        return orderService.getById(id);
    }

    @PostMapping
    @Operation(
        operationId = "createOrder",
        summary = "Create order"
    )
    @ApiResponse(responseCode = "201", description = "Order created")
    public OrderResponse create(@Valid @RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

When handlers are split, each operation can have its own `summary`, `description`, `operationId`, request body, response, status code, and security requirements. This is usually much clearer when the contracts of different HTTP methods diverge.

## 3. One Handler Mapped to Multiple Paths

The `path` or `value` attribute of `@RequestMapping` can accept an array of paths. Spring invokes the same handler when a request matches any of those paths.

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping({ "/{id}", "/legacy/{id}" })
    @Operation(summary = "Get order details")
    public OrderResponse getById(@PathVariable long id) {
        return orderService.getById(id);
    }
}
```

This mapping creates two access paths:

```text
GET /api/orders/{id}
GET /api/orders/legacy/{id}
```

In OpenAPI, the two paths are represented as two Path Items, each containing a `get` operation. This can be useful during URL migrations or when keeping compatibility aliases for legacy clients.

If each URL requires a different description, tag, or `operationId`, a single handler is not flexible enough because annotations on the method are shared. You can split into small handlers calling the same service:

```java
@GetMapping("/{id}")
@Operation(operationId = "getOrderById", summary = "Get order by ID")
public OrderResponse getById(@PathVariable long id) {
    return orderService.getById(id);
}

@GetMapping("/legacy/{id}")
@Operation(operationId = "getLegacyOrderById", summary = "Get order via legacy URL")
public OrderResponse getLegacyById(@PathVariable long id) {
    return orderService.getById(id);
}
```

In OpenAPI, `operationId` must be unique across the entire document. If the same `operationId` is declared for path aliases, the document can violate this rule and confuse client generation tools. Check the output and validator; if each operation needs a distinct identifier, use separate handlers with distinct `operationId` values.

## 4. Combining Class-Level and Method-Level Mappings

Spring allows placing `@RequestMapping` at the controller level to declare a shared path prefix, then placing mappings on individual handlers to specify concrete paths and conditions. Spring combines both levels to form the full path.

```java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    @GetMapping
    @Operation(operationId = "listOrders", summary = "List orders")
    public List<OrderSummary> list() {
        return orderService.findAll();
    }

    @GetMapping("/{id}")
    @Operation(operationId = "getOrderById", summary = "Get order by ID")
    public OrderResponse get(@PathVariable long id) {
        return orderService.getById(id);
    }

    @PostMapping
    @Operation(operationId = "createOrder", summary = "Create order")
    public OrderResponse create(@Valid @RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
```

The result is three operations at `/api/v1/orders` and `/api/v1/orders/{id}`. The class-level prefix avoids repeating paths and keeps controller structure readable. When the OpenAPI document is generated, inspect full paths under `paths` rather than relying solely on the path written on the method annotation.

Do not place multiple independent mapping annotations on the same element, for example:

```java
// Avoid: two mapping annotations on the same method.
@GetMapping("/search")
@PostMapping("/search")
public List<OrderSummary> search() {
    return orderService.search();
}
```

Spring warns when it detects multiple `@RequestMapping` or composed annotations such as `@GetMapping` and `@PostMapping` on the same element; only the first mapping is used. If you genuinely need multiple HTTP methods on the same handler, declare a single `@RequestMapping` with a `method` array. If the methods have different semantics, create separate handlers.

## 5. Multiple Mapping Conditions on the Same Path and HTTP Method

Besides path and HTTP method, Spring can distinguish handlers using conditions:

| Mapping Attribute | Purpose | Related Representation in OpenAPI |
| --- | --- | --- |
| `params` | Condition on presence, absence, or specific value of a query parameter | Declare parameter, `required`, `enum`, and describe the condition |
| `headers` | Condition on request headers | Declare header parameter and describe required values |
| `consumes` | Restricts request `Content-Type` | Media types under `requestBody.content` |
| `produces` | Restricts response type based on `Accept` | Media types under `responses.content` |
| `path` | One or more URL patterns | Separate Path Items under `paths` |
| `method` | One or more HTTP methods | Separate operations per method in a Path Item |

For example, a controller can accept multiple request formats:

```java
@PostMapping(
    path = "/import",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.APPLICATION_XML_VALUE
    },
    produces = MediaType.APPLICATION_JSON_VALUE
)
@Operation(summary = "Import orders")
public OrderResponse importOrder(@Valid @RequestBody ImportOrderRequest request) {
    return orderService.importOrder(request);
}
```

If the application's converters actually support both JSON and XML for `ImportOrderRequest`, OpenAPI can describe a single request body with multiple media types. In OpenAPI structure, they sit under the same operation:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/ImportOrderRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/ImportOrderRequest'
```

This is still one `POST` operation, not two different operations. `consumes` and `produces` describe accepted or returned content types; they do not increase the number of HTTP methods in OpenAPI.

`params` or `headers` conditions can be used by Spring to pick one among several handlers sharing the same path and method. However, OpenAPI has only one operation per path/method pair. If multiple handlers share `GET /api/orders` while differing in `params` or `headers`, they cannot be represented as two independent `get` operations. Document the parameters and valid values within one operation, or design separate paths/methods if they represent genuinely distinct API behaviors.

## 6. Overloaded Handlers with the Same Path and HTTP Method

Java allows overloading multiple methods with the same name and different parameter lists. Spring can also register multiple handlers for the same path and HTTP method when distinguishing conditions such as `consumes`, `params`, or `headers` are present. Even so, OpenAPI does not allow two separate `post` operations at the same path.

For example, the following two handlers accept two different body types at the same `POST /api/orders/import`:

```java
@PostMapping(path = "/import", consumes = MediaType.APPLICATION_JSON_VALUE)
public ImportResult importJson(@RequestBody JsonImportRequest request) {
    return orderService.importJson(request);
}

@PostMapping(path = "/import", consumes = MediaType.APPLICATION_XML_VALUE)
public ImportResult importXml(@RequestBody XmlImportRequest request) {
    return orderService.importXml(request);
}
```

springdoc treats overloaded handlers in the same class sharing the same HTTP method and path as a single OpenAPI endpoint. With differing parameter variants, the document may represent combined schemas via `oneOf`; with multiple consuming media types, the request body can contain multiple content types. Inspect the actual output document to confirm schemas and media types are merged as expected.

If `@Operation` is used on multiple overloaded methods, metadata may be overwritten when springdoc merges them. The springdoc FAQ recommends placing `@Operation` on one of the overloaded methods. If each variant needs an independent summary, response, security, or business rules, consider redesigning to give them distinct paths or methods.

## 7. Operation Metadata When a Handler Is Shared

`@Operation` describes the operation generated by springdoc. When a handler is mapped to multiple methods or multiple paths, annotations on the handler serve as shared metadata. Fields to watch include:

- `summary`: short sentence stating what the action does;
- `description`: usage conditions, differences between methods, or URL aliases;
- `operationId`: unique operation name in the document;
- `tags`: operation group in Swagger UI;
- `deprecated`: marks a legacy operation as no longer recommended;
- `security`: authentication requirements if different from global settings;
- `responses`: status codes and returned payloads.

For backward-compatible endpoints, `deprecated = true` can tell clients to migrate to a new endpoint. However, when one handler is shared by both new and legacy URLs, `deprecated` applies to all operations generated from that handler. If you want to mark only the legacy URL, split into two handlers so each has its own metadata.

Example separating legacy and current aliases:

```java
@GetMapping("/{id}")
@Operation(
    operationId = "getOrderById",
    summary = "Get order by ID"
)
public OrderResponse getById(@PathVariable long id) {
    return orderService.getById(id);
}

@GetMapping("/legacy/{id}")
@Operation(
    operationId = "getLegacyOrderById",
    summary = "Get order via legacy URL",
    description = "Maintained to support legacy clients; please migrate to GET /api/orders/{id}.",
    deprecated = true
)
public OrderResponse getLegacyById(@PathVariable long id) {
    return orderService.getById(id);
}
```

## 8. HEAD, OPTIONS, and Mappings Without a Declared Method

Spring handles certain HTTP methods according to framework conventions:

- `GET` mappings automatically support `HEAD` in Spring MVC; normally there is no need to create a separate `HEAD` handler just to return headers without a response body.
- For `OPTIONS`, Spring MVC by default can return an `Allow` header listing the methods declared for the matching URL. There is no need to create a separate `OPTIONS` operation if relying solely on this automatic behavior.
- If the API has custom `HEAD` or `OPTIONS` behavior that must be published to clients, define the handler explicitly and inspect the OpenAPI output.

`@RequestMapping` without a declared `method` means Spring can accept every HTTP method matching the remaining mapping conditions. This is usually too broad for a public API and makes the contract ambiguous. Declare the method explicitly using `@GetMapping`, `@PostMapping`, or `@RequestMapping(method = ...)` to constrain behavior and make the OpenAPI document easy to verify.

## 9. How to Verify Mappings After Generating OpenAPI

Once the Spring Boot application starts, open the default documentation endpoint `/v3/api-docs` or your custom path. Locate the paths to inspect and confirm:

1. Every expected path pattern appears under `paths`.
2. Each path has the exact operations matching its declared HTTP methods.
3. `summary`, `description`, `tags`, `deprecated`, and `operationId` accurately reflect each operation's meaning.
4. `parameters` contains the required path, query, and header parameters; `required` attributes and schemas are accurate.
5. `requestBody.content` lists the media types the controller actually accepts.
6. `responses` accurately describes returned status codes and media types.
7. There are no duplicate `operationId` values and no operations overwritten due to overloaded handlers.

Quick command to inspect part of the document with `curl`:

```bash
curl -s http://localhost:8080/v3/api-docs
```

For large documents, save the JSON response and use JSONPath or an OpenAPI inspection tool to view `paths` separately. Then test each combination of path, HTTP method, query/header condition, and content type at runtime to confirm Spring selects the right handler. The generated document shows the published contract; only real requests verify that routing and processing conditions behave as intended.

## 10. Common Issues and Troubleshooting

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Only one HTTP method appears in OpenAPI | `@RequestMapping` declares only one method or output is filtered/overwritten | Check `method` in the mapping and `paths` in `/v3/api-docs` |
| Placed `@GetMapping` and `@PostMapping` on the same method, yet only one works | Spring does not support multiple mapping annotations on the same element; only the first is used | Use a single `@RequestMapping(method = {...})` or split handlers |
| Path alias does not appear | Path pattern is missing from the `path` array or filtered out by group config | Check mapping and `springdoc.paths-to-match` |
| Two handlers with the same path/method produce one operation | OpenAPI allows only one operation per path/method; springdoc merges overloads | Document variants in the same operation or split APIs into separate paths/methods |
| Duplicate `operationId` | Multiple path aliases share the same `operationId` value | Use separate handlers with distinct IDs or adjust metadata after generation |
| `consumes` has multiple types yet docs show only one schema | Converter or content annotation does not describe all media types | Check actual converters and declare `@Content` per media type if needed |
| Description overwritten across overloaded handlers | Multiple `@Operation` annotations apply to one merged endpoint | Place operation metadata on only one overload or split handlers |
| Mapping without HTTP method leads to missing or confusing docs | Spring accepts multiple methods; intended contract is unclear | Declare specific methods and verify with your springdoc version |

## 11. Design Principles

Use one handler for multiple HTTP methods only when the methods genuinely share the same purpose and can share request, response, description, and security. Use one handler for multiple paths when the URLs are pure aliases for the same action. For methods or URLs with distinct behaviors, split handlers and share a service at the business layer so each operation has accurate metadata.

In particular, verify `operationId`, because many client generators rely on it to name functions. Ensure each operation has a unique identifier and clearly describes its method/path, request, and responses. Do not rely on Java code compiling to conclude that the OpenAPI document accurately describes the mapping.

## 12. Official References

- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html) — combining class-level/method-level mappings, path arrays, HTTP methods, and request conditions; rule against multiple mapping annotations on the same element; HEAD and OPTIONS behavior.
- [Springdoc-openapi — FAQ](https://springdoc.org/faq.html) — how springdoc handles overloaded handlers on the same path and HTTP method, multiple consuming media types, and merged parameters.
- [OpenAPI Specification 3.1.1 — Path Item Object](https://spec.openapis.org/oas/v3.1.1.html#path-item-object) — path structure and operations per HTTP method.
- [OpenAPI Specification 3.1.1 — Operation Object](https://spec.openapis.org/oas/v3.1.1.html#operation-object) — metadata of each operation and the uniqueness requirement for `operationId`.

When a handler has multiple mappings, treat the OpenAPI output as a map of path/method pairs clients are actually allowed to invoke. Cross-checking this map against Spring mappings and testing each request condition ensures the documentation accurately reflects application behavior.
