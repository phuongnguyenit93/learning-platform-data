# Last-Modified, @LastModifiedDate, and Auditing Support Conditions in Spring Data REST

## Objectives

After this lesson, you will be able to explain the HTTP `Last-Modified` header; configure Spring Data auditing to update a `@LastModifiedDate` property; understand how Spring Data REST uses that value for `If-Modified-Since` conditional requests; distinguish cache revalidation from ETag-based concurrent update control; and recognize conditions that cause the header to be missing or fail to reflect the latest change.

## 1. What Is Last-Modified?

`Last-Modified` is an HTTP response header indicating when the server recorded that a resource was last modified. Example:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Tue, 11 Nov 2025 09:30:00 GMT
```

The client can store this timestamp along with the resource URI. When reading again, the client sends the received timestamp in the `If-Modified-Since` request header. The server can return:

- `200 OK` with the new representation if the resource has changed since the timestamp sent by the client.
- `304 Not Modified` with no response body if the resource has not changed and the cached representation is still valid.

This mechanism is called conditional GET or cache revalidation. The client does not have to re-download the entire body when data has not changed, reducing bandwidth and serialization work on the server.

`Last-Modified` is HTTP response metadata. It does not automatically create a database column, enable auditing, or set a cache expiration time. For Spring Data REST to emit the header based on an entity, the domain model needs modification-time information that Spring Data REST can recognize.

## 2. @LastModifiedDate Provides Modification Time for an Entity

Spring Data Commons provides the annotation:

```java
import org.springframework.data.annotation.LastModifiedDate;
```

Place the annotation on the property representing when the entity was most recently modified:

```java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Receipt {

    @Id
    @GeneratedValue
    private Long id;

    private String saleItem;

    private BigDecimal amount;

    @LastModifiedDate
    private Instant lastModifiedAt;

    // Constructor, getters, and setters
}
```

`@LastModifiedDate` is auditing metadata. When the auditing infrastructure is enabled and the entity listener runs, Spring Data writes the modification timestamp into this property when the entity is persisted or updated.

Temporal types supported by Spring Data auditing include modern Java date/time types, `long`, `Long`, `java.util.Date`, and `Calendar`. For new applications, `Instant` is usually a convenient choice because it represents an absolute point in time and carries no local timezone.

You can also use `@CreatedDate` to store creation time:

```java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;
```

The two fields have different meanings: `createdAt` preserves the creation time, whereas `lastModifiedAt` is updated when the entity changes. Under the default configuration of `@EnableJpaAuditing`, `modifyOnCreate` is `true`, so the modification timestamp is also set when creating the entity. This behavior can be changed via configuration attributes if business rules require it.

## 3. Prerequisites for Auditing to Work with Spring Data JPA

Simply adding `@LastModifiedDate` to a field is not enough. With Spring Data JPA, you need to enable auditing and register `AuditingEntityListener`.

Configuration to enable auditing:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
```

Register the listener on the entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Receipt {
    // Entity properties
}
```

If you want to apply the listener to multiple entities in a persistence unit, you can declare a default listener in `orm.xml` instead of repeating `@EntityListeners` on each entity. For Spring Data JPA applications, use the appropriate store-specific configuration for your running Spring Data version.

Conditions to verify:

1. The application has Spring Data JPA and the required Bean/Auditing providers on the classpath.
2. `@EnableJpaAuditing` configuration is present in the Spring application context.
3. `AuditingEntityListener` is registered on the entity or persistence unit.
4. The property is annotated with the correct `org.springframework.data.annotation.LastModifiedDate` annotation.
5. The property has a data type supported by auditing and is persisted by the persistence mapping.
6. The entity actually goes through a persist/update lifecycle observed by the auditing listener.

If using Spring Data MongoDB, JDBC, R2DBC, or another store, enable auditing using that store's corresponding configuration. `@EnableJpaAuditing` is for JPA only; do not use it as a generic configuration for all Spring Data modules.

## 4. Is AuditorAware Required?

No. If you only need creation and modification timestamps, you do not need to implement `AuditorAware`.

`AuditorAware<T>` is needed only when you want to record who created or modified an entity using `@CreatedBy` and `@LastModifiedBy`. Example:

```java
@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
```

If these properties are needed, provide an `AuditorAware` bean so the auditing infrastructure knows the current principal. Example using Spring Security:

```java
@Bean
AuditorAware<String> auditorAware() {
    return () -> Optional.ofNullable(
            SecurityContextHolder.getContext().getAuthentication())
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
```

If there are multiple `AuditorAware` beans, specify which bean to use via the `auditorAwareRef` attribute of `@EnableJpaAuditing`. For background jobs or message consumers without HTTP authentication, define an appropriate auditor, such as a system account.

For the `Last-Modified` problem, the focus is `@LastModifiedDate`; do not add `AuditorAware` if the application does not need to store the modifier's name.

## 5. How Does Spring Data REST Generate the Last-Modified Header?

When Spring Data REST serves a repository item resource with a `@LastModifiedDate` property updated by auditing, it can place that value into the `Last-Modified` response header.

For example, a Receipt entity has:

```java
@LastModifiedDate
private Instant lastModifiedAt;
```

Item read request:

```http
GET /receipts/42 HTTP/1.1
Accept: application/hal+json
```

The response may contain:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Last-Modified: Tue, 11 Nov 2025 09:30:00 GMT
```

The header value is formatted as an HTTP-date and represents the time in GMT/UTC. Clients should capture the exact header value returned by the server rather than converting database timestamps or formatting date/time strings themselves.

If the property exists but auditing does not run, the value may be null or stale, and the header may not be emitted or may not represent the most recent change. Therefore, verify both the persisted field value and the HTTP header after calling the endpoint.

## 6. Using If-Modified-Since for Conditional GET

After the first GET, the client stores the resource URI and the `Last-Modified` value. When re-reading the same resource, send that timestamp:

```http
GET /receipts/42 HTTP/1.1
Accept: application/hal+json
If-Modified-Since: Tue, 11 Nov 2025 09:30:00 GMT
```

If the resource has not changed since that timestamp, Spring Data REST can return:

```http
HTTP/1.1 304 Not Modified
```

A `304` response does not need to resend the body. The client continues using the cached representation. If the entity has changed, the server returns `200 OK`, the new body, and a new `Last-Modified` value for the client to store.

You can test with curl:

```bash
curl -i http://localhost:8080/receipts/42 \
  -H "Accept: application/hal+json"
```

After retrieving the `Last-Modified` value from the response, use that exact value:

```bash
curl -i http://localhost:8080/receipts/42 \
  -H "Accept: application/hal+json" \
  -H "If-Modified-Since: Tue, 11 Nov 2025 09:30:00 GMT"
```

The specific result depends on the resource's current timestamp. The example above illustrates how to pass the header; do not use a fixed timestamp in real environments.

**Preserve the exact URI and query parameters.** The `Last-Modified` value is obtained from a specific representation/request. Resend that value only when requesting the exact same URI and query parameters. Do not use the timestamp from `/receipts/42` for `/receipts/43`, the `/receipts` collection, or another query. Projections, filters, or pagination parameters can also produce a different representation.

## 7. Distinguishing Last-Modified from ETag

Both `Last-Modified` and `ETag` can support conditional requests, but they carry different information:

| Mechanism | Value represented | Commonly used request header | Purpose |
| --- | --- | --- | --- |
| Last-Modified | Most recent modification time | `If-Modified-Since` | Avoid re-downloading unchanged representations |
| ETag | Identifier/version of the representation or resource per configuration | `If-None-Match`, `If-Match` | Cache revalidation and preventing updates based on stale versions |

Spring Data REST can generate an ETag from a property annotated with `@Version`. When a client sends `If-Match` with the previously read ETag in PUT, PATCH, or DELETE, the server performs the operation only if the current version still matches. If another client updated the resource, the request using the old ETag is rejected with `412 Precondition Failed`.

Example:

```java
@Version
private Long version;
```

Client sends:

```http
PATCH /receipts/42
If-Match: "7"
Content-Type: application/json

{"amount": 125.00}
```

The actual ETag value must be copied from the response header, including quotation marks or syntax returned by the server. The `"7"` example is illustrative only.

For GET, clients can also use `If-None-Match`; if the ETag has not changed, the server returns `304 Not Modified`. When both mechanisms are available, ETag is usually the better choice for version control because it does not depend on timestamp precision.

## 8. Limitations of Last-Modified and Conditions to Watch For

**HTTP-date precision is one second.** An `Instant` property can hold nanoseconds, but a `Last-Modified` value in HTTP-date format does not represent sub-second fractions. If a resource is updated multiple times within the same second, the changes may share the same header value. For rapidly changing resources or when every update must be detected, use ETag/version rather than relying solely on Last-Modified.

**The timestamp must change when the representation changes.** If data is updated via a write path that does not trigger auditing, the field may remain unchanged. With JPA, bulk JPQL updates or native SQL typically bypass entity lifecycle callbacks; you must update the audit column manually or use another mechanism for that write path.

**Changes to related entities do not necessarily update the parent entity.** If a Customer response includes Department data, editing Department does not automatically change Customer's `lastModifiedAt`. If a parent representation depends on child data, clearly define cache invalidation and update the version/timestamp on the proper aggregate or use an appropriate ETag.

**Auditing does not replace a cache policy.** `Last-Modified` is a validator to check whether a resource has changed. Headers such as `Cache-Control` and `Expires` govern how long a cache can use a response without revalidating. Configure cache freshness separately according to security and data freshness requirements.

**Do not use Last-Modified as an authorization mechanism.** Clients can send arbitrary timestamps. The header only serves conditional requests; authorization must still be checked on every request. Do not expose sensitive information simply because a resource has Last-Modified.

## 9. Common Errors and How to Diagnose Them

**Response lacks Last-Modified**

Check whether the property has `@LastModifiedDate` from the correct package; whether auditing is enabled; whether the JPA listener is registered; whether the entity is saved through a lifecycle observed by the listener; and whether the field has a value after flush/reload.

**Last-Modified does not change after an update**

Check whether the update actually saves the entity through the JPA lifecycle. If using bulk updates/native SQL, update the audit field explicitly. Check both the database value and the response header.

**Request always returns 200 instead of 304**

Verify the request sends `If-Modified-Since` in valid HTTP-date syntax, the value was taken from the previous response, the URI and query parameters have not changed, and the server timestamp is not newer than the value sent by the client.

**Request returns 304 but the client displays no data**

This is normal behavior if the client did not store the previous representation. The client must keep the body from the prior `200 OK` and reuse it when receiving `304`. There is no new body in a 304 response.

**Using Last-Modified to prevent data overwrites yet still losing updates**

Use ETag with `@Version` and `If-Match` for optimistic concurrency. Last-Modified/If-Modified-Since in Spring Data REST primarily supports conditional GET and bandwidth savings; it does not replace version checking for PUT/PATCH/DELETE.

**Inconsistent timestamps across environments**

Use a temporal type with clear semantics such as `Instant`; check database timezone, `DateTimeProvider` configuration, and system clocks. In tests, you can provide a fixed DateTimeProvider for deterministic results.

## 10. Verification Workflow from Database to HTTP Response

1. Add a `@LastModifiedDate` property to the entity and ensure the property is saved by persistence mapping.
2. Enable auditing with the appropriate store configuration; for JPA, use `@EnableJpaAuditing` and `AuditingEntityListener`.
3. Create an entity via the repository and verify `lastModifiedAt` is populated.
4. Update the entity via the repository, flush the transaction, and verify the timestamp is updated.
5. Call the item resource with GET; verify the response has `Last-Modified`.
6. Re-send GET with the exact same URI and query parameters using the received `If-Modified-Since`; verify a `304` response when the resource has not changed.
7. Perform a new change; re-GET with the old timestamp and verify the server returns the new representation along with a new `Last-Modified`.
8. If write operations need protection from stale clients, add `@Version` and test ETag/`If-Match` separately.

In integration tests, do not merely check that the annotation is present. Verify that the auditing listener actually updates the field, the value is persisted, and Spring Data REST emits the correct HTTP header.

## Summary

- `@LastModifiedDate` marks a property storing when an entity was most recently modified; the annotation belongs to Spring Data Commons.
- With JPA, `@EnableJpaAuditing` must be enabled and `AuditingEntityListener` must be registered on the entity or persistence unit.
- `AuditorAware` is not needed if only recording created/modified dates; it is needed when using `@CreatedBy` or `@LastModifiedBy`.
- Spring Data REST can emit `Last-Modified` from a property updated by auditing.
- Clients send `If-Modified-Since` for the exact same URI and query parameters; if unchanged, the server can return `304 Not Modified`.
- Last-Modified has one-second HTTP-date precision and does not replace ETag for optimistic concurrency.
- Bulk updates, changes to related entities, and write paths bypassing lifecycle callbacks can prevent timestamps from reflecting all changes.
- Cache freshness, authorization, and version-based write protection must be configured separately.

## References

- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/jpa/reference/data-commons/auditing.html)
- [Spring Data JPA — AuditingEntityListener API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/domain/support/AuditingEntityListener.html)
- [Spring Data JPA — EnableJpaAuditing API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/config/EnableJpaAuditing.html)