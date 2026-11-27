# 400 for Invalid Parameters, JSON, or Input Data

## Objectives

After this lesson, you can:

- Identify situations where Spring Data REST commonly returns HTTP **400 Bad Request**.
- Distinguish parameter parsing errors, JSON deserialization errors, and data validation errors.
- Trace the root cause from the request, response body, and server logs.
- Use Bean Validation or Spring Validator to validate input data.
- Design a consistent error response with appropriate error codes and field information.
- Distinguish 400 from 404, 406, 409, 412, and 415.
- Write tests for valid requests and common invalid input forms.

## 1. What does HTTP 400 mean?

**400 Bad Request** indicates that the server cannot process the request because the request or input data is invalid according to the API contract. With Spring Data REST, the error can occur before the repository is invoked or while the framework converts HTTP data into domain objects.

Examples:

- A query parameter expects an integer, but the client sends letters.
- A path variable cannot be converted to the ID type expected by the endpoint.
- JSON has syntax errors or data types that cannot be deserialized into the entity.
- The request is missing a required field according to the contract.
- Enum, date, or input format values are invalid.
- Validation detects a field violating a business constraint.

HTTP 400 is a general status. Looking at the status code alone is not enough to tell whether the error is in a query parameter, JSON parser, data binding, or validation. You need to read the error response and corresponding logs to pinpoint the exact cause.

## 2. What steps does a request go through?

A write request going through Spring Data REST typically passes through these general steps:

1. The web server and Spring MVC receive the HTTP request.
2. Handler mapping determines the repository resource and HTTP operation.
3. The framework reads path variables, query parameters, headers, and Content-Type.
4. HttpMessageConverter deserializes the body, such as JSON into an entity.
5. Spring Data REST runs the appropriate validators for the repository event.
6. The repository performs the persistence operation.
7. The framework serializes the response representation, usually HAL.

400 can be generated at several early steps:

| Location | Example | Common symptoms |
|---|---|---|
| Parse parameter | ?page=abc when page expects a number | Cannot convert data type |
| Convert path variable | ID cannot be converted to Long | Path variable/type mismatch |
| Deserialize body | JSON missing closing brace or age is an object instead of a number | HttpMessageNotReadableException or parse error |
| Validate entity | empty name or negative age | Field validation error |
| Bind request for custom handler | Missing required parameter or body of wrong type | Binding/argument resolution error |

The repository may not even be invoked if the error happens during parsing, conversion, or deserialization. When validation fails, the save operation must also be rejected.

## 3. Query parameter and path variable errors

Spring Data REST accepts query parameters for paging, sorting, searching, or driving finder methods. The submitted values must be compatible with the data types required by the endpoint.

Example collection supporting page and size:

~~~http
GET /api/people?page=abc&size=20
Accept: application/hal+json
~~~

If page is converted to an integer, the value abc is invalid and the request may return 400.

Example finder method taking an enum parameter:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByStatus(@Param("status") PersonStatus status);
}
~~~

Valid request:

~~~http
GET /api/people/search/findByStatus?status=ACTIVE
Accept: application/hal+json
~~~

If a value is sent that cannot be mapped to the PersonStatus enum, parameter conversion may fail and return a client error.

Cases to check:

- Integers, decimals, and ID types.
- Enums must match a supported value.
- Dates and times must follow a format accepted by the application's converters.
- Booleans must use values supported by the converter.
- Required query parameters of custom endpoints must be present.
- Sort values must point to valid properties allowed by the API.

Do not assume every invalid value is handled the same way. Some endpoints may ignore unknown parameters, use defaults, or return errors depending on resolvers and configuration. Test against the actual endpoint and data types.

## 4. JSON and request body deserialization errors

Spring Data REST uses HttpMessageConverter to convert the HTTP body into the corresponding entity or representation. With JSON, syntax errors or incompatible data types typically cause the request to be rejected before calling the repository.

Malformed JSON syntax:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan",
  "age": 25,
~~~

The body above is missing the closing brace of the object, so the JSON parser cannot read it.

Syntactically valid JSON with wrong data types:

~~~json
{
  "name": "Lan",
  "age": {
    "value": 25
  }
}
~~~

If age in the entity is an Integer, a JSON object cannot be converted to Integer with this structure.

Valid request according to the example:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan",
  "email": "lan@example.com",
  "age": 25
}
~~~

Distinguish three groups:

- **Malformed JSON**: the body is not valid JSON.
- **Deserialization/type mismatch**: JSON is valid, but does not match Java types or property structure.
- **Semantic validation**: the body can be deserialized into an entity, but values violate business rules.

The first two groups typically occur while reading the body; the last group is handled by validation after the entity has been created from the request.

Whether an undeclared JSON property in the entity is ignored or causes an error depends on Jackson configuration and application settings. Do not assume unknown properties always return 400; decide explicitly whether the API rejects unknown fields and test against the actual configuration.

## 5. Content-Type and Accept are two different cases

Not every representation-related error is 400.

- **Content-Type** describes the format of the body sent by the client.
- **Accept** describes the response format the client wants to receive.

For example, a client sending XML to an endpoint that only accepts JSON may receive **415 Unsupported Media Type**.

~~~http
POST /api/people
Content-Type: application/xml
Accept: application/hal+json
~~~

If the client requests a response representation the server does not support, the server may return **406 Not Acceptable**.

~~~http
GET /api/people
Accept: application/x-unknown-format
~~~

When diagnosing, check method, Content-Type, Accept, and body together. Fixing JSON will not resolve 415 if Content-Type is still wrong; changing Accept will not resolve a body parsing error.

## 6. Data validation after deserialization

A request with valid JSON may still contain data that is not allowed to be saved. For example, Person requires a name, a valid email, and a non-negative age.

Constraints can be declared using Jakarta Bean Validation:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(0)
    private Integer age;

    // Getters and setters
}
~~~

The application needs a Bean Validation provider compatible with the Spring/Jakarta version in use. With Spring Boot, the dependency is typically the validation starter.

Spring Data REST also supports Spring Validators bound to repository events via bean naming conventions. Example:

~~~java
@Component("beforeCreatePersonValidator")
public class BeforeCreatePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return Person.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getAge() != null && person.getAge() < 0) {
            errors.rejectValue(
                "age",
                "person.age.negative",
                "Age cannot be negative"
            );
        }
    }
}
~~~

The name **beforeCreatePersonValidator** binds the validator to the event before creating a Person. For rules that must always hold before saving changes, you can register a validator for **beforeSave** or place shared logic in an appropriate service/domain layer.

Distinction:

- Bean Validation uses annotations like **@NotBlank**, **@Email**, **@Min**.
- Spring Validator implements **supports** and **validate**, recording errors via **Errors**.
- Both must be configured and verified in the actual write flow; do not assume merely adding annotations guarantees every entry point executes validation properly.

## 7. Distinguishing format errors and business errors

A helpful classification:

| Error type | Example | Appropriate handling layer |
|---|---|---|
| Syntax | JSON missing } | HTTP message converter/parser |
| Type conversion | age: "abc" when Integer is needed | Data binding/conversion |
| Required field | name must not be blank | Bean Validation or Spring Validator |
| Range/format | negative age, invalid email format | Bean Validation or Spring Validator |
| Cross-field rule | startDate must be before endDate | Class-level constraint or service/domain validation |
| State-dependent rule | Cannot change status of a delivered order | Service/domain rule with access to current state |

Syntax and type conversion errors can usually be fixed by sending a properly formatted request. Business errors require the client to understand which rule was violated so the user can fix the data.

Do not collapse every exception into a single "Invalid request" message. That makes it hard for clients to recover and hides programming or system errors.

## 8. 400 error response body

The HTTP status indicates the result category, while the response body should help the client identify and fix the input. Spring Data REST's default body shape may vary by version, exception handler, and Spring Boot configuration. It may contain a general message, field errors, or validation details; do not depend on an unverified JSON shape.

An application-designed error contract can use this structure:

~~~json
{
  "type": "https://api.example.com/problems/invalid-input",
  "title": "Invalid input data",
  "status": 400,
  "detail": "There are 2 fields that need correction.",
  "instance": "/api/people",
  "code": "VALIDATION_FAILED",
  "violations": [
    {
      "field": "name",
      "code": "NOT_BLANK",
      "message": "Name must not be blank"
    },
    {
      "field": "email",
      "code": "EMAIL_INVALID",
      "message": "Email format is invalid"
    }
  ]
}
~~~

Useful fields:

- **status**: HTTP status.
- **code**: stable error code for client logic.
- **detail**: brief request-level explanation.
- **instance**: request path that caused the error.
- **violations**: list of field-level errors, including error codes.
- **traceId**: correlation ID for looking up logs if supported by the system.

User-facing messages should be clear without exposing stack traces, SQL, internal table names, tokens, passwords, or sensitive data. Avoid echoing back verbatim input that might contain secrets.

If using Spring Framework 6 or higher, consider **ProblemDetail** per RFC 9457 for custom MVC exception handlers. Verify the version and how Spring Data REST handles exceptions before applying a single handler across all endpoints. Do not change the default error contract if existing clients depend on it without a compatibility plan.

## 9. Handling errors in custom controllers

For application-written custom endpoints, you can use **@ExceptionHandler** or **@ControllerAdvice** to map input exceptions to structured responses.

Example with Spring Framework supporting ProblemDetail:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.http.converter.HttpMessageNotReadableException;

@RestControllerAdvice(assignableTypes = PersonCommandController.class)
public class PersonCommandErrorHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ProblemDetail invalidJson(
            HttpMessageNotReadableException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "JSON body is invalid or has incorrect data types."
        );

        problem.setTitle("Invalid input data");
        problem.setProperty("code", "INVALID_JSON");
        return problem;
    }
}
~~~

The example scopes the advice to the specified controller to avoid accidentally changing error handling for the entire Spring Data REST exporter. In a real application, you can add handlers for validation exceptions or custom business errors.

For repository resources managed by Spring Data REST, prefer validation events and exception handling mechanisms compatible with your Spring Data REST version. Do not assume a **@RestControllerAdvice** scoped to a custom controller will automatically replace the exporter's internal handler.

If you need a unified response contract across the API, design an exception mapping with clear scope, verify handler ordering, and write integration tests for both repository resources and custom controllers.

## 10. Distinguishing 400 from common statuses

| Status | Meaning | Example |
|---|---|---|
| **400 Bad Request** | Request or input data is invalid | Malformed JSON, unconvertible parameter, validation failed |
| **404 Not Found** | Resource or endpoint does not exist | ID does not exist in repository |
| **405 Method Not Allowed** | Endpoint exists but does not support that HTTP method | Sending DELETE to a GET-only endpoint |
| **406 Not Acceptable** | No response representation matches Accept | Client requests an unsupported media type |
| **409 Conflict** | Request conflicts with current resource state | Certain business or persistence conflicts |
| **412 Precondition Failed** | HTTP condition such as If-Match is not satisfied | Stale ETag on conditional update |
| **415 Unsupported Media Type** | Server does not support the submitted body format | Unsupported Content-Type |
| **500 Internal Server Error** | Unexpected server-side error | Unmapped bug or infrastructure failure |

Some frameworks or applications may map a specific exception type to a different status. For example, optimistic locking may be mapped to 409 or 412 depending on the API contract and precondition mechanism. Verify the status your application version actually returns.

Do not return 400 for every error just because the request came from a client. A nonexistent ID is typically 404; an unsupported media type is 415; unexpected server-side errors should not be masked as 400.

## 11. Testing with curl

### Malformed JSON

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","age":25' \
  http://localhost:8080/api/people
~~~

The goal is to confirm the parser rejects the body and the response has an appropriate client error status, typically 400.

### Valid JSON syntax with wrong type

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","age":{"value":25}}' \
  http://localhost:8080/api/people
~~~

If the entity expects age as an Integer, this JSON object does not match the data type.

### Unconvertible query parameter

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people?page=abc&size=20"
~~~

Confirm the error occurs during parameter conversion and is not confused with a repository query error.

### Failed validation

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"invalid","age":-1}' \
  http://localhost:8080/api/people
~~~

Check that the response indicates which fields violated constraints and confirm the entity is not saved.

### Valid request

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.com","age":25}' \
  http://localhost:8080/api/people
~~~

A valid request must pass validation and create the resource according to the API contract. Use the self link or Location header from the response to identify the newly created item.

## 12. Testing with integration tests

You should test both the status code and the persistence side effects. Example with MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonRestApiTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    PersonRepository repository;

    @Test
    void rejectsMalformedJson() throws Exception {
        long before = repository.count();

        mockMvc.perform(post("/api/people")
                .contentType(MediaType.APPLICATION_JSON)
                .accept("application/hal+json")
                .content("{\"name\":\"Lan\",\"age\":"))
            .andExpect(status().isBadRequest());

        assertThat(repository.count()).isEqualTo(before);
    }
}
~~~

This example illustrates testing a malformed JSON body. Import MockMvc, request builders, MediaType, status matchers, and the assertion library according to your project's test stack.

For validation, also check:

- Status is 400 per the application contract.
- Field errors have stable field names and error codes.
- No new entity is saved.
- Valid requests still create the resource.
- Unrelated exceptions are not mistakenly converted to 400.

If using a test database with transaction rollback after each test, pay attention to repository count assertions in the test and the request's transaction boundaries. For end-to-end HTTP tests, you can use an isolated test database or verify persistence through a separate transaction to avoid reading a stale persistence context.

## 13. Logging and error diagnosis

When a request returns 400, investigate in this order:

1. Record the method, path, query string, and Content-Type.
2. Verify whether the body is valid JSON.
3. Check the Java fields and corresponding JSON types.
4. Inspect the root exception in server logs, such as deserialization or conversion errors.
5. If the body deserializes successfully, check Bean Validation and Spring Validators.
6. Confirm whether the request reached repository events.
7. Check whether the entity was saved or modified.

You can log the exception class and internal error code without logging the entire body. If the body contains PII or credentials, do not enable uncontrolled request-body logging in production.

A trace ID or correlation ID helps link the error response to server logs. Return that ID to the client so support teams can find the corresponding event without exposing stack traces.

## 14. Error contract design principles

- Use the status code matching the nature of the error.
- Keep machine-readable error codes stable, e.g., **INVALID_JSON**, **INVALID_PARAMETER**, **VALIDATION_FAILED**.
- For validation, return a list of field violations instead of a single generic sentence.
- User-facing messages should be short, actionable, and free of internal details.
- Never return stack traces, SQL, internal class names, or secrets.
- Never echo back the entire request body if it contains personal data.
- Keep error responses compatible across API versions or version contracts explicitly.
- Log on the server with a trace ID for investigation.
- Verify that failed requests do not cause unintended persistence changes.

## 15. Common mistakes

### Returning 400 for every error

An overly broad exception handler can mask 404, 409, or 500 errors as 400. Only map exceptions that genuinely represent invalid input.

### Confusing JSON parsing errors with validation

If JSON has not deserialized yet, the validator does not have a valid entity to inspect. Check message converter errors before looking at validation.

### Using the wrong Content-Type

A JSON body missing Content-Type or declaring an incompatible Content-Type can cause a media type error. Distinguish 415 from 400 caused by invalid JSON content.

### Checking only the status code

Two requests both return 400, yet one has a bad page parameter while the other violates email format. The response body and logs must help pinpoint the exact cause.

### Assuming unknown JSON properties are always valid

Unknown field behavior depends on Jackson configuration. Decide explicitly whether to reject unknown fields and write tests for that contract.

### Validation fails yet data is still saved

Check whether the validator is registered for the right event/domain type, whether an exception is being caught and swallowed, and whether the transaction rolls back properly.

### Returning exception details to the client

Stack traces or database messages can leak internal structure and sensitive data. Use safe messages for clients and keep details in controlled logs.

### Using 400 for nonexistent resources

An unfound ID is typically 404. Do not turn every "cannot complete" situation into Bad Request.

## 16. Takeaways

- **400 Bad Request** is used when the request or input data is invalid.
- Errors can occur while parsing parameters, converting path variables, deserializing JSON, or validating entities.
- Malformed JSON syntax differs from syntactically valid JSON with wrong types; both differ from business validation.
- Use Bean Validation or Spring Validator to validate fields and business rules.
- Error responses should include a stable error code, clear message, and list of field violations when appropriate.
- Distinguish 400 from 404, 405, 406, 409, 412, 415, and 500.
- Check status, response body, root exception, repository events, and persistence impact.
- Do not log or return sensitive data, stack traces, or SQL to clients.
- Write integration tests for malformed JSON, invalid parameters, validation failures, and valid requests.

## References

- [Spring Data REST Reference — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST Reference — Handling Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [RFC 9110 — HTTP Semantics: 400 Bad Request](https://www.rfc-editor.org/rfc/rfc9110.html#name-400-bad-request)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)