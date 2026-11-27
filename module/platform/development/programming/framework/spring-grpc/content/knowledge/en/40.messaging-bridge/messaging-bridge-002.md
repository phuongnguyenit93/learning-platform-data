# Converting RPC Requests into Command Messages

## 1. Mapping Creates a Boundary Between API and Message Flow

In **SPRING_GRPC**, clients send requests according to a Protocol Buffers contract to a Spring service. When an RPC serves as the ingress to a message flow, the server needs to convert the transport request into a **command message** expressing a business intent that consumers can process independently.

Mapping creates a boundary between three models:

- **Protobuf request:** the wire contract structure sent by the client.
- **Application command:** typed data expressing a single business intent.
- **Command message/envelope:** the serialized content sent over the broker, accompanied by metadata for routing, tracing, compatibility, and deduplication.

~~~mermaid
flowchart LR
    A["Protobuf RPC request"] --> B["Validate presence / shape"]
    B --> C["Read trusted caller context"]
    C --> D["Map to application command"]
    D --> E["Wrap in message envelope"]
    E --> F["Serialize with schema"]
    F --> G["Publish to broker"]
    G --> H["Consumer maps to use case"]
~~~

Each step has one responsibility. The mapper does not authenticate credentials, does not make access control decisions, and does not perform business side effects. It receives data already authenticated at the appropriate boundary, normalizes transport fields, and produces a command with a stable structure.

## 2. A Protobuf Request Is Not a Command Message

The two message types may contain similar fields yet serve different purposes:

| Protobuf RPC request | Command message |
|---|---|
| Designed for a client calling an RPC | Designed for a consumer executing an intent |
| Contains fields per the public API | Contains the minimal data required for the use case |
| May contain fields for client compatibility | Has its own schema and version for the message flow |
| Tied to a gRPC method/service | Has a command ID, tenant, correlation, and routing key |
| May contain protobuf-generated default values | Must explicitly express which fields were actually provided |

For example, `SubmitOrderRequest` might carry `customer_id`, a list of lines, and `idempotency_key`. The internal command might add `tenantId`, `actorId`, `commandId`, and `correlationId` taken from the authenticated context. Such information must not be decided by the caller via forged fields.

If you serialize the raw generated request directly onto a topic, consumers become coupled to the package, schema, and lifecycle of the gRPC API. An API change can accidentally break the message flow even though the producer-consumer contract was never redesigned.

## 3. Starting from a Clear RPC Contract

Example API receiving order creation requests:

~~~proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.rpc";

service OrdersIngress {
  rpc SubmitOrder(SubmitOrderRequest) returns (SubmitOrderReply);
}

message SubmitOrderRequest {
  optional string customer_id = 1;
  repeated OrderLine lines = 2;
  string idempotency_key = 3;
  string note = 4;
}

message OrderLine {
  string sku = 1;
  int32 quantity = 2;
}

message SubmitOrderReply {
  string command_id = 1;
  string state = 2;
}
~~~

`customer_id` uses `optional` to distinguish an absent field from a field sent with an empty value. `lines` is a repeated field, so it does not have presence like an optional scalar; an empty list is checked via `getLinesCount()`. `note` is a scalar without presence in this example, so its getter returns the default value when the client omits the field.

Presence decisions must come from API semantics. If `note` needs to distinguish "not provided" from "clear note", use `optional` or `oneof` instead of inferring from an empty string.

## 4. Dedicated Typed Application Commands

A command should reflect business intent and must not depend on generated protobuf classes:

~~~java
import java.util.List;

public record CreateOrderCommand(
        String commandId,
        String tenantId,
        String actorId,
        String customerId,
        List<Line> lines,
        String note,
        String idempotencyKey,
        String correlationId) {

    public CreateOrderCommand {
        lines = List.copyOf(lines);
    }

    public record Line(String sku, int quantity) {}
}
~~~

This command does not contain `SubmitOrderRequest`, `StreamObserver`, `Metadata`, or `ServerCall`. Therefore, consumers can use the command without depending on the gRPC runtime.

A command can be created from multiple adapters: gRPC, REST, a scheduler, or another message consumer. Different adapters can map into the same application command if they express the same business intent.

Do not copy every field from the request into the command out of habit. Keep only fields that the use case needs to execute or audit the intent. Fields meant solely for client display may not need to enter the message.

## 5. Distinguishing Structural Validation from Business Validation

Before mapping, verify that the request has sufficient data to construct a structurally valid command:

- Required fields have presence or are non-empty per the contract.
- The list of lines is non-empty and within size limits.
- Strings are normalized by convention, such as trimming whitespace on identifiers.
- Quantities fall within the allowed domain range.
- The idempotency key has a valid format and length.

Rules such as whether the SKU is currently for sale, whether the customer is permitted to order, whether inventory is sufficient, or whether the order exceeds credit limits do not belong in the mapper. Those are business validations in the use case/consumer and must be re-checked at execution time because state may change after the command is published.

Example:

~~~java
private void validateShape(SubmitOrderRequest request) {
    if (!request.hasCustomerId()
            || request.getCustomerId().isBlank()) {
        throw new InvalidCommandRequest("customer_id is required");
    }
    if (request.getLinesCount() == 0) {
        throw new InvalidCommandRequest("at least one line is required");
    }
    if (request.getLinesCount() > 100) {
        throw new InvalidCommandRequest("too many order lines");
    }
    if (request.getIdempotencyKey().isBlank()) {
        throw new InvalidCommandRequest("idempotency_key is required");
    }
}
~~~

The 100-line limit is only an example. Set limits according to your contract, message size, processing time, and broker/consumer capacity. Do not rely on ingress validation to skip consumer validation: messages can arrive from other producers or be replayed after a long delay.

## 6. Obtaining Tenant and Actor from a Trusted Source

Caller-identifying fields must come from the authenticated principal, typically populated by an authentication interceptor or security integration:

~~~java
public record TrustedCaller(
        String tenantId,
        String actorId,
        String correlationId) {}
~~~

The mapper accepts a dedicated caller context:

~~~java
private CreateOrderCommand toCommand(
        SubmitOrderRequest request,
        TrustedCaller caller,
        String commandId) {

    var lines = request.getLinesList().stream()
            .map(line -> new CreateOrderCommand.Line(
                    line.getSku().trim(),
                    line.getQuantity()))
            .toList();

    return new CreateOrderCommand(
            commandId,
            caller.tenantId(),
            caller.actorId(),
            request.getCustomerId().trim(),
            lines,
            request.getNote(),
            request.getIdempotencyKey(),
            caller.correlationId());
}
~~~

Do not use client-supplied `tenant_id` or `actor_id` as the verified identity. If the API needs the caller to specify an object within a tenant, the use case must verify that the object belongs to the principal's tenant and that the caller has permission to operate on it.

Correlation ID can be read from metadata after format validation, or generated at the ingress if absent. Do not dump all gRPC metadata into the command; only propagate allowlisted values that carry meaning across the message flow.

## 7. Message Envelope Separating Metadata from Payload

A command message should have a consistent envelope so consumers know the message type, origin, and how to handle it:

~~~java
import java.time.Instant;

public record CommandEnvelope<T>(
        String messageId,
        String messageType,
        int schemaVersion,
        String aggregateKey,
        String tenantId,
        String actorId,
        String correlationId,
        String causationId,
        Instant createdAt,
        T payload) {}
~~~

Meaning of fields:

| Field | Role |
|---|---|
| `messageId` | Unique identifier of the message |
| `messageType` | Stable name of the command type, e.g., `orders.create` |
| `schemaVersion` | Schema version of the payload |
| `aggregateKey` | Aggregate-based partitioning/routing key if supported by the broker |
| `tenantId`, `actorId` | Verified tenant and actor context |
| `correlationId` | Links steps of the same request/workflow |
| `causationId` | Message or action that caused the current command |
| `createdAt` | Timestamp when the ingress created the envelope |
| `payload` | Command data with its own schema |

Do not put access tokens, refresh tokens, passwords, or raw transport metadata into the envelope. The message broker is a separate security boundary; topic ACLs, encryption, retention, and consumer permissions must be configured according to payload sensitivity.

## 8. Building the Envelope and Publishing the Message

After the mapper creates the command, the ingress wraps it in an envelope and publishes with an appropriate key:

~~~java
CreateOrderCommand command =
        mapper.toCommand(request, caller, commandId);

CommandEnvelope<CreateOrderCommand> envelope =
        new CommandEnvelope<>(
                command.commandId(),
                "orders.create",
                1,
                command.customerId(),
                command.tenantId(),
                command.actorId(),
                command.correlationId(),
                rpcRequestId,
                clock.instant(),
                command);

kafkaTemplate.send(
        "orders.commands",
        command.customerId(),
        envelope);
~~~

Using customer ID as the key is only appropriate if ordering must be preserved per customer. If mutations must be serialized per order, use `orderId` or the corresponding aggregate key. For an order creation command that does not yet have an `orderId`, you can use the command ID or a stable business key designed for ordering purposes.

Do not pick a key just because the field happens to be available. The key determines partition distribution and ordering guarantees; choosing poorly can concentrate load onto a single partition or cause related commands to run concurrently.

## 9. Idempotency Keys and Command IDs Must Be Stable

Clients may retry the same RPC when a response is lost. The ingress may have already published the message without receiving the acknowledgement. If a retry generates a new `commandId`, the same intent could be processed multiple times.

Mapping rules:

1. The client generates an idempotency key for a business intent.
2. Retries of the same intent resend that same key.
3. The ingress scopes the key by the authenticated tenant/principal.
4. The store has a unique constraint on `(tenantId, idempotencyKey)`.
5. The first request creates the command ID and stores a payload fingerprint; subsequent requests return the existing command ID if the payload is equivalent.
6. The same key with a different payload must return a conflict per the API contract.

Do not simply hash the idempotency key into a command ID and skip storing state. The system still needs to handle races between two concurrent requests with the same key, durably store the mapping result, and track publish status.

Consumers also need to deduplicate by command ID or business key before side effects. Ingress idempotency protects command creation; consumer idempotency protects against duplicate message execution.

## 10. Schema Evolution for Command Messages

Messages can outlive a single deployed version of a producer or consumer. Therefore, command schemas must be managed independently of the gRPC API:

- Add new fields in a backward-compatible way; define defaults when older consumers do not recognize the field.
- Do not reuse deleted field numbers if the payload uses Protobuf.
- Preserve existing field semantics; do not change `customerId` from customer to account just because the field name still seems convenient.
- Use stable `messageType` and `schemaVersion` values.
- Consumers must have a strategy for unsupported versions: controlled rejection, quarantine, or dead-lettering.
- Deploy consumers that understand the new schema before producers begin emitting new required fields.

If the payload uses Protobuf, the generated command message should be a separate message such as `CreateOrderCommandMessage`, not `SubmitOrderRequest`. If the payload uses JSON/Avro, use a schema registry or an equivalent review/versioning process.

Do not assume a mapper automatically preserves unknown fields. When mapping a generated request to an application record, unmapped fields are dropped from the command. That is usually desirable because the command contains only data accepted by the use case; if forward-compatible pass-through is needed, design it explicitly and control which fields are allowed through.

## 11. Enums, Optional, Oneof, and Special Data Types

Mapping must account for protobuf characteristics rather than just calling getters:

| Protobuf | Mapping risk | How to handle |
|---|---|---|
| Scalar without presence | Getter returns default when field is absent | Use `optional`/`oneof` if distinction is needed |
| `repeated` | Empty list may or may not be valid | Validate according to contract |
| Enum | Newer clients may send values older servers do not recognize | Handle `UNRECOGNIZED` explicitly |
| `oneof` | Only one branch is selected | Check `getChoiceCase()` before mapping |
| `google.protobuf.Timestamp` | May contain out-of-range values | Convert to `Instant` via a validating helper |
| `int32`/`int64` | May not match domain type range | Check range before casting |

Enum example:

~~~java
PaymentMethod method = switch (request.getPaymentMethod()) {
    case CARD -> PaymentMethod.CARD;
    case BANK_TRANSFER -> PaymentMethod.BANK_TRANSFER;
    case PAYMENT_METHOD_UNSPECIFIED ->
            throw new InvalidCommandRequest("payment method is required");
    case UNRECOGNIZED ->
            throw new InvalidCommandRequest("unsupported payment method");
};
~~~

Do not store enum ordinals in messages or databases. Enum ordering can change; use stable contract names/values and explicit mapping.

## 12. Consumers Only Receive the Command Contract

Consumers should not depend on gRPC requests or transport context:

~~~java
@KafkaListener(topics = "orders.commands")
public void handle(CommandEnvelope<CreateOrderCommand> envelope) {
    deduplication.executeOnce(
            envelope.messageId(),
            () -> createOrderUseCase.execute(envelope.payload()));
}
~~~

This is a skeleton; a real consumer must handle deserialization, retries, acknowledgement/offset commits, dead-lettering, and transactions. `executeOnce` needs to persist the deduplication marker and side effects in a transaction or suitable idempotency mechanism; checking an in-memory marker alone is unsafe across restarts.

Consumers should verify message type/version, tenant, and schema before invoking the use case. Do not treat an envelope as trustworthy solely because the message came from the broker; broker ACLs and producer permissions must be controlled, and the consumer must still enforce required business authorization.

## 13. Mapping and Publishing May Require a Transactional Outbox

If the ingress must persist a command receipt or idempotency mapping in the database while also publishing a message, doing two separate operations creates a dual-write hazard:

~~~text
DB commit succeeds
    |
    +--> process crashes
             |
             v
       message not yet published
~~~

A transactional outbox writes the command receipt, idempotency mapping, and outbox record in the same database transaction. A relay publishes the outbox record afterward. Once the broker confirms, the relay marks the record as sent. The relay may re-publish after a crash, so consumers must still deduplicate.

With an outbox, the API can define `ACCEPTED` at the time the transaction commits because the command is durably recorded for dispatch. If the contract promises that the broker has received the message, return the response only after relay/broker acknowledgement. These two milestones differ and must be described clearly in the API.

## 14. Testing Request-to-Command Mapping

Mappers should have unit tests independent of the broker. Integration tests verify the full path:

| Scenario | What to verify |
|---|---|
| Valid request | Command has exact fields and normalized values |
| Absent optional scalar | Mapping rejects or applies default per contract |
| Empty/oversized repeated field | Validation handles it properly |
| Enum `UNRECOGNIZED` | Not silently mapped to another valid value |
| `oneof` with no branch set | Returns appropriate validation error |
| Different tenants/principals | Command takes identity from trusted context |
| Metadata missing correlation ID | Generates ID by convention and preserves it across flow |
| Same idempotency key, same payload | Stable command ID, no duplicate operation created |
| Same key, different payload | Returns conflict per contract |
| New schema version | Older consumer handles per compatibility policy |
| Publish failure after DB commit | Outbox relay continues dispatching |
| Consumer receives duplicate message | Side effects do not repeat |

Mapper tests do not need a running broker. Producer/consumer tests need a real or containerized broker to verify serializers, partition keys, acknowledgements, and redelivery. Mocking `KafkaTemplate` only proves the publish call was made, not that the message can be read by a consumer.

## 15. Metrics and Diagnostics

Track each stage separately:

- Rejected validation requests and their reasons.
- Mapping and envelope creation latency.
- Idempotency hits, conflicts, and race conditions.
- Command counts by `messageType`/`schemaVersion`.
- Publish successes/failures, acknowledgement latency, and pending sends.
- Partition distribution, consumer lag, and processing latency.
- Unsupported schema counts, deserialization failures, and dead-letters.
- Correlation ID end-to-end across RPC → command → consumer.

Do not use `commandId`, `customerId`, or correlation ID as high-cardinality metric labels. Use logs/traces to trace individual operations; metric labels should be bounded values such as service, method, message type, version, or status.

## 16. Common Mapping Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Publishing raw protobuf RPC request | Consumer couples to transport contract | Map to a dedicated command schema |
| Trusting client-sent tenant/actor | Risk of identity spoofing | Extract from authenticated principal |
| Not checking scalar presence | Absent field interpreted as valid default | Use `optional`/`oneof` and check presence |
| Putting business validation in mapper | Duplicated rules and not re-checked at consumer | Keep mapper at structural validation; use case validates business rules |
| Generating new command ID on every retry | One intent creates multiple commands | Durable idempotency mapping |
| Using request ID as aggregate key | Ordering does not follow business aggregate | Choose key by entity requiring ordering |
| Changing message schema alongside API without versioning | Older consumers fail to read new messages | Manage schema/versioning independently |
| Putting all metadata into envelope | Leaks tokens and unnecessary transport data | Allowlist propagated fields |
| Testing mapper only with mock producer | Misses serializer, ack, and redelivery issues | Add broker integration tests |

**Key takeaway:** Converting an RPC request into a command message is an intentional mapping step between the protobuf contract, application command, and broker envelope. Validate presence/shape at the ingress, derive tenant/actor from trusted identity, keep command schemas independent of requests, use stable message IDs and idempotency keys, choose aggregate keys according to ordering needs, and version schemas independently. Consumers receive commands, verify them, and execute idempotently; a transactional outbox protects recording alongside publishing when both operations must remain consistent.
