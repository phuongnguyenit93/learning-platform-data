# Distinguishing Query Result DTOs from Update Request DTOs

## Objectives

After this lesson, you can:

- Distinguish DTOs used to return read data from DTOs used to receive create/update commands.
- Explain why these two kinds of DTOs have different fields, validation rules, and lifecycles.
- Use interface projections or constructor projections to query only required data with Spring Data JPA.
- Design request DTOs with validation that allow updating only business-approved fields.
- Update managed entities inside a transaction instead of binding requests directly to entities and merging them.
- Properly handle PUT, PATCH, missing fields, and explicit null values.
- Use versioning for optimistic concurrency control and test both read and write flows.

## 1. What Is a DTO and Why Separate by Data Direction?

A DTO (Data Transfer Object) is a data type used to transfer data across a boundary, such as between a repository and service or between an API and a client. A DTO typically holds only the data to transfer, does not represent the persistence context, and has no JPA-managed identity.

In a Spring Data JPA application, there are at least two common data directions:

- **Read DTO / response DTO**: carries data out of the application, typically serving screens, reports, or API responses.
- **Write DTO / request DTO / command DTO**: carries data from the client into the application to request creating or changing state.

These two directions serve different purposes. A list screen may only need ID, name, and status. A profile update command may need name, email, validation rules, and version control information.

Do not share a single DTO for both directions just because the fields look similar. When read and write requirements evolve independently, a shared DTO easily becomes overly broad, hard to validate, and prone to exposing internal fields.

## 2. Read DTOs: Returning Only the Data Callers Need

A read DTO describes the data a read use case must provide. It can:

- Contain only a subset of an entity's fields.
- Combine data from multiple entities or tables.
- Contain aggregated values such as count, total, or average.
- Rename fields to match the API contract.
- Exclude internal fields such as password hashes, audit metadata, or technical fields not meant to be public.

For example, a customer list page only needs:

~~~java
package com.example.customer;

public record CustomerListItem(
        Long id,
        String name,
        String email
) {
}
~~~

Records fit immutable DTOs well. They automatically provide a constructor, accessors, `equals`, `hashCode`, and `toString` based on their components.

A read DTO does not need `@Entity`, `@Id`, or management by `EntityManager`. It is a read result, not an object needing dirty checking.

### Why Not Return Entities Directly?

Returning entities directly from an API can cause:

- **Data exposure**: entities may contain internal fields that should not be public.
- **Coupling**: changing database mappings can accidentally change the JSON contract.
- **Lazy loading**: serializers may access associations after the persistence context closes.
- **N+1 queries**: serializing a collection can trigger many queries.
- **Object graph cycles**: bidirectional relationships can cause recursive JSON serialization.
- **Over-fetching**: the API loads more fields/associations than the use case needs.

Read DTOs establish a clear boundary between the persistence model and outbound data.

## 3. Creating Read DTOs with Constructor Projections

Spring Data JPA supports JPQL constructor expressions to instantiate DTOs directly from queries.

Suppose the `Customer` entity has fields `id`, `name`, `email`, and `active`. The repository can declare:

~~~java
package com.example.customer;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select new com.example.customer.CustomerListItem(
            c.id,
            c.name,
            c.email
        )
        from Customer c
        where c.active = true
        order by c.name
        """)
    List<CustomerListItem> findActiveCustomerItems();
}
~~~

JPQL uses entity names and Java properties, not SQL table/column names. The `new` clause requires the fully qualified class name of the DTO. Expression order and types must match the DTO constructor.

The results are `CustomerListItem` objects. They are not `Customer` entities and are not tracked by dirty checking. Therefore, do not use read DTOs as objects to directly update entities.

### When Are Constructor Projections a Good Fit?

- When you need a clear, stable result type.
- When you need fields from multiple entities or aggregate functions.
- When you want to avoid loading the full entity.
- When you want to define the exact result shape at the repository level.

If a query involves multiple joins, `group by`, or computed fields, DTO projections usually make the read use case clearer.

## 4. Interface Projections

Spring Data JPA also supports interface projections:

~~~java
public interface CustomerNameView {
    Long getId();
    String getName();
}
~~~

Repository:

~~~java
List<CustomerNameView> findByActiveTrue();
~~~

Spring Data can create a projection proxy exposing only the declared accessors. With closed projections, properties are known upfront so Spring Data can optimize the fetched data depending on the query and provider.

Projections can use nested properties, but accessing nested associations may require joins and load extra data. Do not assume every interface projection always emits just a simple single `SELECT`.

### Comparing the Two Read Approaches

| Criterion | Interface projection | Constructor DTO projection |
|---|---|---|
| Declaration | Interface with getters | Class or record with constructor |
| Result | Usually a projection proxy | DTO object created via constructor |
| Type control | Accessors define the shape | Constructor defines the shape |
| Explicit JPQL | Can use query methods or `@Query` | Typically uses `select new` |
| Best suited for | Simple views, few fields | Reports or results with explicit structure |

Choose based on complexity and maintainability. Do not create a projection just to rename one field if a DTO is clearer for the API.

## 5. Write DTOs: Receiving a Modification Command

A write DTO describes the data clients are allowed to send to request an action. It usually has:

- Only the fields the use case permits creating or updating.
- Input validation.
- Data types aligned with the API.
- Possibly a version or idempotency key if business logic requires it.
- Not necessarily every field of the entity.

Example request to update a Customer profile:

~~~java
package com.example.customer;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateCustomerRequest(
        @NotBlank
        @Size(max = 120)
        String name,

        @NotBlank
        @Email
        @Size(max = 254)
        String email
) {
}
~~~

This is a DTO receiving data from a client. Validation annotations describe request rules; they do not automatically replace database constraints or domain rules.

The controller triggers validation using `@Valid`:

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> update(
            @PathVariable Long id,
            @Valid @RequestBody UpdateCustomerRequest request) {

        service.update(id, request);
        return ResponseEntity.noContent().build();
    }
}
~~~

In this example, `PUT` means replacing the entire profile portion managed by the request. Therefore, both `name` and `email` are required. If the API only allows changing a few fields, design a `PATCH` or dedicated command endpoint instead of accidentally treating missing fields as null.

## 6. Updating Managed Entities with Data from Write DTOs

A safe update flow typically follows these steps:

1. Receive the request DTO and validate input structure.
2. Load the entity to update inside a transaction.
3. Verify authorization and business preconditions.
4. Apply each field permitted to change.
5. Let dirty checking persist changes when the transaction flushes/commits.

`Customer` entity:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, unique = true, length = 254)
    private String email;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {
    }

    public void updateProfile(String name, String email) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("email must not be blank");
        }

        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Service:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void update(Long id, UpdateCustomerRequest request) {
        Customer customer = repository.findById(id)
            .orElseThrow(() ->
                new EntityNotFoundException("Customer not found: " + id)
            );

        customer.updateProfile(request.name(), request.email());

        // customer is managed; dirty checking persists changes on commit.
    }
}
~~~

You do not need to call `repository.save(customer)` again for an entity loaded within the same transaction. The entity is managed; dirty checking detects the changes. Calling `save` may still work, but it is unnecessary for this flow.

### Why Not Map Request to Entity and Merge?

Risky approach:

~~~java
Customer customer = mapper.toEntity(request);
customer.setId(id);
repository.save(customer);
~~~

If the mapper lacks all fields, omitted fields can become null or default values. Spring Data may follow the merge path and copy that state onto the managed instance, causing data loss.

Loading the entity first and then applying changes lets the service control which fields are updated, protect invariants, and check permissions on the exact target object.

## 7. Request Validation vs. Domain Validation

There are multiple layers of validation:

| Layer | Responsibility | Example |
|---|---|---|
| Request validation | Checks input shape and structural constraints | `@NotBlank`, `@Email`, `@Size` |
| Domain validation | Protects business rules | Email must be unique per tenant; cannot update profile when account is locked |
| Database constraint | Protects ultimate integrity | `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, `CHECK` |
| Authorization | Checks whether caller has permission to act | Only account owner or admin can update |

A syntactically valid request can still violate business rules. For instance, an email may be properly formatted yet already belong to another `Customer`.

Checking duplicates in the service can return a friendly error, but a database `UNIQUE` constraint is still required to handle race conditions across concurrent transactions.

Do not rely solely on DTO validation to guarantee database correctness. Data can also be written by batch jobs, scripts, other services, or migrations.

## 8. PUT and PATCH Have Different Semantics

Write DTOs must match the update style the API exposes.

### PUT: Replacing the Defined Resource Representation

With `PUT`, the request typically contains all fields belonging to the resource portion managed by the endpoint. If a required field is missing, the request is rejected. For example, `UpdateCustomerRequest` above requires both `name` and `email`.

### PATCH: Partial Update

With `PATCH`, an omitted field typically means leave unchanged. A field with value `null` may mean clear the value, if the API contract permits it. A field with a concrete value updates it.

JSON examples:

~~~json
{}
~~~

Requests no field changes.

~~~json
{"name": "An Nguyen"}
~~~

Updates only `name`.

~~~json
{"email": null}
~~~

Requests clearing `email`, if the domain allows it and the API defines `null` as a clear operation.

~~~json
{"email": "an@example.com"}
~~~

Updates `email` to the new value.

A regular Java DTO with nullable fields cannot distinguish between an omitted field and a field explicitly sent as `null` after deserialization. If `PATCH` requires these semantics, you must preserve field presence information.

### Using JsonNode to Detect Field Presence

Example handling the `email` field explicitly:

~~~java
JsonNode body = objectMapper.readTree(requestBody);

if (!body.has("email")) {
    // Field absent: keep current email.
} else if (body.get("email").isNull()) {
    // Field is null: clear email if allowed by domain.
} else {
    String email = body.get("email").asText();
    // Validate and update email.
}
~~~

Another option is a wrapper like `JsonNullable<T>` from an appropriate library, or an internal `FieldUpdate<T>` type with a `present` flag. You must configure the deserializer so the wrapper distinguishes absent fields from explicit `null`; merely adding a nullable Java field is not enough.

Do not automatically convert empty strings to null. `""`, whitespace-only strings, and JSON `null` are distinct inputs; normalization rules must be defined by the API/domain.

## 9. Do Not Use a Response DTO as a Request DTO

A response may contain read-only fields:

~~~java
public record CustomerDetailsResponse(
        Long id,
        String name,
        String email,
        boolean active,
        Long version,
        Instant createdAt
) {
}
~~~

Do not reuse this exact type as an update request. A client could send `id`, `active`, `createdAt`, or internal fields the endpoint must not allow changing.

If a controller binds a response DTO directly to an entity or a mapper copies all fields, mass assignment can occur: clients modify attributes they are not authorized to control.

Create a separate request DTO listing only fields editable in that use case. If enabling/disabling an account is needed, use a clear command like `ChangeCustomerStatusRequest` or a dedicated endpoint with matching authorization and domain rules.

## 10. Distinguishing DTOs, Entities, and Mappers

| Type | Has JPA identity? | Dirty-checked? | Purpose |
|---|---:|---:|---|
| Entity | Yes | Yes, when managed | Persistence/domain model |
| Read DTO | No | No | Returns read data |
| Write DTO | No | No | Receives input commands/data |
| Projection interface | Not an entity | No | Exposes a queried subset of properties |

Mappers convert data between DTOs and domain/entities. You can use manual mapping, MapStruct, or similar libraries. Regardless of the tool, update rules must stay explicit:

- Do not automatically copy `ID` from the request if the `ID` comes from the path.
- Do not copy `version` or security state if the client is not authorized to set them.
- Do not overwrite fields omitted in `PATCH`.
- Do not replace an association with a stub object containing only an `ID` without verifying existence and permissions.
- Do not map collections blindly if adding/removing elements has domain rules.

Mappers reduce repetitive code, but they do not replace business decisions.

## 11. Optimistic Locking and Versions in Update Flows

The `Customer` entity in the example has:

~~~java
@Version
private Long version;
~~~

The JPA provider uses `version` to detect when two transactions concurrently update the same entity from a stale state. When a transaction writes with a mismatched version, the operation can fail with an optimistic locking exception.

If the API needs to detect when a client edits stale data, return `version` in the response DTO and accept the expected `version` in the request or via HTTP `ETag`/`If-Match`.

Response example:

~~~json
{
  "id": 10,
  "name": "An",
  "email": "an@example.com",
  "version": 4
}
~~~

The client sends back the version it read when updating. The service can check early to return a friendly conflict message; JPA `@Version` remains the final safeguard because another transaction could update the row after that check.

Do not remove `@Version` just because the API includes a `version` field. Service-level checks and database-level optimistic locking protect against two different points in time.

## 12. Transactions, Associations, and Collection Updates

Write DTOs may carry nested data such as addresses or line items. Do not map the entire request into an object graph and merge it unchecked.

For associations:

1. Load the aggregate root inside the transaction.
2. Verify that related entities exist and the caller has permission to use them.
3. Call domain methods to add, update, or remove associations.
4. Keep owning and inverse sides synchronized.
5. Only use cascade/`orphanRemoval` when appropriate for the domain lifecycle.

For example, a request adding a product to an order should not construct a new `Product` with only an `ID` and cascade persist. Load the existing `Product` or reference a valid entity per domain rules.

For collection `PATCH` operations, explicitly define whether the request provides a full replacement list or only items to add/remove. These two meanings differ and need distinct DTOs/commands.

## 13. Separate Tests for Reads and Writes

Read DTO tests should verify:

- The query returns the exact count and fields.
- Constructor projections match constructor order and types.
- Unneeded fields are neither loaded nor exposed.
- Sorting, pagination, and aggregations are accurate.
- Null associations are represented properly.

Write DTO tests should verify:

- Validation rejects invalid inputs.
- Only permitted fields change.
- Fields omitted in `PATCH` remain intact.
- Explicit `null` clears data only when allowed by the contract.
- Domain rules and authorization are enforced.
- Unique constraints and foreign keys protect data integrity.
- Optimistic locking detects concurrent updates.

Example test for a constructor projection:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void returnsOnlyFieldsNeededByCustomerList() {
        List<CustomerListItem> result =
                repository.findActiveCustomerItems();

        assertEquals(1, result.size());
        assertEquals("An", result.get(0).name());
        assertEquals("an@example.com", result.get(0).email());
    }
}
~~~

This test assumes test data has been seeded with exactly one active `Customer`. It is an integration test for a query projection; there is no need to persist or merge `CustomerListItem` because it is a DTO.

Update tests should run in an appropriate transaction, flush, and clear the persistence context before reloading the entity to confirm the database saved the intended state. For `PATCH`, write separate tests for omitted fields, explicit `null`, and concrete values.

## 14. Common Pitfalls

| Symptom | Cause | How to fix |
|---|---|---|
| API returns too many fields | Returning entities or overly broad shared DTOs | Create read DTOs per use case |
| DTO projection fails to instantiate | Wrong constructor parameter order or types | Align select expressions with the constructor |
| Update turns other fields into null | Mapping partial request to entity and merging | Load managed entity and apply allowed fields |
| Client can change ID/internal status | Binding request to entity or response DTO | Use an allow-listed write DTO |
| PATCH cannot distinguish missing vs. null | Regular nullable DTO collapses both states | Use `JsonNode` or a tri-state wrapper |
| Null field is not cleared | Service treats null as no-op | Define the contract and handle explicit null separately |
| Two users overwrite each other's changes | Missing concurrency control | Use `@Version` and handle optimistic locking |
| Validation passes but database has duplicates | Checked only in service | Add a unique constraint in the database |
| `LazyInitializationException` when returning entity | Serializer accesses association outside transaction | Return a DTO/projection |
| Mapper overwrites associations wrongly | Copying object graph without ownership checks | Load related entities and call domain methods |

## Process for Choosing DTOs

1. Determine whether data flows into or out of the use case.
2. If outbound, design a read DTO with the exact fields and shape callers need.
3. Choose an interface projection or constructor DTO projection for the query.
4. If inbound, design a request/command DTO containing only fields allowed to change.
5. Place structural validation on the request, business rules in domain/service, and final constraints in the database.
6. Load the managed entity in a transaction and apply changes intentionally.
7. For `PATCH`, preserve the distinction between omitted fields, `null`, and values.
8. Use `version`/`ETag` when concurrent update control is needed.
9. Write independent tests for query projections and update commands.

## Pre-Merge Checklist

- [ ] Read DTOs and Write DTOs have separate purposes.
- [ ] Read DTOs return only needed fields and do not leak internal data.
- [ ] Constructor projections have the exact package, parameter order, and types.
- [ ] Write DTOs accept only fields allowed to change.
- [ ] Request validation is not confused with domain validation or database constraints.
- [ ] Services load managed entities and apply changes inside a transaction.
- [ ] Partial entities built from request DTOs are never merged.
- [ ] PUT/PATCH semantics are explicit for missing fields and nulls.
- [ ] Associations have ownership and lifecycle checks.
- [ ] Optimistic locking is used when preventing lost updates is required.
- [ ] Both read projections and write flows have integration tests.

## Conclusion

Read DTOs describe the data an application wants to return; Write DTOs describe the commands and fields clients are permitted to send. Read DTOs are usually built using interface projections or constructor projections and are not managed by JPA. Write DTOs require validation and must be applied to managed entities inside a transaction according to business rules. Separating the two types of DTOs helps control exposed data, prevent mass assignment, stop partial requests from overwriting fields with null, and clarify PUT/PATCH semantics. Test read queries, updates, field presence, and optimistic locking independently.
