# Contrasting Mock Limits with Real Service Behavior

A Spring Boot adapter calling a partner API can pass every unit test: the request hits the expected URI, the mock returns valid JSON, and the app maps it into the right domain object. Yet in production, the partner returns `429 Too Many Requests`, closes idle HTTP connections, or changes a field from `"12.50"` to numeric `12.50`. All of those cases **fall outside the behavior scripted into the mock**. Passing tests prove your app handles *assumed scenarios*, not full compatibility with the real service.

This lesson belongs to the **Contracts and Edge Cases** chapter of the **SPRING_BOOT_INTEGRATION** module. Across HTTP clients, databases, caches, message brokers, and Spring Integration adapters, the goal goes beyond matching request/response samples: you must safeguard **data contracts**, **transactions**, **errors**, **deduplication**, **testing**, **observability**, and end-to-end flow recovery.

This lesson shows how to design a multi-layered testing strategy contrasting **what mocks prove**, **what only real protocol tests uncover**, and **what must be verified directly with the provider or integration environment**.

## 1. Mocks test assumptions; real services run a whole system

Suppose an ordering app checks stock availability from Inventory Service:

~~~text
GET /stocks/SKU-1
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-1","available":12}
~~~

A mock can be programmed to return that exact response every time. Yet the real provider might:

- Require OAuth tokens and enforce per-resource scopes.
- Return `404` for unknown SKUs, `429` when over quota, or `503` during maintenance.
- Return `200` with extra fields, `null` values, Unicode characters, or empty collections.
- Paginate results, use `ETag`s, or serve eventually consistent state.
- Close idle connections, return chunked/gzip bodies, or require valid TLS certificates.
- Enforce per-tenant limits, evolve business rules over time, or vary responses by persisted state.

No mock knows these rules automatically—it only knows what the test author wrote. After every green test, ask: **did this test confirm a truth about the provider, or merely an assumption written by the consumer team?**

### 1.1. Distinguishing test doubles commonly grouped as “mocks”

| Type | Where it runs | What it verifies | What it does NOT prove |
| --- | --- | --- | --- |
| **Interface mock/spy** (Mockito) | Inside test JVM | Method calls, arguments, branching rules, call counts | HTTP serialization, headers, TLS, transport errors, provider contract |
| **Stub/fixture** | In tests or data files | Mapping of sample responses and scripted errors | Whether real responses actually match those samples |
| **Spring `MockRestServiceServer`** | Intercepts at Spring HTTP client layer | URI, method, headers, body built by `RestClient`/`RestTemplate`; handling of fake responses | Real sockets, DNS, TLS, connection pooling, provider behavior |
| **HTTP mock server** (WireMock, MockWebServer) | Separate server, usually loopback/container | Real HTTP over sockets, status/headers/body, scripted timeouts/delays | Real business logic, production auth/quotas/DB on provider |
| **Contract test with provider verification** | Consumer + provider-side verification | Current provider satisfies agreed interactions | Full state combinations, concurrency, network, performance, operations |
| **Real service in sandbox/staging** | Real provider and dependencies in test env | Provider's configured behavior, auth, persistence, protocols, state | Production parity if data/quotas/networks differ |
| **Canary / production observability** | Real traffic path under controlled rollout | Behavior under live operational conditions | Rare faults or unhit scenarios |

In daily practice, **mock** is sometimes used as shorthand for any test double. When evaluating test confidence, state clearly **which layer** ran, whether **real sockets/networks** were involved, whether the provider ran **actual production code**, and where **state/data** originated.

## 2. Identify the source-of-truth contract before writing mocks

If fixtures are crafted by looking at current client code and having a mock server return whatever the client expects, tests merely reinforce misunderstandings. Authoritative sources should have clear owners and version tracking.

Common contracts in `SPRING_BOOT_INTEGRATION`:

| Boundary | Primary contract | Common drift points |
| --- | --- | --- |
| **REST/HTTP** | OpenAPI, JSON Schema, status codes, headers, error/throttling rules | `null` vs. absent, enums, `Retry-After`, empty bodies, idempotency keys |
| **SOAP/XML** | WSDL, XSD, bindings, SOAPAction, SOAP Faults | Namespaces, QNames, element ordering, SOAP 1.1 vs. 1.2 |
| **Kafka/AMQP** | Avro/Protobuf/JSON schemas, routing, keys, ack/retry/DLT policies | Schema evolution, key distribution, ordering, redeliveries |
| **Database** | Schema migrations, constraints, transaction isolation, SQL semantics | Unique keys, locks, decimal precision, rollbacks, timezones |
| **Redis/cache** | Key patterns, TTLs, serialization, consistency and fallback policies | Key expiry, eviction, thundering herds, stale values |
| **Spring Integration** | Payload/header/channel/`errorChannel` and ack/commit boundaries | Unwired error channels, non-durable async handoffs |

**A formal contract is more than a schema.** For write APIs, define how long idempotency keys live, which responses signify durable acceptance, state transition ordering, which timeouts yield uncertain outcomes, and which errors are retryable. Those rules often live in domain specs or integration agreements rather than raw OpenAPI.

Curate fixtures with clear provenance:

~~~text
src/test/resources/contracts/inventory/
  openapi.yaml
  response-stock-available.json
  response-stock-not-found.json
  response-stock-throttled.json
  response-stock-null-field.json
  request-reserve-stock.json
  response-reservation-accepted.json
~~~

Document the contract source and version for each fixture (e.g., provider schema release date or mutually approved snapshot). Captures taken from real services must **strip tokens, PII, passwords, and payment data** before committing to repositories.

## 3. A limit matrix for mocks

To choose tests wisely, map **the behavior you want to guarantee** to **the smallest layer capable of proving it**:

| Scenario | In-process mock | HTTP mock server | Provider/sandbox or real test infra |
| --- | --- | --- | --- |
| Map valid JSON to DTO | Good | Good | Optional cross-check |
| Client sends right method/URI/headers | Partially testable | Good over sockets | Confirms provider accepts them |
| Provider returns required fields/types | Assumed via fixture | Assumed via fixture | Requires schema/provider verification |
| HTTP `429` then `200` | Simulates retry logic | Good over real requests | Verifies real quotas/`Retry-After` |
| DNS/TLS/certificates | No | Limited on loopback; custom TLS possible | Needs realistic network/TLS tests |
| Server closes idle connection | No | Can inject transport faults | Needs real pools, proxies, endpoints |
| Race between two requests | Usually no | Local concurrency only | Needs real provider/state store under load |
| DB rollback/locks/unique constraints | Mock repository proves nothing | No | Real Testcontainers/RDBMS |
| Broker redelivery/rebalance/ack | Mock publisher proves nothing | No | Real Kafka/RabbitMQ test broker |
| Cache TTL/eviction/failover | Mock `Map` proves nothing | No | Real Redis with TTL/faults |
| Duplicate messages emitted on retry | Can assert call counts | Counts HTTP requests | Checks target idempotency and side effects |
| Throughput, quotas, backpressure | Almost never | Helps simulate selected faults | Load/staging/production telemetry |

This table shows mocks are **far from useless**—they remain the fastest way to lock down mappers, error branches, and retry policies. Trouble begins when results from one layer are used to claim guarantees belonging to another.

## 4. Spring Boot example: same adapter via mock and real socket

Suppose the Inventory API contract states:

- `GET /stocks/{sku}` returns `200 application/json` with `sku` (string) and `available` (non-negative integer).
- `404` means the SKU does not exist.
- `429` may include `Retry-After`, signaling rate limiting.
- Extra fields may appear, while required fields must never disappear.

Minimal adapter class:

~~~java
import org.springframework.web.client.RestClient;

// Spring Framework 6.1+; illustrated in Spring Boot with RestClient support.
record Stock(String sku, int available) {}

public final class InventoryGateway {
    private final RestClient client;

    public InventoryGateway(RestClient client) {
        this.client = client;
    }

    public Stock getStock(String sku) {
        return client.get()
                .uri("/stocks/{sku}", sku)
                .retrieve()
                .body(Stock.class);
    }
}
~~~

This illustrative adapter assumes upstream callers configure `404/429` policies; production adapters should map errors to domain types, validate required fields, and apply timeouts and retries. Using primitive `int` for `available` risks masking the difference between `null` and `0` depending on deserialization rules. For mandatory fields, prefer `Integer`, explicit validation, or custom mappers, and test missing/`null` inputs.

### 4.1. Narrow unit/integration test with MockRestServiceServer

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class InventoryGatewayMockTest {

    @Test
    void mapsStockFromExpectedJson() {
        RestClient.Builder builder =
                RestClient.builder().baseUrl("http://inventory.invalid");
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        InventoryGateway gateway = new InventoryGateway(builder.build());

        server.expect(requestTo(
                "http://inventory.invalid/stocks/SKU-1"))
              .andExpect(method(HttpMethod.GET))
              .andRespond(withSuccess(
                  "{\"sku\":\"SKU-1\",\"available\":12}",
                  MediaType.APPLICATION_JSON));

        Stock stock = gateway.getStock("SKU-1");

        assertThat(stock).isEqualTo(new Stock("SKU-1", 12));
        server.verify();
    }
}
~~~

This verifies `RestClient` produces a request accepted by the matchers and Jackson maps the scripted response into `Stock`. It **never opens a socket to `inventory.invalid`** and proves nothing about whether the real provider serves that URL or payload.

To prevent tests from merely mirroring mock assumptions, add negative cases: body missing `available`, `available=null`, wrong types, new enums, unexpected `Content-Type`, and error statuses. To verify contract conformance, validate against JSON Schema/OpenAPI or enforce explicit boundary checks.

### 4.2. HTTP mock server to test real transport

Using the exact same `InventoryGateway`, now point it at **MockWebServer** on loopback. Traffic traverses a real HTTP client and socket:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}
~~~

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

class InventoryGatewayWireTest {

    @Test
    void sendsRequestAcrossActualHttpSocket() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "application/json")
                    .setBody("{\"sku\":\"SKU-1\",\"available\":12}"));
            server.start();

            HttpClient httpClient = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(1))
                    .build();
            JdkClientHttpRequestFactory factory =
                    new JdkClientHttpRequestFactory(httpClient);
            factory.setReadTimeout(Duration.ofSeconds(2));

            InventoryGateway gateway = new InventoryGateway(
                    RestClient.builder()
                              .baseUrl(server.url("/").toString())
                              .requestFactory(factory)
                              .build());

            Stock actual = gateway.getStock("SKU-1");

            assertThat(actual).isEqualTo(new Stock("SKU-1", 12));
            RecordedRequest request =
                    server.takeRequest(1, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("GET", request.getMethod());
            assertEquals("/stocks/SKU-1", request.getPath());
        }
    }
}
~~~

An HTTP mock server exercises real TCP requests, client header/body parsing, timeouts, connection reuse, and response modes that `MockRestServiceServer` bypasses. Even so, **the server returns test-scripted payloads**—it still does not verify contracts against the real provider.

Extend MockWebServer/WireMock tests to return `429` with `Retry-After`, `503` then `200`, error bodies, slow responses, and mid-stream disconnects. To test DNS, TLS, proxies, firewalls, or stale pooled connections, run TLS-enabled test servers or Toxiproxy/Testcontainers and inspect all requests, responses, and metrics.

## 5. Bringing the real provider into the contract verification loop

A **consumer-driven contract test** lets the consumer publish the interactions it relies on: requests, statuses, headers, body structures, and example values. With tools like **Pact**, the consumer emits a pact file and the provider executes verification against its real codebase.

~~~mermaid
flowchart LR
    U["Consumer test"] --> P["Pact / Contract artifact"]
    P --> V["Provider verification"]
    V --> S["Provider code + test state"]
    V --> R["Compatibility result"]
    R --> C["CI / deploy gate"]
    C --> I["Sandbox integration test"]
~~~

### A complete contract cycle

1. **Consumer defines real needs:** only fields it reads, required statuses/errors, headers, auth expectations, and domain scenarios.
2. **Provider runs verification:** checks interactions against live provider code, preparing state per case (SKU in stock, out of stock, unknown, throttled).
3. **Publish versioned results:** tie verification results to consumer/provider versions or commits so CI can evaluate compatibility.
4. **Test in sandbox:** verify real auth, routing, networking, databases, rate limits, and deployment config.
5. **Observe on release:** watch contract errors, deserialization failures, unexpected statuses, and failure rates.

**Consumer contracts do not replace the full provider contract.** If the consumer hasn't handled `429` yet, its pact may omit that case. If provider verification mocks repositories with synthetic states, it also fails to prove provider transactions and concurrency work on a real database.

### Classifying compatible vs. breaking changes

| Provider change | Risk and how to verify |
| --- | --- |
| Add optional JSON field | Usually compatible if consumers ignore extra fields; still check strict deserializers |
| Drop or change type of required field | Usually breaks consumers; contract tests must fail |
| `null` instead of required value | Can slip past primitive defaults; validate domain constraints |
| Rename endpoint, path parameter, enum, or status | Check against contract and error-classification policies |
| Change `200` returning data to `202` async | Semantic shift: callers must poll/handle callbacks/reconcile |
| Change `409` conditions on duplicate requests | Affects idempotency; test with reused keys |
| Add API quotas/rate limits | Schema stays identical while breaking retry/throughput behavior |
| Change pagination or default sort order | Can skip/duplicate items when consumers use cursors/offsets |
| Change event schema or broker key distribution | Impacts consumer compatibility, ordering, and partition assignment |

A “schema-compatible” change can still break business semantics. For instance, if the provider switches inventory updates from synchronous to eventual consistency, responses stay `200` yet immediate read-after-write sees stale stock.

## 6. Edge-case bugs that mocks commonly hide

### 6.1. Data and serialization

- **Absent vs. `null` vs. empty string vs. `0`.** If a required field disappears while a Java DTO uses primitive `int`, the app silently receives `0`; enforce explicit validation.
- **Decimals:** use `BigDecimal` for money/exchange rates and test scale/rounding; a mock returning `12.50` will not catch a provider sending `"12.50"`.
- **Dates/times:** timezone offsets, DST, date-only vs. timestamps, microsecond/nanosecond precision; sandbox data may use only one timezone.
- **Unicode/encoding:** accented names, emojis, escaped characters, `Content-Type` charsets, embedded newlines.
- **Empty lists and pagination:** zero results, final pages, expired cursors, records shifting between pages.
- **Future enums/fields:** policies for unknown values; never default unknown enums to success.
- **Abnormal bodies:** bodyless HTTP 204, `200` with empty body, malformed JSON, oversized payloads, or compression.
- **XML/SOAP:** namespace URIs, QNames, XSD sequence ordering, SOAP Faults, `SOAPAction`, and SOAP 1.1 vs. 1.2.

### 6.2. HTTP semantics missed by simple matchers

| Detail | Easily skipped in mocks | Impact on real calls |
| --- | --- | --- |
| `Content-Type` and `Accept` | Comparing JSON bodies only | Provider returns 415/406 or parser picks wrong codec |
| `Authorization`, scopes, mTLS | Stubs accept every call | Production returns 401/403 or fails TLS handshake |
| Redirects 301/302/307/308 | Returning 200 directly | Client switches HTTP method, drops auth headers, or ignores redirects |
| `Retry-After`, per-tenant quotas | Mock returns a single 503 | Retry storms, account throttling |
| `ETag`, `If-Match`, `If-None-Match` | Ignoring optimistic concurrency | Overwriting newer data or missing updates |
| Idempotency keys and retention | Mock returns 200 on every POST | Duplicate records created after timeouts |
| Timeout after server completed | Mock always replies cleanly | Client cannot tell whether server committed |
| Connection reuse and keep-alive | No real sockets | Stale connections, pool exhaustion, mid-request EOFs |
| Chunked, gzip, truncated bodies | Body always delivered as one string | Parse failures, hangs, timeouts |
| DNS, proxies, certificates | Unconfigured in tests | Connections fail despite valid DTO mapping |

Test **error contracts** explicitly: error shapes, application codes, empty error bodies, correlation headers, and permanent vs. transient separation. Never write `catch (Exception)` and retry every error: retrying bad data amplifies load and masks root causes.

### 6.3. Timeouts and ambiguous success

Suppose the consumer sends:

~~~text
POST /reservations
Idempotency-Key: order-1024-reserve
Content-Type: application/json

{"orderId":"ORD-1024","sku":"SKU-1","quantity":1}
~~~

The provider commits the reservation, then the connection drops before the response returns. The client sees only a timeout. If a mock simulates this by executing `throw new SocketTimeoutException()` **before** updating mock state, the test verifies retry survival without testing the worst failure: **the side effect already happened**.

A meaningful test must:

1. Give the mock provider a **state store**: the first request persists the reservation and intentionally drops the response.
2. Have the client retry with **the same idempotency key**, or query transaction status by ID.
3. Have the provider replay the stored result / recognize the duplicate per contract.
4. Assert **exactly one reservation** exists even when HTTP request count exceeds one.
5. Re-run the scenario in the provider sandbox to confirm real key retention and response behavior.

If a provider lacks idempotency or reconciliation APIs, document that guarantee limit clearly. `@Transactional` inside the consumer cannot roll back a mutation already committed in a remote HTTP service.

## 7. Mock repositories differ from real databases

An in-memory `Map<String, Order>` in unit tests cannot faithfully reproduce isolation levels, unique constraints, transaction rollbacks, deadlocks, lock timeouts, SQL data types, or connection pool recovery.

Example deceptive test:

~~~java
// Mock repository: verifies save() was invoked.
verify(orderRepository).save(any(Order.class));
~~~

This does not prove the order committed or behaves accurately under two concurrent requests. Scenarios to verify against real PostgreSQL/MySQL/SQL Server (via Testcontainers or test DBs):

- Two concurrent requests with the same business key race to insert; unique constraints allow only one valid commit.
- A transaction fails mid-way and rolls back both business state and outbox in **the same DB transaction**.
- DB commits while outbound broker/API send fails; outbox stays `PENDING` and retries cleanly.
- Pool drops connections or DB fails over; stalled transactions do not appear successful and new transactions recover.
- SQL dialects between H2 and real RDBMS: collations, locks, JSON types, date/time types, upserts, and isolation levels.

**H2 in-memory databases are handy for many tests**, yet cannot replace your production database engine when tests depend on locking, transactions, or SQL dialects. At critical boundaries, run compatible database versions in containers.

## 8. Broker mocks do not prove delivery or commits

A test asserting:

~~~java
verify(kafkaTemplate).send(eq("orders.events"), any());
~~~

only shows code **invoked** `send`, not that the broker persisted the log or downstream consumers succeeded. Likewise, mocking `RabbitTemplate` proves nothing about publisher confirms, ACKs, redeliveries, or dead-lettering.

| Boundary | Where test doubles help | What needs a real broker |
| --- | --- | --- |
| Kafka producer | Message/key mapping, topic, header selection | Serialization, broker ACKs, timeouts, idempotent producer, network errors |
| Kafka consumer | Handler/mapper logic on sample events | Partition assignment, committed offsets, rebalances, redeliveries |
| RabbitMQ publisher | Exchange/routing-key mapping | Publisher confirms/returns, unroutable messages, exchange/binding wiring |
| RabbitMQ consumer | Handler branches, business error policies | `ack/nack/requeue`, prefetch, dead-lettering, consumer restarts |
| Spring Integration adapter | Payload/header transforms, routing rules | Executor queues, `errorChannel`, ack/transaction boundaries, scheduler concurrency |

Integration tests with Testcontainers Kafka/RabbitMQ should test **crashing after side effects and before ack/commit**. When records redeliver, the database must show business keys blocked duplicate mutations. In Kafka, consumer groups re-read uncommitted records on partition reassignment; in RabbitMQ, unacked messages redeliver when channels/connections close.

**Exactly-once semantics** within certain Kafka pipelines do not automatically turn external SQL transactions or HTTP calls into one atomic unit. You still need **inboxes/deduplication**, transactional outboxes, idempotency keys, or reconciliation.

## 9. Caches and async flows: real state differs from fake maps

Mocking Redis as a plain `Map` hides **TTLs**, evictions, connection drops, serialization bugs, memory pressure, and cache-miss races. Real tests should cover:

- Key expiration per policy; falling back to the DB or controlled stale values.
- Multiple concurrent misses on a hot key without flooding the DB with hundreds of identical queries (cache stampede).
- Cache update failing after DB commit; safe invalidation/rebuild paths.
- Never using a cache as the sole idempotency store if TTLs or evictions expire sooner than replay windows.

In Spring Integration, differences between **`DirectChannel`** (usually synchronous on caller thread), **`ExecutorChannel`** (offloads to an executor), and **`QueueChannel`** (buffered queue) cause unit tests to misjudge completion timing. Asserting “`send()` was called” proves neither DB commit nor broker ACK.

Across async boundaries, track `accepted`, `in_flight`, `completed`, `failed`, and `outstanding` by **message ID**. Never mark work succeeded while it sits only in an in-memory queue that vanishes on crash.

## 10. Load testing, fault injection, and post-recovery behavior

Beyond data shapes, real providers exhibit operational traits: connection pools, concurrency limits, rate limits, circuit breakers, retry backoffs, timeouts, and outage recovery dynamics.

A happy-path mock test reveals nothing about what happens when 200 threads hit a slow partner simultaneously. Combine:

- **Network fault injection** (Toxiproxy or test-env network shaping) for disconnects, latency, resets, throttling, and flapping links.
- **HTTP fault servers** for 429/503, empty responses, malformed payloads, `Retry-After`, slow bodies, or dropped responses after side effects.
- **Load tests** across multiple producers/consumers and replicas at controlled rates and concurrency.
- **DB/broker integration tests** for timeouts, transaction rollbacks, redeliveries, stale pools, rebalances, and backlogs.
- **Provider sandboxes** to validate real rate limits/quotas, credentials, certificates, test data, and live behavior.

Typical recovery loop:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot Consumer
    participant Mock as Fault proxy / downstream
    participant Outbox as Durable outbox
    participant Target as Target service
    App->>Outbox: Persist outbound intent
    App->>Mock: Call outbound
    Mock--xApp: Timeout / 503
    Note over App,Outbox: Bounded retries; stays PENDING
    Target-->>Mock: Downstream healthy again
    App->>Mock: Retry with backoff + idempotency key
    Mock->>Target: Forward request
    Target-->>Mock: Reply
    Mock-->>App: Outcome
    App->>Outbox: Mark completed
~~~

This test passes only if accepted work reconciles cleanly, backlogs drain to target levels, zero duplicate side effects occur, and recovery triggers no **retry storm**. Derive `p95/p99`, `time_to_resume`, and `time_to_drain` thresholds from real SLOs.

Mocks cannot prove target capacity. Real load tests must run only in authorized environments with controlled data and bounded volume so providers are never disrupted.

## 11. A practical multi-layered testing strategy

~~~mermaid
flowchart TB
    A["Unit tests: mapping, policy, validation"] --> B["HTTP/SOAP mocks: requests & edge errors"]
    B --> C["Consumer contracts + provider verification"]
    C --> D["Testcontainers: real DB/cache/broker"]
    D --> E["Sandbox integration: real provider"]
    E --> F["Canary + metrics in production"]
    F --> G["Capture new edge cases into fixtures/tests"]
    G --> A
~~~

Notice this diagram illustrates **increasing levels of evidence**, not a requirement that every test run sequentially or on every single pull request.

### 11.1. Allocation across pipeline stages

| Stage | Priority tests | Deployment blockers |
| --- | --- | --- |
| **Every commit/PR** | Unit/mappers, mock HTTP/SOAP, schema validation, consumer contract tests | Broken mapping, requests, error policies, or schemas |
| **Provider CI** | Provider verification against published consumer contracts | Provider change breaking verified interactions |
| **Integration CI** | Testcontainers DB/broker/cache, HTTP fault injection, crash windows | Broken transactions, commits, acks, timeouts, or idempotency |
| **Pre-release** | Provider sandbox + real auth/network/config, contract version checks | Bad credentials, endpoints, quotas, SSL, or behavior drift |
| **Scheduled/staging** | Load, concurrency, recovery, and failover | Pool exhaustion, stuck backlogs, retry storms |
| **Post-release** | Canary/telemetry/tracing and data reconciliation | Schema drift, unexpected statuses, error spikes, duplicate effects |

Contract/provider verification cycles should track **traceable versions**: consumer version, provider version, contract ID, verification outcome, and environment. “Contract tests passed last month” does not prove today's provider build remains compatible.

### 11.2. Prioritize by risk

Not every minor path requires a heavy end-to-end suite. Classify each integration by risk:

1. **Impact:** could failures lose money, drop orders, leak data, or cause outages?
2. **Rate of change:** does the provider update contracts often, or is the API highly stable?
3. **Observability:** do traces, correlation IDs, reconciliation, and business-key metrics exist?
4. **Reversibility:** is it a read-only GET or an irreversible state-mutating POST?
5. **Infrastructure coupling:** multiple replicas, pools, transactions, brokers, caches, or simple stateless mapping?

High-risk flows warrant deeper layering: provider verification, real databases/brokers, fault injection, and side-effect reconciliation.

## 12. Turning production discrepancies into regression tests

A practical workflow when mocks stay green yet production breaks:

1. **Capture safe evidence:** operation, endpoint alias, request/response statuses, correlation ID, timestamp, provider version, deserialization error, and key headers (stripping tokens and sensitive payloads).
2. **Classify the discrepancy:** data contract, business semantics, HTTP/transport, auth, state/sync, concurrency, or operational behavior.
3. **Confirm with the provider:** did the response diverge from schema or did the consumer assume too strictly? Distinguish bugs from intentional changes.
4. **Build reproducing fixtures/tests:** add the offending payload, status code, timeout, idempotency check, or fault injection.
5. **Update contracts:** when contracts changed, align versions and compatibility rules and add provider verification.
6. **Test at the right layer:** do not add only a unit mock for a socket fault; do not write a heavy E2E test for a simple mapper fix.
7. **Monitor after fixing:** build dashboards for that error class, reconciled record counts, and real business impact.

Production bug example: after deployment, the consumer breaks on `{"available":null}` even though every prior mock returned numbers. Proper regression coverage adds: a `null` fixture, boundary validation yielding a clear contract error, contract/provider verification clarifying whether `null` is permitted, and a downstream test ensuring orders are never placed when stock is unknown.

### Anti-patterns to avoid

| Anti-pattern | Why it gives false confidence | Fix |
| --- | --- | --- |
| Mocking every repo/HTTP/broker and calling it E2E | Skips real transactions, protocols, and state | Add Testcontainers or real integration environments |
| Stubbing responses directly from consumer DTOs | Tests agree with consumer assumptions, hiding schema drift | Use versioned provider-backed contracts |
| Testing only HTTP 200 | Misses error statuses/bodies, retries, timeouts, semantics | Build a success + error + boundary + recovery matrix |
| Asserting raw full JSON/XML strings | Breaks over whitespace or meaningless key order | Assert schemas, JSON paths, XML namespaces/QNames |
| Using only clean happy-path fixtures | Misses `null`, Unicode, outliers, pagination, malformed data | Add equivalence partitions and negative fixtures |
| Verifying only that `send()` was called | Does not prove broker ACKs or side effects | Test publish/consume against real brokers with idempotency |
| Testing only that connectivity recovered | Misses backlogs, retry storms, duplicates | Reconcile accepted/completed/outstanding counts |
| Retrying every exception | Amplifies permanent errors, adds load, duplicates mutations | Classify errors, cap budgets/backoff, enforce idempotency |
| Running staging against purely mocked data | Hides constraints and real state divergences | Test with controlled provider test states |
| Ignoring contract verification at deploy time | Green CI fails to guard what actually ships | Gate artifacts/deployments on verification matrices |

## 13. Hands-on exercise: assessing confidence in an Inventory integration

Sample flow: Spring Boot accepts an order, calls `POST /reservations`, writes PostgreSQL, publishes `StockReserved` to Kafka, and updates a Redis cache.

### Step 1: Map the contract

Document valid requests/responses, schemas, statuses `200/201/202/400/404/409/429/503` (including only codes the provider publishes), idempotency keys, correlation IDs, timeouts, retry policies, and eventual consistency. Record the source for every assumption.

### Step 2: Test at the adapter layer

Use `MockRestServiceServer` to verify URIs, headers, JSON serialization, and error mappers. Use MockWebServer to verify HTTP over sockets, slow responses, and status/header handling. Include negative cases in both.

### Step 3: Verify contracts with the provider

Author consumer contracts for `reservation accepted`, `duplicate key`, `out of stock`, and `rate limited` where agreed. Have the provider run verification with matching test states. Verify at least one full flow in a sandbox with real TLS and auth.

### Step 4: Test against real databases and brokers

Run Testcontainers PostgreSQL, Kafka, and Redis. Test unique keys, rollbacks, outbox, broker ACKs, redeliveries, cache expiration, and restarts. Deliberately crash after DB commit and before ACK to prove duplicate protection.

### Step 5: Inject faults and load

Configure the provider to return `503` and `429`, then recover. Sever the connection after the server processes POST and before returning a reply. Fire concurrent requests with identical keys and distinct keys. Verify backoff, queue bounds, idempotency, SLOs, and backlog draining.

### Step 6: Reconcile outcomes

Check per `orderId`/`eventId`: valid reservations hold accurate states, business transactions ended cleanly, outbox items emitted or are retrying safely, Kafka consumers avoided duplicate effects, and caches do not serve stale data beyond policy.

**Pass criteria:** explicitly state which test layer proves each requirement, never claim mock evidence proves real provider behavior, catch at least one edge-case defect with a negative test, and prove end-to-end data accuracy after retries and restarts.

## 14. Pre-release integration review checklist

- [ ] Request/response, error, and business-behavior contracts have authoritative sources and versions.
- [ ] Mock fixtures match provider OpenAPI/WSDL/schema/event contracts.
- [ ] Tested missing fields, `null`, unknown enums, wrong types, Unicode, empty bodies, and pagination/cursors.
- [ ] Tested 4xx/5xx statuses, `429`, `Retry-After`, timeouts, and ambiguous responses.
- [ ] Real HTTP client tested over sockets; TLS/DNS/proxies verified in suitable environments.
- [ ] Consumer contracts verified by the provider with results linked to deployed versions.
- [ ] Critical transactions, unique keys, and locks verified on a production-equivalent database.
- [ ] Brokers and caches tested for ACKs, redeliveries, TTLs, failover, and schema evolution where relevant.
- [ ] Retry side effects guarded by idempotency/reconciliation; outbox/inbox tested at crash windows.
- [ ] Overload, connection recovery, backpressure, and backlog draining tested against SLOs.
- [ ] Metrics/tracing reveal schema drift, unexpected errors, and duplicate business mutations.
- [ ] Production incidents converted into regression tests at the right layer with contracts updated as needed.

**Conclusion:** Mocks catch bugs quickly across behaviors you explicitly scripted; real services also enforce **state, protocols, resource limits, concurrency, and operational rules** that mocks often leave out. Systematically cross-checking with schemas, provider verification, real HTTP transport, Testcontainers, sandboxes, and post-deploy telemetry turns “green mocks” into solid evidence that your Spring Boot integration flows work reliably even across edge cases.
