# Limitations of Projections for Write Input, Authorization, and DTO Contracts

## Objectives

In Spring Data REST, projections and excerpts help shape the representation clients see when reading data. However, they do not automatically act as a control mechanism for writable data, do not replace authorization, and do not fully define a DTO contract for create/update operations.

Three responsibilities must be separated:

- **Projection/Excerpt:** determines how a read representation is serialized.
- **Authorization:** determines who is allowed to perform which operation on which resource/data.
- **DTO and write model:** specifies the exact input/output data of a use case and how that data translates into domain changes.

If a projection is used as a security barrier or as a request body allowlist, the application may inadvertently allow writing fields that clients should not control.

## 1. Projections and excerpts serve read representations

A projection in Spring Data REST is typically declared with `@Projection`. It describes a view of a domain object for serialization into a response.

Example domain type:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private boolean active;

    private BigDecimal salary;

    // getters and setters
}
~~~

Projection exposing a subset of properties:

~~~java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();

    boolean isActive();
}
~~~

Clients can request the projection via the query parameter:

~~~http
GET /api/people/42?projection=summary
Accept: application/hal+json
~~~

The returned representation may contain only the properties exposed by the projection along with hypermedia links:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "active": true,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people/42"
    }
  }
}
~~~

Fields omitted from the projection, such as `email` or `salary`, do not appear in this view. That applies only to the representation built for the response; it does not mean those fields are removed from the entity or locked at the write layer.

### Projections do not create a new entity

A projection is neither a separate database record nor a domain object copy that clients can write back. It is a way to present data from a domain object.

A projection can:

- Select a subset of getters included in the response.
- Combine properties from the current object and exposed associations.
- Reshape the representation for a specific read use case.
- Provide a more compact view for clients.

A projection does not automatically:

- Create a separate table or entity.
- Change read/write permissions on fields.
- Validate request bodies.
- Prevent clients from sending fields outside the projection in POST/PUT/PATCH.
- Map a request DTO into a business command.

## 2. Excerpts are default projections for collections

An excerpt projection is a projection applied by default by Spring Data REST to items rendered inside a collection resource, if an excerpt projection is configured/registered for the domain type.

Example:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

When a client calls:

~~~http
GET /api/people
Accept: application/hal+json
~~~

items in `_embedded.people` can use the `PersonSummary` representation. When calling the item URI directly, the client may receive the item's default representation or request a specific projection as configured.

Excerpts keep collection lists lighter and better aligned with list-display needs. They are not an allowlist of fields that POST or PUT may accept.

## 3. Projections do not restrict request bodies on writes

A dangerous misconception is: "If a projection only exposes three fields, then clients can only write those three fields." That is not a guarantee of Spring Data REST.

For example, the projection exposes only:

~~~java
@Projection(name = "publicView", types = Person.class)
public interface PersonPublicView {

    String getFirstName();

    String getLastName();
}
~~~

Yet the entity also has:

~~~java
private String email;
private BigDecimal salary;
private boolean admin;
~~~

The projection does not automatically stop POST/PUT requests from sending these fields. On writes, the request body is deserialized according to the application's Jackson/domain type mapping and configuration, then enters the repository save flow. A projection selected to serialize responses is not an input filter.

For example, a client can attempt to send:

~~~http
POST /api/people
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Nguyen",
  "salary": 999999,
  "admin": true
}
~~~

If properties are bindable and no proper protection is in place, their absence from a read projection does not guarantee they are rejected in the request body. Depending on Jackson configuration, visibility, setters, mapping, and security, fields may be bound, ignored, or cause an error. Do not rely on projections to determine that outcome.

In particular, sensitive fields such as `role`, `admin`, `ownerId`, `approved`, `balance`, or `salary` must be explicitly protected at the write boundary and domain/service layer.

## 4. Authorization is a separate responsibility

Authorization decides which operations the current principal is permitted to perform. Projections only adjust representations; hiding a field from a response does not make that field safe from write requests or other direct access.

For example, an API may allow all authenticated users to read the Person list while allowing only HR to modify `salary`. This rule must be enforced via Spring Security, service authorization, or an appropriate policy.

An illustrative URL-level configuration:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/people/**")
                .hasAuthority("people:read")
            .requestMatchers(HttpMethod.POST, "/api/people")
                .hasAuthority("people:create")
            .requestMatchers(HttpMethod.PUT, "/api/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.PATCH, "/api/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.DELETE, "/api/people/**")
                .hasAuthority("people:delete")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

This example illustrates separating permissions by HTTP method and resource path. A real application needs to configure authentication, CSRF, CORS, and remaining rules suitable for its client/API type.

### URL-level authorization is not enough for all cases

Operation permissions may depend on specific data:

- Users may only edit Persons belonging to their own department.
- Creators may edit records only while the record is still in DRAFT status.
- Only managers may change approval status.
- Users may only view their own data.

These rules must be checked at the service/domain boundary or via method security, rather than relying solely on URLs.

Method security example:

~~~java
@Service
public class PersonService {

    @PreAuthorize("hasAuthority('people:update')")
    public Person updatePerson(Long id, UpdatePersonCommand command) {
        // Load entity, enforce ownership/business rules, apply allowed changes.
        // Save through repository.
        return null;
    }
}
~~~

The method body above only illustrates where authorization belongs; the application must implement loading the entity, checking record-level permissions, and applying actual changes.

### Hiding a field in a response is not authorization

If `salary` does not appear in `PersonPublicView`, clients do not see `salary` in that representation. However, this does not prove clients cannot:

- Send `salary` in a request body.
- Call another endpoint that returns `salary`.
- Follow an association/link to a resource containing sensitive data.
- Use another projection that exposes `salary`.

Protect sensitive data across all read and write paths using consistent policies. Projections can help reduce returned data, but they do not replace access control.

## 5. DTOs define explicit input contracts

A DTO (Data Transfer Object) is a data type designed for a specific communication boundary. For write operations, DTOs clearly specify which fields clients are allowed to send.

Example:

~~~java
public record CreatePersonRequest(
        @NotBlank String firstName,
        @NotBlank String lastName,
        @Email String email
) {
}
~~~

This DTO has only three input fields. Clients do not have `salary`, `admin`, or `approved` fields in the Person creation contract.

A custom controller can accept the DTO:

~~~java
@RestController
@RequestMapping("/api/person-commands")
public class PersonCommandController {

    private final PersonService personService;

    public PersonCommandController(PersonService personService) {
        this.personService = personService;
    }

    @PostMapping
    public ResponseEntity<PersonResponse> create(
            @Valid @RequestBody CreatePersonRequest request) {

        PersonResponse response = personService.create(request);

        return ResponseEntity
                .created(URI.create("/api/people/" + response.id()))
                .body(response);
    }
}
~~~

This example illustrates a dedicated API boundary for the Person creation command. In a real application, the `Location` URI should come from the resource URI created by the application or from an appropriate link/resource mapping, rather than hardcoding if paths can change.

The service maps the DTO to the domain:

~~~java
@Service
public class PersonService {

    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('people:create')")
    public PersonResponse create(CreatePersonRequest request) {
        Person person = new Person();
        person.setFirstName(request.firstName());
        person.setLastName(request.lastName());
        person.setEmail(request.email());

        // Sensitive or server-owned values are assigned by trusted logic.
        person.setActive(true);
        person.setAdmin(false);

        Person saved = repository.save(person);

        return new PersonResponse(
                saved.getId(),
                saved.getFirstName(),
                saved.getLastName(),
                saved.getEmail()
        );
    }
}
~~~

The example above shows that only permitted fields from the DTO are copied to the entity. Server-managed values are assigned by trusted logic. DTOs do not grant permissions on their own; the service still needs authorization and business validation.

## 6. Separating Create, Update, and Response DTOs when contracts differ

Sharing one DTO across every operation can make the API hard to control. Creation and updates usually have different requirements:

| DTO | Purpose | Example fields |
|---|---|---|
| `CreatePersonRequest` | Create Person | firstName, lastName, email |
| `UpdatePersonRequest` | Update allowed fields | firstName, lastName, email |
| `PersonResponse` | Data returned to clients | id, firstName, lastName, status |
| `PersonAdminResponse` | Separate view for authorized users | Adds administrative fields permitted for reading |

Example response DTO:

~~~java
public record PersonResponse(
        Long id,
        String firstName,
        String lastName,
        String email
) {
}
~~~

Do not include internal fields such as password hashes, access tokens, or admin flags in public response DTOs. If a role is permitted to view additional data, you can define a separate response contract or a controlled serialization policy.

DTOs should reflect the use case and field ownership:

- Client-provided fields.
- Server-generated fields, such as IDs and timestamps.
- Workflow-managed fields, such as `approved`/`status`.
- Role-restricted readable fields.
- Internal fields that must not be exposed.

## 7. DTOs and projections can coexist

Projections and DTOs are not mutually exclusive. They serve different directions of data flow:

~~~text
READ
Repository / Domain
       |
       v
Projection / Excerpt
       |
       v
HAL representation
       |
       v
Client

WRITE
Client request
       |
       v
Create/Update DTO
       |
       v
Validation + Authorization
       |
       v
Application Service
       |
       v
Domain changes + Repository save
       |
       v
Response DTO / HAL resource
~~~

For example:

- Collection GET uses an excerpt projection to return a compact list.
- Item GET lets clients select an appropriate projection.
- POST accepts `CreatePersonRequest` via a custom controller.
- PUT/PATCH accepts `UpdatePersonRequest` or a specialized command.
- The service validates, checks entity-level permissions, and applies only allowed fields.
- The response returns a DTO or an appropriate resource representation.

When using Spring Data REST repository endpoints directly for writes, the request body is typically deserialized into the domain representation according to the application's configuration. If a strict per-use-case input contract is required, a custom controller/application service with DTOs is usually clearer and easier to control.

## 8. Jackson utilities do not replace DTOs/policies

Jackson provides annotations to control serialization/deserialization, for example:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private String systemCode;

@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String internalNote;
~~~

- `READ_ONLY`: the field may appear during serialization but is ignored during deserialization according to Jackson configuration.
- `WRITE_ONLY`: the field is accepted during deserialization but omitted during serialization.

These annotations can be useful for simple contracts, but they are not authorization. They do not verify whether a user is allowed to write a field and do not replace validation/business rules. You must also inspect all other serializers/deserializers, projections, controllers, and endpoints using the same entity.

Do not rely on `@JsonIgnore` or ad-hoc visibility settings as the sole protection for sensitive fields. Audit all read/write paths and enforce permissions at the appropriate layer.

## 9. Common misconceptions

- **The projection only has three fields, so write requests only accept three fields.** False: projections shape read representations; request binding is a separate flow.
- **If a field is hidden in the response, users cannot modify that field.** False: write validation, DTO allowlists, and authorization are required.
- **An excerpt is a creation DTO.** False: an excerpt is the default projection for items in a collection representation.
- **Projections control who can read a field.** Not automatically; proper access control or representation policies are required.
- **DTOs secure endpoints on their own.** DTOs define data shape, but validation, authorization, and business checks are still needed.
- **Checking permissions by URL alone is sufficient.** Some permissions depend on the record's owner, tenant, state, or relationships.
- **Sharing the entity across all requests is safe.** Entities may contain internal fields clients should not control; using DTOs/commands clearly bounds input.
- **Jackson annotations are authorization.** Annotations control serialization/binding; they do not decide whether a principal is authorized to act.

## 10. API design checklist

When designing Spring Data REST with projections and write operations, answer each question separately:

1. **Read representation:** Which client needs to see which fields? Which projection/excerpt is appropriate?
2. **Write input:** Exactly which fields is the client allowed to send for each use case?
3. **Validation:** Which required fields, formats, limits, and invariants must be checked?
4. **Authorization:** Who can create, read, update, and delete? Do permissions depend on record/tenant/status?
5. **Server-owned fields:** Which fields must be assigned by the server or workflow?
6. **DTO contract:** Do create, update, and response need separate types?
7. **Mapping:** Which fields are copied from DTO to domain? Which fields must be ignored or recomputed?
8. **Response exposure:** Could a projection/response DTO inadvertently leak sensitive data?
9. **Endpoint coverage:** Does any other read/write path bypass the designed policy?
10. **Tests:** Are there tests for payloads with disallowed fields, unauthorized users, different owners, and responses not leaking sensitive fields?

## 11. Takeaways

- Projections and excerpts control how domain data is presented in read responses.
- Projections are not allowlists for POST/PUT/PATCH and do not automatically restrict writable fields.
- Hiding a field in a representation does not mean that field is protected.
- Authorization must be enforced independently at HTTP security and/or the service/domain boundary.
- DTOs/commands define the input contract per use case; services map permitted fields onto domain objects.
- Create, update, and response may require separate DTOs.
- Jackson annotations assist with serialization/binding but do not replace authorization.
- For strict write contracts, a custom controller + DTO + application service usually creates a clearer boundary than accepting entities directly via repository REST endpoints.

## References

- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Jackson Annotations — JsonProperty.Access](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
