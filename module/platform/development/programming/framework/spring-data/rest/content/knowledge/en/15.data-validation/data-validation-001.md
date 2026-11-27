# Distinguishing JSON Syntax Validation, Data Constraints, and Business Rules

## 1. Why Separate Validation Layers?

A JSON request can be syntactically valid and still fail to convert into a Java object, violate a field constraint, or break a business rule. These errors occur at different times and need to be handled at the appropriate layer.

For example, a client sends a request to create an order:

~~~~json
{
  "customerId": 42,
  "quantity": 0,
  "unitPrice": -10,
  "deliveryDate": "2026-02-01"
}
~~~~

The JSON above is syntactically valid. The values might even deserialize into their corresponding Java types. However, a quantity of 0 and a negative unitPrice may violate data constraints; deliveryDate may violate a business rule if the delivery date is in the past or the order is in a state that does not allow delivery.

A system should distinguish between:

1. **Syntax and binding validation:** Is the body valid JSON and can it be converted into the data type expected by the endpoint?
2. **Data constraints:** Do the bound values satisfy constraints on nullability, length, format, range, and structure?
3. **Business rules:** Is the operation valid given the current state and context of the system?
4. **Persistence constraints:** Can the database maintain data integrity when writing?

These layers complement one another. You should not use a regex to solve business rules, nor should you rely entirely on database exceptions to guide the client on how to fix a request.

## 2. Layer 1 — JSON Syntax, Media Type, and Data Binding

At the first layer, the server reads the request body and converts the JSON into an object or data structure. In Spring MVC, this is handled by HttpMessageConverter; Jackson is typically the JSON converter used in Spring Boot.

A request can fail at the following steps:

| Issue | Example | Common Outcome |
|---|---|---|
| Invalid JSON syntax | Missing bracket, trailing comma, unclosed string | Unable to parse body |
| Wrong JSON root type | Endpoint expects an object but receives an array or scalar | Unable to deserialize into the target type |
| Incompatible field type | age is a number but client sends "twenty" | Type conversion error |
| Malformed date value | LocalDate expects a date but receives an unparseable string | Deserialization error |
| Unsupported Content-Type | Sending XML to an endpoint that only accepts JSON | 415 Unsupported Media Type |
| Unsupported Accept | Client requests a response media type the server cannot produce | 406 Not Acceptable |

Example of a syntactically invalid body:

~~~~json
{
  "name": "Alice",
  "age": 25,
}
~~~~

The trailing comma after 25 makes the JSON invalid under standard syntax. Jackson cannot create a Person object from this body.

Example of valid JSON with a wrong data type:

~~~~json
{
  "name": "Alice",
  "age": "twenty"
}
~~~~

The JSON parser can read the document, but the binder cannot convert the string twenty into an integer if the age field is an Integer. This is a deserialization/binding error, not a Bean Validation error.

Another example: the body may be valid JSON and every field may parse successfully, but a required field is missing. If the constructor or Java type allows default/null values, the request can pass the binding step and only be caught in the subsequent validation step.

### Media type checking

The client should declare the appropriate Content-Type:

~~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json
~~~~

Content-Type describes the format of the outgoing request body. Accept describes the response format the client wants to receive. These two headers serve different purposes.

### Handling binding errors in Spring MVC

In custom controllers, Spring Framework reads and deserializes the body into the @RequestBody parameter. Parse or conversion errors are typically represented by HttpMessageNotReadableException and return 400 Bad Request under default exception handling.

Example:

~~~~java
@PostMapping("/people")
public Person create(@RequestBody PersonInput input) {
    return service.create(input);
}
~~~~

If the JSON is malformed or a field has an unconvertible type, the method may never be invoked because message conversion failed beforehand.

Do not catch all parse errors and return a generic message claiming the data violated a business rule. Distinguish an unreadable body from a valid object that fails to satisfy business conditions.

## 3. Layer 2 — Data Constraints with Bean Validation

After the JSON has been deserialized, Bean Validation checks the object against declared constraints. In modern Spring Boot, annotations usually reside in the jakarta.validation.constraints package.

Common constraints:

| Annotation | Check |
|---|---|
| @NotNull | Value must not be null |
| @NotBlank | String must not be null, empty, or whitespace-only |
| @NotEmpty | String, collection, map, or array must not be empty |
| @Size(min, max) | Limits length or number of elements |
| @Min / @Max | Limits integer numbers by min/max |
| @DecimalMin / @DecimalMax | Limits decimal numbers |
| @Positive / @PositiveOrZero | Number must be positive or non-negative |
| @Email | Checks basic email format |
| @Pattern | Checks a string against a regular expression |
| @Past / @Future | Checks that a date/time value is in the past or future |

Example request DTO:

~~~~java
public record PersonInput(
        @NotBlank
        @Size(max = 80)
        String name,

        @NotNull
        @Min(18)
        Integer age,

        @Email
        String email
) {
}
~~~~

A syntactically valid JSON body can still be rejected if name contains only whitespace, age is less than 18, or email has an invalid format.

### Triggering validation in an MVC controller

Use @Valid or @Validated on the @RequestBody parameter:

~~~~java
@PostMapping("/people")
public Person create(
        @Valid @RequestBody PersonInput input) {

    return service.create(input);
}
~~~~

When a constraint fails and the controller does not declare Errors or BindingResult immediately after the validated parameter, Spring MVC by default throws MethodArgumentNotValidException and returns 400 Bad Request.

If you want to handle errors manually in the controller:

~~~~java
@PostMapping("/people")
public ResponseEntity<?> create(
        @Valid @RequestBody PersonInput input,
        Errors errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(errors.getAllErrors());
    }

    return ResponseEntity.ok(service.create(input));
}
~~~~

The Errors/BindingResult parameter must immediately follow the validated object. When method validation applies to method parameters with direct constraints, Spring may throw HandlerMethodValidationException; handle the appropriate exception type for your controller signature and Spring Framework version.

### Validating nested objects

Use @Valid on nested properties to trigger validation for child objects:

~~~~java
public record AddressInput(
        @NotBlank String city,
        @NotBlank String country
) {
}

public record PersonInput(
        @NotBlank String name,

        @Valid
        @NotNull
        AddressInput address
) {
}
~~~~

Without cascade validation, constraints inside AddressInput may not be checked when validating PersonInput.

### Object-level validation

Some constraints involve multiple fields, such as endDate having to be after startDate. This is neither a JSON syntax error nor a simple single-field constraint.

You can create a class-level constraint using a custom annotation and ConstraintValidator, or write a Spring Validator:

~~~~java
public class BookingValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingInput.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingInput input = (BookingInput) target;

        if (input.startDate() != null
                && input.endDate() != null
                && input.endDate().isBefore(input.startDate())) {
            errors.rejectValue(
                    "endDate",
                    "booking.endDate.beforeStartDate",
                    "End date must be after start date"
            );
        }
    }
}
~~~~

This is still input data validation. If the rule needs to read order status, user permissions, or data from multiple aggregates, it should be moved to the business layer.

### Validation groups

A field may have different requirements during creation versus update. Bean Validation supports groups to select the set of constraints applied to each scenario.

Example:

~~~~java
public interface Create {}
public interface Update {}

public class PersonInput {

    @NotBlank(groups = Create.class)
    private String name;

    @NotNull(groups = Update.class)
    private Long id;
}
~~~~

In a custom controller, you can use @Validated(Create.class) or @Validated(Update.class). With Spring Data REST, check how event validators are invoked and how groups are selected in your project version; do not assume groups are automatically chosen by HTTP method unless the application has configured that.

## 4. Validation in Spring Data REST

Spring Data REST exposes repositories as REST resources. For POST, PUT, or PATCH operations, the request is converted into a domain object and passes through the repository lifecycle.

Spring Data REST provides a mechanism to attach a Spring Validator to repository events. Current documentation supports two registration approaches.

### Approach 1 — Naming the bean after the event

The bean name starts with the event the validator should handle. Example:

~~~~java
@Component("beforeCreatePersonValidator")
public class BeforeCreatePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getName() == null
                || person.getName().isBlank()) {
            errors.rejectValue(
                    "name",
                    "person.name.required",
                    "Name must not be blank"
            );
        }
    }
}
~~~~

The beforeCreate prefix attaches the validator to the creation event. You can use corresponding prefixes such as beforeSave to validate the entity before updating.

### Approach 2 — Manual registration via RepositoryRestConfigurer

If you want to control registration in configuration, use ValidatingRepositoryEventListener:

~~~~java
@Configuration
public class RepositoryValidationConfiguration
        implements RepositoryRestConfigurer {

    private final Validator personValidator;

    public RepositoryValidationConfiguration(
            Validator personValidator) {
        this.personValidator = personValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {

        listener.addValidator("beforeCreate", personValidator);
        listener.addValidator("beforeSave", personValidator);
    }
}
~~~~

A validator can be attached to multiple events if its logic is appropriate for those events. If create and update have different rules, use separate validators or branch intentionally.

Validation-related events include:

| Event | Timing |
|---|---|
| beforeCreate | Before the repository creates a new entity |
| beforeSave | Before the repository saves an existing entity |
| beforeLinkSave | Before saving changes to links between resources |
| afterCreate | After the create operation |
| afterSave | After the save operation |
| beforeDelete / afterDelete | Before or after the delete operation |

Use beforeCreate, beforeSave, or beforeLinkSave when you need to reject data before the corresponding operation. The after events are suitable for post-operation reactions; do not use them as the primary place to prevent invalid data that has already been saved.

### Bean Validation and Spring Validator in repository events

Bean Validation annotations describe constraints on an object, while the Spring Data REST event listener invokes registered Spring Validator instances. If you want to reuse a Bean Validation provider in repository events, you can register a compatible Spring Validator, such as LocalValidatorFactoryBean, with the event listener according to your application configuration.

Do not assume that merely adding @NotBlank or @Email to every entity will automatically run those constraints on every repository event in every Spring Data REST version. Verify that the validator is registered for the right event and domain type; write integration tests for POST, PUT, and PATCH.

## 5. Layer 3 — Business Rules

Business rules determine whether an operation is valid in the current context. Rules often depend on system state, the actor, related data, or transaction history.

Examples:

- Only an order in DRAFT status can be confirmed.
- A user may only edit profiles belonging to their own tenant.
- A shipped order cannot be cancelled.
- Cannot order a quantity exceeding sellable inventory.
- Total discount must not exceed the customer's contract limit.
- The delivery date must fall within the range supported by the shipping service.
- A locked account cannot perform money transfers.

These rules usually cannot be fully checked with @Min, @NotNull, or @Pattern, because they require reading current state and applying business logic.

### Where to place business rules?

Place rules in the domain model or application/service layer, where transactions can be controlled and the required data can be accessed.

Example:

~~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final InventoryService inventory;

    @Transactional
    public Order confirm(Long orderId, User currentUser) {

        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (!order.belongsTo(currentUser.tenantId())) {
            throw new AccessDeniedException("No permission on this order");
        }

        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new InvalidOrderStateException(
                    "Only draft orders can be confirmed"
            );
        }

        inventory.reserve(order.getItems());
        order.confirm();

        return orders.save(order);
    }
}
~~~~

The service checks permissions and state, calls the domain method to transition state, and then persists within a transaction. If a condition is not met, the operation is rejected before writing.

With pure Spring Data REST endpoints, repository event handlers can check or adjust entities at lifecycle events. However, event handlers do not automatically turn a sequence of multi-repository operations into a use case with clear transaction boundaries and ordering. For critical workflows such as payment, order placement, or complex state transitions, a custom controller calling an application service is usually easier to control.

### Do not confuse validation with authorization

A request may be syntactically valid and satisfy all constraints, yet the caller still lacks permission to perform the operation. For example, a user sends a valid Long customerId, but that customer belongs to another tenant.

Authorization must be checked against the security context and trusted server data. Do not rely on client-supplied fields to assert permissions. Returning an "invalid data" error instead of "forbidden/unauthorized" can also distort semantics and obscure security issues.

## 6. Layer 4 — Database Constraints

Database constraints protect integrity at write time, even when data arrives from multiple threads or multiple applications.

Common types:

| Database constraint | Protection |
|---|---|
| NOT NULL | Column cannot be null |
| UNIQUE | Value or combination of values cannot be duplicated |
| PRIMARY KEY | Unique identifier for a row |
| FOREIGN KEY | Referenced relationship must be valid |
| CHECK | Value must satisfy a conditional expression |
| EXCLUSION or specialized constraints | Prevents conflicting data combinations depending on database capabilities |

Example:

~~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~~

Database constraints are the final line of defense. They are especially important for unique constraints because two concurrent requests can both pass an "already exists" check in the application before either request writes data.

For example, a service checking that an email is unused before inserting still has a race condition if two requests run concurrently. Only a database unique constraint guarantees that two records cannot share the same email. The application needs to catch and translate integrity errors into an appropriate response.

Do not confuse @Column(nullable = false) with Bean Validation @NotNull. The JPA annotation can affect mapping/schema generation; it does not automatically replace request validation. If you want early error reporting, use appropriate Bean Validation; if you want storage-level guarantees, keep the constraint in the database.

## 7. How Does a Request Flow Through Validation Layers?

A POST or PUT flow in an MVC controller can be visualized as:

~~~~text
HTTP request
    |
    v
Check Content-Type / select message converter
    |
    v
Parse JSON and deserialize into DTO/object
    |
    +-- Invalid JSON or binding failure --> request read error
    |
    v
Bean Validation (@Valid / @Validated)
    |
    +-- Constraint failure ---------------> validation error
    |
    v
Application service / domain rules
    |
    +-- Invalid state or unauthorized ----> business/authorization error
    |
    v
Repository / transaction
    |
    v
Database constraints
    |
    +-- NOT NULL / UNIQUE / FK / CHECK violation --> integrity error
    |
    v
Commit and return response
~~~~

With Spring Data REST, after the body is read and converted into a domain object, repository events such as beforeCreate or beforeSave are the integration points for validators. If you need to control a multi-step business workflow, you can use a custom controller/application service instead of letting repository events carry the entire use case.

If one layer fails, subsequent steps must not proceed in a way that leaves partial state. For multi-step operations, use transactions and ensure changes are committed or rolled back as an appropriate unit.

## 8. Example Error Classification for the Same Endpoint

Suppose a booking creation endpoint receives:

~~~~json
{
  "customerId": 10,
  "startDate": "2026-12-10",
  "endDate": "2026-12-08",
  "guestCount": 0
}
~~~~

| Check | Result |
|---|---|
| JSON syntax | Valid |
| Data binding | May succeed if fields have types Long, LocalDate, and Integer |
| Bean Validation | guestCount = 0 may violate @Min(1) |
| Object-level validation | endDate before startDate violates object-level constraint |
| Business rule | customer may be blocked or not allowed to book during that period |
| Database constraint | customer_id may violate foreign key if customer does not exist |

If the body is changed to:

~~~~json
{
  "customerId": "ten",
  "startDate": "not-a-date"
}
~~~~

then the error occurs at parse/binding before Bean Validation or the business service is called.

If the body parses successfully and guestCount is valid, but customer does not belong to the current tenant, this is an authorization/business context error, not a JSON error.

## 9. Designing Clear Error Responses

Clients need to know which layer failed and which field needs fixing. Standardize error responses instead of returning stack traces or database SQL statements.

One possible structure:

~~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "errors": [
    {
      "field": "guestCount",
      "code": "Min",
      "message": "Guest count must be at least 1"
    }
  ]
}
~~~~

Errors can be grouped into:

- **Malformed request:** body cannot be parsed or deserialized.
- **Constraint violation:** field or object fails Bean Validation.
- **Business conflict:** operation is invalid in the current state, such as an already shipped order.
- **Authorization failure:** caller lacks permission on the resource or operation.
- **Persistence integrity failure:** violation of unique, foreign key, not-null, or check constraint.

Status codes must be consistent with the API contract. 400 is commonly used for unreadable requests or validation failures; 403 for forbidden access; 404 when a resource does not exist or is hidden by policy; 409 for state conflicts; 412 is usually reserved for preconditions such as ETag mismatch. Database errors should be mapped contextually rather than exposing constraint names or SQL.

In Spring MVC, @RestControllerAdvice can be used to standardize MethodArgumentNotValidException, HttpMessageNotReadableException, business errors, and integrity errors. With Spring Data REST, inspect the default exception handlers and add compatible handling if you want responses consistent with custom controllers.

## 10. Testing Each Layer Independently and Integration Testing

A good test suite should verify both the error cause and that no invalid data is persisted.

### Syntax and binding tests

- Malformed JSON is rejected.
- Fields with wrong types are rejected.
- Unparseable dates are rejected.
- Unsupported Content-Type is rejected.
- Controller/service is not invoked when message conversion fails.

### Bean Validation tests

- Null, empty string, and whitespace-only string are properly distinguished.
- Length, numeric, and pattern limits work.
- Nested objects are cascade-validated.
- Class-level constraints detect invalid relationships between fields.
- Create/update use the proper validation groups.

### Business rule tests

- Only permitted states perform transitions.
- Users cannot access data outside their tenant.
- Out-of-stock orders cannot be confirmed.
- Failures mid-way through multi-step use cases roll back the transaction.
- The same business rule is enforced whether invoked from REST, batch, or message consumer.

### Database constraint tests

- Unique constraints prevent duplicate writes under concurrent requests.
- Foreign keys reject nonexistent references.
- Check constraints reject out-of-range values.
- The application translates persistence exceptions into stable error responses.

With Spring Data REST, write dedicated integration tests for registered validator events: POST must trigger beforeCreate, and PUT/PATCH must trigger beforeSave according to the corresponding repository flow. Do not just unit test a Validator and assume the endpoint has wired the validator properly.

## 11. Choosing the Right Place for Each Check

| Question | Appropriate Layer |
|---|---|
| Is the body valid JSON? | JSON parser / HttpMessageConverter |
| Can this string be converted to LocalDate? | Data binding / Conversion |
| Is the name empty or too long? | Bean Validation |
| Is the end date after the start date? | Class-level validation or domain rule depending on nature |
| Is the user allowed to edit this resource? | Authorization / security policy |
| Is the order in a state that allows confirmation? | Domain/application service |
| Can two concurrent requests create duplicate order numbers? | Database unique constraint and conflict handling |
| Does the related resource exist? | Business/service validation and foreign key |
| Is a multi-step use case committed atomically? | Transaction boundary |

A rule may need to appear at more than one layer for different purposes. For example, quantity greater than 0 can be checked early with @Min for a friendly response, while also protected by a CHECK constraint to preserve data integrity when other write paths exist.

## 12. Conclusion

JSON syntax checking and data binding confirm that the request can be read into the data types expected by the endpoint. Bean Validation checks field and object constraints such as nullability, length, format, range, and cross-field relationships. Business rules decide whether an operation is valid given actual state and context. Database constraints protect integrity at save time, even under concurrent write paths.

In Spring Data REST, you can attach a Spring Validator to events such as beforeCreate, beforeSave, and beforeLinkSave using bean names or RepositoryRestConfigurer. In custom MVC controllers, @Valid/@Validated triggers Bean Validation after deserialization. Keep business rules in the domain/service, use transactions for multi-step use cases, and keep critical constraints in the database. With clear layering, errors are easy to diagnose, responses are easy to standardize, and different write paths can uphold the same data contract.

## References

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — ValidatingRepositoryEventListener API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/ValidatingRepositoryEventListener.html)
- [Spring Framework — @RequestBody and message conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
