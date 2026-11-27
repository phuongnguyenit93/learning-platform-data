# Re-synchronizing Data When Multiple Clients Edit Concurrently

## Objectives

When multiple clients concurrently read and edit a Spring Data REST resource, each client may be holding a copy of stale data. If the server accepts two writes without detecting the stale copy, the later write can overwrite the earlier write's changes. This phenomenon is commonly called a **lost update**.

Spring Data REST can combine ETag with optimistic locking to detect that situation:

- Clients read the resource and store the current ETag.
- When writing, the client sends the read ETag in the `If-Match` header.
- The server accepts the write only if the resource is still at the corresponding version.
- If another client updated earlier, the server rejects the write based on the stale copy; the client must reload, resolve the conflict, and then submit subsequent changes.

This mechanism lets multiple clients synchronize changes without locking the resource for the entire time a user keeps an edit screen open.

## 1. The Problem When Multiple Clients Edit Concurrently

Suppose Person has the data:

~~~json
{
  "id": 42,
  "firstName": "An",
  "lastName": "Nguyen",
  "city": "Hanoi"
}
~~~

Client A and Client B both GET Person 42. Both receive the data snapshot at time T1.

- A changes `city` to `Da Nang`.
- B changes `lastName` to `Tran`.
- A sends an update and the server saves it successfully.
- B still holds the old copy; if B sends the entire old representation along with its own change, A's new `city` value may be overwritten back to `Hanoi`.

This is a lost update: A's operation succeeded, yet that change was lost after B's write.

If the server does not check versions, both requests may return success. Clients find it hard to notice that data was overwritten unless they re-read.

## 2. Optimistic Locking and @Version

Optimistic locking assumes conflicts do not happen often. Clients are allowed to read and work on their own copies; on write, the server checks whether that copy is still fresh.

With Spring Data JPA, you can declare a version field on the entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Person {

    @Id
    private Long id;

    private String firstName;
    private String lastName;
    private String city;

    @Version
    private Long version;

    // getters and setters
}
~~~

`@Version` marks the property used by the persistence provider to detect concurrent updates.

When an entity is saved:

1. The persistence provider reads the current version.
2. On UPDATE, the write statement checks the old version in the update condition.
3. If no other transaction has modified the entity, the update succeeds and the version is incremented.
4. If the version has changed, the update fails to match the expected record/version and optimistic locking detects a conflict.

The exact implementation depends on the persistence provider and datastore. With JPA, the `@Version` field is normally managed by the provider; do not let clients pick the new version themselves.

### How are @Version and ETag related?

Spring Data REST can use the entity's version to generate an ETag for the representation. The ETag is the validator the client receives in the response header; the client does not need to know how the server constructs that value.

Illustrative GET response example:

~~~http
GET /api/people/42
Accept: application/hal+json

HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "7"

{
  "firstName": "An",
  "lastName": "Nguyen",
  "city": "Hanoi"
}
~~~

The value `"7"` is an example only. The actual ETag is a server-generated value, which may depend on the Spring Data REST version and configuration. Treat the ETag as an opaque string: store the exact received value, including quotation marks if present, and do not compute or alter it yourself.

If an entity lacks a version property or the server does not emit an ETag, optimistic concurrency via ETag may not be enabled for that resource. Verify the actual responses and configuration of the application.

## 3. Clients Must Keep the ETag Together with the Data Copy

When a client GETs a resource, store the ETag together with the representation:

~~~text
resource = Person 42
body     = { firstName, lastName, city, ... }
etag     = "7"
~~~

The ETag belongs to the exact resource representation that was read. Do not use Person 42's ETag to update Person 43, and do not use an old ETag after the client has downloaded a new version.

The client should simultaneously store:

- The resource URI, taken from the `self` link or server-published URI.
- The data that was read.
- The ETag received from the response header.
- Changes made by the user relative to the read copy, if merge support is needed.

Do not take a `version` field in JSON as an ETag by concatenating strings yourself. Use the actual ETag header returned by the server.

## 4. Sending If-Match on Write

When sending PUT, PATCH, or DELETE to a resource supporting optimistic locking, the client sends the received ETag in the `If-Match` header.

Example update using PUT:

~~~http
PUT /api/people/42
Content-Type: application/json
Accept: application/hal+json
If-Match: "7"

{
  "firstName": "An",
  "lastName": "Nguyen",
  "city": "Da Nang"
}
~~~

The server compares the precondition against the current version:

- If the ETag still matches, the request can proceed and save the changes.
- If the resource was updated by another client, the ETag no longer matches and the request is rejected.
- If the server requires conditional writes and the client omits the precondition, the response may be `428 Precondition Required`; exact behavior depends on configuration and version.

`If-Match` uses strong comparison under HTTP. With a weak ETag carrying a `W/` prefix, do not expect it to satisfy an `If-Match` precondition. Use the exact ETag provided by the API and check the endpoint contract.

### Using If-Match for PATCH and DELETE

PATCH:

~~~http
PATCH /api/people/42
Content-Type: application/merge-patch+json
If-Match: "7"

{
  "city": "Da Nang"
}
~~~

DELETE:

~~~http
DELETE /api/people/42
If-Match: "7"
~~~

The examples above illustrate conditional requests. Supported PATCH media types and methods depend on the API. For DELETE, `If-Match` helps prevent deleting a resource based on a copy the client read before someone else changed it.

`If-Match: *` only checks that the resource currently exists; it does not verify that the client is using the specific version it read. If the goal is preventing lost updates, use the specific ETag instead of the wildcard.

## 5. Two Clients Updating Concurrently: Step-by-Step Progression

Suppose the server returns ETag `"7"` for Person 42.

<text-placeholder/>

~~~text
             Server: Person 42, ETag "7"
                       |
              +--------+--------+
              |                 |
           Client A          Client B
           GET "7"           GET "7"
              |                 |
         Edit city         Edit lastName
              |                 |
     PUT If-Match "7"             |
              |                 |
           Success                |
        Server -> "8"             |
              |                 |
              +-----------------+
                                |
                       PUT If-Match "7"
                                |
                           Stale ETag
                                |
                     412 Precondition Failed
                                |
                         Client B re-GETs
                                |
                    Receives representation "8"
                                |
                        Compare and merge
                                |
                     PUT If-Match "8"
                                |
                       Save if still fresh
                                |
                         Server -> "9"
~~~

Sequence:

1. A and B both GET the same resource and receive ETag `"7"`.
2. A sends PUT with `If-Match: "7"`; the server accepts, saves the change, and the new version has ETag `"8"`.
3. B sends PUT with ETag `"7"`; the server sees a stale precondition and rejects it.
4. B receives `412 Precondition Failed` and reloads the resource and new ETag.
5. B compares the new data with its own changes, merges if safe, or asks the user to resolve.
6. If the merge is valid, B sends a new request with `If-Match: "8"`. If no one else updated meanwhile, the server accepts and creates the next version.

The ETag numbers in the diagram are only to explain the flow. Clients must not assume versions always increment by one or that ETags are numeric.

## 6. Handling 412 Precondition Failed

`412 Precondition Failed` indicates a condition in the request was no longer true at the time the server processed it. With `If-Match`, the common cause is that the resource changed since the client's GET.

Example:

~~~http
PUT /api/people/42
If-Match: "7"
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Tran",
  "city": "Hanoi"
}

HTTP/1.1 412 Precondition Failed
~~~

When receiving 412, the client should not immediately resend the exact old payload. Appropriate handling workflow:

1. Retain the user-edited copy and the old ETag so the conflict can be explained.
2. Re-GET the resource URI.
3. Extract the new representation and ETag from the response.
4. Compare the original copy, the user-edited copy, and the latest server copy.
5. Identify which fields were changed by only one side and which fields were modified by both sides.
6. Merge non-conflicting changes; for fields edited concurrently, apply business rules or ask the user to choose.
7. Resend the resolved changes along with the new ETag.
8. If 412 is received again, repeat the workflow up to a reasonable limit or ask the user to handle it manually.

Do not automatically swap the old ETag for the new ETag and resend the original payload. Doing so can overwrite someone else's latest changes and recreate the exact lost update bug that optimistic locking prevents.

## 7. How to Merge Changes?

You can compare three versions:

- **Base:** the representation the user originally fetched with GET.
- **Local:** the representation after the user edited it.
- **Remote:** the latest representation fetched from the server after the conflict.

Example:

| Field | Base | Local (B) | Remote (A) | How to handle |
|---|---|---|---|---|
| firstName | An | An | An | Unchanged |
| lastName | Nguyen | Tran | Nguyen | Only B changed; can keep Tran |
| city | Hanoi | Hanoi | Da Nang | Only A changed; keep Da Nang |
| phone | 0900 | 0911 | 0922 | Both changed; conflict resolution required |

In the example, B can merge `lastName=Tran` with `city=Da Nang` because the two clients edited different fields. However, `phone` was changed by both, so a single value cannot be chosen automatically without a business rule.

Field-level merging is only an example. If fields have business relationships, such as `startDate` and `endDate`, or `quantity` and `availableStock`, check domain invariants before combining them. Individual changes that do not conflict at the field level can still conflict at the business level.

## 8. Distinguishing If-Match from If-None-Match

Both headers involve ETags, but their purposes differ:

| Header | Purpose | Typical outcome |
|---|---|---|
| `If-Match` | Execute the operation only if the representation/resource still matches a known validator | Write succeeds or `412 Precondition Failed` |
| `If-None-Match` | Fetch the representation only if the validator does not match; usually for cache revalidation on GET | `200 OK` with new body or `304 Not Modified` |

Cache revalidation example:

~~~http
GET /api/people/42
If-None-Match: "8"
Accept: application/hal+json
~~~

If the representation still corresponds to the sent ETag, the server can return:

~~~http
HTTP/1.1 304 Not Modified
ETag: "8"
~~~

The client keeps its existing cached copy. 304 is not a write conflict response.

Conditional write example:

~~~http
PUT /api/people/42
If-Match: "8"
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Tran",
  "city": "Da Nang"
}
~~~

Here, the client asks the server to update only if the resource is still at the version the client read. If it does not match, the server returns 412.

Do not use `If-None-Match` in place of `If-Match` when protecting write operations from lost updates.

## 9. Clients Must Update the ETag After Every Successful Write

After a successful PUT/PATCH, the server may return a new ETag in the response header. The client must store the new validator along with the new representation.

Example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "8"
~~~

If the response is 204 and the server still returns an ETag, the client can store that ETag even without a body. If there is no new representation or validator, re-GET the resource to synchronize state.

After a POST creation, the client can store the URI from `Location` and the ETag if provided by the response. When acting further on the new resource, use the validator corresponding to that URI.

After a successful DELETE, discard the cache of the deleted resource and remove the old ETag from client state.

## 10. Spring Data REST Configuration and Implementation Notes

For optimistic locking to work on a JPA entity, declare a `@Version` field and ensure write operations go through a persistence provider supporting version checks.

Example:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    private String firstName;
    private String lastName;
}
~~~

With Spring Data REST, check the following points:

- Does GET on the resource return an ETag?
- Does the ETag change after a successful update?
- Do PUT/PATCH/DELETE check `If-Match`?
- How are requests missing preconditions handled in the current version/configuration?
- Is an old ETag rejected after another client updates?
- Which HTTP status/error are persistence-layer optimistic locking exceptions mapped to?
- Are there other write paths (custom controllers, batches, bulk updates, or direct SQL) bypassing version checks?

JPQL/SQL bulk updates or writes outside the entity lifecycle may not go through the same JPA dirty checking/version mechanism. If there are multiple write paths, ensure all of them uphold the domain's concurrency rules.

If the application uses MongoDB or another datastore, use the annotation/version mechanism appropriate for the corresponding Spring Data module. Do not copy `jakarta.persistence.Version` into a non-JPA module.

## 11. CORS When Clients Run in Browsers

If the frontend and API have different origins, the browser must be allowed to send the `If-Match` header and read the `ETag` header.

CORS configuration may need to:

- Allow the `If-Match` request header and necessary headers such as `Content-Type`.
- Expose the `ETag` response header so JavaScript can read it.
- Allow PUT, PATCH, or DELETE methods if supported by the API.
- Handle OPTIONS preflight requests properly.

Conceptual header example:

~~~http
Access-Control-Allow-Headers: Content-Type, If-Match
Access-Control-Expose-Headers: ETag, Location
~~~

These are illustrative headers; actual configuration must be placed at the appropriate CORS layer for the application and allowed origins. If the server returns ETag yet browser JavaScript cannot read it, check `Access-Control-Expose-Headers`.

## 12. Testing with curl

Read the resource and store the ETag:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42
~~~

Copy the exact ETag value from the response, for example `"7"`, then send an update:

~~~bash
curl -i \
  -X PUT \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/hal+json' \
  -H 'If-Match: "7"' \
  -d '{"firstName":"An","lastName":"Nguyen","city":"Da Nang"}' \
  https://localhost:8080/api/people/42
~~~

To test conflicts, perform two GETs before writing:

1. First GET, store the ETag.
2. Second GET, also store the same ETag.
3. PUT from client A with that ETag.
4. PUT from client B with the old ETag.
5. Verify B is rejected with a precondition failure per the server's contract.
6. Re-GET and check the new ETag.

Do not use an illustrative ETag if the server returns a different value. Do not strip quotation marks or replace the version with a guessed number.

## 13. Integration Tests for Optimistic Concurrency

An integration test should verify that two clients both read one version, yet only one write using the old version is accepted.

Conceptual scenario:

~~~text
GET /api/people/42 -> ETag "7"
GET /api/people/42 -> ETag "7"

PUT If-Match "7" -> success, new ETag "8"
PUT If-Match "7" -> 412 Precondition Failed

GET /api/people/42 -> current data, ETag "8"
~~~

With MockMvc, you can verify response headers and status:

~~~java
MvcResult firstRead = mockMvc.perform(
        get("/api/people/42")
            .accept("application/hal+json")
    )
    .andExpect(status().isOk())
    .andReturn();

String etag = firstRead.getResponse().getHeader("ETag");

mockMvc.perform(
        put("/api/people/42")
            .header("If-Match", etag)
            .contentType("application/json")
            .content("""
                {"firstName":"An","lastName":"Tran"}
                """)
    )
    .andExpect(status().isOk());
~~~

This only illustrates capturing the ETag and sending the precondition. To test real contention, the test must retain the old ETag, perform the first write, then send a second request with the old ETag and assert the conflict status appropriate for the running Spring Data REST version/configuration.

## 14. Common Misconceptions

- **ETag is a content hash generated by the client.** ETag is a validator published by the server; treat it as opaque.
- **Having an ETag means all lost updates are automatically prevented.** The server must support and check conditional writes or version locking.
- **Using If-None-Match for PUT.** Use If-Match to require the current version to match before writing.
- **Receiving 412 and resending the old payload with the new ETag.** This can overwrite another client's changes; you must refresh and merge first.
- **Changing the version field in JSON to force a write.** Version is concurrency metadata managed by the server/persistence provider.
- **Every conflict is 412.** Conditional header mismatches are typically 412; optimistic locking errors at other layers may be mapped differently depending on the stack.
- **ETags are only for caching.** ETags can also protect conditional updates.
- **A client can use another resource's ETag.** Validators must be tied to the exact URI/representation.
- **All write paths are automatically protected.** Bulk SQL, batch jobs, or custom write paths may require their own version-checking mechanisms.

## 15. Key Takeaways

- Multiple clients can hold stale data copies at the same time; writes without version checking can cause lost updates.
- `@Version` enables the persistence provider to detect concurrent updates.
- Spring Data REST can expose the version via the ETag response header.
- Clients store the ETag from GET and send the verbatim value in `If-Match` when writing.
- If the ETag matches, the operation can proceed; a stale ETag typically results in `412 Precondition Failed`.
- When receiving 412, re-GET, compare Base/Local/Remote, merge or ask the user to resolve, and only then retry with the new ETag.
- `If-None-Match` primarily serves cache revalidation; `If-Match` protects conditional operations.
- Update the ETag after every successful write and ensure all write paths obey the concurrency policy.

## References

- [RFC 9110 — HTTP Semantics: ETag and conditional requests](https://www.rfc-editor.org/rfc/rfc9110.html)
- [Spring Data REST Reference — Conditional requests and optimistic locking](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data JPA Reference — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Jakarta Persistence — Version attributes](https://jakarta.ee/specifications/persistence/)