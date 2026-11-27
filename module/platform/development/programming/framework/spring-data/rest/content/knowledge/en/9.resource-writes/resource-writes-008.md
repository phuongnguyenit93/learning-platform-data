# JSON Merge Patch with application/merge-patch+json

## 1. What is JSON Merge Patch?

JSON Merge Patch is a format for describing partial changes to a JSON document. The client sends a JSON document containing the properties to add, replace, or remove; the server applies that document onto the current state of the resource.

This format is standardized in **RFC 7396** and is typically used with the HTTP **PATCH** method. The standard media type is:

~~~~http
application/merge-patch+json
~~~~

Spring Data REST supports this media type for item resources. The client sends the patch document to an item's URI, for example:

~~~~http
PATCH /people/42
Content-Type: application/merge-patch+json
Accept: application/hal+json
~~~~

A Merge Patch body is not a full copy of the entity. It is a description of changes structured as JSON. Properties that do not appear in the patch are preserved; properties that are present are processed according to RFC 7396 rules.

## 2. Distinguishing PUT, PATCH, JSON Merge Patch, and JSON Patch

| Mechanism | Meaning |
|---|---|
| PUT | Sends a new representation to replace the resource state at the target URI |
| PATCH | Sends a patch document for the server to apply changes to the resource |
| JSON Merge Patch | JSON-object-based patch format; null in an object indicates removing a member |
| JSON Patch | Operation-list patch format such as add, remove, replace, move, copy, and test by path |

In Spring Data REST, PUT replaces the item's state with the request body, whereas PATCH partially updates the state. PATCH does not by itself define a single body format; the request's media type tells the server which patch format the client is using.

JSON Merge Patch fits well when the resource is mainly a JSON object and updates typically involve changing field values, adding fields, or removing fields. When you need precise operations on array elements, moving values, testing conditions at a path, or explicitly expressing add/remove/replace operations, RFC 6902 JSON Patch may be a better fit.

Do not send an arbitrary JSON object and assume the server treats it as Merge Patch. Declare the explicit Content-Type: application/merge-patch+json.

## 3. RFC 7396 processing rules

There are four rules to remember.

### Properties absent from the patch are preserved

Suppose the current resource is:

~~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "email": "frodo@example.com",
  "active": true
}
~~~~

The client sends:

~~~~json
{
  "firstName": "Sam"
}
~~~~

Result:

~~~~json
{
  "firstName": "Sam",
  "lastName": "Baggins",
  "email": "frodo@example.com",
  "active": true
}
~~~~

Only firstName changes. Fields not mentioned in the patch are not deleted or reset merely because the client did not send them.

### Non-null values replace or add properties

If the field already exists, the new value replaces the old value. If the field does not exist yet, it is added:

~~~~json
{
  "nickname": "Ring-bearer",
  "active": false
}
~~~~

The patch above adds nickname and changes active to false. Values such as false, 0, and empty strings are normal values; they do not mean skipping the field.

### A null value in an object means removing the member

Suppose the resource has:

~~~~json
{
  "firstName": "Frodo",
  "email": "frodo@example.com",
  "phone": "+84-123-456"
}
~~~~

The client sends:

~~~~json
{
  "phone": null
}
~~~~

Result per RFC 7396:

~~~~json
{
  "firstName": "Frodo",
  "email": "frodo@example.com"
}
~~~~

phone is removed from the JSON document. This is a common point of confusion: in JSON Merge Patch, null does not mean "keep the field and set its value to null"; it is an instruction to remove that member.

Therefore, Merge Patch cannot directly express the intent "set a property inside an object to JSON null" in the same way as a regular value. If the domain needs to clearly distinguish an omitted field, a removed field, and a field set to null, consider JSON Patch or a request DTO with its own presence/null convention.

### Nested objects are merged recursively

Patching a child object does not replace the entire child object. Members are merged recursively under the same rules:

~~~~json
{
  "firstName": "Frodo",
  "address": {
    "city": "Hobbiton",
    "country": "Shire",
    "postalCode": "12345"
  }
}
~~~~

Patch:

~~~~json
{
  "address": {
    "city": "Bree"
  }
}
~~~~

Result:

~~~~json
{
  "firstName": "Frodo",
  "address": {
    "city": "Bree",
    "country": "Shire",
    "postalCode": "12345"
  }
}
~~~~

Only address.city changes. country and postalCode are preserved.

## 4. Arrays are a special case

Under RFC 7396, an array is treated as a complete value. When a patch contains an array, the target array is replaced by the new array; elements are not merged by index.

Current resource:

~~~~json
{
  "name": "Travel kit",
  "tags": ["map", "compass", "rope"]
}
~~~~

Patch:

~~~~json
{
  "tags": ["map", "compass"]
}
~~~~

Result:

~~~~json
{
  "name": "Travel kit",
  "tags": ["map", "compass"]
}
~~~~

The element rope is removed because the entire array was replaced. If you want to remove only the element at index 2 while keeping the remaining elements, Merge Patch does not provide syntax for that.

Other limitations:

- null inside an array is a normal null element, not an instruction to remove an element.
- A patch root that is a scalar, array, or null replaces the entire target with that value.
- If the patch root is an object while the current target is not an object, the algorithm starts from an empty object and applies the patch members.
- An empty object {} produces no changes.

Therefore, Merge Patch is particularly suited for object-structured resources. For large collections or per-element operations, design a business endpoint or choose JSON Patch.

## 5. Complete example: updating multiple fields of a person

Suppose GET /people/42 returns:

~~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "email": "frodo@example.com",
  "phone": "+84-123-456",
  "address": {
    "city": "Hobbiton",
    "country": "Shire"
  },
  "tags": ["traveler", "ring-bearer"]
}
~~~~

The client only wants to change the first name, change the city, delete the phone number, and replace the tag list. Patch document:

~~~~json
{
  "firstName": "Sam",
  "address": {
    "city": "Bree"
  },
  "phone": null,
  "tags": ["traveler"]
}
~~~~

Expected result:

~~~~json
{
  "firstName": "Sam",
  "lastName": "Baggins",
  "email": "frodo@example.com",
  "address": {
    "city": "Bree",
    "country": "Shire"
  },
  "tags": ["traveler"]
}
~~~~

You can read the changes as follows:

| Field | Result | Reason |
|---|---|---|
| firstName | Sam | Value replaced |
| lastName | Baggins | Absent from patch, so preserved |
| email | frodo@example.com | Absent from patch, so preserved |
| address.city | Bree | Nested object merged |
| address.country | Shire | Absent from object patch, so preserved |
| phone | Removed | null value in object means removing the member |
| tags | ["traveler"] | Array replaced in full |

## 6. Sending Merge Patch to Spring Data REST

Suppose the repository is exported at /people and the item has ID 42. Sample request:

~~~~bash
curl -i -X PATCH \
  "http://localhost:8080/people/42" \
  -H "Content-Type: application/merge-patch+json" \
  -H "Accept: application/hal+json" \
  -d '{
    "firstName": "Sam",
    "address": {
      "city": "Bree"
    },
    "phone": null,
    "tags": ["traveler"]
  }'
~~~~

The two headers serve different roles:

- Content-Type: application/merge-patch+json tells the server the body follows JSON Merge Patch rules.
- Accept: application/hal+json requests a HAL representation for the response if the server returns a body.

Accept does not replace Content-Type. If the client sends application/json when intending to apply a Merge Patch, behavior depends on how the server interprets that media type; to keep requests explicit and portable, use the exact standard media type.

You can use a bodyless response if the client does not need to receive the representation after updating. With Spring Data REST, the response body and status code of an update operation depend on Accept and RepositoryRestConfiguration.setReturnBodyOnUpdate(…).

## 7. How does Spring Data REST handle PATCH?

Spring Data REST exposes item resources under URIs of the form:

~~~~text
/{repository}/{id}
~~~~

According to the current Repository resources documentation, item resources support GET, PUT, PATCH, and DELETE unless the application intentionally changes method exposure. For PATCH:

- PATCH performs a partial update of the item's state.
- The repository method used to save changes is save(…).
- Media types listed in current documentation include application/hal+json, application/json, application/patch+json, and application/merge-patch+json.
- If save(…) methods do not exist or are hidden with @RestResource(exported = false), PATCH returns 405 Method Not Allowed.

This means the item PATCH endpoint relies on the repository's save capability. You do not need to create a query method named mergePatch in CrudRepository just for Spring Data REST to recognize the media type.

Repository example:

~~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends CrudRepository<Person, Long> {
}
~~~~

Spring Data REST can provide PATCH for the item resource /people/{id}. Body parsing, binding, and entity persistence are handled by the Spring Data REST/Jackson infrastructure of the running version. JSON-level Merge Patch rules remain the basis for understanding document semantics; final binding outcomes should be verified with integration tests against the actual domain model.

If you want to disable PATCH, you can hide the appropriate save method or configure supported HTTP methods. Keep in mind that save(…) also affects POST and PUT, because those operations use save as well. Check individually which methods the API wants to keep.

## 8. Differences between Merge Patch and updating associations

Spring Data REST has separate resources for entity associations. For example, a person has address, roles, or orders links. Association resources have their own HTTP methods and media types; for associations, Spring Data REST typically uses text/uri-list to bind or add related resources.

Therefore, do not assume sending a nested JSON object in Merge Patch has the same semantics as binding an association via URI. Distinguish between:

- Updating simple value fields or embedded objects belonging to the representation.
- Changing relationships between two aggregates/repository resources.
- Adding or removing elements of a collection association.

For associations, follow the links provided by Spring Data REST and use the exact association resource contract. For example, a PUT or POST request with text/uri-list can attach the URI of a related resource to an association. Check the response and relationship state after the operation to make sure the client is modifying the right kind of data.

## 9. Validation, binding, and updatable fields

JSON Merge Patch specifies how to merge JSON documents. It does not determine which fields are allowed to change according to business rules.

When mapping a patch onto a Java entity, keep in mind:

- Fields not appearing in the patch must be preserved.
- Fields with invalid values must be rejected by validation.
- Read-only, computed, audit, or administrative fields should not be opened for client editing.
- IDs, versions, and server-managed properties must be protected from client overwrites.
- Unknown properties may be ignored or cause errors depending on Jackson and binding configuration; check your application's behavior.
- Removing a JSON member may map to null/absent state in a Java object depending on domain types, constructors, setters, and deserialization configuration.

If an entity has many sensitive fields, consider using a DTO/command model for update operations or a custom controller to enforce a field allowlist. Avoid binding arbitrary requests directly onto an entity with many internal properties and relying on the client UI to hide fields.

Example DTO allowing edits to a few properties:

~~~~java
public record PersonPatchInput(
        @Size(max = 80) String firstName,
        @Email String email,
        AddressPatchInput address
) {
}

public record AddressPatchInput(
        @Size(max = 100) String city
) {
}
~~~~

The DTO illustrates a data structure for a custom endpoint. If you need to distinguish an omitted field from a field sent as null, a plain DTO may not suffice because both can map to Java null. In that case, use a presence-tracking wrapper, a JSON tree, or a dedicated patch mechanism.

## 10. Controlling concurrent updates with ETag and If-Match

A patch is typically constructed from a representation the client read earlier. If another client updates the resource before the patch is sent, the stale request may overwrite newer changes or produce an undesirable state.

HTTP PATCH is not idempotent by default. RFC 5789 requires servers to apply the entire patch atomically: if it cannot be applied in full, partial changes must not remain. The RFC also recommends using conditional requests when a patch depends on a known baseline state.

Spring Data REST supports ETag and the If-Match header for PUT, PATCH, and DELETE when the resource has suitable version metadata. For example:

1. Client calls GET /people/42.
2. Server returns header ETag: "7".
3. Client sends PATCH with If-Match: "7".
4. Server performs the update only if the current ETag still matches.
5. If the resource has changed, server returns 412 Precondition Failed.

Example:

~~~~http
PATCH /people/42 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json
If-Match: "7"

{
  "firstName": "Sam"
}
~~~~

With Spring Data JPA, you can use the @Version annotation to mark a version field:

~~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    private String firstName;
}
~~~~

Spring Data REST uses the store's version metadata to generate ETags and check update conditions. Inspect the actual ETag in responses and enable/maintain versioning properly for the store in use.

## 11. Common status codes

| Status | Meaning in a PATCH scenario |
|---|---|
| 200 OK | Update succeeded and server returns representation |
| 204 No Content | Update succeeded with no response body |
| 400 Bad Request | Invalid patch document or request body cannot be parsed/bound |
| 404 Not Found | Item resource does not exist |
| 405 Method Not Allowed | Repository lacks or does not export the required save method |
| 409 Conflict | Change conflicts with current state per application logic |
| 412 Precondition Failed | If-Match header does not match current ETag |
| 415 Unsupported Media Type | Patch Content-Type is not supported by the endpoint |
| 422 Unprocessable Content | Syntactically valid document cannot be applied per business rules (if the application uses this status) |

Actual status codes also depend on configuration, validation, security filters, exception handlers, and Spring Data REST version. Inspect the application's actual responses instead of assuming every binding error returns the same status.

## 12. Testing JSON Merge Patch

An integration test should verify both RFC rules and Spring Data REST's persistence of the entity.

Example using MockMvc:

~~~~java
mockMvc.perform(patch("/people/{id}", 42L)
        .contentType("application/merge-patch+json")
        .accept(MediaType.APPLICATION_HAL_JSON)
        .content("""
            {
              "firstName": "Sam",
              "address": {
                "city": "Bree"
              },
              "phone": null,
              "tags": ["traveler"]
            }
            """))
    .andExpect(status().isOk());
~~~~

The status in the test depends on Spring Data REST's return-body configuration. If configured to return 204 when no body is sent, use isNoContent().

After the request, verify the persisted state via the repository or GET resource:

- firstName changed to Sam.
- address.city changed to Bree.
- address.country kept its old value.
- phone was removed per Merge Patch rules.
- tags was replaced with the new array.

Write separate tests for:

1. Fields absent from the patch are preserved.
2. Fields receiving null are removed from the JSON object.
3. Nested objects are merged recursively.
4. Arrays are replaced completely.
5. false, 0, and empty strings are kept as normal values.
6. Empty patch {} changes no data.
7. Malformed patch or unsupported Content-Type is rejected.
8. Non-updatable fields cannot be overwritten by clients.
9. Stale ETag is rejected when the resource has changed.
10. Failed requests do not leave partial update state behind.

## 13. Choosing between Merge Patch and JSON Patch

| Need | Suitable choice |
|---|---|
| Changing a few fields in an object | JSON Merge Patch |
| Adding or removing object members | JSON Merge Patch |
| Merging nested objects | JSON Merge Patch |
| Replacing an entire array | JSON Merge Patch |
| Editing an array element by index | JSON Patch |
| Moving or copying values between paths | JSON Patch |
| Checking a value before changing via a test operation | JSON Patch |
| Clearly distinguishing omitted field, removed field, and assigning JSON null | JSON Patch or a custom patch contract |

JSON Merge Patch is easy to read because the patch document resembles the target resource. JSON Patch expresses changes more explicitly as an operation list, though the client must know the paths and operation structure.

No single format fits every resource. Choose based on data structure and the operations clients need to perform.

## 14. Conclusion

application/merge-patch+json is the media type for JSON Merge Patch under RFC 7396, commonly sent in the body of an HTTP PATCH. Omitted fields are preserved, new values replace or add fields, null in an object removes the member, nested objects are merged recursively, and arrays are replaced in full.

Spring Data REST currently supports this media type for item PATCH and uses save(…) to persist changes. When implementing, pay attention to domain model binding, association resources, field-level authorization, validation, and concurrency control using ETag/If-Match. For cases requiring fine-grained array manipulation or clearly distinguishing null from absent, choose JSON Patch or a custom update contract.

## References

- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html)
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html)
- [Spring Data REST — Repository resources, item PATCH and supported media types](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Conditional operations with ETag and If-Match](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)