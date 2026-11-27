# Formatting Validation Errors and Testing Invalid Data

Spring Data REST can expose repositories as REST resources without requiring controllers for each CRUD operation. Even so, the API must clearly define which data is valid, what structure errors are returned in, and which error codes clients can rely on for handling. An endpoint that merely returns HTTP 400 when data is wrong is insufficient if the response does not indicate which field failed, which rule was violated, and how to fix the data.

This lesson focuses on two parts: building a stable validation error contract for a Spring Data REST API and testing requests containing invalid data at the integration level.

## 1. At Which Layers Does Validation Occur?

Do not lump all input errors into a single bucket. A request can fail at several different stages:

| Validation Layer | Invalid Data Example | Outcome to Convey |
|---|---|---|
| JSON syntax and conversion | JSON missing a bracket, sending a string into a numeric field | Request is unreadable |
| Field validation | Blank name, malformed email, negative quantity | Violated field and constraint |
| Cross-field rules | End date precedes start date | Relevant business rule |
| Business state | Order is already closed yet client requests modification | Conflict or business error |
| Persistence constraints | Email must be unique but already exists | Data violation, even under concurrent requests |
| Authentication and authorization | User is not allowed to modify resource | Authentication/authorization error |

Each layer has a different detection time and handling strategy. Syntactically invalid JSON is rejected before the entity is converted into a Java object. A @NotBlank error can only be detected after data has been deserialized. A database unique constraint may only fail when the transaction writes data.

Place validation at the layer closest to the invariant being protected:

- Data shape rules belong to Bean Validation or request models.
- Multi-field rules belong to validators/domain services.
- Uniqueness and data integrity rules must be protected by database constraints.
- Rules depending on current state belong to business logic and require handling concurrent updates.

Client-side validation only helps users get early feedback. The server must still revalidate because clients can be bypassed, data can arrive from other integrations, and multiple requests can run concurrently.

## 2. Declaring Constraints on Entities

With Spring Boot 3, Bean Validation uses the jakarta.validation namespace. If the application does not yet have a validation implementation, add the appropriate dependency, typically:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-validation")
~~~

Example Customer entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank(message = "Customer name must not be blank")
    @Size(max = 120, message = "Customer name must be at most 120 characters")
    private String name;

    @NotBlank(message = "Email must not be blank")
    @Email(message = "Email format is invalid")
    private String email;

    @PositiveOrZero(message = "Credit limit must be greater than or equal to 0")
    private BigDecimal creditLimit;

    // getters and setters
}
~~~

Key points to note:

- @NotNull only forbids null; it does not forbid empty strings.
- @NotEmpty forbids null and empty values, but whitespace-only strings can still pass.
- @NotBlank fits required strings that must have non-whitespace content.
- @Email checks email formatting at the validator level; it does not prove the address actually exists or belongs to the user.
- @Positive and @PositiveOrZero fit numbers requiring sign restrictions.
- @Size controls string length or collection size; choose limits matching the API contract and database.

For nested objects, use cascade validation so constraints on child objects are executed too:

~~~java
public class Address {

    @NotBlank
    private String city;

    @NotBlank
    private String street;
}

public class Customer {

    @Valid
    @NotNull
    private Address address;
}
~~~

If a field can legitimately be absent, do not mechanically apply required constraints. Distinguish an omitted field, a field with a null value, an empty string, and a default value produced by deserialization. This is especially important for PATCH because clients usually send only the fields they intend to change.

## 3. Connecting Validation to the Spring Data REST Lifecycle

Spring Data REST provides repository events before and after creating, saving, linking, and deleting entities. Two common points for validating write data are:

- beforeCreate: before creating a new entity.
- beforeSave: before saving changes to an existing entity.

Bean Validation constraints must be integrated into the application's validation flow. For custom rules, you can implement org.springframework.validation.Validator and register the validator for the corresponding event.

Example validating a date range:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component("beforeCreateBookingValidator")
public class BeforeCreateBookingValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Booking.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Booking booking = (Booking) target;

        if (booking.getStartDate() != null
                && booking.getEndDate() != null
                && booking.getEndDate().isBefore(booking.getStartDate())) {
            errors.rejectValue(
                "endDate",
                "booking.dateRange.invalid",
                "End date must be on or after start date"
            );
        }
    }
}
~~~

Spring Data REST supports validators attached to repository events. A common registration approach is using bean names following the convention beforeCreate<DomainType>Validator or beforeSave<DomainType>Validator. Ensure the domain type name matches the entity managed by the repository and check how validator configuration works in the version you are using. If you want explicit control, configure ValidatingRepositoryEventListener and register validators by event name.

If an entity can be created and updated through multiple flows, apply the same invariant to both required events. A validator running only on beforeCreate will not automatically protect an entity when it is updated later.

Do not place side effects such as sending emails or calling payment gateways inside validators. Validators should validate and report errors. Persisting data or triggering downstream tasks should only happen after validation and business transactions succeed.

## 4. Designing Error Structures for Clients

A useful error response should help the client answer:

1. Where did the request fail?
2. Which field or resource has the problem?
3. Which rule was violated?
4. Can the client fix the data and resend, or must it handle a conflict?
5. Is there a reference ID for looking up logs when support is needed?

Example of a validation error contract explicitly standardized by the application using Problem Details:

~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Invalid request data",
  "status": 400,
  "detail": "One or more fields failed validation rules.",
  "instance": "/customers",
  "errors": [
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Customer name must not be blank"
    },
    {
      "field": "email",
      "code": "Email",
      "message": "Email format is invalid"
    },
    {
      "field": "creditLimit",
      "code": "PositiveOrZero",
      "message": "Credit limit must be greater than or equal to 0"
    }
  ],
  "traceId": "01JEXAMPLE9M4Y2"
}
~~~

Meaning of each component:

| Component | Purpose |
|---|---|
| type | URI identifying the error category |
| title | Short summary of the error |
| status | HTTP status code |
| detail | General explanation for the current request |
| instance | URI of the failing request or resource |
| errors | List of detailed per-field errors |
| field | Field name according to the API contract |
| code | Stable error code for client handling |
| message | Human-readable message suitable for display |
| traceId | Log correlation ID, if the system has tracing |

This is an illustrative structure for an API that standardizes its own errors; do not assume Spring Data REST returns this exact JSON automatically. Spring Data REST may use the VndErrors style in some cases. Actual media types, statuses, and contents depend on the version, exception handlers, configuration, and content negotiation of the application.

Before writing clients, send actual requests with the Accept headers your clients use and inspect the responses returned. If you want the API to use Problem Details or a custom schema, implement appropriate exception handling and then test that contract at the HTTP level.

### 4.1. Choosing consistent HTTP statuses

One applicable convention:

| HTTP status | Scenario |
|---|---|
| 400 Bad Request | Malformed JSON, failed deserialization, or field validation failure |
| 401 Unauthorized | Missing or invalid authentication credentials |
| 403 Forbidden | Authenticated but lacking permission |
| 404 Not Found | Target resource does not exist |
| 409 Conflict | Current state or unique constraint conflicts with the operation |
| 412 Precondition Failed | If-Match condition or precondition is no longer true |
| 415 Unsupported Media Type | Content-Type is not supported by the endpoint |
| 422 Unprocessable Content | API chooses a specific convention for syntactically valid content that cannot be processed semantically |
| 500 Internal Server Error | Unexpected server-side error |

Not every API needs to use all statuses. What matters is that the same kind of error has a consistent representation. For example, if field validation always returns 400, clients should not have to handle the same error sometimes as 400, sometimes 409, and sometimes 500.

A unique constraint can be detected after initial validation has already passed. This case should usually return conflict per the API contract, while being distinguished from unexpected database failures. Do not blindly turn every DataIntegrityViolationException into 409 because the exception can stem from many different causes.

### 4.2. Stable error codes and messages

Clients should rely on codes to decide how to display or handle errors. Message text can be translated, edited, or vary by language.

Examples:

- NotBlank: content input is required.
- Email: email format is invalid.
- Size: length limit exceeded.
- PositiveOrZero: value must be non-negative.
- customer.email.duplicate: email is already in use.
- booking.dateRange.invalid: invalid date range.

Do not use free-form prose messages as identifiers. Also avoid returning stack traces, SQL, table names, internal class names, tokens, personal data, or full rejected values if a field may contain sensitive information.

If you need to echo rejected values to help users fix forms, filter by an allowlist. Never echo passwords, access tokens, card numbers, identity documents, or sensitive payloads.

## 5. Handling Different Types of Errors

### 5.1. Malformed JSON or wrong data type

For example, a client sends a non-numeric string for the quantity field:

~~~json
{
  "quantity": "many"
}
~~~

This is a deserialization error, not a @Positive or @NotNull error. The validator may not have been called because the server could not construct a valid object.

The API should return an unreadable-request error with an appropriate status, usually 400, and a message indicating the location or field if possible. Do not return Jackson stack traces to the client.

### 5.2. Field validation failure

For example, a request has an invalid email or a negative quantity. This is an error that can be mapped to a list of field errors.

If a client sends multiple invalid fields, return all errors that can be safely determined in a single response instead of forcing the user to fix one error at a time.

### 5.3. Cross-field rules

For example, startDate and endDate are both validly formatted, yet their date ordering is invalid. This is an object-level error or domain rule. It can be represented via the relevant field (endDate) or an object-level error code such as booking.dateRange.invalid.

Do not arbitrarily assign the error to the first field just so the response has a field name. If a rule applies to the entire object, use the object or path to express scope.

### 5.4. Unique constraints and concurrency errors

Checking "email does not exist yet" at the service layer helps return an early error, but two concurrent requests can both read that the email does not exist and then both write.

Therefore, database unique constraints remain necessary. When a constraint is violated, translate the recognized persistence error into a stable business code, such as customer.email.duplicate. Do not return raw constraint names or SQL statements to the client.

### 5.5. Business state errors

For example, an order is already completed so it cannot transition back to a new state. This is not a field formatting error. Return a conflict or domain error matching the API contract and provide a code so the client knows to reload state or prompt the user for a different action.

## 6. At What Levels Should Invalid Data Be Tested?

A solid test suite needs to verify everything from individual validators to the Spring Data REST HTTP contract.

| Test Level | What to Verify |
|---|---|
| Validator unit tests | Constraints, field paths, and error codes are accurate |
| Domain rule tests | Multi-field rules and business states |
| Repository/database tests | Unique, foreign key, check constraints, and transactions |
| Spring Data REST integration tests | HTTP status, media type, error body, and repository events |
| End-to-end tests | Real clients receive errors and display them properly |

Unit tests cannot replace integration tests. A validator may work when called directly yet not be registered with Spring Data REST events. Conversely, HTTP tests checking only status codes without verifying that the database was left unmodified are also insufficient.

### 6.1. Testing POST with invalid data

Example using MockMvc in a Spring Boot application:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerValidationIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void rejectsInvalidCustomerWithoutPersisting() throws Exception {
        long countBefore = customerRepository.count();

        mockMvc.perform(post("/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": " ",
                      "email": "not-an-email",
                      "creditLimit": -1
                    }
                    """))
            .andExpect(status().isBadRequest());

        assertThat(customerRepository.count()).isEqualTo(countBefore);
    }
}
~~~

The test above demonstrates checking the HTTP status and ensuring an invalid request does not create a new entity. If your API standardizes an error schema, add assertions for type, errors[*].field, and errors[*].code. If the API uses default VndErrors, write assertions matching the actual response rather than copying JSON paths from a different schema.

Note: the example uses application/json for Accept for illustration. For clients using HAL, add tests with the media types clients actually send and verify error responses are negotiated properly.

### 6.2. Testing PUT and PATCH

For PUT, beyond status and error body, re-read the entity after the request to confirm old data is preserved when validation fails.

For PATCH, test both scenarios:

- Patch sending an invalid field.
- Patch sending only one field that violates a cross-field rule once merged with current state.

For example, a booking has startDate on day 10 and endDate on day 20. A PATCH changing only startDate to day 25 must be rejected if the invariant requires endDate not to precede startDate.

Do not validate only the fields present in the patch document. Validate the entity state after applying the patch according to the endpoint's semantics.

### 6.3. Testing database constraints

For unique constraints, tests should send two requests with the same unique value. Sequential tests verify error mapping; concurrent tests uncover race conditions.

Example:

1. Create a Customer with email a@example.com.
2. Send a second request creating a Customer with the same email.
3. Verify the second request receives the status and error code per the contract.
4. Verify the database contains only one Customer with that email.

If the domain requires safety under concurrency, run two requests in parallel and confirm the unique constraint truly prevents duplicate data.

## 7. Matrix of Invalid Data to Test

Do not test only a single empty string. Identify boundaries and data variations for each field.

| Data Group | Values to Test |
|---|---|
| Required fields | Omitted field, null, "", whitespace-only string |
| Length | Shorter than limit, exact limit, one character over |
| Email/URL | Valid, invalid syntax, spaces, very long string |
| Numbers | Negative, 0, positive, excessively large, decimals when only integers accepted |
| Date/time | Wrong format, nonexistent date, timezone, inverted start/end order |
| Enum | Valid value, wrong casing, nonexistent value |
| Relationships | Nonexistent ID, disallowed relationship, nested object missing field |
| JSON | Syntax error, wrong type, unknown field, empty body |
| Unicode | Vietnamese characters, emoji, combining characters, special whitespace |
| State | Closed, deleted, or concurrently updated resource |

Beyond error contents, each test should confirm:

- HTTP status and Content-Type match the contract.
- Error codes are stable and field paths are accurate.
- Responses do not leak stack traces or sensitive data.
- No entity is created, no entity is partially updated, and no unintended side effects occur.
- Valid requests continue to function normally.
- Results do not depend on JSON field ordering.
- Validation errors can be returned together when safe and helpful.

## 8. Common Implementation Pitfalls

**Annotations exist yet the API still saves invalid data:** check the validation dependency, validator configuration, and whether Spring Data REST invokes validation on beforeCreate/beforeSave.

**POST is properly rejected yet PUT still saves invalid data:** the validator may only be attached to beforeCreate. Check update events as well.

**Validator tests pass yet HTTP tests fail:** the validator is not registered on repository events or the actual endpoint uses a different write path.

**Responses only contain generic messages:** standardize field errors, error codes, and object-level errors; do not force clients to parse prose to determine causes.

**Database errors return 500:** identify constraints and translate them into intentional business errors. Handle only known constraints; unknown persistence errors should still be logged as server errors.

**PATCH skips cross-field rules:** validate the final state after applying the patch, not just the JSON fragment.

**Data is written even though the response reports an error:** check transaction boundaries, event listeners, and side effects. Tests must re-read the repository after failed requests.

**Tests only check status codes:** add assertions for error schemas, unchanged data, and absence of side effects.

## 9. Pre-Release API Checklist

1. Every required field and data limit has server-side rules.
2. Cross-field rules have clear validators or domain logic.
3. Validators are registered for both create and update where needed.
4. The database protects invariants that must hold under concurrent requests.
5. The API has consistent status code conventions for validation, conflicts, authentication, and system errors.
6. Error bodies include stable error codes, field paths, and appropriate messages.
7. Clients do not have to parse prose messages to identify errors.
8. Stack traces, SQL, and sensitive rejected values are never returned.
9. POST, PUT, and PATCH all have invalid-data tests.
10. Tests confirm data is not partially written when validation fails.
11. Tests cover nested objects, boundaries, null, missing fields, and Unicode data.
12. Tests cover unique constraints and concurrent requests when invariants require it.
13. Media types and error responses have been verified with real Accept headers.
14. Valid requests are still saved and return responses matching the contract.

## Conclusion

Validation in Spring Data REST must be wired properly into the repository lifecycle and provide a clear error contract to clients. Bean Validation fits per-field constraints; repository event validators and domain logic handle business rules; database constraints protect invariants against concurrent contention.

Testing should not stop at verifying HTTP 400. Confirm that error bodies are usable, data is not partially persisted, side effects do not occur, and valid requests still succeed. Only when these validation layers are verified together can the API reject invalid data predictably and safely for integrating clients.
