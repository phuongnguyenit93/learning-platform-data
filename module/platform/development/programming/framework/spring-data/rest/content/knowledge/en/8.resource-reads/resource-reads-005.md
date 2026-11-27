# OPTIONS and Allow to Inspect Available HTTP Methods

When integrating with Spring Data REST, clients often know a resource's URL but are not certain which HTTP methods that endpoint supports. A collection, an item, a search resource, and an association resource may expose different operations. HTTP `OPTIONS` allows a client to query the capabilities of a target resource; the response typically uses the `Allow` header to advertise supported methods.

## 1. What is OPTIONS used for?

`OPTIONS` is an HTTP method used to ask the server about the communication options available for a resource or server. A request targeting a specific URI helps the client discover which operations that endpoint supports without performing a data read or write operation such as GET, POST, or DELETE.

Example:

```http
OPTIONS /people/42 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

The server may return a success response with the header:

```http
HTTP/1.1 200 OK
Allow: GET, HEAD, PUT, PATCH, DELETE, OPTIONS
```

The list above is only an illustrative example. Actual methods depend on the endpoint, exported repositories, Spring Data REST configuration, Spring MVC, security, and the running framework version.

An OPTIONS response typically does not need to return an entity representation. The primary goal is to advertise communication capabilities through status and response headers. Clients should read the headers rather than expecting JSON containing resource data.

## 2. What does Allow tell you?

`Allow` is a response header that lists the HTTP methods currently supported by the target resource. The methods are separated by commas.

Example:

```http
Allow: GET, HEAD, PUT, PATCH, DELETE, OPTIONS
```

In this example, the endpoint advertises GET, HEAD, PUT, PATCH, DELETE, and OPTIONS. Clients can use this information to decide the next action or display appropriate actions in a user interface.

Understand the scope of the header accurately:

- `Allow` describes the methods supported at the queried resource, not the list of methods for the entire API.
- Collections and items may return different lists.
- Association resources and search resources may also have their own methods.
- The header reflects the server's current capabilities; configuration or deployment version changes can alter the list.
- Having a method in `Allow` does not guarantee every specific request will succeed. The body may still be malformed, data may be invalid, the resource may not be in a state allowing the operation, or the caller may lack permissions.

According to HTTP semantics, a `405 Method Not Allowed` response must include an `Allow` header indicating the methods currently supported for the target resource. This is useful when a client sends a method not accepted by the endpoint.

## 3. Sending OPTIONS with curl

You can use curl to inspect an endpoint:

```bash
curl -i -X OPTIONS https://api.example.test/people
```

Depending on how the server is implemented, you might receive a response like:

```http
HTTP/1.1 200 OK
Allow: GET, HEAD, POST, OPTIONS
```

Then inspect a specific item:

```bash
curl -i -X OPTIONS https://api.example.test/people/42
```

An item may advertise different methods than a collection, for example:

```http
HTTP/1.1 200 OK
Allow: GET, HEAD, PUT, PATCH, DELETE, OPTIONS
```

These are two hypothetical responses illustrating how to read the output, not a guarantee that every Spring Data REST repository returns those exact methods. Call the actual endpoint you are integrating with and inspect the real response.

If the endpoint requires authentication, send credentials using the mechanism the application uses. When receiving `401 Unauthorized` or `403 Forbidden`, distinguish authentication/authorization errors from unsupported methods.

## 4. Inspecting different resource types in Spring Data REST

Do not inspect one URL and apply that `Allow` list to every other endpoint. In Spring Data REST, each resource type represents a distinct group of operations.

| Resource | Example URL | What to check |
|---|---|---|
| Collection | `/people` | Reading the list, creating items, and exported collection methods |
| Item | `/people/42` | Reading, updating, or deleting a single entity |
| Search resource | `/people/search` | Discovering and invoking exported query methods |
| Association | `/people/42/orders` | Reading or modifying relationships between entities |

For example, you can send requests in turn:

```bash
curl -i -X OPTIONS https://api.example.test/people
curl -i -X OPTIONS https://api.example.test/people/42
curl -i -X OPTIONS https://api.example.test/people/search
curl -i -X OPTIONS https://api.example.test/people/42/orders
```

The URLs above are examples. Your application's base path, collection resource rel, item resource rel, and association paths may differ. Use the actual URLs exposed by the API in HAL links or endpoint documentation.

Spring Data REST builds handlers based on repositories and export configuration. Having a Java method on a repository does not automatically mean that method is exposed over REST. For instance, a method or repository marked `@RestResource(exported = false)` will not be exported according to that configuration. Custom repository methods also need to be properly exported and mapped before clients can invoke them over HTTP.

Therefore, OPTIONS is a way to observe a running endpoint. It complements reading repository configuration and HAL links, rather than replacing an understanding of the API contract.

## 5. OPTIONS and 405 Method Not Allowed errors

Suppose a client sends DELETE to a collection that only supports GET and POST. The server may return:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, POST, OPTIONS
Content-Type: application/problem+json
```

Meaning:

- `405` indicates the sent method is not allowed at the target resource.
- `Allow` indicates the currently supported methods.
- The error body, if present, provides additional details in the format used by the server.

The client can use `Allow` to update how it makes requests or display appropriate actions. However, do not automatically retry with another method merely because it appears in the header; the client still needs to know the business semantics and required payload of that operation.

Distinguish some common statuses:

| Status | Meaning in this situation |
|---|---|
| `200 OK` / `204 No Content` | OPTIONS processed successfully; inspect response headers |
| `404 Not Found` | Target URI was not found or is not exposed as handled by the server |
| `405 Method Not Allowed` | Resource exists, but the sent method is unsupported; check `Allow` |
| `401 Unauthorized` | Missing or invalid authentication credentials |
| `403 Forbidden` | Caller was identified but is not permitted to perform the request under policy |

Not every server uses the exact same body or status in every scenario. Rely on the actual status and headers, and check security configuration if the request is rejected.

## 6. Standard OPTIONS vs. CORS preflight

A common point of confusion is that browsers use OPTIONS for **CORS preflight**. This is still HTTP OPTIONS, but the request's purpose is to ask whether an intended cross-origin request is permitted from the current origin.

A browser might send:

```http
OPTIONS /people/42 HTTP/1.1
Host: api.example.test
Origin: https://frontend.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type, authorization
```

The server may return CORS response headers:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://frontend.example.test
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, Authorization
```

Two pieces of information must be distinguished:

| Header | Meaning |
|---|---|
| `Allow` | HTTP methods supported by the target resource |
| `Access-Control-Allow-Methods` | Methods the server allows the browser to use in a CORS context for the origin/request under consideration |

CORS preflight may also check the origin and request headers. Thus, a method present in `Allow` is not necessarily permitted for cross-origin browser calls; CORS policy may restrict it. Conversely, `Access-Control-Allow-Methods` does not replace the endpoint actually implementing that method.

When debugging in a browser, inspect both the OPTIONS request and the CORS response headers in the Network panel. If calling the API with curl succeeds while the browser is blocked, the cause may be CORS policy rather than the repository endpoint.

## 7. OPTIONS does not replace security or validation

OPTIONS helps discover the HTTP capabilities of a resource. It is not an authorization mechanism and does not pre-check all preconditions of an operation.

Examples:

- `Allow` may advertise PATCH, yet PATCH can still return 401 or 403 if the caller lacks sufficient permissions.
- The caller has permission for PATCH, but if the payload is invalid, the server may still return 400.
- DELETE is supported, yet the resource is constrained by business rules or data constraints; the operation can still fail.
- A link or method not advertised in a response is not proof that the URI is safe if accessed directly.

The server must enforce authentication, authorization, validation, and business state checks on the actual request. Clients use OPTIONS as an API discovery signal, not as a guarantee that an action will succeed.

## 8. Client workflow for inspecting methods

1. Obtain the resource URI from a HAL link or the API contract.
2. Send OPTIONS to that exact URI, preserving the necessary authentication context.
3. Read the status code and the `Allow` header if provided by the server.
4. If a browser is making cross-origin calls, also check `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers`.
5. Choose a method according to the API contract and send the real request with the appropriate payload, `Content-Type`, and `Accept`.
6. Handle the actual response: a supported method can still fail due to permissions, validation, resource state, or persistence errors.

By checking each URI individually rather than inferring from a single generic endpoint, clients can clearly understand the capabilities of collection, item, search, and association resources. `OPTIONS` and `Allow` provide a standard way to discover HTTP methods, while Spring Data REST and Spring Security remain responsible for deciding which endpoints are actually exported and which requests are accepted.
