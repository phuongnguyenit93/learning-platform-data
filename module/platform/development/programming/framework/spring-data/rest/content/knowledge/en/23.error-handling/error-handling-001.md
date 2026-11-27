# RepositoryRestExceptionHandler Mechanism and Exception Handling Scope

Spring Data REST has an exception handling mechanism for the controllers that the framework uses to export Spring Data repositories as REST resources. The central component is \`RepositoryRestExceptionHandler\`, a Spring MVC \`@ControllerAdvice\` provided by Spring Data REST.

It is important to understand the scope of this handler correctly. It helps convert errors occurring in the Spring Data REST processing flow into appropriate HTTP responses. It is not a global exception handler for every controller, service, background job, or security error across the entire application.

## 1. What is RepositoryRestExceptionHandler?

The class has the fully qualified name:

~~~java
org.springframework.data.rest.webmvc.RepositoryRestExceptionHandler
~~~

Spring Data REST registers this class as a controller advice. The current Javadoc API shows the selector:

~~~java
@ControllerAdvice(basePackageClasses = RepositoryRestExceptionHandler.class)
public class RepositoryRestExceptionHandler {
    // Framework exception handling methods.
}
~~~

Two noteworthy points:

- This is a component managed and provided out of the box by Spring Data REST. The application does not need to instantiate or call this class directly.
- \`basePackageClasses\` restricts the advice to the package containing the specified class. The purpose of this class is to handle exceptions for Spring Data REST controllers.

When a request passes through a Spring Data REST controller and throws an exception within the framework's handling scope, the handler can convert the exception into an appropriate HTTP status and response body. As a result, the client receives an HTTP error instead of having to handle Java exceptions directly.

You should not rely on the internal implementation details of the framework class as a business API. If the application needs a stable custom error code or payload, define an error contract at the application layer and add a handler with a clear scope.

## 2. Where does a request go before an exception is handled?

A request to a repository resource typically goes through the following general steps:

~~~text
HTTP request
     |
     v
Spring MVC DispatcherServlet
     |
     v
Spring Data REST HandlerMapping
     |
     v
Spring Data REST repository controller
     |
     v
Repository / conversion / validation / persistence
     |
     +---- success ----> HTTP response
     |
     +---- exception ----> HandlerExceptionResolver
                              |
                              v
                     RepositoryRestExceptionHandler
                              |
                              v
                     HTTP status + error response
~~~

The diagram shows that the exception handler is part of the MVC request-processing pipeline. It does not catch every error that occurs anywhere in the JVM.

For example, if a repository REST endpoint tries to convert a string into an invalid data type, or a save operation encounters a data constraint violation, the exception can be handled in the Spring Data REST pipeline. Conversely, an error occurring in a scheduled job without an HTTP request has no HTTP response for this handler to convert.

## 3. Handling scope: Spring Data REST controllers

The API Javadoc describes \`RepositoryRestExceptionHandler\` as the exception handler for Spring Data REST controllers. This scope is tied to controllers and request mappings belonging to Spring Data REST.

Typical cases within scope:

- Requests to collection resources exported from repositories.
- Requests to item resources such as GET, PUT, PATCH, or DELETE.
- Requests to exported finder/search resources.
- Requests to association resources managed by Spring Data REST.
- Custom endpoints integrated into Spring Data REST using \`@RepositoryRestController\`.

Do not interpret this scope as "all code using a Spring Data repository". Having a service call the same repository interface does not automatically turn that call into a Spring Data REST request.

## 4. Distinguishing @RepositoryRestController and @RestController

This is a very important boundary when adding custom endpoints.

### @RepositoryRestController

Use \`@RepositoryRestController\` when a custom endpoint needs to participate in the Spring Data REST environment. The controller is served under the API base path configured in \`RepositoryRestConfiguration.setBasePath\` and can leverage Spring Data REST's configuration, message converters, exception handling, and integrations.

~~~java
@RepositoryRestController
class ProductOperationsController {

    private final ProductRepository repository;

    ProductOperationsController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/products/search/active")
    ResponseEntity<?> findActiveProducts() {
        return ResponseEntity.ok(repository.findByActiveTrue());
    }
}
~~~

This example illustrates a custom endpoint placed in Spring Data REST's URI space. When returning a HAL representation, use appropriate Spring HATEOAS types such as \`EntityModel\` or \`CollectionModel\`, and generate links according to the API configuration.

### @RestController

A regular Spring MVC controller:

~~~java
@RestController
@RequestMapping("/internal/reports")
class ReportController {

    @GetMapping
    List<ReportDto> getReports() {
        // Handle a regular MVC endpoint.
        return List.of();
    }
}
~~~

If you use a regular \`@Controller\` or \`@RestController\` for an application endpoint, that endpoint lies outside the Spring Data REST integration scope, including the framework's request handling, message converters, and exception handling.

This endpoint can still be handled by standard Spring MVC exception handling mechanisms, such as \`@ExceptionHandler\` inside the controller or an application-defined \`@ControllerAdvice\` / \`@RestControllerAdvice\`. Simply do not assume it will receive the same behavior as \`RepositoryRestExceptionHandler\`.

| Endpoint type | Appropriate mechanism |
|---|---|
| Auto-exported repository resource | Spring Data REST controller and \`RepositoryRestExceptionHandler\` |
| Custom endpoint needing Spring Data REST integration | \`@RepositoryRestController\` |
| Regular MVC endpoint | \`@RestController\` / \`@Controller\` and application exception advice |
| Directly invoked service | Exception handling in the caller or business layer |
| Scheduled job / message consumer | Background job error handling mechanism |
| Authentication / authorization in the security filter chain | Spring Security configuration such as \`AuthenticationEntryPoint\` and \`AccessDeniedHandler\` |

## 5. Common errors in repository REST

The framework's default handler processes exceptions appropriate to the Spring Data REST flow and maps them to HTTP responses. Depending on the error type and Spring Data REST version, the exact status and body may vary.

Error categories that commonly need analysis include:

| Error category | Example | Common HTTP meaning |
|---|---|---|
| Resource not found | Item URI does not exist | 404 Not Found |
| Invalid request | Malformed JSON, unconvertible data type | 400 Bad Request |
| Unsupported method | Calling an HTTP method not supported by the endpoint | 405 Method Not Allowed |
| Unsupported media type | Incompatible Content-Type or Accept | 415 Unsupported Media Type or 406 Not Acceptable depending on the situation |
| Data constraint violation | Unique constraint or foreign key constraint | May be 409 Conflict or another status depending on mapping |
| Update conflict | Optimistic locking failure | Usually represents a conflict, though version-specific mapping should be checked |
| Unexpected error | Null pointer or programming bug | Usually 500 Internal Server Error |

The table above is a guide for HTTP error classification, not a guarantee that every exception class always maps one-to-one to the listed status. Test the actual mapping in the Spring Data REST version your application uses.

Some errors are also handled at other layers before reaching controller advice:

- Request parsing or data conversion errors may occur during body/parameter binding.
- Validation errors may be detected through Spring Data REST validators and validation mechanisms.
- User authentication and authorization errors may be intercepted in the Spring Security filter chain before the controller runs.
- Response serialization errors may occur after controller logic has completed.

Therefore, when an error does not enter \`RepositoryRestExceptionHandler\`, check request mapping, the filter chain, binding, validation, and serialization before concluding the handler is broken.

## 6. Adding a custom exception handler for business logic

Applications often need to return stable error codes for specific domain scenarios, such as an existing product code or an order state that does not allow transition.

You can define a custom exception:

~~~java
public class DuplicateProductCodeException extends RuntimeException {

    public DuplicateProductCodeException(String code) {
        super("Product code already exists: " + code);
    }
}
~~~

Then define the application's error response:

~~~java
public record ApiError(
        String code,
        String message
) {}
~~~

And register an advice scoped to custom Spring Data REST controllers:

~~~java
@RestControllerAdvice(annotations = RepositoryRestController.class)
public class RepositoryApiExceptionHandler {

    @ExceptionHandler(DuplicateProductCodeException.class)
    public ResponseEntity<ApiError> handleDuplicateCode(
            DuplicateProductCodeException exception) {

        ApiError body = new ApiError(
                "PRODUCT_CODE_DUPLICATE",
                "Product code already exists."
        );

        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
~~~

The example above illustrates how to scope a custom advice to controllers annotated with \`@RepositoryRestController\`. If you want to scope by package, you can use \`basePackageClasses\` with a marker class belonging to the package containing the target controllers:

~~~java
@RestControllerAdvice(basePackageClasses = RepositoryApiMarker.class)
public class RepositoryApiExceptionHandler {
    // Application @ExceptionHandler methods.
}
~~~

Choose the selector based on the scope actually needed. An advice without a selector can apply more broadly than intended to many controllers in the application.

### Should you override RepositoryRestExceptionHandler?

Usually, there is no need to recreate or subclass the framework's internal class. Add a \`@ControllerAdvice\` / \`@RestControllerAdvice\` for the application's business exceptions.

When multiple advices can handle the same exception, handler precedence and specificity affect the result. You can use \`@Order\` when you need to determine the order between advices, but avoid broad catch-all handlers for every \`Exception\` with overlapping scopes.

Some principles:

- Only catch exceptions that the handler is actually responsible for.
- Prefer handling specific domain exceptions before general exceptions.
- Never return HTTP 200 for a failed request.
- Do not expose stack traces, SQL, table names, tokens, or sensitive data in the response.
- Keep a stable response contract with a machine-readable \`code\` and a client-safe \`message\`.
- Log on the server with a correlation/request ID for detailed investigation.

## 7. Distinguishing HTTP exception handling from transaction rollback

A common misconception is that a handler converting an exception into an HTTP response decides whether the database commits or rolls back.

The two mechanisms have different responsibilities:

- The exception handler decides how an exception is represented as an HTTP status and response body.
- The transaction manager decides to commit or roll back based on transaction boundaries, exception types, rollback rules, and propagation.

For example, a service may have already committed a transaction and then encountered an error while serializing the response. The handler may return HTTP 500, but the committed data is not automatically reverted.

Similarly, if a custom exception handler catches an exception and returns a success response, the transaction might not receive an error signal to roll back. Do not use changing the status in a controller advice as a transaction control mechanism.

When you need to ensure a transaction fails if business logic is invalid, let the appropriate exception propagate out of the transactional boundary or configure explicit rollback rules. Test both the HTTP response and the persisted data after the request.

## 8. Distinguishing HTTP errors from Security errors

Spring Security typically handles authentication and authorization in the filter chain before a request reaches the controller.

Two common error types:

- 401 Unauthorized: the request lacks valid authentication credentials or is not authenticated as required.
- 403 Forbidden: the user is authenticated but does not have permission to perform the operation.

These responses are typically configured via \`AuthenticationEntryPoint\` and \`AccessDeniedHandler\`, depending on the security configuration. Do not try to handle all 401/403 errors with \`RepositoryRestExceptionHandler\`, because the request might not even reach MVC controller advice.

If you want a consistent error body format between repository REST errors and security errors, configure both pipelines to return the same schema at the API contract level while keeping each pipeline's proper responsibility.

## 9. Testing exception handler scope and mapping

The most reliable approach is testing through actual HTTP endpoints using Spring MVC tests, such as MockMvc.

Example testing a business exception on a custom repository REST controller:

~~~java
mockMvc.perform(
        post("/api/products/search/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"code":"P-001"}
                    """)
)
.andExpect(status().isConflict())
.andExpect(jsonPath("$.code").value("PRODUCT_CODE_DUPLICATE"));
~~~

The path and payload in the example need to be adjusted to the application's real mapping.

The test suite should cover:

1. Auto-exported repository resource: trigger a missing entity error and verify HTTP 404.
2. Repository resource: send invalid JSON and verify the binding error is represented properly.
3. Database constraint: trigger a constraint violation and check the actual status/body.
4. Custom \`@RepositoryRestController\`: throw a domain exception and verify the custom advice catches it properly.
5. Regular MVC \`@RestController\`: verify the application's MVC handler is used according to the designed scope.
6. Security filter chain: verify 401/403 errors are handled by security handlers.
7. Transaction: after an error response, read the data back to verify commit/rollback as required.
8. Multiple controller advices: verify the right handler is selected when an exception can match multiple advices.

Do not check only the status code. Verify Content-Type, error code, safe message, and data state after the request. This helps detect cases where the HTTP response reports an error yet data was written, or the response reports success while the business operation did not complete.

## 10. Checklist for choosing the right mechanism

- [ ] Does the request actually pass through a Spring Data REST repository controller?
- [ ] Does the custom endpoint use \`@RepositoryRestController\` if it needs Spring Data REST integration?
- [ ] If it is a regular MVC controller, is there an appropriate \`@ControllerAdvice\` / \`@RestControllerAdvice\`?
- [ ] Did the error occur in the Security filter chain before entering MVC?
- [ ] Are domain exceptions mapped to clear statuses and error codes?
- [ ] Does the advice have a selector scoped to the right package/controller?
- [ ] Could multiple advices catch the exception, and has the order been tested?
- [ ] Does the response accidentally expose internal details?
- [ ] Has transaction rollback been verified independently of the HTTP status?
- [ ] Do integration tests cover both auto-exported repository resources and custom endpoints?

## 11. Conclusion on scope

\`RepositoryRestExceptionHandler\` is the exception handling mechanism for Spring Data REST controllers. It converts errors from the repository REST flow into HTTP responses. Custom endpoints using \`@RepositoryRestController\` can leverage the Spring Data REST environment, whereas regular \`@Controller\` / \`@RestController\` belong to the application's MVC handling scope.

To give the API its own error contract, add controller advice with a clear selector and specific domain exceptions. To handle security errors, background jobs, or transactions, use the corresponding mechanism of each layer. Test over HTTP and verify data after the request to ensure error handling scope matches the design.

## References

- Spring Data REST API — RepositoryRestExceptionHandler: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html
- Spring Data REST Reference — Overriding Spring Data REST Response Handlers: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html
- Spring Framework Reference — Error Responses and @ControllerAdvice: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
