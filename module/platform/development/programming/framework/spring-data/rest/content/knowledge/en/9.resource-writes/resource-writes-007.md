# JSON Patch with application/json-patch+json and Basic Operations

JSON Patch is a format that describes a sequence of changes to apply to a JSON document. Instead of resending the entire entity, the client sends an array of operations specifying the action, path, and value to use. With Spring Data REST, this approach is useful when you want to update a few properties of a resource via HTTP PATCH, provided the endpoint and server configuration support the JSON Patch media type.

## 1. What is JSON Patch?

JSON Patch is standardized in RFC 6902. A JSON Patch document is a JSON array; each element is an operation executed in the exact order it appears.

An operation typically has the fields:

- `op`: operation name, such as `add`, `remove`, `replace`, `move`, `copy`, or `test`.
- `path`: JSON Pointer identifying the target location in the document.
- `value`: value to add, replace, or compare; present only on operations that require a value.
- `from`: source path, used by `move` and `copy`.

Example patch document:

```json
[
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  },
  {
    "op": "add",
    "path": "/nickname",
    "value": "An"
  }
]
```

The two operations are applied sequentially: first changing `name`, then adding the `nickname` property. The final result depends on the initial document and whether each operation is valid at the moment it runs.

JSON Patch differs from JSON Merge Patch. JSON Patch expresses each operation explicitly as an array of operations; JSON Merge Patch expresses an object describing the values to merge and has its own semantics for `null`. The two formats have different media types and cannot be interchanged arbitrarily.

## 2. application/json-patch+json and HTTP PATCH

The standard media type for JSON Patch is:

`application/json-patch+json`

The client sends the patch document in the request body and declares this media type via `Content-Type`. The `Accept` header indicates the representation the client wants back; with Spring Data REST, clients usually request HAL JSON if the endpoint returns hypermedia representations.

Example:

```http
PATCH /people/42 HTTP/1.1
Host: api.example.test
Content-Type: application/json-patch+json
Accept: application/hal+json

[
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  },
  {
    "op": "add",
    "path": "/nickname",
    "value": "An"
  }
]
```

Here:

- `PATCH` indicates a request to partially modify a resource.
- `Content-Type` tells the server the body is a JSON Patch document.
- `Accept` requests the response in HAL JSON.
- `/people/42` is the URI of the item resource in the example.

Not every endpoint that supports PATCH automatically supports `application/json-patch+json`. Spring Data REST depends on the version, HTTP message converters, supporting libraries, and application configuration. Confirm that the endpoint accepts this media type; otherwise, the server may return `415 Unsupported Media Type`. Also distinguish JSON Patch from other PATCH formats the application may configure, such as JSON Merge Patch.

## 3. JSON Pointer: how to specify the target location

The `path` field uses JSON Pointer (RFC 6901). A pointer normally starts with a slash `/`; each segment after a slash identifies a key in an object or a position in an array.

Given the document:

```json
{
  "name": "An",
  "address": {
    "city": "Da Nang",
    "postalCode": "550000"
  },
  "tags": ["java", "spring", "rest"]
}
```

Corresponding pointers:

| Pointer | Location |
|---|---|
| `/name` | The name property at the root |
| `/address/city` | city inside address |
| `/tags/0` | First element of tags |
| `/tags/2` | Third element of tags |

If a key name contains `/` or `~`, JSON Pointer requires escaping:

- `~1` represents `/`.
- `~0` represents `~`.

For example, key `a/b` is written as pointer segment `a~1b`. When both characters appear, escape them strictly according to JSON Pointer rules; do not URL-encode the pointer instead of applying these escape rules.

For arrays, indices start at 0. The token `-` has special meaning in the `add` operation: it indicates the position for appending an element to the end of the array. This token is not a valid index for every operation.

## 4. Six basic operations

### add — add a value

`add` inserts a value at `path`.

- If path points to a nonexistent object property, the property is created.
- If the property already exists, its value is replaced.
- If path points to an array index, the new element is inserted at that position and subsequent elements shift.
- Use `-` to append an element to the end of an array.

Example adding a tag at the end:

```json
[
  {
    "op": "add",
    "path": "/tags/-",
    "value": "spring-data"
  }
]
```

### remove — remove a value

`remove` deletes the value at path. Path must identify an existing property or element.

```json
[
  {
    "op": "remove",
    "path": "/address/postalCode"
  }
]
```

After the operation, the `postalCode` property is no longer in the `address` object.

### replace — replace a value

`replace` replaces the value at path with `value`. Path must exist.

```json
[
  {
    "op": "replace",
    "path": "/address/city",
    "value": "Ho Chi Minh City"
  }
]
```

### move — move a value

`move` removes the value at `from` and adds that value at `path`. Both pointers must be valid for the document at the moment the operation runs.

```json
[
  {
    "op": "move",
    "from": "/address/city",
    "path": "/previousCity"
  }
]
```

A node cannot be moved inside one of its own child nodes. When working with arrays, remember that removing the source element can shift the indices of subsequent elements before the destination is processed.

### copy — copy a value

`copy` reads the value at `from` and adds a copy at `path`. The source value remains intact.

```json
[
  {
    "op": "copy",
    "from": "/address/city",
    "path": "/billingCity"
  }
]
```

### test — test a value

`test` compares the value at path with `value`. If they are not equal under JSON Patch semantics, the operation fails.

```json
[
  {
    "op": "test",
    "path": "/status",
    "value": "ACTIVE"
  },
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  }
]
```

In this example, the replace operation only proceeds if the current status is `ACTIVE`. `test` is useful for asserting a condition on the current state, though it does not replace concurrency control at the HTTP or database level.

## 5. Combining multiple operations in one patch

A patch document can contain multiple operations, and ordering is critical. Each operation sees the result of the operations that ran before it.

Example:

```json
[
  {
    "op": "test",
    "path": "/status",
    "value": "ACTIVE"
  },
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  },
  {
    "op": "add",
    "path": "/tags/-",
    "value": "spring-data"
  },
  {
    "op": "remove",
    "path": "/temporaryNote"
  }
]
```

If `test` fails or another operation has an invalid path, the patch cannot be considered successfully applied. Under HTTP PATCH semantics, the server must apply the entire patch atomically: it must not leave a partially updated state if the patch fails. Actual transaction and persistence details still need to be verified in the server implementation.

JSON Patch is not automatically idempotent. For example, `add` to `/tags/-` can append a duplicate element if the client resends the request. Therefore, do not blindly retry a PATCH after a timeout without knowing whether the server already processed the request.

## 6. JSON Patch in Spring Data REST

Spring Data REST exposes repository resources as HTTP endpoints. An item resource can support PATCH to partially update data. However, the ability to accept JSON Patch specifically depends on the media types and converters/patch handlers configured in the application.

When integrating, verify:

1. The item URI is exported and the client is calling the right URI.
2. The endpoint supports HTTP PATCH.
3. The server accepts `application/json-patch+json` and can read a JSON Patch document.
4. The paths in the patch match properties that the endpoint permits updating.
5. The returned representation matches the `Accept` requested by the client.

Do not assume every Java property is a writable path. A field may be absent from the representation, restricted by mapping, read-only, or disallowed from being modified through the repository resource. Associations may also have their own semantics and association resources; changing relationships often requires following the association links exposed by Spring Data REST rather than assuming every relation can be replaced by a JSON object path.

Example using curl:

```bash
curl -i -X PATCH \
  -H "Content-Type: application/json-patch+json" \
  -H "Accept: application/hal+json" \
  --data-binary '[
    {"op":"replace","path":"/name","value":"An Nguyen"},
    {"op":"add","path":"/nickname","value":"An"}
  ]' \
  https://api.example.test/people/42
```

This is a sample request. Field names, URIs, supported media types, and responses depend on your actual API configuration. If the server uses JSON Merge Patch or a custom PATCH format, send the exact media type advertised by the endpoint.

## 7. Concurrency, ETag, and If-Match

A patch is typically based on state the client read earlier. If another client updates the resource before the patch is sent, the patch could inadvertently apply to a newer version and produce unintended results.

HTTP provides conditional requests to reduce this risk. If the server returns an ETag for the representation, the client can send that value in `If-Match`:

```http
PATCH /people/42 HTTP/1.1
Host: api.example.test
Content-Type: application/json-patch+json
Accept: application/hal+json
If-Match: "version-7"

[
  {
    "op": "replace",
    "path": "/name",
    "value": "An Nguyen"
  }
]
```

The server should apply the change only if the validator still matches the current version. If the representation has changed, the server may return `412 Precondition Failed`. ETags and conditional requests must be supported and properly configured on the server; do not fabricate ETags on the client or assume every Spring Data REST endpoint enables this mechanism.

## 8. Common errors when sending JSON Patch

| Status | Possible causes | Resolution |
|---|---|---|
| `400 Bad Request` | Invalid JSON, missing operation fields, bad pointer, or operation cannot be performed | Check JSON syntax, `op`, `path`, `from`, and document state |
| `404 Not Found` | Item URI or target path does not exist per server handling | Check item URI and pointer |
| `405 Method Not Allowed` | Endpoint does not support PATCH | Check allowed methods and API contract |
| `409 Conflict` | Patch conflicts with current state or server processing rules | Read the new state and construct an appropriate patch |
| `412 Precondition Failed` | `If-Match` condition no longer holds | Re-read representation/ETag and decide on a new patch |
| `415 Unsupported Media Type` | Server does not support `application/json-patch+json` at the endpoint | Check converters and media types accepted by the endpoint |
| `422 Unprocessable Content` | Server understands syntax but cannot process patch content per application rules | Check validation and business rules if the server uses this status |

Actual status codes depend on exception mapping and application configuration. Do not infer the root cause from a status code alone; read the response body, headers, and server logs when needed.

## 9. Checklist for clients

1. Obtain the item URI from the HAL `self` link or API contract.
2. Confirm the endpoint supports PATCH and the `application/json-patch+json` media type.
3. Construct a JSON array of valid operations in the exact desired order.
4. Use accurate JSON Pointers; remember to escape `~` as `~0` and `/` as `~1` in key names.
5. Use `test` or conditional requests when you need to constrain state before modifying.
6. Send `Content-Type: application/json-patch+json` and `Accept` matching the desired response.
7. Handle status codes and returned representations; do not blindly retry a patch that may not be idempotent.

JSON Patch provides a compact, ordered, and explicit way to express changes for HTTP PATCH. When combining proper JSON Pointers, media types, per-operation semantics, and concurrency control, clients can update Spring Data REST resources accurately without resending the entire entity.