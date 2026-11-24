# Spring Cloud Function Web and Function Metadata

Spring Cloud Function lets you write business logic as Java functions independent of how they are deployed. A function can be invoked via HTTP, messaging, or serverless adapters without rewriting the business processing logic. The Spring Cloud Function Web module automatically exposes function beans as HTTP endpoints. `springdoc-openapi` can document those endpoints in OpenAPI, provided appropriate metadata is supplied so the documentation reflects the right operation name, HTTP method, request, response, and schemas.

In this topic, two layers of metadata must be distinguished:

- **Function runtime metadata:** function name, input/output types, `Supplier`/`Function`/`Consumer` kind, and information needed by Spring Cloud Function to convert data.
- **API metadata:** path, HTTP method, `operationId`, tags, parameters, request body, response statuses, and schemas that springdoc includes in OpenAPI.

Runtime metadata helps the framework invoke the function with the right types. API metadata helps clients understand and consume the HTTP contract. Having explicit generic types does not automatically generate full business descriptions for OpenAPI; conversely, OpenAPI annotations do not change how the function executes.

## 1. What Problem Does Spring Cloud Function Solve?

In a traditional Spring Boot application, business logic often lives in controllers or services. If you want to run the same logic over HTTP, message brokers, and serverless platforms, the team may have to write multiple adapters and repeat data conversion logic.

Spring Cloud Function isolates processing logic into a functional bean. The framework provides adapters to invoke the same function across multiple environments:

~~~text
                    +----------------------+
HTTP request ------>|                      |
Message broker ---->|   FunctionCatalog    |----> Function / Consumer / Supplier
Serverless event -->|                      |
                    +----------------------+
~~~

Core Java interfaces:

| Interface | Role | Example |
|---|---|---|
| Supplier<O> | Produces output data without taking input | Generating a report or list |
| Function<I, O> | Takes input and returns output | Normalizing product data |
| Consumer<I> | Takes input and performs a side effect | Recording an event, sending a notification |

Spring Cloud Function normalizes function beans inside `FunctionCatalog`. When invoked through the catalog, functions can be wrapped with capabilities such as type conversion, composition, and `Message` handling.

Spring Cloud Function Web is the HTTP adapter for this model. It fits simple, stateless functions that need to be exposed over HTTP. It does not replace all capabilities of Spring MVC or WebFlux such as complex controller routing, model binding, validation, and every REST convention.

## 2. Declaring Function Beans in Spring Boot

With standard Spring configuration, declare a bean of type `Supplier`, `Function`, or `Consumer`:

~~~java
@SpringBootApplication
public class FunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(FunctionApplication.class, args);
    }

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

The bean method name—`uppercase` in this example—becomes the function name registered by Spring Cloud Function. When using Spring Cloud Function Web, the function can be invoked over HTTP under that name.

For business logic with DTOs, declare concrete input and output types:

~~~java
public record NormalizeProductRequest(
    String sku,
    String displayName
) {}

public record NormalizeProductResponse(
    String sku,
    String displayName
) {}

@Configuration
class ProductFunctions {

    @Bean
    Function<NormalizeProductRequest, NormalizeProductResponse> normalizeProduct() {
        return request -> new NormalizeProductResponse(
            request.sku().trim().toUpperCase(Locale.ROOT),
            request.displayName().trim()
        );
    }
}
~~~

The generic types tell Spring Cloud Function that the input is `NormalizeProductRequest` and the output is `NormalizeProductResponse`. They are also a useful source of information for introspection tools and schema generation.

### Stable Function Naming

The function bean name becomes part of the URL. Renaming the bean method from `normalizeProduct` to `normalizeCatalogItem` can change the published path. Therefore, treat exposed function names as part of the API contract. If you want to change internal names, use an explicit bean name or plan endpoint migration.

Avoid overly generic bean names like `process`, `handle`, or `execute` when an application has multiple functions. Names like `normalizeProduct`, `calculateShippingFee`, or `publishOrderEvent` are much easier to read in URLs, logs, and OpenAPI.

## 3. Adding Spring Cloud Function Web

To automatically expose function beans over HTTP, add the Web module or aggregate starter of Spring Cloud Function:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

This starter gathers the dependencies needed for a quick-start experience. Manage versions using a Spring Cloud BOM compatible with the Spring Boot line in use; do not pin an independent Spring Cloud Function version manually if dependency management already manages versions.

If you prefer lower-level dependency management, you can use the `spring-cloud-function-web` module following the guide for your running Spring Cloud Function version.

Current Spring Cloud Function documentation describes web auto-configuration for Spring Boot web applications with MVC support. When using another web stack, confirm that the Spring Cloud Function adapter and version support that stack. Adding springdoc WebFlux does not automatically turn a Servlet adapter into WebFlux.

### Choosing Springdoc by Web Stack and Needs

Springdoc provides starters that only generate OpenAPI documents and starters that include Swagger UI:

| Web stack | Only OpenAPI JSON/YAML needed | Swagger UI also needed |
|---|---|---|
| Spring MVC / spring-web | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux / spring-webflux | springdoc-openapi-starter-webflux-api | springdoc-openapi-starter-webflux-ui |

Example dependency when the application uses Spring MVC and only needs OpenAPI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
</dependency>
~~~

If Swagger UI is needed, replace it with `springdoc-openapi-starter-webmvc-ui`. For Spring Boot 3, use the compatible springdoc 2.x line; for Spring Boot 4, use the springdoc 3.x line. Spring Boot 2 projects use the springdoc 1.x line with legacy artifacts. Consult your project's compatibility matrix and dependency management before choosing a version.

## 4. How Spring Cloud Function Web Maps Functions to HTTP Endpoints

When the web adapter is enabled, the function name becomes part of the path. The HTTP method and function kind determine how requests are handled.

Common mappings:

| Function kind | HTTP method | Path | Typical behavior |
|---|---|---|---|
| Supplier | GET | /{supplier} | Invokes the supplier and returns emitted data |
| Consumer | POST or PUT | /{consumer} | Sends request body into the consumer, typically returns 202 Accepted |
| Consumer | DELETE | /{consumer} | Invokes consumer via DELETE mapping, typically returns 204 No Content |
| Function | POST or PUT | /{function} | Converts request body to input, invokes function, and returns output |
| Function | GET | /{function}/{item} | Converts path item to input and invokes function |

Example with the `normalizeProduct` function:

~~~http
POST /normalizeProduct
Content-Type: application/json
Accept: application/json

{
  "sku": " p-001 ",
  "displayName": " Ballpoint pen "
}
~~~

Response:

~~~json
{
  "sku": "P-001",
  "displayName": "Ballpoint pen"
}
~~~

For a `Supplier` named `dailyReport`, the HTTP adapter can expose `GET /dailyReport`. For a `Consumer` named `orderEvents`, `POST /orderEvents` sends the payload to the consumer and has no business response like a result-returning `Function`.

If the catalog has only one function, the function name in the path can be optional. When there are multiple functions, the function name is normally placed in the path to select the right bean.

### Changing the Prefix of Function Endpoints

You can set a prefix using the `spring.cloud.function.web.path` property:

~~~yaml
spring:
  cloud:
    function:
      web:
        path: /functions
~~~

Then the `normalizeProduct` function can be called at `/functions/normalizeProduct`. The prefix must be used consistently across OpenAPI, security matchers, reverse proxies, and clients.

## 5. Selecting Exposed Functions and Composition

Spring Cloud Function supports composition by function name. Multiple functions can be chained using a pipe character or comma according to the adapter's rules.

Example with two functions:

~~~java
@Bean
Function<String, String> uppercase() {
    return value -> value.toUpperCase(Locale.ROOT);
}

@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

You can invoke composition by path:

~~~text
/uppercase,reverse
~~~

Or define composition in configuration:

~~~properties
spring.cloud.function.definition=uppercase|reverse
~~~

When using `definition` to select a single function or default composition, the adapter can map it to the root path. When the catalog has multiple functions, you can restrict exported functions using a semicolon-separated list:

~~~properties
spring.cloud.function.definition=normalizeProduct;calculateShippingFee
~~~

When using a filter list, only the listed functions or compositions are exposed; there is no default function at root. Verify the exact syntax and behavior of the Spring Cloud Function version in use.

Spring Cloud Function also allows mapping functions by HTTP method via `spring.cloud.function.http.<method>`. For example:

~~~properties
spring.cloud.function.http.GET=uppercase;reverse
spring.cloud.function.http.POST=normalizeProduct
~~~

These mappings affect runtime HTTP routing. They do not automatically supply complete OpenAPI summaries, request schemas, response schemas, or error codes. Contract descriptions still need to be declared in springdoc.

## 6. Content-Type and Converting Input Data for Functions

Spring Cloud Function converts raw request data into the input type declared by the function. This process relies on generic types, `Content-Type`, and matching `MessageConverter`/`ConversionService` instances.

For example:

| Content-Type | Typical function input |
|---|---|
| application/json | DTO or Map |
| text/plain | String |
| application/octet-stream | byte[] or InputStream depending on declaration |

With the function:

~~~java
Function<NormalizeProductRequest, NormalizeProductResponse> normalizeProduct()
~~~

clients should send `Content-Type: application/json` and JSON structurally compatible with `NormalizeProductRequest`. If `Content-Type` is omitted, Spring Cloud Function may default to `application/json` in documented cases; API clients should still send the header explicitly.

Example call using curl:

~~~bash
curl -i \
  -X POST http://localhost:8080/functions/normalizeProduct \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"sku":" p-001 ","displayName":" Ballpoint pen "}'
~~~

Do not confuse `Content-Type` with `Accept`:

- `Content-Type` describes the format of the body sent by the client.
- `Accept` describes the response format the client wants to receive.

If no converter matches the input type and `Content-Type`, the function may not be invoked and the request fails during data conversion. For special data types, a custom `MessageConverter` may need to be registered.

## 7. Passing Headers and Query Parameters via Message

A function can accept `Message<T>` instead of just payload `T`. `Message` contains both payload and headers, allowing business logic to use correlation IDs, tenant info, request metadata, or values passed by the adapter.

~~~java
@Bean
Function<Message<NormalizeProductRequest>, Message<NormalizeProductResponse>>
normalizeProductWithMetadata() {
    return message -> {
        NormalizeProductRequest request = message.getPayload();
        NormalizeProductResponse response = new NormalizeProductResponse(
            request.sku().trim().toUpperCase(Locale.ROOT),
            request.displayName().trim()
        );

        return MessageBuilder.withPayload(response)
            .copyHeaders(message.getHeaders())
            .build();
    };
}
~~~

When a function accepts `Message`, HTTP request headers can be translated into message headers. When a function returns `Message`, output headers can be translated into HTTP response headers. The payload remains the primary data part to describe in OpenAPI.

HTTP query parameters are placed by the adapter into a message header keyed `http_request_param`, whose value is a `Map`. Therefore, if a function needs to read query parameters, it can declare `Message<T>` as input and read that header. Do not expect query parameters to automatically become properties of the input DTO without a dedicated binding mechanism.

Conceptual example reading query parameters:

~~~java
@Bean
Function<Message<String>, String> greet() {
    return message -> {
        Object params = message.getHeaders().get("http_request_param");
        return "Hello " + message.getPayload() + " (" + params + ")";
    };
}
~~~

Do not copy internal headers, tokens, or sensitive data into response headers. If OpenAPI needs to publish a request/response header, declare it with `@Parameter` or `@ApiResponse` header metadata and verify the actual values.

## 8. Type Metadata in FunctionCatalog

`FunctionCatalog` is where Spring Cloud Function registers and looks up functions. Beans of type `Supplier`, `Function`, or `Consumer` are discovered and normalized into function invocations with appropriate metadata.

In ordinary `@Bean` declarations, the framework can usually infer input/output types from generic signatures. For instance, `Function<NormalizeProductRequest, NormalizeProductResponse>` provides clear type information.

Some ways of declaring functions can lose generic types at runtime, such as registering a function via functional bean definitions or using raw `Function`/`Object`. In such cases, `FunctionRegistration` can supply the type metadata:

~~~java
Function<NormalizeProductRequest, NormalizeProductResponse> function =
    request -> new NormalizeProductResponse(
        request.sku().trim().toUpperCase(Locale.ROOT),
        request.displayName().trim()
    );

FunctionRegistration<Function<NormalizeProductRequest, NormalizeProductResponse>>
    registration = new FunctionRegistration<>(function)
        .type(FunctionType.from(NormalizeProductRequest.class)
            .to(NormalizeProductResponse.class));
~~~

`FunctionRegistration` bundles a function together with its type metadata. `FunctionType` describes the input and output types. This metadata serves function invocation and data conversion; it does not replace OpenAPI schema annotations.

### Looking Up Functions in FunctionCatalog

You can inject `FunctionCatalog` to look up or list functions:

~~~java
@Component
class FunctionInspector {

    private final FunctionCatalog catalog;

    FunctionInspector(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    Set<String> functionNames() {
        return catalog.getNames(null);
    }

    Function<?, ?> findNormalizeProduct() {
        return catalog.lookup("normalizeProduct");
    }
}
~~~

`FunctionCatalog` lookup returns a function instrumented by the framework with capabilities such as type conversion and composition. Do not grab the function bean directly and assume it has all the supporting layers of a function retrieved from the catalog.

### Viewing Metadata via Actuator

Spring Cloud Function can publish the list of functions in the `functions` Actuator endpoint if the application includes Spring Boot Actuator and exposes the corresponding endpoint:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,functions
~~~

The `/actuator/functions` endpoint can display function names, `FUNCTION`/`CONSUMER`/`SUPPLIER` types, and input/output types. This is an operational endpoint for inspecting the catalog, not an OpenAPI document. Expose it only when needed and protect it with Spring Security or a management network policy; never expose internal function lists by default.

## 9. OpenAPI Metadata Differs from Runtime Metadata

`FunctionCatalog` can know input and output types, yet it does not know the full business semantics of an HTTP operation. For example, from `Function<OrderRequest, OrderResponse>`, a tool can infer schemas, but cannot automatically know:

- Whether the endpoint uses POST or PUT.
- What public name and purpose the operation has.
- Whether the request body is required.
- Which status codes such as 400, 404, or 409 can occur in business logic.
- Which fields are deprecated, sensitive, or read-only.
- Which OAuth scopes the endpoint requires.
- Which headers or query parameters are part of the contract.

Springdoc provides metadata annotations to describe this information:

| Annotation | Role |
|---|---|
| @RouterOperation | Describes a single operation generated from a function or functional endpoint |
| @RouterOperations | Describes multiple operations exposed from the same bean/function |
| @Operation | Summary, description, operationId, tags, security, and request body |
| @ApiResponse | HTTP response status and returned content |
| @Content | Media type and schema of request/response |
| @Schema | Name, type, description, example, and constraints of a model |
| @Parameter | Path, query, header, or cookie parameter |
| OpenApiCustomizer | Modifies the OpenAPI model after springdoc assembles the document |

Springdoc has supported documenting Spring Cloud Function Web since version 1.6.3. In current versions, you can use `@RouterOperation`, `@RouterOperations`, or `OpenApiCustomizer` to add metadata.

In springdoc 2.x and 3.x, the `RouterOperation`/`RouterOperations` annotations belong to package `org.springdoc.core.annotations`. Springdoc 1.x projects use the legacy package `org.springdoc.api.annotations`. Use imports matching your installed major version; do not mix annotations from two major versions.

## 10. Documenting a Single Function with @RouterOperation

For a function bean corresponding to one HTTP operation, you can attach `@RouterOperation` directly to the `@Bean` method. Declare `path` and `method` explicitly to avoid ambiguity between runtime mapping and documentation.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.web.bind.annotation.RequestMethod;

@Configuration
class ProductFunctionConfiguration {

    @Bean
    @RouterOperation(
        path = "/normalizeProduct",
        method = RequestMethod.POST,
        operation = @Operation(
            operationId = "products_normalize",
            summary = "Normalize product details",
            description = "Normalizes the SKU and display name of a product.",
            tags = {"Products"},
            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                required = true,
                content = @Content(
                    mediaType = "application/json",
                    schema = @Schema(implementation = NormalizeProductRequest.class)
                )
            ),
            responses = {
                @ApiResponse(
                    responseCode = "200",
                    description = "Normalized product details",
                    content = @Content(
                        mediaType = "application/json",
                        schema = @Schema(implementation = NormalizeProductResponse.class)
                    )
                ),
                @ApiResponse(
                    responseCode = "400",
                    description = "Invalid request body"
                )
            }
        )
    )
    Function<NormalizeProductRequest, NormalizeProductResponse> normalizeProduct() {
        return request -> new NormalizeProductResponse(
            request.sku().trim().toUpperCase(Locale.ROOT),
            request.displayName().trim()
        );
    }
}
~~~

In this example:

- The bean name `normalizeProduct` is used by Spring Cloud Function to identify the function.
- Path `/normalizeProduct` and method `POST` describe the corresponding HTTP route.
- `operationId` `products_normalize` is the stable identifier of the operation in OpenAPI.
- `requestBody` describes `NormalizeProductRequest`.
- Response `200` describes `NormalizeProductResponse`.
- Response `400` provides error details clients need to know.

If the application configures a `/functions` prefix, the public path will be `/functions/normalizeProduct`. Verify the final path in `/v3/api-docs` instead of looking only at annotations.

`operationId` must be unique within the OpenAPI document. Do not reuse the same `operationId` across multiple functions or multiple HTTP methods.

`@RouterOperation` only adds metadata for springdoc; it does not register an HTTP route on its own and does not alter Spring Cloud Function Web mappings. If the annotation describes PUT while runtime only accepts POST, OpenAPI will advertise an uncallable operation. Always verify both runtime mappings and the OpenAPI document.

## 11. Documenting Multiple HTTP Operations with @RouterOperations

A function can be invoked via multiple HTTP methods. When documenting multiple operations tied to the same bean, use `@RouterOperations`. Each `@RouterOperation` needs a `method`; declare `path` clearly so springdoc identifies the route accurately.

~~~java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/normalizeProduct",
        method = RequestMethod.POST,
        operation = @Operation(
            operationId = "products_normalizePost",
            summary = "Normalize product via POST",
            tags = {"Products"},
            responses = @ApiResponse(
                responseCode = "200",
                description = "Normalized product",
                content = @Content(
                    mediaType = "application/json",
                    schema = @Schema(implementation = NormalizeProductResponse.class)
                )
            )
        )
    ),
    @RouterOperation(
        path = "/normalizeProduct",
        method = RequestMethod.PUT,
        operation = @Operation(
            operationId = "products_normalizePut",
            summary = "Normalize product via PUT",
            tags = {"Products"},
            responses = @ApiResponse(
                responseCode = "200",
                description = "Normalized product",
                content = @Content(
                    mediaType = "application/json",
                    schema = @Schema(implementation = NormalizeProductResponse.class)
                )
            )
        )
    )
})
Function<NormalizeProductRequest, NormalizeProductResponse> normalizeProduct() {
    return request -> new NormalizeProductResponse(
        request.sku().trim().toUpperCase(Locale.ROOT),
        request.displayName().trim()
    );
}
~~~

This example documents two methods that Spring Cloud Function Web can use to invoke a `Function`. Publish only methods actually supported by the adapter and application configuration. If runtime only permits POST, do not include PUT in OpenAPI simply because the annotation allows declaring it.

For a bean with multiple function routes or multiple paths, provide sufficient `path`, `method`, `consumes`/`produces`, or conditions needed to uniquely identify each route. If annotations duplicate or mismatch runtime mappings, the documentation may miss operations or misdescribe them.

## 12. Linking Metadata to a Bean Method

When a function is declared on one bean while metadata resides on another method, `@RouterOperation` can use `beanClass` and `beanMethod` so springdoc knows which method to introspect. This is useful when the handler method carries its own Swagger annotations or the function bean is just a thin adapter.

~~~java
@RouterOperation(
    path = "/employees",
    method = RequestMethod.GET,
    beanClass = EmployeeQueryService.class,
    beanMethod = "findAll",
    operation = @Operation(
        operationId = "employees_findAll",
        summary = "List employees",
        tags = {"Employees"}
    )
)
@Bean
Supplier<List<EmployeeResponse>> employees() {
    return employeeQueryService::findAll;
}
~~~

The example above illustrates referencing a method that supplies business metadata. The class and method name must exist, and the method must have types and annotations matching the operation. When `beanMethod` is declared, `@Operation` can also be placed on that method as supported by springdoc.

Do not declare `beanClass`/`beanMethod` just to repeat information unnecessarily. Use them when you genuinely need springdoc to read metadata from another method.

## 13. Documenting Supplier and Consumer

A `Supplier` accepts no request body; it produces data when invoked. OpenAPI should describe a GET operation, response schema, and response conditions.

~~~java
@Bean
@RouterOperation(
    path = "/dailyReport",
    method = RequestMethod.GET,
    operation = @Operation(
        operationId = "reports_getDaily",
        summary = "Get daily report",
        tags = {"Reports"},
        responses = @ApiResponse(
            responseCode = "200",
            description = "Current report",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = DailyReport.class)
            )
        )
    )
)
Supplier<DailyReport> dailyReport() {
    return reportService::createCurrentReport;
}
~~~

A `Consumer` takes input and performs a side effect, such as recording an event. Because a `Consumer` does not return business data, the response is typically `202 Accepted` or `204 No Content` depending on HTTP mapping. Describe the exact runtime status code and body.

~~~java
@Bean
@RouterOperation(
    path = "/orderEvents",
    method = RequestMethod.POST,
    operation = @Operation(
        operationId = "orders_publishEvent",
        summary = "Publish order event",
        tags = {"Orders"},
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = OrderEvent.class)
            )
        ),
        responses = @ApiResponse(
            responseCode = "202",
            description = "Event accepted"
        )
    )
)
Consumer<OrderEvent> orderEvents() {
    return event -> eventPublisher.publish(event);
}
~~~

Do not document a `Consumer` as having a response object if runtime only accepts and processes input. If the HTTP adapter echoes the payload in the response, inspect the actual response and document that exact representation.

## 14. Input/Output Schemas and DTO Annotations

Generic types of `Function` give springdoc a basis for inferring schemas, yet DTOs still need clear descriptions on fields with business meaning:

~~~java
@Schema(name = "NormalizeProductRequest", description = "Input data for normalizing a product")
public record NormalizeProductRequest(
    @Schema(description = "SKU code", example = "p-001", minLength = 1, maxLength = 40)
    String sku,

    @Schema(description = "Display name", example = "Ballpoint pen", minLength = 1, maxLength = 160)
    String displayName
) {}

@Schema(name = "NormalizeProductResponse", description = "Product after normalization")
public record NormalizeProductResponse(
    @Schema(description = "Uppercased and trimmed SKU", example = "P-001")
    String sku,

    @Schema(description = "Trimmed display name", example = "Ballpoint pen")
    String displayName
) {}
~~~

`@Schema` documents schemas in OpenAPI. If runtime validation is needed, use Bean Validation annotations such as `@NotBlank`, `@Size`, or custom validators on DTOs. Writing `minLength`/`maxLength` only in OpenAPI does not make the server reject invalid data.

For a function taking `Message<NormalizeProductRequest>`, the request body schema should describe the `NormalizeProductRequest` payload, not create a `Message` wrapper model as if clients must send that wrapper as JSON. `Message` headers should be documented separately with OpenAPI `Parameter` if they are part of the public contract.

## 15. OpenApiCustomizer for Computed Metadata

Annotations work well when metadata is static and tied to a specific function. If you need to standardize `operationId`, add shared responses, adjust server URLs, or update metadata based on profiles/groups, use `OpenApiCustomizer`.

Example adding a description to an operation generated by springdoc:

~~~java
@Configuration
class FunctionOpenApiConfiguration {

    @Bean
    OpenApiCustomizer functionOperationCustomizer() {
        return openApi -> {
            PathItem pathItem = openApi.getPaths().get("/functions/normalizeProduct");
            if (pathItem != null && pathItem.getPost() != null) {
                pathItem.getPost()
                    .setDescription("Normalizes the SKU and display name of a product.");
            }
        };
    }
}
~~~

This snippet assumes the application configured the `/functions` prefix and the corresponding operation path. If the prefix or function name changes, update the path. With multiple OpenAPI groups, register the customizer in the right group or use the corresponding global mechanism.

`OpenApiCustomizer` only modifies the generated OpenAPI model. It does not register new functions, change HTTP mappings, add runtime validation, or alter the security filter chain.

## 16. Function Composition and the OpenAPI Contract

Composition allows chaining multiple functions into a single pipeline:

~~~java
@Bean
Function<String, String> trim() {
    return String::trim;
}

@Bean
Function<String, String> uppercase() {
    return value -> value.toUpperCase(Locale.ROOT);
}

@Bean
Function<String, String> normalizeSku() {
    return value -> value.replace(" ", "");
}
~~~

A composition can be defined using:

~~~properties
spring.cloud.function.definition=trim|uppercase|normalizeSku
~~~

From an OpenAPI perspective, a composition is typically a single operation with the input type of the first function and the output type of the last function. Creating separate operations for each internal step is unnecessary. If a composition is exposed on a path, document that pipeline's contract with a stable `operationId` and stable input/output schemas.

When functions have intermediate types that are not directly compatible, Spring Cloud Function can use content-type conversion and `MessageConverter`s to convert between steps in the composition. Do not document internal intermediate types as public request/response schemas if clients do not exchange those types directly.

## 17. Generating OpenAPI and Inspecting the Document

With the springdoc API starter, default documents are typically available at:

~~~text
/v3/api-docs
/v3/api-docs.yaml
~~~

If using the UI starter, Swagger UI can also display the document. While running the application, check:

1. Whether the function operation appears in `paths`.
2. Whether the path includes `spring.cloud.function.web.path` or the right context path.
3. Whether the HTTP method matches the actual mapping.
4. Whether `operationId` is unique and stable.
5. Whether the request body has the right media type and input schema.
6. Whether response status, media type, and output schema match runtime.
7. Whether `Consumer` has a response matching its acceptance behavior.
8. Whether security requirements reflect the endpoint protection policy.
9. Whether unexposed functions appear in the document.

Abbreviated OpenAPI YAML example:

~~~yaml
paths:
  /functions/normalizeProduct:
    post:
      operationId: products_normalize
      summary: Normalize product details
      tags:
        - Products
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/NormalizeProductRequest'
      responses:
        '200':
          description: Normalized product
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NormalizeProductResponse'
        '400':
          description: Invalid request body
components:
  schemas:
    NormalizeProductRequest:
      type: object
      required:
        - sku
        - displayName
      properties:
        sku:
          type: string
        displayName:
          type: string
    NormalizeProductResponse:
      type: object
      properties:
        sku:
          type: string
        displayName:
          type: string
~~~

This is an example of the desired contract. Actual generated documents may include additional metadata such as `servers`, `tags`, `security`, schema formats, and different responses depending on configuration. Always inspect the actual JSON/YAML rather than assuming annotations were processed as intended.

## 18. Testing HTTP Functions and OpenAPI

Test both layers: that the function is invoked properly over HTTP and that the OpenAPI document describes the endpoint accurately.

### Testing the Function with MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductFunctionHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void normalizesProduct() throws Exception {
        mockMvc.perform(post("/functions/normalizeProduct")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "sku": " p-001 ",
                      "displayName": " Ballpoint pen "
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sku").value("P-001"))
            .andExpect(jsonPath("$.displayName").value("Ballpoint pen"));
    }
}
~~~

The test assumes the application configured the function web path as `/functions`. If using the default path, call `/normalizeProduct`.

### Testing the OpenAPI Operation

~~~java
@Test
void exposesNormalizeProductOperation() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/functions/normalizeProduct'].post.operationId"
        ).value("products_normalize"))
        .andExpect(jsonPath(
            "$.paths['/functions/normalizeProduct'].post.requestBody.content['application/json'].schema"
        ).exists());
}
~~~

If the JSONPath implementation does not support expressions containing keys with slashes or dots, parse the OpenAPI object and assert directly in the test. Tests should verify `operationId`, method, path, request schema, and response schema.

### Testing Consumers and Suppliers

For a `Consumer`, verify both the status code and the side effect (such as a published event or saved record). For a `Supplier`, verify that GET returns data with the expected media type. Do not check only status `202`/`200` while ignoring the business outcome.

## 19. Reactive Functions and Multi-Item Responses

Spring Cloud Function supports functions using `Mono` and `Flux`. When a function returns multiple items, the HTTP adapter can return multi-valued data. Clients can request a server-sent event stream using `Accept: text/event-stream`.

Reactive function example:

~~~java
@Bean
Function<Flux<String>, Flux<String>> lowercase() {
    return values -> values.map(value -> value.toLowerCase(Locale.ROOT));
}
~~~

Client sending multiple lines of text:

~~~http
POST /lowercase
Content-Type: text/plain
Accept: text/event-stream

HELLO
WORLD
~~~

For multi-item output, `Accept: text/event-stream` requests an SSE representation if the endpoint and codecs support it. If clients want a plain JSON document, choose the appropriate media type and output type; do not infer response framing solely from `Flux`.

In OpenAPI, document the exact media type returned by the endpoint. For SSE, response content uses `text/event-stream` with a description explaining event framing. If the output is a JSON array, the schema should be `array` with `items` pointing to the element schema. If it is an event stream, do not document it as a complete JSON array.

~~~yaml
responses:
  '200':
    description: Event stream sent via Server-Sent Events
    content:
      text/event-stream:
        schema:
          type: string
~~~

Springdoc may need explicit response metadata when reactive generic types are insufficient to infer the representation. Verify actual `Content-Type` and body with tests, curl, or `WebTestClient` before finalizing the OpenAPI contract.

## 20. Security When Exposing Functions over HTTP

When using Spring Cloud Function Web, functions in the catalog can become HTTP endpoints. Therefore, control which functions are exposed and who is permitted to call them.

Principles:

- Export only needed functions; use `spring.cloud.function.definition` to restrict functions or compositions.
- Protect function endpoints with Spring Security, OAuth2 Resource Server, or an appropriate authentication mechanism.
- Apply authorization per function or API group; do not assume every function in the catalog is public.
- Protect `/actuator/functions` and other Actuator endpoints with a management security policy.
- Do not expose internal beans simply because they implement `Function`, `Supplier`, or `Consumer`.
- Enforce request body validation, payload size limits, rate limits, timeouts, and concurrency bounds.

### Be Careful with routing-expression

Spring Cloud Function supports routing via headers `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` in certain cases. `routing-expression` uses SpEL, and documentation warns that if untrusted users can pass expressions via HTTP headers, they can introduce arbitrary expression execution risks.

Never allow Internet clients to freely pass `routing-expression`. Prefer fixed routes by function name, an allowlist of exported functions, or build a router that checks function names against an allowed list. For reactive functions, routing instructions via message headers do not have the same per-message routing capability as imperative functions; check the rules of the version in use.

### OpenAPI Security Metadata Must Match Runtime

If an endpoint requires a Bearer token, declare the security scheme and security requirement in OpenAPI. However, annotations only describe documentation; Spring Security enforces authentication and authorization. If Swagger UI displays an endpoint as requiring no auth while runtime returns `401`/`403`, synchronize the security metadata.

Example security scheme declaration:

~~~java
@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class FunctionApiSecurityConfiguration {}
~~~

Attach the security requirement to operations via `@Operation(security = ...)`, or configure it at the OpenAPI document level if all functions share the same mechanism. If only certain functions require different permissions, set security requirements per operation and verify them against Spring Security matchers.

## 21. Limitations and Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Function does not appear over HTTP | Missing Spring Cloud Function Web or bean not registered | Check dependencies, ApplicationContext, and FunctionCatalog |
| Function path returns 404 | Path name does not match function name or web path prefix | Check `@Bean` name and `spring.cloud.function.web.path` |
| Request JSON not converted to DTO | Missing Content-Type or converter does not support input type | Send `application/json` and check generic types/converters |
| Function receives Map instead of DTO | Input type lost or declared as raw `Function`/`Object` | Declare explicit generics or register `FunctionRegistration` |
| OpenAPI missing function operation | Missing metadata or springdoc does not detect mapping | Use `@RouterOperation`/`@RouterOperations` and check web stack |
| Operation has wrong path or method | Metadata mismatches adapter mapping | Declare explicit path/method and inspect runtime document |
| Duplicate operationId | Multiple functions share the same `operationId` | Set unique `operationId` values across the document |
| Request/response schema is generic Object | Generic type lost or function uses `Message`/raw type | Provide `FunctionRegistration` types and `@Schema` implementation |
| Consumer documented with response object | Confusing `Consumer` with `Function` | Document 202/204 and actual side effects |
| Internal function exposed | Function catalog not filtered or missing security | Use `definition` allowlist and Spring Security |
| Header routing allows choosing arbitrary function | Trusting client-supplied function name/`routing-expression` | Validate against allowlist; do not accept arbitrary SpEL |
| Actuator functions leaks internal metadata | `functions` endpoint exposed publicly | Restrict to management port and require appropriate role |
| Swagger UI calls endpoint and gets 401/403 | OpenAPI security metadata or security matcher out of sync | Check scheme, scopes, and Spring Security chain |

## 22. Workflow for Integrating Spring Cloud Function Web with Springdoc

When adding OpenAPI documentation to function endpoints, follow this sequence:

1. Declare function beans with `Supplier`, `Function`, or `Consumer` and concrete input/output generics.
2. Add Spring Cloud Function Web and manage versions with a compatible Spring Cloud BOM.
3. Identify the actual web stack; choose the matching springdoc webmvc or webflux starter.
4. Choose the API-only starter or UI starter based on how documentation is distributed.
5. Determine function names, HTTP paths, methods, and prefixes.
6. Use `@RouterOperation` for a single operation or `@RouterOperations` for multiple operations.
7. Set unique `operationId`s; declare request body, response statuses, media types, tags, and schemas.
8. Use `FunctionRegistration` if runtime cannot infer generic input/output types.
9. Use `OpenApiCustomizer` for standardized or computed metadata.
10. Restrict exported functions and protect endpoints with Spring Security.
11. Test HTTP functions, content negotiation, and OpenAPI JSON/YAML.
12. Compare the generated contract against actual requests/responses before release.

Spring Cloud Function Web provides an adapter to turn function beans into HTTP endpoints. `FunctionCatalog` and `FunctionRegistration` manage functions alongside type metadata; springdoc uses OpenAPI metadata to describe operations for clients. When both layers are declared consistently, teams can reuse functional business logic while still delivering a clear, testable, and client-generatable API contract.

## 23. References

- [Spring Cloud Function 5.0.5 – Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html): exposing Supplier, Function, and Consumer over HTTP; path, method, content type, function mapping, and filtering.
- [Spring Cloud Function – Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): FunctionCatalog, Function/Consumer/Supplier, Message, headers, and function composition.
- [Spring Cloud Function – Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/docs/current/reference/html/functional.html): FunctionRegistration and input/output type metadata.
- [Spring Cloud Function – Reference Documentation](https://docs.spring.io/spring-cloud-function/reference/index.html): versions, modules, and integration guides.
- [Springdoc OpenAPI – Spring Cloud Function Web support](https://springdoc.org/modules.html#spring-cloud-function-web-support): springdoc starters, `@RouterOperation`, `@RouterOperations`, and `OpenApiCustomizer`.
- [Springdoc OpenAPI – Features](https://springdoc.org/features.html#spring-webfluxwebmvc-fn-with-functional-endpoints): metadata for functional endpoints and operation mapping.
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): operationId, summary, parameters, requestBody, and responses.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): schemas for requests and responses.
