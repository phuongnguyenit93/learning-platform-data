# Replacing Resources with PUT and the Impact on Omitted Properties

In Spring Data REST, **PUT** is used to replace the representation of an existing resource. The client sends a new representation for the resource; therefore, a PUT request must include all writable properties that the client wants to preserve.

A common pitfall that causes data loss is when a property currently has a value in the database but is omitted from the PUT body. When the new representation is bound to the entity, omitted properties may receive null, default values, or an empty state depending on the data type and how the application is configured. If you only want to change a few properties, consider using **PATCH**.

## 1. PUT in Spring Data REST

Spring Data REST automatically exports repositories as REST resources. For a **customers** collection resource, each record can be accessed via an item URL, for example:

~~~http
GET /customers/42
~~~

The client can retrieve the current representation, edit it, and send it back with PUT:

~~~http
PUT /customers/42
Content-Type: application/json
Accept: application/hal+json
~~~

PUT denotes sending a new representation for the resource at that URI. Therefore, the client should send all writable fields that it wants to retain after the update.

For example, the current representation of a customer might include:

~~~json
{
  "name": "Lan",
  "email": "lan@example.com",
  "phone": "0901234567",
  "city": "Da Nang",
  "active": true
}
~~~

If the client wants to change the name while keeping the email, phone number, city, and status, the PUT body should include all of those fields:

~~~http
PUT /customers/42
Content-Type: application/json
Accept: application/hal+json
~~~

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "phone": "0901234567",
  "city": "Da Nang",
  "active": true
}
~~~

After a successful update, the item's representation reflects the newly saved data.

## 2. What happens to omitted properties?

Suppose the current customer has:

| Property | Stored value |
|---|---|
| name | Lan |
| email | lan@example.com |
| phone | 0901234567 |
| city | Da Nang |
| active | true |

The client sends a PUT with only partial data:

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com"
}
~~~

This body describes a new representation but omits **phone**, **city**, and **active**. Omitted fields may be reset when the request is bound and saved:

- Reference fields such as **String**, **Integer**, or **Boolean** may receive **null** if no new value is provided.
- Primitive fields such as **int** or **boolean** may receive Java default values, **0** and **false** respectively.
- Collections or associations may become empty, null, or unlinked depending on entity mapping and relationship handling.
- Constructors, setters, Jackson configuration, custom deserializers, and business logic can affect the final binding result.

Therefore, do not assume that omitted fields will automatically keep their old values in the database. Treat the PUT body as the complete representation the client intends to store and explicitly send the fields to preserve.

### Example of data loss risk

An entity might be declared as follows:

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String email;
    private String phone;
    private String city;
    private boolean active;

    // getters and setters
}
~~~

If a request only sends **name** and **email**, the other properties may be bound to null or default values. When the entity is saved, the previous data for **phone**, **city**, or **active** may be lost or altered.

For the primitive **boolean** type, the default value is **false**. For the wrapper **Boolean**, a missing value can be **null**. This difference matters if the application needs to distinguish a false state from an unprovided state.

## 3. Sending the full representation when using PUT

A safe client workflow is:

1. Send GET to read the current representation.
2. Take the writable fields that need to be preserved.
3. Apply changes to that representation.
4. Send PUT with the complete body to the item's URI.
5. Re-read the resource or inspect the response to confirm the data was saved as expected.

Example:

~~~http
GET /customers/42
Accept: application/hal+json
~~~

After reading the data, the client sends all fields to keep:

~~~http
PUT /customers/42
Content-Type: application/json
Accept: application/hal+json
~~~

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "phone": "0901234567",
  "city": "Da Nang",
  "active": true
}
~~~

If a property needs to be intentionally cleared, express that intent explicitly according to the API contract, such as sending **null** for a nullable field if the endpoint supports it. Do not rely on accidentally omitting a field to express clearing data.

It is not necessary to send fields that are server-managed or not writable. For example, the ID in the URI, audit fields, computed values, version, or properties marked read-only should follow the contract exposed by the API.

## 4. Comparing PUT and PATCH

PUT and PATCH can both be used to update a resource, but the intent of each request differs:

| Criterion | PUT | PATCH |
|---|---|---|
| Meaning | Replace the resource's representation | Partially modify the resource |
| Body | Send all writable fields to preserve | Send only the fields to change in a supported PATCH format |
| Fields absent from body | May be reset according to binding and replacement rules | Typically preserved if not part of the changes |
| When to use | Client has the full representation | Client only changes a few fields |

Example when wanting to change only the customer's name:

**PUT — resend the full representation:**

~~~http
PUT /customers/42
Content-Type: application/json
~~~

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "phone": "0901234567",
  "city": "Da Nang",
  "active": true
}
~~~

**PATCH — send only the change:**

~~~http
PATCH /customers/42
Content-Type: application/merge-patch+json
~~~

~~~json
{
  "name": "Lan Nguyen"
}
~~~

With PATCH, unmentioned properties are usually preserved. How **null**, collections, and associations are interpreted depends on the PATCH format and how Spring Data REST and the application process the request. Check the media types and contract actually supported by the API; do not assume every PATCH style follows the same rules.

## 5. Null values, default values, and validation

When a property is omitted in PUT, the result can affect validation and persistence constraints.

Example entity with validation:

~~~java
@NotNull
private String email;
~~~

If binding sets **email** to null, validation may reject the request. Similarly, a NOT NULL constraint in the database may cause the save operation to fail.

Several points to distinguish:

- **@NotNull** is a validation constraint when Bean Validation is enabled.
- **@Column(nullable = false)** describes mapping and can affect schema; it should not be treated as the sole validation mechanism.
- Primitive types have Java default values, such as **false** or **0**.
- Wrapper and reference types can represent null.
- Default values in a constructor are not guaranteed to be retained if binding assigns a different value.

If a request fails due to validation or persistence constraints, read the response and server-side logs to identify which field is invalid. Do not conclude that data was updated merely because the client sent the request.

## 6. Relationships and collections in representations

An entity may contain relationships to other entities or collections of child elements. When PUT replaces a representation, omitting relationship fields must be considered carefully.

Example of a customer linked to an address:

~~~json
{
  "name": "Lan",
  "address": {
    "street": "Le Loi",
    "city": "Da Nang"
  }
}
~~~

If the PUT body omits **address**, how the link is handled depends on entity mapping and Spring Data REST's binding mechanism. The link may be reset or retained depending on application-specific logic. Do not rely on assuming associations are always preserved.

For associations exported by Spring Data REST as URIs or HAL links, use the exact form exposed by the endpoint. Test assigning, replacing, or removing associations separately; do not treat a nested JSON object and an association link as equivalent representations under every configuration.

For collections such as **orders**, **roles**, or **tags**, check the endpoint contract: whether the request replaces the entire collection, adds elements, or updates a separate association. If only one relationship needs to change, a dedicated association resource operation may be more appropriate than resending the entire item.

## 7. Testing PUT behavior in the application

You can test with a small scenario using known data.

**Step 1 — Create or select a customer with complete data**

Ensure the fields **name**, **email**, **phone**, **city**, and **active** all have values.

**Step 2 — Read the representation before updating**

~~~http
GET /customers/42
Accept: application/hal+json
~~~

Record the values of all writable fields.

**Step 3 — Send PUT intentionally omitting a field**

~~~http
PUT /customers/42
Content-Type: application/json
~~~

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com"
}
~~~

**Step 4 — Re-read the resource**

~~~http
GET /customers/42
Accept: application/hal+json
~~~

Compare **phone**, **city**, and **active** against their pre-request values. The result shows exactly how the current application binds and saves omitted properties.

**Step 5 — Try PATCH for a partial update**

~~~http
PATCH /customers/42
Content-Type: application/merge-patch+json
~~~

~~~json
{
  "name": "Lan Tran"
}
~~~

Re-read the resource to confirm that fields not requested to change remain intact according to the application's PATCH contract.

Do not run field-omission tests on valuable production data. Use test data or a development environment to avoid unintended changes.

## 8. Avoiding overwriting data when multiple clients exist

If two clients read the same resource and then send PUT, the later client's request may overwrite the earlier client's changes.

Example:

1. Client A reads customer when **phone** has the old value.
2. Client B updates **phone** and saves successfully.
3. Client A sends the old representation with PUT just to change **name**.
4. A's PUT may overwrite **phone** back to the old value because the body contains the earlier representation.

To reduce lost updates, the application can use optimistic locking with **@Version** and ETag/conditional requests if configured. Clients should send the validator received from the previous read, such as **If-Match**, according to the endpoint's contract. When the representation has changed, the server can reject the stale request instead of silently overwriting.

## 9. Common errors and how to handle them

| Symptom | Possible cause | Resolution |
|---|---|---|
| Old property becomes null after PUT | Body omitted a reference field to preserve | Send all writable fields in the PUT representation |
| Boolean turns into false | Primitive boolean field omitted during binding | Send the value explicitly or use a wrapper type if business logic needs a null state |
| PUT request rejected by validation | Required field missing or set to null | Check body, validation annotations, and response |
| Association unlinked or altered | Relationship omitted or represented against contract | Check association resources and link format |
| Another client's change overwritten | Client sent a stale representation via PUT | Use ETag/If-Match or optimistic locking when supported by the endpoint |
| Only one field needs changing but many fields must be sent | Using PUT for a partial update | Use PATCH with a supported media type and API contract |

## 10. Selection guidelines

- Use **PUT** when the client has the full representation and wants to replace the resource's state.
- Before PUT, read the current resource or build the complete body from reliable data.
- Explicitly send the fields to preserve; do not rely on omitted fields remaining intact automatically.
- Use **PATCH** when only a partial change is needed and the endpoint supports the required PATCH format.
- Check nullable, primitive, collection, and association fields because they can produce different binding results.
- Use appropriate validation and optimistic locking to prevent invalid data or lost updates.

Understanding the difference between PUT and PATCH helps clients send the right update intent, avoid accidentally clearing data, and keep the REST contract consistent.