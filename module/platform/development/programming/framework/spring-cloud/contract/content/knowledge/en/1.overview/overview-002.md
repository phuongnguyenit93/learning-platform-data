# Producer, Consumer, and the Communication Boundary Between Both Sides

## Learning Objectives

After this lesson, you can:

- Distinguish between the **producer** (the interface provider) and the **consumer** (the interface caller) in a multi-service system.
- Identify the **contract boundary**: which behaviors need to be agreed upon and tested, and which details belong internally to each service.
- Read an HTTP contract written in **Spring Cloud Contract Groovy DSL** and explain how it generates producer-side tests and consumer stubs.
- Recognize compatible changes versus changes at risk of breaking consumers; know how to coordinate teams and integrate contract checks into CI.

## 1. Who Are the Producer and Consumer?

In a service architecture, two sides communicate through a published interface, such as an HTTP API or a message sent over a broker.

- **Producer (provider)** is the party that **provides** the interface and implements the behavior behind it. For HTTP, the producer receives requests and returns responses; for messaging, the producer may be the service emitting messages.
- **Consumer** is the party that **depends on** that interface to complete its work. For HTTP, the consumer sends requests and processes responses; for messaging, the consumer may be the service subscribing to messages.
- **Contract** is a verifiable description of how both sides interact: valid inputs, expected outputs, and rules the consumer can rely on.

For example, an e-commerce system has:

| Component | Role in Interaction | Responsibility |
|---|---|---|
| `Checkout Service` | Consumer | Queries remaining stock to display before the buyer confirms an order |
| `Inventory Service` | Producer | Exposes the inventory check endpoint and returns data matching the contract |
| Inventory contract | Agreement at the boundary | Specifies path, method, data types, and responses for agreed cases |

Roles **depend on each interaction**, rather than being fixed for an entire application. `Inventory Service` may be a producer when answering `Checkout Service`, yet act as a consumer when calling a warehouse service. In an event-driven system, the same service may also both receive and emit different types of messages.

Spring Cloud Contract helps turn this agreement into an **executable specification**: from one contract, the tool can generate tests for the producer and generate stubs for the consumer to test integration without starting the real producer.

## 2. Where Does the Communication Boundary Lie?

Imagine two independent development teams. The Checkout team does not need to know whether Inventory stores data in PostgreSQL, Redis, or calls other services. The Checkout team only needs to know: *if it sends a valid request according to the published interface, what will it receive and how must it handle it?*

That is the communication boundary. A contract describes **externally observable behavior**, not how the producer creates that behavior.

| Belongs to the Boundary (Can Be Put in Contract) | Internal Implementation (Should Not Be Constrained) |
|---|---|
| HTTP method, path, required query parameters | Controller/service class names, package structure |
| Communication-related headers, content format, agreed authentication | Order in which internal functions are called |
| HTTP status code and response JSON/XML structure | Database tables, column names, query algorithms |
| Required fields, data types, values, or matching rules | Producer's internal framework or libraries |
| Success cases, error cases meaningful to the consumer | Logging details, caching, and internal retry implementation |
| For messaging: destination, metadata/headers, event payload structure | How the producer stores events in an outbox |

A good contract needs to be **specific enough** to detect integration-breaking changes, without tying the producer down to details the consumer does not need. For example, Checkout may require `available` to be a boolean and `quantity` to be a non-negative integer; it should not force every dynamic value in real environments to equal the exact example data. Spring Cloud Contract's Groovy/YAML DSL supports matchers to express more flexible rules than literal equality.

> **Distinguishing contracts from all operational guarantees:** contract tests verify defined behavioral examples. They do not by themselves prove that the system meets all load, latency, security, resilience, or business edge-case requirements. Those aspects require additional verification and monitoring.

## 3. Example: Checkout Calls the Inventory API

Suppose the producer exposes the API:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Host: inventory.example.internal
Accept: application/json
~~~

For an existing product, the producer returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 12
}
~~~

In this example, the consumer relies on the following rules:

1. Call `GET /api/inventory/{sku}` to retrieve inventory information for a SKU.
2. When receiving `200 OK`, read `sku` (string), `available` (boolean), and `quantity` (number).
3. If the SKU does not exist, there must be a separately agreed error case, such as `404 Not Found` with a machine-readable error code.
4. Do not infer that `available: true` reserves stock. Quantities can change after the check; reserving inventory requires a different business flow or endpoint.

The fourth point is crucial: **data contracts** and **business semantics** must stay aligned. If the producer only guarantees a snapshot of inventory at query time, the consumer cannot treat it as a promise that stock will still exist when placing an order.

### A Contract in Groovy DSL

In the producer project integrated with Spring Cloud Contract, a contract file can be stored at, for instance, `src/test/resources/contracts/inventory/shouldReturnAvailableStock.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Return inventory for a known SKU'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 12
        )
    }
}
~~~

Reading the contract from top to bottom:

- `request` specifies that the producer must accept a `GET` request with the stated URL and headers.
- `response` specifies the expected response: status `200`, JSON content type, and body fields.
- `description` helps the team understand the purpose of the example; it does not replace the rules in `request` and `response`.

This is **one concrete contract case**, not documentation describing every SKU. For dynamic URLs or values, Spring Cloud Contract matchers can be applied to define value types and appropriate matching rules. The non-existent SKU case must have another contract if the consumer relies on that error response.

Spring Cloud Contract also supports YAML DSL to express equivalent scenarios. The two formats are **ways of writing specifications** and do not change producer/consumer roles or boundary principles.

## 4. Who Verifies What?

<details>
<summary>Contract verification flow for HTTP</summary>

~~~mermaid
flowchart LR
    A["Groovy/YAML Contract<br/>agreed by both sides"] --> B["Generate producer-side tests"]
    A --> C["Generate HTTP stub"]
    B --> D["Run against real producer app"]
    C --> E["Consumer runs tests with Stub Runner"]
    D --> F{"Producer complies?"}
    E --> G{"Consumer interprets correctly?"}
    F -->|Yes| H["Producer build can publish stub"]
    F -->|No| I["Fix producer or negotiate change"]
    G -->|No| J["Fix consumer or clarify contract"]
~~~

</details>

**Producer side:** the tool generates tests from the DSL. When configured properly, these tests call the real application (or the HTTP layer set up for testing) and confirm whether the producer's output matches the contract examples. The producer needs to configure the test environment, the base class for generated tests, and required test data; simply placing a Groovy file in the project is not enough to guarantee all tests run automatically.

**Consumer side:** the stub generated from the contract acts as a simulated producer at the HTTP boundary. The consumer sends requests to the stub via **Spring Cloud Contract Stub Runner** (or WireMock configured accordingly), then tests its own API calling logic, response deserialization, and result handling.

| Verification Question | Producer Contract Test | Consumer Test Using Stub |
|---|---|---|
| Does the real producer application return the committed behavior? | **Yes**, for the cases covered by contracts | No, because it calls a fake producer |
| Does the consumer send the right request and read the response per contract? | Does not fully verify consumer code | **Yes**, if consumer tests are written for those flows |
| Do end-to-end execution, networking, and real infrastructure work? | Not sufficient | Not sufficient |

For example, the consumer passing against a stub **does not prove** the producer has implemented it properly. Both results must go together: the producer must pass the generated tests, and the consumer must test integration logic against the corresponding stub.

### Typical Collaboration Cycle

1. **Agree on needs:** the consumer proposes specific behaviors its application depends on, such as the `available` field and its meaning.
2. **Define the contract:** producer and consumer review the HTTP/message cases to support, then store contracts in version control (usually the producer's repository or a shared contracts repository).
3. **Verify the producer:** the pipeline generates and runs contract tests against producer code. If tests fail, the change does not comply with the current contract.
4. **Publish the stub:** when verification succeeds, the build can package the stub artifact (with Maven typically using the `stubs` classifier) and upload it to an artifact repository.
5. **Verify the consumer:** the consumer fetches the **exact stub version** and uses Stub Runner to execute its interaction tests.
6. **Integrate with CI:** pipelines provide early feedback automatically whenever either side changes the interface, before release or deployment to a shared environment.

Plugin names, contract file locations, base test creation, artifact repositories, and stub version selection depend on the project's Spring Cloud Contract configuration. Never assume two pipelines are using the same contract version just because both are green: **contract/stub versioning is part of coordination**.

## 5. When Can a Change Break the Consumer?

Compatibility must be evaluated **from what the consumer actually depends on**. For example:

| Producer-Side Change | Risk | Reason |
|---|---|---|
| Change `quantity` from number to string | High | Consumer deserializing to a number may fail |
| Change `GET /api/inventory/{sku}` to another path without keeping the old path | High | Old requests are no longer supported |
| Change success response from `200` to `204` and drop body | High | Consumer expects a body to process |
| Change meaning of `available` while keeping the same name and data type | High, hard to detect if contract lacks business rules | JSON stays valid, yet ordering decisions can be wrong |
| Add an optional field to the JSON response | Usually low risk **if** consumer ignores unknown fields | Consumers with strict deserializers can still be affected |
| Replace PostgreSQL with another database while preserving external behavior | Usually does not affect the contract | Storage details lie outside the boundary |

There is no universal rule that "adding a field is always compatible." Compatibility also depends on how the consumer parses data, whether fields are required, what the contract publishes, and how both sides manage versions.

When a major change is needed, you can keep the old interface for a transition period, introduce a new version, let consumers migrate gradually, and then retire the old interface on an agreed schedule. Contract tests and stub tests help catch expectation-breaking changes early, but API evolution decisions still require cross-team coordination.

## 6. With Messaging, Who Are the Producer and Consumer?

For a `StockChanged` event:

- `Inventory Service` is the **message producer** because it emits the event.
- `Checkout Service` (if subscribed) is the **message consumer** because it processes the event.
- The boundary can include the **destination**, **headers**, **payload**, event type, identifiers, and fields needed for processing.

Example of an expected payload:

~~~json
{
  "eventType": "StockChanged",
  "sku": "SKU-101",
  "quantity": 8
}
~~~

A change such as turning `quantity` from a number into a string can still break the consumer, even without an HTTP request/response. Spring Cloud Contract supports describing message interactions in the DSL and generating tests for emit/receive behavior matching the project's messaging setup.

Guarantees regarding **event ordering, at-least-once delivery, deduplication, and replay timing** depend on the broker system and business design. If the consumer needs them, they must be specified and tested additionally. A single payload example does not prove all of those guarantees.

## 7. Common Misconceptions

**Misconception 1: The consumer must wait for the real producer to run before it can test.** Stubs from Spring Cloud Contract allow the consumer to test API-calling logic independently of the producer environment. Even so, producer contract tests and an appropriate level of integration testing are still required.

**Misconception 2: Contract tests cover all business logic.** Contracts only verify the described scenarios. If only happy-path cases exist, `400`, `401`, `404`, timeouts, or other error responses that the consumer relies on will not be protected by contracts.

**Misconception 3: Locking down every JSON value is always better.** Variable data like IDs, timestamps, and stock quantities need suitable matchers when literal equality is not required. Overly strict checks cause false positives; overly loose checks miss interface-breaking changes.

**Misconception 4: Any field a consumer uses automatically becomes part of the contract.** Consumers should not read experimental fields or rely on JSON key ordering unless the producer has committed to them. Both teams must document meaningful dependencies before treating them as producer obligations.

**Misconception 5: Green tests mean the stub in use matches what will be released.** If the consumer uses an outdated stub, tests can still pass while the producer is preparing a new change. CI needs policies for selecting, updating, and verifying stub versions.

## 8. Thought Exercise

You are building `Checkout Service` consuming `Inventory Service`. The producer team proposes returning:

~~~json
{
  "sku": "SKU-101",
  "available": "yes",
  "quantity": 12,
  "warehouse": "WH-01"
}
~~~

In the previous contract, `available` was a boolean and `warehouse` was absent.

1. **Which change raises an immediate warning?** The value of `available` changing to a string: consumers expecting a boolean may fail. Adding `warehouse` depends on the policy for parsing unknown fields.
2. **Which tests detect the failure?** The producer contract test expecting `available` as a boolean will mismatch the new response. Consumer tests with the new stub help reveal that consumer logic cannot deserialize or handle string values.
3. **What should the two teams discuss?** Is the producer required to change the type? Can it keep the boolean and add a separate field for detailed status? If the change is unavoidable, what is the versioning migration plan and when will old behavior be retired?

### Self-Check

- Can you explain why a service can simultaneously be a producer and a consumer?
- Can you distinguish externally observable API behavior from internal producer implementation details?
- Can you state why **both** producer contract tests **and** consumer tests with stubs are needed?
- Can you point out at least one error case that should be added beyond the success response?

## Key Takeaways

**The producer commits to behavior at the interface, and the consumer relies on that behavior.** Spring Cloud Contract records the commitment using Groovy or YAML DSL, then supports two-sided verification: generating tests against the producer implementation and generating stubs for the consumer to test integration. The value of contracts lies in clarifying **dependency boundaries** and detecting early when both sides no longer share the same understanding of the interface.
