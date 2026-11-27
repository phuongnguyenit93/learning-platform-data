# Partial Updates, Null Values, and Avoiding Unintended Data Overwrites

A partial update modifies only the fields that a client actually intends to change. In Spring Data JPA APIs, a common mistake is receiving a DTO with many `null` properties, creating a new entity from that DTO, and calling `save()`. Properties omitted from the request can be interpreted as null values and overwrite existing data.

To update safely, three states must be clearly distinguished for each field:

1. **Absent (not sent):** keep the current value.
2. **Sent as null:** clear the value if business rules and the schema allow it.
3. **Sent with a value:** replace the current value.

A regular Java `String` property cannot, after JSON deserialization, distinguish by itself between an absent field and a field explicitly sent as `null`. The DTO, mapping, and transaction design must preserve this distinction until the entity is updated.

## 1. Distinguishing PUT, PATCH, and the Meaning of Null

Under common HTTP conventions:

- `PUT` typically replaces the entire representation of a resource. The client must send all fields required by the representation.
- `PATCH` applies a partial modification. Omitted fields are generally left untouched, while how `null` is interpreted depends on the format and API contract.

With standard JSON:

```json
{
  "name": "Lan"
}
```

The request includes only `name`; the client is not asking to change `email`.

```json
{
  "name": "Lan",
  "email": null
}
```

The second request includes the `email` field and sends a null value. If the API specifies that null means clearing the email, the server must set email to null. If the API requires email to be present, the server must return a validation error.

Never assume every null value has the same meaning. Document the contract explicitly for every field, especially numbers, booleans, dates/times, relationships, and collections.

## 2. Why Creating an Entity from a DTO and Calling save() Can Lose Data

Suppose we have an entity:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private String email;

    private String phone;

    // constructors, getters and setters
}
```

A DTO accepts only a subset of fields:

```java
public record CustomerUpdateRequest(
        String name,
        String email
) {
}
```

An error-prone approach:

```java
@Transactional
public void update(Long id, CustomerUpdateRequest request) {
    Customer customer = new Customer();
    customer.setId(id);
    customer.setName(request.name());
    customer.setEmail(request.email());

    customerRepository.save(customer);
}
```

If the client sends only `name`, `request.email()` will be null. The new entity also has `phone = null`. When Spring Data JPA chooses `EntityManager.merge()` for an existing entity, the state of the passed entity is copied onto a managed entity. Null fields in the detached object can overwrite values already stored in the database.

Keep in mind:

- Spring Data JPA's `save()` usually calls `persist()` if the entity is detected as new.
- For a non-new entity, `save()` usually calls `merge()`.
- `merge()` copies the state of the input object into a managed instance and returns that managed instance.
- The object passed into `merge()` does not itself become managed merely because `merge()` was called.

Therefore, do not construct an entity from an incomplete DTO as if it were a full record and call `save()` when the goal is only to update a few attributes.

## 3. The Safe Approach: Load the Managed Entity and Mutate Only Sent Fields

For typical partial updates, the most controllable approach is to load the entity within a transaction, apply permitted changes, and let JPA dirty checking persist the modified attributes.

```java
@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public Customer updateName(Long id, String newName) {
        Customer customer = customers.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Customer not found: " + id));

        customer.setName(newName);

        // customer is managed within the transaction.
        // Dirty checking persists changes on flush/commit.
        return customer;
    }
}
```

The entity is loaded by the repository inside an active transaction. When only the setter for `name` is called, `email` and `phone` are not reassigned. There is no need to call `save()` again for an entity already managed in the same persistence context; dirty checking detects the change.

The transaction must wrap both the read and the update. If `findById()` runs in a short repository transaction and the entity is modified after that method returns, the entity may already be detached and subsequent changes will not be saved automatically.

This approach also allows checking permissions, current state, and business rules before applying modifications. Do not accept a JPA entity directly from the request body and attach it to the persistence context.

## 4. Preserving Absent, Null, and Value States in the DTO

A DTO using plain `String` fields cannot distinguish absent from explicit null after deserialization. With Jackson, setters can mark whether a field appeared in the JSON. The setter is invoked even when the value is null, whereas for an absent field the setter is not called.

Example DTO:

```java
import com.fasterxml.jackson.annotation.JsonSetter;

public class CustomerPatchRequest {

    private boolean nameProvided;
    private String name;

    private boolean emailProvided;
    private String email;

    @JsonSetter("name")
    public void setName(String name) {
        this.nameProvided = true;
        this.name = name;
    }

    @JsonSetter("email")
    public void setEmail(String email) {
        this.emailProvided = true;
        this.email = email;
    }

    public boolean isNameProvided() {
        return nameProvided;
    }

    public String getName() {
        return name;
    }

    public boolean isEmailProvided() {
        return emailProvided;
    }

    public String getEmail() {
        return email;
    }
}
```

Under Jackson's default configuration for setters, `@JsonSetter` receives explicit null. If `Nulls.SKIP` or a custom deserializer is configured, behavior may differ; test against your application's actual configuration.

The Service applies all three states accurately:

```java
@Transactional
public Customer patch(Long id, CustomerPatchRequest request) {
    Customer customer = customers.findById(id)
            .orElseThrow(() ->
                    new IllegalArgumentException(
                            "Customer not found: " + id));

    if (request.isNameProvided()) {
        if (request.getName() == null
                || request.getName().isBlank()) {
            throw new IllegalArgumentException(
                    "Name must not be blank");
        }
        customer.setName(request.getName());
    }

    if (request.isEmailProvided()) {
        // null means clearing email per the API contract.
        customer.setEmail(request.getEmail());
    }

    return customer;
}
```

Outcome:

| Submitted JSON | `name` | `email` |
|---|---|---|
| `{}` | Unchanged | Unchanged |
| `{"name":"Lan"}` | Changed to Lan | Unchanged |
| `{"email":null}` | Unchanged | Set to null if allowed |
| `{"email":"lan@example.com"}` | Unchanged | Changed to new address |
| `{"name":null}` | Validation fails in example | Unchanged |

This is a straightforward implementation. For DTOs with many fields, you can create a wrapper type representing `UNSET`, `NULL`, and `VALUE`, or use a library like `JsonNullable<T>` to express the three states explicitly. Do not rely on `Optional<T>` as a default solution without verifying how your JSON library handles absent versus explicit null.

## 5. Defining Null Semantics per Data Type

Null behavior must be defined by business meaning, not solely by Java type.

| Field type | Absent | Explicit null | Value provided |
|---|---|---|---|
| Required name | Unchanged | Reject | Validate and update |
| Optional email | Unchanged | Clear email | Validate format and update |
| Optional phone number | Unchanged | Clear phone number | Normalize and update |
| Quantity | Unchanged | Usually reject | Validate value range |
| Boolean | Unchanged | Explicitly specify whether null is allowed | Update true/false |
| Collection | Unchanged | Specify keep, clear, or reject | Replace or apply add/remove operations |

Distinguish null from empty string `""`, whitespace-only strings, and empty collections. For example, `email = ""` is not automatically equivalent to `email = null`; the API should normalize or reject it according to the contract.

At the database layer, the column must be nullable if business logic allows clearing the value. A `NOT NULL` constraint, `@NotNull`, service validation, or a trigger can cause setting null to fail. Check all relevant constraint layers.

## 6. MapStruct and the Null-Ignore Strategy

MapStruct supports `NullValuePropertyMappingStrategy.IGNORE` for update mappings on an existing target:

```java
@Mapper(componentModel = "spring")
public interface CustomerMapper {

    @BeanMapping(
        nullValuePropertyMappingStrategy =
                NullValuePropertyMappingStrategy.IGNORE
    )
    void updateFrom(
            CustomerUpdateRequest request,
            @MappingTarget Customer customer);
}
```

With this configuration, null properties from the source are ignored and the existing values on the target are preserved. This is useful when the DTO contract defines null as "do not update".

However, the IGNORE strategy removes the ability to use null to clear a field. If the API needs both absent = keep and explicit null = clear, the DTO must preserve presence information separately. You can use `@Condition`, custom mapping methods, or apply fields with presence flags manually before or after mapping.

Do not apply `NullValuePropertyMappingStrategy.IGNORE` globally if different fields have different null rules. An optional field may need to be cleared, whereas a required field must reject null.

## 7. JSON Merge Patch and API Contracts

If the API uses `Content-Type: application/merge-patch+json`, JSON Merge Patch (RFC 7396) defines:

- Member absent from the patch: keep unchanged.
- Member with value null: remove the corresponding member.
- Member with an object value: apply merge recursively.
- Member with an array value: replace the entire array rather than merging individual elements.

Example:

```json
{
  "email": null,
  "displayName": "Lan Nguyen"
}
```

Under JSON Merge Patch, `email` is cleared and `displayName` is updated. The application must still validate domain rules and database nullability.

Not every `PATCH` endpoint automatically uses JSON Merge Patch. When using `application/json` with custom DTOs, define and document the meaning of absent, null, empty arrays, and default values yourself. Do not claim RFC 7396 compliance if actual handling differs.

## 8. Partial Updates via JPQL or SQL

For high volumes, bulk updates can be considered to avoid loading each entity. However, bulk DML bypasses entity lifecycle callbacks and does not synchronize entities already in the persistence context.

A query updating a single field can be straightforward:

```java
@Modifying
@Query("""
    update Customer c
    set c.email = :email
    where c.id = :id
    """)
int updateEmail(
        @Param("id") Long id,
        @Param("email") String email);
```

This method sets email to the passed value, including null if mapping and database allow it. It does not represent the absent state. Invoke this query only when the request actually includes the email field.

If you need to update multiple fields with presence flags, you can use `CASE WHEN :fieldProvided THEN :fieldValue ELSE c.field END`, or define separate queries for specific updatable field sets. Test null parameter type inference with your specific provider and database.

Do not use `COALESCE(:email, c.email)` if explicit null must clear the email. `COALESCE` returns the first non-null value, so when the parameter is null it keeps the existing column value and cannot distinguish "clear" from "not sent".

Bulk updates must run inside a transaction. Consider `flushAutomatically` and `clearAutomatically` on `@Modifying` to keep the persistence context synchronized when entities are already loaded. If the entity uses `@Version`, bulk updates do not perform automatic version checking like regular entity updates; you must design an appropriate version and audit strategy.

## 9. @DynamicUpdate Does Not Replace PATCH Design

Hibernate provides `@DynamicUpdate` to generate UPDATE statements containing only columns determined to have changed:

```java
@Entity
@DynamicUpdate
public class Customer {
    // fields, mapping and accessors
}
```

This can reduce the number of columns written when an entity is updated. However:

- `@DynamicUpdate` does not distinguish absent from explicit null.
- If the mapping assigns null to the entity, null is still a change and can be written to the database.
- It does not fix the bug of building a detached entity from an incomplete DTO and merging it.
- It does not replace optimistic locking when multiple requests update concurrently.
- It can cause Hibernate to generate more distinct SQL UPDATE shapes depending on which fields changed.

Use DTO presence tracking and deliberate entity mutations to guarantee semantics. Treat `@DynamicUpdate` as an SQL generation and performance option, not as a solution for the partial update contract.

## 10. Avoiding Overwrites from Concurrent Updates

Even when each request modifies only part of a resource, two concurrent requests can still read the same stale state and write conflicting updates. To detect stale writes, use optimistic locking with `@Version`:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private String email;

    @Version
    private Long version;
}
```

When the entity is updated, JPA uses the current version in the UPDATE condition and increments the version. If another transaction has already updated the entity, the subsequent update no longer matches the version and raises an optimistic locking failure on flush/commit.

Clients can send back the version read earlier or use HTTP ETag/If-Match to indicate the patch applies only to the resource version the client observed. If the version is stale, the API can return `409 Conflict` or `412 Precondition Failed` depending on the contract.

Do not blindly retry every optimistic lock exception. Reload and reapply the patch only if the operation can be safely reinterpreted on the new state. If two users edit the same field, define clear data precedence or ask the client to resolve the conflict.

## 11. Protecting Allowed Updatable Fields

Do not bind requests directly onto JPA entities. Clients should not gain permission to change internal fields simply because setters exist or fields appear in JSON.

Fields that typically need protection:

- Primary keys and sensitive foreign keys.
- `createdBy`, `createdDate`, `lastModifiedBy`, `lastModifiedDate`.
- `version`.
- Roles, permissions, approval status, or payment status.
- Fields linking the entity to a tenant or owner.

Use dedicated DTOs per use case and apply only allow-listed fields. Check object access permissions before updating; knowing an ID does not imply permission to modify the record. For relationships, load the related entity and verify permissions/tenant rather than assigning a client-supplied ID onto a new object.

## 12. Testing Partial Updates

Test all three states for every important field:

1. **Absent:** send a request without the field and verify the database value remains unchanged.
2. **Explicit null:** send the field as null and verify it is cleared or rejected by validation per contract.
3. **Value:** send a new value and verify the data is updated.

Also test:

- Required fields, empty strings, and whitespace-only strings.
- Boolean `false` and numeric `0` to ensure they are not treated as absent.
- Empty collections, null collections, and absent collections.
- MapStruct mappings with null and presence flags.
- Transaction rollback when validation or update fails.
- Two concurrent transactions updating the same entity with `@Version`.
- Bulk updates and persistence context state after the query.
- Clients sending extra unauthorized fields like role or audit metadata.

Re-read the data from a new transaction or fresh persistence context in integration tests to confirm values were actually persisted.

## 13. Safe Implementation Workflow

1. Determine whether the endpoint is a full-replacement PUT or a partial-update PATCH.
2. Define absent, null, empty string, and empty collection semantics clearly for each field.
3. Use a dedicated request DTO; do not accept JPA entities directly.
4. Preserve per-field presence using setters, a three-state wrapper, or the chosen patch format.
5. Load the entity inside a service transaction and verify permissions and current state.
6. Call setters only for submitted fields; validate explicit nulls according to business rules.
7. Use `@Version` or ETag/If-Match when concurrent updates must be detected.
8. Use bulk DML only for clear performance reasons and handle auditing, versioning, and the persistence context explicitly.
9. Test absent/null/value and re-read from the database.

## Conclusion

Safe partial updates require distinguishing an omitted field, a field sent as null, and a field with a value. Avoid constructing an incomplete entity and calling `save()`, because `merge()` can copy null values onto the managed entity. The most controllable approach is to load the entity inside a transaction, use a DTO with presence tracking, and mutate only allowed fields. Combine validation, `@Version`, allow-listing, and tests covering all three states to prevent unintended data loss.