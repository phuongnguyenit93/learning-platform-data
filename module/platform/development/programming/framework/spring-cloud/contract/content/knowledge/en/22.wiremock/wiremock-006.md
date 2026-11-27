# Verifying Call Counts and Actual Requests Received

**WireMock** does more than return mock responses for HTTP requests; it can also **record the requests that reached the stub server** and let you verify **call counts, paths, methods, headers, query parameters, and bodies**. This capability is essential when using **Spring Cloud Contract**: consumer tests do not merely prove "the client can read a sample response" but also check **what the HTTP client code actually sent and how many times**.

This lesson belongs to the **WireMock** chapter of the **SPRING_CLOUD_CONTRACT** module. The module covers defining agreements between producer and consumer via **Groovy/YAML DSL**, generating producer verification tests, packaging stubs, using **Stub Runner**, and integrating CI to catch incompatible API changes. Here we focus on the **request journal**, the `verify(...)` and `findAll(...)` APIs, the WireMock Admin API, and combining them with Stub Runner. We also clarify the boundaries: "the stub received the request" **does not mean** "the real producer executed the request," and a 404 response can simply mean **no mapping matched**.

## 1. Three questions to distinguish

Suppose **Billing Service** (consumer) calls **Order Service** (producer) to read order 42. The producer publishes the contract:

~~~http
GET /api/orders/42
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

In consumer tests, distinguish three verification layers:

| Question | How to observe | Meaning |
| --- | --- | --- |
| **What did the stub return?** | Assert status, headers, and body returned by `OrderClient`. | Consumer decodes and handles the contract response. |
| **What did the stub receive?** | Inspect the WireMock request journal, `verify`, `findAll`. | What requests the consumer actually sent, and how many times. |
| **Does the real producer honor the contract?** | Spring Cloud Contract's generated producer tests on Order Service. | Real producer implementation satisfies the published request/response. |

A consumer test asserting only `status=PAID` might miss that the client **called twice instead of once**. Conversely, a test verifying only that WireMock received one `GET` does not prove the client parsed the JSON properly. To protect integration, you usually need **both response assertions and request journal assertions**.

~~~mermaid
flowchart TD
    A["Groovy/YAML contract"] --> B["Producer verification tests"]
    B --> C["Real producer verified"]
    A --> D["Package HTTP stub mappings"]
    D --> E["Stub Runner / WireMock"]
    F["Consumer HTTP client"] -->|Real client request| E
    E -->|Sample response| F
    E --> G["Request journal"]
    G --> H["verify count, method, URL, headers, body"]
    F --> I["Response assertions and business handling"]
~~~

**Scope note:** entries in the request journal are what the **WireMock server saw**, not the producer's internal request log. It helps catch bugs in consumer code, but never replaces generated producer tests.

## 2. Request matching vs. request verification

WireMock performs two related but distinct tasks:

1. **Stub matching:** when an HTTP request arrives, WireMock finds a matching mapping to decide which response to return.
2. **Request verification:** after consumer code runs, the test queries the request journal to verify the **count** and **contents** of received requests.

Example of a mapping that can match:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/orders/42"
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": 42,
      "status": "PAID"
    }
  }
}
~~~

After the consumer sends a request to the stub, the test checks:

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

**Mappings** and **`verify`** can use similar matchers, but they operate at **two different times**. Mappings decide the response; `verify` checks requests that **already occurred**. The existence of a mapping does not prove the consumer called it, and a recorded request did not necessarily match a mapping.

## 3. Spring Cloud Contract creates stubs before request verification

The producer can place a contract at `src/test/resources/contracts/orders/get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Read paid order'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(id: 42, status: 'PAID')
    }
}
~~~

Or the same behavior in YAML DSL:

~~~yaml
description: Read paid order
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

Both files are **two ways to illustrate the same contract**; in an actual build, place **only one active version** in the path scanned by Contract Verifier. The producer runs generated tests to verify real code, then packages artifact `com.acme:order-service:1.0.0:stubs` for consumers.

The consumer uses Stub Runner to load the artifact and run WireMock with the generated mappings. The **call-count** checks in this lesson belong to **consumer tests**: they confirm client behavior when interacting with that stub. A contract describes HTTP request/response shapes; it **does not automatically impose a "must call exactly once" requirement** on every consumer.

## 4. Starting a standalone WireMockServer to learn the request journal

Before integrating Stub Runner, the simplest way to learn request verification is using **`WireMockServer`** directly in a JUnit 5 test. This example runs an HTTP stub on a dynamic port, keeping the test independent of external services.

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;

class OrderClientWireMockTest {
    private WireMockServer wireMockServer;

    @BeforeEach
    void startWireMock() {
        wireMockServer = new WireMockServer(
            wireMockConfig().dynamicPort()
        );
        wireMockServer.start();

        wireMockServer.stubFor(
            get(urlEqualTo("/api/orders/42"))
                .withHeader("Accept", containing("application/json"))
                .willReturn(okJson(
                    "{\"id\":42,\"status\":\"PAID\"}"
                ))
        );
    }

    @AfterEach
    void stopWireMock() {
        wireMockServer.stop();
    }

    @Test
    void callsOrderEndpointExactlyOnce() {
        OrderClient client = new OrderClient(wireMockServer.baseUrl());

        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.status()).isEqualTo("PAID");
        wireMockServer.verify(
            1,
            getRequestedFor(urlEqualTo("/api/orders/42"))
                .withHeader("Accept", containing("application/json"))
        );
    }
}
~~~

`OrderClient` above is Billing's **real consumer code**, implemented in the next section. The test uses **`wireMockServer.baseUrl()`** rather than guessing a port or hardcoding `localhost:8089`. Because a fresh server is created in `@BeforeEach`, each test method has a **clean request journal** and isolated mappings.

**Compilation requirements:** the project needs WireMock with matching APIs (`com.github.tomakehurst.wiremock`), JUnit Jupiter, AssertJ, and Spring Web/RestClient if using the client in section 5. Different WireMock/Spring Cloud Contract versions may have slightly different APIs or setup; check your project's dependencies and versions.

## 5. Real HTTP client code must be tested

For tests to be valuable to the consumer, call the **HTTP client class used by the application**, rather than firing a raw test-only HTTP call and claiming the business client works.

Example using **Spring RestClient** (Spring Framework 6.1+):

~~~java
package com.acme.billing;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient client;

    public OrderClient(String baseUrl) {
        this.client = RestClient.builder()
            .baseUrl(baseUrl)
            .build();
    }

    public OrderDto getOrder(long id) {
        return client.get()
            .uri("/api/orders/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status) {}
}
~~~

With this client, the test in section 4 simultaneously verifies:

- Consumer **sends GET** to `/api/orders/42`.
- Request includes `Accept` containing `application/json`.
- Client **parses JSON** into `OrderDto`.
- Stub **actually received exactly one call** matching the conditions.

If the client has automatic retries sending two requests to WireMock, `verify(1, ...)` will **FAIL**. That may be a bug or intended behavior depending on business rules. **Do not enforce "exactly once" blindly on every API**: understand the business contract and retry policy before choosing the expected count.

## 6. Verifying call counts: 0, 1, N and assertion limits

WireMock's standard verification form is:

~~~java
wireMockServer.verify(
    expectedCount,
    getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

Examples:

~~~java
// Expect exactly one GET for order 42:
wireMockServer.verify(
    1, getRequestedFor(urlEqualTo("/api/orders/42"))
);

// Ensure the client does not call any delete endpoint:
wireMockServer.verify(
    0, deleteRequestedFor(urlMatching("/api/orders/.*"))
);

// After an intentional batch, require exactly three POSTs:
wireMockServer.verify(
    3, postRequestedFor(urlEqualTo("/api/orders"))
);
~~~

When you need **at least** or **at most** some count, WireMock offers `moreThanOrExactly(...)`, `lessThanOrExactly(...)`, or comparing `findAll(...).size()` depending on version. In this lesson, a clear, configuration-light option is:

~~~java
int count = wireMockServer.findAll(
    getRequestedFor(urlEqualTo("/api/orders/42"))
).size();

assertThat(count).isBetween(1, 3);
~~~

**It counts requests matching the matcher**, not total arbitrary requests. If the consumer calls `GET /api/orders/42` once and `GET /health` twice, `verify(1, getRequestedFor(...))` still passes because only one request matched. If the goal is "only a single HTTP request reached the stub," inspect the **entire request journal** as well.

### 6.1. Exactly once in a test does not guarantee end-to-end exactly-once

Counting requests in WireMock can catch a duplicate call **in a specific test**, yet does not prove a distributed system guarantees exactly-once delivery under dropped connections, retries, timeouts, or redeliveries. For payment APIs, instead of asserting only "exactly one POST", you typically need an **idempotency key**, retry-handling contracts, and integration tests verifying business side effects are not duplicated.

Likewise, a happy-path test sending one request and passing `verify(1, ...)` can still hide a client that retries twice **on a 503**. To test retries, construct a **controlled failure scenario** and assert the actual retry policy in that situation.

## 7. Verifying request matchers: method, URL, query, headers, and body

When verifying requests, check **elements belonging to the contract or truly important to the consumer**.

### 7.1. Exact URL vs. path-only

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/42?view=summary"))
);
~~~

`urlEqualTo` checks the URL path and query as one string in that exact order, which can be overly strict regarding query parameter ordering. If the API treats query order as insignificant, use `urlPathEqualTo` with query matchers:

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlPathEqualTo("/api/orders/42"))
        .withQueryParam("view", equalTo("summary"))
        .withQueryParam("lang", equalTo("vi"))
);
~~~

This protects **parameter names and values** without forcing the consumer to place `view` before `lang` in the URL string. If the requirement is "no other query params allowed," inspect the actual request details or use an appropriate rule/schema; checking these two params **does not forbid extra parameters automatically**.

### 7.2. Verifying headers

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlPathEqualTo("/api/orders/42"))
        .withHeader("Accept", containing("application/json"))
        .withHeader("X-Correlation-Id", matching("[a-zA-Z0-9-]{8,64}"))
);
~~~

In HTTP, header names are case-insensitive, while **values and formats** can affect integration. Avoid verifying auto-generated headers (like `User-Agent` or `Connection`) unless consumer and producer treat them as part of the stable interface.

**For sensitive values** such as bearer tokens, you may check **presence or minimal format** when necessary, but never print real tokens in logs or examples. Seeing a token string in WireMock does not mean it **validated the signature, permissions, or expiration** of that token.

### 7.3. Verifying JSON body content

Suppose Billing sends an invoice creation request:

~~~http
POST /api/invoices
Content-Type: application/json
Idempotency-Key: invoice-ORD-1042

{"orderId":"ORD-1042","amountMinor":125000}
~~~

To verify key fields:

~~~java
wireMockServer.verify(
    1,
    postRequestedFor(urlPathEqualTo("/api/invoices"))
        .withHeader("Content-Type", containing("application/json"))
        .withHeader("Idempotency-Key",
                    equalTo("invoice-ORD-1042"))
        .withRequestBody(matchingJsonPath(
            "$.orderId", equalTo("ORD-1042")))
        .withRequestBody(matchingJsonPath(
            "$.amountMinor", equalTo("125000")))
);
~~~

**JSONPath note:** some matchers convert extracted values to strings for comparison, so `equalTo("125000")` here **is not a strict check of the JSON number type**. If the consumer must send a number rather than a string, verify the actual JSON type using Jackson as in section 9 (section 8.1), or use a type-aware JSON/schema matcher.

If the body must match **exact JSON structure**, use `equalToJson` rather than comparing raw byte strings verbatim:

~~~java
wireMockServer.verify(
    1,
    postRequestedFor(urlEqualTo("/api/invoices"))
        .withRequestBody(equalToJson(
            "{\"orderId\":\"ORD-1042\",\"amountMinor\":125000}"
        ))
);
~~~

Structural JSON comparison is typically **independent of object key ordering**. Options for ignoring extra elements or array order change strictness; enable them only when the real API does not promise those constraints.

## 8. Inspecting all received requests with findAll

`verify(...)` answers "did the expected number of requests match?". When a test fails or you need to inspect actual data, use the **request journal**:

~~~java
import com.github.tomakehurst.wiremock.verification.LoggedRequest;

List<LoggedRequest> requests = wireMockServer.findAll(
    getRequestedFor(urlPathEqualTo("/api/orders/42"))
);

assertThat(requests).hasSize(1);

LoggedRequest received = requests.get(0);
assertThat(received.getUrl()).isEqualTo("/api/orders/42");
assertThat(received.getHeader("Accept"))
    .contains("application/json");
~~~

These are **requests the server actually received**, not requests constructed by the test as expectations. When the client uses a different query string or omits a header, the journal reveals the discrepancy.

Diagnostic usage example:

~~~java
List<LoggedRequest> allOrders = wireMockServer.findAll(
    getRequestedFor(urlPathMatching("/api/orders/.*"))
);

for (LoggedRequest request : allOrders) {
    System.out.println(
        request.getMethod().getName() + " " + request.getUrl()
    );
}
~~~

**Never dump full requests containing Authorization headers, cookies, or personal data into CI logs**. When logging for investigation, print only non-sensitive fields, mask tokens, and limit record counts. For large payloads, assert or log critical JSONPaths instead of dumping the entire body.

### 8.1. Reading the actual body instead of relying only on JSONPath

~~~java
List<LoggedRequest> posts = wireMockServer.findAll(
    postRequestedFor(urlPathEqualTo("/api/invoices"))
);

assertThat(posts).hasSize(1);

String actualBody = posts.get(0).getBodyAsString();
JsonNode json = objectMapper.readTree(actualBody);

assertThat(json.get("orderId").asText()).isEqualTo("ORD-1042");
assertThat(json.get("amountMinor").isIntegralNumber()).isTrue();
assertThat(json.get("amountMinor").longValue()).isEqualTo(125000L);
~~~

Here `objectMapper` is a Jackson `ObjectMapper` initialized or injected by the test. The snippet illustrates part of a JUnit method with appropriate `throws Exception`/imports. Checking `isIntegralNumber()` protects an **integral JSON number**, rather than accidentally accepting a numeric-looking string `"125000"`.

## 9. Distinguishing matched and unmatched requests

WireMock can **record a request even when no mapping matches it**. For example, the mapping only allows:

~~~http
GET /api/orders/42
~~~

but the consumer sends:

~~~http
GET /api/order/42
~~~

The server still **receives an HTTP request**; it simply **does not match** the contract mapping, so it can return a default 404.

Related APIs:

~~~java
// Query requests that did not match any stub mapping:
List<LoggedRequest> unmatched =
    wireMockServer.findUnmatchedRequests();

assertThat(unmatched).isEmpty();

// Inspect served requests along with matching/response info:
var serveEvents = wireMockServer.getAllServeEvents();
assertThat(serveEvents).isNotEmpty();
~~~

`findUnmatchedRequests()` tells you whether any requests failed to match a mapping. `getAllServeEvents()` provides richer diagnostic data (request, mapping/response, and match status depending on version API). Avoid relying on unverified helper methods on `ServeEvent` when you only want to assert call counts.

**Important check:** `verify(0, getRequestedFor(urlEqualTo("/api/orders/42")))` can PASS when the client **called nothing at all**, and can also PASS when the client **called the wrong path**. If the test requires one successful call, assert a **positive count** and check consumer output; to catch malformed calls, assert an **empty unmatched journal** or inspect all received requests.

### 9.1. HTTP 404 alone does not prove a business error

A stub can return 404 in at least two cases:

1. There is an explicit **404 error contract**, a mapping matched and returned the `ORDER_NOT_FOUND` payload.
2. No mapping matched, so WireMock returned a **no-match** 404.

If a consumer test asserts only status 404, it can **pass falsely** in the second case—even if the client sent the wrong URL. To test business error handling, define a 404 contract with a body:

~~~json
{"code":"ORDER_NOT_FOUND","message":"Order does not exist"}
~~~

then assert `code=ORDER_NOT_FOUND` **and** verify the request matched the expected path/headers. `findUnmatchedRequests()` helps catch no-match cases when running WireMock with the request journal enabled.

## 10. Resetting the request journal for independent tests

Call counts are **stateful data** inside the stub server. If test A makes one call and test B runs `verify(1, ...)` on the same server without resetting, B can see **two calls** and fail. Choose an appropriate lifecycle:

| Reset approach | What is cleared | When to use |
| --- | --- | --- |
| `resetRequests()` | Recorded request journal. | Keep stub mappings, clear only history before each test. |
| `resetAll()` | Request journal and registered mappings/stub state. | Rebuild all stubs from scratch, typically with a self-managed server. |
| `resetScenarios()` | WireMock scenario states. | When using stateful mappings for retries or ordered request sequences. |
| **New server per test** | No shared request journal/mappings from earlier tests. | Cleanest way to prevent state leaks when resources allow. |

Example with a reused `WireMockServer`:

~~~java
@BeforeEach
void clearRequestHistory() {
    wireMockServer.resetRequests();
}
~~~

**Do not blindly call `resetAll()` in tests using Stub Runner** if your goal is keeping mappings loaded from contract artifacts: wiping mappings can make valid requests return 404. When you only need fresh request counts, use **`resetRequests()`** or isolate contexts/servers.

### 10.1. Parallel execution requires more than a reset

If tests A and B **write into the same request journal** concurrently, a reset can wipe a request the other test is about to assert. For reliable parallel execution:

- Give each test/class its **own `WireMockServer`** on a dynamic port.
- Or isolate each test's requests with a **correlation ID** and verify matchers by ID when servers truly cannot be separated.
- If sharing a Stub Runner context and mappings, manage parallel execution explicitly and avoid resetting the journal concurrently across tests.
- Never share a mutable global client port configuration across instances during parallel execution.

A request-counting test must have a clearly defined **measurement window**: from the reset (or fresh instance creation) until the client behavior under test completes.

## 11. Admin API: verifying requests on a Stub Runner HTTP server

In tests using **Stub Runner**, you usually have the **URL of the WireMock stub** rather than direct access to a `WireMockServer` bean. WireMock provides an **Admin API** to query the request journal over HTTP on that same stub server.

Common endpoints:

| Admin endpoint | Purpose |
| --- | --- |
| `GET /__admin/requests` | Retrieve the list of received requests. |
| `POST /__admin/requests/count` | Count requests matching a request pattern. |
| `POST /__admin/requests/find` | Find requests matching a pattern and retrieve actual records. |
| `GET /__admin/requests/unmatched` | List requests that matched no mapping. |
| `DELETE /__admin/requests` | Clear request history while keeping mappings intact. |

Example body sent to the **count API**:

~~~json
{
  "method": "GET",
  "url": "/api/orders/42",
  "headers": {
    "Accept": {
      "contains": "application/json"
    }
  }
}
~~~

Sample response:

~~~json
{"count":1}
~~~

**Do not confuse the Admin API with the producer's API.** `/__admin/requests/count` is a WireMock testing/observability endpoint, not an Order Service business endpoint. Access it only in trusted test environments; never expose the Admin API to the public Internet without access controls.

### 11.1. Counting via curl

Assuming the environment variable `STUB_URL` holds the base URL allocated by Stub Runner:

~~~shell
curl -sS -X POST "$STUB_URL/__admin/requests/count" \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","url":"/api/orders/42"}'
~~~

This command **does not need a hardcoded port**; `STUB_URL` might be `http://localhost:12543` or another address depending on the test environment. Obtain the URL from Stub Runner or verified environment config—**never guess** port numbers.

When searching for actual requests:

~~~shell
curl -sS -X POST "$STUB_URL/__admin/requests/find" \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","urlPath":"/api/orders/42"}'
~~~

These commands only illustrate the Admin API interface; there is no need to invoke shells inside every consumer test. It is better to write Java assertions that fail with clear diagnostics in CI.

## 12. Stub Runner + StubFinder + Admin API: consumer test example

A JUnit 5 consumer test can use **`StubFinder`** to resolve the dynamic URL of the Order Service stub, invoke real client code, and query the Admin count API to learn **how many times the stub received the request**.

~~~java
import java.net.URL;
import java.util.Map;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired
    private StubFinder stubFinder;

    @Test
    void callsCorrectOrderEndpointOnce() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub was not started"
        );

        String baseUrl = url.toExternalForm();
        RestClient admin = RestClient.create(baseUrl);

        // 1. Clear the journal for this test; do not delete stub mappings.
        admin.delete().uri("/__admin/requests")
            .retrieve().toBodilessEntity();

        // 2. Invoke the real consumer code.
        OrderClient client = new OrderClient(baseUrl);
        OrderClient.OrderDto result = client.getOrder(42L);

        assertThat(result.id()).isEqualTo(42L);
        assertThat(result.status()).isEqualTo("PAID");

        // 3. Verify the server received the expected request once.
        RequestCount count = admin.post()
            .uri("/__admin/requests/count")
            .contentType(MediaType.APPLICATION_JSON)
            .body(Map.of(
                "method", "GET",
                "url", "/api/orders/42"
            ))
            .retrieve()
            .body(RequestCount.class);

        assertThat(count).isNotNull();
        assertThat(count.count()).isEqualTo(1);
    }

    record RequestCount(int count) {}
}
~~~

**Execution prerequisites:** real consumer `OrderClient` code as in section 5; artifact `com.acme:order-service:1.0.0:stubs` installed into local Maven by the producer; compatible Spring Boot Test, Stub Runner, RestClient, Jackson, and AssertJ dependencies. This example assumes an isolated context/test; **do not reset the journal mid-run if other tests share the same stub instance**.

With `StubsMode.REMOTE`, Stub Runner downloads the artifact from the configured Maven repository while still starting WireMock on a dynamic port on the test machine. `StubFinder` returns the **URL of the running HTTP stub**, **not** the repository URL; the Admin API is called against that stub URL.

### 12.1. Inspecting more details of actual received requests

The Count API reports the **quantity**, without showing full request details. For deeper inspection, call:

~~~java
String journal = admin.get()
    .uri("/__admin/requests")
    .retrieve()
    .body(String.class);

// Parse the journal with Jackson JsonNode, reading only fields needed for assertions.
// Avoid printing the entire journal containing tokens/PII into CI logs.
~~~

Or POST `/__admin/requests/find` with a JSON pattern and inspect the returned request list. Across WireMock versions, some Admin response fields can vary; check your running version's API before hardcoding deep JSONPaths into the journal structure.

## 13. Testing retries: call counts can be an actual requirement

Suppose Billing has the requirement:

- When Order Service returns `200`: send only **one** GET.
- When encountering a transient `503` error: retry **at most twice**, meaning at most **three requests** per operation.
- When encountering a business `404`: **do not retry**.

This is a **consumer policy**, not something automatically derived from a happy-path HTTP contract. WireMock can use **scenarios** to return `503` on the first call and `200` afterward:

~~~java
import static com.github.tomakehurst.wiremock.stubbing.Scenario.STARTED;

wireMockServer.stubFor(
    get(urlEqualTo("/api/orders/42"))
        .inScenario("temporary-order-outage")
        .whenScenarioStateIs(STARTED)
        .willReturn(aResponse().withStatus(503))
        .willSetStateTo("recovered")
);

wireMockServer.stubFor(
    get(urlEqualTo("/api/orders/42"))
        .inScenario("temporary-order-outage")
        .whenScenarioStateIs("recovered")
        .willReturn(okJson("{\"id\":42,\"status\":\"PAID\"}"))
);
~~~

After invoking a client **configured with retry**, you can assert:

~~~java
wireMockServer.verify(
    2,
    getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

**Note:** this snippet only configures stub responses; it **does not add retry logic** to `OrderClient` from section 5. If the client has no retry policy, it stops at 503 with a call count of 1. A complete retry test needs **real client retry code**, error handling, and a response assertion after retrying—not merely expecting count 2 and assuming retries exist.

To verify "at most three requests," check `findAll(...).size()` within `1..3`. When verifying no retry on 404, define a **business 404 mapping** rather than relying on a no-match 404, and reset scenarios/journal at the proper time.

### 13.1. Request idempotency and duplicate submissions

For `POST /api/payments` or `POST /api/invoices`, repeating requests can cause side effects. The WireMock request journal tells you the consumer sent **two HTTP requests**, yet **does not fully simulate how the producer enforces idempotency**. If the API uses an `Idempotency-Key`, tests should check:

1. Every retry of the same transaction uses the **same key**.
2. Independent transactions use distinct keys.
3. Retry counts stay within policy with appropriate backoff/timeouts.
4. Producer integration tests verify **business side effects** are not duplicated.

Do not claim "exactly-once" merely because a happy-path Stub Runner test recorded one request.

## 14. Reading the request journal in async flows

A consumer may use `WebClient`, `CompletableFuture`, or dispatch requests asynchronously. If `verify` runs too early, the journal will not contain the request yet:

~~~java
client.getOrderAsync(42L); // Start the async operation.
wireMockServer.verify(
    1, getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

This test can **FAIL intermittently** because the HTTP request has not occurred yet when `verify` runs. **Await completion of the consumer operation** using an async primitive with an explicit timeout, then verify the request count:

~~~java
OrderDto order = client.getOrderAsync(42L)
    .get(3, TimeUnit.SECONDS);

assertThat(order.status()).isEqualTo("PAID");
wireMockServer.verify(
    1, getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

This illustrates a client returning a `CompletionStage`/`Future`; `OrderDto`, imports, and the async method must be provided by the project. With Reactor/`WebClient`, use `StepVerifier` with a deadline or await publisher completion in the test.

**Never use fixed `Thread.sleep` to "wait long enough"**: it neither guarantees the request arrived nor keeps CI fast/reliable. For background events without a completion future, use bounded conditional waiting such as Awaitility with specific matchers.

## 15. Avoiding overly strict or overly loose verification

Reliable checks reflect **exactly what the API and consumer behavior must uphold**.

| Check | When appropriate | Risk |
| --- | --- | --- |
| `verify(1, getRequestedFor(urlEqualTo(...)))` | Exactly one call to a fixed URL is required. | May be too strict when retries are allowed. |
| `urlPathEqualTo` + `withQueryParam` | Query parameter order does not matter. | Does not automatically forbid extra query params. |
| `withHeader("Accept", containing(...))` | Verify the client asks for JSON. | May be too weak if the API requires an exact media type. |
| `matchingJsonPath("$.orderId", ...)` | Verify key fields regardless of key order. | Can miss extra fields or type errors unless checked separately. |
| `equalToJson(...)` | Verify JSON body structurally. | Must decide on extra elements/array order. |
| `findUnmatchedRequests().isEmpty()` | Detect requests outside declared mappings. | A very broad mapping can still accept business-invalid requests. |
| `getAllServeEvents()` | Diagnose served requests/responses. | Does not replace intentional assertions. |

In particular, a **stub's request matcher** may be looser than the matcher used in `verify`. For example, the stub accepts `GET /api/orders/.*`, whereas the consumer contract allows only numeric IDs `/api/orders/[0-9]+`; a stub returning success for an invalid path does not prove the client is right. Pick strict-enough matchers and **assert the actual sent requests**.

Conversely, avoid asserting JSON key order or auto-generated headers outside the contract: a valid HTTP client upgrade can trigger false failures.

## 16. CI: combining producer verification, Stub Runner, and the request journal

An end-to-end contract-level testing flow:

~~~mermaid
flowchart TD
    A["Producer updates API/contract"] --> B["Verifier generates producer tests"]
    B --> C{"Producer verification passes?"}
    C -->|No| D["Block stub publish"]
    C -->|Yes| E["Package stubs-classifier artifact"]
    E --> F["Publish selected version"]
    F --> G["Consumer CI fetches stub via Stub Runner"]
    G --> H["Run real client code, receive sample response"]
    H --> I["WireMock records request journal"]
    I --> J["Assert count, URL, headers, body, no-match"]
    J --> K["Evaluate consumer compatibility"]
~~~

Key checklist:

1. **Verify producer tests are actually generated and run**, rather than treating a stubs JAR's existence as proof the producer fulfills the contract.
2. **Pin the stub version** in consumer CI; avoid silently drifting artifacts.
3. **Use Stub Runner's actual URL/port**, e.g., via `StubFinder`, avoiding hardcoded `localhost:8089` in parallel runs.
4. **Isolate the request journal** per test/context, resetting only when safe for other tests.
5. **Assert responses** from real client code and **assert the request journal** at the right strictness.
6. **Check unmatched requests** when catching wrong paths/headers/bodies outside mappings.
7. **Never log sensitive data** from the journal. Filter or redact relevant fields when debugging.
8. **Distinguish test wiring errors from API errors**: missing stub, connection refused, no-match 404, and business error responses are not the same.

### 16.1. Practical verification scenarios

| Consumer scenario | What to verify from the journal | What else to check |
| --- | --- | --- |
| Read an order successfully | One `GET` with right path/query/Accept. | Parsed `PAID` and producer verification. |
| Submit an invoice | One `POST` with right body and Idempotency-Key. | Producer does not create duplicate invoices in business tests. |
| Retry after 503 | Call count matches policy; requests are consistent. | Retries only on eligible errors; backoff/timeouts. |
| Hit business 404 | No unintended retries. | 404 mapping with error body; client handles properly. |
| Multiple producer stubs | Request appears in the journal of the **right** stub instance. | Resolved URL, version, and per-producer behavior. |
| Parallel execution | Journal does not mix requests across tests. | Isolation by test context/port/correlation ID. |

## 17. Common errors and diagnostics

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `verify(1, ...)` reports 0 requests. | Client never called, called wrong stub URL, or matcher is too strict. | Check actual URL, `getAllServeEvents()`, `findUnmatchedRequests()`, and journal. |
| `verify(1, ...)` reports 2 requests. | Client retried, called twice, or journal kept earlier test requests. | Inspect retry policy, journal reset, and isolation. |
| `200` response succeeds yet header verify FAILS. | Client omitted header or header matcher mismatches. | Inspect actual request; fix client code or agreed rules. |
| WireMock returns 404. | Request matched no mapping or mapping returns business error. | Check unmatched journal and mappings; assert error body for business 404. |
| Request body test PASSES despite number becoming string. | JSONPath matcher compares text without enforcing type. | Parse body with `JsonNode`, assert `isIntegralNumber()`/schema. |
| `findAll(...)` returns history from another test. | Shared server without resetting request journal. | Use a server per test, or reset cleanly when non-parallel. |
| `resetAll()` makes all requests return 404. | Wiped Contract Stub Runner's mappings too. | Use `resetRequests()` to clear only the journal; reload mappings if needed. |
| Request missing from journal despite HTTP call succeeding. | Journal disabled, querying wrong WireMock instance, or call hit another server. | Check recording/journal config, URL, instance, and test setup. |
| Flaky async test. | `verify` runs before the HTTP request finishes. | Await future/publisher with a deadline before reading journal. |
| Admin API errors or unreachable. | Wrong host/port, proxy blocking admin, version difference, or secured. | Resolve Stub Runner URL, check permissions/API; never expose admin publicly. |
| Producer test green yet consumer sends wrong path. | Producer verification only tests producer implementation with sample inputs; consumer client has its own bug. | Run consumer tests with real client code and verify the request journal. |

For serious issues, follow the order **right artifact → right stub URL → did the request arrive → did the request match → what response was returned → call count and request contents → consumer policy**. Avoid altering contracts just to mask test configuration bugs.

## 18. Practice exercise: from response assertion to request verification

On an Order Service producer with Spring Cloud Contract Verifier and a Billing Service consumer:

1. **Define the contract** `GET /api/orders/42` returning `200` with JSON `{"id":42,"status":"PAID"}` using Groovy or YAML DSL.
2. **Run generated producer tests**, verifying the real Order Service satisfies the contract; package/install or publish artifact `com.acme:order-service:1.0.0:stubs`.
3. **Create a standalone `WireMockServer`** on a dynamic port to practice `verify(1, ...)`, `findAll(...)`, `findUnmatchedRequests()`, and `resetRequests()`.
4. **Write a real `OrderClient`** sending GET with `Accept: application/json` and parsing JSON into a DTO. Use this client in tests rather than a raw test-only HTTP client.
5. **Assert response and count**: `id=42`, `status=PAID`, exactly one GET to `/api/orders/42`.
6. **Intentionally break client code** to call `/api/order/42`; confirm the journal records an unmatched request and the test FAILS. Restore.
7. **Intentionally call twice**; observe `verify(1, ...)` FAIL, then update test or client per business requirements rather than changing the expected count arbitrarily.
8. **Add a JSON POST** with `orderId` and `amountMinor`; use `matchingJsonPath`, then parse `LoggedRequest.getBodyAsString()` with Jackson to verify an actual JSON number.
9. **Switch to Stub Runner** loading the real artifact, resolve the URL via `StubFinder`, and use the Admin count API to verify exactly one request without needing a `WireMockServer` bean.
10. **Check journal state across tests**, try parallel execution, and apply resets/isolation so tests are order-independent.
11. **Test a 503 → 200 retry scenario** with WireMock scenarios, checking call counts and timing against the client's actual policy.
12. **Integrate into CI**: producer verification → publish stubs → consumer Stub Runner → response + request journal assertions; keep deterministic artifact versions and never log tokens.

**Completion criteria:** you can prove **exactly which requests WireMock received**, **how many times**, **which parts of the request were verified**, **which requests matched no mapping**, and explain clearly **why consumer test results do not replace producer verification**.

## 19. Self-check questions

1. What is the difference between **request matching** when returning a response and **request verification** after the client makes a call?
2. Why does the existence of a WireMock mapping not prove the consumer called the endpoint?
3. Does `verify(1, getRequestedFor(...))` count all requests hitting the server or only requests matching the matcher?
4. Under what circumstances can `verify(0, ...)` PASS and lead you to the wrong conclusion?
5. When should you use `urlPathEqualTo` combined with `withQueryParam` instead of `urlEqualTo`?
6. Why might `matchingJsonPath("$.amountMinor", equalTo("125000"))` fail to protect the JSON number type?
7. What are the differences between `findAll(...)`, `findUnmatchedRequests()`, and `getAllServeEvents()`?
8. Why is `resetAll()` a poor choice if you want to preserve Stub Runner mappings?
9. Why is a 404 response from a stub not always a business 404 error from the producer?
10. When Stub Runner does not expose a `WireMockServer` bean, which Admin API endpoint can check call counts?
11. Why does `StubsMode.REMOTE` not mean the Admin API should be called against the Maven repository URL?
12. If a client retries after 503, what else should be verified besides request count?
13. In async tests, why must you await completion of the operation before reading the request journal?
14. Why can a request journal containing data from an earlier test break tests even when neither producer nor consumer changed?

**Remember:** **WireMock's request journal tells you which requests the stub received and how many times**, whereas mappings decide which responses are returned. Use `verify(...)` to check counts and matchers, `findAll(...)`/`getAllServeEvents()` to inspect actual requests, `findUnmatchedRequests()` to detect no-match calls, and the **Admin API** when you only have Stub Runner's URL. Isolate the journal per test, validate request headers/bodies accurately, distinguish business 404s from no-match 404s, and pair **consumer tests with producer verification** before releasing stubs. That way, a contract test protects both the **API promise** and **how the consumer actually uses that promise**, rather than merely confirming a stub returns sample JSON.
