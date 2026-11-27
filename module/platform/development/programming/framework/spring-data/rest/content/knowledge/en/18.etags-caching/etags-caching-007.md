# If-Modified-Since and Checking Modification Time in Spring Data REST

Spring Data REST supports conditional GET via the HTTP `Last-Modified` and `If-Modified-Since` headers. This mechanism lets a client ask the server whether a resource has changed since the previous read. If it has not changed, the server can return `304 Not Modified` and omit the response body, reducing bandwidth and transfer time.

For Spring Data REST to know an entity's modification time, the domain type needs a property annotated with `@LastModifiedDate` and auditing must be enabled. The client stores the received `Last-Modified` value and sends it back in `If-Modified-Since` when requesting the exact same resource.

## 1. How Do Last-Modified and If-Modified-Since Work?

The two headers form a time-based cache validation mechanism:

- **`Last-Modified`** is a response header indicating when the resource was last modified according to server data.
- **`If-Modified-Since`** is a request header indicating the timestamp of the client's previously held representation.
- If the resource was modified after the timestamp sent by the client, the server returns the new representation, typically with HTTP `200 OK` and a new `Last-Modified` value.
- If the resource has not been modified after that timestamp, the server returns HTTP `304 Not Modified` without resending the representation in the response body.

Example initial response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Wed, 11 Nov 2026 02:30:00 GMT

{
  "id": 42,
  "name": "An Nguyen"
}
~~~

The client stores the header value:

~~~text
Wed, 11 Nov 2026 02:30:00 GMT
~~~

On the next read, the client sends:

~~~http
GET /people/42
If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT
Accept: application/hal+json
~~~

If the resource has not changed since that time, the response can be:

~~~http
HTTP/1.1 304 Not Modified
~~~

The client keeps its cached representation and does not need to re-download the content.

## 2. Configuring @LastModifiedDate for Domain Entities

Spring Data Commons provides the `@LastModifiedDate` annotation to store when an entity was most recently modified. Spring Data REST uses this metadata to produce the `Last-Modified` response header.

Example with Spring Data JPA:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @LastModifiedDate
    private Instant lastModifiedDate;

    // getters and setters
}
~~~

Key components:

- `@LastModifiedDate` marks the property storing the most recent modification time.
- `Instant` represents a point on the UTC timeline, suitable for audit data.
- `@EntityListeners(AuditingEntityListener.class)` connects the entity to Spring Data JPA's auditing listener.
- The auditing infrastructure updates the property when the entity is created or modified according to the corresponding persistence lifecycle.

The property name does not have to be `lastModifiedDate`, though it should be named clearly and use a data type supported by Spring Data auditing.

## 3. Enabling Auditing in Spring Data JPA

Simply adding `@LastModifiedDate` to the entity is not enough. The application needs to enable auditing so Spring Data registers the metadata update mechanism.

Example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

If the application uses Spring Boot, this configuration class must be within component scan scope or imported into the ApplicationContext.

With other Spring Data modules, use that module's corresponding auditing configuration, such as `@EnableMongoAuditing` for MongoDB. Do not apply JPA `AuditingEntityListener` across all stores.

You can combine `@CreatedDate` and `@LastModifiedDate` if both creation and modification times need to be stored:

~~~java
@CreatedDate
private Instant createdDate;

@LastModifiedDate
private Instant lastModifiedDate;
~~~

If only tracking timestamps, the application is not required to implement `AuditorAware`. That interface is only needed when recording who created or modified the entity via `@CreatedBy` and `@LastModifiedBy`.

## 4. Spring Data REST Returning Last-Modified

When a repository exposes an entity with a `@LastModifiedDate` property, Spring Data REST can include that timestamp in the `Last-Modified` response header of the item resource.

Example request:

~~~http
GET /people/42
Accept: application/hal+json
~~~

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Wed, 11 Nov 2026 02:30:00 GMT
ETag: "7"

{
  "id": 42,
  "name": "An Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

The `Last-Modified` header uses the HTTP-date format and expresses time in GMT. The example above illustrates the response structure; the ETag value appears only when the entity and configuration support the ETag mechanism.

Clients should store the header received from the response rather than constructing date/time strings themselves. This value is already formatted properly by the server for use in the next conditional request.

## 5. Sending If-Modified-Since in the Next Request

Use the exact `Last-Modified` value received in the previous GET:

~~~http
GET /people/42
If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT
Accept: application/hal+json
~~~

Spring Data REST checks the resource's most recent modification time:

- If the modification time is newer than the `If-Modified-Since` value, the server returns the new content and an updated `Last-Modified` header.
- If the modification time is not newer than the value sent by the client, the server returns `304 Not Modified`.

Example when the resource has been modified:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Wed, 11 Nov 2026 03:15:00 GMT

{
  "id": 42,
  "name": "Anh Nguyen"
}
~~~

The client replaces the old cache validator with the new `Last-Modified` and stores the new representation.

Example when the resource has not changed:

~~~http
HTTP/1.1 304 Not Modified
~~~

The `304` response carries no resource body. The client uses the representation stored in cache.

## 6. Using the Exact URI and Query Parameters

The `Last-Modified` value must remain bound to the exact representation the client downloaded. Do not use a timestamp obtained from one URI for another URI or for a query with different parameters.

For example, if the client read:

~~~http
GET /orders/42?projection=orderSummary
~~~

then it should resend `If-Modified-Since` for that exact URI and query parameter:

~~~http
GET /orders/42?projection=orderSummary
If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT
~~~

Do not take the header from `/orders/42` and use it for `/orders/43`, or take it from the `orderSummary` projection and use it for a different projection. Different representations can have different modification times and contents.

Clients should store the cache validator alongside the request's cache key, at a minimum including the URI and query parameters affecting the representation. If the response uses `Vary` on request headers, the cache key must also account for the corresponding headers.

## 7. Time Precision and Limitations of Last-Modified

The HTTP-date of `Last-Modified` has one-second resolution. If a resource changes multiple times within the same second, the timestamp may not distinguish those two versions.

Other limitations:

- The server clock must be sufficiently synchronized for timestamps to be meaningful.
- The `@LastModifiedDate` value must be updated whenever data related to the representation changes.
- If a change occurs outside the entity auditing mechanism, the timestamp may not be updated as expected.
- A representation may depend on associations or aggregated data outside the entity; a timestamp on the root entity might not reflect all changes to related data.
- Clients should not reuse an old timestamp for another request or another query.

Therefore, `Last-Modified` is useful for cache validation, though it is not always a sufficiently precise validator for every kind of representation.

## 8. Distinguishing If-Modified-Since from ETag

Spring Data REST also supports ETags and related conditional headers. The two mechanisms have similar goals but use different validators:

| Mechanism | Validator | Request header | Purpose |
|---|---|---|---|
| Last-Modified | Most recent modification time | `If-Modified-Since` | Check if a resource is newer than a timestamp |
| ETag | Version/representation identifier | `If-None-Match` | Check if a representation matches a cached validator |
| Optimistic locking | Current ETag of the entity | `If-Match` | Protect updates from overwriting another client's changes |

ETag is usually more accurate when timestamps only have one-second resolution or representations are constructed in complex ways. `If-Modified-Since` is time-based; `If-None-Match` is ETag-validator-based.

If a GET request sends both `If-None-Match` and `If-Modified-Since`, HTTP rules prioritize `If-None-Match`; the server evaluates the ETag and does not use `If-Modified-Since` to override that condition.

Example:

~~~http
GET /people/42
If-None-Match: "7"
If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT
~~~

For write operations such as PUT, PATCH, or DELETE, use `If-Match` to check the ETag and protect concurrent updates. `If-Modified-Since` is primarily intended for conditional GET/HEAD, not as a replacement for optimistic locking.

## 9. Distinguishing Conditional Requests from Cache Freshness

`If-Modified-Since` is a **revalidation** mechanism: the client asks the server whether the cached copy is still usable. It does not by itself determine how long the client is allowed to keep the cache.

Headers such as `Cache-Control` and `Expires` govern freshness lifetime. While a cached entry is still fresh, the cache can reuse it without sending a request. Once the cached entry loses freshness, the client or intermediary can send a conditional request with `If-Modified-Since` to check.

Example response:

~~~http
HTTP/1.1 200 OK
Cache-Control: max-age=60
Last-Modified: Wed, 11 Nov 2026 02:30:00 GMT
~~~

`max-age=60` indicates the response may be considered fresh for 60 seconds under caching rules. After that duration, the client can revalidate with `If-Modified-Since`.

Cache policy configuration must match the time sensitivity of the data and security requirements. Private or frequently changing data should not be cached simply because an endpoint emits `Last-Modified`.

## 10. Handling 304 Responses on the Client

When the server returns `304 Not Modified`, the client should not treat this as an error. It is a successful result of a conditional GET, indicating that the representation in cache can still be used.

Client flow:

1. GET the resource for the first time and store the body along with the `Last-Modified` header.
2. When re-reading, send GET with the saved `If-Modified-Since`.
3. If receiving `200 OK`, replace the body and validator in the cache.
4. If receiving `304 Not Modified`, keep the existing cached body.
5. If receiving another error, handle it per the application's retry or error-display policy.

Example using curl:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/people/42
~~~

After receiving `Last-Modified`, send the conditional request:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  -H "If-Modified-Since: Wed, 11 Nov 2026 02:30:00 GMT" \
  http://localhost:8080/people/42
~~~

You can verify both cases by running the second request before and after modifying the entity through the API or an auditing-enabled update flow.

## 11. Testing If-Modified-Since in Spring Data REST

Test via HTTP integration tests to confirm both auditing and conditional responses work in the actual configuration.

Cases to test:

1. Create a new entity and verify the `@LastModifiedDate` property is populated.
2. GET the item resource and verify the response includes a `Last-Modified` header.
3. Re-send GET with the exact `If-Modified-Since` value received and verify the server returns `304 Not Modified` when the entity has not changed.
4. Update the entity via the REST endpoint and verify the timestamp changes.
5. Re-send a conditional GET with the old timestamp and verify the server returns the new representation with an updated header.
6. Verify whether entities updated through services or other flows have auditing updated.
7. Test requests using a different URI or different query parameters to ensure clients do not mistakenly reuse validators.
8. Test requests containing both `If-None-Match` and `If-Modified-Since` if the application supports ETags.
9. Test responses when an entity lacks `@LastModifiedDate` metadata.
10. Test timezones, one-second resolution, and multiple changes within the same second if data has high update frequency.

Do not assert only the status code. Check the body, headers, and persisted timestamp value in the entity to be sure the validator reflects actual data changes.

## 12. Implementation Workflow

1. Identify item resources that need conditional GET support.
2. Add a modification-time property to the domain entity and annotate it with `@LastModifiedDate`.
3. Enable auditing for the right Spring Data module; for JPA, use `@EnableJpaAuditing` and `AuditingEntityListener`.
4. GET the resource and verify Spring Data REST returns `Last-Modified`.
5. Store the header along with the cache key of the corresponding URI and query parameters on the client.
6. Send `If-Modified-Since` when revalidating the same resource.
7. Handle `304 Not Modified` by reusing the cached body.
8. Combine with ETag if a more precise validator is needed or if write operations need protection via `If-Match`.
9. Run integration tests for both unchanged and modified resource cases.

## 13. Key Takeaways

- `Last-Modified` is a response header recording the resource's most recent modification time.
- `If-Modified-Since` is a request header used to ask the server whether the resource has changed since that timestamp.
- If unchanged, Spring Data REST can return `304 Not Modified` without resending the body.
- Use `@LastModifiedDate` and enable auditing so Spring Data has the modification time; with JPA, configure the auditing listener.
- Re-send the validator for the exact URI and query parameters used to retrieve the representation.
- HTTP-date has one-second precision; ETag may be more suitable when exact version identification is required.
- When both `If-None-Match` and `If-Modified-Since` are present, the ETag condition takes precedence under HTTP rules.
- `If-Modified-Since` is for cache revalidation; `Cache-Control` and `Expires` determine freshness.
- Use `If-Match` with ETag for conditional updates; do not use `If-Modified-Since` in place of optimistic locking.

## References

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
- [HTTP Semantics — RFC 9110, If-Modified-Since](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-modified-since)