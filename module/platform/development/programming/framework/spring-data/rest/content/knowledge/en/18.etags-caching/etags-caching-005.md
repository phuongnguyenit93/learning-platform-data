# If-None-Match for GET and the 304 Not Modified Response

## 1. What Is Conditional GET?

When a client calls GET to read a resource, the server normally returns 200 OK along with the representation and response headers. If the client has already stored that representation, re-downloading the entire body on every refresh can waste bandwidth, time, and device battery.

HTTP supports **conditional GET** so a client can ask the server whether the stored representation is still fresh. With ETags, the client sends the previously received value in the **If-None-Match** request header.

- If the current representation still matches the sent ETag, the server returns **304 Not Modified** without resending the body.
- If the representation has changed, the server returns **200 OK**, the new body, and a new ETag.

The client uses its stored body when receiving 304. This is an HTTP cache revalidation mechanism, not a type of response containing abbreviated data.

Spring Data REST supports checking If-None-Match when handling GET. If the header value matches the resource's current ETag, Spring Data REST returns 304 Not Modified instead of the full representation.

## 2. What Is an ETag?

An ETag (entity tag) is a server-provided validator identifying a representation version of a resource. This value is opaque to the client: the client stores and sends it back verbatim without parsing or fabricating the value.

Example response:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "7"

{
  "id": 42,
  "name": "Alice"
}
~~~~

In the example, "7" is the ETag issued by the server. The client must not strip quotation marks or alter the format when sending it back.

An ETag may be generated from a version, hash, or another internal mechanism. Under HTTP, the client only needs to compare the validator provided by the server; do not assume the ETag is always a hash of the JSON or always equals a database version number.

ETags typically come in one of two forms:

- **Strong ETag:** for example "abc123", indicating a strong validator for the representation.
- **Weak ETag:** for example W/"abc123", allowing weak comparison when the goal is cache validation and byte-for-byte identity is not required.

If-None-Match uses weak comparison under HTTP Semantics. Therefore, clients should preserve the header value as-is rather than manipulating the W/ prefix.

## 3. Generating ETag in Spring Data REST with @Version

Spring Data REST can generate an ETag from a domain object's version property. Current Spring Data REST documentation describes:

- With Spring Data JPA, use the JPA @Version annotation.
- With other Spring Data modules, use org.springframework.data.annotation.Version.

JPA entity example:

~~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @jakarta.persistence.Version
    private Long version;

    private String name;

    // getters/setters
}
~~~~

When Person is served as a REST resource, Spring Data REST can place the version value into the ETag response header. For example, a resource with version 7 can return:

~~~~http
ETag: "7"
~~~~

When the entity is updated successfully, the persistence provider/store manages the version according to its mechanism. The next GET will receive a new ETag if the version has changed.

With a non-JPA module, for example declaring the version using Spring Data Commons:

~~~~java
public class Person {

    @Id
    private String id;

    @org.springframework.data.annotation.Version
    private Long version;

    private String name;
}
~~~~

How the version is annotated and what the version means can vary by store. Spring Data REST relies on the store's metadata to recognize the version property. Use the right annotation for the deployed module and inspect actual responses to verify the ETag is emitted.

@Version can also support optimistic locking. However, the focus of this lesson is using the version as a validator for GET; conditional writes using If-Match are a related mechanism with a different purpose.

## 4. Sending the Initial GET to Obtain the ETag

The client starts with a normal GET request:

~~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/people/42
~~~~

Illustrative response:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "7"
Cache-Control: no-cache

{
  "id": 42,
  "name": "Alice"
}
~~~~

The client needs to store:

- The exact URI requested.
- Query parameters, if any.
- The representation or body received.
- The verbatim ETag.
- Necessary cache metadata such as Cache-Control, Date, Expires, and Vary.

Do not store only the ETag while discarding the body. If the server returns 304 next time, the client needs the cached representation to continue displaying the data.

## 5. Sending If-None-Match on the Next GET

When checking whether the resource has changed, the client sends back the ETag in the header:

~~~~bash
curl -i -H "Accept: application/hal+json" -H 'If-None-Match: "7"' http://localhost:8080/people/42
~~~~

If the representation still has the corresponding ETag, Spring Data REST returns the response:

~~~~http
HTTP/1.1 304 Not Modified
ETag: "7"
Cache-Control: no-cache
~~~~

A 304 response has no body. The client uses the body stored from the previous 200 response.

If the resource has changed and the current ETag differs from "7", the server returns the new representation:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "8"

{
  "id": 42,
  "name": "Alice Smith"
}
~~~~

The client replaces the old cached body and stores the new ETag "8" for future revalidation.

## 6. HTTP Rules for Evaluating If-None-Match

RFC 9110 defines If-None-Match as a request precondition. The header can contain a single ETag, a list of ETags, or the `*` character.

### Single ETag

~~~~http
If-None-Match: "7"
~~~~

For GET, if the selected representation's ETag matches the sent value under weak comparison, the server returns 304. If it does not match, the server continues processing the GET and returns the representation, typically 200.

### List of ETags

~~~~http
If-None-Match: "5", "7", W/"9"
~~~~

The server checks whether the current representation's ETag matches any tag in the list. If there is a match for GET, it returns 304.

### Wildcard

~~~~http
If-None-Match: *
~~~~

For GET, the wildcard matches when the resource has a current representation. If the resource exists, the server returns 304; if there is no current representation, the request is processed through the normal GET flow, typically returning 404 when the item does not exist.

### Distinguishing from If-Match

If-None-Match is typically used to revalidate caches. If-Match is typically used to protect write operations from updating on a stale version.

- GET + If-None-Match matching ETag: 304 Not Modified.
- PUT/PATCH/DELETE + If-Match mismatching: 412 Precondition Failed.
- For unsafe methods, If-None-Match has different semantics: if the condition fails, the server returns 412 instead of 304.

Do not use If-None-Match in place of If-Match when the goal is preventing lost updates.

## 7. What Does 304 Not Modified Mean?

304 Not Modified is a response to a conditional GET or HEAD indicating the server determined the client already holds a still-valid representation. The server does not resend the body to reduce transferred data.

Key points:

- 304 is not a redirect to another URL.
- 304 has no response body.
- The client must have a previously cached representation to reuse.
- The server may resend the ETag and necessary cache metadata so the client can update its cache entry.
- If the client has no cached body, receiving only 304 will not be enough to construct the resource content.

According to RFC 9110, a 304 response must carry the corresponding headers that a 200 response for the same request would send, as specified for ETag, Date, Vary, Cache-Control, Expires, and Content-Location when those headers apply.

Example response check:

~~~~bash
curl -i -H 'If-None-Match: "7"' http://localhost:8080/people/42
~~~~

If the result is 304, do not expect a JSON body in the response.

## 8. How ETag and Cache-Control Work Together

ETag is a validator to check whether a representation has changed. Cache-Control specifies how clients and intermediary caches are allowed to store, reuse, and revalidate the response.

Some common directives:

| Directive | Meaning |
|---|---|
| max-age=60 | Caches can use the response for 60 seconds without needing to ask the server again |
| no-cache | Response can be stored, but must be revalidated before reuse |
| no-store | Do not store the response in a cache |
| private | Only the client's private cache may store the response; shared caches must not use it |
| public | Allows shared caches to store the response if other caching conditions are also met |

Example:

~~~~http
Cache-Control: private, no-cache
ETag: "7"
~~~~

The client can store the response in its private cache, but needs to check with the server before reusing it. If the ETag still matches, the server returns 304 and the client uses the stored body.

Another example:

~~~~http
Cache-Control: public, max-age=60
ETag: "7"
~~~~

For 60 seconds, the cache can serve the fresh response without sending a request. Once the response loses freshness, the cache can send a conditional GET with If-None-Match to revalidate.

no-cache does not mean "do not store"; the directive forbids reuse without revalidation. no-store is the directive that instructs not to store the response.

For personal data or representations that depend on the current user, configure an appropriate cache policy, typically private or no-store depending on security requirements. Do not let a shared cache reuse one user's representation for another user.

Spring Data REST emitting an ETag does not mean the application already has the right Cache-Control policy. Cache headers need to be configured at the application, filter, gateway, or reverse proxy based on the data's characteristics.

## 9. Do Not Misuse ETags Across Different Requests

ETag identifies the validator of a selected representation. A representation can depend on the URI, query parameters, and content negotiation.

Example:

~~~~text
GET /people?active=true
GET /people?active=false
GET /people/42
~~~~

Do not take the ETag from the first request and send it for the second request. Those requests select different resources/representations.

Spring Data REST also notes not to mix validator values across queries. Use an ETag only for the exact URI and query parameters that produced it.

If the API supports multiple representations via Accept, such as HAL JSON and JSON, store cache entries and validators per corresponding representation. The Vary header tells caches which request headers affect the selected representation. Do not assume one ETag can be shared across all media types.

For collection resources with paging or filtering, each URI with different page, size, sort, and filter parameters must be treated as a separate cache key.

## 10. If-Modified-Since as a Time-Based Option

Spring Data REST also supports time-based conditional GET through Last-Modified and If-Modified-Since.

A domain type can use Spring Data auditing:

~~~~java
@Document
public class Receipt {

    @Id
    private String id;

    @Version
    private Long version;

    @LastModifiedDate
    private Instant lastModifiedDate;

    private String saleItem;
}
~~~~

When auditing is configured and the last-modified field is updated, Spring Data REST can return:

~~~~http
Last-Modified: Wed, 24 Jun 2026 20:28:15 GMT
~~~~

The client sends back the received date:

~~~~bash
curl -i -H 'If-Modified-Since: Wed, 24 Jun 2026 20:28:15 GMT' http://localhost:8080/receipts/42
~~~~

If the resource has not been modified after that timestamp, the server can return 304. If it has changed, the server returns 200 along with the new representation and new Last-Modified.

ETag is usually more accurate than a date validator because Last-Modified has one-second resolution and may not distinguish multiple changes occurring within the same second.

If a request includes both If-None-Match and If-Modified-Since, RFC 9110 requires the server to prioritize If-None-Match and ignore If-Modified-Since. Prefer ETag for cache validation when the API provides it.

## 11. Client-Side Cache Revalidation Workflow

A client can implement the following workflow:

1. Send GET with the appropriate URI and Accept header.
2. When receiving 200, store the body, ETag, and cache metadata.
3. While the response is still fresh per Cache-Control, reuse the cached body without sending a request.
4. When revalidation is needed, send GET with the same URI/query/representation and add If-None-Match with the stored ETag.
5. If receiving 304, keep the body and update cache metadata according to the response.
6. If receiving 200, replace the body and ETag with the new values.
7. If receiving 404, handle the deleted or nonexistent resource according to the API contract.
8. If the request encounters a network error, decide whether to use stale cache or report an error per application policy.

Pseudo-code:

~~~~java
CachedResponse cached = cache.get(cacheKey);

HttpRequest.Builder request = HttpRequest.newBuilder(uri)
        .header("Accept", "application/hal+json")
        .GET();

if (cached != null && cached.etag() != null) {
    request.header("If-None-Match", cached.etag());
}

HttpResponse<String> response = client.send(
        request.build(),
        HttpResponse.BodyHandlers.ofString()
);

if (response.statusCode() == 304 && cached != null) {
    return cached.body();
}

if (response.statusCode() == 200) {
    String etag = response.headers()
            .firstValue("ETag")
            .orElse(null);

    cache.put(cacheKey, new CachedResponse(
            response.body(),
            etag,
            response.headers()
    ));

    return response.body();
}

throw new IllegalStateException(
        "Unexpected HTTP status: " + response.statusCode()
);
~~~~

This is illustrative pseudo-code. A real HTTP client or caching library may manage caching, freshness, and revalidation automatically. If implementing it manually, you also need to handle redirects, authorization, Vary, network errors, response bodies, and other statuses.

## 12. Testing If-None-Match with Spring Data REST

You should test through actual HTTP endpoints rather than only unit testing a version comparison function.

### Manual testing with curl

First request:

~~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/people/42
~~~~

Record the ETag from the 200 response. Then resend to the exact same URI:

~~~~bash
curl -i -H "Accept: application/hal+json" -H 'If-None-Match: "7"' http://localhost:8080/people/42
~~~~

When the resource has not changed, verify:

- Status is 304.
- Response has no body.
- ETag/cache metadata are returned appropriately.
- The client can use the cached body from the first GET.

Modify the entity via a valid update request, then resend the old ETag. The server should return the new representation with 200 if the version/ETag has changed.

### Integration testing with MockMvc

Example:

~~~~java
MvcResult firstResponse = mockMvc.perform(
        get("/people/{id}", 42L)
            .accept(MediaType.parseMediaType("application/hal+json"))
    )
    .andExpect(status().isOk())
    .andReturn();

String etag = firstResponse.getResponse()
        .getHeader(HttpHeaders.ETAG);

assertThat(etag).isNotNull();

mockMvc.perform(
        get("/people/{id}", 42L)
            .accept(MediaType.parseMediaType("application/hal+json"))
            .header(HttpHeaders.IF_NONE_MATCH, etag)
    )
    .andExpect(status().isNotModified())
    .andExpect(content().string(""));
~~~~

This test requires a repository resource with appropriate version metadata and an ETag emitted by Spring Data REST. If there is no ETag, check the version annotation, store module, persistence mapping, and endpoint configuration before concluding conditional GET does not work.

Additional test cases should be added for:

- Matching ETag: returns 304.
- Old ETag after an update: returns 200 and a new ETag.
- List of ETags with one matching value: returns 304.
- Wildcard with an existing resource: verify HTTP semantics.
- Different URI or query parameters: do not reuse the ETag from the previous request.
- Different representation via Accept: check cache key and Vary.
- Nonexistent resource: handle 404 per contract.
- 304 response contains no body.

## 13. Common Errors

| Symptom | Possible cause | How to resolve |
|---|---|---|
| GET always returns 200 even though ETag has not changed | Request does not send If-None-Match, endpoint does not support validators, or ETag is not generated | Check request headers and version metadata |
| Response has no ETag | Domain type is missing a version field or store does not recognize version metadata | Use the right @Version annotation for the module and inspect responses |
| Sent ETag but received 200 | ETag does not match selected representation, resource changed, or sent to wrong URI/query | Store ETag verbatim and use the right request key |
| Received 304 but UI has no data | Client did not store the body from the previous 200 response | Store the body along with the ETag |
| Used collection ETag for item | Cache key/validator mixed across different URIs | Store validators per specific URI and query |
| 304 response still has a body | Proxy, custom handler, or test setup violates the response contract | Inspect responses at origin and intermediaries |
| Cache shows another user's data | Cache-Control/Vary inappropriate for user-dependent data | Use private/no-store and configure safe caching |
| Last-Modified misses some rapid changes | Timestamp resolution is in seconds | Prefer ETag |
| ETag does not change after updating an association | Version metadata does not reflect every representation change | Review aggregate/version strategy or use a representation-appropriate validator |

## 14. Conclusion

If-None-Match lets clients perform conditional GETs by sending a previously received ETag. If the ETag matches the current representation, Spring Data REST returns 304 Not Modified and omits the body; if the resource has changed, the server returns 200 OK, the new representation, and a new ETag.

In Spring Data REST, a store-appropriate @Version field can be used to generate the ETag. Clients must store the ETag with the body, reuse it for the exact URI and query, understand that 304 has no body, and update cache metadata per the response. Cache-Control determines how responses are stored and reused; If-Modified-Since is a time-based option when Last-Modified is available. Test the initial GET, unchanged revalidation, and modified-resource cases.

## References

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
- [RFC 9110 — HTTP Semantics, If-None-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.2)
- [RFC 9110 — HTTP Semantics, 304 Not Modified](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4.5)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [MDN — If-None-Match](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-None-Match)
- [MDN — 304 Not Modified](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/304)