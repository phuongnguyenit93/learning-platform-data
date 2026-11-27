# Producer Tests Pass, Yet the Consumer Is Still Incompatible

An **Order Service** pipeline may report all generated producer contract tests as PASSING, yet immediately after release, **Billing Service** still fails when calling the API. Billing might fail to deserialize the response, send the wrong header, mishandle 404/409 statuses, misread monetary units, or load a different `stubs` JAR than the contract the producer just verified. A green producer test result is essential evidence, yet **it does not automatically prove every supported consumer is compatible with the producer release about to ship**.

In **Spring Cloud Contract**, producer verification tests are generated from Groovy/YAML contracts and run against the producer implementation. They answer: **does the producer satisfy the scenarios described in the contract?** Consumer tests with **Stub Runner** answer a different question: **can the consumer's client/listener code work with the selected stub behavior?** For both results to mean something together, contracts must reflect real consumer needs, consumer tests must exercise the real client, artifacts must match versions, and release/deployment must stay tied to the exact verified contracts.

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_CONTRACT** module. The module covers producer–consumer contract testing over HTTP or messaging, defining behavior via Groovy/YAML DSL, generating producer tests, publishing stubs, using Stub Runner, and integrating CI to detect incompatible API changes. This lesson focuses on **producer tests passing while the consumer remains incompatible**, spanning evidence scoping through request, response, artifact, DTO, semantics, transport, and release process diagnosis.

## 1. What Do Green Producer Tests Actually Prove?

Suppose Order Service has the contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'

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
        body(
            id: 42,
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

When generated producer tests PASS, you have evidence that **under that build's test mode/base test/fixtures**, the described request triggered the producer and the response satisfied the assertions generated from the contract.

This result **does not automatically prove**:

- Every API endpoint, query parameter, header, error response, and business state is covered.
- Every live version of Billing has a compatible DTO/HTTP client.
- The consumer is loading the exact `stubs` artifact of the producer release just verified.
- The deployed Docker image matches the source that passed producer verification.
- Production gateways, TLS, authentication, compression, proxies, and networks behave like the test context.
- Existing events in brokers, retries, DLQs, or replays are compatible.
- Matchers are not so loose that a wrong-valued response still passes on type alone.

**Producer verification proves the implementation matches what the contract asks for; the strength of that proof depends on contract coverage and precision.**

## 2. Four Kinds of Evidence That Must Connect

~~~mermaid
flowchart TD
    A["Consumer needs + Groovy/YAML contracts"] --> B["Producer generated verification"]
    A --> C["Packaged stub artifact"]
    B --> D["Verified producer release"]
    C --> E["Consumer Stub Runner tests"]
    E --> F["Real consumer client/listener"]
    D --> G["Deployed producer image"]
    G --> H["Runtime API/message behavior"]
    F --> I["Compatibility evidence"]
    H --> I
~~~

| Evidence | Question Answered | Limitation |
| --- | --- | --- |
| **Generated producer test** | Does the producer implementation satisfy the contract scenario? | Covers only scenarios/assertions generated and executed. |
| **Stub Runner consumer test** | Does consumer code work with the selected stub artifact? | Does not prove the production producer image matches the stub without release/deploy linkage. |
| **Artifact provenance** | Which producer commit/build produced the stubs JAR? | Does not prove which image was deployed or whether runtime config differs. |
| **Runtime/deployment evidence** | Which producer image/version serves live traffic and what does it return? | Does not replace thorough testing across all consumer scenarios. |

**Never infer the other three from a single PASS.** When an incident occurs, identify which link in the evidence chain is missing or mismatched.

## 3. Example: Order Service and Billing Service

The producer publishes:

~~~http
GET /api/orders/42
Accept: application/json
~~~

Contract response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

The Billing client uses DTO:

~~~java
package com.acme.billing;

import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderDto(
    long id,
    String status,
    long amountMinor,
    String currency
) {}
~~~

Here, if the client calls the right endpoint and the actual response follows the schema, the DTO deserializes cleanly. Yet the following changes can still break Billing:

| Actual Producer Response | Potential Consumer Failure |
| --- | --- |
| `amountMinor` changes from number to string | Jackson/DTO may fail conversion or alter semantics. |
| `currency` is omitted | Consumer receives `null`/default or fails validation. |
| `status` changes from `PAID` to `SETTLED` | Enum mapping or business branches fail to recognize the new value. |
| `amountMinor` shifts meaning from minor units to major units | JSON parses cleanly yet monetary amounts are wildly wrong. |
| `Content-Type` switches to another media type | Message converter skips the JSON converter. |
| Status changes from `200` to `202` | Client treats data as incomplete or takes another branch. |
| Path moves to `/api/v2/orders/42` | Older client still calls v1 or receives 404. |
| 404 body changes schema | Error decoder cannot extract error codes. |

**Many failures cannot be caught by a single happy path.** Contracts must include scenarios representing the behaviors consumers rely on, and consumer tests must exercise the real client with meaningful data.

## 4. Cause 1: Contracts Do Not Represent Consumer Needs

A producer might write a contract covering only the happy path:

~~~text
GET /api/orders/42 -> 200
~~~

While Billing also relies on:

- Specific `Accept` and `Authorization` headers.
- Query parameters `include=payment` or `currency` if specified by the API.
- `404` when an order does not exist.
- `403` when a token lacks scope.
- `409` when an order is in a non-payable state.
- Error payloads with `code` and `message` mapped to domain exceptions.
- Monetary, timezone, idempotency, and retry semantics.

A green producer test on the happy path **proves nothing about those remaining scenarios**.

### 4.1. Write Contracts Around Consumer-Visible Behavior

Contracts should reflect **what callers observe and depend on**, not internal controller structure. Example adding an error scenario:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnOrderNotFound'

    request {
        method 'GET'
        url '/api/orders/999'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND',
            message: 'Order does not exist'
        )
    }
}
~~~

This is an **additional scenario** for API errors. It lets producer verification enforce the promised 404 response and lets consumer tests verify error mapping. `message` text may need a flexible matcher if not guaranteed verbatim; error `code` is usually more critical than display text.

### 4.2. Consumers Must Participate in Contract Review

A consumer-driven or collaborative producer/consumer workflow should:

1. Have consumers state the **request/response/message behaviors** their clients genuinely need.
2. Have producers confirm they can uphold those semantics and compatibility guarantees.
3. Review schemas, required fields, types, enums, errors, headers, auth, and retries jointly.
4. Commit contracts to a source with clear ownership.
5. Run producer verification against the implementation.
6. Run consumer Stub Runner tests against the real client/listener.

**Producer-authored contracts can still be valid**, yet if the producer does not know what consumers depend on, contracts easily miss critical scenarios.

## 5. Cause 2: Overly Broad Matchers Give False-Green Producer Tests

A contract may use:

~~~groovy
bodyMatchers {
    jsonPath('$.status', byType())
    jsonPath('$.amountMinor', byType())
}
~~~

Type matchers help when values legitimately vary while **JSON types must hold**. However, if Billing's fixture requires `status=PAID` and `amountMinor=125000`, type-only checks let this slip through:

~~~json
{
  "status": "CANCELLED",
  "amountMinor": -1
}
~~~

Producer tests PASS type assertions even though business data is completely wrong.

| Field | Checks to Consider |
| --- | --- |
| `id` tied to request ID | Equality or request–response invariant. |
| `status` in a PAID scenario | Equality/enum semantics, not merely string type. |
| `amountMinor` | Numeric type + value/range/business invariant. |
| `currency` | Required field and published enum/code. |
| Dynamic `createdAt` | Pattern/parse validity and timezone policy. |
| Dynamic `traceId` | Presence/format, not equality with a sample ID. |

**Do not loosen matchers just to make producer tests green.** Test with mutations: a valid change must PASS; a semantics-breaking change must FAIL.

## 6. Cause 3: Consumer DTO or Deserializer Differs from the Contract

Even when responses match the contract, the consumer can deserialize wrongly due to:

- Java field name differing without matching `@JsonProperty`/naming strategy.
- DTO declaring `int` while the producer returns values overflowing 32-bit integers.
- Consumer enum lacking a new value the producer began emitting.
- Consumer using `LocalDateTime` while the API returns timestamps with offsets/timezones.
- Consumer requiring non-null fields while the contract allows missing/`null`.
- Jackson enforcing strict unknown-property rejection when the producer adds a field.
- Consumer converters not supporting the actual media type.

### 6.1. Field Names and DTOs

If the producer returns:

~~~json
{
  "order_id": "ORD-42",
  "amount_minor": 125000
}
~~~

while the consumer DTO uses:

~~~java
public record OrderDto(
    String orderId,
    long amountMinor
) {}
~~~

confirm the actual mapping convention. You can use:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderDto(
    @JsonProperty("order_id") String orderId,
    @JsonProperty("amount_minor") long amountMinor
) {}
~~~

**Do not rename contract fields just to match an old DTO** if the producer already published a different schema and the consumer needs updating. First confirm the real JSON response matches the contract; then fix DTO/client mapping or adjust the contract via a reviewed API decision.

### 6.2. Unknown Fields and Missing Fields

`@JsonIgnoreProperties(ignoreUnknown = true)` helps older DTOs ignore **unused new fields**:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderDto(
    long id,
    String status,
    long amountMinor,
    String currency
) {}
~~~

Yet this annotation **does not synthesize missing fields**, does not resolve renamed fields, and does not guarantee semantics. If `currency` is required and the producer omits it, the consumer may receive `null` or a default; enforce explicit validation and error handling.

Do not enable ignore-unknown globally without checking schema policy. Some APIs intentionally use closed schemas to catch producers emitting out-of-contract fields.

## 7. Cause 4: Different Data Types and Semantics

JSON can deserialize cleanly while the consumer still miscomputes.

| Contract Expects | Actual Producer Returns | Problem |
| --- | --- | --- |
| Number `amountMinor` | String `"125000"` | Wire type changed. |
| Minor units | Major units | Parses cleanly yet wrong unit scale. |
| `currency=VND` | `currency=USD` | Wrong business semantics. |
| UTC timestamp | Local timestamp without offset | Different instant interpretation. |
| `status=PAID` | `status=SETTLED` | Consumer enum/switch lacks support. |
| Boolean `paid=true` | String `"true"` | Wrong JSON type. |
| Required array `items` | `items=null` or omitted | Presence/nullability mismatch. |
| Ordered history | Same elements in different order | Semantic violation if order matters. |

**Producer tests protect semantics only when contracts include matching assertions.** If a contract checks only that `amountMinor` is a number, it cannot detect unit changes. Express business invariants with contract scenarios/matchers or dedicated business tests.

## 8. Cause 5: Consumer Request Does Not Match the Stub

Consumer tests with Stub Runner can fail even when producer verification PASSES because the consumer sends:

- Wrong method or path.
- Missing query parameters.
- `Accept`/`Content-Type` header differing from the mapping.
- Body missing fields or wrong JSON types.
- Dynamic request ID checked by an equality matcher against a fixed sample.
- Missing or misconfigured `Authorization` header in tests.

Example contract request:

~~~groovy
request {
    method 'GET'
    url '/api/orders/42'
    headers {
        header('Accept', 'application/json')
    }
}
~~~

Yet the consumer calls `/api/order/42` (missing `s`) or `POST`. WireMock returns **404 no-match**. That is not evidence of a producer business 404 response.

**Inspect the actual request and mapping**:

1. Is the method right?
2. Is the path right after URI template expansion?
3. Are query parameters encoded/serialized properly?
4. Are required headers present?
5. Does the body match structure and types?
6. Does the stub artifact contain the latest mapping?

Never loosen request matchers so every request matches. Stubs must catch consumers sending invalid requests.

## 9. Cause 6: Incompatible Status Codes and Error Handling

A client may handle only `200`, while the producer starts returning `202` or `204` for new behavior. Or the producer returns `409` on duplicate requests while the consumer maps only `400`.

| Response | Consumer Handling Needed |
| --- | --- |
| 200 OK | Deserialize body and process success payload. |
| 201 Created | May need to read body and/or `Location`. |
| 202 Accepted | Do not assume business completion yet. |
| 204 No Content | Do not attempt to deserialize a nonexistent JSON body. |
| 400 Bad Request | Map validation errors. |
| 401 Unauthorized | Handle token/authentication. |
| 403 Forbidden | Distinguish missing permissions from missing auth. |
| 404 Not Found | Handle nonexistent resources. |
| 409 Conflict | Handle state conflicts/idempotency. |
| 429 Too Many Requests | Honor retry/backoff/`Retry-After` if promised. |
| 5xx | Apply timeouts/retries/circuit breakers per policy. |

**Producer contract tests must cover the error scenarios the producer promises**; consumer tests must check how the client handles them. Never use an “any 4xx” matcher that hides differences among 401, 403, 404, and 409.

## 10. Cause 7: Stub Runner Is Using an Old or Wrong Artifact

A producer updates a contract and producer tests PASS, yet consumer tests still fail. Billing may be downloading:

~~~text
com.acme:order-service:1.4.1:stubs
~~~

while the new producer build produced:

~~~text
com.acme:order-service:1.4.2:stubs
~~~

Or both runs share `1.4.2` in a repository that allows overwriting JARs.

Consumer config:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
~~~

Check:

- Exact `groupId:artifactId:version:classifier`.
- `StubsMode.LOCAL` vs `REMOTE`.
- Whether local Maven cache holds an older JAR at the same coordinates.
- Whether the remote repository serves the exact release bytes.
- Whether the stub JAR contains the newly edited mapping/contract.
- Whether the downloaded JAR's checksum matches the producer build record.
- Whether consumer tests use mutable `latest`/`SNAPSHOT` versions.

**Editing contracts in source does not automatically update the JAR Stub Runner loads.** Build, publish/install the exact artifact, pin versions, and inspect actual contents.

## 11. Cause 8: Producer Stub and Producer Image Came from Different Builds

A serious process flaw:

1. Producer CI build A runs generated tests and publishes the `stubs` JAR.
2. Another job rebuilds the container image from a modified branch or different dependency graph.
3. The new image deploys while consumers tested against build A's JAR.

Both **producer tests PASS and consumer tests PASS can be true**, yet apply to different releases.

A release record should link:

| Field | Example |
| --- | --- |
| Producer Git SHA | Full commit SHA. |
| Contract paths | Groovy/YAML files loaded. |
| Producer CI run | Build ID that executed verification. |
| Producer test report | Link/report ID, test count. |
| Stub coordinates | `com.acme:order-service:1.4.2:stubs`. |
| Stub checksum | SHA-256 of published JAR. |
| Container image digest | Digest of deployed producer image. |
| Deployment revision | Environment, region, rollout ID. |

**Promote the exact verified artifact** or ensure reproducible build/deploy from identical source/toolchain with proper gates. Never rely on mutable tag names as sole proof.

## 12. Consumer Tests with Stub Runner: Must Exercise the Real Client

A meaningful test does more than check that Stub Runner loaded an artifact. It invokes **Billing's real HTTP client code**:

~~~java
package com.acme.billing;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingOrderClientContractTest {

    @Autowired
    StubFinder stubFinder;

    @Test
    void billingClientReadsPaidOrder() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );

        OrderClient client = new OrderClient(stubUrl.toExternalForm());
        OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
        assertThat(order.amountMinor()).isEqualTo(125000L);
        assertThat(order.currency()).isEqualTo("VND");
    }
}
~~~

`OrderClient` and `OrderDto` are Billing's example application classes. For `LOCAL`, the stub JAR must exist in the test runner's local Maven repository. For `REMOTE`, provide the repository URL and read credentials.

**Never spin up a fresh `RestClient` inside tests if production uses a differently configured client** and declare the consumer compatible. If production injects `OrderClient` with custom base URLs, converters, interceptors, auth, timeouts, and error handlers, tests should use that exact bean/client or the same factory/configuration.

### 12.1. Also Assert Outgoing Client Requests

A consumer might deserialize a sample response fine while sending the wrong URL/headers. Verify outgoing requests via WireMock's journal or verification API:

~~~java
wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/42"))
        .withHeader("Accept", containing("application/json"))
);
~~~

This assumes the test has access to the exact `WireMockServer` instance. With Stub Runner, if no server bean is exposed directly, query **WireMock's Admin API** at the URL returned by `StubFinder`. Avoid hard-coding ports since Stub Runner commonly allocates dynamic ports.

## 13. Consumer Compatibility Matrix

A producer may have multiple supported consumer versions running at once. Never test only the newest consumer:

| Consumer | Producer Stub Release | Test Status | Meaning |
| --- | --- | --- | --- |
| Billing 3.7 | Order 1.4.1 stubs | PASS | Baseline prior to change. |
| Billing 3.7 | Order 1.4.2 stubs | FAIL | Older consumer incompatible with new release. |
| Billing 3.8 | Order 1.4.2 stubs | PASS | Newer client supports updated schema. |
| Analytics batch 2.2 | Order 1.4.2 stubs | NOT TESTED | Must verify before declaring release safe. |

This is a **hypothetical illustrative table**, not real test output. It shows how a producer release can work with a new consumer while breaking an older one.

**Matrix priorities**:

- Consumer versions live in production or still under support.
- Upcoming producer release.
- Long-lived deployable consumers (batch jobs, mobile apps, external partners).
- Scenarios touching modified fields, enums, errors, headers, or auth.
- Versions inside deprecation/migration windows.

You need not test every historical combination, yet **every combination claimed as supported must have test evidence** or an explicit documented waiver.

## 14. API v1/v2 and Expand–Migrate–Contract

If a producer makes a breaking schema change, such as:

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000
}
~~~

to:

~~~json
{
  "orderId": "ORD-42",
  "state": "PAID",
  "amount": {
    "minor": 125000,
    "currency": "VND"
  }
}
~~~

v1 consumers cannot remain compatible automatically. Safe progression:

1. **Expand:** add v2 while keeping v1 semantics intact during the migration window.
2. **Migrate:** consumers switch to v2, run Stub Runner tests against the v2 artifact, and deploy.
3. **Verify:** check consumer inventory/usage, error behavior, telemetry, and deployment evidence.
4. **Contract:** drop v1 only after an approved EOL decision.

Producer releases during migration must **verify both v1 and v2** while both remain supported. The accompanying `stubs` JAR must reflect all still-supported contracts.

## 15. Consumer Misconfigures Base URL or Path

Consumer tests may hit the stub cleanly while production hits the wrong route:

~~~text
Contract path:  /api/orders/{id}
Consumer config: https://order-service/api/order/{id}
                                  ^ missing "s"
~~~

Common mistakes:

- Base URL already contains `/api`, and the client appends `/api` again.
- URI template mis-encodes braces or query parameters.
- Gateway prefix/route rewrite differs from the test environment.
- Consumer uses HTTP instead of HTTPS, or the wrong hostname.
- DNS/service discovery points to an older version or different service.
- Timeouts/proxies/TLS certificates prevent requests from reaching the producer.

**Stub Runner provides its own WireMock URL** and does not replicate all production service discovery/runtime routing. Consumer tests must inject the stub URL into the right abstraction, and deployments must configure accurate base URLs/routes.

### 15.1. Distinguish HTTP Client Errors from Contract Errors

| Signal | What to Check |
| --- | --- |
| Connection refused | Stub URL/port, server lifecycle, network namespace. |
| 404 no-match | Method/path/query/headers/body and stub mapping. |
| 401/403 | Authorization, token scopes, security config. |
| 415 Unsupported Media Type | Request `Content-Type` and converters. |
| 406 Not Acceptable | Request `Accept` and producer media types. |
| 429 | Rate limits/retry policy. |
| 5xx | Producer runtime, gateway, dependencies, or test fixtures. |
| Timeout | Network, async behavior, retries, and timeout config. |
| JSON parse exception | Actual response body, media type, DTO/converters. |

Do not alter contract paths when the real defect is the consumer's base URL or a gateway rewrite.

## 16. Headers, Content Negotiation, and Serialization

Producer tests running under MockMvc may pass while the real consumer uses another HTTP client with different converters/settings.

Check:

- `Accept`: does the client accept the media type the producer returns?
- `Content-Type`: does the server return JSON or another media type?
- `charset`: does the consumer decode with the right character encoding?
- `Content-Encoding`: does the client decompress gzip/br?
- `Authorization`: are token audience/scopes aligned?
- `If-Match`/`ETag`: do optimistic concurrency semantics match?
- `Idempotency-Key`: do retries reuse the same key per policy?
- `Location`: do resource-creating clients parse the URL properly?
- `Retry-After`: does the consumer honor throttling headers?

For example:

~~~http
Content-Type: application/json;charset=UTF-8
~~~

and:

~~~http
Content-Type: application/problem+json
~~~

are not always handled identically by converters. If a consumer registers JSON converters only for `application/json`, Problem Details error payloads may fail to parse into the expected error DTO.

**Never remove header assertions just to hide converter errors** when that header is part of the contract. Identify the real media type and update the contract or client under review.

## 17. Consumer Error Decoders and Retry Behavior

Many consumers wrap calls in a client helper:

~~~java
public OrderDto getOrder(long id) {
    return restClient.get()
        .uri("/api/orders/{id}", id)
        .retrieve()
        .body(OrderDto.class);
}
~~~

This short snippet hides error mapping. Real code often adds:

- `onStatus(...)` or `ResponseErrorHandler`.
- Retry templates/resilience policies.
- Circuit breakers/time limiters.
- Mapping HTTP errors to domain exceptions.
- Logging/metrics/interceptors.

If the producer changes a 404 body or returns 409, the client wrapper may throw an unexpected exception or retry wrongly. **Consumer contract tests must verify both happy paths and error paths the application relies on**, not only success DTOs.

A test might assert:

~~~java
assertThatThrownBy(() -> client.getOrder(999L))
    .isInstanceOf(OrderNotFoundException.class);
~~~

This assumes the client maps domain exceptions as shown. If the API returns 404 with a specific error code, tests should assert that exception carries the right code/meaning rather than accepting any exception.

## 18. Messaging: Producer Verification Passes Yet Consumer Listener Cannot Read

In event-driven architectures, producer tests may verify an event in a test adapter while the consumer still fails because of:

- Differing topic/destination or routing key.
- Missing or type-changed `eventType`/`schemaVersion` headers.
- Serializer emitting bytes incompatible with the consumer's schema.
- Consumer listener subscribing to the wrong group/queue.
- Broker retention, offsets, retries, or DLQs feeding stale messages.
- Consumer lacking support for a new event version.
- Test adapter using an in-memory fake while production uses a different SDK/codec.

Example message contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'
    input {
        triggeredBy('publishOrderCreated()')
    }
    outputMessage {
        sentTo('orders.created')
        headers {
            header('eventType', 'OrderCreated')
            header('schemaVersion', 1)
            header('contentType', 'application/json')
        }
        body(
            eventId: 'evt-42',
            orderId: 'ORD-42',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

Producer verification PASSES prove **messages observed through the verifier adapter** match the contract in that test context. With a fake adapter, that **does not prove wire bytes on a real broker** are identical. Whenever transport/codecs carry risk, add integration tests with a real test broker and real consumer decoder.

### 18.1. Consumer Stub Runner Message Trigger

A consumer can trigger messages by stub artifact label:

~~~java
assertThat(stubTrigger.trigger(
    "com.acme:order-service", "orderCreatedV1"
)).isTrue();

assertThat(billingEventProbe.awaitOrder(
    "ORD-42", Duration.ofSeconds(5)
)).isTrue();
~~~

`stubTrigger` and `billingEventProbe` are project-configured beans/helpers. Tests need the sender adapter and transport the real listener consumes. **Trigger returning `true` does not prove the listener processed it properly**; assert the business side effect.

If consumer tests wire Stub Runner messaging to a fake sender while the production listener connects to another broker, the two never meet. Inspect Spring test contexts, adapter beans, destination mappings, headers, and queue/topic namespaces.

## 19. Consumer Tests Pass Against Stubs, Yet Production Fails

This is the reverse case: Stub Runner consumer tests PASS, yet calling the live producer fails.

Possible causes:

1. Stale stub JAR or sample mappings do not reflect the live producer release's real responses.
2. Fixed stub response includes a field the live producer omits at runtime.
3. Deployed producer image is not the build that passed contract verification.
4. Gateway/auth/TLS/content negotiation differs from tests.
5. Real producer data contains enums/nulls/ranges absent from test fixtures.
6. Consumer tests do not use production HTTP client configuration.
7. Consumer tested only the happy path, skipping timeouts/errors/retries.

**A stub models contractual behavior, not the entire producer runtime.** Use post-deploy smoke/integration tests and runtime observability to confirm.

### 19.1. Safely Comparing Real Responses Against Contracts

During an incident, collect:

- HTTP method, route template, status.
- Media type and contract-relevant headers.
- Schema/body samples with **PII/secrets redacted**.
- Producer deployment revision/image digest.
- Consumer release and trace/correlation ID.
- Contract source/version and stub artifact checksum.

Never log `Authorization`, cookies, tokens, or raw customer payloads just for debugging. Build an equivalent synthetic request in staging to reproduce.

## 20. Contract Verifier, Stub Runner, and Integration Tests Have Distinct Scopes

| Test Type | Scope | Catches Well | Insufficient to Conclude |
| --- | --- | --- | --- |
| Generated producer verification | Producer code against contract scenarios | Producer responses/messages violating contract. | Consumer DTOs/logic are compatible. |
| Stub Runner consumer test | Consumer code against stub artifact | Client/listener unable to consume stub behavior. | Deployed producer image matches stub artifact. |
| Adapter/codec unit test | Mapping/serialization helpers | Converter, header mapping, custom logic bugs. | Full broker/runtime behavior. |
| Broker/HTTP integration test | Real transport or representative test instance | Routing, codecs, auth, delivery. | Every deployment/consumer combination. |
| Staging smoke/E2E | Deployed services | Real config/runtime/networking. | Every edge case, every consumer version. |

**A mature pipeline layers these together.** You need not run full E2E on every PR if expensive, yet you need gates proportional to change risk plus post-deploy verification.

## 21. Evidence-Based Diagnostic Workflow

~~~mermaid
flowchart TD
    A["Consumer fails after producer release"] --> B["Identify consumer release + trace/request"]
    B --> C["Check request: method/path/query/headers/body"]
    C --> D["Check actual response: status/media type/schema"]
    D --> E["Cross-check consumer DTO/client/error handling"]
    E --> F["Inspect contract source and generated producer tests"]
    F --> G["Inspect stub coordinates/checksum/mappings"]
    G --> H["Link producer Git SHA -> image digest -> deployment"]
    H --> I{"Same release and valid semantics?"}
    I -->|No| J["Fix version/artifact/deployment or contract gap"]
    I -->|Yes| K["Fix consumer/client/config/transport"]
    J --> L["Rerun producer + consumer + integration checks"]
    K --> L
~~~

Proceed in order:

1. **Pin down the exact failure:** request timeout, 404 no-match, 401/403, 415, JSON parse error, wrong business outcome, or undelivered message.
2. **Record the consumer release:** Git SHA, app version, HTTP client/config, or listener version.
3. **Inspect the actual request:** method/path/query/headers/body; never guess from caller code.
4. **Inspect the actual response/message:** status, media type, JSON types, error codes, destination, and headers.
5. **Cross-check consumer DTO/decoder:** field mappings, enums, nullability, date/time, numeric precision, error handling.
6. **Read the contract source:** do scenarios cover consumer needs, or are matchers too loose?
7. **Inspect generated producer tests:** which tests ran, which assertions guard fields/semantics, were any skipped?
8. **Inspect the stub artifact:** version, `LOCAL`/`REMOTE` mode, checksum, mappings, and source producer run.
9. **Inspect the producer deployment:** image digest, environment/region, rollout revision, config.
10. **Reproduce cleanly:** exact consumer source with the exact stub artifact or staging producer release.
11. **Fix at the right layer:** contract gap, producer implementation, consumer client, artifact publishing, deployment, or transport.
12. **Rerun both sides:** producer verification and consumer Stub Runner tests; add integration/smoke tests per risk.

## 22. Symptom and Cause Matrix

| Symptom | Possible Cause | Priority Check |
| --- | --- | --- |
| Producer tests PASS, consumer JSON parse fails | DTO/field/type/media type mismatch | Actual response, DTO, Jackson config. |
| Consumer sees `null` for field | Field missing/null or JSON key mismatch | Contract body and JSONPath/DTO mapping. |
| Consumer enum mapping fails | Producer added/renamed enum value | Enum contract and forward compatibility. |
| Consumer miscalculates money despite clean parse | Unit/rounding/semantics changed | Business invariants, currency, scale. |
| Stub Runner returns 404 | Unmatched request or stale artifact | WireMock journal, path/method/headers/body, JAR version. |
| Stub Runner returns 200, production returns 404 | Different gateway route/base URL/deployment | Runtime URL, routing, producer deployment. |
| Producer tests green, production returns 401/403 | Different test security context, tokens/scopes | Auth contract, gateway/security config. |
| Consumer receives no message | Destination/header/group/adapter mismatch | Broker route, listener, consumer group, test namespace. |
| Stub trigger succeeds, business state unchanged | Listener skips or probe doesn't await properly | Sender adapter, listener binding, side effects. |
| Consumer green on stub, production schema differs | Old stub or mismatched producer image build | Artifact checksum, image digest, release manifest. |
| Producer tests cover only one happy path | Contract omits error/edge scenarios | Coverage and consumer requirements. |
| `byType()` matcher passes despite wrong value | Overly loose matcher | Equality/range/invariants and mutation tests. |
| Older consumer fails after new field added | Strict deserializer/closed schema | Unknown-field policy and supported consumer matrix. |
| Consumer gets 202 while code expects complete body | Incompatible status semantics | Status contract and async workflow. |
| Error response returns HTML instead of JSON | Gateway/security/error handler | Status, `Content-Type`, and error path. |
| Fails only in production | Real config/network/TLS/proxy/data | Environment parity, smoke tests, telemetry. |
| New release breaks v1 while v2 consumer passes | Tested only new consumer, no legacy matrix | Supported consumer versions and v1 contracts. |

## 23. Quick Fixes That Usually Make Things Worse

| Hasty Fix | Why It Is Dangerous | Right Approach |
| --- | --- | --- |
| Changing every matcher to `byType()` | Hides broken enums, IDs, amounts. | Loosen only dynamic fields; keep business assertions. |
| Deleting producer contract tests because consumer fails | Loses producer implementation proof. | Identify missing scenarios or wrong matchers. |
| Deleting consumer Stub Runner tests because producer passes | Stops testing the real client. | Fix DTO/client/request and keep tests. |
| Updating all consumer DTOs to match an unreviewed response | Silently accepts unagreed breaking changes. | Review API change, versioning, and consumer impact. |
| Using `latest` “to grab the newest stub” | Unreproducible runs; cache picks differently. | Pin versions/checksums. |
| Testing only one consumer version | Misses older binaries still running in production. | Maintain supported consumer/producer matrix. |
| Mocking the entire HTTP client | Never tests URLs, converters, interceptors, or error handlers. | Use production client with base URL pointed at Stub Runner. |
| Disabling security filters in all tests | False-green producer tests despite broken prod auth. | Dedicated negative contract/security scenarios. |
| Treating WireMock 404 as business 404 | Client may simply be calling the wrong path. | Inspect request journal and error body mapping. |
| Editing generated test code | Overwritten on next regeneration. | Edit Groovy/YAML contract or base test. |
| Deploying a rebuilt image different from verified artifact | Stubs and producer runtime drift apart. | Promote verified artifacts and store digests. |
| Dropping v1 as soon as v2 producer tests pass | v1 consumers may still be supported. | Expand–migrate–contract and EOL gates. |

## 24. CI Gates to Prevent “Green Producer, Red Consumer”

~~~mermaid
flowchart TD
    A["Producer PR + contract diff"] --> B["Review consumer impact + API owner"]
    B --> C["Generate producer tests"]
    C --> D["Run producer verification"]
    D --> E{"Required scenarios pass?"}
    E -->|No| X["Block publish"]
    E -->|Yes| F["Package immutable stubs + checksum"]
    F --> G["Consumer matrix: Stub Runner + real clients"]
    G --> H{"Supported consumers pass?"}
    H -->|No| Y["Block release or approve migration exception"]
    H -->|Yes| I["Build/promote verified producer image"]
    I --> J["Deploy canary + smoke/integration checks"]
    J --> K["Record runtime version and monitor"]
~~~

Recommended gates:

1. **Contract review:** explicit owner, affected consumers, compatibility classification.
2. **Producer verification:** generated tests created and executed, never 0 tests or skipped.
3. **Matcher quality:** required fields, types, enums, statuses, error scenarios, and business invariants protected.
4. **Stub packaging:** `stubs` JAR holds expected mappings/contracts, immutable version, recorded checksum.
5. **Consumer matrix:** tests real clients/listeners of supported consumers with the exact artifact version.
6. **Legacy support:** while producer still supports v1, run v1 contracts/tests on the current producer release.
7. **Provenance:** producer Git SHA, CI run, stub checksum, and image digest all reconcile.
8. **Post-deploy:** smoke/integration tests and metrics/traces confirm runtime behavior.
9. **Rollback/migration:** documented plan if an uninventoried or legacy consumer breaks.

**An untested consumer must never be treated as PASS.** Explicitly record `NOT TESTED`/`EXEMPTED` with owner/approval rather than assuming compatibility.

## 25. Hands-on Exercise: Producer PASSES Yet Billing Is Incompatible

Practice with Order Service (producer) and Billing Service (consumer):

1. **Create a v1 contract** for `GET /api/orders/42` returning `id`, `status`, `amountMinor`, `currency`; create the base test and generated producer tests.
2. **Run producer verification** and confirm tests truly generate and execute. Intentionally change `amountMinor` to a string to prove tests fail.
3. **Build real Billing `OrderClient` and `OrderDto`**, injecting base URL cleanly in tests.
4. **Publish a pinned stub artifact version**, e.g., `com.acme:order-service:1.4.2:stubs`; inspect the JAR for new mappings and record its checksum.
5. **Run Stub Runner consumer tests** in `LOCAL` or `REMOTE`; obtain dynamic URL via `StubFinder`, call the real client, and assert fields/semantics.
6. **Introduce controlled consumer failures:** rename a DTO field, drop `currency`, change enum mapping, or use the wrong path; observe test failures and log exact exceptions/statuses.
7. **Demonstrate an overly broad matcher:** change `status=PAID` to `CANCELLED` while keeping only `byType()`; show producer tests miss it, then restore equality/business assertions.
8. **Add negative contracts** for 404/401/403/409; verify producer checks and Billing error mapping.
9. **Test artifact drift:** run consumer against old stub JAR then new JAR, comparing results and recording coordinates/checksums per run.
10. **Test producer image drift:** simulate deploying a different image than the CI build that verified stubs; explain why both producer tests and consumer stub tests could still appear green.
11. **Build a compatibility matrix** covering old/new Billing and Analytics batch; mark `NOT TESTED` where evidence is absent.
12. **Try a v2 breaking change** changing `amountMinor` to `amount.minor`; add separate v2 while preserving v1 during the migration window and run both producer suites.
13. **Add a message contract** `OrderCreated` with `eventType`/`schemaVersion`; trigger via Stub Runner and assert Billing listener side effects.
14. **If a test broker is available**, verify serializers/headers/routing on the real test broker; contrast fake adapter vs. transport integration results.
15. **Wire CI gates**: producer verification → stub packaging → consumer matrix → verified image promotion → staging smoke.
16. **Write an incident note** listing symptoms, actual request/response, contract/version, producer test report, stub checksum, consumer release, and root cause.

**Pass criteria:** learners explain what green producer tests prove and do not prove; locate consumer incompatibility at the exact layer; run consumer tests with real clients/listeners and exact stub versions; distinguish contract, DTO, request, artifact, and deployment failures; and protect still-supported consumer versions.

## 26. Self-Check Questions

1. What exactly does a PASSING generated producer test prove?
2. Why does producer verification alone not prove every consumer is compatible?
3. How do producer verification and Stub Runner consumer tests differ?
4. If contracts cover only the 200 happy path, are 401/403/404/409 errors protected?
5. Why can `byType()` on `status` hide `PAID` changing to `CANCELLED`?
6. When can a contract-compliant JSON response still break a Jackson DTO?
7. What does `@JsonIgnoreProperties(ignoreUnknown = true)` solve, and what does it fail to solve?
8. Why is successful JSON parsing not enough to prove amount/currency semantics?
9. When Stub Runner returns 404, how do you distinguish no-match from a business 404?
10. Why inspect the consumer's actual method/path/query/headers/body?
11. How do `LOCAL` and `REMOTE` differ in Stub Runner?
12. Why are identical Maven coordinates not enough to prove two `stubs` JARs are identical?
13. Which fields link a producer stub JAR to a producer container image?
14. Should consumer tests use the production HTTP client or construct a different client in tests? Why?
15. Why verify status handling, error decoders, and retry behavior as well?
16. When a producer supports API v1 and v2 concurrently, which contracts must the pipeline guard?
17. Does a passing producer messaging test with a fake adapter prove real broker serialization?
18. Does `StubTrigger` returning `true` prove the consumer listener processed the event?
19. Which test layers cover schema registries, routing, and broker acks/retries?
20. If a new consumer PASSES while older Billing FAILS, can the producer release be considered compatible with all supported consumers?
21. What information should you gather for production failures without logging secrets/PII?
22. Why should CI record `NOT TESTED` rather than defaulting untested consumers to PASS?

## 27. Quick Diagnostic Checklist

| Group | What to Confirm |
| --- | --- |
| **Contract coverage** | Cover scenarios, requests, responses, errors, headers, and business semantics consumers need? |
| **Producer verification** | Generated tests created and run completely, without unintended skips or 0 tests? |
| **Matcher quality** | Not overly loose on statuses, enums, required fields, types, amounts, or auth? |
| **Consumer client** | Uses exact DTOs, converters, base URLs, headers, timeouts, and error decoders? |
| **Consumer tests** | Stub Runner invokes real client/listener and asserts business outcomes? |
| **Stub artifact** | Exact coordinates, version, classifier, mode, checksum, and mappings? |
| **Request matching** | Method/path/query/headers/body match? Any 404 no-match? |
| **Runtime response** | Status, `Content-Type`, body, null/type/enum/units match contract? |
| **Version matrix** | Evidence gathered for every supported consumer version? |
| **Deployment provenance** | Producer image digest traced to the exact verified source build? |
| **Messaging** | Destination, `schemaVersion`, headers, codecs, offsets/replay, and listeners aligned? |
| **CI/post-deploy** | Compatibility gates, smoke tests, monitoring, and rollback plans in place? |

**Key takeaway:** **Green producer tests are necessary, not a system-wide compatibility guarantee.** Verify that contracts capture real consumer needs including error and business scenarios; generated assertions are strict enough; consumer tests run real clients/listeners; Stub Runner loads the exact `stubs` JAR; deployed producer images match verified builds; and all supported consumer versions appear in the compatibility matrix. When investigating, trace from actual requests/responses or messages through DTOs, contracts, generated tests, artifacts, and deployment records. Fix the exact offending layer, keep both producer verification and consumer tests active, and enforce CI gates to catch regressions before release.
