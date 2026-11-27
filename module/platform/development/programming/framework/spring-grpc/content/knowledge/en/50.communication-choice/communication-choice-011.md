# Documenting Why gRPC Was Chosen and Its Limitations

When building **SPRING_GRPC** services, the decision to use gRPC should stem from the system's communication requirements and be documented alongside accepted limitations. gRPC provides RPC communication over HTTP/2, Protocol Buffers contracts, and client/server code generated from `.proto`. These characteristics fit many service-to-service connections, yet do not automatically make gRPC the best choice for every API.

A useful architectural decision must answer: how does the system need to exchange data, who are the clients, is unary or streaming needed, what are the latency and throughput requirements, does infrastructure support HTTP/2, can operations observe and troubleshoot this protocol, and what limitations are being accepted. This lesson guides how to evaluate and record those answers so the team can revisit them when context changes.

## 1. Start from Communication Requirements

Before selecting a protocol, describe the communication flow in business terms. Do not begin with "Is gRPC faster than REST?" because speed is only one of many factors. Clarify these questions:

- **Who calls whom?** Internal services, mobile apps, browsers, external partners, or resource-constrained devices?
- **What interaction pattern?** One request returning one response, streaming data, or sending asynchronous events?
- **Does the contract need code generation?** Do Java, Go, Kotlin, Python, or other clients need to share schemas and stubs generated from a single source?
- **What are the load characteristics?** Payload size, call frequency, concurrent connections, target latency, message size, and stream lifetime?
- **What are the error requirements?** What level of deadlines, cancellation, retries, structured statuses, and idempotency do clients need?
- **Does infrastructure support it?** Do gateways, proxies, load balancers, service meshes, ingress, firewalls, and monitoring tools support HTTP/2/gRPC as required?
- **Who operates it?** Does the engineering team have experience with Protocol Buffers, schema management, certificates, tracing, and RPC error handling?

Document both functional and operational requirements. For example, "need continuous inventory updates" is insufficient for choosing streaming. You must determine how long streams can stay open, whether resume after disconnection is needed, whether the server can emit on demand or must enforce backpressure, and how many concurrent streams a client may open.

## 2. Valid Reasons to Choose gRPC

gRPC is usually appropriate when one or more of the following characteristics are key requirements:

### Clear API Contracts and Multi-Language Code Generation

Protocol Buffers defines services, RPCs, and message structures in `.proto` files. From that contract, code generators produce message types and client/server stubs for supported languages. Clients and servers share a single schema, reducing manual synchronization of field names, data types, and method signatures.

Example of a simple unary contract:

```proto
syntax = "proto3";

package inventory.v1;

option java_multiple_files = true;
option java_package = "com.example.inventory.v1";

service InventoryService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
}

message GetItemRequest {
  string item_id = 1;
}

message GetItemResponse {
  string item_id = 1;
  int64 available_quantity = 2;
  string version = 3;
}
```

This contract lets Java clients use `GetItemRequest` and `GetItemResponse` types instead of assembling JSON strings or mapping fields manually. However, code generation does not replace schema version management: `.proto` changes must still follow backward and forward compatibility rules.

### Structured Service-to-Service Communication

gRPC defines explicit RPC methods and status codes. In a multi-service system, a unified contract helps govern interfaces, generate stubs, enforce deadlines, carry metadata, and standardize error interpretation. Java services in the Spring ecosystem can use generated stubs to call other services while integrating interceptors and observability at the gRPC layer.

### Need for Two-Way Streaming or Continuous Data Streams

gRPC supports four RPC shapes:

| RPC Shape | Client Sends | Server Returns | Best Fit Examples |
| --- | --- | --- | --- |
| Unary | One message | One message | Product lookup, transaction confirmation |
| Server streaming | One message | Multiple messages | Processing status tracking, receiving continuous updates |
| Client streaming | Multiple messages | One message | Uploading data batches, sending measurement series |
| Bidirectional streaming | Multiple messages | Multiple messages | Interactive two-way connections, session synchronization |

Streaming maintains a single RPC while exchanging multiple messages, avoiding modeling every piece of data as a sequence of independent requests. In return, the application must manage cancellation, deadlines, backpressure, duration limits, reconnects, and stream state.

### Binary Payloads and Serialization Cost Matter

Protocol Buffers often has a compact binary representation and more efficient serialization than JSON for certain data types and workloads. This can reduce payload size or serialize/deserialize CPU overhead. Actual results depend on message structure, call rate, data size, compression, network, and implementation. Measure on a representative workload instead of writing into a decision that gRPC is "always faster than REST".

### Need for HTTP/2 and RPC Capabilities

gRPC uses HTTP/2 for framing, multiplexing, and message transport. A single channel can serve multiple concurrent RPCs over an HTTP/2 connection while supporting gRPC metadata, deadlines, and statuses. These capabilities benefit high-frequency internal communication, provided proxies and network infrastructure are configured properly.

## 3. When gRPC Is Not the Right Choice

Another protocol may fit better if the system's primary needs fall outside gRPC's strengths:

- **Public APIs for browsers:** browsers do not fully support the native gRPC protocol like standard gRPC clients. You may need gRPC-Web, a translating proxy, or an HTTP/JSON gateway. If primary clients are web browsers and the API needs easy accessibility, REST/JSON is usually simpler.
- **Partner integrations without client control:** partners may want curl, ubiquitous SDKs, OpenAPI docs, and direct debugging with HTTP/JSON. REST can lower integration barriers.
- **Need for HTTP/CDN caching or URL-based resource operations:** REST with standard HTTP semantics, cache headers, and resource URLs usually fits cacheable or directly fetchable content better.
- **Asynchronous communication needing durable storage and replay:** message brokers/event streaming fit events requiring temporal decoupling of producers and consumers, retention, replay, or eventual consistency handling. gRPC streaming does not inherently provide durable queues.
- **Infrastructure lacking end-to-end HTTP/2 support:** if proxies, ingress, or firewalls only handle HTTP/1.1 or lack required trailer/streaming support, deploying gRPC can introduce extra translation layers and failure points.
- **Team unable to operate schemas and RPCs yet:** without processes for codegen, `.proto` compatibility management, certificates, deadlines, and observability, adoption cost may outweigh benefits.

You do not have to force one protocol across the entire system. An architecture can use REST for public APIs, gRPC for internal calls needing strong contracts, and a message broker for asynchronous events. What matters is defining clear boundaries and responsibilities for each communication style, avoiding pointless translation layers.

## 4. Comparing the Options

The table below serves to guide discussion. Final outcomes still depend on clients, infrastructure, and specific project requirements.

| Criterion | gRPC | REST/HTTP JSON | Messaging / Event streaming |
| --- | --- | --- | --- |
| Model | Synchronous RPC; supports streaming | HTTP resources and operations; typically request/response | Asynchronous producer/consumer |
| Contract | `.proto`, code generation | OpenAPI/JSON Schema can be used for docs and codegen | Event schemas, registries, or message contracts |
| Payload | Typically binary Protobuf | Typically human-readable JSON | Format-dependent, e.g., Protobuf/JSON/Avro |
| Browser | Requires gRPC-Web or a gateway for many cases | Directly supported | Requires a backend or suitable SDK |
| Streaming | Unary and three streaming RPC shapes | Can use SSE/WebSocket or chunked transfer as needed | Consumers receive messages per broker mechanics |
| HTTP caching | Not as convenient as REST resources | Supports common HTTP cache semantics | Not an HTTP caching model |
| Durability/replay | Not provided natively | Not provided natively | Available depending on broker and retention settings |
| Operational complexity | HTTP/2, schemas, stubs, statuses, streams | HTTP semantics, auth, API versioning | Brokers, partitions, offsets, retries, dead-letter, and schemas |
| Typical fit | Service-to-service communication with contracts and/or streaming | Public APIs, browsers, simple integrations | Events, background processing, producer/consumer decoupling |

Do not compare based solely on serialization benchmarks. A public API may need caching, browser calls, and accessible docs; an event pipeline may need replay; an internal RPC may need tight deadlines and generated data types. Those differences usually matter more than a few microseconds in an isolated benchmark.

## 5. Documenting gRPC Limitations and Risks

Choosing gRPC means accepting the following limitations and having a plan to address them.

### Client and Proxy Compatibility

gRPC requires a transport path supporting HTTP/2 and required protocol features. Some proxies terminate HTTP/2 and forward in their own way; that does not mean every setup supports streaming or trailers. Verify ingress, service meshes, load balancers, firewalls, idle connection timeouts, and message size limits in a realistic environment.

gRPC clients typically maintain long-lived channels. An L4 load balancer distributing TCP connections balances channels rather than individual RPCs; one channel carrying many multiplexed RPCs can skew load across backends. Evaluate gRPC-aware load balancing or suitable client-side policies while monitoring RPC counts per instance.

### Managing Protocol Buffers Compatibility

A `.proto` schema is a shared contract, so field changes must follow compatibility rules:

- Never repurpose a published field number for a different meaning.
- Never reuse deleted field numbers or names; use `reserved` to mark retired slots.
- Add new fields with new field numbers and design appropriate defaults/presence.
- When deleting a field, remove both the field name and number from active schemas and reserve them.
- Never change data types arbitrarily; some changes cause parse errors or alter data meaning even when code still compiles.
- For enums, keep published numeric values stable; consider `UNSPECIFIED = 0` and how old clients handle unknown enum values.
- Check compatibility with linting/breaking-change tools in CI pipelines before releasing.

Example of reserving deleted fields:

```proto
message GetItemResponse {
  reserved 4, 7;
  reserved "legacy_code", "old_description";

  string item_id = 1;
  int64 available_quantity = 2;
  string version = 3;
}
```

Not every change is compatible in both directions. Test both new-client-to-old-server and old-client-to-new-server cases if versions can coexist during rolling deployments.

### Deadlines, Retries, and Business State

Deadlines must be propagated and chosen according to end-to-end budgets. Without client deadlines, calls can live longer than intended. Too-short deadlines increase false failures; too-long deadlines tie up resources when dependencies slow down.

Retries also require explicit policies. A status like `UNAVAILABLE` may be retryable in some cases, yet does not prove the server did not execute the operation. For write operations, use idempotency keys or idempotent designs before enabling automatic retries. Distinguish transport, deadline, authentication, and business errors so clients react appropriately.

### Streaming and Resource Limits

Long-lived streams can hold connections, memory, state, and processing resources. Define limits for concurrent streams, message sizes, message rates, stream durations, deadlines, and client-cancel behavior. For streams supporting reconnect, design sequence numbers or resume tokens if business rules require zero data loss. Never treat a streaming RPC as a durable queue.

### Security and Metadata

gRPC does not automatically enable application security simply by using Protobuf or HTTP/2. Configure TLS; consider mTLS for service-to-service calls when connection-level identity verification is needed; enforce per-method authentication and authorization; bound metadata size and contents. Never put access tokens, personal data, or secrets into logs, trace attributes, or metric labels.

### Observability and Operations

Standard HTTP logs may be insufficient to explain RPC failures. Collect full method names, gRPC statuses, latencies, deadlines, trace context, and necessary streaming signals. Metric labels must have bounded cardinality; never use request IDs, user IDs, or tokens as metric labels. Dashboards should show error rates and latency by method, active RPC counts, and per-instance load distribution.

### Performance Is Not Automatically Better

Binary payloads and multiplexing can help, but bottlenecks may live in databases, business logic, lock contention, network hops, or connection distribution. Benchmarks must measure end-to-end on realistic data and load, including p50/p95/p99 latency, throughput, CPU, memory, payload size, connection count, and operational cost.

## 6. Verifiable Decision Process

A short, evidence-based process avoids choosing protocols on gut feeling:

1. **Describe the use case:** identify producers, consumers, data, frequency, RPC shape, lifetime, and error requirements.
2. **List constraints:** browsers, client languages, public APIs, caching, HTTP/2, gateways, compliance, and operational capability.
3. **Compare at least viable alternatives:** gRPC, REST/JSON, and messaging if the problem can be asynchronous.
4. **Set measurement criteria:** p95/p99 latency, throughput, CPU, memory, payload size, error rate, client development time, and operational cost.
5. **Run a proof of concept:** implement a representative flow across production-like infrastructure; measure failure cases, retries, rolling deployments, and interrupted streams.
6. **Document the decision and trade-offs:** state the chosen option, rationale, rejected options, risks, mitigations, and review triggers.
7. **Review periodically:** revisit when browser clients, new partners, infrastructure changes, higher load, or altered reliability requirements emerge.

You do not need a complex scoring matrix if a few criteria decide the choice. However, critical criteria must be written down explicitly, for example: "clients are all internal Java/Go services, two-way streaming is needed, all ingress supports HTTP/2, and the team already has a Protobuf compatibility pipeline." This evidence can be re-evaluated later.

## 7. Example Architecture Decision Record (ADR)

An ADR is a short document recording context, decision, and consequences. The following example illustrates documenting a decision for an internal Spring gRPC system; numbers and conditions must be replaced with actual project data.

```markdown
# ADR-007: Use gRPC for Internal Inventory Communication

## Status
Accepted

## Context
- Inventory and Order are internal services.
- Clients are primarily Java and Go, deployed on the same platform.
- Some flows need server streaming to push status updates.
- Public APIs for browsers are exposed via a separate API edge.
- Internal ingress supports HTTP/2 and has RPC monitoring dashboards.

## Decision
Use gRPC with Protocol Buffers for synchronous RPCs between Inventory
and Order. Use unary for short queries/updates and server streaming
for update streams with bounded duration.

## Rationale
- .proto contracts serve as a shared schema source for Java/Go clients.
- Generated stubs reduce mapping boilerplate and method-signature drift.
- gRPC supports contract-level deadlines, statuses, and streaming.
- Internal network paths already support HTTP/2.

## Alternatives Considered
- REST/JSON: easy to debug and ubiquitous, but requires a separate
  streaming mechanism for continuous update use cases.
- Messaging: fits async events and replay, but cannot replace
  synchronous queries requiring immediate responses.

## Limitations and Risks
- Browsers cannot call native gRPC directly; public APIs continue using
  REST/JSON at the API edge.
- Must manage schema compatibility and generated code versions.
- Long streams can hold resources; deadlines and duration limits are required.
- Load balancers must distribute RPCs suitably for long-lived HTTP/2 channels.

## Mitigations
- CI checks .proto breaking changes.
- Enforce deadlines, message size limits, and controlled retry policies.
- Use idempotency for retryable write operations.
- Monitor latency, status, active calls, and stream counts per instance.
- Test rolling deployments and reconnects before release.

## Review Triggers
- Browser or external partner clients need direct API access.
- Infrastructure no longer supports HTTP/2 as required.
- Use case shifts to async events needing retention/replay.
- Measurements show operational costs outweigh communication benefits.
```

An ADR must record real project rationale rather than copying an example as a default decision. If the decision scopes gRPC to a specific boundary, state clearly which services are in scope and which interactions continue using other protocols.

## 8. Quantifying Choices in a Proof of Concept

When undecided, pick a representative business flow and implement two options with identical logic, dependencies, and load conditions. Avoid microbenchmarks measuring only serialization because they ignore real-world costs.

| Measurement Group | Suggested Metrics | Question to Answer |
| --- | --- | --- |
| Performance | p50/p95/p99 latency, throughput | Does the protocol meet SLOs at target load? |
| Resources | CPU, heap, allocations, network bytes | What is the cost per request and cost as load scales? |
| Reliability | status/error rates, timeouts, retries, reconnects | How does the system behave when backends slow down or connections drop? |
| Streaming | active streams, message rate, stream duration | Can long streams and resources be kept under control? |
| Development | client creation time, schema changes, debugging | Can the team implement and support it? |
| Operations | dashboards, trace coverage, rollout behavior | Can failures be investigated and versions deployed safely? |

Measure under identical conditions: same data, client count, backend count, network topology, TLS, compression, and resource limits. Run long enough to observe warm-up, connection reuse, and load variance. Store configuration, code versions, and results alongside the ADR so others can reproduce the measurements.

## 9. Checklist Before Finalizing the Choice

- [ ] Use case, clients, and service boundaries are clearly described.
- [ ] Required unary, streaming, or asynchronous communication is identified.
- [ ] REST/JSON and messaging are evaluated where appropriate.
- [ ] Clients, gateways, proxies, load balancers, and firewalls support the required protocol.
- [ ] A plan exists for managing `.proto`, generated code, and breaking-change checks.
- [ ] Policies exist for deadlines, cancellation, retries, and idempotency.
- [ ] Message, stream, and resource limits are defined.
- [ ] TLS/authentication/authorization and metadata protection rules are in place.
- [ ] Metrics, logs, traces, and dashboards are ready for operations.
- [ ] Representative POC results exist, or it is documented why a POC was unnecessary.
- [ ] ADR records rationale, alternatives considered, limitations, mitigations, and review triggers.

Choosing gRPC responsibly means selecting it for the right communication boundary based on requirements and evidence, while explicitly recording accepted costs. In the Spring ecosystem, Protocol Buffers and generated stubs form a strong contract foundation for clients and servers; deadlines, statuses, interceptors, TLS, integration tests, and observability turn that choice into an operable solution. The ADR preserves context and rationale so the team can re-evaluate as the system evolves.
