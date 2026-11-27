# Controlling Mass Assignment and Unexpected Input in Spring Data REST

## Objectives

When Spring Data REST receives a write request, the JSON body is typically bound onto a domain object and passed to the repository. If clients can send any property supported by the entity, a request intended to update a few fields can accidentally or maliciously alter internal data as well. This is the **mass assignment** risk.

For example, suppose a use case only allows updating the display name and email:

~~~http
PATCH /api/people/42
Content-Type: application/merge-patch+json

{
  "displayName": "Ada Lovelace",
  "email": "ada@example.com"
}
~~~

A client can manually add extra properties that are not part of the UI form or write contract:

~~~json
{
  "displayName": "Ada Lovelace",
  "email": "ada@example.com",
  "role": "ADMIN",
  "tenantId": "tenant-other",
  "approved": true,
  "createdBy": "attacker"
}
~~~

If those fields exist on the entity and can be bound, the server risks persisting changes beyond the caller's privileges.

The goal of controlling mass assignment is to define precisely **who can write which field, through which endpoint, and under what conditions**. You need a combination of JSON binding controls, input allowlisting, validation, authorization, and domain rules. Hiding fields in the UI or hiding HAL links does not protect against directly crafted requests.

## 1. Where does mass assignment occur in the write flow?

A typical Spring Data REST write request can be visualized as follows:

~~~text
HTTP request
    |
    v
Spring Security authentication / authorization
    |
    v
Spring MVC message converter (Jackson)
    |
    v
Domain object / association binding
    |
    v
Repository event handlers and validation
    |
    v
Repository save / database
    |
    v
HTTP response representation
~~~

The risk appears at the binding stage: JSON data is mapped onto properties that the object accepts. The repository may then save the modified object.

Controls are needed at multiple points:

- **Before binding:** define which fields each endpoint and request contract permits.
- **During binding:** prevent server-managed properties from accepting values from JSON.
- **Before saving:** validate values, permissions, and domain invariants.
- **When modifying relationships:** verify the target entity and linking permissions.
- **After the operation:** verify actual persisted state, not just the response body.

Spring Data REST automatically provides CRUD endpoints for exported repositories. Therefore, whenever an entity has sensitive properties, examine how POST, PUT, PATCH, and association resources handle request bodies.

## 2. Classify properties before opening write endpoints

Not every property on an entity should be client-controlled. Classify properties before exporting a repository:

| Property group | Examples | Typical write rule |
|---|---|---|
| User-managed data | \`displayName\`, \`description\` | Allowed per use case and validation. |
| Contact data | \`email\`, \`phoneNumber\` | Conditionally allowed; validate format and edit permission. |
| Identifiers | \`id\`, auto-generated codes | Managed by server/database. |
| Permissions and roles | \`role\`, \`admin\`, \`permissions\` | Only via administrative flows with dedicated authorization. |
| Tenant and ownership | \`tenantId\`, \`ownerId\`, \`organizationId\` | Derived from principal or verified server-side. |
| Workflow state | \`approved\`, \`verified\`, \`reviewedBy\` | Transitioned only via valid commands. |
| Audit fields | \`createdAt\`, \`createdBy\`, \`updatedBy\` | Populated by the server. |
| Computed values | \`balance\`, \`totalPrice\`, \`riskScore\` | Calculated by the server from source data. |
| Sensitive associations | \`account\`, \`manager\`, \`organization\` | Check permissions on both source and target entities. |

This table represents a business classification. A field may be writable by one group of users in one use case, yet read-only in another. When write permissions vary by role or state, a generic CRUD endpoint may fail to express that contract clearly.

## 3. Why hiding fields in the UI is not enough

A UI typically submits a JSON object containing only visible fields. However, API callers can:

- Craft requests manually with curl or Postman.
- Modify payloads in browser developer tools.
- Call endpoints directly from scripts.
- Send properties missing from the form yet present on the entity.
- Send an association URI pointing to an entity they are not authorized to link.

For instance, the form omits the role field, but the entity has a role property:

~~~java
@Entity
class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;
    private String role;

    // getters/setters
}
~~~

If the endpoint accepts the entity and Jackson allows binding \`role\`, the following request can still be submitted:

~~~http
POST /api/people
Content-Type: application/json

{
  "displayName": "Ada",
  "role": "ADMIN"
}
~~~

Write contracts must be enforced on the server. Never rely on a field's absence from a form as a security boundary.

## 4. Blocking writes to server-managed properties with Jackson

If a property may be returned in responses but must not be accepted from JSON requests, Jackson provides:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private String role;
~~~

Entity example:

~~~java
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

READ_ONLY properties can be serialized into responses, but Jackson does not read values from JSON input to populate them.

Use this for server-managed fields that clients still need to read, such as IDs, timestamps, current tenant, or workflow-derived statuses.

### READ_ONLY is not authorization

READ_ONLY controls JSON deserialization. It does not determine which users may read the value, does not protect other write paths such as internal services, batch jobs, or direct database access, and does not replace authorization.

If only administrators may change roles, build a dedicated administrative operation, verify permissions server-side, and perform the change via a service. Do not open the role field on a generic CRUD endpoint just to serve one special use case.

### Use WRITE_ONLY and JsonIgnore for their intended purposes

Jackson offers three common options:

| Annotation | Serialize in response | Deserialize from request |
|---|---|---|
| \`@JsonProperty(access = READ_ONLY)\` | May appear | Ignores input value |
| \`@JsonProperty(access = WRITE_ONLY)\` | Does not appear | May accept input value |
| \`@JsonIgnore\` | Ignored | Ignored |

WRITE_ONLY suits inputs that must be accepted but never returned, such as a secret. Credentials must be handled in dedicated services, hashed before storage, and never logged.

JsonIgnore fits when a property should never be exchanged over JSON in either direction. If clients need to read a property without writing it, READ_ONLY is usually a better fit.

Check annotations across fields, getters, and setters. Jackson merges them into one logical property; inconsistent configuration can yield unexpected behavior.

## 5. Allowlist inputs with request DTOs

When a use case permits only specific fields, a request DTO clearly expresses the input contract. Example:

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

Custom controller accepting the DTO and calling the service:

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

        return ResponseEntity.ok(
            personService.updateProfile(id, request)
        );
    }
}
~~~

The service loads the existing entity and updates only allowlisted fields:

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

Fields such as role, tenantId, approved, and createdAt are absent from the DTO, so the service never copies them from the request into the entity.

Spring Data REST publishes repository domain resources by default; it does not automatically convert repository endpoints into DTO-accepting endpoints. When a use case requires strict input allowlisting, create a custom controller/service at a separate URI. If the custom endpoint completely replaces the repository API, consider hiding the repository with \`@RepositoryRestResource(exported = false)\`.

If policy requires rejecting any JSON key outside the DTO, configure unknown-property handling explicitly and test the actual ObjectMapper. The default value of \`FAIL_ON_UNKNOWN_PROPERTIES\` can vary across configurations and versions. Whether unknown keys are ignored or rejected, that alone does not replace allowlisting for properties that already exist on the entity.

## 6. Controlling POST, PUT, and PATCH

Mass assignment can occur in any JSON-accepting write request:

| Method | Resource | Primary risk |
|---|---|---|
| POST | Collection, e.g., \`/api/people\` | Creating an entity with client-chosen role, owner, or tenant. |
| PUT | Item, e.g., \`/api/people/42\` | Sending properties outside the update contract. |
| PATCH | Item, e.g., \`/api/people/42\` | Altering a sensitive property with a minimal payload. |
| PATCH/PUT | Association resource | Attaching or replacing a relationship to an unauthorized entity. |

Do not assume PATCH is safer than PUT. If a sensitive property is bindable, a tiny PATCH payload can still overwrite it.

For each method, define:

1. Which properties may be created or updated.
2. Which properties only the server may change.
3. Behavior when a client sends a read-only property.
4. Behavior for JSON keys outside the contract.
5. Required principal permissions.
6. Validation rules for current state prior to saving.

For PUT, understand the endpoint's representation-replacement semantics and which values are ignored by configuration. For PATCH, verify the media type and patch mechanism in use. Do not assume all PATCH formats share identical binding behavior.

## 7. Controlling associations and URI references

Spring Data REST can allow clients to update associations using the target entity's URI. Example:

~~~http
PUT /api/people/42/address
Content-Type: text/uri-list

http://localhost:8080/api/addresses/7
~~~

Even when the JSON body has no \`address\` property, a client can still modify the relationship via the association resource if the endpoint is exported and the method is permitted.

Therefore, verify:

- Which user or tenant Person 42 belongs to.
- Whether the user has permission to modify Person 42's associations.
- Whether Address 7 exists.
- Whether Address 7 belongs to a tenant or scope Person 42 is allowed to reference.
- Whether the association is allowed to change in the current state.
- Which data cascade and orphan removal may affect.

Hiding an association with \`@RestResource(exported = false)\` controls Spring Data REST link/resource exposure. It is not a general allowlist across all JSON binding paths and does not replace authorization.

For sensitive relationships, test both requests to association URIs and JSON requests to item/collection resources. Do not check only whether the link is displayed.

## 8. Setting tenant, owner, and state on the server

Fields such as tenantId, ownerId, role, approved, and audit fields should normally be set from the security context or domain rules.

Entity creation example:

~~~java
@Transactional
public Person createPerson(
        CreatePersonRequest request,
        CurrentUser currentUser) {

    Person person = new Person();
    person.setDisplayName(request.displayName());
    person.setEmail(request.email());

    person.setTenantId(currentUser.tenantId());
    person.setRole(Role.USER);
    person.setApproved(false);
    person.setCreatedAt(Instant.now());

    return repository.save(person);
}
~~~

The client sends only allowed business inputs. The server derives the tenant from the principal, assigns the default role, and records the audit timestamp.

For updates, fetch the existing entity scoped to the right tenant, verify principal permissions, and update each permitted property individually. Never trust an ownerId or tenantId supplied by the client as proof of access rights.

In multi-tenant systems, tenant scoping and checks must be enforced consistently on the server. Checking tenant in the UI or merely filtering results after loading entities is insufficient.

## 9. Validation and domain invariants

Allowlisting determines which properties are accepted; validation determines whether received values are valid. Both layers must work together.

### Bean Validation

~~~java
public record CreatePersonRequest(
    @NotBlank
    @Size(max = 120)
    String displayName,

    @NotBlank
    @Email
    @Size(max = 254)
    String email
) {
}
~~~

Apply \`@Valid\` at the request boundary to trigger DTO validation. For Spring Data REST repository event validation, ensure validators are registered for the appropriate create/update lifecycle events.

### Repository event handlers

Spring Data REST provides events such as before-create, before-save, and before-link-save. Example:

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

Event handlers can check state and reject operations before the repository saves. However, event handlers do not automatically act as a JSON allowlist. If a sensitive property has already been bound, code must explicitly detect and reject that change.

Rules depending on principal, tenant, admin privileges, or workflow generally belong in the service/domain layer where full context can be checked. Do not rely solely on validation annotations to enforce authorization.

## 10. Configuring unknown JSON keys

A request may include keys that do not exist on the entity:

~~~json
{
  "displayName": "Ada",
  "unexpectedFlag": true
}
~~~

Jackson may ignore this key or reject the request depending on ObjectMapper configuration. Applications can customize this through Spring Boot properties, an ObjectMapper bean, modules, mixins, or message converters.

Distinguish clearly between:

- **Unknown property:** a key absent from the model, such as unexpectedFlag.
- **Known but forbidden property:** a key existing on the entity that the client is not allowed to write, such as role.

Enabling \`FAIL_ON_UNKNOWN_PROPERTIES\` helps catch off-contract payloads, but it does not block sensitive properties that already exist on the entity. To prevent mass assignment, control known properties via READ_ONLY, DTO allowlists, or dedicated write logic.

Test using the exact ObjectMapper that the Spring Data REST endpoint uses. Do not infer behavior solely from a standalone ObjectMapper constructed in a unit test.

## 11. Authorization for write operations

Allowing HTTP POST or PATCH at the URL level does not mean every user is authorized to modify every field. Authorization should be tied to specific actions and resources.

Example business rules:

- Users may edit only their own profile.
- Only admins may change roles.
- Tenant A may not assign an association to an entity belonging to tenant B.
- Only approvers may transition state from PENDING to APPROVED.
- Prices, balances, and risk scores are computed by the server.
- Managers may only make changes allowed by organizational rules.

You can use Spring Security request authorization and method security to protect endpoints and services. For sensitive operations, verify permissions against the current entity and workflow state inside the business flow.

Hiding HAL links does not protect endpoints. Clients can invoke URIs directly. The server must enforce permissions on every actual request.

## 12. Testing mass assignment with integration tests

Tests should submit payloads containing both valid properties and disallowed properties, then read back the database to verify state.

Example with a READ_ONLY property:

~~~java
@Test
void patchCannotChangeServerManagedFields() throws Exception {
    Person person = new Person();
    person.setDisplayName("Ada");
    person.setRole("USER");
    person = repository.save(person);

    mockMvc.perform(patch("/api/people/{id}", person.getId())
            .contentType(MediaType.APPLICATION_JSON)
            .accept("application/hal+json")
            .content("""
                {
                  "displayName": "Ada Lovelace",
                  "role": "ADMIN"
                }
                """))
        .andExpect(status().is2xxSuccessful());

    Person saved = repository.findById(person.getId())
        .orElseThrow();

    assertThat(saved.getDisplayName())
        .isEqualTo("Ada Lovelace");
    assertThat(saved.getRole()).isEqualTo("USER");
}
~~~

Adapt the example to your project's PATCH media type and configuration. If the API policy is to reject payloads containing forbidden properties, assert the error status and confirm the database remains unchanged.

Tests should cover:

1. POST with allowed fields creates the entity successfully.
2. POST attempting to send role, tenant, or owner does not alter server-managed values.
3. PUT updates only fields permitted by the contract.
4. PATCH of one valid field does not alter other fields.
5. PATCH sending only READ_ONLY properties does not alter server-managed state.
6. Payloads with unknown keys follow the published reject/ignore policy.
7. Association updates referencing out-of-tenant entities are rejected.
8. Unauthorized users cannot change roles or approval status.
9. Responses do not expose secrets.
10. Database state is verified after every request, not just the HTTP status.

## 13. Verification examples using curl

Create a Person with permitted data only:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"displayName":"Ada Lovelace","email":"ada@example.com"}' \
  http://localhost:8080/api/people
~~~

Attempt to send extra server-managed fields in a test environment:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"displayName":"Ada","role":"ADMIN","approved":true}' \
  http://localhost:8080/api/people
~~~

Update profile using a dedicated DTO endpoint:

~~~bash
curl -i -X PATCH \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"displayName":"Ada Lovelace","email":"ada@example.com"}' \
  http://localhost:8080/api/person-commands/42
~~~

Attempt to assign an association in a test environment:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data-binary "http://localhost:8080/api/addresses/7" \
  http://localhost:8080/api/people/42/address
~~~

Requests with unauthorized fields should be tested only in appropriate test data/environments. After each request, read the entity back to confirm the server did not persist off-contract changes.

## 14. Remediation workflow when mass assignment is discovered

When a property is modified unexpectedly:

1. Identify the URI, HTTP method, principal, and actual request body.
2. Identify which property changed in the entity/database.
3. Inspect entity fields, getters/setters, constructors, and Jackson annotations.
4. Inspect the ObjectMapper/message converter used by Spring Data REST.
5. Determine whether the endpoint binds directly to a domain object or uses a DTO.
6. Classify properties by write permissions and use cases.
7. Mark server-managed properties with READ_ONLY or exclude them from JSON as appropriate.
8. Migrate endpoints with restricted inputs to DTO allowlists if needed.
9. Audit association resources and URI reference binding.
10. Enforce validation and authorization on the server.
11. Add integration tests sending payloads with sensitive fields.
12. Review records that were improperly modified and remediate them according to the application's data recovery process.

Do not merely update the UI to hide fields. Fix the contract and enforcement on the server.

## 15. Common misconceptions

1. **The field is not on the form, so clients cannot send it.** Clients can craft HTTP requests manually.
2. **Unknown-property handling prevents mass assignment.** It only addresses keys absent from the model; sensitive properties that already exist can still be bound.
3. **READ_ONLY is an authorization mechanism.** It controls JSON binding, not access control.
4. **JsonIgnore is always the best choice.** When clients need to read a field without writing it, READ_ONLY expresses the intent better.
5. **PATCH has no risk because it only updates partially.** A single sensitive property in the payload can still be overwritten.
6. **Hiding an association link means the relationship cannot be updated.** Both association URIs and JSON binding must be controlled.
7. **exported=false acts as a property allowlist.** It controls exporting resources/methods/associations, not a general per-property write policy.
8. **Validation automatically blocks disallowed properties.** Validation checks values; allowlists define which properties are accepted.
9. **Client-supplied tenant/owner is trustworthy.** The server must derive or verify ownership permissions on the entity.
10. **Checking the response is enough.** Data may have been persisted even if the response omits that field.
11. **Event handlers automatically strip every unintended field.** Handlers only run the logic programmed into them; they do not replace binding policies.
12. **Projections protect write endpoints.** Projections primarily shape read representations, not write allowlists.

## 16. Implementation checklist

- Define property allowlists for each create/update operation.
- Mark IDs, tenant, owner, audit, and server-managed state appropriately.
- Use READ_ONLY when a property needs to be read without accepting JSON input.
- Use WRITE_ONLY for necessary secret inputs and handle them securely.
- Use JsonIgnore when a property should never be exchanged via JSON.
- Use request DTOs for use cases with restricted inputs.
- Explicitly map each permitted property inside the service.
- Never trust client-supplied tenantId, ownerId, or role.
- Check permissions on both source and target entities when updating associations.
- Enforce Bean Validation and domain invariants.
- Protect sensitive operations with Spring Security/service authorization.
- Verify POST, PUT, PATCH, and association updates.
- Define an explicit policy for unknown JSON properties.
- Verify database state after test requests.
- Never rely on the UI or HAL links as security boundaries.
- Never leak secrets or internal data in responses/logs.

## Summary

Mass assignment in Spring Data REST occurs when a request body is bound onto a domain object and clients can write properties beyond the use case's permissions. The risk exists across POST, PUT, PATCH, and association resources.

Classify properties by write permission, use Jackson READ_ONLY for readable server-managed fields, JsonIgnore for fields excluded from JSON, and DTO allowlists when a strict input contract is needed. Services must derive tenant, owner, role, and audit data from server context; association updates must verify permissions on both source and target entities.

Validation checks values, authorization checks permissions, and allowlists restrict accepted fields. Test direct requests carrying extra sensitive properties and verify that the database does not change unexpectedly.

## References

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Repository Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Jackson — JsonProperty.Access](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
- [Jackson — JsonIgnore](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
