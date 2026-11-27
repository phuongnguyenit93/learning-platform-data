# `If-Match` for PUT, PATCH, DELETE, and the 412 Response

## Objectives

`If-Match` lets a client update or delete a resource only when that resource is still at the version the client read. This mechanism prevents the situation where two clients concurrently edit an entity and the later request silently overwrites the earlier request's changes (lost update).

Spring Data REST supports conditional requests based on ETags. The server returns an ETag when reading a resource; the client sends that value back in the `If-Match` header when performing `PUT`, `PATCH`, or `DELETE`. If the ETag no longer matches the current version, the server rejects the operation with `412 Precondition Failed`.

## ETag and the `@Version` Property

An ETag is a version identifier of a representation/resource emitted by the server. For JPA entities, the standard way for Spring Data REST to support version checking is to declare a property annotated with `@Version`:

    @Entity
    public class Product {
        @Id
        @GeneratedValue
        private Long id;

        private String name;

        private BigDecimal price;

        @Version
        private Long version;

        // getters and setters
    }

`@Version` allows the persistence provider to detect concurrent updates. When a transaction writes the entity, the version is checked and incremented under JPA's optimistic locking mechanism. Spring Data REST can use this version information to generate the ETag and check preconditions for conditional requests.

An ETag is an opaque value to the client. Do not compute the ETag yourself from the ID, timestamp, or `version` field; use the exact value returned by the server, including quotation marks if present. Do not assume the ETag is always a number or always directly equals the value of the `@Version` property.

## Fetching the ETag Before Updating

First, the client reads the item resource and stores the `ETag` header from the response:

    GET /api/products/42 HTTP/1.1
    Host: localhost:8080
    Accept: application/hal+json

Example response:

    HTTP/1.1 200 OK
    Content-Type: application/hal+json
    ETag: "0"

    {
      "name": "Keyboard",
      "price": 75.00,
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/products/42"
        }
      }
    }

In the example, the client stores the exact header value `ETag: "0"`. This value is illustrative only; the actual ETag is determined by the server.

## Using `If-Match` with PUT

`PUT` replaces the resource's representation according to the endpoint contract. The client sends the ETag read earlier in `If-Match`:

    PUT /api/products/42 HTTP/1.1
    Host: localhost:8080
    Content-Type: application/json
    If-Match: "0"

    {
      "name": "Mechanical Keyboard",
      "price": 89.00
    }

If the resource still has an ETag matching `"0"`, the server processes the update. After a successful update, the response may return a new ETag; the client needs to store the new value for the next update.

If another client has already updated the resource and the current ETag changed to `"1"`, a request still sending `If-Match: "0"` will not be applied. The server returns `412 Precondition Failed` to report that the precondition is no longer true.

## Using `If-Match` with PATCH

`PATCH` modifies part of a representation. The version check mechanism is the same as PUT: the client sends the latest ETag in `If-Match` along with the patch document:

    PATCH /api/products/42 HTTP/1.1
    Host: localhost:8080
    Content-Type: application/merge-patch+json
    If-Match: "1"

    {
      "price": 92.00
    }

The example above illustrates JSON Merge Patch; the media type and patch format must match the patch type supported by the endpoint in the application. `If-Match` ensures the patch is applied only if the resource is still at the version on which the client based the patch.

Do not omit `If-Match` just because the patch only changes one field. A change to another field between read time and patch submission can still make the client's business decision stale.

## Using `If-Match` with DELETE

A client can also request to delete a resource only if it has not changed since the most recent read:

    DELETE /api/products/42 HTTP/1.1
    Host: localhost:8080
    If-Match: "2"

If the ETag matches, the server proceeds with deletion subject to access permissions and application constraints. If the resource has changed, the server returns `412 Precondition Failed` and does not execute the delete operation under the stale precondition.

This is useful when a UI displays resource details for a user to confirm deletion. If the resource was edited by someone else while the user was viewing it, the client can ask the user to reload before confirming the action.

## Meaning of the 412 Response

`412 Precondition Failed` means the condition in the request was no longer true at the time the server processed it. With `If-Match`, the common cause is that the ETag sent by the client does not match the resource's current ETag.

Example:

1. Client A reads the resource and receives ETag `"4"`.
2. Client B reads the same resource, updates successfully, and the server issues a new ETag `"5"`.
3. Client A sends PUT with `If-Match: "4"`.
4. The server compares against the current version, detects that the ETag has changed, and returns `412 Precondition Failed`.

Client A should not automatically resend the same payload with the new ETag without reading the new state. The safe way to handle this is:

- Re-read the resource to obtain the new representation and ETag.
- Compare the current changes with the user's or business intent.
- Incorporate the other party's changes if appropriate.
- Build a new request based on the new representation and send it with the new ETag.
- If the conflict cannot be resolved automatically, ask the user to choose how to proceed.

`412` is a precondition conflict, unlike `409 Conflict`, which usually represents a state or business rule conflict at the application layer. Clients should handle errors according to the actual status and error body committed by the API.

## When If-Match Is Omitted

If a client sends PUT, PATCH, or DELETE without `If-Match`, the request does not carry the version condition previously read by the client. Therefore, the client does not receive lost-update protection from this precondition.

For operations requiring concurrent update protection, require clients to send the ETag. You can enforce a mandatory conditional request policy at the API or service layer if the application needs to reject operations without preconditions. Do not assume all Spring Data REST configurations require `If-Match` when the header is omitted.

The `If-Match: *` header means in HTTP to proceed only if the resource currently exists; it does not confirm that the resource is still at the exact version the client read. If the goal is to prevent lost updates, use the specific ETag received from the response rather than a wildcard.

## Examples with cURL

Read the resource and inspect the ETag:

    curl -i http://localhost:8080/api/products/42 \
      -H "Accept: application/hal+json"

Copy the exact ETag from the response and use it in PUT:

    curl -i -X PUT http://localhost:8080/api/products/42 \
      -H "Content-Type: application/json" \
      -H 'If-Match: "0"' \
      -d '{"name":"Mechanical Keyboard","price":89.00}'

PATCH example:

    curl -i -X PATCH http://localhost:8080/api/products/42 \
      -H "Content-Type: application/merge-patch+json" \
      -H 'If-Match: "1"' \
      -d '{"price":92.00}'

DELETE example:

    curl -i -X DELETE http://localhost:8080/api/products/42 \
      -H 'If-Match: "2"'

The ETags `"0"`, `"1"`, and `"2"` are sequential examples only. In a real application, always take the ETag from the most recent response for that exact resource.

## Verifying Configuration and Behavior

1. Declare `@Version` on the entity exposed via Spring Data REST and ensure the persistence provider supports optimistic locking.
2. Send GET to the item endpoint; verify the response has an `ETag` header.
3. Send PUT with the ETag just read; verify the update succeeds and receives a new ETag if the response provides one.
4. Send PATCH with the current ETag; verify the patch is applied only while the precondition remains true.
5. Send DELETE with the current ETag; verify the operation obeys the version condition.
6. Read the resource from two clients; update from the first client, then send a request from the second client with the old ETag; verify the server returns `412`.
7. After `412`, verify the data was not overwritten by the stale request and the client must re-read before deciding to send new changes.
8. Try a request without `If-Match` to confirm whether the application's policy allows or requires conditional requests.

Integration tests should check the status code, returned ETag, database state after a successful request, and database state after a request with a stale ETag. Checking only for a `412` response is not enough without confirming the data remained unchanged.

## Implementation Notes

- Use `@Version` to enable optimistic locking at the persistence layer; ETag and `If-Match` provide the mechanism to pass preconditions over HTTP.
- The ETag must be treated as an opaque token. Keep quotation marks intact and do not manually increment or fabricate values.
- Store the new ETag after every successful read or update; do not reuse an old ETag after the resource has changed.
- Apply version checking to PUT, PATCH, and DELETE on item URIs; association endpoints or custom endpoints need to be verified according to the application's actual support.
- If the response lacks an ETag, check `@Version`, the repository type, Spring Data REST configuration, and response headers before letting clients rely on conditional updates.
- Optimistic locking does not replace authorization, validation, or database constraints. It only detects requests based on a stale version.

`If-Match` binds a write or delete operation to the exact resource version the client read. When the version changes, `412 Precondition Failed` helps prevent silent overwrites; the client must re-read, resolve conflicts, and only then send a new request.