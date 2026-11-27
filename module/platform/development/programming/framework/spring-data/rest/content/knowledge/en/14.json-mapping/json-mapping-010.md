# Controlling Mass Assignment and Unexpected Input Data in Spring Data REST

## Objectives

Spring Data REST can accept JSON from clients and use Jackson to map properties in the request body onto repository domain objects. While convenient for CRUD, this mechanism creates a **mass assignment** risk if the API lets clients write properties that normal user interfaces do not send.

Mass assignment happens when the server automatically binds many properties from a request onto an object when the application only intended to let the client modify a small subset. A client can inject fields such as `role`, `admin`, `ownerId`, `tenantId`, `approved`, `createdAt`, or `internalStatus` into JSON even though those fields never appear in the form.

For example, a screen only allows editing a Person's name, yet a request can be crafted manually:

~~~json
{
  "displayName": "Ada",
  "role": "ADMIN",
  "tenantId": "tenant-other",
  "approved": true
}
~~~

If Jackson binds these properties onto the entity without server-side controls, clients can alter data unexpectedly.

To mitigate this risk, combine:

- Restricting which properties are writable per API.
- Marking server-managed properties as read-only or excluding them from serialization/binding.
- Using allowlist DTOs when an endpoint needs a clearly bounded set of inputs.
- Validating data with Bean Validation and domain rules.
- Enforcing server-side authorization for every sensitive action.
- Testing with requests that intentionally send fields outside the API contract.

## 1. Mass Assignment During JSON Mapping

Suppose the Person repository is exported:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

A request to create a Person may send JSON:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "displayName": "Ada Lovelace",
  "email": "ada@example.com"
}
~~~

Spring Data REST receives the request body and uses Spring MVC/Jackson message conversion to construct or update the domain object. JSON properties matching model properties can be bound by Jackson depending on mapper configuration, constructors, setters, and visibility.

Risk arises when the entity contains bindable internal properties:

~~~java
@Entity
class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;
    private String email;

    private String role;
    private UUID tenantId;
    private boolean approved;
    private Instant createdAt;

    // getters/setters
}
~~~

If the API accepts the entity directly and sensitive properties are writable, clients can supply those extra keys. The fact that a UI does not display a field does not mean an HTTP request cannot include it.

### Properties to Review

| Property Group | Examples | Risk If Client Writes Directly |
|---|---|---|
| Roles and permissions | `role`, `admin`, `permissions` | Privilege escalation or self-granting permissions. |
| Ownership and tenant | `ownerId`, `tenantId`, `organizationId` | Reassigning data to another user or tenant. |
| Approval status | `approved`, `verified`, `reviewedBy` | Bypassing approval workflows. |
| Audit fields | `createdAt`, `createdBy`, `updatedBy` | Corrupting data provenance and history. |
| Internal computed fields | `balance`, `priceAfterDiscount`, `riskScore` | Overwriting values that must be calculated by the server. |
| Sensitive relationships | `manager`, `account`, `organization` | Attaching the entity to objects the client is not authorized to manage. |

Not every property in the table is always sensitive. Decisions depend on business logic, principal permissions, and the API contract.

## 2. Distinguishing Valid Input from Unexpected Data

There are three distinct cases when the server receives JSON:

1. **Writable properties:** the client is permitted to send them and the server may bind them onto the domain object.
2. **Readable properties that clients must not modify:** the server may return them in responses but must ignore or reject them when present in requests.
3. **Properties outside the API contract:** clients should not send them; how Jackson handles unknown keys depends on ObjectMapper and message converter settings.

Do not rely on Jackson ignoring unknown properties as a defense mechanism. A key like `role` is not an unknown property if the entity actually has that property. Jackson can bind it just like any normal property.

Also do not confuse hiding a property from responses with preventing clients from writing that property. Explicitly configure both serialization and deserialization directions.

## 3. Using @JsonProperty(access = READ_ONLY) for Server-Managed Properties

Jackson supports `@JsonProperty(access = JsonProperty.Access.READ_ONLY)`. A read-only property can be serialized into responses but does not accept values from JSON input.

Example:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;
    private String email;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String role;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private UUID tenantId;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Instant createdAt;

    // getters/setters
}
~~~

When a client sends:

~~~json
{
  "displayName": "Ada",
  "role": "ADMIN",
  "tenantId": "tenant-other",
  "createdAt": "2026-01-01T00:00:00Z"
}
~~~

Jackson does not use the input values of properties marked READ_ONLY to update the object. During serialization, those values can still appear in responses.

### When to Use READ_ONLY?

Use for properties that are:

- Generated or updated automatically by the server.
- Safe to show to clients but must not be controlled by clients.
- Computed results or internal state only the server may alter.
- Needed in responses for clients to read, while excluded from write contracts.

Common examples include database-generated IDs, audit timestamps, approval states, or a tenant derived from the principal.

### READ_ONLY Does Not Replace Authorization

READ_ONLY blocks Jackson JSON binding. It does not decide which users may read the property, does not cover every write path in the application, and does not replace service/domain-layer permissions.

If a user must not read `tenantId` or `role`, enforce separate representation or authorization controls. If an administrative action is allowed to change roles, provide a use case with explicit authorization instead of opening that property on a generic CRUD endpoint.

## 4. Using WRITE_ONLY for Client-Submitted-Only Data

Jackson also offers:

~~~java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String password;
~~~

WRITE_ONLY allows a property to be bound from JSON input while omitting it from serialized responses.

This suits certain inputs such as secrets accepted from clients, but handle them carefully:

- Never store passwords in plain text.
- Transmit only over HTTPS.
- Hash/encode in a dedicated service before persisting.
- Never return secrets in responses or logs.
- Do not let a generic repository endpoint accidentally allow credential changes without executing the appropriate business flow.

For credentials, tokens, or secrets, dedicated DTOs and services are usually clearer than placing the property directly on an exported entity.

## 5. Using @JsonIgnore When a Property Must Not Be Read or Written via JSON

If a property should never appear in JSON representations and must never be bound from JSON, you can use:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

@Entity
class Person {

    private String displayName;

    @JsonIgnore
    private String internalRiskFlag;

    // getters/setters
}
~~~

`@JsonIgnore` applies to both serialization and deserialization according to how Jackson handles the property. Thus, responses do not expose the property and request JSON does not bind to it.

Comparison:

| Configuration | Response Serialization | Request Deserialization |
|---|---|---|
| `@JsonProperty(access = READ_ONLY)` | May appear | Does not accept input values |
| `@JsonProperty(access = WRITE_ONLY)` | Does not appear | May accept input values |
| `@JsonIgnore` | Ignored | Ignored |

Inspect how annotations are placed across fields/getters/setters and check the application's Jackson configuration. Jackson can merge fields and accessors into one logical property; inconsistent annotations across accessors can cause confusing behavior.

If a property should be readable in the API but only viewable by certain roles, `@JsonIgnore` is too broad. In that case, design representations or endpoints according to access permissions.

## 6. Hiding an Association Does Not Automatically Protect All Write Paths

Spring Data REST can export associations as links and association resources. You can hide an association from the REST exporter with `@RestResource(exported = false)`:

~~~java
@ManyToOne
@RestResource(exported = false)
private Organization organization;
~~~

This setting controls Spring Data REST's exposure of the association resource/link. It should not be treated as a general allowlist for all JSON binding or application authorization.

If the entity still has the `organization` property and the JSON mapper still accepts it, control binding separately. Use Jackson annotations, input DTOs, or custom endpoints with explicit permission checks.

For sensitive associations, verify both paths:

- Calling the association resource directly with applicable HTTP methods.
- Sending JSON containing the association property in POST/PUT/PATCH requests to the item or collection.

Test both cases to avoid only hiding links while leaving another write path open.

## 7. Allowlist DTOs Are a Clear Choice for Bounded Input

When an endpoint should accept only a specific set of fields, the most reliable and controllable option is accepting a request DTO instead of binding directly to the entity.

Example:

~~~java
public record UpdatePersonRequest(
    @NotBlank
    @Size(max = 120)
    String displayName,

    @Email
    @Size(max = 254)
    String email
) {
}
~~~

Controller calling the service:

~~~java
@RestController
@RequestMapping("/api/person-commands")
class PersonCommandController {

    private final PersonService personService;

    PersonCommandController(PersonService personService) {
        this.personService = personService;
    }

    @PatchMapping("/{id}")
    ResponseEntity<PersonResponse> update(
            @PathVariable Long id,
            @Valid @RequestBody UpdatePersonRequest request) {

        PersonResponse response =
                personService.updateProfile(id, request);

        return ResponseEntity.ok(response);
    }
}
~~~

The service copies only permitted properties:

~~~java
@Transactional
public PersonResponse updateProfile(
        Long id,
        UpdatePersonRequest request) {

    Person person = repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException());

    person.setDisplayName(request.displayName());
    person.setEmail(request.email());

    return PersonResponse.from(person);
}
~~~

The DTO acts as an allowlist: only declared components belong to the input contract. Fields like `role`, `tenantId`, `approved`, or `createdAt` do not exist on the DTO and are therefore not copied onto the entity by the service.

### If Keys Outside the Contract Must Be Rejected

Depending on Jackson settings, unrecognized properties in JSON may be ignored or fail the request. If the API requirement is to reject any key outside the DTO, configure strict deserialization and test that behavior against the application's actual ObjectMapper/message converter.

Do not assume every Spring Boot version has the same default value for `FAIL_ON_UNKNOWN_PROPERTIES`. Check the actual configuration.

### DTOs and Spring Data REST

Spring Data REST exports repository domain resources by default; it does not automatically turn every repository endpoint into a DTO-accepting endpoint. If you need an input allowlist, you can:

- Create a custom controller and service for that use case.
- Place the custom endpoint at a URI that does not conflict with repository resources.
- Or hide the repository resource using `@RepositoryRestResource(exported = false)` if the DTO endpoint replaces that CRUD API altogether.

Do not create a controller on the same URI as an exported collection/item resource expecting routing to pick yours as desired. Design distinct paths and verify actual mappings.

## 8. Validation and Domain Invariants

Restricting bindable properties solves only part of the problem. Permitted input data must still be valid.

### Bean Validation

Example:

~~~java
@Entity
class Person {

    @NotBlank
    @Size(max = 120)
    private String displayName;

    @Email
    @Size(max = 254)
    private String email;
}
~~~

Bean Validation checks values against declared constraints. With Spring Data REST, validation can be wired through repository event listeners. Ensure validators are registered and run on the appropriate lifecycle events for create/update operations.

### Repository Event Handlers

Spring Data REST supports event handlers for the repository lifecycle:

~~~java
@Component
@RepositoryEventHandler
class PersonEventHandler {

    @HandleBeforeCreate
    void beforeCreate(Person person) {
        validatePerson(person);
    }

    @HandleBeforeSave
    void beforeSave(Person person) {
        validatePerson(person);
    }

    private void validatePerson(Person person) {
        if (person.getDisplayName() == null
                || person.getDisplayName().isBlank()) {
            throw new IllegalArgumentException(
                    "displayName is required");
        }
    }
}
~~~

These handlers suit checks or processing before/after repository operations. However, they are not a JSON allowlist: if a sensitive field has already been bound, the event handler must proactively detect and reject or revert unauthorized values.

For rules depending on the current user, tenant, administrative permissions, or workflow state, the service/domain layer is often a better place to make business decisions.

## 9. Protecting Server-Managed Properties

A common pattern is assigning server-managed properties from the security context or service:

~~~java
@Transactional
public Person createPerson(CreatePersonRequest request, CurrentUser user) {
    Person person = new Person();

    person.setDisplayName(request.displayName());
    person.setEmail(request.email());

    person.setTenantId(user.tenantId());
    person.setRole(Role.USER);
    person.setApproved(false);
    person.setCreatedAt(Instant.now());

    return repository.save(person);
}
~~~

Clients do not send `tenantId`, `role`, `approved`, or `createdAt`. The server sets those values based on the principal and business rules.

For updates, do not blindly overwrite the whole object from input. Load the existing entity, verify the principal's permissions, and update only permitted fields. This avoids accidentally overwriting internal values when a request only intends to change a few properties.

### Do Not Trust Client-Supplied Identifiers to Determine Permissions

If a client sends `ownerId` or `tenantId`, never treat that as proof that the user is authorized to act on the corresponding object. Derive tenant/owner from the authentication context or verify permissions against the existing entity on the server.

Especially in multi-tenant applications, queries fetching entities and tenant checks must be performed consistently. Checking tenants only in the UI or filtering data after loading entities is insufficient.

## 10. PUT, PATCH, and POST All Require Input Control

Mass assignment does not only happen on POST creation. Inspect every method that accepts JSON:

| Method | Common Purpose | Risk |
|---|---|---|
| POST collection | Create a new entity | Client adds role, owner, tenant, or internal status to the new object. |
| PUT item | Replace/update item representation per endpoint semantics | Client sends extra properties beyond permitted fields. |
| PATCH item | Partially update a representation | Client only needs to send one sensitive field to change state. |
| PATCH association | Update a relationship or part of a related resource | Client may attach links to entities they are not authorized to access. |

Do not assume PATCH is safer than PUT merely because the request body is small. If a sensitive property is bindable, a small JSON PATCH can still alter it.

For each write endpoint, determine:

- Which properties clients may set on creation.
- Which properties clients may modify on update.
- Which properties only the server may change.
- Which associations clients may link or unlink.
- Which permissions are required for the specific operation.

## 11. Authorization and Business-Rule Enforcement

Spring Security protects endpoints with authentication and authorization. Permitting POST or PATCH at the URL level does not mean every property on an entity may be modified.

Some rules belong in the business layer:

- Only administrators may change roles.
- Users may only edit their own profiles.
- Tenant A must not attach entities belonging to Tenant B.
- Only approvers may transition status from PENDING to APPROVED.
- Prices or balances must be calculated by the server.
- Manager relationships must obey organizational rules.

If a generic CRUD endpoint cannot cleanly express these permissions, create a dedicated command/service endpoint for the use case. The service method can be protected with appropriate authorization and then inspect current state before making changes.

Hiding a property from JSON or marking it READ_ONLY does not replace authorization. Conversely, having URL-level authorization without field-level control can still leave mass assignment vulnerabilities.

## 12. Unknown JSON Properties and Jackson Configuration

A request may contain keys that do not exist on the entity:

~~~json
{
  "displayName": "Ada",
  "unexpectedFlag": true
}
~~~

Jackson can:

- Ignore unknown properties if configuration allows.
- Reject the request if unknown-property failure is enabled.
- Process via a custom deserializer or mixin if the application configures one.

Exact behavior depends on the ObjectMapper used by Spring MVC/Spring Data REST and the framework version. Do not rely on defaults without verifying.

More importantly: **unknown properties and sensitive known properties are two different cases**.

- `unexpectedFlag` does not exist on the model, so it may be unknown.
- `role` exists on the entity and has a setter, so it can be bound even if the UI never sends it.

Enabling `FAIL_ON_UNKNOWN_PROPERTIES` only handles unrecognized keys. It does not prevent clients from writing valid yet sensitive properties.

## 13. Testing Against Mass Assignment

Integration tests should send requests containing both valid fields and disallowed fields. After the request, inspect persisted state in the database, not just the response.

Illustrative example:

~~~java
@Test
void patchMustNotChangeServerManagedFields() throws Exception {
    Person person = new Person();
    person.setDisplayName("Ada");
    person.setRole("USER");
    person.setTenantId(UUID.fromString(
            "11111111-1111-1111-1111-111111111111"));
    person = repository.save(person);

    mockMvc.perform(patch("/api/people/{id}", person.getId())
            .contentType(MediaType.APPLICATION_JSON)
            .accept("application/hal+json")
            .content("""
                {
                  "displayName": "Ada Lovelace",
                  "role": "ADMIN",
                  "tenantId": "22222222-2222-2222-2222-222222222222"
                }
                """))
            .andExpect(status().is2xxSuccessful());

    Person saved = repository.findById(person.getId()).orElseThrow();

    assertThat(saved.getDisplayName()).isEqualTo("Ada Lovelace");
    assertThat(saved.getRole()).isEqualTo("USER");
    assertThat(saved.getTenantId()).isEqualTo(
            UUID.fromString(
                "11111111-1111-1111-1111-111111111111"));
}
~~~

This is a test example with READ_ONLY properties and a suitably configured Spring Data REST endpoint. In a real project, use the appropriate media types, authentication, and fixtures for your running version. If the API chooses to reject the request rather than ignore fields, adjust the status assertion for an error status and still verify the database did not change.

Cases to include in integration tests:

1. POST with only allowed fields: succeeds.
2. POST adding role/tenant/owner: server does not accept unauthorized changes.
3. PATCH one valid field: only that field changes.
4. PATCH with only read-only fields: server-managed state remains unchanged.
5. PUT with properties outside the allowlist: server handles per the chosen contract.
6. Assigning an association to an entity in another tenant: rejected.
7. Non-admin user attempting to change role: rejected.
8. Request with unknown JSON keys: behavior matches API policy.
9. Responses do not leak secrets or internal fields.
10. Assert entity state after each request, not just the status code.

## 14. Investigation Workflow When Unexpected Field Writes Are Discovered

When a client is able to modify an unexpected field, investigate in order:

1. Identify the endpoint and HTTP method that received the request.
2. Capture the actual request body and content type.
3. Identify which entity properties changed after binding.
4. Inspect getters/setters, constructors, field visibility, and Jackson annotations.
5. Inspect the application's ObjectMapper/message converters.
6. Mark server-managed properties READ_ONLY or hide them completely if appropriate.
7. If input needs a strict allowlist, switch to a request DTO and service mapping.
8. Inspect association endpoints and JSON association binding separately.
9. Enforce validation and authorization on the server.
10. Write integration tests sending sensitive fields directly in requests.
11. Audit already-modified data and run appropriate remediation procedures if any.

Do not just tweak the UI to hide a field. Clients can send requests directly without going through the UI.

## 15. Common Misconceptions

1. **Assuming that if a field is not on the form, clients cannot send it.** HTTP requests can be crafted manually.
2. **Assuming Jackson only binds fields present in the UI's DTO.** When an endpoint accepts an entity, Jackson uses the model's property mappings and configuration.
3. **Using `@JsonIgnore` when the field still needs to be returned to clients.** Use READ_ONLY if it should be readable without accepting input.
4. **Using `@JsonProperty(READ_ONLY)` as an authorization mechanism.** The annotation controls JSON binding; it does not determine which users may read or modify data via other paths.
5. **Enabling FAIL_ON_UNKNOWN_PROPERTIES and assuming mass assignment is blocked.** That setting does not block sensitive properties that already exist on the entity.
6. **Testing only POST.** PUT, PATCH, and association updates also require control.
7. **Hiding an association link and assuming the relationship cannot be written.** Test association URIs and JSON binding directly.
8. **Using `exported = false` in place of a field allowlist.** That annotation controls resource/method/association exposure, not a general rule for all input properties.
9. **Trusting ownerId or tenantId from the client.** These values must be determined or verified on the server.
10. **Checking only the response.** The field may have been written to the database even if the response omits it.
11. **Assuming validation automatically blocks disallowed fields.** Validation checks values; allowlists decide which properties may accept input.
12. **Using projections to prevent mass assignment.** Projections primarily govern read representations, not write allowlists.

## 16. Secure Implementation Checklist

- Clearly define which properties are writable for each use case.
- Mark server-managed properties with `@JsonProperty(access = READ_ONLY)` if they still need to be serialized.
- Use `@JsonIgnore` if a property should not be read/written via JSON.
- Use WRITE_ONLY only for genuinely needed inputs and handle secrets securely.
- Use allowlist DTOs for endpoints with bounded inputs or complex business rules.
- Map each permitted field explicitly in the service.
- Determine tenant, owner, role, audit, and workflow status on the server.
- Control associations through both export configuration and authorization.
- Enforce Bean Validation and domain invariants.
- Protect sensitive operations with Spring Security/service authorization.
- Do not rely on UI controls, hidden links, or unknown-property behavior as security boundaries.
- Integration-test POST, PUT, PATCH, and association updates with payloads containing unexpected fields.
- Verify database state after every test request.
- Ensure responses do not disclose secrets or internal data.

## Summary

Mass assignment arises when JSON is bound directly onto domain objects and clients can supply additional properties that the use case does not permit changing. In Spring Data REST, examine every endpoint that accepts JSON—especially POST, PUT, and PATCH—along with association resources.

Use `@JsonProperty(access = READ_ONLY)` for properties that should be read without accepting input; use `@JsonIgnore` when a property must not be exchanged over JSON; use WRITE_ONLY for input that must not be returned. When an explicit allowlist is needed, accept a request DTO and map only permitted fields in the service.

Validation, authorization, and domain invariants must still be enforced on the server. Test by sending direct requests containing unexpected roles, tenants, owners, statuses, and associations, and verify that the database is not modified without authorization.

## References

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Customizing JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Jackson — JsonProperty.Access](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
- [Jackson — JsonIgnore](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
