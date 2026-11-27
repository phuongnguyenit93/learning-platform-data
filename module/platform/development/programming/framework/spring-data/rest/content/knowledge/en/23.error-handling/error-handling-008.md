# Formatting Validation Errors, Association Errors, and Business Exceptions in Spring Data REST

> Scope: Spring Data REST running on Spring MVC. Class names and APIs are verified against Spring Data REST 5.1 documentation. Re-verify responses using integration tests on your project's exact Spring Boot, Spring Data REST, and Spring Framework BOM, because handlers and media types can differ across major versions.

## 1. Error response model

An error response needs two stable parts: the HTTP status for the client to decide how to react, and the body for the client to display or log the error. Spring Data REST registers `RepositoryRestExceptionHandler` for REST exporter controllers. For general errors, `ExceptionMessage` converts the exception into a JSON-friendly object. Per the current Javadoc, the serialized part is the outermost exception message; the cause chain is for server-side handling only and is not serialized to JSON.

Common error types:

| Situation | Recommended/used HTTP status | Body or symptoms to check |
| --- | --- | --- |
| Spring `Validator` reports errors on a repository event | `400 Bad Request` | `errors` is a list of errors; each item has `entity`, `property`, `invalidValue`, `message` |
| Jakarta Bean Validation throws `ConstraintViolationException` | Usually `400 Bad Request`; confirm handler for the running version | Helper `ConstraintViolationExceptionMessage` has `cause` and `messages`; each message has entity, property, invalidValue, message |
| JSON is unreadable/unparseable or data type is invalid | `400 Bad Request` | Usually `{"message":"..."}` from `ExceptionMessage`; do not rely on this body to parse field errors |
| Resource or association path does not exist | `404 Not Found` | `ResourceNotFoundException` is annotated with `@ResponseStatus(NOT_FOUND)`; body depends on handler |
| Association accepts only one URI but client sends multiple URIs | `400 Bad Request` | Spring Data REST documentation explicitly specifies this error for to-one association `PUT` |
| Conflicting business state or concurrent update | `409 Conflict` | Use a stable business error code; inspect the handler mapping the application's exception |
| Unsupported HTTP method or media type | `405 Method Not Allowed` or `415 Unsupported Media Type` | Check the methods and `Content-Type` advertised by the endpoint |

The table above is a classification guide, not a guarantee that every application exception automatically shares the same mapping. For custom business exceptions, declare explicit mappings and lock down behavior with tests.

## 2. Validation on repository resources

### 2.1. Registering a Spring Validator by event

Spring Data REST invokes validators via `ValidatingRepositoryEventListener`. The simplest approach is naming the bean after the pattern `<event><DomainType>Validator`. For instance, `beforeCreatePersonValidator` runs before creating a `Person`; use `beforeSavePersonValidator` if updates must also be checked.

```java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component("beforeCreatePersonValidator")
public class BeforeCreatePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getEmail() == null || !person.getEmail().contains("@")) {
            errors.rejectValue("email", "email.invalid", "Invalid email");
        }
    }
}
```

When manual registration is needed, implement `RepositoryRestConfigurer` and add the validator to the appropriate event:

```java
@Configuration
public class RestValidationConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeSave", new BeforeSavePersonValidator());
    }
}
```

Commonly used events include `beforeCreate`, `beforeSave`, `beforeLinkSave`, and `beforeDelete`. Choose the event matching the operation you need to guard. The validator must return `true` in `supports` for the right domain type; otherwise, Spring Data REST will not apply it.

### 2.2. Validation error structure

When a Spring `Validator` adds errors to `Errors`, Spring Data REST throws `RepositoryConstraintViolationException`. The current API provides `RepositoryConstraintViolationExceptionMessage` and nested `ValidationError`; clients can use these fields to highlight invalid fields:

```json
{
  "errors": [
    {
      "entity": "Person",
      "property": "email",
      "invalidValue": "invalid-email",
      "message": "Invalid email"
    }
  ]
}
```

This is an illustrative structural example, not a fixed message string. `entity`, property name, and message depend on the domain model, validator, and `MessageSource`. For object-level errors created via `errors.reject(...)`, property may have no value.

Spring Data REST also has a dedicated helper for `jakarta.validation.ConstraintViolationException`: `ConstraintViolationExceptionMessage` provides `cause` and a list of `messages`; each `ConstraintViolationMessage` has `entity`, `property`, `invalidValue`, and `message`. If the project uses an older Spring Data REST version, the validation namespace may be `javax.validation` instead of `jakarta.validation`; use the namespace matching your managed dependencies.

Do not include sensitive values such as passwords, tokens, or personal data in error responses. Since validation payloads can include `invalidValue`, audit which fields are returned externally and use a custom DTO/handler if values must be masked.

## 3. Association and reference URI errors

### 3.1. Using links and the right media type

Spring Data REST represents relationships using HAL links in `_links`. Clients should start from the root resource, read published relations, and follow those links rather than constructing URLs from assumptions about repository or association names. Paths may also be affected by `spring.data.rest.base-path` and `@RestResource`.

Main operations on association resources:

- `GET` reads the association state.
- `PUT` binds the resource indicated by the URI to the association; the request body uses `text/uri-list`.
- `POST` adds an element to a collection association; the request body also uses `text/uri-list`.
- `DELETE` removes the link if the association permits that operation.

Example binding an address to a user's to-one `address` relationship:

```bash
curl -i -X PUT "http://localhost:8080/people/1/address" \
  -H "Content-Type: text/uri-list" \
  --data-binary "http://localhost:8080/addresses/42"
```

For a to-one association, the body must contain exactly one URI. Sending multiple URIs for a to-one relationship returns `400 Bad Request`. For collection associations, use `POST` to add a single element; use `PUT` when sending the set of URIs to bind according to the endpoint's semantics.

### 3.2. Distinguishing URI errors and association errors

When receiving a linking error, check in order:

1. Does the URI have the correct host, scheme, base path, and path segments published by the API?
2. Does the parent resource exist; is the ID of the right type and converted properly by the repository?
3. Does the relation appear in the parent resource's `_links`; was the relation name changed via `@RestResource`?
4. Does the target URI point to an exported item resource, and does that item exist?
5. Did the request use `Content-Type: text/uri-list` for association `PUT`/`POST`; does the body have one URI per line?

Spring Data REST's `ResourceNotFoundException` is marked `404 Not Found`. This status is appropriate when the server determines the resource or association route does not exist. Do not assume all invalid URIs return the same body: URI parse errors, wrong media types, wrong cardinality, and missing resources may go through different handlers. Reproduce each case with MockMvc on your project's exact version.

## 4. Business exceptions and response standardization

### 4.1. Choosing statuses by business meaning

- Request data violates field rules or invariants checkable before saving: return `400` with field errors via `Validator`.
- Resource does not exist: return `404`.
- Syntactically valid command cannot execute in the current state, or an update conflict occurred: return `409`.
- Caller lacks permission to perform the action: return `403`.
- Unexpected error: return `500`, log fully on the server, and do not expose stack traces/SQL to the client.

Do not use `500` for a business condition the client can handle. Likewise, do not mechanically convert every `DataIntegrityViolationException` into `400`: distinguish fixable input errors from data conflicts or changed state.

### 4.2. Using ProblemDetail for custom endpoints

From Spring Framework 6 onward, you can return `ProblemDetail` per Problem Details for HTTP APIs; current Spring Framework supports RFC 9457. `ProblemDetail` includes standard fields such as `type`, `title`, `status`, `detail`, and `instance`; you can add extension properties such as `code` so clients can handle stable error codes. For older Spring Framework versions, use a custom error DTO with equivalent fields.

When writing custom endpoints within Spring Data REST's URI space, use `@RepositoryRestController`. This annotation lets the endpoint share Spring Data REST's base path, message converters, and exception handling. Regular `@RestController` controllers fall outside that integration scope.

```java
@RepositoryRestController
public class OrderCommandController {

    private final OrderService orderService;

    public OrderCommandController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/orders/{id}/confirm")
    public ResponseEntity<Void> confirm(@PathVariable Long id) {
        orderService.confirm(id);
        return ResponseEntity.noContent().build();
    }

    @ExceptionHandler(OrderCannotBeConfirmedException.class)
    public ResponseEntity<ProblemDetail> handleCannotConfirm(
            OrderCannotBeConfirmedException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "The order is not in a confirmable state.");
        problem.setTitle("Cannot confirm order");
        problem.setProperty("code", "ORDER_NOT_CONFIRMABLE");

        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
```

`@ExceptionHandler` placed in the controller above handles exceptions thrown from that controller's handler methods. If an exception arises in the default repository endpoint flow, such as from a repository event handler, check the order and scope of `@ControllerAdvice` relative to `RepositoryRestExceptionHandler`; do not assume another controller's advice will win. Use integration tests to confirm the actual mapping.

Illustrative response for a command invalid in the current state:

```json
{
  "type": "about:blank",
  "title": "Cannot confirm order",
  "status": 409,
  "detail": "The order is not in a confirmable state.",
  "code": "ORDER_NOT_CONFIRMABLE"
}
```

Keep `code` stable across wording or language changes. `detail` is for human readers; clients should branch on HTTP status and `code`, not parse messages. Never return `exception.getMessage()` if the message might contain SQL, table names, sensitive data, or internal information.

## 5. Testing error contracts with MockMvc

Test over real HTTP instead of calling validators or services directly. The example test skeleton below assumes the application exports `PersonRepository`, the `address` association is to-one, and the custom order confirmation endpoint is registered:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SpringDataRestErrorTest {

    @Autowired MockMvc mockMvc;
    @Autowired ObjectMapper objectMapper;

    @Test
    void invalidPersonReturnsFieldErrors() throws Exception {
        Person invalid = new Person("An", "invalid-email");

        mockMvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(invalid)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].property").value("email"))
            .andExpect(jsonPath("$.errors[0].message").exists());
    }

    @Test
    void toOneAssociationRejectsMultipleUris() throws Exception {
        // Fixture must create person 1 and the two referenced addresses beforehand.
        mockMvc.perform(put("/people/1/address")
                .contentType(MediaType.parseMediaType("text/uri-list"))
                .content("http://localhost:8080/addresses/10\\nhttp://localhost:8080/addresses/11"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingPersonReturnsNotFound() throws Exception {
        mockMvc.perform(get("/people/999999"))
            .andExpect(status().isNotFound());
    }

    @Test
    void businessConflictReturnsProblemDetail() throws Exception {
        mockMvc.perform(post("/orders/1/confirm"))
            .andExpect(status().isConflict())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_CONFIRMABLE"));
    }
}
```

Add repository and service fixtures following your project's test structure. If `base-path` is configured, prepend that prefix to the URLs. When testing validation responses, assert only the required contract fields; avoid coupling tests to default message text that may be localized via `MessageSource`.

Checklist for each test:

- Assert the exact status code, not just `is4xxClientError()`.
- Assert `Content-Type` and the JSON fields clients actually consume.
- For associations, test media type, cardinality, and target URI.
- For business errors, assert a stable `code` and the corresponding status.
- Verify failed requests do not write or modify data.
- Verify responses do not contain stack traces, SQL, internal class names, or sensitive data.

## 6. Troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| POST/PUT returns `400` with only `message`, no `errors` | JSON parsing/type conversion failed before validator ran, or validator is not registered | Check request JSON, bean name, component scan, `supports`, and `beforeCreate`/`beforeSave` events |
| Validator runs on create but not on update | Only `beforeCreate` was registered | Register `beforeSave` as well if the rule also applies to updates |
| Association returns `404` | Wrong base path, relation, item ID, or unexported/missing resource | Read `_links` from root and parent resource; verify target URI |
| Association returns `400` | Malformed body or multiple URIs sent for a to-one association | Use `text/uri-list`; send exactly one URI for to-one |
| Association returns `415` | `Content-Type` is not supported by the endpoint | Use `text/uri-list` for association `PUT`/`POST` |
| Business exception becomes `500` | Missing handler or exception thrown inside default repository flow | Categorize the exception, add appropriate mapping, and verify `@ControllerAdvice` ordering with MockMvc |
| Response leaks database details | Outermost exception message contains internal details | Produce safe messages, log causes on the server, and return public `code` values |

When debugging, log correlation/request ID, exception type, and stack trace on the server. Clients only need status, error code, and sanitized detail. Do not enable stack trace display in production responses to diagnose root causes.

## 7. Official references

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): registering validators by bean name and `RepositoryRestConfigurer`.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): HTTP methods, media types, and status codes of collection, item, and association resources.
- [Spring Data REST — Overriding response handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html): using `@RepositoryRestController`, base path, and exception handling integration.
- [RepositoryRestExceptionHandler Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestExceptionHandler.html): handler for Spring Data REST controllers.
- [RepositoryConstraintViolationException Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/RepositoryConstraintViolationException.html): exception thrown when a Spring `Validator` reports errors.
- [RepositoryConstraintViolationExceptionMessage.ValidationError Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/RepositoryConstraintViolationExceptionMessage.ValidationError.html): fields of each validation error.
- [ConstraintViolationExceptionMessage Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/ConstraintViolationExceptionMessage.html): `cause` and `messages` structure for Jakarta validation exceptions.
- [ResourceNotFoundException Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/ResourceNotFoundException.html): `NOT_FOUND` mapping.
- [ExceptionMessage Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/ExceptionMessage.html): how exception messages are serialized and the cause chain omitted from JSON.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, RFC 9457, `ResponseEntityExceptionHandler`, and message customization.