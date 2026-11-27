# HEAD to Check Resources and Read Headers

## Objectives

In Spring Data REST, `HEAD` allows a client to inspect a resource and read response metadata without receiving a representation body. This is useful for checking whether an endpoint or item exists, reading caching and content negotiation information, or deciding whether it is necessary to fetch the content with `GET`.

Key point: **HEAD has the same semantics as GET on the same URI, except the response has no body**. Therefore, the client can read the status and headers, but cannot rely on HEAD to inspect JSON/HAL, business data, `_links`, or `_embedded`.

## 1. How does HEAD work?

According to HTTP, HEAD asks the server to return metadata identical to the GET response for the same resource, but omits the message body.

Example:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

GET might return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "person-42-v3"
Cache-Control: private, max-age=60

{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people/42"
    }
  }
}
~~~

A HEAD request to the same URI might return:

~~~http
HEAD /api/people/42
Accept: application/hal+json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "person-42-v3"
Cache-Control: private, max-age=60
~~~

The HEAD response does not contain a JSON body. The exact headers depend on the server, configuration, and resource; the example above only illustrates a response with an ETag and cache policy.

HEAD is a **safe** and **idempotent** method in HTTP:

- Safe: the request is intended to read state, not ask the server to modify business data.
- Idempotent: repeating the same request does not alter the business outcome caused by the request.

HEAD is not a command to delete, create, or update a resource. If the goal is to modify data, use an appropriate method such as POST, PUT, PATCH, or DELETE.

## 2. HEAD in Spring Data REST

Spring Data REST exposes repository resources by resource type. Collection and item endpoints typically support HEAD alongside their corresponding read operations.

Suppose the Person repository is exported at `/api/people`.

| Resource type | Request | Purpose |
|---|---|---|
| Collection | `HEAD /api/people` | Check the collection endpoint and read headers |
| Item | `HEAD /api/people/42` | Check item 42 and read headers |
| Collection | `GET /api/people` | Read the collection representation |
| Item | `GET /api/people/42` | Read the item representation |

HEAD example for a collection:

~~~http
HEAD /api/people?page=0&size=20
Accept: application/hal+json
~~~

HEAD example for an item:

~~~http
HEAD /api/people/42
Accept: application/hal+json
~~~

For standard repository resources, Spring Data REST handles HEAD according to the read capabilities of the collection or item. In Spring MVC, HEAD may be handled through the same processing flow as GET, with the body stripped when generating the response. Therefore, **you should not assume HEAD is always cheaper than GET or guaranteed not to query the repository**. The server may still need to look up data to determine whether the item exists, produce the status, compute validators, or generate the corresponding headers.

The paths and base path in the examples depend on configuration. If the application does not use `/api`, use the actual URIs exposed by the API.

## 3. What does HEAD tell you?

HEAD helps clients read information contained in the status line and response headers.

| Information | How it is used |
|---|---|
| Status code | Indicates whether the request succeeded, the resource does not exist, was denied, or does not support the method |
| `Content-Type` | Indicates the representation type the corresponding GET would return, if provided by the server |
| `Content-Length` | If present, usually describes the body length of the corresponding GET response; the server may omit it if unknown or not computed |
| `ETag` | Validator for comparing representation versions |
| `Last-Modified` | Time the resource/representation was last modified, if provided by the server |
| `Cache-Control` | Cache policy such as `private`, `no-store`, `max-age` |
| `Vary` | Tells caches which request headers may alter the representation |
| `Content-Language` | Language of the representation, if provided |

Not every Spring Data REST application returns all of these headers. For example, ETag and Last-Modified are only meaningful when the server or infrastructure layer configures appropriate validators. Do not write clients that assume a header is always present; check for its presence before using it.

### 3.1. Content-Type still matters even without a body

A client can send:

~~~http
Accept: application/hal+json
~~~

If the server supports HAL JSON, the HEAD response may include:

~~~http
Content-Type: application/hal+json
~~~

This header indicates the representation format of the corresponding GET. However, the client still receives no JSON to parse. To read business fields or hypermedia links, the client must call GET.

If the Accept value is not supported by the server, the request may receive `406 Not Acceptable`. Thus, HEAD still participates in content negotiation.

### 3.2. Content-Length is not always present

In HTTP semantics, if the server sends Content-Length for HEAD, that value describes the body length the corresponding GET would return, not the HEAD body length (since the HEAD body is 0 bytes). However, the server may omit Content-Length when it cannot determine the value without generating the body.

Therefore:

- Do not use the absence of Content-Length to conclude the resource does not exist.
- Do not interpret Content-Length on a HEAD response as the actual number of bytes transferred in the HEAD response.
- If you need to know the actual payload size, inspect the headers and behavior of the specific endpoint; HEAD does not guarantee the server will always provide the size.

## 4. Distinguishing collection existence from item existence

An important difference is that a collection endpoint can exist even when the collection has no elements.

Example:

~~~http
HEAD /api/people
~~~

If the collection endpoint is exported and accessible, the server may return `200 OK` even when the repository currently contains no Person records.

Meanwhile:

~~~http
HEAD /api/people/999999
~~~

If there is no item with that ID, the server typically returns `404 Not Found`.

You can interpret the results as follows:

| Response | Interpretation |
|---|---|
| `200 OK` for collection | Collection endpoint is accessible; does not prove the collection has elements |
| `200 OK` for item | Item resource was found and is accessible |
| `404 Not Found` for item | Item was not found at that URI, or the server does not disclose its existence |
| `401 Unauthorized` | Missing or invalid authentication credentials |
| `403 Forbidden` | Caller does not have permission to perform the request |
| `405 Method Not Allowed` | Resource does not support HEAD under the current configuration |
| `406 Not Acceptable` | No representation matches Accept |
| `5xx` | Server or infrastructure encountered an error |

HEAD does not tell you how many elements a collection has, because the response body containing the list and pagination metadata is omitted. If you need the count or want to inspect the items, call collection GET.

## 5. HEAD and cache validator headers

HEAD is often useful when a client works with caching. Two common validators are ETag and Last-Modified.

### 5.1. ETag and If-None-Match

The server might return:

~~~http
HTTP/1.1 200 OK
ETag: "people-42-v5"
~~~

The client stores that ETag. On the next check, the client sends:

~~~http
HEAD /api/people/42
If-None-Match: "people-42-v5"
Accept: application/hal+json
~~~

If the representation still matches the sent validator, the server may return:

~~~http
HTTP/1.1 304 Not Modified
ETag: "people-42-v5"
~~~

`304 Not Modified` indicates the representation has not changed according to the validator provided by the client; the client can continue using its cached copy if still valid under the cache policy. A 304 response also has no body.

If the representation has changed, the server typically returns the current HEAD response status (such as 200) along with the new validator if available.

### 5.2. Last-Modified and If-Modified-Since

If the server exposes Last-Modified:

~~~http
Last-Modified: Tue, 10 Nov 2026 08:30:00 GMT
~~~

The client can send:

~~~http
HEAD /api/people/42
If-Modified-Since: Tue, 10 Nov 2026 08:30:00 GMT
~~~

If the resource has not changed since that time, the server may return 304. If it has changed, the server returns a new HEAD response with the corresponding headers.

ETag is usually a more accurate validator when the server can produce a reliable version token. Last-Modified has time resolution and accuracy dependent on the data source. Do not fabricate or compare validators by guesswork; use the values returned by the server.

Note: conditional requests only take effect when the server or the application's web/cache layer supports validators. Not every Spring Data REST endpoint automatically provides ETag or Last-Modified.

## 6. Testing examples with curl

The `curl -I` command sends a HEAD request and displays response headers.

Check a collection:

~~~bash
curl -I \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people
~~~

Check an item:

~~~bash
curl -I \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42
~~~

Inspect detailed request/response exchange:

~~~bash
curl -v -I \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42
~~~

Compare HEAD and GET:

~~~bash
# HEAD: receives only status and headers
curl -I -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42

# GET: receives status, headers, and HAL body
curl -i -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/42
~~~

If the API requires authentication, add the appropriate Authorization header:

~~~bash
curl -I \
  -H "Accept: application/hal+json" \
  -H "Authorization: Bearer <access-token>" \
  https://localhost:8080/api/people/42
~~~

Do not record real tokens in documentation, shared logs, or shared shell history. The example above uses a placeholder.

When reading the output, look at the status code first, then inspect Content-Type, ETag, Last-Modified, Cache-Control, and other headers. Do not look for a JSON body in a HEAD response.

## 7. Testing HEAD in integration tests

In a Spring MVC application, you can test the endpoint with MockMvc:

~~~java
mockMvc.perform(
        head("/api/people/42")
            .accept("application/hal+json")
    )
    .andExpect(status().isOk())
    .andExpect(content().string(""));
~~~

The test above verifies that the item is accessible and the response contains no body. You can also test the non-existent item case:

~~~java
mockMvc.perform(
        head("/api/people/999999")
            .accept("application/hal+json")
    )
    .andExpect(status().isNotFound())
    .andExpect(content().string(""));
~~~

The exact status also depends on how the application handles errors and security. If the API intentionally hides the existence of a resource, an unauthorized request may receive 404 instead of 403.

Do not assert ETag or Last-Modified in every test if the application has not configured them. When you want to test validators, explicitly configure the validator-generating layer before asserting the corresponding headers.

## 8. HEAD does not replace GET or OPTIONS

The three methods serve different purposes:

| Method | Purpose | Typically has a response body? |
|---|---|---|
| HEAD | Read metadata equivalent to GET, check resource | No |
| GET | Read the resource representation | May have one |
| OPTIONS | Discover communication options/methods supported at the target resource | May have no body or a body depending on the server |

Use HEAD when you only need status and headers. Use GET when you need business data, HAL links, embedded resources, or pagination metadata in the body. Use OPTIONS when you want to discover supported methods; the Allow header is typically associated with advertising valid methods, and you should not infer the list of supported methods from a HEAD response alone.

A successful HEAD also does not prove that other operations such as POST, PUT, PATCH, or DELETE are enabled. Each operation depends on exported repository methods, Spring Data REST configuration, and access permissions.

## 9. Common misconceptions

- **HEAD does not return abbreviated JSON.** It returns no body; to view partial data, use GET or an appropriate projection.
- **HEAD does not guarantee no database query.** The server may run read logic similar to GET to locate the resource and build headers.
- **HEAD 200 on a collection does not prove the collection has data.** It only indicates the collection endpoint is accessible.
- **HEAD does not provide the total element count if that information only lives in the body.** Use collection GET if you need pagination metadata.
- **Missing Content-Length does not mean the resource does not exist.** The header may be omitted.
- **Not every endpoint has ETag or Last-Modified.** Only rely on validators when the server actually provides them and supports conditional requests.
- **HEAD does not replace OPTIONS.** HEAD inspects representation metadata; OPTIONS is for discovering communication capabilities.
- **HEAD still needs protection.** If a user is not permitted to know a resource exists, the HEAD status itself can leak information.

## 10. Debugging workflow for a HEAD request

When HEAD returns an unexpected result, check in order:

1. **URI:** Does the path match the collection path or item URI exposed by the API?
2. **Method:** Does the endpoint support HEAD? If you receive 405, check mappings and exposure configuration.
3. **Authentication:** Is the authentication header valid? Do security rules apply to HEAD?
4. **Authorization:** Does the caller have permission to read the resource? Some APIs intentionally use 404 to hide resources.
5. **Accept:** Did the client request a supported media type, such as `application/hal+json`?
6. **Status:** Distinguish 200, 304, 404, 405, 406, and 4xx/5xx errors.
7. **Headers:** Inspect Content-Type, ETag, Last-Modified, Cache-Control, and Vary if present.
8. **Cross-check with GET:** If you need to verify business fields or links, send GET to the same URI with the same Accept header and credentials.

HEAD enables fast resource inspection from an HTTP perspective. When you need to understand content or hypermedia structure, GET remains the operation to use.

## 11. Key takeaways

- HEAD corresponds to GET on the same URI but without a response body.
- Spring Data REST supports HEAD for standard repository resources such as collections and items.
- The status code helps determine whether the request succeeded, the item does not exist, the method is unsupported, or access was denied.
- Response headers may provide Content-Type, Content-Length, ETag, Last-Modified, and cache policies; individual headers depend on the server.
- Conditional HEAD can use If-None-Match or If-Modified-Since to receive 304 when the representation is unchanged.
- HEAD does not prove a collection has elements, does not return a HAL body, and does not guarantee avoiding a repository query.
- Use GET to read data, HEAD to inspect metadata, and OPTIONS to discover communication options.

## References

- [RFC 9110 — HTTP Semantics, HEAD](https://www.rfc-editor.org/rfc/rfc9110.html#name-head)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Framework — HTTP HEAD support](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
