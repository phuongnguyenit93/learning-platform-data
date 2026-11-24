# Changing Response or Hidden Annotations with the Correct Package and Context

When migrating an API from SpringFox/Swagger 2 to springdoc-openapi/OpenAPI 3, two annotation groups that frequently cause import errors or inaccurate descriptions are **response** and **hidden**. Annotation names may look similar, yet their packages, attributes, and applicable scopes are not completely identical.

With OpenAPI 3, the annotation describing a response is **io.swagger.v3.oas.annotations.responses.ApiResponse**; the annotation hiding a resource is **io.swagger.v3.oas.annotations.Hidden**. Choose the annotation matching the exact target being described: an operation's response, an entire controller, a single operation, a single parameter, or a schema property.

One distinction to keep in mind throughout this guide: Swagger annotations describe the contract in the OpenAPI document. Spring annotations such as **@ResponseStatus** and **ResponseEntity** are what actually control the controller's runtime HTTP response.

## 1. Identify the right annotation packages

Common OpenAPI 3 annotations used in Spring controllers:

| Annotation | Correct package | Purpose |
| --- | --- | --- |
| @ApiResponse | io.swagger.v3.oas.annotations.responses.ApiResponse | Describe a response code and body |
| @ApiResponses | io.swagger.v3.oas.annotations.responses.ApiResponses | Group multiple responses for an operation |
| @Operation | io.swagger.v3.oas.annotations.Operation | Describe an operation and its metadata |
| @Hidden | io.swagger.v3.oas.annotations.Hidden | Hide a controller, method, or bean from documentation |
| @Parameter | io.swagger.v3.oas.annotations.Parameter | Describe a parameter; can hide a single parameter |
| @Content | io.swagger.v3.oas.annotations.media.Content | Describe media type and content schema |
| @Schema | io.swagger.v3.oas.annotations.media.Schema | Describe or hide a schema/model/property |

Do not confuse @Parameter with @RequestBody: @Parameter sits in the root io.swagger.v3.oas.annotations package, whereas the OpenAPI @RequestBody annotation lives in io.swagger.v3.oas.annotations.parameters. Spring also has org.springframework.web.bind.annotation.RequestBody to bind an HTTP body to a Java parameter.

The two key packages to remember for this topic:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.Hidden;
~~~

@ApiResponse is not directly inside io.swagger.v3.oas.annotations. @Hidden is not inside responses, media, or the internal org.springdoc package.

## 2. Distinguish Swagger 2 ApiResponse and OpenAPI 3 ApiResponse

In Swagger 2/SpringFox, the annotation is typically imported from:

~~~java
import io.swagger.annotations.ApiResponse;
import io.swagger.annotations.ApiResponses;
~~~

Old example:

~~~java
@ApiResponses({
    @ApiResponse(code = 201, message = "Created"),
    @ApiResponse(code = 400, message = "Invalid request")
})
~~~

When switching to OpenAPI 3, use the new package and attributes:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@ApiResponses({
    @ApiResponse(responseCode = "201", description = "Created"),
    @ApiResponse(responseCode = "400", description = "Invalid request")
})
~~~

Differences to note:

| Swagger 2 | OpenAPI 3 |
| --- | --- |
| io.swagger.annotations.ApiResponse | io.swagger.v3.oas.annotations.responses.ApiResponse |
| code = 201 is an integer | responseCode = "201" is a string |
| message = "Created" | description = "Created" |
| response = Order.class | content = @Content(schema = @Schema(implementation = Order.class)) |
| responseContainer | Describe structure with the appropriate schema/array schema |

Do not just fix the package name while keeping old attributes. OpenAPI 3 uses responseCode, description, and content to describe a response. Swagger 2's response attribute is no longer how schemas are declared in OpenAPI 3 annotations.

## 3. Declare a single response with @ApiResponse

@ApiResponse describes one possible response when an operation is invoked. Fields typically declared include:

- responseCode: HTTP status code as a string, such as "200", "201", "400", "404", or "default".
- description: meaning of the response.
- content: media type and schema of the response body.
- headers: response headers if they need to be documented.
- ref: reference to a shared response component when appropriate.

Example of a successful JSON response:

~~~java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Order retrieved successfully",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Order not found"
    )
})
~~~

@Schema(implementation = OrderResponse.class) indicates the response body follows the OrderResponse model structure. If the controller returns multiple content types, declare each corresponding media type inside content.

When a method returns a DTO whose schema springdoc already infers accurately, there is no need to repeat metadata for the success response just to restate the return type. Add @ApiResponse when you need to specify status codes, business descriptions, error responses, headers, or custom content.

## 4. Declare multiple responses with @ApiResponses

@ApiResponses is a container that groups multiple @ApiResponse annotations on an operation. In OpenAPI 3 swagger-annotations, @ApiResponse is also repeatable, though the wrapper helps keep response codes readable and easy to review.

Order creation endpoint example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;

@PostMapping("/api/orders")
@ResponseStatus(HttpStatus.CREATED)
@Operation(summary = "Create order")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order created",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request payload",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiErrorResponse.class)
        )
    )
})
public OrderResponse createOrder(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

In this example:

- @Operation describes the operation.
- @ApiResponses lists possible responses.
- @ResponseStatus(HttpStatus.CREATED) sets the actual HTTP status for the method's success path.
- @RequestBody here is the Spring MVC annotation to bind the JSON request body, not OpenAPI's parameters.RequestBody annotation.

Types OrderResponse, ApiErrorResponse, CreateOrderRequest, and orderService are application models/services.

You can place @ApiResponse directly inside @Operation.responses:

~~~java
@Operation(
    summary = "Get order by ID",
    responses = {
        @ApiResponse(
            responseCode = "200",
            description = "Success",
            content = @Content(
                schema = @Schema(implementation = OrderResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Not found"
        )
    }
)
~~~

Choose one consistent style per operation. Avoid declaring the same status code multiple times in both @Operation.responses and @ApiResponses unintentionally, as documentation can become hard to read or get overwritten during aggregation.

## 5. Describing a response does not control HTTP status

This is a common point of confusion when migrating response annotations. @ApiResponse only documents the OpenAPI spec. It does not set the HTTP status when the controller runs.

Conversely, @ResponseStatus belongs to Spring MVC:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.CREATED)
~~~

This annotation tells Spring to set the response status when the handler executes. Another option is returning ResponseEntity:

~~~java
return ResponseEntity
    .status(HttpStatus.CREATED)
    .body(orderResponse);
~~~

Comparison:

| Component | Role | Directly controls runtime response? |
| --- | --- | --- |
| @ApiResponse(responseCode = "201") | Documents 201 response in OpenAPI | No |
| @ResponseStatus(HttpStatus.CREATED) | Sets status on handler response | Yes |
| ResponseEntity.status(...).body(...) | Sets status, headers, and body when returning response | Yes |
| @Operation | Describes operation | No |

If the documentation says 201 while the controller actually returns 200, OpenAPI misrepresents the behavior. If the controller returns 201 while documentation only mentions 200, client generators and readers also receive an inaccurate contract. Both layers must stay aligned.

Do not replace @ResponseStatus with @ApiResponse, and do not add @ResponseStatus merely because you declared responseCode. Pick the HTTP control mechanism that fits the implementation, then document that result with OpenAPI.

## 6. Responses without a body

For an endpoint returning 204 No Content, document an empty response:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "Order deleted",
    content = @Content
)
~~~

Do not declare a body schema for a 204 response if the server genuinely sends no body. If an endpoint returns a JSON body, declare the matching media type and schema rather than documenting an empty response.

Similarly, a 404 response can have only a description if the API truly sends no body. If the application returns ProblemDetail or ApiErrorResponse, declare the error schema so clients know the data structure.

## 7. Choose the right package when migrating to @Hidden

In SpringFox, the annotation commonly used to ignore resources is:

~~~java
import springfox.documentation.annotations.ApiIgnore;
~~~

With springdoc/OpenAPI 3, the @Hidden annotation resides at:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
~~~

There is no io.swagger.v3.oas.annotations.responses.Hidden package. @Hidden is not a response annotation; it marks a resource, class, method, or bean type to be excluded from documentation scanning/generation.

You can use the fully qualified name to avoid wrong imports:

~~~java
@io.swagger.v3.oas.annotations.Hidden
~~~

The springdoc FAQ confirms @Hidden can be used on @RestController, @RestControllerAdvice, and at the method level. For a specific operation, @Operation(hidden = true) is also a suitable choice.

## 8. Choose hidden with the right scope

Do not replace every @ApiIgnore with a single @Hidden. First determine what the old annotation intended to hide:

| Target to hide | Appropriate OpenAPI 3 annotation |
| --- | --- |
| Entire controller/resource | @Hidden on the class |
| Entire @RestControllerAdvice from docs | @Hidden on the advice class |
| Single method/operation | @Hidden on the method or @Operation(hidden = true) |
| Single parameter | @Parameter(hidden = true) |
| Field/property in a model | @Schema(hidden = true) |
| Schema of a specific response | @Schema(hidden = true) inside that response's @Content, if intentionally omitting the body schema |

These annotations have distinct scopes. Hiding a parameter does not hide the operation. Hiding a schema property does not hide the endpoint. Hiding a controller excludes every operation in that controller from documentation.

## 9. Hide an entire controller

When a controller is internal and should not appear in the OpenAPI document, place @Hidden at the class level:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/maintenance")
class MaintenanceController {

    // Internal endpoints are omitted from the OpenAPI document.
}
~~~

Place the annotation on the class to apply it to the entire controller. There is no need to repeat it on each method if all endpoints in the class should be hidden.

Note: @Hidden only hides documentation. Endpoints can still be registered by Spring and accessed over HTTP. If an internal route needs protection, configure Spring Security, network policies, or the appropriate authorization mechanism.

## 10. Hide one operation while keeping others

If a controller mixes public APIs and internal diagnostic endpoints, hide only the required method:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    public List<OrderResponse> listOrders() {
        return orderService.findAll();
    }

    @GetMapping("/internal/order-cache")
    @Operation(hidden = true)
    public Map<String, Integer> inspectCache() {
        return orderService.cacheStatistics();
    }
}
~~~

In this case, /api/orders still appears in OpenAPI; /internal/order-cache is hidden. You can also place @Hidden directly on the method:

~~~java
@Hidden
@GetMapping("/internal/order-cache")
public Map<String, Integer> inspectCache() {
    return orderService.cacheStatistics();
}
~~~

@Operation(hidden = true) expresses intent at the Operation Object level. @Hidden works well when marking a method/resource excluded from documentation scanning. Pick one style and keep it consistent within a module.

## 11. Hide a parameter from documentation

A method may accept parameters for Spring Security or infrastructure rather than values sent over HTTP by clients. For instance, @AuthenticationPrincipal is injected by Spring from the security context.

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/me")
public UserResponse getCurrentUser(
    @Parameter(hidden = true)
    @AuthenticationPrincipal CurrentUser currentUser
) {
    return userService.toResponse(currentUser);
}
~~~

Here only the currentUser parameter is hidden. The /api/me operation remains visible and other query/path parameters remain documented.

Do not place @Hidden on the method if you only want to hide one parameter. Putting @Hidden on the method can exclude the entire operation from documentation.

## 12. Hide a schema field or property

If a model contains an internal field that should not appear in the OpenAPI schema, use @Schema(hidden = true):

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record UserResponse(
    String id,
    String displayName,
    @Schema(hidden = true)
    String internalRiskScore
) {}
~~~

This annotation applies to the schema property. It does not hide the entire endpoint and does not automatically remove the field from Jackson JSON serialization.

If the field must also be omitted from runtime JSON, configure the model/serializer appropriately, such as @JsonIgnore or a separate response DTO. @Schema(hidden = true) affects only OpenAPI documentation; @JsonIgnore affects Jackson serialization/deserialization.

## 13. Hide the schema of a specific response

The springdoc FAQ shows using @Schema(hidden = true) inside @Content when hiding a response schema:

~~~java
@Operation(
    responses = @ApiResponse(
        responseCode = "200",
        description = "Success",
        content = @Content(
            schema = @Schema(hidden = true)
        )
    )
)
~~~

This hides the response body schema. It differs from:

- @Operation(hidden = true): hides the entire operation.
- @Hidden on the controller: hides the entire controller.
- @Parameter(hidden = true): hides a parameter.

Use this approach only when intentionally omitting the body schema structure. If clients need the JSON response structure to integrate, document the schema instead of hiding it.

## 14. Hide ControllerAdvice and exception handlers

springdoc can scan @ControllerAdvice to aggregate error responses into documentation. If an advice exists purely for internal handling or should not contribute responses to OpenAPI, place @Hidden on the class:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.ControllerAdvice;

@Hidden
@ControllerAdvice
class InternalExceptionAdvice {
    // Internal exception handlers.
}
~~~

If only one exception handler should be excluded from generic error responses, place @Hidden on that handler method. The springdoc FAQ notes that annotations on exception handlers are considered when building generic responses from @ControllerAdvice.

Do not hide the entire advice if error responses required by public APIs are generated from the same advice. Check the OpenAPI document after making changes to confirm public error responses remain present.

## 15. Map @ApiIgnore to OpenAPI 3 annotations

@ApiIgnore in legacy code may have been placed in several locations. When converting, check its placement and intent first:

| Old @ApiIgnore placement | Suggested replacement |
| --- | --- |
| On a controller | @Hidden on the class |
| On a method/operation | @Hidden on the method or @Operation(hidden = true) |
| On a parameter | @Parameter(hidden = true) |

Old example:

~~~java
@ApiIgnore
@RestController
class InternalController {
}
~~~

After conversion:

~~~java
@Hidden
@RestController
class InternalController {
}
~~~

Old parameter hiding example:

~~~java
public UserResponse currentUser(@ApiIgnore CurrentUser user) {
    // ...
}
~~~

After conversion:

~~~java
public UserResponse currentUser(
    @Parameter(hidden = true) CurrentUser user
) {
    // ...
}
~~~

Do not mechanically convert every occurrence into @Hidden. Doing so can accidentally hide an entire endpoint when only a single parameter needed hiding.

Note: SpringFox @ApiIgnore targets only methods, types, and parameters. If old code used @ApiModelProperty(hidden = true) to hide a model property, convert that case separately to @Schema(hidden = true); that is a migration from a model property annotation, not from @ApiIgnore.

## 16. Distinguish SpringFox-to-springdoc migration from springdoc v1-to-v2 migration

These two upgrade paths are often conflated:

**SpringFox/Swagger 2 to springdoc/OpenAPI 3:** switches the annotation system from Swagger 2 to Swagger 3. For instance, @ApiResponse moves to io.swagger.v3.oas.annotations.responses, @ApiIgnore is replaced by scoped hidden annotations, and @ApiOperation becomes @Operation.

**springdoc v1 to springdoc v2:** springdoc changed starter/module names and several internal classes/annotations. Swagger 3 annotations like @ApiResponse and @Hidden remain in io.swagger.v3.oas.annotations...; they do not move to org.springdoc.

Some internal springdoc packages that changed between v1 and v2:

| springdoc v1 | springdoc v2 |
| --- | --- |
| org.springdoc.api.annotations.ParameterObject | org.springdoc.core.annotations.ParameterObject |
| org.springdoc.core.GroupedOpenApi | org.springdoc.core.models.GroupedOpenApi |
| org.springdoc.core.customizers.OpenApiCustomiser | org.springdoc.core.customizers.OpenApiCustomizer |
| org.springdoc.core.SpringDocUtils | org.springdoc.core.utils.SpringDocUtils |
| org.springdoc.core.Constants | org.springdoc.core.utils.Constants |
| org.springdoc.core.SwaggerUiConfigParameters | org.springdoc.core.properties.SwaggerUiConfigParameters |

Do not apply these internal package changes to @ApiResponse, @ApiResponses, @Hidden, @Operation, @Parameter, or @Schema. They are swagger-core annotations, not internal springdoc classes.

## 17. Update starters when upgrading springdoc v1 to v2

springdoc v2 is designed for Spring Boot 3.x. Starters and modules were also renamed:

| springdoc v1 | springdoc v2 |
| --- | --- |
| springdoc-openapi-ui | springdoc-openapi-starter-webmvc-ui |
| springdoc-openapi-webflux-ui | springdoc-openapi-starter-webflux-ui |
| springdoc-openapi-webmvc-core | springdoc-openapi-starter-webmvc-api |
| springdoc-openapi-webflux-core | springdoc-openapi-starter-webflux-api |
| springdoc-openapi-common | springdoc-openapi-starter-common |

Maven example for a Spring MVC application needing Swagger UI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

If you only need OpenAPI endpoints without Swagger UI, use the API starter matching your stack. With WebFlux, select the corresponding WebFlux starter. Do not add both MVC and WebFlux starters at the same time if the application runs a single web stack.

When upgrading from Spring Boot 2 to Spring Boot 3, you also need to handle Spring Framework 6/Jakarta changes such as javax.* to jakarta.* for the relevant Java EE APIs. The Jakarta package change does not alter swagger-core annotation packages.

## 18. Avoid confusing the ApiResponse model and annotation

In addition to the annotation, swagger-core has a model class with the same name:

~~~java
io.swagger.v3.oas.annotations.responses.ApiResponse
io.swagger.v3.oas.models.responses.ApiResponse
~~~

These two types serve different purposes:

| Type | What is it? | Where is it used? |
| --- | --- | --- |
| io.swagger.v3.oas.annotations.responses.ApiResponse | Java annotation | Placed on controller methods/types or inside @Operation |
| io.swagger.v3.oas.models.responses.ApiResponse | OpenAPI model object | Creates/modifies responses in Java code inside customizers/beans |

If a Java file needs both types, Java does not allow importing two classes with the same simple name. Import the more frequently used one and use the fully qualified name for the other:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;

io.swagger.v3.oas.models.responses.ApiResponse responseModel =
    new io.swagger.v3.oas.models.responses.ApiResponse()
        .description("Success");
~~~

Likewise, do not confuse @ApiResponse with Spring's @ResponseStatus. Their names are somewhat close, but their packages and responsibilities are completely different.

## 19. Check dependencies and old imports

If code fails to compile or annotations are ignored by springdoc:

1. Check imports at the top of controller and DTO files.
2. Search for leftover io.swagger.annotations.* imports from Swagger 2.
3. Inspect the dependency tree for old springfox or swagger-annotations versions still on the classpath.
4. Confirm the springdoc starter matches Spring MVC/WebFlux and your Spring Boot version.
5. Use the Swagger 3 annotations supplied by the starter; avoid mixing Swagger 2 and OpenAPI 3 annotations on the same controller.

Common diagnostic clues:

| Error | Common cause |
| --- | --- |
| responseCode does not exist | Importing Swagger 2 io.swagger.annotations.ApiResponse |
| code or message does not exist | Importing OpenAPI 3 ApiResponse while still using Swagger 2 attributes |
| Cannot find @Hidden | Wrong package imported or missing compatible swagger-annotations |
| @Hidden does not hide parameter as expected | Used annotation at the wrong scope; use @Parameter(hidden = true) |
| Entire endpoint disappeared | Placed @Hidden at the controller level instead of parameter/operation |
| Documentation says 201 but request returns 200 | Only declared @ApiResponse without configuring runtime status |
| Response schema disappeared | Unintentionally placed @Schema(hidden = true) on response content or DTO |

## 20. Test response and hidden annotations in the OpenAPI document

After updating annotations, verify the JSON generated by springdoc. By default the endpoint is typically /v3/api-docs.

Example checking the 201 response:

~~~bash
curl --fail --silent --show-error http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/orders"].post.responses'
~~~

Verify hidden operations are absent from the document:

~~~bash
curl --fail --silent --show-error http://localhost:8080/v3/api-docs \
  | jq '.paths | keys'
~~~

You can write an integration test with MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiAnnotationMigrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsCreatedResponseAndHidesInternalOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.paths['/api/orders'].post.responses['201'].description"
            ).value("Order created"))
            .andExpect(jsonPath(
                "$.paths['/internal/maintenance']"
            ).doesNotExist());
    }
}
~~~

If only a parameter is hidden, verify the operation still exists and that parameter does not appear in parameters. If only a schema property is hidden, verify the endpoint and other public properties are still generated.

Also verify runtime HTTP behavior separately:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerId":"c-100"}
            """))
    .andExpect(status().isCreated());
~~~

Documentation tests verify @ApiResponse; runtime tests verify Spring returns the right status and body. Do not merge both goals into a single assertion.

## 21. Common pitfalls during migration

**Keeping io.swagger.annotations.ApiResponse imports.** That is Swagger 2. Replace with io.swagger.v3.oas.annotations.responses.ApiResponse.

**Putting @Hidden in the responses package.** @Hidden lives in the root package io.swagger.v3.oas.annotations.

**Using @Hidden to hide a parameter.** Choose @Parameter(hidden = true) so the operation stays visible.

**Using @Operation(hidden = true) on a controller class.** That annotation targets operation methods. To hide an entire controller, place @Hidden on the class.

**Replacing every @ApiIgnore with @Hidden.** Check whether the old annotation was on a class, method, parameter, or property, and choose the matching annotation.

**Using @ApiResponse(code = 201, message = "...") in OpenAPI 3.** Change to responseCode = "201" and description = "...".

**Using @ApiResponse to force an HTTP 201 status.** Configure @ResponseStatus or ResponseEntity at runtime.

**Replacing response annotations but forgetting content schemas.** If the body has a JSON/XML model to publish, document content and schema.

**Hiding a schema with @Schema(hidden = true) even though clients need the response.** Only hide when intentionally omitting body structure; otherwise keep the schema public.

**Upgrading springdoc v1 to v2 and moving all annotations to org.springdoc.** Only the internal springdoc classes listed in the migration guide changed packages; swagger-core annotations continue using io.swagger.v3.oas.annotations.

**A hidden endpoint is still reachable and assuming @Hidden failed.** @Hidden affects documentation only, not route security.

## 22. Pre-completion migration checklist

- [ ] Using io.swagger.v3.oas.annotations.responses.ApiResponse.
- [ ] Using io.swagger.v3.oas.annotations.responses.ApiResponses.
- [ ] Using string responseCode and description, not Swagger 2's code/message.
- [ ] Documenting response bodies with content and @Schema(implementation = ...) when needed.
- [ ] Using io.swagger.v3.oas.annotations.Hidden from the right package.
- [ ] Choosing @Hidden, @Operation(hidden = true), @Parameter(hidden = true), or @Schema(hidden = true) at the right scope.
- [ ] Distinguishing OpenAPI annotations from @ResponseStatus and ResponseEntity.
- [ ] Not confusing the ApiResponse annotation with the io.swagger.v3.oas.models.responses.ApiResponse model.
- [ ] Removed leftover old Swagger 2 imports.
- [ ] When upgrading springdoc v1 to v2, updated starters and changed only the internal packages listed in the migration guide.
- [ ] Verified OpenAPI JSON after building.
- [ ] Verified actual HTTP status/body with separate integration tests.
- [ ] Verified hidden endpoints remain protected by security if they are internal endpoints.

## 23. Conclusion

When migrating response annotations, use io.swagger.v3.oas.annotations.responses.ApiResponse and declare responseCode, description, and content per OpenAPI 3. When migrating ignore annotations, choose @Hidden for resources/controllers or methods, @Operation(hidden = true) for operations, @Parameter(hidden = true) for parameters, and @Schema(hidden = true) for properties/schemas. Do not confuse response documentation annotations with @ResponseStatus, which controls actual HTTP responses. Finally, inspect imports, starters, OpenAPI JSON, and runtime responses to confirm the documentation accurately reflects the application.

## 24. References

- [springdoc-openapi — Migrating from v1 to v2](https://springdoc.org/v2/migrating-from-springdoc-v1.html): modules, classes, and internal packages that changed between springdoc v1 and v2.
- [springdoc-openapi — Migrating from SpringFox](https://springdoc.org/v1/migrating-from-springfox.html): mapping Swagger 2 annotations to OpenAPI 3, including @ApiResponse and @ApiIgnore.
- [springdoc-openapi v2 — Migrating from SpringFox](https://springdoc.org/v2/migrating-from-springfox.html): mapping Swagger 2 annotations to OpenAPI 3 for Spring Boot 3.
- [SpringFox — ApiIgnore Javadoc](https://springfox.github.io/springfox/javadoc/current/springfox/documentation/annotations/ApiIgnore.html): package and method, type, and parameter targets of @ApiIgnore.
- [springdoc-openapi v2 FAQ — Hide operation/controller](https://springdoc.org/v2/faq.html): scope of @Hidden, @Operation(hidden = true), and @Parameter(hidden = true).
- [springdoc-openapi v2 FAQ — Hide response schema](https://springdoc.org/v2/faq.html): example of @Schema(hidden = true) inside response content.
- [swagger-core — ApiResponse annotation](https://docs.swagger.io/swagger-core/v2.2.27/apidocs/io/swagger/v3/oas/annotations/responses/ApiResponse.html): package, responseCode/description/content attributes, and annotation scope.
- [swagger-core — Hidden annotation](https://docs.swagger.io/swagger-core/v2.2.27/apidocs/io/swagger/v3/oas/annotations/Hidden.html): package and applicable scope of @Hidden.
- [Spring Framework — ResponseStatus](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html): runtime behavior of @ResponseStatus.
