# Verifying That Consumer Requirements Are Reflected in the Contract

## 1. Why Can a Syntactically Valid Contract Still Miss Consumer Needs?

In a microservices system, the **consumer** depends on public behavior from the **producer** to fulfill its task. Spring Cloud Contract supports describing HTTP or messaging interactions with the **Groovy/YAML DSL**, generating producer-side tests, producing stubs, running **Stub Runner** for consumer testing, and integrating into CI to detect incompatible API changes.

However, **a syntactically valid contract does not automatically protect everything the consumer needs**.

For example, Checkout Service (consumer) calls Inventory Service (producer) to decide whether a customer can order three items:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

The producer might define a contract that only checks:

~~~json
{
  "sku": "SKU-100"
}
~~~

That contract can generate a test and pass. Yet Checkout actually needs to know:

- Is `available` a boolean to decide if the item is in stock?
- Is `quantity` a number so it can be compared against the requested order quantity?
- If the SKU **does not exist**, which status and error code does the producer return?
- If the response is `404`, does Checkout display the right message or mistakenly try to create the order?
- Can `quantity` ever be returned as `null` or omitted?

If these expectations are not reflected in the contract and tests, both producer and consumer tests can pass while data changes still break the application.

**Goal of this lesson:** Verify that real consumer requirements have been turned into **observable commitments**, tested on both the producer and consumer sides, rather than existing only as prose in documentation.

### After This Lesson, You Will Be Able To

1. Gather and classify consumer needs across requests, responses, errors, and messages.
2. Build a traceability table from business needs to contracts, assertions, and consumer tests.
3. Inspect Groovy/YAML DSL contracts to spot missing statuses, headers, fields, JSON types, or error branches.
4. Choose matchers flexible enough for dynamic data yet strict enough for critical codes and fields.
5. Distinguish generated producer verification from consumer tests using stubs.
6. Verify that the consumer client sends the **right request** and handles the **right response**.
7. Identify gaps in contract reviews, versioning, and CI.
8. Design hands-on exercises and a checklist before accepting a contract.

> **Principle:** Do not start by asking "What is the producer returning?". Start by asking **"What decision must the consumer make, and which observable signals are needed to make that decision correctly?"**

## 2. Three Layers That Must Align: Needs, Contract, and Execution

A consumer requirement usually begins with a use case. For example: Checkout Service only allows placing an order when available stock is at least the quantity the customer wants to buy.

From this use case, we need at least three layers:

| Layer | Question | Illustration |
| --- | --- | --- |
| **Consumer need** | What data/behavior does the consumer need to make a decision? | `available` and `quantity`, plus the SKU-not-found scenario |
| **Contract** | What does the public interface commit to? | `GET /api/inventory/{sku}`, HTTP `200`, boolean `available`, number `quantity`, `404` error |
| **Executable verification** | Who verifies what? | Producer generated tests verify the real API; consumer tests via Stub Runner verify the client and use case |

Flow:

~~~mermaid
flowchart TD
    A["Consumer use case"] --> B["Observable needs at the API boundary"]
    B --> C["Groovy/YAML contract"]
    C --> D["Generated producer tests"]
    C --> E["Stub mappings"]
    D --> F["Producer verification passes"]
    E --> G["Stub Runner starts stubs"]
    G --> H["Consumer code sends request"]
    H --> I["Assertions on consumer behavior"]
    F --> J["Stub version approved for CI"]
    I --> J
~~~

This is a **two-sided verification loop**:

- If the producer changes a JSON number into a String on a field constrained by the contract, the **producer test** should catch the mismatch.
- If the consumer sends the wrong path/header or misreads JSON, the **consumer test with the stub** should catch it.
- If a requirement is not written into **either the contract or consumer tests**, nothing automatically protects it.

### 2.1. Contracts Do Not Guess Requirements

Spring Cloud Contract **does not read consumer code to infer business requirements**. Selecting statuses, fields, matchers, request cases, and protected error branches remains a shared responsibility of API designers, producers, and consumers.

Generated tests only verify what the DSL expresses under the generation rules. If the DSL omits `quantity`, you cannot assume the generated test will warn if the producer drops that field.

## 3. Gathering Needs from Consumer Behavior, Not Just Endpoints

Suppose a method in Checkout looks like:

~~~java
public boolean canPlaceOrder(String sku, int requestedQuantity) {
    InventoryStock stock = inventoryClient.findStock(sku);

    return stock.available()
        && stock.quantity() >= requestedQuantity;
}
~~~

This example is illustrative code: a real application also handles `404`, timeouts, security, and user messaging.

Read the **decision conditions** to record the requirements:

1. The consumer needs to identify the exact product via `sku`.
2. The consumer needs `available` as a **boolean**, not the string `"true"`.
3. The consumer needs `quantity` as a **number**, not the string `"8"`.
4. When quantity is 0, the consumer needs to handle the out-of-stock case.
5. For a non-existent SKU, the consumer needs to distinguish it from a system error.
6. The consumer needs content and a media type it can deserialize, such as `application/json`.

### 3.1. Categories of Requirements

| Category | Example Questions to Ask the Consumer |
| --- | --- |
| **Request target** | Which HTTP method, path, path variables, and query parameters? |
| **Request headers** | Which `Accept`, `Content-Type`, auth, tenant, or correlation ID headers are part of the interface? |
| **Request body** | Which fields are required, what types, nullability, lists/maps, and validation rules? |
| **Success status** | `200`, `201`, `204`, or another status? |
| **Success body** | Which fields does the consumer read, with what types, and can any be absent? |
| **Error status/body** | For not-found, invalid request, or conflict, which status/code does the client branch on? |
| **Dynamic vs. static** | Do IDs/timestamps vary? Which status codes must remain fixed? |
| **Version** | Which API/stub version is the consumer running against? |
| **Messaging** | Which topic/destination, event type, headers, payload, and schema version? |
| **Non-functional** | Which timeouts, retries, auth, ordering/delivery semantics belong in separate test layers? |

**Not every requirement has to be stuffed into a contract.** An HTTP contract should focus on **observable communication behavior**; algorithms, performance, or distributed-systems mechanics usually require separate unit/integration/performance/security tests.

### 3.2. Scoping by Use Case

The consumer may need four outcomes:

- Sufficient stock: allow placing the order.
- Insufficient stock: reject the order.
- Non-existent SKU: show a not-found message.
- API unavailable: enter a temporary-error state or apply controlled retries.

Of these, the first three likely require **specific responses** published by the producer. The unavailable case may require resilience tests independent of the committed stub responses.

## 4. Building a Traceability Matrix: Requirement → Contract → Tests

Before writing the DSL, create a table with **requirement IDs** and measurable acceptance criteria.

| ID | Consumer Requirement | Representation in Contract | Producer Test | Consumer Test |
| --- | --- | --- | --- | --- |
| C-01 | Look up stock by SKU | `GET /api/inventory/SKU-100` | Sends exact GET/path | Client calls right endpoint |
| C-02 | Receive JSON when SKU exists | Status `200`, `Content-Type: application/json` | Assert status/media type | Deserialize into DTO |
| C-03 | Know if in stock | `available: true` (boolean) | Assert field/type | Checkout decides based on boolean |
| C-04 | Know stock quantity | `quantity: 8` (number) | Assert field/type | Compare against requested quantity |
| C-05 | Handle out-of-stock case | Response `quantity: 0`, `available: false` | Generated test for this case | Reject placing order |
| C-06 | Distinguish non-existent SKU | `404` + `code: INVENTORY_NOT_FOUND` | Assert status, code | Display/report not-found |
| C-07 | Avoid misclassifying unmatched stub errors | Mapping for C-06 has distinct body | Real producer response | Assert code, not just status |
| C-08 | Distinguish invalid input | `400` + `code: INVALID_SKU` if published by API | Test invalid input | Client shows input error |

This table is a **review tool**, not a runtime artifact. Its value lies in answering the question:

> If someone changes `quantity` from a JSON number to a String, **which test must fail?**

If you cannot point to a specific assertion or scenario, the requirement may not be adequately protected.

### 4.1. What Does "Reflected" Mean?

A requirement is considered **contract-protected** when:

1. It is written as an observable condition: request, status, header, field, type, error code, or message.
2. A contract at the right source and version contains that condition.
3. Generated producer tests are generated and **executed** with matching assertions.
4. Consumer tests use the right stub version, call **real consumer code**, and verify the decision/behavior.
5. CI catches deleted contracts, skipped tests, or mismatched stub versions.

If only the contract DSL exists without running generated producer tests, mark the status as **"specified, producer unverified"** rather than "compatibility guaranteed."

## 5. Building a Success HTTP Contract from Consumer Needs

Start with C-01 through C-04. Illustrative source file:

~~~text
src/test/resources/contracts/inventory/get_inventory_available.groovy
~~~

Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_available')
    description('Checkout checks an in-stock SKU to decide whether to place an order')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')

        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()

        headers {
            contentType(applicationJson())
        }

        body(
            sku: 'SKU-100',
            available: true,
            quantity: 8
        )
    }
}
~~~

Meaning:

- `method GET()`: Consumer uses GET; if the client sends POST, the stub mapping should not match.
- `urlPath('/api/inventory/SKU-100')`: A concrete request verified on the producer.
- `Accept: application/json`: Consumer declares the expected response format.
- `status OK()`: Producer must return `200` for this case.
- `Content-Type`: Consumer deserializes JSON per the agreed media type.
- `available: true`: JSON boolean, not a String.
- `quantity: 8`: JSON number, not a String.

### 5.1. Why Choosing the Exact JSON Type Matters

Two responses that look similar at a glance:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

~~~json
{
  "sku": "SKU-100",
  "available": "true",
  "quantity": "8"
}
~~~

Yet the second response switches to String types, which can break consumer deserialization or alter behavior unexpectedly. **Types are part of the data interface** whenever the consumer deserializes into a DTO with boolean/int fields.

When reviewing generated producer tests, check that the matchers and assertions genuinely constrain the expected types. Do not merely glance at the response sample and assume every field is tested the way the consumer needs.

### 5.2. Do Not Over-Constrain Unneeded Fields

If the response also includes `debugInfo`, `internalNodeId`, or `generatedAt` that the consumer does not use, avoid rigidly pinning every value just because you saw them in a sample JSON payload.

Aim for a **contract strict enough** for the behavior the consumer relies on, and **flexible enough** for unneeded metadata. If a client uses strict JSON deserialization or rejects unknown fields, adding new fields can still break it; document actual parser behavior in compatibility reviews.

## 6. Insufficient Stock Needs Its Own Fixture

C-05 is not proven by the `available: true` case alone. If Checkout must reject orders when stock is insufficient, there should be another interaction or another consumer test built on the contract-published response.

Example:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_out_of_stock')

    request {
        method GET()
        urlPath('/api/inventory/SKU-EMPTY')

        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-EMPTY',
            available: false,
            quantity: 0
        )
    }
}
~~~

Distinction:

- The **producer contract** here verifies that an existing but out-of-stock SKU is represented as `200` with `available: false`, `quantity: 0`.
- The **consumer test** must verify that Checkout **does not allow placing the order** upon receiving that response.

You do not need hundreds of contracts just to test every quantity value. Once the contract protects types and shape, the logic comparing `requestedQuantity` against `quantity` can be tested with **Checkout unit tests** across values like `0`, `1`, `8`, and `9`. Contract tests focus on representative scenarios the consumer relies on.

### 6.1. Sensible Division of Responsibilities

| Question | Contract Test | Unit/Domain Test |
| --- | --- | --- |
| Does the producer expose a numeric `quantity` field? | Yes, if protected by DSL/matchers | Not the primary focus |
| Does the producer return `available: false` for the out-of-stock fixture? | Yes | Not required |
| Does Checkout reject an order for 9 when 8 are in stock? | Can be tested end-to-end with stub | Should have unit tests for boundary rules |
| Is real stock updated accurately under concurrent orders? | Insufficient on its own | Requires transaction/concurrency/integration tests |

## 7. Error Branches Are Consumer Requirements, Not Afterthoughts

Suppose the consumer distinguishes **non-existent** from **out of stock**:

- Existing SKU, quantity 0 → `200` with `available: false`.
- Non-existent SKU → `404` with `code: INVENTORY_NOT_FOUND`.

If both cases turn into `404`, Checkout may display the wrong message or mishandle the flow.

Groovy DSL for the not-found branch:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_not_found')

    request {
        method GET()
        urlPath('/api/inventory/SKU-404')

        headers {
            accept(applicationJson())
        }
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVENTORY_NOT_FOUND',
            message: 'SKU not found'
        )
    }
}
~~~

The consumer should test all of the following:

1. HTTP `404` with code `INVENTORY_NOT_FOUND` branches into a "SKU not found" outcome.
2. Checkout does not treat this result as zero stock and attempt an order.
3. An unmatched WireMock `404` (from a wrong path, header, or port) **is not confused** with the business error carrying the committed body.

### 7.1. Wrong-Request Responses vs. Business Error Responses

An important pitfall with Stub Runner: if the client calls `/api/inventories/SKU-404` (wrong path), WireMock may return `404` because **no mapping matched**.

Meanwhile, the not-found contract expects:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "INVENTORY_NOT_FOUND",
  "message": "SKU not found"
}
~~~

Asserting only status `404` can make a consumer test produce a **false green**. Verify the error code/body or a consumer behavior that only triggers on the genuine business error.

### 7.2. Invalid Requests Need Contracts When the Consumer Relies on That Branch

If the client may send an empty SKU or invalid characters and the API publishes `400` + `INVALID_SKU`, define an additional case:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_invalid_sku')

    request {
        method GET()
        urlPath('/api/inventory/INVALID-SKU!')
    }

    response {
        status BAD_REQUEST()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVALID_SKU'
        )
    }
}
~~~

This example is only valid if the producer **actually treats `INVALID-SKU!` as invalid under its public API rules** and returns the committed response; a route containing special characters might also be handled differently by filters/routers. When practicing, use a test error code and route consistent with your project's validation policy. Do not force every API to use `400` or the exact field name `code`; those are conventions chosen jointly by producer and consumer.

## 8. Expressing Success Requirements in YAML DSL

The same `get_inventory_available` contract in YAML:

~~~yaml
name: get_inventory_available
description: Checkout checks an in-stock SKU to decide whether to place an order
request:
  method: GET
  urlPath: /api/inventory/SKU-100
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-100
    available: true
    quantity: 8
~~~

The same not-found contract:

~~~yaml
name: get_inventory_not_found
request:
  method: GET
  urlPath: /api/inventory/SKU-404
  headers:
    Accept: application/json
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: INVENTORY_NOT_FOUND
    message: SKU not found
~~~

**Pick one source format suited to your project**; do not enable both Groovy and YAML defining duplicate interactions just to have two examples. Both are shown in this lesson so readers understand the syntax.

### 8.1. Common Mistakes When Converting from Groovy to YAML

- `available: true` must be a YAML boolean, not `available: "true"`.
- `quantity: 8` must be a number, not `"8"` if the API commits to a Number.
- For empty strings, write `""` explicitly so it is not parsed as null.
- JSON arrays are written as YAML sequences (`-`), not maps.
- Strings like `"00123"` need quotes if the consumer expects a String with leading zeros.
- If a JSON field has dots or special characters, use appropriate YAML and JSONPath escaping.

Generating producer tests from YAML does not eliminate the need to review **semantics**: valid syntax with overly broad matchers or missing statuses still leaves gaps.

## 9. Dynamic Data: Constrain What Must Be Stable, Relax What Must Vary

A reservation-creation API may return a new ID and varying timestamp on each request:

~~~json
{
  "reservationId": "RES-123",
  "status": "CONFIRMED",
  "createdAt": "2026-11-24T03:00:00Z"
}
~~~

The consumer needs:

- `reservationId` in a valid format so it can call subsequent APIs.
- `status` equal to `CONFIRMED` to proceed to the next step.
- `createdAt` parseable as a timestamp, without depending on one fixed instant.

You can use response matchers:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_reservation')

    request {
        method POST()
        urlPath('/api/reservations')
        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }
        body(
            sku: 'SKU-100',
            quantity: 1
        )
    }

    response {
        status CREATED()
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: 'RES-123',
            status: 'CONFIRMED',
            createdAt: '2026-11-24T03:00:00Z'
        )
        bodyMatchers {
            jsonPath('$.reservationId', byRegex('RES-[0-9]+'))
            jsonPath('$.createdAt', byTimestamp())
        }
    }
}
~~~

**Key point:** `status` stays a strict literal; `reservationId` and `createdAt` vary, so they use matchers tailored to consumer needs.

### 9.1. Overly Broad Matchers Mask Breaking Changes

If a contract only checks `quantity` with `byType()`, a producer returning 999 when stock is 8 still passes because it is still a Number. A type matcher protects the **type**, not the **business value**.

When the consumer depends on a decisive value (such as `status: CONFIRMED` or `code: INVENTORY_NOT_FOUND`), match it exactly or use an intentionally narrow matcher. Never turn every field into `byRegex('.*')` just to make the build green.

### 9.2. Consumer-Side vs. Producer-Side Values

Spring Cloud Contract supports two-sided expressions for dynamic values, for example in a **request**:

~~~groovy
request {
    method POST()
    urlPath('/api/echo')
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: $(consumer(regex('CUS-[0-9]+')),
                      producer('CUS-7'))
    )
}
~~~

In a request, the generated **producer test** typically sends the concrete value `CUS-7`, while the **stub** can accept any code matching the regex. Do not confuse a broad stub matcher with the producer having been tested against all customer IDs.

In responses, the consumer sample and producer-side matcher also need to be understood accurately per the DSL. During review, always open the generated producer assertions and actual stub mappings to confirm both sides enforce what the consumer needs.

## 10. Consumer Needs Are Only Protected When Both Sides Are Tested

A standard workflow:

~~~mermaid
flowchart TD
    N["Consumer needs documented"] --> DSL["Groovy/YAML Contract"]
    DSL --> PT["Generated producer tests"]
    DSL --> STUB["Stub JAR / mappings"]
    PT --> P{"Producer complies?"}
    P -- "No" --> FIX["Fix producer or renegotiate contract"]
    P -- "Yes" --> R["Publish verified stub"]
    STUB --> R
    R --> SR["Consumer runs Stub Runner"]
    SR --> CT["Consumer client and use-case tests"]
    CT --> Q{"Consumer handles properly?"}
    Q -- "No" --> CF["Fix consumer or review contract"]
    Q -- "Yes" --> PASS["Requirement backed by two-sided evidence"]
~~~

**Generated producer tests** verify that the producer actually returns the contracted responses in its test environment. **Consumer tests** verify that the consumer sends the right requests and handles the stub responses properly.

What one side alone does not prove:

| Which Tests Are Green? | What Is Proven | What Is Not Proven |
| --- | --- | --- |
| Only producer generated tests | Producer satisfies the generated and executed interactions | Is the consumer calling the right endpoint and handling responses properly? |
| Only consumer stub tests | Consumer handles the stub fixtures that ran | Does real producer code still satisfy the contract? |
| Both green, but missing the 404 case | Described cases pass | Not-found requirement may still be unprotected |
| Both green, but using an old stub version | Compatible with the tested version | Does not prove compatibility with the new producer |
| Both green with a full matrix | Strong evidence for in-scope interface needs | Does not prove all concurrency/security/latency scenarios |

### 10.1. Why Contract Reviews Must Include Consumer Code

A producer might propose a perfectly reasonable schema while the consumer actually relies on:

~~~text
response.data.inventory.available
~~~

whereas the new contract only describes:

~~~text
response.available
~~~

Both are valid JSON, yet their structures differ. A proper review compares the **consumer's DTO/client parser/use cases** against the **schema described by the contract**, not just the contract against a sample API payload from the producer.


## 11. Writing Consumer Tests: Calling the Real Client via Stub Runner

Assume Inventory Service has packaged its stubs JAR from contracts and producer verification has passed. Checkout Service uses an HTTP client to fetch stock information.

An illustrative client using Spring `RestClient`:

~~~java
public record InventoryStock(
    String sku,
    boolean available,
    int quantity
) {}

public final class InventoryClient {
    private final RestClient client;

    public InventoryClient(String baseUrl) {
        this.client = RestClient.create(baseUrl);
    }

    public InventoryStock findStock(String sku) {
        return client.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(InventoryStock.class);
    }
}
~~~

This class illustrates a Java record and `RestClient` (Spring Framework 6.1+); in real code, add appropriate packages/imports and substitute WebClient, OpenFeign, or whichever client adapter Checkout uses.

Consumer use case:

~~~java
public final class CheckoutService {
    private final InventoryClient inventoryClient;

    public CheckoutService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public boolean canPlaceOrder(String sku, int requestedQuantity) {
        InventoryStock stock = inventoryClient.findStock(sku);
        return stock.available()
            && stock.quantity() >= requestedQuantity;
    }
}
~~~

Test running with Stub Runner, getting the WireMock port from `@StubRunnerPort`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutConsumerContractTest {

    @StubRunnerPort("com.example:inventory-producer")
    int inventoryStubPort;

    @Test
    void shouldAllowOrderWhenInventoryIsAvailable() {
        InventoryClient client =
            new InventoryClient("http://localhost:" + inventoryStubPort);
        CheckoutService checkout = new CheckoutService(client);

        boolean allowed = checkout.canPlaceOrder("SKU-100", 3);

        assertThat(allowed).isTrue();
    }

    @Test
    void shouldRejectOrderWhenOutOfStock() {
        InventoryClient client =
            new InventoryClient("http://localhost:" + inventoryStubPort);
        CheckoutService checkout = new CheckoutService(client);

        boolean allowed = checkout.canPlaceOrder("SKU-EMPTY", 1);

        assertThat(allowed).isFalse();
    }
}
~~~

Required assumptions for this example:

- The producer has generated mappings for `SKU-100` and `SKU-EMPTY`.
- Stub artifact `com.example:inventory-producer:1.2.3:stubs` is installed in the local Maven repository; otherwise adjust `stubsMode`/source accordingly.
- Checkout tests include compatible Spring Boot Test, Spring Cloud Contract Stub Runner, and HTTP client/Jackson dependencies.
- A real project must run on compatible Spring configuration and JUnit versions.
- If Checkout uses dependency injection, test the **real CheckoutService with the real InventoryClient** wired to the stub URL, rather than constructing a fake logic stub just for the test.

### 11.1. Why a Stub Smoke Test Is Not Enough

A test like:

~~~java
String response = RestClient
    .create("http://localhost:" + inventoryStubPort)
    .get()
    .uri("/api/inventory/SKU-100")
    .retrieve()
    .body(String.class);

assertThat(response).contains("SKU-100");
~~~

only proves **WireMock returns sample data**. It does not prove:

- Checkout's InventoryClient sends the right method/URL/headers.
- Checkout parses `available` and `quantity` with the right types.
- Checkout rejects orders when `quantity` is insufficient.
- Checkout distinguishes not-found from system errors.

**Purpose-built consumer tests must exercise consumer code** and assert the behavior the use case requires.

### 11.2. Do Not Hard-Code Ports Unnecessarily

In the example, `ids` omits the port so Stub Runner chooses an available port per configuration. `@StubRunnerPort` injects the port for that producer. This reduces collisions when multiple suites run in parallel.

When multiple stub services exist, look up the distinct port for Inventory, Pricing, Payment, etc. Never point all clients at a single WireMock server just because you only looked up one `localhost` port.

## 12. Testing Error Branches Through Consumer Behavior

With the `get_inventory_not_found` contract, when the client requests `SKU-404`, WireMock returns `404` with the `INVENTORY_NOT_FOUND` JSON.

With default `RestClient.retrieve()` settings, `4xx` responses usually throw an HTTP client error exception. The consumer must handle both the **error status and error body**, or use an adapter that returns a classified result.

Pseudocode for the business requirement:

~~~java
// PSEUDOCODE: Checkout's own API, not a built-in function
CheckoutResult result = checkout.tryPlaceOrder("SKU-404", 1);

assertThat(result.reason()).isEqualTo("SKU_NOT_FOUND");
assertThat(result.isAccepted()).isFalse();
~~~

Additional tests to include:

- `SKU-EMPTY`: valid request, `200` response; Checkout rejects due to out-of-stock.
- `SKU-404`: `404` response with `code: INVENTORY_NOT_FOUND`; Checkout reports not found.
- Client sends wrong path: unmatched WireMock stub; test must fail rather than mistaking it for a valid not-found response.
- `400` on invalid input, if that is an error branch the consumer actually receives and handles.
- Downstream `5xx`/timeouts if the system has retry/circuit-breaker policies; resilience behavior should also be tested with appropriate tools/methods.

### 12.1. Error Codes Can Matter More Than Messages

Example response:

~~~json
{
  "code": "INVENTORY_NOT_FOUND",
  "message": "SKU not found"
}
~~~

If Checkout uses `code` to drive branching logic, `INVENTORY_NOT_FOUND` must remain stable and contract-protected. `message` may change due to localization; determine whether the consumer depends on the wording or merely expects a String field, and choose the right constraint level.

**Never branch business logic on human-readable `message` strings** when the API provides a stable machine-readable error code. If an existing consumer actually branches on `message`, record it as a compatibility risk and plan a migration instead of pretending it does not happen.

## 13. HTTP Is More Than Response Bodies: Requests Must Also Reflect Consumer Needs

The consumer may need to pass warehouse, tenant, or channel information. If the contract only describes the response and leaves the request overly loose, the stub may match too broadly and let broken clients pass.

Example of an API expecting an `X-Channel` header:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_for_checkout')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')

        headers {
            accept(applicationJson())
            header('X-Channel', 'checkout')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-100',
            available: true,
            quantity: 8
        )
    }
}
~~~

If `X-Channel` is part of the public interface affecting returned data or access control, constrain it in the contract. If it is purely an internal observability header that the consumer does not rely on, decide carefully whether it belongs in the contract.

### 13.1. Query Parameters, Paths, and Request Bodies

Checklist when comparing contracts against the client:

| Detail | Contract and Consumer Must Agree On |
| --- | --- |
| HTTP method | `GET` vs. `POST` |
| Path | `/api/inventory/SKU-100` vs. `/api/inventories/SKU-100` |
| Query | `warehouse=HCM` vs. `warehouse=HN` if results depend on warehouse |
| Headers | `Accept`, `Content-Type`, auth/tenant/channel when published by the API |
| JSON body | Field names, types, nulls, lists, and nested objects |
| Encoding | URL encoding of special characters in paths/queries |
| Status | `200`, `201`, `204`, `400`, `404` and their meanings |

For a dynamic route `/api/inventory/{sku}`, a contract using the literal `SKU-100` verifies **one concrete representative**. If the consumer calls multiple SKUs, choose appropriate request matchers and add fixtures across meaningful data partitions; never treat a single literal as proof that every valid URL is handled properly by the producer.

### 13.2. Overly Broad Contracts Can Let Broken Clients Pass

For instance, a WireMock mapping matching any path starting with `/api/` without requiring a specific method or body would let the consumer send the wrong path `/api/inventory/item/SKU-100` and still get `200`.

Therefore, request matching must be strict enough for the **request shapes the consumer is permitted to emit**. At the same time, do not pin unneeded dynamic headers like correlation IDs to a single literal; use pattern/type matchers if they are genuinely part of the contract.

## 14. Messaging Consumers: Verifying Events the Consumer Actually Uses

In messaging, a consumer may need a payment-authorized event to unlock an order.

Example message contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('payment_authorized_event')
    label 'paymentAuthorized'

    input {
        triggeredBy('publishAuthorizedPayment()')
    }

    outputMessage {
        sentTo('payments.authorized')
        headers {
            header('eventType', 'PaymentAuthorized')
        }
        body(
            eventId: 'evt-100',
            paymentId: 'PAY-100',
            orderId: 'ORD-123',
            amount: 120000
        )
    }
}
~~~

What the consumer actually needs:

- Exact destination/event type so the listener receives the message.
- `orderId` to correlate with the order.
- `amount` as a number if the consumer performs calculations or comparisons.
- `eventId` with stable identity to support idempotency, if needed.
- Schema version or new fields handled per the agreed compatibility strategy.

With appropriate Stub Runner messaging integration, consumer tests can trigger the message stub and verify that the listener deserializes and processes the event.

**Important limitation:** A message contract verifies destination, headers, and body; it **does not by itself prove** broker-wide ordering, redelivery/ack behavior, or exactly-once business effects. Those requirements must be covered by **broker integration**, idempotency, or failure-injection tests. Never mark them "contract-protected" just because `eventId` appears in the JSON.

## 15. Reviewing Contracts with Reverse-Change Questions (Mutation Thinking)

An effective way to spot coverage gaps is to ask:

> "If the producer changes X, which test must turn red?"

Mutation check matrix:

| Hypothetical Producer Change | Potential Impact on Consumer | Required Test Evidence |
| --- | --- | --- |
| Delete field `quantity` | Checkout cannot compare stock | Generated test fails due to missing field |
| Change `quantity` from number to String | Deserialization or comparison fails | Generated assertion checks type |
| Rename `available` to `inStock` | Client cannot read old field name | Contract protects field name |
| Change `200` to `204` | No body left for consumer to read | Status and response body assertions |
| Change `404` to `200` with error JSON | Client may treat error as success | Not-found contract checks status |
| Change `INVENTORY_NOT_FOUND` to `SKU_MISSING` | Consumer branching on old code breaks | Equality check on error code |
| Change request path without keeping old route | Client calling old endpoint fails | Producer/generated test hits old path |
| Add required header consumer does not send | WireMock/client or producer rejects request | Contract/request matching and consumer test |
| Change message destination | Listener stops receiving events | Message contract checks `sentTo` |
| Deliver message twice | Consumer may process business action twice | Idempotency/integration tests, **not just** contracts |
| Increase latency beyond SLA | Client times out | Dedicated performance/resilience tests |

This is a **coverage-thinking exercise**. You do not need to modify real producer code for every row during review. For high-impact changes, run controlled mutation experiments in a test environment to confirm assertions actually catch the fault.

### 15.1. When a Test Does Not Turn Red as Expected

Possible reasons:

1. The requirement was never expressed in the DSL.
2. The matcher is too broad and accepts invalid values.
3. Generated producer tests were not generated or were skipped.
4. Consumer tests only ping the stub without calling consumer code.
5. The stub is using an old version.
6. An error branch or boundary value has no fixture.
7. Data is mocked at a layer that bypasses the behavior under test.

Fix this by returning to **consumer requirements and execution boundaries**, rather than rushing to add arbitrary matchers.

## 16. Review Workflow Between Producer and Consumer

A sound contract typically goes through these steps:

### Step 1 — Consumer States the Use Case and Decision Needed

For example: "Checkout needs `available` and `quantity` to decide whether to accept an order; if the SKU does not exist, it must display a not-found message."

Do not start from the producer's internal DTO classes.

### Step 2 — Convert Into Measurable Acceptance Criteria

For example:

- When calling `GET /api/inventory/SKU-100`, receive `200`, JSON with `sku`, boolean `available`, and number `quantity`.
- When calling `GET /api/inventory/SKU-EMPTY`, receive `200`, `available: false`, and `quantity: 0`.
- When calling `GET /api/inventory/SKU-404`, receive `404` and `code: INVENTORY_NOT_FOUND`.

### Step 3 — Compare DSL Against Acceptance Criteria

Check whether the Groovy/YAML contract covers the request, response, status, headers, error code, shape, and matchers.

### Step 4 — Producer Runs Generated Verification

Ensure the producer genuinely produces the right response in its test context; when producer code changes, tests must catch agreement violations.

### Step 5 — Consumer Tests via Stub Runner

Start the stub at the right version, wire it into the real client, and assert the use case along with error branches.

### Step 6 — Record Out-of-Scope Requirements Explicitly

Concurrency, transactions, security policies, retries, or delivery semantics belong in other tests. Link those results back to the original requirement rather than deleting the requirement from the checklist.

### Step 7 — Accept or Negotiate Changes

When the producer wants to change a schema, assess impacted live consumers, migration plans, deprecation windows, versioning, and corresponding artifact publishing workflows.

### 16.1. Role of Each Party

| Role | What to Confirm |
| --- | --- |
| Consumer developer | Contracts protect the fields/branches the client actually uses |
| Producer developer | Behavior can be implemented and generated tests reflect commitments |
| API/platform owner | Naming, media types, error schemas, and versioning are consistent |
| QA/test engineer | Boundary cases, error coverage, setup assumptions, and test evidence exist |
| CI/release owner | Stubs use exact versions, tests are never skipped, release gates are clear |

You do not need heavy meetings for every single field; a pull request template and a short traceability table work well. However, **producer-only reviews** easily miss requirements the client relies on.

## 17. Compatibility Scenarios and API Changes

### 17.1. Is Adding a New Field Always Compatible?

There is no absolute yes. If the consumer uses a JSON parser that ignores unknown fields, adding a field is usually compatible. If the client uses strict schema validation or a decoder that rejects unknown fields, it can fail.

Therefore, reviews should inspect actual deserialization behavior rather than blindly applying "adding a field is backward compatible" in every case.

### 17.2. Removing or Renaming a Field Used by the Consumer

Usually a breaking change. For instance, renaming `quantity` to `remainingQuantity` breaks existing clients unless the producer maintains both fields during a transition period.

### 17.3. Loosening Matchers Does Not Replace Migration

If the producer wants to change `status: CONFIRMED` to `ACCEPTED`, turning the contract matcher into an arbitrary String just to keep tests green hides broken consumer branching. You need to:

1. Identify which consumers rely on `CONFIRMED`.
2. Agree on versioning/migration.
3. Keep the old behavior or support both in parallel during transition.
4. Maintain contracts/tests for both new and old behaviors while both exist.
5. Remove the old contract only after no consumer depends on it.

### 17.4. Controlled Stub Version Updates

After verification, the producer may publish `com.example:inventory-producer:1.2.4:stubs`. A consumer currently on `1.2.3` needs a plan to bump the stub version and test compatibility against the new release.

Avoid blindly using `+` or `latest` in reproducible CI. A green test against an old stub **does not prove compatibility with a new release**.

## 18. CI: Measure Covered Requirements, Not Just Test Counts

Example producer Maven pipeline configured with Spring Cloud Contract Verifier:

~~~bash
./mvnw -B clean verify
~~~

Or with Gradle configured with the plugin/tasks:

~~~bash
./gradlew clean build
~~~

These commands are examples. CI must confirm that **generated tests are generated, compiled, and executed**, not merely that the build succeeded with 0 tests.

### 18.1. Recommended Quality Gates

| Gate | Question |
| --- | --- |
| Contract review | Which consumers and requirements does a change impact? |
| Producer verification | Did contract tests for key scenarios run and pass? |
| Stub packaging | Does the artifact contain valid mappings with exact coordinates/classifier/version? |
| Consumer verification | Did the consumer client/logic run against the right stub? |
| Negative-path coverage | Were `404`/`400`/`409` and boundary data used by the consumer tested? |
| Version discipline | Which stub version is consumer CI using? Is it updated when the producer changes? |
| Separate reliability tests | Which test types cover out-of-contract requirements? |

### 18.2. A Useful Coverage Report

Instead of reporting only "15 contracts, 35 tests", report:

~~~text
C-01 GET path/header:          COVERED (producer + consumer)
C-02 HTTP 200 JSON:            COVERED (producer + consumer)
C-03 available boolean:        COVERED (producer + consumer)
C-04 quantity number:          COVERED (producer + consumer)
C-05 out-of-stock branch:      COVERED (producer + consumer)
C-06 not-found 404 + code:     MISSING consumer behavior test
C-07 avoid unmatched stub 404: MISSING assertion
C-08 invalid SKU 400:          NOT REQUIRED for current use case
~~~

The labels `COVERED`, `MISSING`, and `NOT REQUIRED` should link to evidence in contracts, tests, or build results within your internal workflow where available.

**Do not turn coverage into simple field counting.** Counting 100 JSON fields while leaving Checkout's required 404 branch unprotected is still an incomplete contract.

## 19. Practice Exercise: Reviewing a Shipping Service Contract

Suppose Checkout Service needs to display estimated shipping fees. Shipping Service (producer) provides:

~~~http
POST /api/shipping/quotes HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "destinationZone": "HCM",
  "weightGrams": 800
}
~~~

Expected response:

~~~json
{
  "quoteId": "Q-123",
  "fee": 30000,
  "currency": "VND",
  "service": "STANDARD"
}
~~~

Consumer requirements:

1. `fee` must be a Number to calculate the checkout total.
2. `currency` must be `VND` when the quote uses Vietnamese Dong in this scenario.
3. `service` must indicate the service tier.
4. `quoteId` must follow a format that can be stored and used when confirming delivery.
5. If `weightGrams` is invalid, the producer must return a specific API-published error.
6. When no service is available in the selected zone, there must be a response branch Checkout can display appropriately.

### 19.1. Task A — Spot the Gaps

Initial contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    request {
        method POST()
        urlPath('/api/shipping/quotes')
        body(
            destinationZone: 'HCM',
            weightGrams: 800
        )
    }

    response {
        status OK()
        body(
            quoteId: 'Q-123'
        )
    }
}
~~~

Identify the gaps:

- Request/response media types are not declared even though the consumer requires JSON.
- `fee`, `currency`, and `service` are not protected.
- No distinction between a dynamic ID field and fixed business fields.
- No invalid-input or unavailable-service branches.
- No consumer tests verifying fee summation and error display.

### 19.2. Task B — Write the Revised Contract

Hint:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_shipping_quote')

    request {
        method POST()
        urlPath('/api/shipping/quotes')
        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }
        body(
            destinationZone: 'HCM',
            weightGrams: 800
        )
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            quoteId: 'Q-123',
            fee: 30000,
            currency: 'VND',
            service: 'STANDARD'
        )
        bodyMatchers {
            jsonPath('$.quoteId', byRegex('Q-[0-9]+'))
        }
    }
}
~~~

Note: Status `200` here is Shipping Service's assumed policy, not a mandatory value for every quote-creation API. If the real API commits to `201`, use `201` and test accordingly.

### 19.3. Task C — Build the Traceability Matrix

Create at least six rows:

| Requirement | Contract Case | Producer Assertion | Consumer Assertion |
| --- | --- | --- | --- |
| Fee is numeric | `create_shipping_quote` | `$.fee` is a number | Calculates total fee accurately |
| Currency VND | `create_shipping_quote` | `currency == VND` | Displays exact currency unit |
| Valid ID | `create_shipping_quote` | Regex `Q-[0-9]+` | Client stores and reuses ID |
| Invalid input | Dedicated 400 contract | Status/error code | Does not proceed with order |
| Service unavailable | Dedicated error contract | Status/body per API | Displays appropriate state |
| Sends valid body | `create_shipping_quote` | Request method/body | Client emits valid request |

### 19.4. Task D — Consumer Tests via Stub Runner

- Start the Shipping Service stub at the right version.
- Point Checkout's real ShippingClient to the stub.
- Send `destinationZone: HCM`, `weightGrams: 800`.
- Verify Checkout displays or calculates using `fee: 30000`, `currency: VND`.
- Exercise invalid-input and no-service cases with the contract-published stub mappings.
- Verify unmatched stub requests are not mistaken for valid business errors.

### 19.5. Task E — Mutation Review

Suppose the producer sequentially:

1. Changes `fee` from `30000` to String `"30000"`.
2. Removes `service`.
3. Changes `currency` to `USD`.
4. Changes `quoteId` from `Q-123` to `INVALID`.
5. Returns `200` for invalid input that previously returned `400`.
6. Keeps the response intact but changes the path to `/api/shipping/prices` and deletes the old route.

For each change, state **which contract assertion is expected to fail**, **which consumer behavior is impacted**, and **whether the producer needs a fix or a new API agreement is required**.

### 19.6. Self-Assessment Questions

1. Why does a passing generated producer test still not prove the consumer sent the right HTTP request?
2. Does `byType()` on `fee` verify the exact price `30000`?
3. Why might a `404` response without an error code indicate an unmatched stub instead of a business error?
4. When is adding a new field compatible? When can it break a strict parser?
5. Why should you avoid using stub version `+` in reproducible CI?
6. Must every timeout and concurrency bug be specified in Spring Cloud Contract?
7. How should a traceability row that has DSL and producer tests but lacks a consumer test be marked?
8. Why should consumer authors approve contracts before accepting breaking changes?

**Guidance:** Contracts specify, producer verification proves the producer, and Stub Runner tests prove the consumer. Choose matchers based on actual invariants; test out-of-interface properties separately.

## 20. Checklist: Are Consumer Requirements Truly Reflected?

- [ ] Identified the consumer use case and the business decision it must make.
- [ ] Listed the method, path, query, headers, and body the client actually sends.
- [ ] Specified the success status and media type.
- [ ] Included all JSON fields/types the consumer reads.
- [ ] Deliberately decided nullability, optionality, lists/maps, and nested structures.
- [ ] Covered success, out-of-stock, not-found, and critical validation/error branches.
- [ ] Constrained error codes if the consumer branches on them.
- [ ] Matchers are not so broad that type mismatches or wrong business codes slip through.
- [ ] Dynamic data uses appropriate matchers instead of hard-coding random IDs/timestamps.
- [ ] Contracts have clear names and locations tracing back to requirements.
- [ ] Producer generated tests are generated, executed, and never skipped.
- [ ] Producer fixtures genuinely construct the contracted scenarios.
- [ ] Stub artifact has the right version, classifier, and mappings.
- [ ] Consumer tests use Stub Runner and invoke **real consumer code**.
- [ ] Consumer assertions verify behavior rather than merely pinging WireMock.
- [ ] 404 tests inspect body/code to avoid false greens from unmatched stubs.
- [ ] When the producer changes a field/path/status, you can point to the exact test that must fail.
- [ ] Migration/versioning plans exist when the API changes incompatibly.
- [ ] Concurrency/security/retry/latency needs are assigned to appropriate separate tests.
- [ ] CI and reviews clearly show which requirements are COVERED, MISSING, or NOT REQUIRED.

## 21. References

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): producer/consumer contract testing architecture, stubs, and build integration.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): method, URL, headers, request, and response DSL.
- [Spring Cloud Contract — Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): producer/consumer values, response matchers, and JSONPath.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): locating/running stubs for consumers.
- [Spring Cloud Contract — Developing Your First Application](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): generated producer verification and consumer use of stubs.
- [Spring Cloud Contract — Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): message contracts by destination, headers, and payload.

**Key takeaway:** Verifying that consumer requirements are reflected in the contract means **tracing from use cases to verifiable criteria**, not merely checking Groovy/YAML syntax. Every critical requirement must trace to a contract, generated producer assertions, an exact-version stub, and a consumer behavior test. Only when both sides and CI verify the exact signals the consumer depends on does the team have real evidence that the API or message contract protects compatibility.
