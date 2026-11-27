# Content Negotiation with Accept and Content-Type

In HTTP, client and server must agree on how outgoing data is represented and how returned data is represented. Two essential headers for this are `Content-Type` and `Accept`. With Spring Data REST, understanding these two headers properly helps clients send valid payloads, receive the right HAL representation, and work accurately with both resource and association endpoints.

## 1. Two Headers Solve Two Different Directions

**`Content-Type` describes the content of the request body.** The client sends this header to tell the server which media type the payload is encoded in. For example, a JSON body typically uses `application/json`; a list of URIs used to manipulate associations typically uses `text/uri-list`.

**`Accept` describes the representation the client wants to receive in the response.** The client can request HAL JSON using `application/hal+json`, or another media type supported by the server.

You can remember this with two questions:

| Header | Question | Direction |
|---|---|---|
| `Content-Type` | What format am I sending data in? | Request body → server |
| `Accept` | What format do I want the response in? | Client ← response |

For example, a request to create a person can send JSON while requesting a HAL response:

```http
POST /people HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/hal+json

{
  "name": "An",
  "email": "an@example.test"
}
```

Here, `Content-Type` tells Spring how to read the JSON body. `Accept` tells Spring that the client wants the returned representation to be HAL JSON. The two headers do not need to match because they describe two independent directions.

## 2. Media Types and Content Negotiation

A media type has the general form:

```text
type/subtype
```

Some media types commonly encountered in Spring Data REST and HAL:

| Media type | Common meaning |
|---|---|
| `application/json` | Plain JSON |
| `application/hal+json` | JSON following HAL structure, which may contain `_links` and `_embedded` |
| `application/alps+json` | Profile metadata in ALPS format |
| `text/uri-list` | One or more URIs, commonly used when manipulating associations |

**Content negotiation** is the process of selecting an appropriate representation based on the client's request and the server's capabilities. The client sends `Accept`; Spring MVC and `HttpMessageConverter`s check the requested media types, the representations the endpoint can produce, and which converter can write that data.

Spring Data REST uses HAL as its default hypermedia representation in standard configurations. Consequently, collection or item responses typically contain `_links`, and collections may contain `_embedded`. When a client wants to rely on hypermedia relations, it should explicitly request `application/hal+json` to state its expectation.

Example:

```http
GET /people/42 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

Illustrative response:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

```json
{
  "name": "An",
  "email": "an@example.test",
  "_links": {
    "self": {
      "href": "https://api.example.test/people/42"
    }
  }
}
```

The actual media type depends on the endpoint, converters, and `RepositoryRestConfiguration`. If an application changes the default media type or HAL settings, clients must follow the contract published by the server.

## 3. Using Accept to Request a HAL Response

When a client needs to navigate the API using relations, `Accept: application/hal+json` is the explicit choice:

```bash
curl -i \
  -H "Accept: application/hal+json" \
  https://api.example.test/people/42
```

The client inspects the response `Content-Type` to confirm which representation the server returned. Then, if the response is HAL, the client reads the relations in `_links` instead of assuming URLs from route structures.

If a client sends multiple media types in `Accept`, it can indicate preference order using a quality value `q`:

```http
Accept: application/hal+json, application/json;q=0.8
```

The `q` value ranges from 0 to 1; higher values indicate higher priority. The server can still only select a representation that the endpoint and converters actually support. A wildcard such as `*/*` indicates the client accepts many content types, so the server may fall back to its default media type.

Do not assume that sending `Accept: application/json` always produces the exact same structure as HAL. Plain JSON and HAL JSON are two media types with different purposes. If an application depends on `_links`, request HAL explicitly and verify the response `Content-Type`.

## 4. Using Content-Type When Sending Entity JSON

For operations that create or update an entity through a repository resource, the JSON body must use a media type supported by the endpoint, usually `application/json`. Example:

```bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"name":"An","email":"an@example.test"}' \
  https://api.example.test/people
```

Spring MVC selects the appropriate `HttpMessageConverter` to read the body. Jackson deserializes the JSON into a Java object before Spring Data REST proceeds with the repository operation.

A request can fail before the repository is invoked if:

- The JSON is syntactically invalid.
- A data type in the JSON cannot be converted to the corresponding Java type.
- The request declares a `Content-Type` that the endpoint does not support.
- The body fails application constraints or validation.

Distinguish parse/conversion errors from validation errors. For example, `"age": "abc"` when the Java field is numeric may fail during type conversion; whereas `"name": ""` may convert successfully but be rejected by a validator.

## 5. Special Content-Type When Manipulating Associations

Spring Data REST does not always accept a full entity JSON when a client modifies a relationship. For association resources, a common approach is to send the URI of the related resource using the `text/uri-list` media type.

Example assigning an address with URI `/addresses/7` to a person's `address` association:

```http
PUT /people/42/address HTTP/1.1
Host: api.example.test
Content-Type: text/uri-list
Accept: application/hal+json

https://api.example.test/addresses/7
```

Here, the body is not a JSON object. It is a URI sent in `text/uri-list` format. If the client sends a URI body while declaring `Content-Type: application/json`, the converter may try to parse the content as JSON and the request will not be processed as intended.

For multi-valued associations, `text/uri-list` can contain multiple URIs, one per line. Whether to use PUT, POST, PATCH, or DELETE also depends on the association type and the semantics supported by the association endpoint. Read the API contract and the links returned by the server to determine valid operations.

## 6. Profiles and Metadata Media Types

A HAL response can advertise a `profile` relation so clients can discover the semantic description of a resource. In Spring Data REST, the profile typically leads to ALPS metadata. When accessing a profile resource, the client can request the `application/alps+json` media type.

Example:

```http
GET /profile/people HTTP/1.1
Host: api.example.test
Accept: application/alps+json
```

This differs from requesting an entity representation in HAL. `application/alps+json` describes metadata/profiles; `application/hal+json` represents resources alongside hypermedia links. Clients need to choose the `Accept` header matching the type of resource they are accessing.

## 7. Common Negotiation Errors

| HTTP status | Common cause | How to check |
|---|---|---|
| `406 Not Acceptable` | The server cannot produce a representation matching the media types in `Accept` | Check `Accept`, media types supported by the endpoint, and converter configuration |
| `415 Unsupported Media Type` | The server cannot read the request body with the sent `Content-Type` | Check the payload's media type; use JSON or `text/uri-list` as appropriate |
| `400 Bad Request` | Malformed body, wrong types, or validation failure | Check JSON syntax, data types, and validation errors in the response |
| `401 Unauthorized` / `403 Forbidden` | Request lacks authentication or sufficient permissions | Check credentials and authorization; changing media types does not resolve permission errors |

Do not treat every error as a single "invalid JSON" error. 406 usually relates to the output representation; 415 relates to the request body format; 400 may be a deserialization or validation error. Distinguishing them properly helps the client fix the right header or payload.

## 8. Header Selection Workflow for Clients

Before sending a request, a client can apply these steps:

1. Identify whether the target endpoint is an item, collection, search, profile, or association resource.
2. Determine whether a body is present and whether the body is a JSON entity, HAL payload, or URI list.
3. Set `Content-Type` to match the body's exact format; if there is no body, do not add this header unnecessarily.
4. Set `Accept` to the desired representation, such as `application/hal+json` for hypermedia resources or `application/alps+json` for ALPS profiles.
5. Read the response `Content-Type` and check the status code before parsing the body.
6. If HAL is received, use relations in `_links` to continue navigating; do not infer URIs from entity names or IDs.

| Scenario | Request Content-Type | Request Accept |
|---|---|---|
| GET a HAL item | No request body | `application/hal+json` |
| GET an ALPS profile | No request body | `application/alps+json` |
| POST a JSON entity | `application/json` | `application/hal+json` |
| PUT an association by URI | `text/uri-list` | `application/hal+json` |

These values are common patterns for Spring Data REST; specific application configuration and endpoints still determine supported media types. Check response headers and server API documentation when integrating with a real system.

When you properly distinguish `Accept` and `Content-Type`, clients can request the appropriate hypermedia representation, send the right format for each endpoint type, and identify the root cause of negotiation errors. This is the foundation for stable Spring Data REST integration while taking full advantage of HAL and HATEOAS.
