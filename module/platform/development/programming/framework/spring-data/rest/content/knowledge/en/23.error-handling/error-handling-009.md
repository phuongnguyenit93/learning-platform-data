# Customizing Error Handling with Advice Scoped to the Spring Data REST Exporter

## 1. Purpose and processing flow

Spring Data REST exports Spring Data repositories as REST resources through Spring MVC. When a request enters an exporter-created endpoint, exceptions pass through Spring MVC's error handling mechanism (DispatcherServlet and HandlerExceptionResolver). @ExceptionHandler inside @ControllerAdvice is the appropriate extension point to turn exceptions into HTTP statuses and structured response bodies.

An important caveat is that the advice must target the actual controller handling the request. An unscoped @RestControllerAdvice applies to many controllers across the application, whereas controllers managed by the Spring Data REST exporter have their own package scope and message converters. Therefore, before writing a handler, determine whether the request belongs to an exporter-generated repository endpoint or an application custom controller.

## 2. Choosing advice scope matching the exporter

Spring Data REST has RepositoryRestExceptionHandler in the org.springframework.data.rest.webmvc package. Its API shows it is annotated with:

\`\`\`java
@ControllerAdvice(basePackageClasses = RepositoryRestExceptionHandler.class)
\`\`\`

This is the package marker the exporter uses to scope advice to Spring Data REST controllers. You can use the same class as a package marker for your application's custom advice.

| Endpoint type | Controller | Recommended advice scope |
|---|---|---|
| Exporter-generated repository resource | Internal Spring Data REST controller | @ControllerAdvice(basePackageClasses = RepositoryRestExceptionHandler.class) |
| Custom endpoint tied to a resource/repository | @RepositoryRestController | assignableTypes = MyRepositoryRestController.class or basePackageClasses = MyRepositoryRestController.class |
| Other custom operation under basePath | @BasePathAwareController | Marker class or package of application controllers |
| Regular Spring MVC endpoint | @Controller / @RestController | Advice for that package or controller; only use global advice when application-wide scope is truly intended |

@RepositoryRestController lets custom controllers use Spring Data REST configuration such as API base path, message converters, and exception handling. A plain @Controller or @RestController lies outside Spring Data REST's handling scope. If you need a custom operation under basePath without tying it to a specific repository resource, Spring Data REST documentation recommends @BasePathAwareController.

**Important note on package markers:** RepositoryRestExceptionHandler.class points to the exporter's controller package (org.springframework.data.rest.webmvc). It does not automatically select custom controllers placed in the application's com.example... package. For custom controllers, use the controller class itself or a marker class in the application package.

## 3. Example: mapping a business exception to ProblemDetail

The example below uses Spring Framework 6 or higher (typically paired with Spring Boot 3 or higher). ProblemDetail represents errors per RFC 9457 and allows adding custom fields like code.

Business exception:

\`\`\`java
public class CatalogRuleViolationException extends RuntimeException {

    public CatalogRuleViolationException() {
        super("Catalog cannot be changed in its current state");
    }
}
\`\`\`

Advice for exporter-managed repository endpoints:

\`\`\`java
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.data.rest.webmvc.RepositoryRestExceptionHandler;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

@ControllerAdvice(basePackageClasses = RepositoryRestExceptionHandler.class)
@Order(Ordered.HIGHEST_PRECEDENCE)
public class SpringDataRestExporterAdvice {

    @ExceptionHandler(CatalogRuleViolationException.class)
    public ResponseEntity<ProblemDetail> handleCatalogRuleViolation(
            CatalogRuleViolationException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "The resource is in a state that does not allow this operation."
        );
        problem.setTitle("Business conflict");
        problem.setProperty("code", "CATALOG_RULE_CONFLICT");

        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
\`\`\`

The advice above only handles CatalogRuleViolationException. Other exceptions still fall through to Spring Data REST's default handler. ResponseEntity lets you specify status and body; when the body is ProblemDetail, Spring MVC supports content types application/problem+json or application/problem+xml via content negotiation.

Do not put exception.getMessage() or stack traces directly into public responses. Return stable, localizable messages and client-facing error codes; log full exceptions on the server with correlation/request IDs if the system supports them.

### If the application is not yet on Spring Framework 6

ProblemDetail is not available in Spring Framework 5.x. On Spring Boot 2 / Spring Framework 5, use an application error DTO as the response body, such as ApiError(code, message), and return ResponseEntity<ApiError>. Keep the same @ControllerAdvice scope and exception mapping; only change the body type.

## 4. Throwing exceptions from Spring Data REST event handlers

The exporter publishes events during the entity operation lifecycle, including BeforeCreateEvent, BeforeSaveEvent, BeforeDeleteEvent, and their post-operation counterparts. You can use annotated handlers to check business rules before the repository saves an entity.

\`\`\`java
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler
public class CatalogRepositoryEvents {

    @HandleBeforeCreate
    public void validateBeforeCreate(Catalog catalog) {
        if ("blocked".equalsIgnoreCase(catalog.getName())) {
            throw new CatalogRuleViolationException();
        }
    }
}
\`\`\`

Spring Data REST determines the domain type from the first parameter type of the annotated method. The bean must be registered in the application context; @Component allows component scanning to detect it. To check update operations, use @HandleBeforeSave; choose the event matching the business lifecycle point to validate. Spring application events execute synchronously by default, so exceptions thrown in a synchronous request handler propagate up the request-processing chain for advice mapping.

Keep event handlers focused on business rule checks and throwing meaningful exceptions. Choosing HTTP statuses, error titles, and JSON responses belongs in the web advice layer.

## 5. Advice for custom @RepositoryRestController

Custom controllers live in the application package, so the selector must point to that controller or its containing package.

\`\`\`java
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.http.ResponseEntity;

@RepositoryRestController
public class CatalogCommandController {

    @PostMapping("/catalogs/{id}/publish")
    public ResponseEntity<Void> publish(@PathVariable Long id) {
        // Perform publish business logic...
        throw new CatalogRuleViolationException();
    }
}
\`\`\`

Advice applying only to the controller above:

\`\`\`java
@ControllerAdvice(assignableTypes = CatalogCommandController.class)
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CatalogCommandAdvice {

    @ExceptionHandler(CatalogRuleViolationException.class)
    public ResponseEntity<ProblemDetail> handle(CatalogRuleViolationException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Cannot publish catalog in its current state."
        );
        problem.setTitle("Business conflict");
        problem.setProperty("code", "CATALOG_RULE_CONFLICT");

        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
\`\`\`

If multiple custom controllers need the same advice, you can use basePackageClasses = CatalogCommandController.class to select the application package. If a controller is not tied to a repository resource and only needs to live under basePath, consider @BasePathAwareController. When using @RepositoryRestController, the effective path is RepositoryRestConfiguration.getBasePath() plus the method mapping.

## 6. Ordering and specificity of exception mapping

Spring MVC orders @ControllerAdvice beans by Ordered, @Order, or @Priority. For exception handling, the first advice with a matching method is chosen. Within a single advice, a mapping matching the root exception typically takes precedence over a mapping matching only a cause. However, a cause mapping in a higher-precedence advice can still beat a root-exception mapping in a lower-precedence advice.

Apply these principles:

- Declare handlers for specific exceptions, such as CatalogRuleViolationException, instead of catching every Exception.
- Set @Order(Ordered.HIGHEST_PRECEDENCE) only when the custom advice must be evaluated before the default handler or other advices.
- Never write a catch-all returning 400 or 404 for every error; unexpected errors should proceed through default handling and typically return 500.
- If a handler decides not to handle an exception, it can rethrow that exception to forward it to the next resolver/advice.
- There is no need to subclass RepositoryRestExceptionHandler just to add a mapping. Creating a separate advice with clear selectors and exception mappings is easier to control.

Suggested status choices:

| Situation | Commonly used HTTP status |
|---|---:|
| Malformed JSON syntax or invalid input data | 400 Bad Request |
| Resource genuinely does not exist | 404 Not Found |
| Current state conflicts with operation, e.g. updating a locked resource | 409 Conflict |
| Syntactically valid content that violates business rules | 422 Unprocessable Content |
| Unexpected error that cannot be safely classified | 500 Internal Server Error |

Choose statuses according to the existing API contract and stay consistent across endpoints.

## 7. Testing with MockMvc

Do not only invoke controller or advice methods directly. Direct calls do not test request mapping, message conversion, DispatcherServlet, or @ExceptionHandler. MockMvc runs Spring MVC's processing flow through DispatcherServlet without starting an HTTP server, making it well suited to confirm the advice actually catches exceptions on exporter endpoints.

Integration example with the /catalogs repository resource and the event handler above:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SpringDataRestExceptionAdviceTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void mapsBusinessRuleFailureFromExporter() throws Exception {
        mockMvc.perform(post("/catalogs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_PROBLEM_JSON)
                        .content("""
                                {"name":"blocked"}
                                """))
                .andExpect(status().isConflict())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.title").value("Business conflict"))
                .andExpect(jsonPath("$.code").value("CATALOG_RULE_CONFLICT"));
    }
}
\`\`\`

Adjust /catalogs, JSON, and data to your application's actual repository mapping. If RepositoryRestConfiguration.setBasePath("/api") is configured, test requests must use /api/catalogs. Tests should verify HTTP status, content type, and public fields in the response. Add one test for a valid request and one test for an unmapped exception to confirm the default handler still works.

With Spring Boot, @SpringBootTest creates a mock web environment by default; combine with @AutoConfigureMockMvc to inject MockMvc. Run with your project's build command, e.g., ./mvnw test or ./gradlew test.

## 8. Troubleshooting common issues

| Symptom | Common cause | Check / resolution |
|---|---|---|
| Advice is not called for repository endpoint | Selector does not target exporter's controller package | Use basePackageClasses = RepositoryRestExceptionHandler.class for exporter controllers; check if exception is actually thrown |
| Advice is not called for custom controller | Custom controller is in application package, while advice used Spring Data REST's internal package marker | Use assignableTypes or basePackageClasses pointing to the custom controller |
| Advice catches unrelated MVC controllers | @ControllerAdvice has no selector so it applies globally | Restrict using package, class, or annotation selectors |
| Default handler runs before custom mapping | Custom advice has lower precedence or exception mapping does not match | Check @Order, root/cause exception types, and method signatures |
| Response is HTML or lacks expected body | Handler returns a view name or content negotiation mismatch | Return ResponseEntity / ProblemDetail; send Accept: application/problem+json when testing |
| Fails to catch a 404 response | Code may have returned ResponseEntity.notFound() instead of throwing an exception | @ExceptionHandler only handles exceptions; locate where 404 is produced and test that flow |
| Direct method test passes yet HTTP request fails | Test bypasses DispatcherServlet and exception resolvers | Use MockMvc with the real application context |
| Response leaks SQL or internal details | Body directly uses exception.getMessage() or stack trace | Return stable messages, log details on the server, and keep client-facing error codes |
| ProblemDetail does not compile | Project is using Spring Framework 5.x | Use a custom error DTO with ResponseEntity; do not upgrade a single Spring module outside Spring Boot dependency management |

## 9. Implementation checklist

1. Identify whether the endpoint is an exporter-generated repository resource or a custom controller.
2. Choose a selector matching the controller's actual package/class.
3. Create dedicated business exceptions and map them with specific @ExceptionHandler methods.
4. Choose stable HTTP statuses and response schemas; never return stack traces or sensitive information.
5. Adjust @Order only when conflicting with other advices or the default handler.
6. Use MockMvc to test real requests through the exporter, checking status, content type, body, and behavior for unmapped exceptions.

## Official references

- [Spring Data REST – Overriding Spring Data REST Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST – RepositoryRestExceptionHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html)
- [Spring Data REST – Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework – ControllerAdvice API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html)
- [Spring Framework – Exception handling with @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Framework – Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework – MockMvc overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html)
- [Spring Boot – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)