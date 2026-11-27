# Capabilities and Limitations of Metadata for Validation, Authorization, and Business Rules

## Objectives

Metadata helps clients discover an API and understand the shape of data exposed by Spring Data REST. It can describe resources, properties, REST transitions, projections, and JSON structure. As a result, frontends, API discovery tools, or documentation can determine which endpoints to call and how to prepare payloads.

However, metadata is descriptive information published to clients. It does not enforce rules on the server. Three responsibilities must be distinguished:

- **Validation:** does the submitted data have the right structure, format, and constraints?
- **Authorization:** is the current principal permitted to read or perform an operation on a specific resource?
- **Business rules:** is the operation valid given domain state, relationships, and invariants?

ALPS and JSON Schema help describe the contract. Spring `Validator`/Bean Validation checks data. Spring Security decides permissions. Application services and domain models protect business rules.

## 1. What Is Metadata in Spring Data REST?

Spring Data REST inspects repositories and domain models to publish a hypermedia-driven REST API. Alongside resources and links, an application can expose metadata so clients can discover API semantics and structure.

Two important metadata formats are:

- **ALPS (Application-Level Profile Semantics):** describes the semantics of representations and the exposed REST transitions.
- **JSON Schema:** describes data structure, property types, and certain characteristics of a representation.

A root resource typically has a `profile` link:

~~~json
{
  "_links": {
    "people": {
      "href": "https://api.example.com/people"
    },
    "profile": {
      "href": "https://api.example.com/profile"
    }
  }
}
~~~

The client follows the `profile` link to discover metadata. From there, it can locate the profile for a repository, such as `/profile/people`. Actual URIs must be obtained from server hypermedia links; the example above is illustrative only.

## 2. ALPS Describes Properties and REST Transitions

Spring Data REST provides an ALPS document for every exported repository. ALPS can describe resource properties and REST transitions such as collection `GET`, item `GET`, `POST`, `PUT`, `PATCH`, or `DELETE`.

Abridged example of ALPS descriptors:

~~~json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person-representation",
      "descriptors": [
        {
          "name": "firstName",
          "type": "SEMANTIC"
        },
        {
          "name": "lastName",
          "type": "SEMANTIC"
        }
      ]
    },
    {
      "id": "create-people",
      "name": "people",
      "type": "UNSAFE",
      "rt": "#person-representation"
    },
    {
      "id": "get-people",
      "name": "people",
      "type": "SAFE",
      "rt": "#person-representation"
    }
  ]
}
~~~

These descriptors tell clients several things:

- `person-representation` describes the properties of a `Person` representation.
- `firstName` and `lastName` are semantic descriptors of data.
- `get-people` describes a transition to read the collection.
- `create-people` describes a transition to create a resource and its associated representation.

ALPS classifies hypermedia controls with common types:

| Type | General Meaning |
|---|---|
| `SEMANTIC` | Semantic property or data element in a representation |
| `SAFE` | Safe transition that does not modify server state, typically `GET`/`HEAD` |
| `IDEMPOTENT` | Transition that may modify state where repeating the same request has idempotent semantics, typically `PUT`/`DELETE` |
| `UNSAFE` | Transition that may modify state and lacks idempotent semantics, typically `POST` |

These types describe the semantics of HTTP operations. `UNSAFE` does not mean an operation is forbidden or requires elevated privileges; `SAFE` likewise does not mean everyone is allowed to read. They are not roles, permissions, or policies.

## 3. JSON Schema Describes Data Structure

Spring Data REST supports JSON Schema as another form of metadata. Clients can request the schema from a repository's profile link using media type `application/schema+json`.

Example request:

~~~http
GET /profile/people
Accept: application/schema+json
~~~

The URI must be taken from the corresponding profile link in the running API. An illustrative schema might look like:

~~~json
{
  "title": "Person",
  "type": "object",
  "properties": {
    "firstName": {
      "type": "string",
      "readOnly": false
    },
    "lastName": {
      "type": "string",
      "readOnly": false
    },
    "createdAt": {
      "type": "string",
      "format": "date-time",
      "readOnly": true
    }
  }
}
~~~

A schema can help clients:

- Display a list of properties and data types.
- Select appropriate inputs, such as text, number, date-time, or URI.
- Distinguish certain read-only fields from editable fields.
- Generate documentation, forms, or client-side JSON structure validation.
- Write contract tests based on the advertised data shape.

The example only illustrates the structure. Actual schemas are generated from the domain model and application configuration; property sets, formats, descriptors, and constraint expressiveness can vary by version.

### Schema Is Not a Full Copy of Validation Logic

JSON Schema can express many structural constraints, but an API-published schema does not necessarily reflect every rule running on the server.

Rules such as the following usually require additional logic:

- Email must be unique in the database.
- End date must be after start date.
- An `Order` can only be confirmed while still in `DRAFT` state.
- Users may only modify data belonging to their own tenant.
- Order quantity cannot exceed available inventory at commit time.
- A value is only valid in combination with the current role or state.

A schema can help clients catch simple errors before sending requests, but cannot replace checks against live data and current state on the server.

## 4. How Far Can ALPS and JSON Schema Assist Clients?

Metadata is most useful when treated as part of API discovery and contract documentation.

For example, a frontend can:

1. `GET` the root resource.
2. Follow the `profile` link to find the repository's metadata.
3. Read ALPS to learn which properties and transitions the resource has.
4. Request JSON Schema to learn data types and field structure.
5. Use that information to build forms or display guidance.
6. Send requests to resource/transition links advertised by the server.
7. Handle success responses or validation/authorization errors from the server.

Clients can use metadata to improve UX and reduce malformed requests. However, clients must never treat metadata as proof that an operation is guaranteed permitted or valid at write time.

## 5. Metadata Does Not Enforce Server-Side Validation

Suppose JSON Schema describes `firstName` as a string. A client can render a text input and reject blank values before submitting. Yet another client can bypass the form, craft an HTTP request directly, or call the API via `curl`.

Therefore, the server must validate requests independently.

### Bean Validation

Constraints can be declared on entities or DTOs:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class CreatePersonRequest {

    @NotBlank
    private String firstName;

    @NotBlank
    private String lastName;

    @Email
    private String email;

    // getters and setters
}
~~~

Annotations express simple constraints:

- `@NotBlank`: the string must contain non-whitespace characters.
- `@Email`: validates email format according to the configured validator.

For a custom Spring MVC controller, you can trigger validation on a request DTO with `@Valid`:

~~~java
@PostMapping("/people")
public ResponseEntity<PersonResponse> create(
        @Valid @RequestBody CreatePersonRequest request) {

    PersonResponse response = personService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
}
~~~

For repository REST endpoints, you can register a Spring `Validator` on repository events:

~~~java
@Configuration
public class RepositoryValidationConfig
        implements RepositoryRestConfigurer {

    private final PersonValidator personValidator;

    public RepositoryValidationConfig(PersonValidator personValidator) {
        this.personValidator = personValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeCreate", personValidator);
        listener.addValidator("beforeSave", personValidator);
    }
}
~~~

The validator inspects the target and records errors into `Errors`:

~~~java
@Component
public class PersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getFirstName() == null
                || person.getFirstName().isBlank()) {
            errors.rejectValue(
                "firstName",
                "person.firstName.required",
                "First name is required"
            );
        }
    }
}
~~~

Register validators for the proper lifecycle events and domain types. Validation errors should be translated into error responses according to the active Spring Data REST/Spring MVC mechanism. Do not assume JSON Schema invokes validators automatically or that requests will be rejected merely because the client received a schema.

## 6. Structural Validation vs. Business Validation

Separate at least two layers:

| Check Type | Examples | Appropriate Place |
|---|---|---|
| Structure/format | Required fields, valid email format, numbers within range | Bean Validation or request validator |
| Business rules | Order can only be confirmed when eligible, quantity does not exceed stock | Application service/domain model, transactional when needed |

Some simple constraints may appear in the schema or be pre-checked by clients. However, rules depending on the database, time, state, or other users' data must be re-evaluated on the server at processing time.

For example, a client reads inventory as `5` and submits an order for `4` items. Another client may have ordered `3` items moments earlier. Client-side checks based on stale inventory numbers are insufficient to guarantee the operation remains valid. The server must check and update inventory consistently, typically within a transaction with appropriate concurrency control.

## 7. Metadata and Authorization Are Separate Concerns

Authorization determines what the current principal is permitted to do. Metadata describes the API and the transitions a client can discover.

ALPS may describe an operation as `UNSAFE`, or a HAL response may contain a link to an operation. That information does not prove the current user has permission to execute the operation.

For example, a client sees a collection link:

~~~json
{
  "_links": {
    "people": {
      "href": "https://api.example.com/people"
    }
  }
}
~~~

The client can attempt a `POST` to the collection, yet the server must still authenticate and check permissions. Hiding a link in a response can help the UI omit unavailable buttons; it is not a standalone security boundary.

### Enforcing Permissions in Spring Security

HTTP requests can be protected by method and path:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/people/**")
                .hasAuthority("people:read")
            .requestMatchers(HttpMethod.POST, "/people")
                .hasAuthority("people:create")
            .requestMatchers(HttpMethod.PUT, "/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.PATCH, "/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.DELETE, "/people/**")
                .hasAuthority("people:delete")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

This is an illustrative URL-level authorization example. Applications must configure authentication, CSRF, CORS, and remaining matchers according to their actual architecture.

### Per-Resource Permissions

Permissions can depend on individual records, not only HTTP methods and URLs:

- Users may only edit `Person` records belonging to their own tenant.
- Only the creator or a manager may edit a record.
- Only HR may view the `salary` field.
- Only authorized users may transition an `Order` to `APPROVED`.

Method security can be used at the service layer:

~~~java
@Service
public class PersonService {

    @PreAuthorize("hasAuthority('people:update')")
    public PersonResponse update(Long id, UpdatePersonRequest request) {
        // Load entity and verify ownership/tenant policy.
        // Apply allowed changes and save.
        return null;
    }
}
~~~

`@PreAuthorize` checks the authority before invoking the method. Ownership/tenant verification for the entity itself must still be implemented with appropriate logic. A generic URL rule cannot know on its own whether a user is allowed to edit a specific record.

## 8. Metadata Does Not Enforce Business Rules

Business rules are conditions determining whether an action is valid in the domain. Examples:

- Cannot pay for an `Order` that has already been canceled.
- Cannot transition status from `DELIVERED` back to `DRAFT`.
- Cannot order a quantity greater than available stock.
- Cannot approve a request created by the approver themselves.
- Start date must precede end date.
- Total discount must not exceed the contract limit.

Metadata may describe a `status` field as a string or list some static values. Whether a state transition is valid depends on the current state, principal, related data, and execution time.

Protect invariants in the application service/domain model:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Order approve(Long id, User currentUser) {
        Order order = repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException());

        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only draft orders can be approved"
            );
        }

        if (order.getCreatedBy().equals(currentUser.getId())) {
            throw new AccessDeniedException(
                "The creator cannot approve this order"
            );
        }

        order.setStatus(OrderStatus.APPROVED);
        return repository.save(order);
    }
}
~~~

This is an abridged example. In a real application, retrieve the principal from the security context, map errors via appropriate exception handlers, and apply concurrency/transaction controls required by the domain.

The key point is that a request must not be allowed to dictate the final state simply by sending `"status": "APPROVED"`. The service/domain must verify that both the transition and the actor are valid.

## 9. Metadata Can Be Customized or Incomplete

Metadata reflects what the application publishes at request time. It can be influenced by:

- Which repositories are exported.
- Domain models and associations.
- Registered projections.
- Spring Data REST configuration.
- Customizations of representations or controllers.
- Library versions and requested media types.

ALPS can include additional descriptions via message properties such as `rest.description.*`. These descriptions help explain resources and fields in human-readable language. They remain documentation only.

Example:

~~~properties
rest.description.person=A collection of people
rest.description.person.firstName=Person's first name
rest.description.person.lastName=Person's last name
~~~

The descriptions above help clients understand field meanings. Changing `rest.description.person.firstName` does not add `@NotBlank`, create a unique constraint, or grant field access permissions.

If an API has custom endpoints or rules not captured in metadata, publish supplemental contracts/documentation. Clients should handle actual responses and HTTP errors rather than assuming metadata describes every possible behavior.

## 10. Responsibility Matrix

| Question | Metadata | Validation | Authorization | Business rules |
|---|---|---|---|---|
| What fields does the resource have? | Described via ALPS/Schema | Not its primary purpose | Not its primary purpose | Not its primary purpose |
| What type is a field? | Described by JSON Schema | Validates input type/format | Does not decide | Domain may use the type |
| Is a field required? | May be described if schema expresses it | Server must validate | Does not decide | May be an invariant |
| Who can read/modify? | Does not decide | Does not decide | Spring Security/policy | May check actor in use case |
| Is the operation valid in the current state? | Not guaranteed to describe fully | Partial only | May check permissions | Decided by service/domain |
| Can the client build forms? | Yes, aids discovery | Can assist UX | Can hide affordances | Can display guidance |

## 11. Workflow for Designing and Using Metadata Safely

When building a Spring Data REST API or client:

1. Discover the root resource and follow the `profile` link advertised by the server.
2. Read ALPS to understand resources, fields, and documented transitions.
3. Request JSON Schema using `Accept: application/schema+json` if supported by the API.
4. Use the schema to build forms, check structure, and provide early user feedback.
5. Enforce validation on the server using Bean Validation, Spring `Validator`, or appropriate request DTOs.
6. Protect endpoints with Spring Security; enforce per-resource/tenant permissions when needed.
7. Place invariants and state transitions in the application service/domain model.
8. Handle validation errors, `401`/`403`, and business errors according to the response contract.
9. Test HTTP requests directly, including crafted requests that bypass the client UI.
10. Update metadata and documentation whenever the API contract changes.

## 12. Testing Metadata Boundaries

Maintain independent test groups:

- **Metadata tests:** root resource has a `profile` link; ALPS and JSON Schema return proper media types and describe expected fields.
- **Validation tests:** requests missing required fields or having invalid formats are rejected even when calling endpoints directly.
- **Authorization tests:** unauthorized users receive `403` when calling URLs directly, even when crafting requests for links hidden by the UI.
- **Resource policy tests:** a user in tenant A cannot modify a resource belonging to tenant B.
- **Business rule tests:** operations violating state rules or invariants are rejected even if the payload conforms to JSON Schema.
- **Concurrency tests:** when rules depend on stock or concurrently modified state, test transactions and suitable optimistic/pessimistic locking.

Do not only verify that the frontend hides a button or that JSON Schema marks a field `readOnly`. Send requests directly to the server to prove actual enforcement works.

## 13. Common Misconceptions

- **ALPS marks an operation `UNSAFE` so users cannot call it.** `UNSAFE` describes transition semantics, not access permissions.
- **A link exists in HAL so everyone is allowed to use it.** The server must still enforce authorization on every request.
- **No link means the data is protected.** Clients can still call URIs directly; security must be enforced on the server.
- **JSON Schema describes fields so the server automatically validates every rule.** Schema is just metadata; requests must be validated in the server pipeline.
- **A `readOnly` field in the schema is a security barrier.** Clients can ignore the schema and submit any payload; the server must control binding and write permissions.
- **Metadata describes `status` so clients can change `status` directly.** State transitions must be checked in the domain/service.
- **Validation replaces authorization.** Valid data does not mean the caller is authorized to perform the action.
- **Authorization replaces business rules.** Authorized users can still submit operations that violate state or invariants.
- **Documentation properties alter API behavior.** `rest.description.*` adds descriptions; it does not add constraints or permissions.

## 14. Key Takeaways

- Spring Data REST provides ALPS and JSON Schema to discover resource semantics and structure.
- ALPS describes properties and transition types; JSON Schema describes data shape.
- Metadata assists form generation, documentation, and client discovery, but is not an enforcement mechanism.
- Validation must run on the server; schema/client-side validation only catches simple errors early.
- Authorization must be enforced with Spring Security and per-resource policies when needed.
- Business rules and state transitions must be protected in the application service/domain model.
- An advertised link or descriptor does not prove the current principal has permission to execute an operation.
- Test with direct HTTP requests to prove validation, authorization, and business rules hold when clients bypass metadata.

## References

- [Spring Data REST Reference — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST Reference — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST Reference — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [JSON Schema Specification](https://json-schema.org/specification)
