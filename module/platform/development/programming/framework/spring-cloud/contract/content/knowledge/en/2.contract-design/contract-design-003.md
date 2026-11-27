# Describing Observable Behavior Instead of Implementation Details

## Lesson Objectives

In contract testing between a **producer** (a service providing an API or publishing messages) and a **consumer** (a service or application consuming the API/messages), a good contract must answer the question:

> When the consumer sends a valid request or receives a valid message, what observable behaviors of the producer can the consumer observe and rely on?

A contract does not need to describe which Java classes the producer uses, which tables it stores data in, or how many internal methods it calls. With **Spring Cloud Contract**, observable behaviors are described using the **Groovy DSL** or **YAML DSL**. From there, the tool can generate verification tests on the producer side and produce stubs so the consumer can run integration tests before the two systems run together.

After this lesson, you can:

- Distinguish public commitments from internal implementation decisions.
- Choose the right inputs, outputs, and error cases to put into an HTTP or message contract.
- Write illustrative contracts in Groovy/YAML DSL without coupling tightly to the producer's source code structure.
- Recognize compatible changes versus changes that risk breaking the consumer.
- Understand how generated tests, stubs, Stub Runner, and CI work together to verify those commitments.

## 1. A Contract Is the Boundary the Consumer Actually Sees

Imagine the producer as a **black box**. The consumer only knows how to send requests, receive responses, or handle public messages. The producer can change algorithms, databases, frameworks, or package structures without requiring changes in the consumer, as long as commitments at the integration boundary are preserved.

For an HTTP API, observable behavior typically includes:

| Component | Consumer question | Example commitment |
| --- | --- | --- |
| Request | How do I call the endpoint? | GET /api/orders/ORD-1001 |
| Input | Which parameters, headers, and body fields matter? | Order ID in the URL; Accept: application/json |
| Success response | When valid, what status and data do I receive? | HTTP 200; JSON containing id and status |
| Error response | What if the data does not exist or the input is invalid? | HTTP 404 with error code ORDER_NOT_FOUND |
| Data rules | Which types or value sets can the consumer rely on? | status is a string; PAID indicates the order is paid |
| Public effect | After an operation, what outcome can be observed? | Creating an order successfully returns an order ID usable in subsequent queries |

For a message contract, the observable boundary is the **published/received event**, message type, required data fields, headers or metadata, and how the consumer interprets them. A queue or topic name is only part of the contract if it is genuinely the integration interface committed to the consumer.

Conversely, the following details generally **do not belong in a contract**:

- Whether OrderController calls OrderService or a facade.
- Whether data is read from PostgreSQL, Redis, or another service.
- Whether the producer uses JPA, JDBC, WebFlux, or changes module architecture.
- The number of SQL queries, column names, table names, and method call order.
- Exact processing times or internal hostnames, unless there is an explicit external commitment concerning them.

The key is **classifying by commitment**, not by implementation mechanism. For instance, caching mechanisms are usually internal; however, an HTTP `Cache-Control` header exposed by the producer may be behavior worth verifying. Similarly, an error code is part of the interface if the consumer uses it to decide the next step; a Java stack trace should never be included in a contract.

## 2. Designing from Consumer Needs

Suppose a storefront application needs to display an order's payment status. The producer provides the Order API. The consumer only needs to know whether the order ID exists and what its current status is in order to render the appropriate button or message.

The integration flow can be depicted as follows:

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant P as Producer: Order API
    C->>P: GET /api/orders/ORD-1001
    alt Order exists
        P-->>C: 200 {"id":"ORD-1001","status":"PAID"}
        Note over C: Display "Paid"
    else Order not found
        P-->>C: 404 {"code":"ORDER_NOT_FOUND"}
        Note over C: Display appropriate message
    end
~~~

To design the contract, answer these in order:

1. **Who is the consumer and what decision do they need to make?** The storefront app needs to know the order status.
2. **Which input signals matter?** The GET method and the order ID in the path.
3. **What minimal output signals are sufficient?** HTTP status, id, status, and the error code when not found.
4. **Which rules need to stay stable?** Data types, the meaning of PAID, HTTP 200/404, and the error structure.
5. **What can change without affecting the consumer?** Class names, database schema, caching, and status-fetching algorithms.

This mindset avoids two extremes: contracts that are **too vague** (only checking HTTP 200 so wrong data still passes) and contracts that are **too detailed** (forcing the producer to preserve fields or details the consumer does not use).

## 3. Specifying an HTTP Behavior with YAML DSL

A contract for retrieving a paid order can be written as follows:

~~~yaml
description: "Returns the status of an existing order"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

This example describes **one verifiable case**:

- With GET and the specified path, the producer must accept a request containing the corresponding Accept header.
- The producer must return HTTP 200 and a JSON payload with the declared values.
- The consumer can rely on the id and status fields; it does not need to know where the data is loaded from.

In this example, `ORD-1001` and `PAID` are **deterministic sample data**. When running tests generated by Spring Cloud Contract, the producer must prepare test data state matching this sample (for instance via test fixtures). This is not an instruction to create a real record in the production database.

If the consumer only needs the **format** of a dynamically generated ID or timestamp, do not hardcode a random value in the contract. Spring Cloud Contract supports matchers/expressions and distinct values for the consumer vs. producer sides; the right choice depends on the DSL version and the rule you want to commit to. Assert only the invariant part—for example, that the field is a string, matches a valid format, or belongs to a published set of values.

### Same behavior in Groovy DSL

In a project using the Groovy DSL, the equivalent case can be expressed as:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description("Returns the status of an existing order")

    request {
        method GET()
        url "/api/orders/ORD-1001"
        headers {
            header("Accept", "application/json")
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "PAID"
        )
    }
}
~~~

Both representations share the same goal: specifying a **sendable request** and a **verifiable public response**. Choose the DSL according to project standards and required features; there is no need to write both for the same scenario.

### Contracts for error paths

Describing only the success case is not enough if the consumer needs to distinguish an error from an empty result. Another contract for a non-existent order ID:

~~~yaml
description: "Returns an error when the order is not found"
name: get_unknown_order
request:
  method: GET
  url: /api/orders/ORD-9999
  headers:
    Accept: application/json
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
~~~

Structured error codes help consumers handle failures more reliably than depending on an entire message sentence that might be translated or reworded. Only specify the display message if that wording **is also** part of the public commitment.

For write APIs, you may need contracts for invalid input (400), missing permissions (401/403), or state conflict (409) **when those branches are genuinely part of the behavior the consumer uses**. You do not have to list every hypothetical error: each contract should serve a concrete integration scenario.

## 4. Do Not Turn Contracts into Source-Code Structure Tests

Suppose the producer initially handles requests via OrderController, OrderService, and OrderRepository. If contract tests depend on how many times the repository is called, switching to a cache or another API will break tests even though the consumer still receives the exact same data.

Example of a test overly coupled to implementation:

~~~java
// This is an internal interaction test, NOT an API contract.
verify(orderRepository, times(1)).findById("ORD-1001");
verify(orderMapper).toResponse(any());
~~~

Interaction checks like this can be useful in a targeted **unit test**. But for the producer–consumer boundary, what needs to be guaranteed is:

~~~text
Request:  GET /api/orders/ORD-1001
Response: HTTP 200
          Content-Type: application/json
          {"id":"ORD-1001","status":"PAID"}
~~~

Practical difference:

| When the producer changes... | Does the behavior contract need to change? | Why |
| --- | --- | --- |
| Switches from SQL to another data source | No, if the public response remains unchanged | The consumer does not access storage internals |
| Splits one service into multiple classes | No | The call graph is an internal detail |
| Renames JSON field `status` to `state` | Risks breaking the consumer | The consumer reads the public field name |
| Changes not-found response from 404 to 200 with empty body | Risks breaking the consumer | The consumer may control flow by status |
| Adds an optional JSON field | Usually compatible, verify first | Depends on how the consumer parses data and schema commitments |
| Changes the set of `status` values, e.g. removes PAID | Risks breaking the consumer | The business meaning of the data changed |

A practical rule of thumb: **if a change stays strictly inside the producer and the consumer cannot distinguish it through the published interface, do not write a contract that forces that change to leak out**.

## 5. Contract Precision: Tight Enough, Flexible Enough

Not every value in a response needs to match character for character. Conversely, whatever the consumer relies on must be specified precisely enough.

### Things to constrain explicitly

- Endpoint method, path, and required parameters.
- HTTP statuses used by the consumer for branching.
- JSON field names, data types, and necessary business semantics.
- Significant business-domain values (such as PAID, CANCELLED).
- Headers like Content-Type, Location, or versioning headers **if the consumer depends on them**.
- Formats of monetary amounts, identifiers, timestamps, or error codes when those formats are part of the public interface.

### Things to avoid constraining arbitrarily

- Property order inside a JSON object, when order has no meaning.
- Specific timestamps, UUIDs, or random values if the consumer only needs the format.
- Millisecond-level response durations in functional contracts; performance SLAs have dedicated verification methods.
- Headers injected automatically by proxies or deployment environments that the consumer does not use.
- Debug fields, stack traces, node names, file paths, or internal data.
- The entire contents of an object just because the producer currently returns it, even though the consumer uses very few fields.

**Example with monetary amounts:** if the consumer calculates or displays a total amount, explicitly decide whether the amount is represented as an integer in the smallest currency unit, a decimal number, or a string, and where the currency code lives. Do not switch the type from number to string simply because the producer switched money libraries. That is an interface decision that can impact the consumer.

**Example with timestamps:** if the system requires ISO-8601 format with timezone, validate the format and temporal semantics rather than forcing every run to return the exact same instant. Avoid creating flaky tests tied to the system clock.

A contract is not a verbatim copy of every response ever seen in production. It is a set of **intentional examples and rules** that both sides agree to uphold.

## 6. Observable Behavior of Asynchronous Messages

Beyond HTTP, Spring Cloud Contract also supports describing contracts for message-based interactions. For an event indicating an order was paid, the consumer typically cares about the event type and payload:

~~~json
{
  "eventType": "ORDER_PAID",
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-24T04:00:00Z"
}
~~~

This is an **illustrative payload sample**, not a YAML/Groovy contract file itself. In an actual messaging contract, describe the triggering input or producer output, the send/receive destination if that is a public interface, and the corresponding matchers.

Identify what the consumer actually depends on:

| Needs commitment | Do not lock tightly unless publicly committed |
| --- | --- |
| Event type ORDER_PAID | Java class name that constructs the event |
| Field `orderId` is a validly formatted order ID | Internal record ID used in the database |
| Meaning and format of `occurredAt` | Fixed timestamp from the example |
| Routing or version headers when used by the consumer | Thread pool settings or internal serialization approach |
| Ordering, duplicate possibility, or delivery guarantees **if agreed upon** | Internal retry strategies not exposed on the interface |

In particular, never implicitly assume every messaging system guarantees exactly-once delivery or global ordering. If the consumer relies on those properties, there must be a communication agreement and appropriate system-level tests; a sample payload cannot prove all of those operational characteristics.

## 7. How Behavioral Contracts Feed into Testing and CI

Spring Cloud Contract turns behavioral specifications into executable assets.

~~~mermaid
flowchart TD
    A["Groovy/YAML Contract"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generate producer-side tests"]
    B --> D["Generate mappings/stubs"]
    C --> E["Build and test producer in CI"]
    D --> E
    E -->|"Tests pass"| F["Package and publish stubs"]
    F --> G["Consumer uses Stub Runner"]
    G --> H["Consumer integration tests"]
~~~

**Producer side:** The Verifier generates tests from the requests and responses in the contracts. Tests call into the application or an appropriate test setup, so the test environment must prepare data such as ORD-1001 and ORD-9999. If the producer changes not-found from 404 to 200, the generated test from the corresponding contract can fail immediately in the producer's CI.

**Consumer side:** Stubs published from contracts allow the consumer to test how it issues HTTP calls and handles responses without running a real producer in the same environment. **Stub Runner** helps locate and run published stubs to integrate into consumer tests. The consumer can verify UI rendering flows, error handling, or subsequent API calls based on sample responses.

**In CI:** a typical cycle consists of checking contracts on the producer side, running generated tests, packaging/publishing stub artifacts after tests pass, and then consuming the corresponding artifacts in consumer tests. Which repository hosts the artifacts, how versions are selected, and when tests run depend on the project's pipeline.

Key point to remember: **stubs only show how the consumer behaves with a specified response; producer-side tests verify that the producer actually meets that specification**. Both sides complement each other. Running only consumer tests with stubs without verifying the producer can create a false sense of compatibility if stubs are stale or fail to reflect real behavior.

## 8. Identifying Incompatible API Changes

Suppose a consumer already uses a contract receiving payment status:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

The following producer changes should be evaluated before release:

| Producer change | Potential impact | Action to take |
| --- | --- | --- |
| Rename `status` to `paymentState` | Consumer reading `status` breaks | Keep the old field temporarily, or agree to bump contract version and migrate consumer |
| Change `status` from string to number | Parser/business logic may fail | Avoid changing types on an existing interface |
| Change 404 to 204 | Error-branching logic may change | Discuss with consumer, update contract and both sides' tests |
| Add optional `description` field | Usually safe for consumers that ignore unknown fields | Verify deserialization behavior; document optional field |
| Add status value `REFUNDED` | Consumers using a closed enum may fail to handle it | Check handling of new values and commitments around the value set |
| Change storage strategy while keeping HTTP response identical | Consumer is unaffected | No contract update needed solely for internal refactoring |

There is no absolute rule that every added field is always compatible: a consumer configured with a strict parser may still reject unknown fields. Conversely, two systems can intentionally design extensibility rules. Therefore, evaluate based on **the behavior the consumer depends on and the compatibility agreement**, not merely whether the JSON remains valid.

When making major changes, consider maintaining the old behavior during a transition period, publishing contracts and stubs for each version, running consumer tests against the appropriate version, and then retiring the old behavior according to an agreed schedule.

## 9. Common Design Pitfalls

### Pitfall 1: Checking only status 200

A contract that only commits to status 200 can still pass even if the producer returns an empty body or omits the `status` field the consumer needs. Declare **the minimal required fields and semantics**.

### Pitfall 2: Copying an entire internal entity into the contract

If the body includes every field of OrderEntity, schema changes or adding columns can force unnecessary contract updates. Design public DTOs around consumer needs and commit only to externally meaningful fields.

### Pitfall 3: Using random data while asserting exact equality

Hardcoding timestamps or UUIDs regenerated on every run causes flaky test failures. Use fixed fixtures for deterministic scenarios; use appropriate matchers when the requirement is a format or data relationship.

### Pitfall 4: Using stubs to replace all testing

Stubs help test the consumer's integration against a controlled simulation. They do not replace tests for internal logic, authorization, network reliability, performance, or end-to-end system tests. The producer must still run contract verification tests.

### Pitfall 5: Failing to align on business semantics

Two sides may both use `status` as a string while interpreting `PAID` or `CANCELLED` differently. Contracts should include descriptions of semantics or business rules when data types alone are insufficient to express the commitment.

## 10. Practice Exercises

**Exercise A — Choose the contract boundary.** A producer returns an order via a GET API. Someone suggests adding the following fields to the JSON: id, status, databaseShard, cacheHit, totalAmount, currency. The consumer only needs to display the status and total amount with currency unit. Choose which fields need commitment, explain why the rest should be excluded, and consider whether `id` is needed.

**Exercise B — Add an error case.** Write a separate YAML contract for GET /api/orders/ORD-9999 returning HTTP 404 with a body containing `code: ORDER_NOT_FOUND`. Explain why changing only the body of the success contract is insufficient without changing the HTTP status and input data.

**Exercise C — Assess a change.** The producer switches storage from SQL to Redis, renames JSON `status` to `state`, and adds an `X-Request-Id` header. Identify which changes require negotiation with the consumer. Then describe how producer tests and consumer tests with Stub Runner will detect the discrepancy.

**Self-check hints:** For Exercise A, `status`, `totalAmount`, and `currency` serve the public need; `id` needs commitment if the consumer uses it to correlate the right order. `databaseShard` and `cacheHit` are internal details in this context. For Exercise C, renaming `status` risks breaking the contract; changing the storage backend usually does not. A new header only becomes part of the commitment if the consumer is required to use it or if it affects compatibility.

## Checklist Before Finalizing a Contract

- [ ] Clearly identify the consumer and concrete use case.
- [ ] Commit only to requests, responses, events, and effects observable from the integration interface.
- [ ] Check all statuses, data types, field names, and error codes needed by the consumer.
- [ ] Avoid constraining internal classes, repositories, databases, caches, and debug details.
- [ ] Distinguish fixed fixture data from fields requiring matchers/format rules.
- [ ] Include important error cases instead of checking only the happy path.
- [ ] Prepare fixtures so producer-side generated tests run deterministically.
- [ ] Publish stubs from producer-verified contracts and run consumer tests with Stub Runner.
- [ ] Evaluate compatibility before changing any public interface.

**Remember:** Spring Cloud Contract works best when contracts describe **what the consumer is entitled to expect**, specific enough for automated tests to catch discrepancies yet independent enough for the producer to improve internal implementations. This is the foundation for meaningful producer–consumer contract testing and CI pipelines that catch incompatible API changes.
