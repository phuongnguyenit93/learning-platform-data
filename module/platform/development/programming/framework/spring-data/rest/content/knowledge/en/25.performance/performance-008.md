# Limiting Request Bodies, Resource-Intensive Queries, and Request Rates in Spring Data REST

## Objectives

Spring Data REST lets you publish repositories quickly, yet a broad CRUD endpoint can consume excessive resources if clients send oversized payloads, request unbounded page sizes, sort or filter on expensive fields, or send requests at too high a rate.

You need to protect the API across three groups of limits:

- **Request body:** cap the byte size, element count, and complexity of input data.
- **Query and response:** cap page size, offset, supported sorts/filters, query execution time, and result size.
- **Request rate and concurrency:** limit request counts per user, API key, IP, or tenant; control concurrently executing requests.

Limits must be enforced on the server. Do not rely on the UI, JavaScript, or the client self-limiting data volume, because callers can send requests directly.

This lesson covers control points across Spring Data REST, Spring MVC, Spring Security, gateways, and databases; how to choose sensible limits; how to return 413/429 errors; and how to test so the API is protected from abuse or unintentional overload.

## 1. Viewing a Request as a Resource Budget

A request can consume resources across multiple stages:

~~~text
Client
  |
  v
Gateway / reverse proxy
  |  body size, rate, connection limits
  v
Servlet container
  |  request size, header size, timeout
  v
Spring Security / MVC
  |  authentication, authorization, validation
  v
Spring Data REST
  |  binding, repository invocation, pagination
  v
Database
  |  query cost, sort, joins, locks, execution time
  v
Response serialization
     response bytes, nested associations, CPU
~~~

A limit at one layer does not replace a limit at another. For example:

- Limiting page size does not prevent a POST with a huge JSON body.
- Limiting body size does not prevent a small query from running for several minutes.
- Rate limiting does not prevent a single request from asking for millions of records if page size is unbounded.
- Limiting queries does not prevent a client from sending thousands of concurrent requests.

Define a budget for each endpoint category: maximum input bytes, maximum items per page, maximum filter/sort conditions, maximum query duration, response size, and request count over a time window.

## 2. Limiting Page Size in Spring Data REST

Pagination is one of the most important safeguards when exposing collections. Spring Data REST allows configuring default and maximum page sizes:

~~~java
@Configuration
class RestApiConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
    }
}
~~~

In this example:

- Requests omitting size use the default page size of 25.
- Requests passing size above the maximum are capped by the exporter's configuration.
- Clients cannot ask for an arbitrarily large page merely by changing a query parameter.

The values 25 and 100 are only examples. Choose limits based on serialized field count, association size, database load, latency, and screen purpose.

### Do Not Look Only at Item Count

A page of 100 items can be small if each item has only a few fields, yet huge if each item carries many associations or nested representations. Projections can reduce returned data, but they do not replace a page size limit.

When choosing max page size, measure response bytes and serialization time on realistic data. Do not pick a limit based on item count alone.

## 3. Limiting Deep Pagination and Offset

Even a small page size can trigger an expensive query if the client requests a very large page index. With offset pagination, the database may have to skip many rows before returning results.

Example:

~~~http
GET /api/orders?page=500000&size=100
Accept: application/hal+json
~~~

Even though at most 100 items are returned, the query can be costly due to the large offset, depending on the database, query plan, and indexes.

Ways to control this:

- Set a page size limit.
- Evaluate a maximum page index or offset for endpoints over large datasets.
- Restrict sorts/filters so queries use appropriate indexes.
- Use query methods with explicit predicates instead of allowing unbounded general-purpose queries.
- For very large or rapidly changing datasets, consider cursor/keyset pagination if the API and repository support it.

Spring Data REST's page size configuration does not automatically solve all deep-offset issues. If you need to bound offset, validate the request before querying or design a dedicated endpoint with explicit bounds. Do not assume max page size also means max page number.

## 4. Limiting Resource-Intensive Sorts and Filters

Sorting by an unindexed column, sorting across associations, or combining many conditions can produce expensive query plans. Client-supplied query parameters should be restricted via an allowlist.

Suppose a client sends:

~~~http
GET /api/orders?sort=createdAt,desc&page=0&size=25
~~~

An API should define which sort properties are permitted:

- createdAt.
- orderNumber.
- status.
- totalAmount if supported by queries and indexes.

Do not allow clients to sort arbitrarily on every property, especially nested properties or associations with high join costs.

This can be enforced at multiple layers:

- Expose only query methods with supported parameters.
- Use a custom controller/service to parse and allowlist sorts/filters.
- Use a query builder with whitelisted properties rather than concatenating query strings from input.
- Create indexes matching common queries.
- Limit the number of sort and filter criteria.
- Apply an appropriate database statement timeout or query timeout.

Do not treat client-supplied property names as SQL. Even so, permitting arbitrary properties can inflate query cost or inadvertently expose search capabilities the application did not intend to support.

## 5. Limiting Request Body by Bytes

A POST or PATCH can send an enormous JSON payload:

~~~http
POST /api/people
Content-Type: application/json

{
  "displayName": "Ada",
  "notes": "... very large content ...",
  "attachments": [ ... thousands of entries ... ]
}
~~~

Spring Data REST uses Spring MVC message conversion to read request bodies. Size limits must be enforced at the appropriate layers:

- A reverse proxy or API gateway is typically the first layer to reject oversized bodies before requests reach the application.
- Servlet containers have limits for requests/headers and certain body types depending on configuration.
- For JSON bodies, a bounded request wrapper or dedicated filter may be needed if the platform does not provide a suitable byte limit.
- For multipart uploads, use Spring Boot/container multipart limits.

Do not confuse multipart configuration with a general JSON limit. For example, multipart properties such as max-file-size or max-request-size primarily govern multipart uploads; they are not a complete policy for all application/json requests.

### Content-Length Is Not the Only Proof

Some requests may use chunked transfer encoding or lack the expected Content-Length header. Even if you inspect the Content-Length header, ensure the actual input stream is bounded so oversized bodies cannot bypass the check.

A gateway/proxy is usually a good place for a global byte limit. If enforced inside the application, use an approach that counts bytes as the stream is read and rejects immediately upon exceeding the threshold, rather than reading the entire body into memory first and checking afterward.

### Returning Errors for Oversized Bodies

HTTP 413 Payload Too Large is the appropriate status when a request body exceeds the limit. The error body should be concise and must not echo back the oversized payload.

Example response using Problem Details:

~~~json
{
  "type": "about:blank",
  "title": "Payload too large",
  "status": 413,
  "detail": "The request body exceeds the allowed size.",
  "code": "REQUEST_BODY_TOO_LARGE"
}
~~~

Clients can shrink payloads, split them into batches, or use a dedicated upload workflow.

## 6. Limiting JSON Element Count and Depth

A byte limit is not always sufficient. A small JSON payload with deeply nested structures or a huge number of nodes can spike CPU and memory during parsing/binding.

For example, a request creating a deeply nested collection or an array with a massive number of elements.

Appropriate safeguards include:

- Capping collection element counts in input via validation.
- Capping string lengths and accepted field counts.
- Capping nesting depth and parser constraints according to your Jackson version.
- Avoiding binding a huge object graph when the use case needs only a few fields.
- Using DTOs with an allowlist to define the input contract.
- Limiting the number of items processed per batch.
- Separating large file uploads from JSON CRUD endpoints.

DTO example:

~~~java
public record BulkStatusRequest(
    @NotEmpty
    @Size(max = 100)
    List<@NotNull Long> ids,

    @NotNull
    OrderStatus status
) {
}
~~~

The DTO caps the ID list at 100 and requires status. The server must still verify permissions on every ID and validate business rules before saving.

## 7. Avoiding Oversized Queries and Responses from Associations

A collection page can return a huge response if each item embeds many associations or if a projection includes numerous properties.

Example:

- Person has many Addresses.
- Order has many OrderLines.
- Each OrderLine also has Product and Category.
- Deeply nested projections multiply the number of serialized objects.

Ways to cut costs:

- Use slim projections for collections.
- Expose only truly needed associations.
- Use links so clients fetch related resources on demand.
- Avoid overly deep nested representations.
- Cap child collections or provide dedicated endpoints to query them.
- Check for N+1 queries during HAL serialization.
- Measure response size and serialization time.

Projections help select representations, yet do not automatically guarantee efficient queries. A projection invoking association getters can trigger lazy loading and generate many queries. Inspect SQL and query plans on real data.

## 8. Limiting Query Execution Time and Database Resources

A request can be small yet run a very expensive query due to missing indexes, large joins, complex sorting, or long lock waits.

Combine the following:

- Indexes for common filters/sorts.
- Query timeouts at the JPA/provider or database layer.
- Statement timeouts in the database if supported.
- Limits on record counts and query predicates.
- Connection pool and concurrency limits.
- Monitoring of slow queries and execution plans.
- Short transaction boundaries, avoiding holding transactions across network I/O.
- Disallowing arbitrary client-driven queries outside the API contract.

Example using a timeout hint on a JPA query:

~~~java
TypedQuery<Order> query = entityManager.createQuery(
    "select o from Order o where o.status = :status",
    Order.class
);

query.setParameter("status", OrderStatus.OPEN);
query.setHint("jakarta.persistence.query.timeout", 2000);
~~~

Timeout values and enforcement behavior depend on the JPA provider and database. Verify actual configuration, as an unsupported hint may be ignored or handled differently.

When a query timeout occurs, classify the error per the API contract. Do not turn a database timeout into a 400 when the client's request was valid and the system could not complete within the allowed time.

## 9. Limiting Request Counts and Rate Limiting

A client can send continuous bursts of requests that exhaust CPU, connections, and the database. Rate limiting controls request volume within a time window.

You can limit by:

- IP address.
- User ID or principal.
- API key/client ID.
- Tenant or organization.
- Endpoint group.
- A combination of dimensions, such as an IP limit plus a user limit.

Illustrative policy examples:

| API group | Example limit | Rationale |
|---|---|---|
| GET collection | 60 requests/min/user | Read frequently, often cacheable. |
| Expensive GET search | 20 requests/min/user | More complex queries. |
| POST/PATCH | 30 requests/min/user | Reduces repeated writes or excessive automation. |
| Bulk operation | 5 requests/min/admin | High impact and needs strict control. |
| Login/token | Per dedicated authentication policy | Prevents brute force and credential abuse. |

These are only examples. Measure real traffic, SLAs, backend capacity, and client needs before setting thresholds.

### Where to Enforce Rate Limits?

Rate limits are typically placed at the API gateway or reverse proxy to reject requests early. You can supplement with application-level rate limiting when policies depend on principal or business rules.

Across multiple instances, rate-limit counters must be shared or coordinated between instances. Separate in-memory counters on each node can let aggregate usage exceed the intended limit.

Use token bucket, leaky bucket, or sliding window algorithms depending on gateway capabilities. Pick an algorithm whose behavior fits burst traffic.

### Returning 429 Too Many Requests

When rate limits are exceeded, return HTTP 429. When possible, include Retry-After so clients know when they may retry:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "about:blank",
  "title": "Too many requests",
  "status": 429,
  "detail": "The request limit has been reached. Try again later.",
  "code": "RATE_LIMIT_EXCEEDED"
}
~~~

Clients should honor Retry-After and use exponential backoff with jitter when retrying. Do not retry continuously immediately after receiving a 429.

## 10. Limiting Concurrent Requests and Queues

A per-minute rate limit does not stop a client from firing many simultaneous requests in a burst. Consider concurrency limits:

- Cap active in-flight requests per user/tenant.
- Cap concurrent database queries.
- Set timeouts for requests and upstream calls.
- Use bounded queues if asynchronous processing is used.
- Reject early under overload rather than queuing indefinitely.
- Cap bulk operations so they do not starve worker threads.

If an endpoint calls multiple external services, cumulative wait times can tie up servlet threads and connections for long periods. Set timeouts on each dependency and put appropriate circuit breakers in place.

Do not build an unbounded queue “so no request is dropped”. Unbounded queue growth turns overload into memory exhaustion and extreme latency.

## 11. Limiting Response Size and Returned Data Volume

A request may be valid while its response is still too large. Bound responses by:

- Using pagination for collections.
- Setting a max page size.
- Choosing appropriate projections.
- Limiting nested associations.
- Providing dedicated export/download endpoints for large datasets.
- Streaming data when the use case demands it and infrastructure supports it.
- Setting response timeouts and size caps at the gateway if needed.

Do not use standard collection endpoints to download hundreds of thousands of records in one response. When large exports are needed, design an asynchronous export job: the client submits a request, the server builds the file in the background, and the client downloads the result via an authorized resource.

## 12. Combining Spring Data REST with Gateways and Spring Security

Control layers should work together:

| Layer | Responsibility |
|---|---|
| Reverse proxy/API gateway | Body byte limits, request rate, connection limits, timeouts. |
| Servlet container | Header/request constraints and connections. |
| Spring Security | Authentication, authorization, and per-principal quotas if integrated. |
| Spring Data REST configurer | Default/max page size and resource exposure. |
| Controller/service | Filter/sort allowlists, batch sizes, validation, and business limits. |
| Database | Indexes, statement timeouts, query plans, and connection capacity. |

Do not use CORS as rate limiting or authorization. CORS only governs browser cross-origin behavior. The API must still authenticate, authorize, and enforce resource limits for all direct requests.

For write endpoints, govern item count in the body, authorization on every entity, transaction size, and call frequency. A batch of 100 items may be reasonable, whereas a batch of 100,000 items requires a dedicated workflow.

## 13. Observability and Measurement

You cannot pick sound limits without knowing how many resources requests consume.

Track at least:

- Request counts by endpoint, status, and principal/tenant without exposing sensitive data.
- Request body size and response size.
- Page sizes, offsets, and sorts/filters used.
- Time spent at the gateway, application, and database.
- Query count per request and slow queries.
- In-flight request counts and queue depth.
- Rates of 413, 429, 503, and timeouts.
- CPU, heap, garbage collection, connection pools, and thread pools.

Use metrics and tracing to identify which endpoints need tighter bounds. Avoid logging full request bodies; bodies may contain personal information, credentials, or sensitive data.

## 14. Example Page Size and Validation Configuration

Spring Data REST configuration:

~~~java
@Configuration
class RestApiConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
    }
}
~~~

DTO for a batch operation:

~~~java
public record BulkUpdateRequest(
    @NotEmpty
    @Size(max = 100)
    List<@NotNull Long> ids,

    @NotNull
    OrderStatus status
) {
}
~~~

The service must verify permissions across the entire ID set before updating:

~~~java
@Transactional
public void updateStatuses(
        BulkUpdateRequest request,
        CurrentUser user) {

    List<Order> orders = repository.findAllById(request.ids());

    if (orders.size() != request.ids().stream().distinct().count()) {
        throw new EntityNotFoundException();
    }

    authorizationService.requireCanUpdateAll(user, orders);

    for (Order order : orders) {
        order.changeStatus(request.status());
    }

    repository.saveAll(orders);
}
~~~

This is an illustrative example. Handle duplicate IDs, tenant scope, workflow state, and batch limits according to real business rules. Do not check only total ID count; verify every entity belongs to the scope the principal is allowed to modify.

## 15. Testing Limits

Maintain integration tests for boundary conditions:

1. Request bodies under the limit are accepted.
2. Request bodies exceeding the limit are rejected with 413.
3. JSON payloads with too many elements are rejected by validation.
4. Overly deep JSON nesting is handled according to parser/validation policy.
5. Requests omitting page size use the default.
6. Requests exceeding max page size are capped or rejected per the chosen configuration.
7. Page indices/offsets exceeding thresholds are handled properly if the API enforces a cap.
8. Sort properties outside the allowlist are rejected.
9. Query timeouts do not hang requests indefinitely and return errors per contract.
10. Rate limiting permits requests within quota.
11. Requests exceeding quota receive 429 and an appropriate Retry-After header.
12. Concurrency limits do not create unbounded queues.
13. Bulk operations exceeding maximum item count are rejected.
14. Collection responses do not exceed configured page size and projection bounds.
15. Different principals receive quotas and permissions matching policy.

Example page size test:

~~~java
mockMvc.perform(get("/api/people")
        .param("size", "10000")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(100));
~~~

This test assumes max page size is configured as 100 and the Spring Data REST version in use caps requested size to that setting. Confirm actual behavior in your project's integration tests.

## 16. Common Mistakes

1. **Limiting only page size.** Bodies, query cost, request rate, and concurrency may still be unbounded.
2. **Confusing multipart limits with JSON body limits.** File upload settings are not a general limit for application/json.
3. **Checking only Content-Length.** Chunked requests or missing headers require enforcing limits while reading the stream.
4. **Setting an enormous page size to reduce request count.** That can spike memory, query cost, and response serialization.
5. **Ignoring deep offsets.** A small page size does not make a huge page index cheap.
6. **Allowing sorting on every property.** Can create expensive query plans or expose fields that should not be searchable.
7. **Not limiting nested associations.** A small page can still produce large responses and N+1 queries.
8. **Rate limiting solely by IP.** Users behind a proxy or multiple users sharing an IP may be unfairly throttled; consider principal/API key/tenant.
9. **Using in-memory counters across multiple instances.** Each node tracks limits separately and total quota can be exceeded.
10. **Retrying immediately after 429.** Can amplify traffic bursts; honor Retry-After and back off.
11. **Unbounded request queues.** Large queues increase memory consumption and latency.
12. **Using validation in place of authorization.** A valid ID can still belong to another tenant.
13. **Logging full request bodies.** Can leak sensitive data and inflate log storage costs.
14. **Failing to measure response size.** Projections and associations can make responses larger than expected.
15. **Failing to distinguish 413, 429, and timeout errors.** Clients need to know whether to shrink payloads, wait for quota, or handle system errors.
16. **Applying a single limit across all endpoints.** Search, CRUD, upload, and bulk operations have distinct resource profiles.

## 17. Implementation Checklist

- Set default and max page size for Spring Data REST.
- Evaluate deep offset limits or use cursor/keyset pagination when appropriate.
- Allowlist sorts/filters and cap query predicates.
- Enforce body byte limits at the gateway/proxy and bound stream reads if needed.
- Distinguish JSON limits from multipart upload limits.
- Cap JSON element counts, string lengths, and nesting depth.
- Use allowlisted DTOs for batch inputs.
- Limit nested associations and response sizes.
- Configure query/statement timeouts and monitor slow queries.
- Design indexes for common filters/sorts.
- Apply rate limits by principal/API key/tenant and IP as appropriate.
- Share rate-limit state across application instances.
- Cap concurrent requests and queues.
- Return 413 for oversized payloads and 429 for exceeded quotas.
- Provide Retry-After when appropriate.
- Monitor request/response bytes, latency, query counts, and error rates.
- Test thresholds just below, at, and above limits.
- Never log sensitive payloads or rely on the UI to protect resources.

## Summary

Protecting Spring Data REST performance requires bounding inputs, queries, responses, and request rates. Use default/max page sizes to govern collections; restrict deep offsets, sorts/filters, and query durations to avoid expensive queries; set body byte limits and JSON structural bounds; and apply rate limits and concurrency limits to shield the system from burst traffic.

The Spring Data REST configurer addresses only part of the picture, such as page size and exposure. Body limits typically require a gateway, proxy, container, or bounded request handling; query cost requires service/repository/database controls; rate limiting requires a gateway or state shared across instances. Return 413 for oversized payloads, 429 for quota exhaustion, and keep status/error contracts clear.

Measure request/response sizes, query times, query counts, and concurrency before choosing thresholds. Test boundary values and confirm rejected requests leave no side effects and do not consume unbounded resources.

## References

- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Boot — Servlet Web Server](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Cloud Gateway — Request Rate Limiting](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html)
- [RFC 9110 — HTTP Semantics: 413 and 429](https://www.rfc-editor.org/rfc/rfc9110)
