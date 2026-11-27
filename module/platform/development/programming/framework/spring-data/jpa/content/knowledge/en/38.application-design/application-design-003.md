# Separating Persistence Entities from DTOs and Response Models

In a Spring Data JPA application, an Entity represents state managed by the persistence layer, whereas a DTO (Data Transfer Object) represents data crossing boundaries between layers or between the API and clients. The two models serve different purposes, so Entities should not be used as the request body or JSON response for every endpoint.

Separating Entities from DTOs helps control input/output data, prevents clients from directly modifying internal fields, reduces API coupling to the database schema, and minimizes errors caused by lazy loading or relationship serialization cycles. In return, the application needs explicit mapping and appropriate data-loading timing.

A common design is: the Controller receives a request DTO, the Service validates business rules and coordinates the transaction, the Repository reads/writes Entities, and a Mapper converts Entities into response DTOs. For list queries or screens needing only a subset of fields, projections can fetch data directly in the output shape.

## 1. How Do Entities, DTOs, and Response Models Differ?

| Model | Purpose | Example |
|---|---|---|
| JPA Entity | Represents state managed by the persistence provider and mapped to tables | Customer, PurchaseOrder |
| Request DTO | Describes data a client is permitted to send for an operation | CreateCustomerRequest |
| Command | Describes the business intent the service needs to execute | CreateCustomerCommand |
| Response DTO | Describes data the endpoint is permitted to return | CustomerResponse |
| Projection | Retrieves only the subset of attributes needed for a read query | CustomerSummary |
| Domain model | Models business rules and behavior; may align with or be separate from the Entity depending on architecture | Customer aggregate |

DTOs do not necessarily have to be separate classes for every case, but requests and responses usually have different requirements. For example, when creating a customer, the client sends a raw password; the server stores a password hash; the response must never return the password or the hash.

An Entity may contain primary keys, versions, JPA relationships, internal persistence fields, business states, and sensitive data. A response model should contain only information that the API intentionally exposes. Do not let adding a field to an Entity automatically cause that field to appear in JSON.

## 2. Why Should You Not Return Entities Directly from a Controller?

Returning Entities directly can cause several problems:

1. **Leaking internal data:** Entities may contain passwordHash, internalNote, moderation status, or information that must not be disclosed.
2. **API coupled to schema:** changing mappings or renaming Entity properties can alter the JSON contract.
3. **Lazy loading:** the serializer accesses LAZY relationships after the transaction ends and throws LazyInitializationException.
4. **N+1 queries:** the serializer iterates over a collection and triggers additional queries per Entity.
5. **Relationship cycles:** Customer has orders, and each Order has a customer; Jackson may loop infinitely or require special annotations.
6. **Mass assignment:** clients send extra Entity properties such as role, status, ownerId, or version and unintentionally alter data.
7. **Hard to version the API:** a single Entity is often shared across many use cases, whereas each endpoint needs a different data shape.

What to avoid:

~~~java
@PostMapping("/customers")
public Customer create(@RequestBody Customer customer) {
    return customerRepository.save(customer);
}
~~~

Clients can send more fields than the business operation requires. Binding an Entity directly from JSON also tightly couples the Controller to the persistence model.

A safer approach is to accept a request DTO, call the service, and return a response DTO.

## 3. Designing Entities for the Persistence Layer

Example Customer Entity containing internal data:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, unique = true, length = 254)
    private String email;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private CustomerStatus status;

    @Version
    private Long version;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(String name, String email, String passwordHash) {
        this.name = name;
        this.email = email;
        this.passwordHash = passwordHash;
        this.status = CustomerStatus.PENDING;
    }

    public void rename(String name) {
        this.name = name;
    }

    public void changeEmail(String email) {
        this.email = email;
    }

    public void activate() {
        this.status = CustomerStatus.ACTIVE;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Enum:

~~~java
public enum CustomerStatus {
    PENDING,
    ACTIVE,
    SUSPENDED
}
~~~

This is an illustrative Entity; constructors, getters, and mappings should be adjusted to fit the project. Notable points:
- passwordHash is internal persistence data.
- status is initialized according to business rules, not accepted arbitrarily from the creation request.
- version supports optimistic locking.
- The Entity provides business methods instead of letting the Controller assign every field directly.
- The Entity has a protected no-arg constructor as required by JPA.

There is no need to generate public setters for every field. Limiting mutation entry points helps protect invariants and prevents the web layer from directly altering persistence fields.

## 4. Request DTOs for Creation Operations

A request DTO contains only data the client is allowed to provide:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank
        @Size(max = 120)
        String name,

        @NotBlank
        @Email
        @Size(max = 254)
        String email,

        @NotBlank
        @Size(min = 12, max = 128)
        String password
) {
}
~~~

Validation annotations check the structural format of input data:
- NotBlank rejects null, empty strings, and whitespace-only strings.
- Email checks email formatting at the validation level.
- Size limits string length.
- The password rule here is just an example; applications need an appropriate password policy.

DTO validation does not replace business validation. For example, whether an email already exists must be checked in the service/database. A unique constraint in the database is still necessary because two concurrent requests could both pass the application check before writing.

The request DTO has no id, passwordHash, status, createdAt, or version. Clients cannot send those fields to force unintended values onto the Entity.

## 5. Response DTOs for Public Data

A response DTO describes exactly what an endpoint is permitted to return:

~~~java
import java.time.Instant;

public record CustomerResponse(
        Long id,
        String name,
        String email,
        CustomerStatus status,
        Instant createdAt,
        Long version
) {
}
~~~

The response does not contain password or passwordHash. You can include version in the response if the client needs to send it back on subsequent updates to detect stale data; otherwise, version can be kept in an ETag header or omitted publicly.

Different APIs may need different responses:
- CustomerSummary for lists.
- CustomerDetailResponse for detail pages.
- CustomerAdminResponse for admin screens.
- CustomerPublicProfile for public endpoints.

Avoid creating one giant response DTO and returning it from every endpoint. Choose data based on the use case and access permissions.

## 6. Creating Entities from Requests via the Service

Do not let the Controller instantiate an Entity directly and call the Repository. The Service is responsible for checking business rules and coordinating writes.

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;
    private final PasswordEncoder passwordEncoder;
    private final CustomerMapper mapper;

    public CustomerService(
            CustomerRepository repository,
            PasswordEncoder passwordEncoder,
            CustomerMapper mapper) {
        this.repository = repository;
        this.passwordEncoder = passwordEncoder;
        this.mapper = mapper;
    }

    @Transactional
    public CustomerResponse create(CreateCustomerRequest request) {
        if (repository.existsByEmailIgnoreCase(request.email())) {
            throw new DuplicateCustomerEmailException(request.email());
        }

        String passwordHash =
                passwordEncoder.encode(request.password());

        Customer customer = new Customer(
                request.name().trim(),
                request.email().trim().toLowerCase(Locale.ROOT),
                passwordHash
        );

        Customer saved = repository.save(customer);

        return mapper.toResponse(saved);
    }
}
~~~

This example requires a PasswordEncoder bean, Repository, Mapper, and the corresponding exception. If the database has specific collation or email normalization rules, align normalization across validation, queries, and unique constraints.

The Service is responsible for:
1. Checking business conditions.
2. Hashing the password using PasswordEncoder.
3. Creating the Entity in a valid state.
4. Saving the Entity within a transaction.
5. Converting the result into a response DTO.

Never store raw passwords. Never return hashes in responses or logs.

## 7. Keep the Controller Focused on HTTP Concerns

The Controller receives the request DTO, triggers validation, invokes the service, and returns the response DTO:

~~~java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {

        CustomerResponse response = service.create(request);

        URI location = URI.create("/api/customers/" + response.id());

        return ResponseEntity.created(location).body(response);
    }
}
~~~

The Controller should not call EntityManager directly, decide between persist and merge, hash passwords, return Entities, contain logic updating multiple Repositories, or handle lazy relationships by arbitrarily invoking getters.

Business exceptions can be mapped to HTTP statuses via `@RestControllerAdvice`. Do not return stack traces or database details to clients.

## 8. What Role Does a Mapper Play?

A Mapper converts between models. It can be hand-written Java methods, MapStruct generating code at compile time, a dedicated per-use-case assembler, or direct constructor projections from queries on the read path.

A Mapper should not become a place containing critical business rules. For example, selecting ACTIVE status, verifying email, hashing passwords, or checking permissions must belong to the service/domain/security layer.

Mappers are typically suited for structural transformations:
- Customer Entity to CustomerResponse.
- Address Entity to AddressResponse.
- Request DTO to command.
- Projection to response model.

## 9. Manual Mapping

For simple response DTOs, a manual mapper is very clear:

~~~java
@Component
public class CustomerMapper {

    public CustomerResponse toResponse(Customer customer) {
        return new CustomerResponse(
                customer.getId(),
                customer.getName(),
                customer.getEmail(),
                customer.getStatus(),
                customer.getCreatedAt(),
                customer.getVersion()
        );
    }
}
~~~

Advantages:
- Easy to read and debug.
- Requires no annotation processor.
- Explicitly controls which fields are exposed.
- Easy to add simple formatting logic.

Disadvantages:
- Can become repetitive when there are many DTOs.
- When adding a field, the mapper must be updated manually.
- Mapping large nested graphs can be verbose.

For APIs with a moderate number of DTOs, manual mapping is often a good choice because it makes the contract explicit.

## 10. Mapping with MapStruct

MapStruct generates mapper implementations at compile time, avoiding runtime reflection and catching missing or mismatched mappings early.

Response mapper:

~~~java
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;

@Mapper(
    componentModel = "spring",
    unmappedTargetPolicy = ReportingPolicy.ERROR
)
public interface CustomerMapper {

    CustomerResponse toResponse(Customer customer);
}
~~~

Because CustomerResponse contains only a subset of public properties and field names match, MapStruct can map matching attributes automatically. passwordHash is absent from the response, so it is not exposed.

If field names differ:

~~~java
@Mapper(componentModel = "spring")
public interface CustomerMapper {

    @Mapping(source = "createdAt", target = "registeredAt")
    CustomerDetailResponse toDetail(Customer customer);
}
~~~

When using MapStruct:
- Configure the annotation processor in Maven/Gradle.
- Use `componentModel = "spring"` so the mapper can be injected.
- Use an appropriate `unmappedTargetPolicy` to catch unmapped fields.
- Do not let the mapper automatically map sensitive fields into DTOs.
- Inspect generated source for complex mappings.
- Use `@Mapping(ignore = true)` explicitly if the target has fields the service assigns separately.

Do not use a mapper to blindly map an entire request into an Entity and assume omitted fields will always remain safe. Map only the fields the client is allowed to modify.

## 11. Request DTOs and Commands Can Be Separated

In larger applications, a request DTO is the HTTP contract, while a command represents an internal business request.

For example:

~~~java
public record CreateCustomerCommand(
        String normalizedName,
        String normalizedEmail,
        String passwordHash
) {
}
~~~

The Controller receives CreateCustomerRequest, and the service normalizes and converts it into a command, or the application service accepts a prepared command. The domain layer does not need to depend on Jackson or Jakarta Validation annotations.

A flow can look like:

~~~text
HTTP JSON
   |
   v
CreateCustomerRequest
   |
   v
Controller + validation
   |
   v
Application Service
   |
   +--> normalize/authorize/hash
   |
   v
CreateCustomerCommand
   |
   v
Domain/Repository
   |
   v
Customer Entity
~~~

For small applications, there is no need to add a Command class if it merely duplicates the request DTO verbatim. Split them when the two models have different lifecycles, semantics, or consumers.

## 12. DTOs Are Not Always Projections

A DTO is often constructed by mapping from a loaded Entity. A projection can instruct the database to return only the columns needed for a read use case.

Example interface projection:

~~~java
public interface CustomerSummary {
    Long getId();
    String getName();
    String getEmail();
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<CustomerSummary> findByStatus(CustomerStatus status);
}
~~~

Spring Data can use projections to produce results containing only the required attributes depending on the projection/provider mechanism. Inspect the actual SQL if the goal is to reduce SELECT columns or optimize queries.

DTO projection via a JPQL constructor expression:

~~~java
@Query("""
    select new com.example.api.CustomerSummaryDto(
        c.id,
        c.name,
        c.email
    )
    from Customer c
    where c.status = :status
    order by c.name
    """)
List<CustomerSummaryDto> findSummaries(
        @Param("status") CustomerStatus status
);
~~~

The DTO constructor must have parameters in the exact matching order and types. JPQL constructor expressions use the fully qualified class name in the `new` expression.

Use projections for large lists or read-only screens when the full Entity is not needed. Use Entities when business state needs to be modified and managed by JPA dirty checking.

## 13. Nested DTOs for Entity Relationships

For example, an Order has a Customer and multiple OrderLines. The response can represent the necessary data without returning the entire Entity graph:

~~~java
public record OrderLineResponse(
        Long productId,
        String productName,
        int quantity,
        BigDecimal unitPrice
) {
}

public record OrderResponse(
        Long id,
        String orderNumber,
        String customerName,
        List<OrderLineResponse> lines
) {
}
~~~

Mapper:

~~~java
@Component
public class OrderMapper {

    public OrderResponse toResponse(PurchaseOrder order) {
        List<OrderLineResponse> lines = order.getLines().stream()
                .map(line -> new OrderLineResponse(
                        line.getProduct().getId(),
                        line.getProduct().getName(),
                        line.getQuantity(),
                        line.getUnitPrice()
                ))
                .toList();

        return new OrderResponse(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getName(),
                lines
        );
    }
}
~~~

The mapping code accesses customer, lines, and product. The required relationships must be loaded inside the transaction via fetch join, EntityGraph, or an appropriate projection query. Otherwise, the mapper may trigger LazyInitializationException or N+1 queries.

Do not expose the entire Customer or Product just to display a few fields. Nested DTOs make explicit which data belongs in the response.

## 14. Mapping Inside or Outside the Transaction?

If the mapper accesses LAZY attributes, perform the mapping within the transaction scope and ensure the query loads the necessary relationships.

For example:

~~~java
@Transactional(readOnly = true)
public OrderResponse findOrder(Long id) {
    PurchaseOrder order = repository.findWithDetailsById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

    return mapper.toResponse(order);
}
~~~

The Repository can declare an EntityGraph:

~~~java
@EntityGraph(attributePaths = {
        "customer",
        "lines",
        "lines.product"
})
Optional<PurchaseOrder> findWithDetailsById(Long id);
~~~

EntityGraph instructs the provider to load the specified relationships according to the fetch plan. Inspect the generated SQL and cardinality; fetching multiple collections can cause Cartesian multiplication or duplicate rows depending on the query.

Mapping DTOs inside the service transaction keeps the response independent of the persistence context once the Controller receives the result. The Service returns a complete DTO rather than returning an Entity with uninitialized lazy relationships to be serialized later.

## 15. Avoiding N+1 Queries When Building DTOs

N+1 happens when an initial query fetches a list of N Entities, and then the mapper accesses a LAZY relationship, triggering an extra query for each Entity.

For example:
1. One query fetches 50 Orders.
2. The mapper reads `order.getCustomer().getName()`.
3. Hibernate issues an additional query for each Customer if not already loaded.
4. Total query count can approach 1 + N.

Solutions:
- Use projections to select `customerName` directly.
- Use `@EntityGraph` for required relationships.
- Use controlled fetch joins.
- Use batch fetching when appropriate.
- Write a custom query to fetch a DTO matching the response shape.

Do not mechanically add fetch joins to every relationship. Load only the data the endpoint needs, and verify the SQL, row counts, and execution plan.

## 16. Updating Entities Using Request DTOs

For standard updates, load the managed Entity and apply only the fields permitted to change:

~~~java
public record UpdateCustomerRequest(
        @NotBlank @Size(max = 120) String name,
        @NotBlank @Email String email
) {
}
~~~

~~~java
@Transactional
public CustomerResponse update(
        Long id,
        UpdateCustomerRequest request) {

    Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

    customer.rename(request.name().trim());
    customer.changeEmail(request.email().trim().toLowerCase(Locale.ROOT));

    return mapper.toResponse(customer);
}
~~~

There is no need to construct a new Entity from the request and call `save()` to merge all state. An Entity loaded inside a transaction is managed; dirty checking synchronizes the changes on commit.

This approach preserves fields absent from the request, prevents clients from tampering with status, version, or passwordHash, lets the service enforce rules field by field, and avoids merging an incomplete object that overwrites existing data.

If status needs to change, provide a dedicated use case such as `activateCustomer()` and verify permissions and transition conditions.

## 17. PUT and PATCH Have Different Semantics

PUT usually represents replacing a resource's representation under the API contract. PATCH represents a partial change. DTOs must express those semantics clearly.

A simple DTO with nullable fields:

~~~java
public record PatchCustomerRequest(
        String name,
        String email
) {
}
~~~

cannot distinguish two cases:
- The client did not send `email`.
- The client sent `email: null`.

If null means "clear the value", a three-state representation is needed: absent, present-null, and present-value. You can use `JsonNullable` from the `jackson-databind-nullable` library or a dedicated wrapper/command.

Conceptual example with JsonNullable:

~~~java
public record PatchCustomerRequest(
        JsonNullable<String> name,
        JsonNullable<String> email
) {
}
~~~

The Service must check whether a field was provided before reading its value. Configure the Jackson module for JsonNullable and test JSON absent/null/value cases.

Do not rely on `request.email() != null` logic if the API needs to differentiate absent from explicit null. For APIs that disallow clearing email, the contract can be simplified by rejecting null.

## 18. DTO Validation and Entity Validation

Input validation and persistence constraints solve two different problems.

| Mechanism | Purpose |
|---|---|
| `@NotBlank`, `@Email`, `@Size` on request DTOs | Validate that the request has valid structure/format |
| Checks in service/domain | Protect business rules |
| `@Column(nullable = false)` | Describe mapping and schema constraints |
| Unique/FK/check constraints in the database | Protect data integrity at the database level |
| Bean Validation on Entities | Validate object constraints when the validation lifecycle is triggered |

Do not rely on `@Column(nullable = false)` to generate user-friendly error messages for clients. Likewise, do not rely on `@Valid` request DTOs to replace unique constraints, because race conditions can still occur.

The Controller can use:

~~~java
@PostMapping
public CustomerResponse create(
        @Valid @RequestBody CreateCustomerRequest request) {
    return service.create(request);
}
~~~

Use `@RestControllerAdvice` to translate validation errors and business exceptions into a consistent error response model.

## 19. Security and Mass Assignment

If JSON is bound directly to an Entity, a client can send fields outside their update permissions:

~~~json
{
  "name": "An",
  "status": "ACTIVE",
  "role": "ADMIN",
  "passwordHash": "attacker-value",
  "version": 99
}
~~~

Even if certain fields are excluded from serialization, deserialization can still accept them if the mapping allows it. Using an allow-listed request DTO ensures only intended fields are accepted.

Practices:
- Separate Create, Update, and Patch DTOs according to permissions and semantics.
- Never accept `passwordHash` from clients.
- Never let clients assign `ownerId`, `tenantId`, `role`, or sensitive `status` values directly.
- Enforce authorization in the service/use case.
- Never expose Entities via JSON.
- Do not treat `@JsonIgnore` as the sole security boundary.
- Ensure logs and error responses do not leak sensitive data.

DTOs do not automatically enforce authorization. The Service must still verify that the caller has permission to act on the specific resource.

## 20. Do Not Use @JsonIgnore as a Replacement for DTOs

An Entity property can be marked with `@JsonIgnore`:

~~~java
@JsonIgnore
private String passwordHash;
~~~

This can prevent Jackson from serializing the property under standard configurations, but it does not solve all issues:
- The Entity remains the API contract.
- Request binding may behave differently depending on annotations/configuration.
- Endpoints needing different responses still share the same Entity.
- Lazy loading and relationship cycles can still occur.
- Field-level access permissions still need separate control.

DTOs establish an explicit allow-list: whichever fields appear in the response are explicitly declared.

If an application needs to hide a couple of fields on one special endpoint, `JsonView` or Jackson annotations can be helpful, but for APIs with multiple use cases, DTOs are usually easier to understand and test.

## 21. Do Not Let Jackson Serialize Bidirectional Entity Relationships

For example:
- Customer has `List<Order>`.
- Order has `Customer`.

Serializing Customer can follow `orders`, return to `customer`, and loop repeatedly. Jackson annotations like `JsonManagedReference`/`JsonBackReference` or `JsonIdentityInfo` can be used in some cases, but those annotations still tie API serialization to the Entity graph.

Response DTOs prevent cycles by choosing a finite structure:

~~~java
public record CustomerResponse(
        Long id,
        String name,
        List<OrderSummaryResponse> orders
) {
}

public record OrderSummaryResponse(
        Long id,
        String orderNumber
) {
}
~~~

`OrderSummaryResponse` does not nest `CustomerResponse` back inside. The response structure is tailored to the endpoint's requirements without needing to mirror the full JPA relationship graph.

## 22. Projections, DTO Mapping, and Entities: Choosing by Use Case

| Requirement | Typically suitable choice |
|---|---|
| Create/update an aggregate and apply domain rules | Managed Entity inside a transaction |
| Return a small response from an already loaded Entity | Map Entity to response DTO |
| Large list needing only a few columns | Interface/constructor projection |
| Summary reports | DTO projection or native query |
| Response with nested relations | DTO mapper with an explicit fetch plan |
| Multiple APIs with different contracts over the same Entity | Separate response DTOs |
| Partial field update | Patch DTO/command applied to a managed Entity |

There is no need to map Entity to DTO and back to Entity for every operation. For update commands, loading a managed Entity and calling a domain method is usually sufficient. For large read queries, projections avoid hydrating unnecessary Entities.

## 23. Response Models and API Versioning

Entities can evolve through database migrations, while API contracts need greater stability. Response DTOs allow:
- Renaming database columns without changing JSON fields.
- Adding response fields in a controlled manner.
- Maintaining multiple API versions.
- Returning formatted or aggregated values.
- Hiding internal fields.
- Changing storage structure without coupling clients.

For example, the Entity stores `firstName` and `lastName`, while the API returns `fullName`. The mapper can combine both fields:

~~~java
public record CustomerProfileResponse(
        Long id,
        String fullName
) {
}
~~~

~~~java
public CustomerProfileResponse toProfile(Customer customer) {
    return new CustomerProfileResponse(
            customer.getId(),
            customer.getFirstName() + " " + customer.getLastName()
    );
}
~~~

If a response field is a derived value, define its format/null behavior clearly and test it to prevent unintended API changes.

## 24. Version and Optimistic Locking Through DTOs

Entities use `@Version` to detect concurrent updates. Version can be exposed in the response if the client needs to send it back during updates.

Example response containing version:

~~~java
public record CustomerResponse(
        Long id,
        String name,
        Long version
) {
}
~~~

Update request with expected version:

~~~java
public record UpdateCustomerRequest(
        @NotBlank String name,
        @NotNull Long expectedVersion
) {
}
~~~

The Service can compare `expectedVersion` with the loaded Entity's version, and still rely on JPA `@Version` to protect at the database level against races between read and commit.

A more standard HTTP approach is using ETag/If-Match. Do not directly assign a client-supplied version value onto a managed Entity to overwrite the provider-managed version. Input version is a precondition check, not an arbitrary field for the client to update.

## 25. Handling Responses After Saving an Entity

When creating an Entity, the database ID might only be assigned after persist/flush depending on the key generation strategy. If the response needs the ID, mapping after `repository.save()` is usually sufficient with IDENTITY/sequences and compatible providers; if SQL execution must be guaranteed beforehand, flush can be used.

For example:

~~~java
@Transactional
public CustomerResponse create(CreateCustomerRequest request) {
    Customer customer = new Customer(
            request.name(),
            request.email(),
            passwordEncoder.encode(request.password())
    );

    Customer saved = repository.save(customer);

    return mapper.toResponse(saved);
}
~~~

Do not call `saveAndFlush()` merely to "make sure it saves" when there is no need for an early flush. Commit still occurs at the transaction boundary; flush does not mean commit.

If the response needs data populated by database triggers/defaults, you may need to refresh or re-query after flush depending on the mapping/provider. Verify actual behavior instead of assuming every generated column is populated in the object immediately after save().

## 26. Testing DTOs and Mappers

Mappers can be unit tested independently:

~~~java
class CustomerMapperTest {

    private final CustomerMapper mapper = new CustomerMapper();

    @Test
    void mapsOnlyPublicCustomerFields() {
        Customer customer =
                new Customer("An", "an@example.com", "secret-hash");

        CustomerResponse response = mapper.toResponse(customer);

        assertEquals("An", response.name());
        assertEquals("an@example.com", response.email());
    }
}
~~~

This is an illustrative example; Customer requires getters and the corresponding fields. Tests should verify that the response does not contain `passwordHash` or internal fields.

With MapStruct, the generated mapper can be tested similarly. Setting `unmappedTargetPolicy` to ERROR helps catch unmapped target fields at compile time.

## 27. Testing API Serialization

Do not test only DTO objects; verify the JSON contract as well:

- Does the response have the right field names and data types?
- Are sensitive fields absent?
- Are nulls omitted or returned according to contract?
- Are enums serialized by name or custom value?
- Are Instants formatted consistently in ISO-8601 and timezone?
- Do nested collections have the expected structure without cycles?
- Are requests prevented from setting status/role/passwordHash/version?
- Do validation errors return the expected status and error body?

Example with MockMvc:

~~~java
mockMvc.perform(post("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "name": "An",
              "email": "an@example.com",
              "password": "correct-horse-battery"
            }
            """))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.name").value("An"))
    .andExpect(jsonPath("$.email").value("an@example.com"))
    .andExpect(jsonPath("$.passwordHash").doesNotExist());
~~~

This test needs the controller, service, and appropriate fixtures/mocks. You should also verify that the response does not contain `password`, internal `role`, or other Entity attributes outside the contract.

## 28. Testing Lazy Loading and Queries

An integration test for a detail endpoint should run under production-like settings:
1. Save the Entity and its relationships.
2. End the fixture-creation transaction.
3. Call the detail read service.
4. Map to DTO using the designated fetch plan.
5. Verify no LazyInitializationException occurs.
6. Monitor SQL counts to detect N+1 queries.
7. Verify the response includes the required relationships.

Do not run the mapper inside a test with an open persistence context and conclude the endpoint has no lazy loading bugs. Open Session in View can mask a service's failure to load complete data; consider disabling OSIV or testing along the transaction boundaries your architecture intends.

## 29. Common Mistakes

**Returning Entities directly from Controllers**

The API becomes coupled to the persistence schema and relationships. Return response DTOs according to the endpoint contract.

**Binding request JSON directly into Entities**

Clients can modify internal or unauthorized fields. Use allow-listed request DTOs.

**Using the same DTO for create, update, and response**

Operations have different fields and semantics. Split DTOs per use case when contracts differ.

**Mapping password or passwordHash into responses**

Leaks sensitive data. Omit those fields from response models and verify JSON output in tests.

**Mapping Entities to DTOs after the transaction closes**

The mapper may access LAZY relationships and fail. Map inside the service transaction with a clear fetch plan.

**Mappers causing N+1 queries**

Accessing LAZY relationships inside loops. Use projections, EntityGraph, or controlled fetch joins.

**Merging an Entity constructed from a request DTO**

Null/default fields can overwrite existing data. Load a managed Entity and apply only allowed fields.

**Using DTOs as full copies of Entities**

DTOs can still carry too many fields and couple the API contract to persistence. Design around the data the endpoint actually needs.

**Using `@JsonIgnore` as the sole security boundary**

The Entity remains the response model and may have other serialization paths. Use allow-listed DTOs.

**Not distinguishing absent from null in PATCH**

The application cannot tell whether the client wants to keep or clear a field. Use a three-state type or an explicit PATCH contract.

**Skipping authorization checks because a DTO is used**

DTOs only restrict fields; the service must still verify the caller is authorized to modify the resource.

**Returning DTO projections from queries that do not fetch enough data**

Constructor/field mappings can be wrong or trigger extra queries. Verify SQL, mappings, and run integration tests.

## 30. Workflow for Designing the Entity–DTO Boundary

When building a Spring Data JPA endpoint:

1. Identify the data clients are allowed to send and create a dedicated request DTO.
2. Add validation for input shape and format.
3. Enforce business rules and access permissions in the service.
4. Load or create the Entity inside a transaction.
5. Modify only permitted fields through domain/service methods.
6. Use the Repository to persist the Entity and let JPA manage its lifecycle.
7. Choose a response DTO matching the endpoint contract.
8. Map manually or with MapStruct; do not put business decisions in the mapper.
9. If few columns or large lists are needed, consider projections.
10. If the response needs LAZY relationships, define a fetch plan before mapping.
11. Verify JSON does not expose internal fields or contain cycles.
12. Test validation, authorization, mappers, transactions, lazy loading, and query counts.
13. Keep the API contract stable when Entities or schemas change.

## 31. Conclusion

An Entity is the persistence model managed by JPA; request DTOs and response DTOs are the data contracts of individual use cases/APIs. Separating these models restricts which fields clients can submit, prevents sensitive data leaks, controls JSON output, and reduces API coupling to the database schema. The Controller receives request DTOs, the Service enforces business rules within transactions, the Repository works with Entities, and the Mapper produces response DTOs. For lists or read queries needing only a few columns, projections can be more efficient than loading full Entities.

Map Entities to DTOs inside transactions when LAZY relationships are needed, use EntityGraph/projections to prevent N+1 queries, load managed Entities and apply commands for partial updates, and test JSON contracts. DTOs do not replace authorization or database constraints; they establish a clear boundary so the application deliberately controls what data is accepted and exposed.