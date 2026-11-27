# @JsonIgnore, Read-Only Properties, and Write-Only Properties in Spring Data REST

Spring Data REST uses Jackson to map JSON data to domain object properties when reading and writing resources. Jackson annotations let you control which properties appear in responses and which properties are accepted from requests.

Three common approaches serve different purposes:

- **@JsonIgnore** excludes a property from JSON mapping, typically for both response serialization and request deserialization.
- **@JsonProperty(access = READ_ONLY)** allows returning a property in responses but does not accept its value from JSON requests.
- **@JsonProperty(access = WRITE_ONLY)** accepts a property from JSON requests but does not include it in JSON responses.

These rules are useful when exposing repositories via Spring Data REST, but they govern JSON mapping rather than authorization mechanisms or database immutability constraints.

## 1. How Jackson Participates in Spring Data REST's JSON Flow

When a client reads an item resource, Spring Data REST retrieves the domain object from the repository and uses Jackson to produce a JSON or HAL representation. When a client sends POST, PUT, or PATCH with a JSON body, Jackson participates in converting request data into values on the domain object before Spring Data REST processes and persists it.

Example of a simple HAL response:

~~~json
{
  "id": 42,
  "name": "An Nguyen",
  "email": "an@example.com",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Jackson annotations on fields, getters, or setters affect which data properties are serialized or deserialized. Hypermedia links such as _links are added by Spring Data REST according to resource configuration; they are not regular business fields of the entity.

Because Spring Data REST typically exposes the repository's domain type directly, JSON annotations on a domain type can affect multiple endpoints that share the same representation. Clarify which properties should be hidden, read-only, or write-only before applying annotations.

## 2. @JsonIgnore: Skipping a Property in JSON Mapping

@JsonIgnore marks a property to be ignored by Jackson. The typical behavior is excluding the property from JSON responses and not taking values from JSON requests to assign to that property.

Example Person entity with an internal note:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Person {

    @Id
    private Long id;

    private String name;

    @JsonIgnore
    private String internalNote;

    // getters and setters
}
~~~

When a client calls:

~~~http
GET /people/42
Accept: application/hal+json
~~~

the representation can include id and name without internalNote:

~~~json
{
  "id": 42,
  "name": "An Nguyen"
}
~~~

If the client sends:

~~~http
PATCH /people/42
Content-Type: application/json

{
  "name": "An",
  "internalNote": "new value"
}
~~~

Jackson does not use internalNote from the JSON to update the property marked with @JsonIgnore. Depending on Jackson configuration, the ignored property may be silently skipped or the request may be rejected if the application enables error handling for ignored properties.

### When Should You Use @JsonIgnore?

Use it when a property should not participate in the API's JSON representation in either direction. For example:

- An internal field used only for domain processing.
- A technical property that does not need to be exposed to clients.
- An association or property that should not be read/written through the JSON endpoint in use.
- A derived value that the API neither wants to expose nor accept from clients.

Do not use @JsonIgnore for a property that needs to accept input during creation/updates and only needs to be hidden from responses. That case is better suited to WRITE_ONLY.

## 3. @JsonProperty(access = READ_ONLY): Read-Only from the API Perspective

READ_ONLY means Jackson allows serializing the property into responses but ignores the corresponding value when deserializing JSON requests.

For example, server-managed ID and creation timestamp:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonProperty.Access;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.time.Instant;

@Entity
public class Person {

    @Id
    @JsonProperty(access = Access.READ_ONLY)
    private Long id;

    private String name;

    @JsonProperty(access = Access.READ_ONLY)
    private Instant createdAt;

    // getters and setters
}
~~~

When performing GET on the resource, clients still see id and createdAt:

~~~json
{
  "id": 42,
  "name": "An Nguyen",
  "createdAt": "2026-11-11T02:30:00Z"
}
~~~

If a client sends a request containing these values:

~~~http
PATCH /people/42
Content-Type: application/json

{
  "name": "An",
  "id": 999,
  "createdAt": "2000-01-01T00:00:00Z"
}
~~~

Jackson does not bind id and createdAt from the JSON request onto the READ_ONLY properties. The request can update name according to application configuration and logic, while server-managed values are not taken from the body.

### Suitable Cases for READ_ONLY

- Database- or system-generated IDs.
- createdAt and createdBy recorded by the server.
- Computed statuses that clients may only view.
- Aggregated figures or derived values that clients must not send to overwrite.

READ_ONLY does not generate values for properties by itself. The application still needs to populate IDs, timestamps, or audit fields through persistence, entity listeners, auditing, or an appropriate service.

## 4. @JsonProperty(access = WRITE_ONLY): Write-Only from the API Perspective

WRITE_ONLY allows Jackson to read values from JSON requests while not serializing that property into responses.

For example, an API receiving a password when creating or changing credentials:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonProperty.Access;

public class AccountInput {

    private String username;

    @JsonProperty(access = Access.WRITE_ONLY)
    private String password;

    // getters and setters
}
~~~

When a client sends a request:

~~~http
POST /accounts
Content-Type: application/json

{
  "username": "an",
  "password": "temporary-secret"
}
~~~

Jackson can bind password into the target object. When the representation is serialized, the password property does not appear:

~~~json
{
  "username": "an"
}
~~~

If using an entity directly as the request/response type in Spring Data REST, ensure WRITE_ONLY properties are handled properly in both creation and update flows according to the application design.

### Suitable Cases for WRITE_ONLY

- Passwords or new passwords.
- Verification codes that are only submitted as input.
- Input secrets that the API must never return.
- Input data used solely for an operation that should not appear in responses.

WRITE_ONLY only prevents Jackson from serializing the property. It does not automatically encrypt, hash, or protect the stored value. For passwords, the application must hash them using an appropriate algorithm before saving and never write raw passwords to logs or return them via another endpoint.

## 5. Comparing the Three Configurations

| Configuration | JSON response | JSON request | Purpose |
|---|---|---|---|
| Default | Can be serialized | Can be deserialized | Normal reading and writing |
| @JsonIgnore | Omitted | Ignored | Excluded from JSON mapping |
| @JsonProperty(access = READ_ONLY) | Included | Ignored when reading request | Server-provided, client read-only |
| @JsonProperty(access = WRITE_ONLY) | Omitted | Included | Client-submitted, never returned by server |

Jackson defines additional access modes such as READ_WRITE and AUTO. AUTO is the default mode following Jackson's property detection rules; READ_WRITE allows both serialization and deserialization. When expressing an API contract clearly, READ_ONLY and WRITE_ONLY are usually easier to understand.

## 6. Placing Annotations on Fields, Getters, or Setters

Jackson can detect a property from a field, getter, setter, or constructor parameter depending on visibility and ObjectMapper configuration.

Example placing the annotation on a getter:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
public Instant getCreatedAt() {
    return createdAt;
}
~~~

Or placing it on a field:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private Instant createdAt;
~~~

Declare annotations consistently for the same property. If a field, getter, and setter carry conflicting annotations, Jackson can merge metadata according to property introspection rules; the result can be confusing when a model has multiple accessors.

If a property has separate getter and setter methods with different read/write requirements, using @JsonProperty(access = ...) at the property level expresses intent more clearly than arbitrarily attaching @JsonIgnore to one accessor.

## 7. Example Combining Property Types in an Entity

An entity can combine regular, read-only, write-only, and ignored properties:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonProperty.Access;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.time.Instant;

@Entity
public class Account {

    @Id
    @JsonProperty(access = Access.READ_ONLY)
    private Long id;

    private String username;

    @JsonProperty(access = Access.WRITE_ONLY)
    private String password;

    @JsonProperty(access = Access.READ_ONLY)
    private Instant createdAt;

    @JsonIgnore
    private String internalRiskFlag;

    // getters and setters
}
~~~

Expected JSON contract:

- id: returned by the server; clients cannot assign it via JSON requests.
- username: readable and writable according to other application rules.
- password: submitted by clients; omitted from responses.
- createdAt: returned by the server; clients cannot write it via JSON requests.
- internalRiskFlag: excluded from JSON mapping in both directions.

Annotations do not replace validation or authorization. For example, whether username may be changed still needs to be governed by business rules and caller permissions.

## 8. Impact on POST, PUT, and PATCH

Spring Data REST uses Jackson when receiving JSON bodies for write operations. Consequently, READ_ONLY, WRITE_ONLY, and JsonIgnore rules can affect different requests.

### POST Creating a Resource

- Regular properties can be bound from the body.
- READ_ONLY does not accept client-sent values.
- WRITE_ONLY accepts values from the body but does not appear when the response is serialized.
- JsonIgnore is ignored during JSON mapping.

For example, clients can send username and password when creating an account; id and createdAt are managed by the server.

### PUT Replacing a Representation

PUT expresses the intent to replace resource state according to the request representation. READ_ONLY properties are still not bound from JSON. Properties ignored or omitted from the body can be affected by how Spring Data REST binds domain objects and by application logic.

Do not treat READ_ONLY as an automatic data-preservation mechanism across all PUT workflows. Test the entity state after requests, especially when the domain model uses constructors, setters, factory methods, or custom deserializers.

### PATCH Partially Updating a Resource

PATCH typically sends only the properties that need to change. READ_ONLY and JsonIgnore properties are not updated from the body per their Jackson configuration; WRITE_ONLY properties can accept input values without appearing in the response.

Test cases where a key is absent, present with null, and present with a concrete value. How null values, nested objects, and associations are handled also depends on binding, validation, and application configuration.

## 9. JSON Annotations Are Not a Security Mechanism

Do not rely on serialization annotations to protect sensitive data.

- READ_ONLY does not prevent modifying properties via internal services, the database, custom controllers, or other endpoints.
- WRITE_ONLY does not hash passwords and does not prevent the application from logging secrets.
- JsonIgnore does not replace authorization; data can still be accessed via another endpoint or serializer.
- Another projection, custom serializer, or ObjectMapper can produce a different representation than the endpoint under consideration.

Enforce access control at the security/service layer, validate input data, protect secrets at rest, and audit all endpoints that may expose the same domain type.

If different user groups need to see different sets of properties, static annotations on an entity may not be enough. In that case, consider DTOs, appropriate read projections, custom controllers, or separate representations tailored to use cases and permissions.

## 10. Relationship with Associations and HAL

Spring Data REST typically represents associations as HAL links in _links. An association property may be presented as a link rather than a nested JSON object, depending on the representation and projection.

Example:

~~~json
{
  "name": "An",
  "_links": {
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~

If @JsonIgnore is placed on an association property, the corresponding JSON property may be excluded from serialization/deserialization. However, how Spring Data REST discovers and exposes associations also involves repository metadata and REST configuration. Inspect actual HAL responses rather than assuming a field annotation always removes every related link.

If the goal is not to expose an association through Spring Data REST, review association/repository export configuration supported by your version. JsonIgnore controls Jackson properties; export configuration controls whether Spring Data REST exposes resources and associations.

## 11. Testing Serialization and Deserialization

Test both JSON directions. A test that only calls GET and asserts a field is hidden does not prove the server ignores that field in incoming requests.

Cases to verify:

1. GET an item resource and confirm READ_ONLY fields still appear.
2. GET an item resource and confirm WRITE_ONLY and JsonIgnore fields do not appear.
3. Send POST with fake id or createdAt values and confirm the server does not take them from the body.
4. Send POST with password and confirm the value is received, processed, and stored safely without appearing in the response.
5. Send PATCH with a READ_ONLY property and confirm server-managed values are not overwritten.
6. Send a request containing a JsonIgnore property and confirm behavior matches Jackson configuration.
7. Test responses when error handling for ignored properties is enabled/disabled if the application configures it.
8. Verify association links in HAL after applying annotations.
9. Check custom serializers, projections, and other endpoints if they share the same entity.

An independent Jackson unit test can use ObjectMapper:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = mapper.writeValueAsString(account);

// Assert password and internalRiskFlag do not appear.
// Assert id and createdAt still appear.
~~~

For Spring Data REST, add HTTP integration tests because a standalone ObjectMapper in a unit test may differ from the configuration registered by the application for the REST layer.

## 12. Choosing Annotations Based on Requirements

| API Requirement | Suitable Approach |
|---|---|
| Neither accept nor return the property | @JsonIgnore |
| Return the property but prevent clients from writing it via JSON | @JsonProperty(access = READ_ONLY) |
| Accept the property but omit it from JSON responses | @JsonProperty(access = WRITE_ONLY) |
| Normal reading and writing | No access override needed |
| Different fields by role or use case | Security + appropriate DTO/projection/custom representation |

Before choosing an annotation, answer two questions for each property:

1. Does the server need to include this value in the JSON response?
2. Should the server accept this value from a JSON request?

If the answers are no/no, use JsonIgnore; yes/no, use READ_ONLY; no/yes, use WRITE_ONLY; yes/yes, keep the default behavior if no other requirements apply.

## 13. Key Points to Remember

- Spring Data REST uses Jackson to map JSON requests and responses to domain objects.
- @JsonIgnore omits a property from JSON mapping; @JsonProperty READ_ONLY only outputs data; WRITE_ONLY only accepts input data.
- READ_ONLY fits IDs, timestamps, and server-managed values.
- WRITE_ONLY fits passwords or input secrets, though the application must still hash/protect the value before storing.
- Annotations can be placed on fields or accessors; avoid conflicting metadata on the same property.
- Annotations affect JSON mapping and do not replace authorization, validation, or database constraints.
- For HAL associations, inspect both JSON properties and links exposed by Spring Data REST.
- Test both response serialization and request deserialization against actual Spring Data REST endpoints.

## References

- [Jackson — JsonIgnore API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Jackson — JsonProperty.Access API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
- [Spring Data REST — Reference documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Jackson — Annotations documentation](https://github.com/FasterXML/jackson-annotations)
