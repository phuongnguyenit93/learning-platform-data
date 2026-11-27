# Storing ETags by Exact URI, Parameters, and Requested Representation

An ETag is a validator returned by the server to identify a version of a representation. The client can store the ETag along with the received data, resend the validator in a subsequent request to check whether the data has changed, or use it to protect update operations from overwriting changes made by another client.

With Spring Data REST, the ETag is typically tied to the entity's version property. However, an ETag received from a specific URI or query should only be reused within that exact request context. Do not store an ETag keyed solely by entity id and share it across all projections, filters, pages, or media types.

## 1. What Does an ETag Represent?

The server sends an ETag in a response header:

~~~http
HTTP/1.1 200 OK
ETag: "7"
Content-Type: application/hal+json
Cache-Control: private, no-cache
~~~

The ETag value is an opaque validator: the client stores and sends it back verbatim without needing to know whether the server generated it from a version number, a content hash, or another internal mechanism. An ETag can be a strong tag like "7" or a weak tag like W/"abc". The quotation marks and the W/ prefix are part of the value.

In Spring Data REST, an entity with a version field annotated with @Version can emit an ETag carrying that field's value. With Spring Data JPA, use jakarta.persistence.Version; with other Spring Data modules, use org.springframework.data.annotation.Version.

JPA entity example:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
class Order {

    @Id
    private Long id;

    private String status;

    @Version
    private Long version;

    protected Order() {
    }
}
~~~

When a repository exposes this entity as a REST resource, Spring Data REST can use the version field as the ETag. After a successful update, the version changes and a new ETag is returned. If an entity lacks appropriate version metadata, do not assume every endpoint emits an ETag; inspect actual responses.

ETags serve two related but distinct goals:

- Cache validation: determining whether the stored representation is still fresh or needs to be re-fetched.
- Optimistic locking: determining whether the client is updating based on the latest version or using stale data.

## 2. The Cache Key Must Include the Exact URI and Parameters

A resource id is not sufficient to identify a representation in a cache. The same entity can be queried via multiple different URIs or queries, and each result can have different content.

Example:

| Request | Representation context |
|---|---|
| GET /orders/42 | Default resource |
| GET /orders/42?projection=summary | Summary projection |
| GET /orders/42?projection=detail | Detail projection |
| GET /orders?status=OPEN&page=0&size=20 | First page of open orders |
| GET /orders?status=CLOSED&page=0&size=20 | First page of closed orders |
| GET /orders?status=OPEN&page=1&size=20 | Next page of the same result set |

Do not share ETags across these requests. A change in filter, projection, pagination, sorting, or other parameters can change the selected representation. Spring Data REST requires using an ETag only for the exact URI and parameters that generated that ETag.

**A minimal cache key** needs to distinguish:

1. The appropriate HTTP method, typically GET or HEAD.
2. The full URI, including the path and entire query string.
3. The media type requested by the client via Accept.
4. Any request headers listed by the server in Vary.
5. User or tenant scope if data depends on access identity.

Do not strip the query string from the cache key. Do not drop parameters with default values, collapse duplicate parameters, or reorder query parameters to form a shared key unless the API contract explicitly defines those URIs as equivalent. Keep the exact URL that the client actually sends.

## 3. Representation Is Also Part of the Cache Key

The same URI can return different representations depending on content negotiation. Example:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

and:

~~~http
GET /orders/42
Accept: application/json
~~~

The client is requesting two different formats. When storing the ETag, store it alongside the corresponding Accept value. If the server returns a Vary header, you must distinguish values of the request headers listed in Vary.

Example response:

~~~http
Vary: Accept, Accept-Language
ETag: "7"
~~~

In that case, two requests can share a cache entry only if the URI, query parameters, Accept, and Accept-Language all match. If the response has `Vary: *`, do not use that entry to satisfy any other request.

In Spring Data REST, projections via query parameters such as projection=summary must also be included in the key. Do not rely on two representations pointing to the same entity to reuse a validator.

If a response depends on the logged-in user, tenant, permissions, or cookies, the cache must be partitioned by that exact scope. Do not share one user's body or ETag with another user. Respect the server's Cache-Control; in particular, do not store responses with no-store.

## 4. Store the ETag Together with the Response Body

An ETag does not replace the downloaded data. When the server returns 304 Not Modified, the response normally has no body; the client must retrieve the body from the cache entry matching the request being checked.

Therefore, each entry must hold at minimum:

- The request's cache key.
- The verbatim received ETag.
- The received response body.
- Necessary cache metadata such as Cache-Control, Vary, and response receipt time.

Workflow:

1. Send GET with the desired URI, query parameters, and representation.
2. On receiving 200 OK, store the body and ETag under the same cache key.
3. When calling the exact same request again, send If-None-Match with the stored ETag.
4. On receiving 304 Not Modified, reuse the body in the matching cache entry; update response metadata if present.
5. On receiving 200 OK, replace the old body and ETag with the new data.
6. If the new response no longer has an ETag, do not continue using the old validator as if it were still valid for the new body.

Example cache structure in JavaScript:

~~~javascript
const responseCache = new Map();

function makeCacheKey(url, accept, acceptLanguage = "") {
    const fullUrl = new URL(url, window.location.href).href;

    return JSON.stringify({
        method: "GET",
        url: fullUrl,
        accept,
        acceptLanguage
    });
}

async function getOrder(url) {
    const accept = "application/hal+json";
    const acceptLanguage = "vi";
    const key = makeCacheKey(url, accept, acceptLanguage);
    const cached = responseCache.get(key);

    const headers = new Headers({
        Accept: accept,
        "Accept-Language": acceptLanguage
    });

    if (cached?.etag) {
        headers.set("If-None-Match", cached.etag);
    }

    const response = await fetch(url, {
        method: "GET",
        headers,
        credentials: "same-origin"
    });

    if (response.status === 304) {
        if (!cached) {
            throw new Error("304 received without a matching cached body");
        }

        return cached.body;
    }

    if (!response.ok) {
        throw new Error("GET failed: " + response.status);
    }

    const body = await response.json();
    const etag = response.headers.get("ETag");
    const cacheControl = response.headers.get("Cache-Control") || "";

    if (cacheControl.toLowerCase().includes("no-store")) {
        responseCache.delete(key);
    } else if (etag) {
        responseCache.set(key, {
            etag,
            body,
            cacheControl,
            vary: response.headers.get("Vary")
        });
    } else {
        responseCache.delete(key);
    }

    return body;
}
~~~

This example uses an in-memory cache and distinguishes the full URI, Accept, and Accept-Language. If an endpoint has additional headers affecting the representation, the values of those headers must be included in the key per the response's Vary header. If the application has multiple users or tenants, use separate caches per session/identity; do not put raw access tokens into the key.

This code always sends the validator when an entry exists, making it suitable to illustrate revalidation. A production cache also needs to handle freshness via max-age, expiry, invalidation after writes, and application-specific policies. With no-cache, the response may be stored but must be revalidated before reuse; with no-store, do not store the body or validator.

## 5. If-None-Match: Checking the Cache on Read

If-None-Match is used primarily with GET or HEAD. The client sends the stored ETag for the exact request:

~~~http
GET /orders/42?projection=detail
Accept: application/hal+json
If-None-Match: "7"
~~~

If the selected representation still matches the validator, the server returns:

~~~http
HTTP/1.1 304 Not Modified
ETag: "7"
~~~

304 indicates the client can use the stored representation; there is no new body to replace the old one. If the representation has changed, the server returns 200 OK with the new body and ETag.

Do not handle 304 as a normal JSON response. If there is no cached body matching the exact URI, parameters, and representation, the client has no data to reuse. Issue an unconditional GET to fetch the full representation.

If-None-Match supports weak comparison under HTTP semantics. Therefore, clients should not manually compare ETag strings by stripping the W/ prefix or removing quotation marks.

## 6. If-Match: Protecting Update Operations

When a client reads an entity and wants to update it, it can send the exact resource's ETag in If-Match:

~~~http
PATCH /orders/42
Content-Type: application/json
Accept: application/hal+json
If-Match: "7"

{"status":"SHIPPED"}
~~~

Spring Data REST executes the operation only when the resource's current ETag matches the sent validator. If another client updated the resource and changed the version, the old ETag no longer matches; the server returns HTTP 412 Precondition Failed.

Scenario:

1. Client A reads Order 42 and receives ETag "7".
2. Client B updates Order 42; the server issues a new ETag, for example "8".
3. Client A sends PATCH with If-Match: "7".
4. The server rejects the operation with 412 because A's data is stale.

When encountering 412:

- Do not automatically resend the PATCH/PUT content with the new ETag without reading the current data.
- Re-GET the exact resource to obtain the latest state.
- Compare the client's changes with the current data.
- Resolve the conflict according to business rules before sending the next update operation.

If-Match uses strong comparison. A weak ETag with a W/ prefix is unsuitable as a validator for this condition. Use the exact ETag returned by the server and verify actual responses.

For update operations, obtain the validator from the resource URI that the client will update. If only a projection or another query was read earlier, do not transfer that ETag to the write URI. GET the exact resource URI per the API contract to obtain the appropriate validator.

## 7. Cache-Control Determines Whether Caching Is Allowed

ETag only provides a validator. It does not by itself grant permission to store a response or specify how long a response may be reused. Read Cache-Control:

| Directive | Meaning for client caches |
|---|---|
| max-age=N | The response can be reused for N seconds while still fresh |
| no-cache | Can be stored, but must be rechecked with the server before reuse |
| no-store | Do not store the response or validator in cache |
| private | Client private cache only; shared caches must not reuse under this policy |
| public | Allows shared caches to store when other HTTP conditions are met |

Example:

~~~http
Cache-Control: private, no-cache
ETag: "7"
~~~

The client can keep the body and ETag in a private cache, but must revalidate before reusing it.

~~~http
Cache-Control: no-store
~~~

Do not store the body or ETag. Do not ignore no-store simply because an ETag is present.

When receiving 304, update the cache entry's metadata according to the headers present in the response while keeping the old body. When receiving 200, replace the body and validator with the new pair. When the response has no-store, delete the corresponding entry.

## 8. Testing Examples with curl

**Read one exact representation:**

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/orders/42?projection=detail"
~~~

Extract the ETag value verbatim from the response header.

**Revalidate the exact URI and query parameters:**

~~~bash
curl -i -H "Accept: application/hal+json" -H 'If-None-Match: "7"' "http://localhost:8080/orders/42?projection=detail"
~~~

If the data has not changed, the server can return 304. Do not alter the URI or projection in this request.

**Try a different projection:**

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/orders/42?projection=summary"
~~~

This is a different cache entry from the detail projection. Do not take the ETag of the detail projection and send it for the summary request.

**Conditional update:**

~~~bash
curl -i -X PATCH "http://localhost:8080/orders/42" -H "Content-Type: application/json" -H "Accept: application/hal+json" -H 'If-Match: "7"' -d '{"status":"SHIPPED"}'
~~~

If the current ETag is still "7", the operation can succeed and the response returns a new ETag. If the version has changed, handle HTTP 412 by re-reading and resolving the conflict.

The URIs, entities, and ETag values in the examples are illustrative. Use actual endpoints and validators from the application's responses.

## 9. Common Errors and Resolutions

| Error | Cause | Resolution |
|---|---|---|
| Using ETag of /orders/42 for /orders/42?projection=detail | The two URIs select different representations | Store ETags per individual URI and query string |
| Using ETag of page 0 for page 1 | Paginated results differ | Include page, size, sort, and filters in the key |
| Using HAL JSON ETag for another JSON representation | Accept headers differ | Separate caches by media type and Vary |
| Storing only ETag without storing the body | 304 does not contain the new representation | Store body and validator as one entry |
| Receiving 304 but the cache entry was lost | The validator is no longer paired with a corresponding body | Perform an unconditional GET to fetch the new body |
| Encountering 412 on PATCH/PUT | Stale ETag because another client updated | Re-GET, reconcile, and resolve the conflict |
| ETag does not appear in JavaScript | CORS does not expose the response header | Configure Access-Control-Expose-Headers: ETag |
| Request with If-None-Match or If-Match blocked by CORS | Server has not allowed custom request headers | Allow these headers in Access-Control-Allow-Headers |
| Serving another user's cache | Cache is not partitioned by identity or tenant | Use a private per-session cache and obey Cache-Control |

For applications calling cross-origin APIs, JavaScript can read the ETag only when the server exposes that header via CORS. If sending If-None-Match or If-Match, the CORS configuration must allow the corresponding request headers. Exposing ETag does not replace access-control checks or cache policies.

## 10. Implementation Checklist

- [ ] Confirm the endpoint actually returns an ETag.
- [ ] If using Spring Data REST optimistic locking, annotate the version property with the right `@Version` for the persistence type.
- [ ] Store the ETag together with the response body.
- [ ] Preserve the full URI and all query parameters in the cache key.
- [ ] Distinguish Accept and every request header present in Vary.
- [ ] Partition caches by user/tenant when data has private scope.
- [ ] Obey Cache-Control, especially no-store and no-cache.
- [ ] Send If-None-Match only with the validator of the exact request representation.
- [ ] Use If-Match for write operations when the API supports optimistic locking.
- [ ] Handle 304 using the stored body and handle 412 with a re-read and reconciliation flow.
- [ ] Replace the body and ETag after a new 200 response; remove the entry when a response lacks an appropriate validator or specifies no-store.

## References

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): @Version, ETag, If-Match, If-None-Match, HTTP 304/412, and the rule of reusing ETags only for the exact URI with matching parameters.
- [RFC 9110 — HTTP Semantics, ETag](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.8.3): ETag as an opaque validator for the selected representation; weak and strong entity tags.
- [RFC 9110 — If-None-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.2): GET/HEAD conditionals and weak comparison.
- [RFC 9110 — Vary](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.5): request headers to distinguish in the cache key.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): freshness, validation, and how caches reuse responses.
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): Cache-Control, ETag, and 304 responses in Spring.