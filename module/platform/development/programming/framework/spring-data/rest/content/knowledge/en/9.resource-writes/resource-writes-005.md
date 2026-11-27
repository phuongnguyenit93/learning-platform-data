# Partial Updates with PATCH and Distinguishing Them from PUT in Spring Data REST

In Spring Data REST, clients can modify resources using HTTP methods such as PUT and PATCH. Both methods can update an item resource, but they express different intents:

- **PUT** sends a representation used to replace the state of the resource at the target URI.
- **PATCH** sends the changes to apply to the current resource, typically including only the properties to be updated.

Choosing the right method helps clients avoid accidentally overwriting data they did not intend to change. It is also an important part of the API contract when multiple clients update the same kind of resource concurrently.

## 1. Resource update endpoints in Spring Data REST

Suppose the application has a repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST can expose a collection resource at `/people` and item resources by ID, for example:

~~~http
GET /people/42
~~~

To update an item resource, the client sends a request to the URI of that resource itself:

~~~http
PUT /people/42
PATCH /people/42
~~~

These operations are mapped by Spring Data REST to the repository and the domain object's binding mechanism. The actual URI depends on the application's path, base path, export configuration, and repository.

The examples below assume an item resource representing a person with the properties `firstName`, `lastName`, `email`, and `active`.

## 2. PUT: sending a representation to replace the resource

PUT expresses the intent to set the state of the resource at the target URI according to the representation sent by the client. With Spring Data REST, clients should send all properties needed in the updated representation.

Example:

~~~http
PUT /people/42
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an.nguyen@example.com",
  "active": true
}
~~~

The client is sending the representation of the person with ID 42. This is appropriate when the client has the complete data and wants to replace the resource state according to the request content.

If the client only sends:

~~~http
PUT /people/42
Content-Type: application/json

{
  "email": "an.new@example.com"
}
~~~

then the request still carries PUT semantics. Clients should not assume that omitted properties are guaranteed to be preserved. Because PUT is a representation replacement operation, unsent fields may revert to default values or null depending on how Spring Data REST binds data into the domain object, constructors, setters, and application logic.

Therefore, if you want to keep the other fields, the client should send the full representation or choose PATCH to explicitly express a partial update intent.

PUT is idempotent under HTTP semantics: sending the same request multiple times should leave the resource in the same target state as sending it once, provided the request and related state do not change. This does not mean every custom business side effect automatically runs exactly once; the application must design events and business logic appropriately.

## 3. PATCH: sending only the properties to change

PATCH expresses the intent to apply a partial change to the current resource. With Spring Data REST, a common usage is sending a JSON object containing only the properties to update.

For example, the client only wants to change the email:

~~~http
PATCH /people/42
Content-Type: application/json
Accept: application/hal+json

{
  "email": "an.new@example.com"
}
~~~

In this case, `firstName`, `lastName`, and `active` do not appear in the request, so they are not part of the changes requested by the client. This is the right choice when the client only knows or only wants to edit a few fields.

Another example, updating the first name and status:

~~~http
PATCH /people/42
Content-Type: application/json

{
  "firstName": "Anh",
  "active": false
}
~~~

The client does not need to resend the old email and last name if it does not intend to change them.

PATCH is not guaranteed by HTTP to be idempotent in all cases. However, an assignment-style request such as `{"active": false}` can usually be resent while still leaving the resource in the same state. Operations such as incrementing a counter or appending an element can behave differently depending on the server implementation.

## 4. Comparing PUT and PATCH

| Criterion | PUT | PATCH |
|---|---|---|
| Intent | Replace the state of the resource at the target URI | Apply changes to the current resource |
| Request content | Usually sends the full representation | Usually sends only the fields to change |
| Omitted fields | Should not be assumed to be preserved | Usually not part of the update |
| HTTP idempotency | Yes | Not generally guaranteed |
| Suitable scenario | Client has the entire state to write | Client only needs a partial edit |
| Common risk | Overwriting data not included in the request | Misunderstanding how null, nested objects, or associations are handled |

Both requests can return success, but they cannot be treated as equivalent ways of writing the same thing. The meaning of a request depends on the HTTP method and how the server implements the update.

## 5. Distinguishing omitted properties from null properties

This requires special attention when sending PATCH.

Suppose the current resource has:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an.nguyen@example.com",
  "phone": "0900000000"
}
~~~

If the client sends:

~~~json
{
  "email": "an.new@example.com"
}
~~~

then the client is only requesting to change the email. Fields that do not appear, such as `firstName`, `lastName`, and `phone`, are not requested to change.

If the client sends:

~~~json
{
  "phone": null
}
~~~

then this is an explicitly sent value. With a nullable property and the corresponding binding mechanism, it may request clearing the current phone value.

Distinguish between:

- **Key absent:** the client did not send that property.
- **Key present with value null:** the client sent that property and set its value to null.
- **Key present with a concrete value:** the client requested setting a new value.

Whether a property can be cleared also depends on the Java type, validation, constructor/setter, business rules, and how Spring Data REST binds the request. If the field does not allow null or has required validation, the request may be rejected.

Do not assume all nested object structures or collections are deep-merged by the exact same rules. For nested objects, lists, and associations, verify the behavior of your Spring Data REST version and actual model, and write integration tests for the cases you need to support.

## 6. PATCH is not synonymous with every JSON Patch format

PATCH is an HTTP method; the method name itself does not dictate a single body format. There are multiple ways to represent a partial change, such as JSON Patch under RFC 6902 or JSON Merge Patch under RFC 7396.

Example JSON Patch using an array of operations:

~~~json
[
  {
    "op": "replace",
    "path": "/email",
    "value": "an.new@example.com"
  }
]
~~~

JSON Merge Patch can use a JSON object to represent the values to merge:

~~~json
{
  "email": "an.new@example.com",
  "phone": null
}
~~~

Spring Data REST's common PATCH usage takes a partial JSON representation with `Content-Type: application/json`. Do not automatically assume a repository endpoint accepts every media type or every JSON Patch/Merge Patch syntax just because the HTTP method is PATCH.

If the application wants to support RFC 6902 or RFC 7396, verify whether the actual endpoint and configuration support that media type; if using a custom controller, the implementation must handle the corresponding format properly.

## 7. Updating associations and collections

Domain objects may contain associations such as an address, orders, or member groups. Spring Data REST usually exposes associations as discoverable links.

Example item resource:

~~~json
{
  "firstName": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~

When you want to modify an association, inspect the relation and association endpoint exposed by the server. An association endpoint can accept the URI of the related resource according to Spring Data REST's contract.

Illustrative example of updating an address link:

~~~http
PUT /people/42/address
Content-Type: text/uri-list

http://localhost:8080/addresses/7
~~~

This request illustrates assigning an association via the URI of the related resource. It is different from PATCHing scalar properties on `/people/42`.

For collection associations, distinguish between replacing the list of links and partially updating it. Do not send a shortened array with PUT if the goal is only to add an element without replacing existing relationships. Rely on the association endpoints, media types, and semantics exposed by the API; test adding, replacing, and unlinking cases separately.

## 8. Validation, authorization, and business logic

Using PATCH does not mean requests skip validation. Domain constraints and application validation can still be enforced when Spring Data REST binds and saves the entity.

Things to check:

- Whether the property is allowed to be updated via REST.
- Whether the new value is valid and satisfies domain constraints.
- Whether the client has permission to perform the update operation.
- Whether updating one field affects business invariants or related state.
- Whether the assigned association is within the scope the user is allowed to access.

For example, a client may send a PATCH changing only `email`, yet the application still needs to validate the email format, check permissions, and ensure the email is not duplicated if the domain requires uniqueness.

If business logic needs to coordinate multiple fields, place that logic in the service/domain layer or an appropriate application mechanism. Do not rely on whether the client sends all fields or a single field to protect data invariants.

## 9. Concurrent updates and avoiding overwriting data

When multiple clients read and then update the same resource, a later request can overwrite the changes of an earlier request. PATCH reduces the amount of data sent, but by itself does not resolve all concurrency conflicts.

If the application uses optimistic locking, the entity may have a version field, for example:

~~~java
@Version
private Long version;
~~~

When Spring Data REST and the application configuration provide ETags/conditional requests, clients can read the ETag and send an `If-Match` condition when updating. The server can reject the request if the representation has changed since the previous read, typically with a precondition failed response.

Illustrative conditional request example:

~~~http
PATCH /people/42
If-Match: "version-etag"
Content-Type: application/json

{
  "email": "an.new@example.com"
}
~~~

The ETag name above is illustrative only. Clients must use the exact ETag value received from the server response and rely on this mechanism only when the application actually enables, configures, and tests optimistic locking.

## 10. Testing PUT and PATCH

Test both the state before and after the request rather than checking only the status code.

Example for PATCH:

1. Create or prepare a person with firstName, lastName, email, and phone.
2. Send PATCH containing only the new email.
3. Re-read the item resource.
4. Confirm email changed and unsent properties retained their old values.
5. Send PATCH with a nullable field set to null and confirm clearing behavior matches the contract.
6. Test validation when sending invalid values.

Example for PUT:

1. Prepare the full representation of the resource.
2. Send PUT with all fields the client intends to preserve.
3. Re-read the resource and confirm the state matches the expected representation.
4. Test omitting a property to understand clearly how the binder and domain model handle missing fields.
5. Verify associations, validation, and update permissions.

In addition, test wrong media types, nonexistent resources, invalid IDs, unauthorized updates, and version conflicts if optimistic locking is enabled.

## 11. How to choose a method in an application

Use PUT when the client has the full representation and wants to replace the resource state with that content. Use PATCH when the client only wants to change a subset of properties and the server supports the corresponding partial update mechanism.

Examples:

- An admin screen that loads full user details, allows editing the entire form, and submits the entire representation back: PUT may be appropriate.
- A screen that only allows changing email or toggling a status: PATCH is usually more suitable.
- An operation that changes an association: use the association endpoint and semantics exposed by the API instead of guessing how to PATCH a nested field.
- An update that needs to avoid overwriting another client's data: combine with optimistic locking/conditional requests if supported by the application.

## 12. Key takeaways

- PUT expresses the intent to replace the resource state at the target URI; clients typically send the full representation.
- PATCH expresses the intent to apply a partial change; clients send only the properties to update.
- With PATCH, an omitted key is different from a key with value null.
- PUT and PATCH have different HTTP semantics; do not choose a method solely based on whether the JSON body is short or long.
- PATCH in Spring Data REST commonly uses a partial JSON object with `Content-Type: application/json`; do not assume it is RFC 6902 JSON Patch or RFC 7396 JSON Merge Patch by default.
- Associations and collections have their own endpoints, media types, and rules; inspect exposed links and test replace/add/unlink behavior.
- Validation, authorization, domain logic, and concurrency conflict handling still need to be enforced on updates.