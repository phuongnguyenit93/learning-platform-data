# Path, Query, Header, and Cookie Parameters

An API often receives input data from multiple locations in an HTTP request. Some resource identifiers reside directly in the URL, filters sit after the question mark, metadata travels in headers, and session information is sent by browsers via cookies. In OpenAPI, these four groups are described using **parameter** objects with locations (**in**) **path**, **query**, **header**, and **cookie**, respectively.

With **springdoc-openapi**, Spring MVC annotations help the library infer most parameters from controller signatures. OpenAPI annotations add descriptions, examples, schemas, and serialization rules when the contract needs to be more explicit. This lesson focuses on choosing the right location, declaring them in Spring Boot, and verifying the generated specification.

## 1. Four Parameter Locations in an HTTP Request

Consider a request to fetch an order:

~~~http
GET /api/orders/8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001?includeItems=true&page=0 HTTP/1.1
Host: api.example.com
X-Request-Id: req-2026-0042
Cookie: locale=vi
~~~

Input values sit in different locations:

| OpenAPI location | Example data | Common purpose | Spring MVC |
|---|---|---|---|
| **path** | **/api/orders/{orderId}** | Identify a resource or sub-resource | **@PathVariable** |
| **query** | **includeItems=true**, **page=0** | Filter, search, paginate, sort, or choose representation | **@RequestParam** |
| **header** | **X-Request-Id: req-2026-0042** | Request metadata, tracing, preconditions, or versioning | **@RequestHeader** |
| **cookie** | **locale=vi** | Preferences or state stored by the client in cookies | **@CookieValue** |

In OpenAPI, each parameter has a **name**, a location (**in**), and usually a schema describing its data type. The combination of name and location identifies a parameter; the same name can appear in two different locations, such as **version** in query and **X-Api-Version** in header.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Path"]
    A --> C["Query string"]
    A --> D["Headers"]
    A --> E["Cookies"]
    B --> F["path parameter"]
    C --> G["query parameter"]
    D --> H["header parameter"]
    E --> I["cookie parameter"]
    F --> J["OpenAPI Parameter"]
    G --> J
    H --> J
    I --> J
    J --> K["name + in + schema + description"]
~~~

A key point to remember is that parameters describe values passed outside the request body. If the client sends a JSON object in the HTTP body, describe it using **requestBody**; the body schema is a separate schema, not a query parameter.

## 2. Path Parameters: Identifying Resources in the Path

A path parameter is part of a path template. For example, **/api/orders/{orderId}** uses **orderId** to identify an order. In Spring MVC, use **@PathVariable**:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{orderId}")
    public OrderResponse getOrder(
        @PathVariable("orderId") UUID orderId
    ) {
        // Find the order by orderId
        return null;
    }
}
~~~

springdoc recognizes **@PathVariable** and generates a parameter with location **path**. Descriptions and examples can be added using the **@Parameter** annotation:

~~~java
@GetMapping("/{orderId}")
public OrderResponse getOrder(
    @Parameter(
        description = "UUID of the order to view",
        example = "8f4c2c2e-3d3d-4c2b-a3d8-5e3b7b6a1001"
    )
    @PathVariable("orderId") UUID orderId
) {
    // ...
}
~~~

Important rules:

- The placeholder name in the path must match the bound variable name. Using an explicit **@PathVariable("orderId")** avoids relying on parameter name retention during compilation.
- Path parameters are always required. According to the OpenAPI specification, a parameter with **in: path** must have **required: true**.
- If a path template has multiple placeholders, all corresponding parameters must be declared.
- Path parameters should represent resource identifiers or hierarchy. Optional filters usually fit query parameters better.

For example, **/api/orders/{orderId}/items/{itemId}** has two path parameters: **orderId** and **itemId**. Both are required because missing either value means the URL no longer matches the path template.

## 3. Query Parameters: Filtering, Pagination, and Query Options

Query parameters appear after the **?** in a URL. Multiple values are joined with **&**. They are commonly used for search criteria, pagination, sorting, or selecting returned data.

~~~java
@GetMapping
public List<OrderResponse> searchOrders(
    @Parameter(description = "Order status", example = "PAID")
    @RequestParam(required = false) OrderStatus status,

    @Parameter(description = "Page number, starting from 0", example = "0")
    @RequestParam(defaultValue = "0") int page,

    @Parameter(description = "Number of records per page", example = "20")
    @RequestParam(defaultValue = "20") int size,

    @Parameter(description = "Whether to include line items in the result", example = "true")
    @RequestParam(defaultValue = "false") boolean includeItems
) {
    // ...
    return List.of();
}
~~~

In Spring MVC:

- **@RequestParam** is required by default (**required = true**) if no **defaultValue** is specified.
- **required = false** allows the request to omit the parameter.
- With **defaultValue**, Spring uses the default value when the parameter is absent or empty; the parameter is no longer required for binding.
- Java types such as **int**, **boolean**, **UUID**, or enums are converted by Spring from text values received in the URL. Invalid values can result in conversion errors or request errors.

For public APIs, clearly document the meaning, value domain, units, default value, and examples. For instance, whether **page** starts at 0 or 1 is part of the contract; simply writing the name **page** is not enough.

### Grouping Multiple Query Parameters with ParameterObject

When an endpoint has many filters, the method signature can become long. springdoc-openapi's **@ParameterObject** allows expanding an object's properties into individual query parameters in the documentation:

~~~java
public class OrderSearchCriteria {
    private OrderStatus status;
    private String customer;
    private Integer page;
    private Integer size;

    public OrderStatus getStatus() { return status; }
    public void setStatus(OrderStatus status) { this.status = status; }
    public String getCustomer() { return customer; }
    public void setCustomer(String customer) { this.customer = customer; }
    public Integer getPage() { return page; }
    public void setPage(Integer page) { this.page = page; }
    public Integer getSize() { return size; }
    public void setSize(Integer size) { this.size = size; }
}

@GetMapping("/search")
public List<OrderResponse> search(
    @ParameterObject OrderSearchCriteria criteria
) {
    // ...
    return List.of();
}
~~~

In the example, the **status**, **customer**, **page**, and **size** properties are rendered as query parameters. **@ParameterObject** is a springdoc annotation, typically imported from **org.springdoc.core.annotations.ParameterObject** in the springdoc 2.x line. Check the corresponding package if the project uses a different version line.

Only use **@ParameterObject** for objects bound from the query string, typically model attributes. If the client sends a JSON object in the body, use **@RequestBody**; these two mechanisms have different transmission methods and OpenAPI structures.

## 4. Header Parameters: Request Metadata

Headers carry metadata at the HTTP request level. Common examples include request IDs, language, cache conditions, or routing information. In Spring MVC, use **@RequestHeader**:

~~~java
@GetMapping("/{orderId}")
public OrderResponse getOrder(
    @PathVariable UUID orderId,
    @Parameter(
        description = "Correlation ID to trace the request across services",
        example = "req-2026-0042"
    )
    @RequestHeader(name = "X-Request-Id", required = false)
    String requestId
) {
    // ...
    return null;
}
~~~

A header parameter can be required or optional. If a header is absent while **required = true**, Spring MVC may return a missing-header error before invoking controller logic. For optional headers, define how the application behaves when no value is provided.

HTTP header names are case-insensitive according to HTTP rules. However, use a consistent casing in documentation, such as **X-Request-Id**, so integrators can easily recognize it.

### Do Not Document Authentication Headers as Regular Parameters

The **Authorization**, **Accept**, and **Content-Type** headers have dedicated representations in OpenAPI:

- Document authentication using **securitySchemes** and **security**, such as HTTP Bearer or API key.
- Request body media types are documented in **requestBody.content**.
- Response media types are documented in **responses.content**.

The OpenAPI specification ignores header parameters named **Accept**, **Content-Type**, or **Authorization**. Therefore, do not declare them as regular parameters to replace content negotiation or security schemes.

Example of documenting a Bearer token header with OpenAPI:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI orderApi() {
        return new OpenAPI()
            .components(new Components().addSecuritySchemes(
                "bearerAuth",
                new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")
            ))
            .addSecurityItem(new SecurityRequirement().addList("bearerAuth"));
    }
}
~~~

This example documents an authentication mechanism applied at the document level. If only certain operations require authentication, you can attach **@SecurityRequirement** to those operations or configure them accordingly. Do not put real tokens into examples or parameter descriptions.

## 5. Cookie Parameters: Values Sent in the Cookie Header

Browsers and HTTP clients send cookies in the **Cookie** header. Spring MVC provides **@CookieValue** to bind a specific cookie:

~~~java
@GetMapping("/preferences")
public PreferenceResponse getPreferences(
    @Parameter(
        description = "Selected language code",
        example = "vi"
    )
    @CookieValue(name = "locale", required = false)
    String locale
) {
    String selectedLocale = locale == null ? "vi" : locale;
    // ...
    return null;
}
~~~

Cookie parameters can be optional. If a cookie is required but not sent, Spring MVC reports a missing cookie error. Cookies are also transmitted as text; if binding to another type is needed, Spring performs conversion similarly to other request values.

In OpenAPI, a cookie parameter is represented with **in: cookie**. Example:

~~~yaml
parameters:
  - name: locale
    in: cookie
    required: false
    description: Selected language code
    schema:
      type: string
      example: vi
~~~

Several design considerations:

- Cookies are usually sent automatically by browsers based on domain, path, SameSite, and configured cookie attributes. Swagger UI users may not have the same control over cookies as with a dedicated HTTP client.
- **HttpOnly** cookies cannot be read directly by browser-side JavaScript. Testing APIs in Swagger UI also depends on CORS configuration, credentials, and browser cookie policies.
- If a cookie contains a session or authentication credentials, document the authentication mechanism using an appropriate security scheme, such as API key with **in: cookie**, rather than treating it merely as a UI preference.
- Authentication cookies introduce CSRF protection requirements depending on the application architecture. The API specification should clearly state how clients send the cookie and anti-CSRF token if required by the system.

Example of declaring a cookie as an API key in OpenAPI configuration:

~~~java
@Bean
public OpenAPI cookieAuthenticatedApi() {
    return new OpenAPI()
        .components(new Components().addSecuritySchemes(
            "sessionCookie",
            new SecurityScheme()
                .type(SecurityScheme.Type.APIKEY)
                .in(SecurityScheme.In.COOKIE)
                .name("SESSION")
        ))
        .addSecurityItem(new SecurityRequirement().addList("sessionCookie"));
}
~~~

This is how cookies used for authentication are documented. If a cookie only stores non-sensitive preferences such as display language, it can be documented as a regular cookie parameter.

## 6. Parameter Schema, Requiredness, and Example Values

Each parameter has a schema describing its data type and constraints. A few examples:

| Data | Common OpenAPI schema |
|---|---|
| Order UUID | **type: string**, **format: uuid** |
| Page number | **type: integer**, **format: int32**, **minimum: 0** |
| Toggle flag | **type: boolean** |
| Order status | **type: string**, **enum: [PENDING, PAID, CANCELLED]** |
| Timestamp | **type: string**, **format: date-time** |

You can use **@Parameter** to add descriptions, examples, and schemas:

~~~java
@GetMapping
public List<OrderResponse> find(
    @Parameter(
        name = "status",
        description = "Status to filter by",
        example = "PAID",
        schema = @Schema(
            type = "string",
            allowableValues = {"PENDING", "PAID", "CANCELLED"}
        )
    )
    @RequestParam(required = false) String status
) {
    // ...
    return List.of();
}
~~~

If the Java parameter already has an enum type, springdoc can usually infer the set of values from the enum. Only redeclare **allowableValues** when you need to control the description or when the Java type does not fully express the contract.

**required** specifies whether the client must send the parameter. It does not mean whether the value is allowed or disallowed to be **null**. For parameters, clearly define:

- Path parameters are always required.
- Query, header, and cookie parameters can be required or optional depending on the contract.
- Default values must be expressed consistently across Spring MVC, OpenAPI documentation, and actual logic.
- Schemas should describe types, formats, enums, and numeric or length bounds if they are part of the contract.

Do not put real sensitive values in **example**. Use mock illustrative values for tokens, customer IDs, session cookies, or personal data.

## 7. Passing Lists and Serialization Rules

A parameter can be an array or list. For example, a client may want to filter by multiple statuses. OpenAPI describes not only the array type but also how values are serialized on the HTTP wire.

For query parameters, two forms are common:

~~~http
GET /api/orders?status=PAID&status=PENDING
GET /api/orders?status=PAID,PENDING
~~~

The first form passes multiple values with the same name; the second separates values with commas. In OpenAPI, the representation is controlled by **style** and **explode**. For query parameters, **style: form** is the default; **explode: true** typically produces the repeated-name form, whereas **explode: false** produces the comma-separated form.

~~~yaml
parameters:
  - name: status
    in: query
    required: false
    style: form
    explode: true
    description: List of statuses to filter by
    schema:
      type: array
      items:
        type: string
        enum: [PENDING, PAID, CANCELLED]
~~~

For parameters in other locations, OpenAPI has its own default serialization rules. Path and header typically use **style: simple**; query and cookie typically use **style: form**. When a special format is needed, declare it explicitly and verify the request Swagger UI actually sends.

In Spring MVC, how a list is converted also depends on the parameter type, converters, and binding configuration. For example, **List<String>** can be bound from a comma-separated string, while **MultiValueMap** or repeated-key submission preserves multiple values. Therefore, the documentation must match actual controller behavior, not just the intended schema.

With OpenAPI annotations, arrays can be described using **@ArraySchema**:

~~~java
@GetMapping
public List<OrderResponse> findByStatuses(
    @Parameter(
        description = "Statuses to filter by",
        array = @ArraySchema(
            schema = @Schema(
                type = "string",
                allowableValues = {"PENDING", "PAID", "CANCELLED"}
            )
        ),
        style = ParameterStyle.FORM,
        explode = Explode.TRUE
    )
    @RequestParam(required = false) List<String> status
) {
    // ...
    return List.of();
}
~~~

The **ParameterStyle** and **Explode** types belong to swagger-annotations. Depending on the library version, annotation signatures may differ; if the project does not need custom serialization, let springdoc infer the schema from the Java type and inspect the output specification.

## 8. Declaring Parameters at the Method and Operation Levels

In normal cases, placing **@Parameter** directly beside the controller parameter keeps the description close to where the value is bound:

~~~java
@GetMapping("/{orderId}")
public OrderResponse get(
    @Parameter(description = "Order ID", example = "42")
    @PathVariable long orderId,

    @Parameter(description = "Request correlation ID")
    @RequestHeader(name = "X-Request-Id", required = false)
    String requestId
) {
    // ...
    return null;
}
~~~

When you want to declare parameters at the operation level, you can use the **parameters** attribute of **@Operation**:

~~~java
@Operation(
    summary = "Search orders",
    parameters = {
        @Parameter(
            name = "X-Client-Version",
            in = ParameterIn.HEADER,
            description = "Client version",
            required = false,
            example = "2.4.0"
        )
    }
)
@GetMapping
public List<OrderResponse> find() {
    // ...
    return List.of();
}
~~~

Operation-level parameters are useful when the documentation needs to describe a value that is not bound directly to a method parameter, or when supplementing contract details. However, if the application actually needs to read that value, the controller or processing layer must have a mechanism to receive it. Declaring documentation does not automatically make Spring MVC bind additional data.

You can hide a parameter from documentation using **@Parameter(hidden = true)** when appropriate. Hiding only affects documentation; it does not protect the endpoint, bypass permission checks, or turn a value into a secret. Do not use hidden as a security mechanism.

## 9. Spring MVC and OpenAPI Annotation Mapping

| Goal | Spring MVC annotation | OpenAPI / springdoc annotation |
|---|---|---|
| Receive path parameter | **@PathVariable** | **@Parameter** |
| Receive query parameter | **@RequestParam** | **@Parameter**, **@ParameterObject** |
| Receive header parameter | **@RequestHeader** | **@Parameter** |
| Receive cookie parameter | **@CookieValue** | **@Parameter** |
| Describe types and constraints | Java types, Bean Validation | **@Schema**, **@ArraySchema** |
| Describe authentication | Spring Security and security config | **@SecurityScheme**, **@SecurityRequirement**, **OpenAPI** bean |

Spring MVC determines how requests are bound and processed. OpenAPI describes the contract seen by the client. springdoc combines mappings and Java types with OpenAPI annotations to generate the specification. If documentation annotations declare something different from actual behavior, Swagger UI may guide clients to send invalid requests even though the application still runs.

## 10. Reading an Operation's OpenAPI Specification

The compact example below describes an endpoint with all four parameter locations:

~~~yaml
paths:
  /api/orders/{orderId}:
    get:
      operationId: getOrder
      summary: Get order
      parameters:
        - name: orderId
          in: path
          required: true
          description: Order UUID
          schema:
            type: string
            format: uuid
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
            default: false
        - name: X-Request-Id
          in: header
          required: false
          schema:
            type: string
        - name: locale
          in: cookie
          required: false
          schema:
            type: string
            example: vi
      responses:
        "200":
          description: Order retrieved successfully
~~~

When reading the **parameters** section, verify in order:

1. Does **name** match the actual placeholder, query key, header, or cookie name?
2. Is **in** the correct location where the data is sent?
3. Does **required** reflect actual controller behavior?
4. Does **schema** have the right type, format, enum, and constraints?
5. Do **description**, **example**, **style**, and **explode** help clients send valid requests?

Parameters can be placed directly inside the operation or referenced from **components.parameters** when multiple operations share a definition. Either way, the final specification must clearly state the name, location, and schema.

## 11. Verifying the Document Generated by springdoc

After writing the controller and annotations, open the OpenAPI JSON endpoint, typically **/v3/api-docs**; if the application enables YAML, check **/v3/api-docs.yaml**. Swagger UI is usually located at **/swagger-ui/index.html**, unless the project has customized the path.

For each endpoint, cross-check three layers:

- **Source code:** Do the Spring MVC annotations use the right binding location and requiredness policy?
- **Specification:** Does **parameters** have the right name, in, schema, example, style, and explode?
- **Actual request:** Does Swagger UI or an HTTP client send the exact URL, headers, and cookies expected by the server?

Scenarios worth testing:

- Omit a path parameter: the URL must no longer match the path template.
- Omit an optional query parameter: the server must apply the published default handling.
- Send a query value of the wrong type or outside the enum: the server must return an error matching the contract.
- Omit a required header: verify the missing-header error.
- Send an optional cookie and omit the cookie: both cases must be handled properly.
- Send a list using the published serialization: verify Spring binds all values.

If the endpoint works but the documentation displays incorrectly, review the mappings, parameter types, OpenAPI annotations, and springdoc configuration. If the documentation is accurate but test requests in Swagger UI fail, also check CORS, credentials, cookie policies, security schemes, and server configuration.

## 12. Common Design Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
|---|---|---|
| Using a path parameter for an optional filter | Resource URL becomes confusing and values cannot be omitted | Move the filter to a query parameter |
| **@PathVariable** name does not match placeholder | Spring fails to bind the value or documentation is unclear | Specify names explicitly in both mapping and annotation |
| Marking a query parameter required in docs while the controller allows omitting it | Clients send unnecessary data or misunderstand the contract | Synchronize **required**, **defaultValue**, and descriptions |
| Declaring Authorization as a header parameter | Security documentation is not modeled properly | Use a security scheme |
| Describing Content-Type as a parameter | Confuses body metadata with parameters | Use **requestBody.content** |
| Documenting a list without specifying the separator | Clients send **a,b** while the server expects separate values or vice versa | Declare and verify **style** / **explode** |
| Using cookies for auth while ignoring CSRF and browser policies | API testing or browser integration fails, increasing security risks | Document the security scheme and cookie/CSRF requirements clearly |
| Using **hidden** to conceal a sensitive parameter | Creates a false sense of security; the server still accepts the value | Protect with authentication, authorization, and proper data handling |

Secrets should not be passed in the query string because URLs can appear in browser history, logs, analytics systems, and referrer headers. Sensitive data must be transmitted using an appropriate authentication mechanism over HTTPS and must not be logged indiscriminately.

## Conclusion

Path, query, header, and cookie are all locations for passing parameters in an HTTP request, each serving a distinct purpose. **@PathVariable** identifies resources; **@RequestParam** passes filters and options; **@RequestHeader** carries metadata; **@CookieValue** reads cookies from the request. springdoc-openapi uses these annotations to generate OpenAPI parameters, while **@Parameter**, **@ParameterObject**, **@Schema**, and security schemes express the contract in greater detail. Check both the JSON/YAML specification and actual requests to ensure documentation, controllers, and client submissions always stay aligned.
