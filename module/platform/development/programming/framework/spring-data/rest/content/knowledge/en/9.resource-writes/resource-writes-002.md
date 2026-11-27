# `201 Created`, `Location`, and Retrieving the Representation After Creation

## Objectives

When a client creates an entity through Spring Data REST, the request is typically a `POST` to the repository's collection endpoint. If creation succeeds, the server returns `201 Created` and a `Location` header containing the URI of the newly created resource. The client uses this URI to access the exact new resource, even when the server generates the ID itself or the path has been customized.

## Sending a resource creation request

For example, `PersonRepository` is exposed at `/people`, the application has base path `/api`, and the entity has fields `firstName`, `lastName`:

    POST /api/people HTTP/1.1
    Host: localhost:8080
    Content-Type: application/json
    Accept: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen"
    }

Spring Data REST receives the JSON, creates the entity, and saves it via the repository. When the operation succeeds, the response looks like:

    HTTP/1.1 201 Created
    Location: http://localhost:8080/api/people/42

In the example, `42` is the system-assigned ID. The actual value depends on the key generation mechanism and existing data; clients should not guess IDs or assemble URIs from a fixed rule.

## Meaning of `201 Created`

`201 Created` indicates that the request successfully created a new resource. In Spring Data REST, the created resource is an item belonging to the repository collection that received the request.

The `Location` header indicates the URI of the newly created item. This is key information for the client to continue working with the resource: reading data, updating, or deleting at that URI. Take the header value directly from the response, treat it as a URI, and do not assume that IDs are always numeric or that paths always follow `/{id}`.

The path in `Location` is affected by the repository's collection path and the application base path. For example, `spring.data.rest.base-path=/api` prefixes URLs with `/api`; `@RepositoryRestResource(path = "...")` can change the collection path segment.

## Retrieving the representation of the newly created resource

The `Location` header is the resource-identifying URI; it does not mean the response always includes the full JSON of the entity. By default, Spring Data REST does not return a representation in the creation response body. Therefore, the client can send a `GET` request to the URI received in `Location` to retrieve the representation:

    GET /api/people/42 HTTP/1.1
    Host: localhost:8080
    Accept: application/hal+json

The resource read response typically looks like:

    HTTP/1.1 200 OK
    Content-Type: application/hal+json

    {
      "firstName": "An",
      "lastName": "Nguyen",
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/people/42"
        },
        "person": {
          "href": "http://localhost:8080/api/people/42"
        }
      }
    }

The actual body depends on entity properties, projections, serialization configuration, and the links the application exposes. Use the `Location` URI to identify the resource and then read the representation from the `GET` response; do not rely on a fixed JSON example.

## Asking Spring Data REST to return a body directly in the creation response

If the client needs the representation immediately after `POST`, you can enable the `return-body-on-create` option:

    spring.data.rest.return-body-on-create=true

In Spring Boot, set this property in `application.properties` or the equivalent configuration for your application's runtime environment. When enabled, Spring Data REST can include the representation of the new resource in the `201 Created` response. The `Location` header still provides the resource's URI and should still be used by clients as the canonical identifier.

If this option is not enabled, the client should perform a `GET` to `Location` when it needs the newly saved data. Receiving the body directly or calling `GET` is a choice about how the client obtains the representation; both cases rely on the same created resource.

## Example with cURL

You can save the creation request's response headers to obtain the URI returned by the server:

    curl -i -X POST http://localhost:8080/api/people \
      -H "Content-Type: application/json" \
      -H "Accept: application/hal+json" \
      -d '{"firstName":"An","lastName":"Nguyen"}'

Read the `Location` value in the response, then call that URI:

    curl -i http://localhost:8080/api/people/42 \
      -H "Accept: application/hal+json"

In a real application, replace the illustrative URL with the exact `Location` value received from the first response. This example separates the two steps to make clear that the ID and URI are decided by the server.

## Error handling and edge cases to watch out for

- `400 Bad Request`: invalid JSON or data fails validation; inspect the response to find the field and error cause.
- `415 Unsupported Media Type`: the request sent a media type not supported by the endpoint; when sending JSON, set `Content-Type: application/json`.
- `409 Conflict`: the creation operation conflicts with the application's state or data constraints; handle according to the error details returned by the server.
- Missing expected `Location`: inspect the actual response, receiving endpoint, and Spring Data REST configuration; the client should not construct a URI on the server's behalf.
- `GET` to `Location` fails: check whether the URI was preserved when parsed, client access permissions, and whether the resource still exists.

Validation, uniqueness constraints, and business logic still apply when an entity is created through a REST repository. `201 Created` is returned only when the creation operation completes successfully.

## Workflow clients should follow

1. Send `POST` to the collection endpoint with `Content-Type: application/json` and a valid payload.
2. Check for status `201 Created`.
3. Read the `Location` header and store the URI returned by the server.
4. If the response already contains a representation and the client needs to use it immediately, read that body; otherwise, send `GET` to the URI in `Location` with `Accept: application/hal+json`.
5. Use the HAL links in the representation to continue navigating or operating on the resource.

Do not assemble URIs from assumed IDs, do not assume `POST` responses always have a body, and do not confuse `Location` with the representation content. These two pieces of information serve different purposes: `Location` identifies the new resource, while the representation describes that resource's state and links.