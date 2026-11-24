# Documenting Contracts and Responsibilities of Each Participating Party

## Objectives

In a messaging system, producers and consumers must agree on how to send, receive, and interpret messages. If routes, payloads, metadata, errors, or retry rules exist only in code, teams easily build incompatible integrations and struggle when the system evolves.

This lesson focuses on message contracts in Spring RSocket. After this lesson, you will be able to:

- Identify the essential components of a message contract.
- Document routes, interaction models, payloads, metadata, errors, and lifecycles.
- Define responsibilities for requesters, responders, service owners, and operations teams.
- Manage contract versions and backward-compatible changes.
- Design examples, contract tests, and a change publication process.
- Organize documentation so other teams can integrate without reading internal implementations.

## 1. What Is a Message Contract?

A message contract is a verifiable agreement between parties exchanging messages. It describes what one party is permitted to send, what the other must understand, and what outcomes each side can expect.

A good contract answers these questions:

1. Who sends the message and who handles it?
2. Which route is called, and what does the route mean?
3. Which RSocket interaction model is used?
4. What is the structure and data type of the payload?
5. Which metadata is required and which is optional?
6. How are success, business rejections, and technical errors represented?
7. Are ordering, deadlines, retries, or idempotency guaranteed?
8. Who owns the contract, who approves changes, and who provides support during incidents?

A contract is the public communication boundary between services. Implementations may change internally as long as they continue satisfying the published contract.

### 1.1. Distinguishing Contract from Implementation

| Contract | Implementation |
|---|---|
| Route orders.submit | Java method name in a controller |
| Payload SubmitOrder | How orders are stored in the database |
| Response OrderAccepted | Repositories, transaction managers, and SQL statements |
| Error code ORDER_REJECTED | Internal exception class |
| Tenant metadata and correlation ID | How the system extracts tenant info from security context |
| Published maximum timeout | Specific timeout settings inside each client |

Do not expose internal details such as database table names, private packages, stack traces, or unnecessary algorithms in the contract. Publish only the details consumers need to integrate and operate correctly.

### 1.2. A Contract Is a Two-Way Agreement

The requester is responsible for sending valid payloads, calling the right route, supplying required metadata, and handling responses or errors. The responder is responsible for validating inputs, executing the published semantics accurately, and returning results per the contract.

Both sides must agree on timeouts, cancellation, retries, versioning, and how to handle ambiguous outcomes. A contract is incomplete if it documents only the request DTO while omitting errors, stream termination, or responsibilities upon connection loss.

## 2. Components That Must Be Documented

### 2.1. Identification and Ownership

Every contract should include:

- API or capability name, e.g., Inventory Reservation.
- Stable identifier, e.g., inventory-reservation.
- Contract version and effective date.
- Service owning the responder and support contact group.
- Registered consumers or dependents relying on the contract.
- Links to schemas, examples, changelog, and operational guides.
- Lifecycle status: draft, active, deprecated, or retired.

Service names and route names should remain stable. Do not use Java class or method names as contract identifiers because implementations can be renamed without changing the API.

### 2.2. Transport and Encoding

For RSocket, specify:

- Transport: TCP or WebSocket.
- Host/port or WebSocket mapping path in each environment.
- Data MIME type, e.g., application/json.
- Metadata MIME type, e.g., message/x.rsocket.composite-metadata when using composite metadata.
- Supported codecs or serialization rules.
- TLS and connection authentication requirements.
- Payload and metadata size limits.
- Keepalive, timeout, and reconnect/resume policies if consumers need to know them.

Never include credentials, real tokens, or sensitive infrastructure addresses in public documentation. Use placeholders and deliver environment details via secure configuration channels.

### 2.3. Routes and Interaction Models

A route is the logical name used by a requester to direct messages to a handler. In Spring, routes are typically mapped via @MessageMapping.

Document for each route:

- Exact route name, including case sensitivity if the system enforces it.
- Business purpose.
- Requester and responder.
- Interaction model.
- Input and output payload types.
- Cardinality: single response or multiple responses.
- Ordering: whether order is guaranteed.
- Completion conditions and error conditions.
- Timeouts, retries, idempotency, and load limits.

Four common interaction models:

| RSocket Model | What the Contract Must State |
|---|---|
| Request-Response | One request, one response or one error. |
| Request-Stream | One request, zero or more response payloads, followed by complete or error. |
| Request-Channel | Both sides exchange streamed payloads; document inbound and outbound directions separately. |
| Fire-and-Forget | No business response payload; describe how to confirm or query status on another route if needed. |

For streams, clearly document what happens when the client cancels, the server errors, the connection drops, or the producer has no more data. Never assume a stream always emits at least one item.

### 2.4. Payload Schema

Each payload must document:

- Field names and business meaning.
- Data types, formats, and units.
- Required vs. optional.
- Whether `null` is valid.
- Validation rules and length bounds.
- Default values, if any.
- Compatibility rules when adding or removing fields.
- Valid and invalid request/response examples.

Avoid vague field names like value, data, or status without definitions. For monetary amounts, specify currency and precision rules. For timestamps, specify format, timezone, and timestamp meaning.

Example request schema:

~~~json
{
  "requestId": "req-2026-0042",
  "customerId": "cust-101",
  "amount": 125000,
  "currency": "VND"
}
~~~

Meaning:

| Field | Type | Required | Rules |
|---|---|---|---|
| requestId | string | Yes | Unique ID for the logical request; preserved when retrying the same operation. |
| customerId | string | Yes | Customer ID issued by the identity system. |
| amount | integer | Yes | Monetary amount in the minor unit specified by the contract; this example uses whole VND. |
| currency | string | Yes | ISO 4217 currency code, e.g., VND. |

If decimals are required, specify precision, scale, and rounding rules explicitly. Avoid letting consumers guess units or rounding rules.

### 2.5. Metadata

Metadata typically carries control or contextual information outside the business payload, such as:

- Authentication credentials or tokens per the agreed security mechanism.
- Correlation IDs and trace context.
- Tenant or organization context.
- Locale or client capabilities if genuinely needed.
- Deadlines or priority information per system policy.

Each metadata field needs a name, encoding, origin, required/optional status, applicability scope, and validation rules. Distinguish connection-level SETUP metadata from per-request metadata. A value sent in SETUP may persist for the connection's lifetime; do not rely on it for data that varies per request if the contract expects updates.

Never trust a tenant ID or role merely because a consumer sent it in metadata. The responder must authenticate identity and check permissions on the specific resource.

## 3. Documenting Errors and Outcomes

A contract must help consumers distinguish business outcomes from protocol or infrastructure errors.

### 3.1. Three Outcome Categories

| Category | Example | Representation |
|---|---|---|
| Success | Order accepted. | Response payload matching schema. |
| Business rejection | Quota exceeded, item out of stock. | Business outcome with stable code or published error convention. |
| Technical error | Service unavailable, connection error, unexpected failure. | RSocket ERROR or transport error; may include standardized error codes. |

For business cases consumers are expected to handle normally, return a response DTO with a clear status and error code. Avoid throwing exceptions for routine business rejections if doing so forces consumers to parse unstable error message strings.

Technical errors should be categorized clearly enough for consumers to decide whether to retry or stop. Never expose stack traces, SQL, internal hostnames, or credentials in error payloads.

### 3.2. Stable Error Codes

Example business response:

~~~json
{
  "requestId": "req-2026-0042",
  "status": "REJECTED",
  "code": "LIMIT_EXCEEDED",
  "message": "The requested amount exceeds the allowed limit",
  "retryable": false
}
~~~

Every code should have a definition, trigger condition, required consumer action, and retry rule. Human-readable messages may change or be localized; consumers should rely on stable codes.

An error catalog might include:

| Code | Meaning | Retry |
|---|---|---|
| VALIDATION_FAILED | Invalid payload. | No; fix the request. |
| NOT_AUTHORIZED | Principal lacks permission to execute. | No; fix permissions. |
| RESOURCE_NOT_FOUND | Target resource does not exist. | Usually no; verify ID. |
| BUSINESS_RULE_REJECTED | Rejected by business rules. | Do not retry automatically. |
| TEMPORARY_UNAVAILABLE | Dependency temporarily unavailable. | May retry with backoff and limits. |
| REQUEST_TIMEOUT | No outcome received within deadline. | Query status before retrying side-effecting operations. |
| INTERNAL_ERROR | Unexpected error. | Per retry policy; use correlation ID to investigate. |

### 3.3. Timeouts and Indeterminate Outcomes

A timeout does not prove the responder has not processed the request. The server may have already committed side effects while the response failed to reach the consumer.

For operations with side effects, the contract should specify:

- A stable request ID or idempotency key.
- A status lookup route if consumers can lose responses.
- Status retention period and how long consumers may query it.
- How to retry without creating duplicate side effects.
- How to handle `PROCESSING` or `UNKNOWN` statuses.

Never document a timeout as a guaranteed `FAILED` result unless the server has confirmed the business state.

## 4. Assigning Responsibilities to Each Party

In a messaging system, responsibilities must be divided clearly. Consumers should never have to guess a responder's internal rules, and responders should never rely on undocumented consumer behavior.

### 4.1. Requester / Consumer

The requester is responsible for:

1. Reading and complying with the published contract version.
2. Sending the correct route, payload schema, and required metadata.
3. Validating data client-side to catch errors early, without replacing server-side validation.
4. Setting deadlines/timeouts aligned with business requirements.
5. Handling responses, errors, stream completion, and cancellation.
6. Retrying only when permitted by the contract; preserving the idempotency key for the same logical operation.
7. Never assuming a timeout means the operation did not happen.
8. Protecting credentials and sensitive data in logs.
9. Testing compatibility against supported responder versions.
10. Notifying the service owner when contract changes are needed or behavior diverges from documentation.

Consumers must not invent interpretations for new fields, new enums, or undefined error codes. When encountering unknown values, apply safe fallbacks according to agreed compatibility rules.

### 4.2. Responder / Provider

The responder is responsible for:

1. Publishing routes, interaction models, payloads, and metadata.
2. Validating requests at the service boundary.
3. Authenticating identity and authorizing every operation.
4. Executing published business semantics and transaction boundaries accurately.
5. Returning responses or errors conforming to stable schemas and rules.
6. Implementing idempotency when the contract promises safe retries.
7. Never leaking internal details or sensitive data in responses.
8. Maintaining compatibility throughout the support window for active consumers.
9. Providing changelogs, examples, and migration guides.
10. Monitoring errors, latency, and route usage to detect the impact of changes.

Responders must never silently alter field meanings, units, ordering, or error semantics that consumers rely on.

### 4.3. Service Owner / Contract Owner

The contract owner is responsible for documentation quality and lifecycle:

- Defining the API's purpose and scope.
- Designating requester/responder teams and accountable owners.
- Approving schemas, routes, error models, and compatibility changes.
- Managing versions, changelogs, deprecations, and retirement dates.
- Maintaining verifiable examples and contract tests.
- Coordinating with impacted consumers before breaking changes.
- Defining support channels and incident escalation paths.

The contract owner may be the service team owning the responder. Designate a specific maintainer so contracts do not go stale.

### 4.4. Platform / Operations

Platform and operations teams are responsible for the runtime environment:

- Provisioning transport endpoints, DNS, ports, certificates, and TLS policies.
- Managing capacity, connection limits, and network timeouts.
- Monitoring connections, streams, transport errors, latency, and saturation.
- Establishing alerts and runbooks.
- Managing rollouts, rollbacks, and environment configurations.
- Assisting cross-service incident diagnosis using correlation IDs/trace IDs.

Operations teams do not decide business meanings of payloads. Those decisions belong to service owners and domain owners.

### 4.5. Security / Data Owner

Security or data owner teams define:

- How connections and requester identities are authenticated.
- Which principals may call which routes and access which tenants/resources.
- Which sensitive metadata may be transmitted.
- Rules for encryption, retention, auditing, and redaction.
- Data classification within payloads.
- Data-related compliance requirements.

Service owners implement these controls in responders; consumers protect their credentials and data when sending and receiving.

### 4.6. Summary Responsibility Matrix

| Responsibility | Consumer | Responder Owner | Contract Owner | Platform/Ops | Security/Data |
|---|---|---|---|---|---|
| Send valid payloads | Accountable | Defines schema | Approves contract | Provides tooling | Defines data policy |
| Validate and process business logic | Honors response | Accountable | Approves semantics | Monitors health | Approves access rules |
| Route and transport | Uses published endpoint | Publishes route | Approves contract | Operates endpoint | Approves transport security |
| Retry/idempotency | Follows policy | Implements guarantee | Defines rules | Monitors retries/load | Reviews risks |
| Versioning/deprecation | Upgrades consumer | Supports versions | Coordinates and approves | Supports rollout | Reviews impact |
| Incident response | Supplies correlation ID | Investigates service errors | Coordinates contract issues | Investigates infrastructure | Assists security incidents |

This table is a template assignment. Organizations may combine roles, but must name a single accountable owner or group for each decision.

## 5. RSocket Contract Example

Suppose an API accepts an order placement request. The consumer sends one request and the responder returns a consolidated response.

### 5.1. Contract Specification

~~~yaml
contract:
  id: order-submission
  version: 1.0.0
  owner: order-service-team
  status: active

transport:
  protocol: rsocket
  transport: tcp
  dataMimeType: application/json
  metadataMimeType: message/x.rsocket.composite-metadata
  tls: required

route:
  name: orders.submit
  interaction: request-response
  requester: checkout-service
  responder: order-service
  request: SubmitOrder
  response: OrderAccepted
  timeout: 3s
  idempotency: required

requestFields:
  - name: requestId
    type: string
    required: true
    description: Stable identifier for this logical submission
  - name: customerId
    type: string
    required: true
    description: Customer identifier
  - name: items
    type: array
    required: true
    description: At least one order item

responseFields:
  - name: orderId
    type: string
    required: true
  - name: status
    type: string
    required: true
    allowedValues: [ACCEPTED, REJECTED]
  - name: acceptedAt
    type: string
    format: date-time
    required: false

errors:
  - code: VALIDATION_FAILED
    retryable: false
  - code: BUSINESS_RULE_REJECTED
    retryable: false
  - code: TEMPORARY_UNAVAILABLE
    retryable: true

responsibilities:
  requester:
    - Validate required fields
    - Preserve requestId across retries
    - Handle timeout and query status when outcome is unknown
  responder:
    - Validate payload and authorize customer
    - Enforce idempotency for requestId
    - Return a response that follows this schema
~~~

This is an illustrative YAML format for storing contracts in a repository. It is not a mandatory RSocket standard schema. Organizations may choose JSON Schema, Avro, Protobuf, or an internal format; what matters is that schemas are versioned and automatically verifiable.

### 5.2. Example Payloads

Request:

~~~json
{
  "requestId": "checkout-2026-0042",
  "customerId": "customer-101",
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ]
}
~~~

Response:

~~~json
{
  "orderId": "order-9001",
  "status": "ACCEPTED",
  "acceptedAt": "2026-11-07T10:30:00Z"
}
~~~

This example assumes one request creates one order. If the system allows accepting items independently, the response must include a list of per-item outcomes rather than only one overall status.

### 5.3. DTOs and Responder in Spring

Shared DTOs in this example live in three separate files in package `com.example.orders.contract`.

**File `OrderItem.java`:**

~~~java
package com.example.orders.contract;

public record OrderItem(String sku, int quantity) {}
~~~

**File `SubmitOrder.java`:**

~~~java
package com.example.orders.contract;

import java.util.List;

public record SubmitOrder(
    String requestId,
    String customerId,
    List<OrderItem> items
) {}
~~~

**File `OrderAccepted.java`:**

~~~java
package com.example.orders.contract;

public record OrderAccepted(
    String orderId,
    String status,
    String acceptedAt
) {}
~~~

Responder:

~~~java
package com.example.orders;

import com.example.orders.contract.OrderAccepted;
import com.example.orders.contract.SubmitOrder;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    private final OrderApplicationService service;

    public OrderRSocketController(OrderApplicationService service) {
        this.service = service;
    }

    @MessageMapping("orders.submit")
    public Mono<OrderAccepted> submit(
        @Payload SubmitOrder command
    ) {
        return service.submitIdempotently(command);
    }
}
~~~

`OrderApplicationService` is the application-implemented business service. The contract requires the service to protect `requestId` against duplicate order creation and return `OrderAccepted` only once the accepted state has been durably stored.

### 5.4. Requester in Spring

~~~java
package com.example.checkout;

import com.example.orders.contract.OrderAccepted;
import com.example.orders.contract.SubmitOrder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class OrderClient {

    private final RSocketRequester requester;

    public OrderClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("order-service", 7000);
    }

    public Mono<OrderAccepted> submit(SubmitOrder command) {
        return requester
            .route("orders.submit")
            .data(command)
            .retrieveMono(OrderAccepted.class);
    }
}
~~~

This example assumes `builder` has been configured by Spring Boot and the environment can resolve host `order-service`. Consumers must still handle timeouts, transport errors, and indeterminate outcomes per the contract. In production, configure timeouts, authentication metadata, and lifecycle disposal per application policy.

## 6. Versioning and Compatible Changes

Contracts outlive individual deployments. Service owners need rules so consumers can upgrade in a planned manner.

### 6.1. Typically Compatible Changes

The following changes are generally compatible if serializers and consumers follow the rule of ignoring unknown fields:

- Adding an optional field with a safe default.
- Adding a new route without changing existing routes.
- Adding a new error code if consumers have a fallback for unknown codes.
- Adding optional metadata that the responder does not require from old consumers.

Even so, check your specific serializer. A strict consumer may reject new fields or new enum values. Never assume every consumer ignores unknown data.

### 6.2. Potentially Breaking Changes

The following changes usually require a major version or migration plan:

- Renaming or deleting a route.
- Changing field data types, units, or meaning.
- Making an optional field required.
- Changing semantics from Request-Response to a stream or vice versa.
- Changing ordering, cardinality, or stream termination conditions.
- Changing error codes or turning a retryable error into non-retryable without notice.
- Changing idempotency, authorization, or timeout rules in ways that break existing consumers.

Do not judge compatibility by schema alone. Changing semantics is also a contract change, even when the JSON stays identical.

### 6.3. Deprecation Process

A practical process:

1. Publish the new route or version along with the reason for the change.
2. Update documentation, examples, and contract tests.
3. Notify affected consumers and communicate the migration timeline.
4. Run old and new versions in parallel for the agreed window.
5. Monitor traffic on the old version.
6. Confirm consumers have migrated or have an approved exception plan.
7. Retire support for the old version on the announced date.
8. Update the changelog and set contract status to retired.

Do not delete an old route merely because a new consumer was deployed. Base removal on usage metrics or confirmation from accountable consumers.

### 6.4. Semantic Versioning for Contracts

You can adopt the convention:

- MAJOR: breaking changes.
- MINOR: backward-compatible additions.
- PATCH: documentation, examples, or clarifications without changing semantics.

This is an organizational versioning policy, not an RSocket protocol requirement. Document how it applies clearly in the repository.

## 7. Security and Access Control in Contracts

Contracts must describe security boundaries clearly enough for consumers to integrate properly:

- Whether TLS is mandatory on the transport.
- How connections are authenticated and how credentials are sent.
- Which routes require which permissions.
- How tenants or resources are identified.
- Which metadata may be sent and which metadata is never trusted blindly.
- Redaction rules for logs and traces.
- Credential lifetimes and rotation procedures.

RSocket is a bidirectional protocol. Either side can initiate requests, and the peer can also send requests over the same connection. Therefore, do not assume permissions apply only in one direction. The contract must clarify which principals may invoke which routes in each direction.

Authentication establishes identity; authorization determines which actions that identity may perform. Responders must enforce permissions on the server even if the consumer hid a button or checked permissions in the UI.

Never include real tokens in examples. Use placeholders such as TOKEN_FROM_SECRET_STORE and never log tokens.

## 8. Observability and Operations

A production-ready contract must specify how requests are traced.

### 8.1. Correlation and Tracing

Every request should carry a correlation ID or trace context to link logs across consumers, responders, and downstream services. Specify:

- Which metadata keys or tracing standards are used.
- Which party generates the trace ID.
- How context is propagated across downstream calls.
- How correlation IDs are returned on errors.
- Logging and redaction rules.

Do not use correlation IDs in place of request IDs or idempotency keys. Correlation IDs serve observability; idempotency keys identify logical operations.

### 8.2. Metrics and SLOs

Service owners and platform teams should align on:

- Request rate per route.
- Rates of success, business rejections, and technical errors.
- p50, p95, and p99 latency.
- Open connections and active stream counts.
- Reconnect, resume, and retry counts.
- Timed-out or cancelled request counts.
- Payload sizes and limit-exceeded rates.

SLOs must define the measurement scope, such as the percentage of Request-Response calls completing within deadline, rather than just TCP connection uptime. An open connection does not mean a business route is healthy.

### 8.3. Runbooks

Operational docs should specify:

1. Which dashboards and metrics to inspect.
2. Which log fields or trace IDs to search.
3. Common errors and how to distinguish consumer, responder, transport, and dependency faults.
4. How to inspect which routes are being called and which versions are running.
5. How to mitigate retry storms or reconnect storms.
6. Escalation channels and service-owning teams.
7. Procedures for rolling back or disabling a route during an incident.

## 9. Contract Testing

Documentation is trustworthy only when tests keep the implementation aligned with it.

### 9.1. Schema Tests

Verify:

- Valid payloads deserialize properly.
- Payloads missing required fields are rejected.
- Invalid data types are handled per convention.
- Optional fields receive proper defaults.
- New enums or error codes do not crash consumers unexpectedly.
- Oversized payloads exceeding limits are handled cleanly.

### 9.2. Provider Contract Tests

Responder tests must verify:

- The exact route is registered.
- Valid requests return responses matching the schema.
- Validation and authorization are enforced.
- Error codes and retry semantics match the contract.
- Idempotency works when the same request is sent multiple times.
- Streams emit expected payload types, ordering, and terminal signals.
- Cancellation and timeouts do not lose committed outcomes.

### 9.3. Consumer Contract Tests

Consumer tests must verify:

- Correct routes and payloads are sent.
- Responses are decoded per the schema.
- Unknown fields or unknown codes trigger safe fallbacks.
- Non-retryable errors are not retried.
- Status is queried when outcomes are indeterminate.
- Streams are cancelled and resources released properly.

### 9.4. Integration Tests with RSocketRequester

An integration test can start the server and use a real requester to invoke a route. Example response check:

~~~java
StepVerifier.create(
    requester
        .route("orders.submit")
        .data(command)
        .retrieveMono(OrderAccepted.class)
)
.expectNextMatches(response ->
    response.orderId() != null
        && response.status().equals("ACCEPTED")
)
.verifyComplete();
~~~

This test assumes an RSocket server is running, `command` is valid, and Reactor Test is configured. Tests should verify routes, codecs, metadata, and error paths; calling Java methods directly skips RSocket routing and serialization.

## 10. Per-Route Checklist Template

Before publishing a route, complete the following items:

- [ ] Route name and business purpose.
- [ ] Requester, responder, and contract owner.
- [ ] Interaction model: Request-Response, Request-Stream, Channel, or Fire-and-Forget.
- [ ] Request schema and response schema.
- [ ] Data MIME type, metadata MIME type, and codec.
- [ ] Required/optional metadata and validation rules.
- [ ] Error codes, business rejections, and retryability.
- [ ] Timeouts, ordering, cardinality, and stream termination.
- [ ] Idempotency, operation status, and unknown outcomes for side effects.
- [ ] Security, authorization, and data classification.
- [ ] Payload limits, rate/capacity constraints, and backpressure.
- [ ] Versioning, compatibility, changelog, and deprecation policy.
- [ ] Examples, schema tests, provider tests, and consumer tests.
- [ ] Metrics, tracing, dashboards, runbooks, and support contacts.

## 11. Recommended Repository Structure

Contracts can live alongside the service owning the responder:

~~~text
order-service/
  contracts/
    orders-v1/
      contract.yaml
      schemas/
        submit-order.json
        order-accepted.json
        order-error.json
      examples/
        submit-order.request.json
        order-accepted.response.json
      CHANGELOG.md
      README.md
  src/
    main/
    test/
~~~

Purpose:

- `contract.yaml` describes routes, interactions, metadata, and responsibilities.
- `schemas` contains machine-readable schemas.
- `examples` helps consumers test integrations quickly.
- `CHANGELOG` records changes between versions.
- `README` explains connection details, authentication, testing, and owner contacts.
- Contract tests in `src` ensure the implementation never drifts from documentation.

If multiple services share a central contract repository, clearly define owners, review workflows, and how versions sync with service releases. Never allow multiple unsynchronized copies without a single source of truth.

## 12. Common Documentation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Documenting only DTOs and omitting routes | Consumers do not know where to call. | Document route and interaction model for every message. |
| Not stating who owns the contract | Changes lack approvers or support. | Designate a service owner and contract owner. |
| Omitting metadata | Consumers lack auth, trace, or tenant context. | Document metadata, encoding, and validation. |
| Not describing error semantics | Consumers retry incorrectly or swallow errors. | Publish error codes, retryability, and actions. |
| Providing only success examples | Unable to integrate error paths and edge cases. | Include validation, rejection, timeout, and stream error examples. |
| Not specifying compatibility rules | Minor changes break existing consumers. | Maintain versioning, changelogs, and deprecation policies. |
| Exposing internal implementation in contracts | Consumers depend on volatile internal details. | Publish only boundary behaviors and schemas. |
| Having no contract tests | Docs and code drift apart over time. | Automatically verify schemas, routes, and responses. |
| Using correlation IDs as idempotency keys | Fails to prevent duplicate side effects. | Keep two separate identifiers for their distinct purposes. |
| Lacking runbooks or support contacts | Incidents drag on and miss the right team. | Attach dashboards, owners, and escalation paths. |

## Conclusion

A good message contract is clear enough for consumers to know how to send requests, interpret responses, handle errors, and upgrade safely. It also states what the responder is accountable for, who approves changes, who operates the transport, and who supports incidents.

With Spring RSocket, document routes and interaction models alongside payloads, metadata, MIME types, error semantics, timeouts, cancellation, idempotency, and versioning. Pair contracts with schemas, examples, and automated tests so documentation always reflects real behavior.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, annotated responders, route mapping, and metadata.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): auto-configuration, server transport, and requester builder.
- [RSocket Protocol](https://rsocket.io/about/protocol/): interaction models, setup, metadata, errors, and stream lifecycle.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, backpressure, cancellation, and retries.
- [JSON Schema](https://json-schema.org/): describing and validating JSON payload structures.
