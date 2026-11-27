# Building a Reactive Access Flow with Error Handling and Resource Bounds

## 1. Capstone Problem: An Order API That Scales While Staying Bounded

In the **SPRING_DATA_MONGODB** module, we learned how to connect to MongoDB, map documents, and operate on collections through **MongoTemplate** or **repositories**. Querying, aggregation, indexing, transactions, reactive access, testing, and performance diagnostics come together in the **Capstone Practice** chapter to build an operationally sound feature.

Suppose a multi-tenant enterprise platform needs an API to browse paid orders. Each user may only view orders belonging to their authenticated tenant. Collections can grow to millions of documents; many users may paginate concurrently while MongoDB experiences network jitter or replica set primary transitions.

System requirements:

1. Use **Spring WebFlux** and **ReactiveMongoTemplate** to access MongoDB without blocking processing threads while waiting on I/O.
2. Always filter by tenant from the authenticated identity; never let clients choose an arbitrary tenant.
3. Return results in a deterministic order and **bound the number of documents read per call**.
4. Use **keyset pagination** to avoid costs growing with page depth as in skip/offset.
5. Classify parameter errors, database failures, and timeouts; return proper HTTP statuses without exposing internal details.
6. Bound wait times, concurrent operations, connection pool resources, and in-memory data retention.
7. Verify behavior with Reactor StepVerifier, integration tests, and load metrics.

**The goal of this lesson** is a complete flow from HTTP request to MongoDB and back to the client, with clear contracts for data safety and failure behavior. Code focuses on standard APIs of Spring Boot 3.x, Spring WebFlux, Spring Data MongoDB, and Reactor on Java 17+; verify APIs and configuration metadata when using other versions.

## 2. Reactive Thinking and Its Limits

### 2.1. Mono and Flux Do Not Mean Infinite Resources

In Reactor:

| Type | Logical outcome | Example in this lesson |
| --- | --- | --- |
| Mono<T> | 0 or 1 element, or error signal | A single OrderPage returned from a query |
| Flux<T> | 0 to many elements, or error signal | Sequence of MongoDB documents streamed from a cursor |
| Subscription | Publisher consumption lifecycle | Managed by WebFlux when handling HTTP requests |
| Backpressure | Downstream signals demand for elements | Coordinates emission and consumption rates |
| Cancellation | Consumer stops receiving elements | Triggered on timeout or client disconnect |

Reactive avoids tying up one thread per I/O call, yet MongoDB connection pools, CPU, RAM, bandwidth, and HTTP write throughput remain finite. Launching 10,000 parallel MongoDB queries via an unbounded flatMap will still exhaust connections and memory.

Never call **block()** or manually call **subscribe()** inside a WebFlux controller. Return Mono/Flux and let the framework drive subscriptions. Never wrap a blocking MongoTemplate call in Mono.just and treat the pipeline as non-blocking.

### 2.2. Designing the Flow

~~~mermaid
flowchart LR
  A[GET /api/orders] --> B[Spring Security verifies JWT]
  B --> C[Controller extracts tenant_id]
  C --> D[Validate status / size / cursor]
  D --> E[ReactiveMongoTemplate]
  E --> F[(MongoDB with compound index)]
  F --> G[Flux up to size + 1]
  G --> H[Bounded collectList]
  H --> I[OrderPage and nextCursor]
  I --> J[HTTP JSON]
~~~

Alongside the data stream, the service layer applies timeouts and translates known infrastructure errors into proper HTTP responses. Queries always carry the tenant predicate; MongoDB connection pools and application concurrency must be bounded beyond any single query.

## 3. Data and API Contracts

### 3.1. Sample Document

The **orders** collection uses an illustrative schema:

~~~javascript
{
  _id: ObjectId("65350f8453dbe413901c1211"),
  tenantId: "tenant-A",
  status: "PAID",
  createdAt: ISODate("2026-11-18T08:30:00.000Z"),
  totalCents: NumberLong("125000")
}
~~~

Rules:

- tenantId comes from the caller's verified identity; every order has exactly one tenantId.
- status belongs to PAID, PENDING, CANCELLED in this example.
- createdAt is a BSON Date, always present, and **must not be arbitrarily mutated after creation**.
- _id is a unique ObjectId; totals are stored in integer cents to avoid floating-point math.
- Timestamps use UTC; MongoDB Date stores millisecond precision.

### 3.2. Bounded Search API

~~~http
GET /api/orders?status=PAID&size=20
Authorization: Bearer <JWT_TOKEN>
Accept: application/json
~~~

Sample response:

~~~json
{
  "items": [
    {
      "id": "65350f8453dbe413901c1211",
      "status": "PAID",
      "createdAt": "2026-11-18T08:30:00Z",
      "totalCents": 125000
    }
  ],
  "hasNext": true,
  "nextCursor": {
    "createdAt": "2026-11-18T08:30:00Z",
    "id": "65350f8453dbe413901c1211"
  }
}
~~~

The client passes the last received item's key pair to request the next page:

~~~http
GET /api/orders?status=PAID&size=20&afterCreatedAt=2026-11-18T08%3A30%3A00Z&afterId=65350f8453dbe413901c1211
Authorization: Bearer <JWT_TOKEN>
~~~

**Important:** the sample response only illustrates structure. In the implementation below, nextCursor is non-null only when at least one more document exists after the current page. Because data changes over time, keyset pagination keeps a stable ordering over the live dataset rather than guaranteeing an immutable snapshot across HTTP calls.

API bounds:

| Rule | Example value | Rationale |
| --- | --- | --- |
| Default size | 20 | Prevents accidental large reads |
| Max size | 100 | Stops clients from requesting thousands of records |
| Actual fetch | size + 1 | Determines hasNext without counting the whole collection |
| Ordering | createdAt DESC, _id DESC | Provides a unique tie-breaker for identical timestamps |
| Per request | One page | Bounds memory and resource hold duration |
| Reactive deadline | 3 seconds in this lesson | Prevents requests from hanging indefinitely |
| Cursor | afterCreatedAt and afterId must appear together | Prevents broken pagination from half a cursor |

In production, consider encoding both cursor fields into a signed **opaque token** bound to tenant, filters, sort, and expiration. This lesson exposes the pair explicitly to make the algorithm clear; tampering with client-sent cursor values still cannot bypass the authenticated tenant predicate.

## 4. Preparing Spring Boot and MongoDB

### 4.1. Dependencies

Required starters by capability:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The example assumes a compatible Spring Boot parent/BOM; do not hardcode individual starter versions when managed by a BOM. Configure the JWT resource server for your identity provider's issuer/audience; trust the tenant_id claim only after signature verification and tenant mapping confirmation.

### 4.2. Connection Configuration

Sample application.yml for Spring Boot 3.x:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}

server:
  shutdown: graceful
~~~

MONGODB_URI must be injected via a secret manager or secure runtime configuration. Replica set, TLS, and pool limits can be configured in the URI. Never commit real credentials. Property structure may differ in Spring Boot 4; verify your target version before applying.

Example MongoDB URI options **without credentials**:

~~~text
mongodb://db1.example.internal:27017,db2.example.internal:27017/shop?replicaSet=rs0&tls=true&maxPoolSize=40&minPoolSize=4&maxConnecting=2&serverSelectionTimeoutMS=2500&connectTimeoutMS=1500
~~~

**maxPoolSize bounds the pool per MongoClient per server**, not cluster-wide across pods. These numbers are starting candidates for load testing; check total pod count and MongoDB server capacity. If using Client-Side Operation Timeout (CSOT) with timeoutMS, understand how timeoutMS interacts with legacy timeouts. Coordinate Reactor timeouts and driver timeouts with your SLOs.

### 4.3. Index Matching Filter and Sort

Run once during provisioning/migration using an account with index-creation privileges:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_status_created_id" }
);
~~~

Explanation:

1. tenantId and status are equality predicates narrowing the scan range.
2. createdAt and _id match the descending sort order, avoiding large in-memory sorts.
3. _id acts as a unique tie-breaker for orders sharing the same createdAt.

If the application adds queries omitting status or sorting by other fields, re-run explain and evaluate additional indexes. Never create indexes inside HTTP requests; runtime MongoDB accounts typically do not need createIndex privileges.

## 5. Models and DTOs

### 5.1. Order.java

~~~java
package example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id ObjectId id,
    String tenantId,
    String status,
    Instant createdAt,
    long totalCents
) {}
~~~

Java records keep the example concise. In real systems, MongoDB documents must carry all required fields, especially createdAt and _id. Avoid nullable sort keys with keyset pagination; enforce types via converters and schema validation.

### 5.2. OrderView.java

~~~java
package example.orders;

import java.time.Instant;

public record OrderView(
    String id,
    String status,
    Instant createdAt,
    long totalCents
) {
    public static OrderView from(Order order) {
        return new OrderView(
            order.id().toHexString(),
            order.status(),
            order.createdAt(),
            order.totalCents()
        );
    }
}
~~~

The DTO omits tenantId and internal metadata not meant for clients. However, **omitting tenantId from the response is not access control**: the server-side query must filter by tenant before mapping results.

### 5.3. OrderPage.java

~~~java
package example.orders;

import java.time.Instant;
import java.util.List;

public record OrderPage(
    List<OrderView> items,
    boolean hasNext,
    NextCursor nextCursor
) {
    public record NextCursor(Instant createdAt, String id) {}
}
~~~

This design returns a bounded page of at most 100 items without computing totalPages or countDocuments on every page view. That avoids an expensive count query solely to check whether another page exists.

## 6. ReactiveMongoTemplate: Keyset Queries and Memory Bounds

### 6.1. Queries for the First and Subsequent Pages

First page:

~~~javascript
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(21);
~~~

The page following a document with createdAt = T and _id = I must satisfy:

~~~text
createdAt < T
OR
(createdAt = T AND _id < I)
~~~

This is lexicographical ordering for descending sort keys. Comparing only createdAt drops documents sharing the same timestamp; requiring both createdAt and _id to be strictly less incorrectly drops valid documents.

~~~javascript
const lastCreatedAt = ISODate("2026-11-18T08:30:00.000Z");
const lastId = ObjectId("65350f8453dbe413901c1211");

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(21);
~~~

### 6.2. OrderReadService.java

The following service contains full parameter validation, query construction, item bounds, and mapping of infrastructure errors to HTTP errors. Model classes from the previous section belong to the same **example.orders** package.

~~~java
package example.orders;

import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeoutException;

import com.mongodb.MongoTimeoutException;
import org.bson.types.ObjectId;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class OrderReadService {

    private static final int MAX_PAGE_SIZE = 100;
    private static final Set<String> ALLOWED_STATUS =
        Set.of("PAID", "PENDING", "CANCELLED");
    private static final Duration READ_DEADLINE = Duration.ofSeconds(3);

    private final ReactiveMongoTemplate template;

    public OrderReadService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<OrderPage> findPage(
            String tenantId,
            String status,
            int size,
            String afterCreatedAt,
            String afterId) {

        if (tenantId == null || tenantId.isBlank()) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Tenant scope is required"
            ));
        }
        if (status == null || !ALLOWED_STATUS.contains(status)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Unsupported order status"
            ));
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Page size must be between 1 and 100"
            ));
        }
        if ((afterCreatedAt == null) != (afterId == null)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Cursor requires both keys"
            ));
        }

        Instant cursorTime = null;
        ObjectId cursorId = null;
        if (afterCreatedAt != null) {
            if (!ObjectId.isValid(afterId)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid cursor id"
                ));
            }
            try {
                cursorTime = Instant.parse(afterCreatedAt);
            } catch (DateTimeParseException exception) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid cursor timestamp",
                    exception
                ));
            }
            cursorId = new ObjectId(afterId);
        }

        Query query = buildQuery(
            tenantId, status, size + 1, cursorTime, cursorId
        );

        return template.find(query, Order.class)
            // MongoDB limits output to at most size+1, so collectList is bounded.
            .collectList()
            .map(rows -> toPage(rows, size))
            .timeout(READ_DEADLINE)
            .onErrorMap(TimeoutException.class, exception ->
                new ResponseStatusException(
                    HttpStatus.GATEWAY_TIMEOUT,
                    "Order query exceeded the time budget",
                    exception
                )
            )
            .onErrorMap(MongoTimeoutException.class, exception ->
                new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Database temporarily unavailable",
                    exception
                )
            )
            .onErrorMap(DataAccessResourceFailureException.class, exception ->
                new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Database temporarily unavailable",
                    exception
                )
            );
    }

    private static Query buildQuery(
            String tenantId,
            String status,
            int fetchSize,
            Instant cursorTime,
            ObjectId cursorId) {

        Criteria scope = new Criteria().andOperator(
            Criteria.where("tenantId").is(tenantId),
            Criteria.where("status").is(status)
        );

        if (cursorTime != null) {
            Criteria older = new Criteria().orOperator(
                Criteria.where("createdAt").lt(cursorTime),
                new Criteria().andOperator(
                    Criteria.where("createdAt").is(cursorTime),
                    Criteria.where("_id").lt(cursorId)
                )
            );
            scope = new Criteria().andOperator(scope, older);
        }

        return Query.query(scope)
            .with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("_id")
            ))
            .limit(fetchSize);
    }

    private static OrderPage toPage(List<Order> rows, int size) {
        boolean hasNext = rows.size() > size;
        List<Order> visible = rows.subList(
            0, Math.min(rows.size(), size)
        );
        List<OrderView> items = visible.stream()
            .map(OrderView::from)
            .toList();

        OrderPage.NextCursor nextCursor = null;
        if (hasNext) {
            Order last = visible.get(visible.size() - 1);
            nextCursor = new OrderPage.NextCursor(
                last.createdAt(), last.id().toHexString()
            );
        }
        return new OrderPage(items, hasNext, nextCursor);
    }
}
~~~

**Why size + 1?** With size = 20, the query fetches at most 21 documents. If 21 arrive, return 20 and hasNext = true; if 20 or fewer arrive, hasNext = false. No full-collection count is needed. Because size is validated upfront, collectList never buffers unbounded documents.

**Why place timeout after collectList?** When the subscription does not complete within 3 seconds, Reactor emits TimeoutException and cancels the active subscription. This is an application-side time bound, not proof that MongoDB halts all server-side work immediately at that instant. Coordinate it with driver timeouts/CSOT, gateway timeouts, and verified cancellation behavior.

**Why not add retries inside the service?** Reads already benefit from driver retryable reads under qualifying conditions. Adding Reactor-level retries should only be done after measuring load impact, classifying recoverable failures, and checking remaining time budgets. In this lesson, we favor an explicit deadline and clear error reporting.

**Why not catch all Exceptions and return 503?** Mapping errors, bugs, and programming defects must surface as server errors. Map only identified infrastructure errors to 503/504; unclassified errors fall through to default error handling for investigation, with appropriate internal logging and non-leaky responses.

## 7. WebFlux Controller: Deriving Tenant from Verified Identity

### 7.1. OrderController.java

This example uses Spring Security OAuth2 Resource Server with a verified JWT. The tenant_id claim must be trusted only as issued by your identity provider and authorization policy.

~~~java
package example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderReadService service;

    public OrderController(OrderReadService service) {
        this.service = service;
    }

    @GetMapping
    public Mono<OrderPage> list(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam String status,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String afterCreatedAt,
            @RequestParam(required = false) String afterId) {

        if (jwt == null) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED, "Authentication required"
            ));
        }

        String tenantId = jwt.getClaimAsString("tenant_id");
        return service.findPage(
            tenantId, status, size, afterCreatedAt, afterId
        );
    }
}
~~~

The endpoint also needs a **SecurityWebFilterChain** enforcing authentication and JWT issuer/audience validation. Without security configured, merely declaring a Jwt parameter does not protect the endpoint. Never let clients pass tenantId in the URL and treat it as trusted identity.

### 7.2. Expected HTTP Statuses

| Scenario | Status | Meaning |
| --- | --- | --- |
| Valid query, with or without records | 200 | Returns OrderPage; items may be empty |
| Missing/invalid status, size outside 1–100, invalid cursor | 400 | Invalid request |
| No valid identity | 401 | Rejected by Spring Security/Controller |
| No authorized tenant scope | 403 | Cannot access tenant-scoped data |
| Reactor deadline exceeded | 504 in example | API did not finish within time budget |
| Mongo timeout or classified resource failure | 503 | Database temporarily unavailable |
| Unclassified bug or mapping error | 500 | Needs server-side logging/investigation |

Because the API returns a **Mono wrapping the full page**, HTTP status is decided before body bytes are written. That is a practical advantage when returning clean error codes. If switching to direct streaming, errors occurring after the first byte is flushed require a different strategy.

## 8. A Resource-Bounded API Must Bound Multiple Layers

### 8.1. Complementary Bounds

| Bound | Setting in this lesson | What it protects |
| --- | --- | --- |
| Page item count | Max size 100 | Response memory and payload size |
| Actual fetch | Query.limit(size + 1) | Prevents reading the entire collection |
| Pagination | Keyset by createdAt and _id | Avoids deep-page skip overhead |
| Time | Mono.timeout(3 seconds) | Prevents API requests hanging indefinitely |
| Connection pool | maxPoolSize, maxConnecting, minPoolSize | Protects sockets and MongoDB capacity |
| Request rate | Rate limit/quota at gateway or app | Stops one client from flooding requests |
| Fan-out | flatMap with explicit concurrency | Prevents excessive concurrent independent queries |
| Per-document payload | Schema, projection, size caps | Prevents huge responses even with few items |

Capping page size is not enough if documents contain large binaries or thousand-element arrays. In production, use projections to fetch only displayed fields and split GridFS content or large histories into separate endpoints.

When paginating by sort keys, projections must **keep all fields needed for the cursor**, such as createdAt and _id. Ordering can shift if documents are modified between reads; cursors alone do not provide snapshot isolation.

### 8.2. Sizing the MongoDB Pool for Load

Sample URI options:

~~~text
maxPoolSize=40&minPoolSize=4&maxConnecting=2
~~~

MongoClient maintains a pool **per server** in the topology. With 8 pods each configured with maxPoolSize=40, potential connections to a single primary can reach 320, plus monitoring and other services. Never treat maxPoolSize=40 as a global cluster limit.

An initial estimate can use Little's Law:

~~~text
Average active connections
≈ MongoDB operations/sec × Average connection hold time (sec)
~~~

For example, if each pod runs 120 MongoDB operations/sec with a 50 ms average hold time, average concurrency is roughly 6. However, bursts, slow queries, transactions, and background load push peak demand much higher. **Never set maxPoolSize equal to the average directly**; load test, measure checkout wait times, and correlate with MongoDB CPU/I/O.

### 8.3. Bounding Fan-Out with flatMap Concurrency

When querying multiple order IDs independently, cap concurrent inner publishers:

~~~java
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<Order> findSomeOrders(
        ReactiveMongoTemplate template,
        String authenticatedTenantId,
        List<ObjectId> ids) {

    if (ids.size() > 100) {
        return Flux.error(new IllegalArgumentException(
            "Too many requested ids"
        ));
    }

    return Flux.fromIterable(ids)
        .flatMap(id ->
            template.findOne(
                Query.query(Criteria.where("_id").is(id)
                    .and("tenantId").is(authenticatedTenantId)),
                Order.class
            ),
            8
        );
}
~~~

Here, 8 limits concurrent active inner queries in this pipeline stage, **not pool size**. Since flatMap may emit out of input order, evaluate flatMapSequential or concatMap along with latency trade-offs if order matters. Before firing 100 separate findOne queries, usually consider **a single `$in` query on `_id`** combined with tenant scope and proper indexing.

### 8.4. limitRate Does Not Bound Total Documents

**limitRate(n)** shapes downstream prefetch batch sizes; it does not cap the total items a pipeline emits, does not bound concurrent independent queries like flatMap(concurrency), and never replaces Query.limit. Likewise, an **unbounded onBackpressureBuffer()** can grow heap uncontrollably when the producer outpaces the consumer.

Bound the system at the database query, concurrency limits, and request rate. Backpressure coordinates flow only when publishers and operators honor demand signals.

## 9. When Should You Stream Flux Directly over HTTP?

### 9.1. NDJSON Streaming vs Paginated Responses

The API in Section 7 returns **Mono<OrderPage>**. The server holds at most size + 1 documents to compute hasNext, then sends a single JSON object. That lets you return 400/503/504 **before the HTTP body starts**, since query failures surface before the page completes.

When clients must consume documents incrementally as MongoDB emits them, Spring WebFlux can stream **NDJSON** (*Newline Delimited JSON*): each line is a standalone JSON object. This fits bounded exports, event streams, or read-only feeds consumed incrementally.

| Criterion | Mono<OrderPage> | Flux<OrderView> NDJSON |
| --- | --- | --- |
| HTTP shape | Single JSON object with items/hasNext | Multiple JSON objects, one per line |
| App memory | O(size), bounded item count | No need to collect full stream; still depends on buffers and downstream |
| Pre-body error handling | Easy to set HTTP status | Works if error occurs before the first byte |
| Mid-body error handling | Rare since response builds after query | Cannot change HTTP status; client may get truncated stream |
| Pagination | Built-in cursor/hasNext | Needs separate resume/cursor protocol for multi-page streaming |
| Typical use | List UIs, APIs needing crisp error codes | Bounded exports, incremental consumer pipelines |

**Do not choose direct streaming just because the service returns a Flux.** A Mono holding a bounded list is still reactive: MongoDB reads via the reactive driver, WebFlux does not block threads on I/O, and collectList is bounded by Query.limit.

### 9.2. Example Bounded NDJSON Endpoint

Add this method **inside OrderReadService** from Section 6, reusing the declared template and ALLOWED_STATUS fields:

~~~java
import java.time.Duration;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;

public Flux<OrderView> streamLimited(
        String tenantId, String status, int size) {

    if (tenantId == null || tenantId.isBlank()) {
        return Flux.error(new ResponseStatusException(
            HttpStatus.FORBIDDEN, "Tenant scope is required"
        ));
    }
    if (status == null || !ALLOWED_STATUS.contains(status)) {
        return Flux.error(new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Unsupported status"
        ));
    }
    if (size < 1 || size > MAX_PAGE_SIZE) {
        return Flux.error(new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Invalid stream size"
        ));
    }

    Query query = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is(status)
    )
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")
    ))
    .limit(size)
    .cursorBatchSize(32);

    return template.find(query, Order.class)
        .map(OrderView::from)
        .limitRate(32)
        // On Flux, timeout limits idle gaps between signals.
        .timeout(Duration.ofSeconds(2));
}
~~~

In **OrderStreamController.java**, you can expose:

~~~java
package example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/orders")
public class OrderStreamController {

    private final OrderReadService service;

    public OrderStreamController(OrderReadService service) {
        this.service = service;
    }

    @GetMapping(value = "/stream",
                produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<OrderView> stream(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam String status,
            @RequestParam(defaultValue = "20") int size) {
        if (jwt == null) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED, "Authentication required"
            ));
        }
        return service.streamLimited(
            jwt.getClaimAsString("tenant_id"), status, size
        );
    }
}
~~~

Client example:

~~~bash
curl --no-buffer \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Accept: application/x-ndjson" \
  "http://localhost:8080/api/orders/stream?status=PAID&size=20"
~~~

Each line returned is an OrderView, with no envelope containing hasNext. **cursorBatchSize(32)** hints batch size to the MongoDB cursor, while **limitRate(32)** controls Reactor downstream demand; they serve different roles. Neither replaces **Query.limit(size)** for bounding total records.

One crucial difference: on Flux, **timeout(Duration)** errors when **time until the first signal or between two signals** exceeds the threshold; it is not an overall stream wall-clock deadline. To bound total HTTP request duration, enforce a gateway/server deadline or a dedicated total-duration timeout, and test cancellation.

### 9.3. Errors After the HTTP Body Starts

Suppose the server has flushed 10 NDJSON lines, and MongoDB drops the connection before line 11. HTTP headers are already sent; the server cannot reliably switch HTTP 200 to 503. The client receives a truncated stream.

Therefore:

- For business pages requiring **all-or-error**, prefer bounded Mono<OrderPage>.
- For long streams, define explicit resume/checkpoint protocols; consumers must never treat truncated streams as complete.
- Never use onErrorResume to silently turn database errors into Flux.empty() or an empty page, which hides data loss.
- Logs and metrics must record mid-stream cancellations, post-commit errors, and emitted item counts, not just HTTP status codes.
- When clients disconnect, WebFlux cancels the subscription; verify in real tests that driver cursors and connections are released cleanly.

If using NDJSON for multi-page exports, never replace all limits with an unbounded find. Use batched/checkpointed cursors and total export quotas.

## 10. Error Handling in Reactive Pipelines

### 10.1. Categories of Errors to Distinguish

| Error | Example | Strategy |
| --- | --- | --- |
| Request error | size=10000, half-missing cursor, disallowed status | 400, never query MongoDB |
| Access error | Missing JWT, unauthorized tenant_id | 401/403 before querying |
| Transient infrastructure error | Server selection failure, socket/pool error | 503 or 504, never expose hostnames/URIs |
| Data/mapping error | Missing createdAt, wrong BSON type | Log enough to diagnose; never swallow into empty list |
| Business error | Action disallowed in current order status | Appropriate 4xx per contract |
| Unexpected bug | NullPointerException, coding error | 500 with correlation ID for log lookup |

In Section 6, the service uses **onErrorMap** for TimeoutException, MongoTimeoutException, and DataAccessResourceFailureException. Spring Data translates some driver exceptions into DataAccessException subtypes; observe the actual exceptions thrown under your mapping and version.

When an error occurs in a pipeline, Reactor emits a terminal **onError** signal; downstream operators stop receiving normal elements. To map errors consistently to HTTP contracts, use ResponseStatusException or a unified @RestControllerAdvice.

### 10.2. Why Never Return an Empty List on Database Errors?

Anti-pattern to avoid:

~~~java
// Anti-pattern: masking a database failure as a valid empty result.
return template.find(query, Order.class)
    .collectList()
    .onErrorReturn(List.of());
~~~

Clients will think zero orders exist when the server actually failed to reach MongoDB. That corrupts reports or triggers bad compensating actions. An empty list is valid only when the query succeeded and matched zero documents.

### 10.3. Controlled Retries

MongoDB Driver includes **retryable reads/writes** for qualifying operations. Avoid sprinkling arbitrary retries at the Reactive layer, as retries across HTTP clients, gateways, services, and drivers multiply attempts.

In a read-only pipeline, when retrying specific transient failures is genuinely warranted:

~~~java
import java.time.Duration;
import com.mongodb.MongoSocketException;
import reactor.util.retry.Retry;

Retry limitedRetry = Retry.backoff(1, Duration.ofMillis(100))
    .maxBackoff(Duration.ofMillis(300))
    .filter(error -> error instanceof MongoSocketException);
~~~

This is an illustrative **retry policy definition**, not wired into the main service yet. Attach retryWhen before the overall operation timeout only after verifying actual exception types (which Spring Data may wrap), retry safety, and total time budgets. Never retry auth, validation, or duplicate key errors.

For order writes, a timeout does not prove the write failed to execute; use business keys/idempotency and status reconciliation. Reactive MongoDB does not automatically make external side effects like payments or emails run once.

### 10.4. Multi-Layer Timeouts

Hypothetical time budget for an API with a sub-4-second SLO:

~~~text
HTTP gateway deadline                  4000 ms
Total MongoDB read at service          3000 ms
Remaining budget for auth/serialize    1000 ms
~~~

This is **a discussion example**, not an additive guarantee. Auth, network, queuing, and serialization times vary; measure real p95/p99 and leave headroom. If MongoDB Java Driver **timeoutMS** (CSOT) is enabled, check its interaction with Reactor timeouts and other options to avoid conflicting deadlines.

## 11. Automated Testing with Reactor StepVerifier

### 11.1. Verifying size + 1 and nextCursor

Sample unit test using Mockito to stub ReactiveMongoTemplate; this tests pagination logic and does not replace real MongoDB integration tests.

~~~java
package example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderReadServiceTest {

    @Mock
    ReactiveMongoTemplate template;

    private OrderReadService service;

    @BeforeEach
    void setUp() {
        service = new OrderReadService(template);
    }

    @Test
    void returnsBoundedPageAndNextCursor() {
        Instant timestamp = Instant.parse("2026-11-18T08:30:00Z");
        Order first = new Order(
            new ObjectId("65350f8453dbe413901c1213"),
            "tenant-A", "PAID", timestamp, 1000L
        );
        Order second = new Order(
            new ObjectId("65350f8453dbe413901c1212"),
            "tenant-A", "PAID", timestamp, 2000L
        );
        Order extra = new Order(
            new ObjectId("65350f8453dbe413901c1211"),
            "tenant-A", "PAID", timestamp, 3000L
        );

        when(template.find(any(Query.class), eq(Order.class)))
            .thenReturn(Flux.just(first, second, extra));

        StepVerifier.create(
                service.findPage("tenant-A", "PAID", 2, null, null))
            .assertNext(page -> {
                assertEquals(2, page.items().size());
                assertTrue(page.hasNext());
                assertEquals(second.id().toHexString(),
                    page.nextCursor().id());
            })
            .verifyComplete();

        ArgumentCaptor<Query> query =
            ArgumentCaptor.forClass(Query.class);
        verify(template).find(query.capture(), eq(Order.class));
        assertEquals(3, query.getValue().getLimit());
    }

    @Test
    void rejectsOversizedPageBeforeQuery() {
        StepVerifier.create(
                service.findPage("tenant-A", "PAID", 101, null, null))
            .expectErrorSatisfies(error ->
                assertInstanceOf(
                    org.springframework.web.server.ResponseStatusException.class,
                    error
                )
            )
            .verify();

        verifyNoInteractions(template);
    }
}
~~~

In this test, mocked data is emitted in expected order to check mapping; Mockito **does not verify that MongoDB uses indexes or executes sorts**. Real integration tests are needed for that.

### 11.2. Testing Database Errors and Timeouts

Cases to cover:

1. Mock Flux emitting MongoTimeoutException and verify Mono fails with ResponseStatusException 503.
2. Mock a never-completing Flux with Flux.never(); use **StepVerifier.withVirtualTime** to verify Duration timeouts without waiting real seconds.
3. Return 0 documents and verify items is empty, hasNext is false, and nextCursor is null.
4. Return exact size documents and verify no next page.
5. Return size + 1 documents and verify nextCursor comes from the last **returned** item, not the extra item.
6. Half-present cursor or invalid ObjectId must fail with 400 before touching MongoDB.
7. When an order lacks valid createdAt/id, tests detect the data defect instead of silently building a broken cursor.

Note: with virtual time, publishers and time operators must be constructed inside StepVerifier.withVirtualTime's supplier so the virtual scheduler hooks in properly; do not wrap a pre-built Mono subscribed elsewhere and expect virtual time to advance it.

### 11.3. Integration Testing with Real MongoDB

Use a MongoDB test container or test replica set compatible with the driver. The dataset should include:

- Tenant A and tenant B with orders in the same statuses.
- Multiple orders with **identical createdAt** and different _id values.
- Enough orders to span at least three pages with a small page size.
- Timestamps crossing UTC day boundaries.
- Empty collection and valid status with zero matching results.

Key tests:

| Test | Evidence required |
| --- | --- |
| Start from page 1 and traverse all pages via cursor | Every tenant A ID appears exactly once over static data |
| Tenant A supplies cursor pointing into tenant B data | Query still returns zero tenant B documents |
| Two orders share createdAt | Descending _id order, zero skips across page boundaries |
| Size limit | Each response has at most size items; query limits to size + 1 |
| Compound index usage | explain shows appropriate index and no unnecessary blocking sort |
| MongoDB disconnected | 503/504 per error category, no URI/password leaked |
| Client cancels NDJSON stream | Cancellation propagates to driver and resources release |
| 50–100 concurrent requests | Heap, event-loop, pool wait, and MongoDB CPU/I/O within bounds |
| Expired JWT / missing tenant claim | Rejected prior to query execution |

Tests where data updates during pagination must explicitly state the expected consistency contract. If an immutable snapshot is required, keyset pagination alone does not suffice; use a snapshot/watermark mechanism or matching data model. Never hold an open transaction across multiple HTTP requests just to freeze a list view.

## 12. Metrics and Incident Tracing

### 12.1. Essential Metrics

| Group | Metrics | Question answered |
| --- | --- | --- |
| HTTP | p50/p95/p99 latency, 4xx/5xx, request cancellations | How much are users impacted? |
| MongoDB command | duration, command errors, commands per request | Are queries slow or retrying/fanning out excessively? |
| Connection pool | checked-out connections, checkout wait, checkout timeouts | Is the pool saturated? |
| Server | CPU, I/O, connections, slow queries, replication lag | Does the database still have headroom? |
| Reactive | active subscriptions, buffers, cancellations | Are streams stalling or publishers leaking? |
| App limits | rate-limited requests, rejected sizes, timeouts | Are protective bounds actually firing? |

MongoDB Java Driver provides **ConnectionPoolListener** and **CommandListener**, integrable with Micrometer or your observability stack. Never put raw tenantId, orderId, or JWT values into **high-cardinality metric tags**. Never log raw queries holding personal data or MongoDB URIs containing secrets.

### 12.2. Analyzing an Overload Example

Suppose you observe:

~~~text
HTTP p95:                2900 ms
MongoDB command p95:      170 ms
Pool checkout p95:       1800 ms
Checked-out connections: 40 / 40
MongoDB CPU:              40%
~~~

These are illustrative numbers. Latency sits mainly in pool checkout wait; inspect unclosed cursors/transactions, concurrent subscriptions, fan-out, and MongoDB headroom before raising maxPoolSize incrementally.

Conversely:

~~~text
HTTP p95:                3400 ms
MongoDB command p95:     3000 ms
Pool checkout p95:         15 ms
MongoDB CPU:              95%
~~~

The bottleneck is query/server execution. Raising pool size will overload the server further. Inspect indexes, filters, sorts, explain plans, document sizes, and request volume, then throttle concurrency/rate limits if necessary.

### 12.3. Actionable Logging Without Secret Leakage

An acceptable operational log line:

~~~text
traceId=... operation=order_page status=timeout
size=20 elapsedMs=3000 queryShape=tenant_status_after_createdAt
~~~

Never include passwords, access tokens, full URIs, raw documents, or customer ID lists in logs. To troubleshoot a specific tenant, use controlled correlation and retention policies rather than emitting unbounded tenant labels on metrics.

## 13. Common Capstone Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Wrapping `mongoTemplate.find(...)` in `Mono.just(...)` | Blocking call runs eagerly before subscribe | Use ReactiveMongoTemplate and reactive driver |
| Calling `block()` in a WebFlux controller | Stalls event-loop, cuts throughput | Return Mono/Flux to the framework |
| Returning unbounded Flux and calling `collectList()` | Unbounded heap growth | Enforce Query.limit before collecting |
| Bounding only with `limitRate` | Total emitted documents can remain unbounded | Bound query and quota at source |
| Using large `skip` values | Deep pages waste server scan work | Use keyset pagination with unique tie-breaker |
| Using only `createdAt` as cursor | Skips documents sharing timestamps | Add `_id` and proper OR predicate |
| Reading `tenantId` directly from query params | Cross-tenant data exposure | Derive from verified auth/authz identity |
| Using `onErrorReturn(empty page)` on all errors | Clients mistake DB failure for zero orders | Map errors to proper HTTP statuses |
| Unbounded `retryWhen` on all errors | Retry storm, pool exhaustion, duplicate side effects | Classify errors, bound attempts and deadline |
| Raising `maxPoolSize` instead of fixing slow queries | Worsens MongoDB overload | Measure command latency, explain, and CPU |
| Using `ResponseEntity` mid-NDJSON body | Cannot alter already-committed status | Design error/resume protocol or use bounded pages |
| Never testing cancellation | Cursors/connections may leak | Test client disconnects and verify pool release |
| Mapping every exception to 503 | Hides real bugs and mapping errors | Map only identified infrastructure errors |

## 14. Practice Tasks and Acceptance Criteria

### 14.1. Tasks to Complete

Starting from a Spring Boot project with WebFlux and Spring Data MongoDB Reactive:

1. **Seed data:** at least two tenants, three order statuses, and multiple documents sharing identical createdAt values.
2. **Create index:** tenantId + status + createdAt DESC + _id DESC; verify via getIndexes/explain.
3. **Build API:** /api/orders accepting status, size, and afterCreatedAt/afterId; derive tenant from verified JWT.
4. **Enforce bounds:** size between 1 and 100, query fetches at most size + 1, one page retains at most 101 documents.
5. **Handle errors:** 400 for invalid inputs, 401/403 for auth/tenant errors, 503 for database resource failures, 504 for app deadlines.
6. **Test:** write StepVerifier and integration tests for paging, cursors, timestamp ties, cross-tenant isolation, timeouts, and empty results.
7. **Optional stream:** add bounded NDJSON streaming with cursorBatchSize, limitRate, and test client disconnects.
8. **Load bounds:** configure MongoClient pool sizing, run 10/50/100 concurrent requests, and record p95/p99, checkout wait, and command duration.
9. **Evaluate:** compare against a `skip` implementation and an unindexed version, verifying data correctness as well.

### 14.2. PASS Criteria

| Condition | Expectation |
| --- | --- |
| Zero MongoDB queries on bad requests | Unit test verifyNoInteractions or command metrics verify zero calls |
| No cross-tenant leaks | Every response contains only authorized tenant documents |
| Stable ordering over static dataset | Traversing all pages neither duplicates nor drops IDs |
| Bounded memory | No collectList on unbounded Flux |
| Transparent errors | Timeouts/DB failures never return 200 empty pages |
| Non-blocking event loop | Zero block()/sleep/blocking driver calls inside WebFlux handlers |
| Finite wait times | Requests never hang forever when backend stops responding |
| No retry amplification | No unbounded retry loops; driver default retries accounted for |
| Workload-appropriate pool | Checkout wait, MongoDB CPU/I/O, and HTTP SLOs meet team targets |
| Observable failures | Safe metrics/logs and correlation IDs for diagnostics |

### 14.3. Self-Assessment Questions

- Why is Mono<OrderPage> still a reactive design despite calling collectList?
- What problem does Query.limit(size + 1) solve that limitRate does not?
- Why must the MongoDB index include both createdAt and _id with matching sort directions?
- Why can a partially flushed NDJSON response not always return HTTP 503 on error?
- When Reactor's timeout triggers an error, can we assume MongoDB immediately stopped all command execution?
- Does maxPoolSize=40 across eight pods cap total cluster connections at 40?
- Why do we need both a verified JWT tenant claim and a tenantId predicate in the query?
- When can retries create duplicate orders or payments?

A reliable reactive pipeline is built from **properly scoped queries, bounded result sizes, stable pagination rules, well-placed timeouts, transparent error handling, and load-tested connection pools**. Mono/Flux types are only part of the picture; domain correctness and operational behavior determine whether an app can run safely in production.

## 15. References

- [Spring Data MongoDB – Reactive MongoDB Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/reactive-mongo.html): configuration and usage of the MongoDB Reactive Driver.
- [Spring Data MongoDB – Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): Query, Criteria, sort, limit, and timeouts.
- [Spring Data MongoDB – Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html): reactive repositories and data access.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive controllers, HTTP handling, and streaming.
- [Project Reactor – Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, backpressure, cancellation, timeout, and retry.
- [Reactor Test – StepVerifier](https://projectreactor.io/docs/test/release/reference/): testing publishers and virtual time.
- [MongoDB – Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/): key ordering and query performance.
- [MongoDB – cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/): limitations of offset pagination.
- [MongoDB Java Reactive Streams Driver](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/): reactive driver, configuration, and connectivity.
- [MongoDB – Connection Pool Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): maxPoolSize, minPoolSize, maxConnecting, and timeouts.
