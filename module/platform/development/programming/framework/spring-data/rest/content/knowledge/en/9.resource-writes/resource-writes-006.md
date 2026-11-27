# Partial Updates with JSON Using Supported Media Types

Spring Data REST provides HTTP **PATCH** on item resources to partially update entity state. The client sends the data or operations to change in the request body; the server loads the current entity, applies the update, and then invokes the repository's **save(…)** method.

What determines how the server interprets the JSON is the **Content-Type** header. A plain JSON object, JSON Merge Patch, and JSON Patch have different structures and rules. Choosing the right media type keeps client and server aligned on the meaning of omitted fields, null-valued fields, array operations, and replace/remove operations.

## Objectives

After this lesson, you will be able to:

- Distinguish PUT and PATCH on an item resource.
- Send partial updates using application/json or application/hal+json.
- Distinguish JSON Merge Patch (application/merge-patch+json) from JSON Patch (application/json-patch+json).
- Choose the right Content-Type while using Accept to control the returned representation.
- Check the conditions for PATCH to be exposed, common errors, and security risks related to JSON Patch.

## 1. PATCH for partially updating an item resource

Suppose the people repository manages the entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phoneNumber;
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST exposes the item resource in the form:

~~~text
/people/{id}
~~~

For an existing item, the methods have different meanings:

| HTTP method | Meaning | Data sent by client |
| --- | --- | --- |
| PUT | Replace the resource state with the sent representation | Full representation per the update contract |
| PATCH | Partially update the resource state | Fields or operations to change |
| GET | Read the current state | No request body for normal operations |

For example, the current state:

~~~json
{
  "firstName": "An",
  "lastName": "Tran",
  "email": "an@example.com",
  "phoneNumber": "0900000000"
}
~~~

If you only want to change lastName, PATCH lets you send the change without resending firstName, email, and phoneNumber.

Spring Data REST handles item resource PATCH through the save(…) method if the repository exports that method. Therefore, the repository must be able to save entities and must not disable exporting save(…).

## 2. Content-Type and Accept serve different roles

Two headers commonly appear in requests:

- **Content-Type** tells the server the format and semantics of the request body.
- **Accept** tells the server which media type the client wants for the response.

Example:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json

{
  "lastName": "Nguyen"
}
~~~

Here, the server interprets the body as JSON Merge Patch; the client requests the response in HAL JSON format.

Do not change Accept to fix an error where the server cannot read the request body. When encountering 415 Unsupported Media Type, check Content-Type first, the media types actually supported by the endpoint, and the Spring Data REST version running.

## 3. PATCH media types documented as supported by Spring Data REST

The Spring Data REST 5.1.0 Repository resources documentation lists the media types for item resource PATCH:

| Media type | Usage |
| --- | --- |
| application/json | Send a JSON object containing the fields to update using Spring Data REST's partial binding mechanism. |
| application/hal+json | Send JSON following the HAL representation. |
| application/merge-patch+json | Send a JSON Merge Patch document per RFC 7396. |
| application/patch+json | Listed in the Supported Media Types table of the Spring Data REST documentation; verify runtime behavior of your version before choosing. |
| application/json-patch+json | Standard media type for JSON Patch per RFC 6902; Spring Data REST's Spring Security Advisory also identifies JSON Patch requests by this media type. |

There is a difference in how the media type name is written between the Supported Media Types table in the Repository resources documentation (application/patch+json) and the RFC 6902 specification/Spring Security Advisory (application/json-patch+json). When using JSON Patch, prefer the standard media type application/json-patch+json and test on the exact library version you are running. You can inspect the constant RestMediaTypes.JSON_PATCH_JSON in your dependencies to confirm the value recognized at runtime.

The media types above cannot be substituted for one another arbitrarily. For example, a body that is an array of op/path/value operations must be sent as JSON Patch; a body that is an object describing part of the new state uses JSON or Merge Patch as appropriate.

## 4. Partial updates with application/json

This is the simplest approach when you only need to send the fields you want to change:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "lastName": "Nguyen",
  "phoneNumber": "0911111111"
}
~~~

Properties not present in the request body are preserved under Spring Data REST's partial update mechanism. This mechanism uses DomainObjectReader to apply an ObjectNode onto the current domain object and can merge nested objects.

For example, if you only send:

~~~json
{
  "lastName": "Nguyen"
}
~~~

then the goal is to change lastName; other fields are not resent.

Distinguish this partial binding mechanism from JSON Merge Patch under RFC 7396:

- application/json sends a partial object using Spring Data REST's mechanism.
- Do not assume on your own that null, arrays, or nested objects will follow full RFC 7396 semantics.
- If you need an explicit contract for the meaning of null and how objects are merged, choose application/merge-patch+json.

DomainObjectReader is the Spring Data REST component that applies a JSON object onto an existing entity. Its API documentation describes it as performing recursive merging on nested objects within the limits of the binding process.

## 5. JSON Merge Patch — application/merge-patch+json

JSON Merge Patch is defined in RFC 7396. The body looks similar in shape to the resource's JSON representation and contains only the members to change.

Example current state:

~~~json
{
  "firstName": "An",
  "lastName": "Tran",
  "email": "an@example.com",
  "address": {
    "city": "Ho Chi Minh City",
    "district": "District 1"
  }
}
~~~

The client only wants to change the last name and city:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json

{
  "lastName": "Nguyen",
  "address": {
    "city": "Da Nang"
  }
}
~~~

Semantics under RFC 7396:

- Members not appearing in the patch are kept as is.
- New members are added.
- Existing members are replaced with the value in the patch.
- Nested objects are merged recursively.
- A member with value null indicates a request to remove that member from the target.
- If a patch value is an array, the target array is replaced with the entire new array; Merge Patch has no operation to edit a single array element.

Example clearing the email value using Merge Patch semantics:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json

{
  "email": null
}
~~~

During binding onto an entity, removing a property may correspond to setting that property to null. The final result also depends on the Java type, validation, database constraints, and business rules. If the field does not allow null, the operation may fail during validation or persistence.

**Important note:** Merge Patch uses null as a removal signal. Therefore, this format is not suitable if the API needs to clearly distinguish between "set the actual value to null" and "remove the member from the document".

### Updating nested objects

With the body:

~~~json
{
  "address": {
    "city": "Da Nang"
  }
}
~~~

Merge Patch means keeping the other members of address under recursive merge rules; district is not deleted simply because it does not appear in the patch.

If you want to replace an entire object or collection, express the full replacement structure explicitly and test against the actual entity.

## 6. JSON Patch — application/json-patch+json

JSON Patch is defined in RFC 6902. Instead of sending a partial state object, the client sends an **array of operations**. Each operation specifies the action and the target location.

Standard operations:

| op | Meaning |
| --- | --- |
| add | Add a member or element |
| remove | Remove a member or element |
| replace | Replace the value at an existing location |
| move | Move a value from a source location to a target location |
| copy | Copy a value from a source location to a target location |
| test | Verify whether the current value matches a condition |

Each operation typically uses the fields:

- op: operation name.
- path: JSON Pointer pointing to the location to operate on.
- value: new value for add, replace, or test.
- from: source path for move and copy.

Example changing lastName:

~~~http
PATCH /people/1 HTTP/1.1
Content-Type: application/json-patch+json
Accept: application/hal+json

[
  {
    "op": "replace",
    "path": "/lastName",
    "value": "Nguyen"
  }
]
~~~

Example appending an element to the end of the tags array:

~~~json
[
  {
    "op": "add",
    "path": "/tags/-",
    "value": "priority"
  }
]
~~~

In JSON Pointer:

- /lastName points to the lastName property at the current level.
- /address/city points to the city property inside address.
- For arrays, use an index such as /tags/0; `-` denotes the end of the array when appending an element.
- Characters `~` and `/` in member names must be escaped per JSON Pointer: `~0` represents `~`, `~1` represents `/`.

Operations are applied in the order they appear in the array. If an earlier operation changes the structure, subsequent operations are evaluated against the updated state.

Example combining test and replace:

~~~json
[
  {
    "op": "test",
    "path": "/status",
    "value": "DRAFT"
  },
  {
    "op": "replace",
    "path": "/status",
    "value": "PUBLISHED"
  }
]
~~~

If the test condition does not hold, the patch is not considered successful. This is a way to place a condition on the current state before applying subsequent operations.

## 7. Comparing JSON Patch and JSON Merge Patch

| Criterion | JSON Merge Patch | JSON Patch |
| --- | --- | --- |
| Standard media type | application/merge-patch+json | application/json-patch+json |
| Body structure | JSON object shaped similarly to the resource | Array of operation objects |
| Changing a field | Send field name and new value | Use add, remove, replace with JSON Pointer |
| Deleting a field | Send value null | Use remove |
| Changing an array | Usually replaces the entire array | Can operate by index or end position |
| Pre-edit condition | No dedicated test operation | Has test |
| Operation ordering | Structural merge semantics | Order of operations in the array matters |
| Suitable scenario | Updating a few simple fields/objects | Precise operations on paths, arrays, or conditional checks |

Example with the same goal of changing lastName:

**Merge Patch**

~~~json
{
  "lastName": "Nguyen"
}
~~~

**JSON Patch**

~~~json
[
  {
    "op": "replace",
    "path": "/lastName",
    "value": "Nguyen"
  }
]
~~~

When changing only a few simple fields, Merge Patch is usually easier to read. When you need to explicitly specify each operation, manipulate array elements, or check state before updating, JSON Patch is more expressive.

## 8. PUT and PATCH: avoiding sending incomplete data with PUT

PUT replaces the resource state with the request body. PATCH only applies the partial changes.

Suppose the current entity has firstName, lastName, email:

- Sending PUT with only {"lastName":"Nguyen"} may cause unsent fields to be set to default values or null depending on the binding mechanism.
- Sending PATCH with the same content is understood as wanting to change only lastName.

Therefore, choose PUT when the client owns the full representation and wants to replace it. Choose PATCH when the client only has a set of changes.

Do not use PATCH as a way to bypass validation or business rules. The data after applying the patch must still satisfy the application's validation, domain, and persistence constraints.

## 9. Sending requests with curl

### 9.1. JSON partial object

~~~bash
curl -i -X PATCH -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"lastName":"Nguyen"}' http://localhost:8080/people/1
~~~

### 9.2. JSON Merge Patch

~~~bash
curl -i -X PATCH -H "Content-Type: application/merge-patch+json" -H "Accept: application/hal+json" -d '{"lastName":"Nguyen","address":{"city":"Da Nang"}}' http://localhost:8080/people/1
~~~

### 9.3. JSON Patch

~~~bash
curl -i -X PATCH -H "Content-Type: application/json-patch+json" -H "Accept: application/hal+json" -d '[{"op":"replace","path":"/lastName","value":"Nguyen"}]' http://localhost:8080/people/1
~~~

The examples use default host and paths for illustration. If the application configures a different base path, reverse proxy, or repository path, use the actual URI exposed by the API.

## 10. Conditions for PATCH exposure and responses

According to the Repository resources reference:

- Item resources support PATCH if configuration and the repository permit it.
- Spring Data REST invokes save(…) to persist the entity after applying the patch.
- If the repository lacks a suitable save(…) method or that method is hidden with @RestResource(exported = false), the PATCH endpoint may return 405 Method Not Allowed.
- Response bodies depend on Accept and RepositoryRestConfiguration.setReturnBodyOnUpdate(…).

When response bodies are enabled and the client requests a representation, updates typically return 200 OK with the representation. When no body is returned, a successful update response is typically 204 No Content. Application configuration may alter this behavior.

Errors to distinguish:

| HTTP status | Common situation |
| --- | --- |
| 400 Bad Request | Malformed JSON, invalid JSON Patch operation, unapplicable path, or data fails binding/validation |
| 404 Not Found | Item resource does not exist |
| 405 Method Not Allowed | PATCH/save is not exported or endpoint does not support the method |
| 406 Not Acceptable | Server cannot produce a response matching the media type in Accept |
| 415 Unsupported Media Type | Content-Type is not supported by the endpoint |

Actual error codes may depend on converters, exception handlers, and application configuration. When diagnosing, record the method, URL, Content-Type, Accept, request body, and response body/status.

## 11. Association resources have their own contract

PATCHing an item resource and updating an association resource are two different flows.

For example, an item resource:

~~~text
/people/1
~~~

can accept PATCH with a partial JSON body in a supported media type.

An association resource, for example:

~~~text
/people/1/address
~~~

has a separate HTTP contract. According to the Repository resources reference, PUT and POST on association resources use text/uri-list to link resource URIs; POST applies to collection associations. Do not send a JSON Merge Patch object to an association endpoint and assume it has the same semantics as PATCHing an item resource.

Follow the association links returned by the HAL representation and use the exact methods/media types documented for that resource.

## 12. Testing partial updates

A PATCH test should verify the before state, the request, and the after state.

1. Create or prepare an entity with multiple populated fields.
2. Send PATCH containing only one field to change.
3. Re-read the item resource and confirm the sent field changed.
4. Confirm unsent fields remained unchanged.
5. With Merge Patch, test null fields, nested objects, and arrays separately.
6. With JSON Patch, test each operation, JSON Pointer path, and operation ordering.
7. Send a request with an unsupported Content-Type to confirm the endpoint rejects it properly.
8. Test the case where the repository disables exporting save(…).
9. Test validation and database constraints when a patch sets a field to null or modifies relationships.
10. Re-read the data via the repository or API after the request finishes to confirm the state was persisted.

Example verifying unrelated fields remain intact:

~~~text
Before:
firstName = An
lastName  = Tran
email     = an@example.com

PATCH:
{"lastName":"Nguyen"}

Expected:
firstName = An
lastName  = Nguyen
email     = an@example.com
~~~

Do not check only the HTTP status. A request returning 2xx still needs verification that the right field changed and other fields stayed intact according to the contract.

## 13. Security and Spring Data REST versions

Spring published **CVE-2026-41729**, a SpEL expression injection vulnerability in JSON Patch handling when an entity or embedded type has a persistent Map-typed property. A JSON Patch request can place a map key in a JSON Pointer path; in affected versions, this path can enter a SpEL expression without being safely sanitized.

The Spring Security Advisory lists the affected versions:

- Spring Data REST 5.0.0 through 5.0.5.
- Spring Data REST 4.5.0 through 4.5.11.
- Spring Data REST 4.4.0 through 4.4.14.
- Spring Data REST 4.3.0 through 4.3.16.
- Spring Data REST 3.7.19 and older releases in that branch.

The fixes listed by the advisory:

| Branch | Fixed release |
| --- | --- |
| 5.0.x | 5.0.6 (OSS); 5.0.5.1 (Enterprise Support) |
| 4.5.x | 4.5.12 (OSS); 4.5.11.1 (Enterprise Support) |
| 4.4.x | 4.4.15 (Enterprise Support) |
| 4.3.x | 4.3.17 (Enterprise Support) |
| 3.7.x | 3.7.20 (Enterprise Support) |

When using JSON Patch, inspect your dependency tree to see the actual resolved versions of spring-data-rest-webmvc and Spring Data REST modules. Prefer the latest supported patched release for your application branch. Do not rely solely on the declared Spring Boot version if dependency management or overrides alter the final Spring Data REST version.

In addition to upgrading:

- Expose PATCH only to users authorized to modify the resource.
- Control modifiable fields through validation and business logic.
- Do not trust paths, values, or URIs sent by clients.
- Test patches on Map properties, nested objects, and associations if your domain model contains these structures.
- Do not use PATCH to permit arbitrary updates to internal fields such as moderation status, owner, or access permissions.

## 14. Quick checklist

- [ ] Identified whether the request updates an item resource or an association resource.
- [ ] Chosen PUT or PATCH properly according to replacement vs. partial update semantics.
- [ ] Content-Type matches the body format.
- [ ] Accept matches the desired response representation.
- [ ] With Merge Patch, understood that null removes and arrays are replaced completely.
- [ ] With JSON Patch, body is an array of operations and paths use valid JSON Pointers.
- [ ] Verified save(…) is exported.
- [ ] Verified response status/body matches the return-body configuration.
- [ ] Tested that unsent fields remain intact.
- [ ] Checked validation, authorization, and a patched Spring Data REST version.

## 15. Key points to remember

PATCH is a partial update operation on an item resource. The server interprets the request body according to Content-Type:

- application/json: partial object using Spring Data REST's binding mechanism.
- application/merge-patch+json: patch object per RFC 7396, where null denotes removing a member.
- application/json-patch+json: array of operations per RFC 6902, using op, path, value, and optionally from.
- application/hal+json: HAL representation listed by Spring Data REST among the supported media types for PATCH.

Use Accept to choose the response format. Check the actual version and the JSON Patch media type recognized at runtime, because current documentation has a discrepancy between application/patch+json and application/json-patch+json.

## References

- Spring Data REST Reference — Repository resources, Item Resource / PATCH: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST API — DomainObjectReader: https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/json/DomainObjectReader.html
- Spring Data REST API — RestMediaTypes: https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RestMediaTypes.html
- RFC 7396 — JSON Merge Patch: https://www.rfc-editor.org/rfc/rfc7396.html
- RFC 6902 — JavaScript Object Notation (JSON) Patch: https://www.rfc-editor.org/rfc/rfc6902.html
- Spring Security Advisory — CVE-2026-41729: https://spring.io/security/cve-2026-41729/