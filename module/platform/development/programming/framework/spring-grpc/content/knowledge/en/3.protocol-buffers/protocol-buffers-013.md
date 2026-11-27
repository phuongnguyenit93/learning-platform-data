# Any, Empty, FieldMask, and Wrappers

## Learning Objectives

After this lesson, you will be able to:

- Choose the right well-known type for dynamically typed payloads, data-less RPCs, partial updates, and scalars needing presence.
- Pack, inspect, and unpack messages using **google.protobuf.Any** in Java.
- Use **google.protobuf.Empty** for requests or responses without fields.
- Design update requests with **google.protobuf.FieldMask**, validate paths, and clearly define update semantics.
- Understand the role of scalar wrapper types and when to use **optional** instead.
- Recognize ProtoJSON representations and compatibility constraints of each type.

## 1. Choosing a Well-Known Type by Purpose

Protocol Buffers provides **well-known types (WKTs)** to represent common structures. In **SPRING_GRPC** services, they help clients and servers share a standard contract instead of inventing many similar custom types.

| Type | Use when | Main meaning |
| --- | --- | --- |
| **google.protobuf.Any** | Must hold a Protobuf message whose concrete type is known only at runtime | Wraps a message with a type identifier. |
| **google.protobuf.Empty** | An RPC needs no request or response data | Standard message with no fields. |
| **google.protobuf.FieldMask** | Must specify which fields are read or updated | List of field paths. |
| **google.protobuf.*Value** | Must wrap a scalar in a message with presence, often for legacy schema compatibility | Wrapper message for a scalar. |

These types are not interchangeable. **Any** wraps a typed message; **Empty** is an empty message; **FieldMask** selects fields by path; wrappers enclose a single scalar value. This lesson focuses on declaration syntax, Java APIs, ProtoJSON, and key design decisions.

## 2. Any: Holding a Message Whose Type Is Determined at Runtime

Declaration:

~~~proto
syntax = "proto3";

package learning.events.v1;

import "google/protobuf/any.proto";

message EventEnvelope {
  string event_id = 1;
  google.protobuf.Any payload = 2;
}
~~~

**Any** has two parts:

- **type_url**: identifier of the packed Protobuf type, usually ending with the message's fully qualified name.
- **value**: byte sequence containing the serialized message.

Example of two event types:

~~~proto
message OrderCreated {
  string order_id = 1;
  string customer_id = 2;
}

message PaymentCaptured {
  string order_id = 1;
  int64 amount_minor_units = 2;
  string currency_code = 3;
}
~~~

An EventEnvelope can hold either OrderCreated or PaymentCaptured. The envelope schema does not need a separate field for every new payload kind.

Any fits event buses, extension points, or APIs that genuinely need an extensible set of messages. If the set of options is known and stable, **oneof** is usually easier to validate and more type-safe than Any.

## 3. Packing and Unpacking Any in Java

The corresponding Java class is **com.google.protobuf.Any**. You can pack a message with **Any.pack()**:

~~~java
import com.example.events.v1.OrderCreated;
import com.google.protobuf.Any;

OrderCreated event = OrderCreated.newBuilder()
    .setOrderId("O-42")
    .setCustomerId("C-17")
    .build();

Any payload = Any.pack(event);
~~~

Then place Any inside the envelope:

~~~java
EventEnvelope envelope = EventEnvelope.newBuilder()
    .setEventId("evt-100")
    .setPayload(payload)
    .build();
~~~

When reading, check the type before unpacking:

~~~java
import com.google.protobuf.InvalidProtocolBufferException;

if (envelope.getPayload().is(OrderCreated.class)) {
    OrderCreated decoded =
        envelope.getPayload().unpack(OrderCreated.class);
    handleOrderCreated(decoded);
} else if (envelope.getPayload().is(PaymentCaptured.class)) {
    PaymentCaptured decoded =
        envelope.getPayload().unpack(PaymentCaptured.class);
    handlePaymentCaptured(decoded);
} else {
    handleUnsupportedEventType(
        envelope.getPayload().getTypeUrl());
}
~~~

**is(Class)** verifies whether the type URL matches the expected class; **unpack(Class)** decodes the payload and can throw **InvalidProtocolBufferException** if the data is invalid. Never call unpack blindly with an arbitrary class.

For production systems, maintain an allowlist of accepted types, handle unsupported types explicitly, and log the verified type URL. Any is not an authorization mechanism: knowing a type URL does not mean the sender is authorized to invoke server behavior for that type.

## 4. Any and ProtoJSON

In ProtoJSON, Any has a special **@type** property identifying the packed message type. For a regular message:

~~~json
{
  "@type": "type.googleapis.com/learning.events.v1.OrderCreated",
  "orderId": "O-42",
  "customerId": "C-17"
}
~~~

When Any contains a well-known type that has a special JSON mapping, its content usually appears under the **value** property. For example, Any containing a Duration looks like:

~~~json
{
  "@type": "type.googleapis.com/google.protobuf.Duration",
  "value": "3.5s"
}
~~~

For JsonFormat to resolve allowed message types inside Any, register descriptors via **TypeRegistry**:

~~~java
import com.google.protobuf.TypeRegistry;
import com.google.protobuf.util.JsonFormat;

TypeRegistry registry = TypeRegistry.newBuilder()
    .add(OrderCreated.getDescriptor())
    .add(PaymentCaptured.getDescriptor())
    .build();

String json = JsonFormat.printer()
    .usingTypeRegistry(registry)
    .print(envelope);
~~~

The parser uses the same registry:

~~~java
EventEnvelope.Builder builder = EventEnvelope.newBuilder();
JsonFormat.parser()
    .usingTypeRegistry(registry)
    .merge(json, builder);
~~~

If a type is missing from the registry, JsonFormat cannot decode the Any payload into its corresponding message. The registry should include only the types the application intends to support, rather than indiscriminately exposing every message in the system.

## 5. Empty: A Message Without Fields

**google.protobuf.Empty** is a standard message with no fields:

~~~proto
syntax = "proto3";

import "google/protobuf/empty.proto";

message HealthStatus {
  bool serving = 1;
}

service HealthService {
  rpc Check(google.protobuf.Empty) returns (HealthStatus);
  rpc ResetCache(google.protobuf.Empty) returns (google.protobuf.Empty);
}
~~~

Empty is still a Protobuf message. It does not mean no request exists or no frame is sent over the connection. A unary RPC still has request/response messages in its signature; the Empty message simply carries no data fields.

In Java:

~~~java
import com.google.protobuf.Empty;

Empty request = Empty.getDefaultInstance();
~~~

The server can return Empty:

~~~java
observer.onNext(Empty.getDefaultInstance());
observer.onCompleted();
~~~

Empty is useful when an operation only needs gRPC metadata or authentication context, such as a global cache-clear command. If the operation needs to return a count of deleted items, an execution timestamp, or detailed status, define a response message with those fields.

ProtoJSON represents Empty as an empty object:

~~~json
{}
~~~

Do not use Empty for every operation that “needs little data”. A request might still need a **request_id**, reason, scope, or idempotency key; in that case, declare a dedicated message.

## 6. FieldMask: Specifying Which Fields Are Updated

**google.protobuf.FieldMask** holds a list of field paths. It commonly appears in partial-update requests to distinguish fields to modify from fields to keep unchanged.

Example:

~~~proto
syntax = "proto3";

import "google/protobuf/field_mask.proto";

message UserProfile {
  string display_name = 1;
  string email = 2;
  repeated string labels = 3;
}

message UpdateUserRequest {
  string user_id = 1;
  UserProfile profile = 2;
  google.protobuf.FieldMask update_mask = 3;
}
~~~

If the client wants to update only the email, the mask contains the path **email**. If it wants to clear the labels list by replacing it with an empty list, the mask must contain **labels** and the server must define replace semantics.

FieldMask does not modify data on its own, does not check permissions automatically, and does not decide whether collections are appended or replaced. It only states **which fields fall within the update scope**; the application must define how the mask is applied.

### Path Names

In schemas and Java representations, FieldMask stores paths using Protobuf field names, typically **lower_snake_case**:

~~~java
import com.google.protobuf.FieldMask;

FieldMask mask = FieldMask.newBuilder()
    .addPaths("display_name")
    .addPaths("email")
    .build();
~~~

In ProtoJSON, FieldMask has a comma-separated string representation and converts field names to **lowerCamelCase**:

~~~json
{
  "updateMask": "displayName,email"
}
~~~

For nested fields, use dots to separate path segments, such as **preferences.email** in the schema; ProtoJSON converts each segment to lowerCamelCase. Do not use array indices or map keys in paths as if FieldMask were an arbitrary query language.

## 7. Applying FieldMask at the Application Layer

The server should validate the mask before mutating the entity. A straightforward approach checks each supported path:

~~~java
void applyUpdate(
        UpdateUserRequest request,
        UserProfile.Builder current) {

    if (!request.hasProfile()) {
        throw invalidArgument("profile is required");
    }

    for (String path : request.getUpdateMask().getPathsList()) {
        switch (path) {
            case "display_name" ->
                current.setDisplayName(
                    request.getProfile().getDisplayName());
            case "email" ->
                current.setEmail(request.getProfile().getEmail());
            case "labels" -> {
                current.clearLabels();
                current.addAllLabels(
                    request.getProfile().getLabelsList());
            }
            default ->
                throw invalidArgument("Unsupported update path: " + path);
        }
    }
}
~~~

In the example, labels is **completely replaced** whenever the labels path is present in the mask. If the path is absent from the mask, the existing list stays intact. This handling also lets clients intentionally replace the list with empty.

Several rules should be defined clearly in the API:

- Does an empty mask mean update nothing, or update all fields?
- Is a missing mask accepted?
- Are unsupported fields rejected or ignored?
- Are repeated/map fields replaced, appended, merged, or cleared?
- Are updates allowed on identifier fields, read-only fields, or sensitive fields?

There is no single automatic update semantics that fits every API. RPC documentation and server logic must agree on this policy.

## 8. FieldMask for Nested Fields and Path Validation

Suppose:

~~~proto
message Preferences {
  bool marketing_enabled = 1;
  string locale = 2;
}

message UserProfile {
  string display_name = 1;
  Preferences preferences = 2;
}
~~~

A path such as **preferences.locale** selects the nested field locale. If the mask contains only **preferences**, the application may define that as replacing the whole Preferences message; if it contains **preferences.locale**, the application updates only locale.

The server must validate paths against the target message's descriptor or an explicit allowlist. Do not merely check for non-empty strings and use arbitrary reflection to update any field, as that could allow modifying internal or disallowed fields.

When a field is renamed in a schema, FieldMask paths are affected too. They are part of the API contract, so evaluate old clients, ProtoJSON, and update logic during schema evolution.

## 9. Scalar Wrappers: Messages Wrapping Single Values

Protobuf provides wrapper types:

- **google.protobuf.StringValue**
- **google.protobuf.BoolValue**
- **google.protobuf.Int32Value**, **Int64Value**
- **google.protobuf.UInt32Value**, **UInt64Value**
- **google.protobuf.FloatValue**, **DoubleValue**
- **google.protobuf.BytesValue**

Legacy schema example:

~~~proto
syntax = "proto3";

import "google/protobuf/wrappers.proto";

message LegacySettings {
  google.protobuf.BoolValue notifications_enabled = 1;
  google.protobuf.Int32Value retry_limit = 2;
  google.protobuf.StringValue nickname = 3;
}
~~~

Because a wrapper is a message field, it has presence:

~~~java
LegacySettings absent = LegacySettings.newBuilder().build();

LegacySettings explicitFalse = LegacySettings.newBuilder()
    .setNotificationsEnabled(
        com.google.protobuf.BoolValue.newBuilder()
            .setValue(false)
            .build())
    .build();

System.out.println(absent.hasNotificationsEnabled());       // false
System.out.println(explicitFalse.hasNotificationsEnabled()); // true
System.out.println(explicitFalse.getNotificationsEnabled().getValue());
// false
~~~

Wrappers enabled older proto3 schemas to distinguish absent scalars from scalars present with default values. In newer schemas, **optional bool**, **optional int32**, or **optional string** is usually simpler for scalar presence:

~~~proto
message ModernSettings {
  optional bool notifications_enabled = 1;
  optional int32 retry_limit = 2;
  optional string nickname = 3;
}
~~~

Do not replace a released wrapper with an optional scalar on the same field number merely because both have presence. A wrapper is encoded as a nested message; an optional scalar uses the scalar's wire type. Changing this can break binary compatibility.

## 10. ProtoJSON for Wrappers and Key Caveats

ProtoJSON represents a wrapper as a **scalar value**, not an object with a value property:

~~~json
{
  "notificationsEnabled": false,
  "retryLimit": 3,
  "nickname": "An"
}
~~~

Some types follow the JSON rules of the underlying scalar: int64/uint64 wrappers are represented as decimal number strings; BytesValue is represented in Base64.

For wrapper fields, JSON **null** is accepted to represent that the field has no value/presence. This differs from setting the wrapper to false or 0:

- **notificationsEnabled** omitted or null: wrapper is not present.
- **notificationsEnabled: false**: wrapper is present with value false.

In newer schemas, optional scalars can also express presence; test the exact behavior of the parser/printer used at the gateway. Do not confuse null with a database delete command unless the update contract explicitly defines it.

Wrappers today are mainly needed for legacy schema compatibility or APIs requiring a specific wrapper message. For new scalar fields in proto3, prefer **optional** when you only need explicit presence.

## 11. Choosing Any, oneof, Struct, or Wrappers?

| Requirement | Usually suitable choice | Reason |
| --- | --- | --- |
| One of a few known payloads, controlled set of options | **oneof** | Generates concrete types and explicit case enums. |
| Extensible payload with Protobuf message resolved at runtime | **Any** | Carries type URL and message bytes. |
| Dynamic JSON-like data with no fixed Protobuf schema | **Struct/Value/ListValue** | Models JSON-style objects/arrays/values. |
| Scalar needing presence in a new schema | **optional scalar** | Cleaner than wrappers. |
| Existing scalar wrapper in a legacy API | **google.protobuf.*Value** | Preserves compatibility with existing message types. |
| RPC needing no data fields | **Empty** | Uses the standard empty message. |
| Partial message update | **FieldMask** | Explicitly specifies field paths to process. |

Any should not be used just to avoid defining a schema. It gives up some compile-time type safety and requires runtime checks on type URLs, allowlists, and unpacking. If payloads are known in advance, oneof is usually easier to govern.

## 12. Testing Well-Known Types

Important cases:

1. Any packs and unpacks valid messages; unsupported types are handled deliberately.
2. Any round-trips through ProtoJSON using a TypeRegistry with the right descriptors.
3. Empty is sent and received as an empty message; never confused with skipping the RPC.
4. FieldMask preserves paths, converts names accurately across ProtoJSON, and rejects unsupported paths.
5. FieldMask selecting empty repeated/map fields applies the defined replace semantics accurately.
6. Wrappers distinguish absent from present-default; JSON null and false/0 are handled differently.
7. Old and new schemas do not swap wrappers with optional scalars on the same field number.

JUnit 5 example testing Any:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.events.v1.OrderCreated;
import com.google.protobuf.Any;
import com.google.protobuf.InvalidProtocolBufferException;
import org.junit.jupiter.api.Test;

class AnyPayloadTest {
    @Test
    void packsAndUnpacksKnownMessage() throws Exception {
        OrderCreated source = OrderCreated.newBuilder()
            .setOrderId("O-42")
            .setCustomerId("C-17")
            .build();

        Any packed = Any.pack(source);

        assertTrue(packed.is(OrderCreated.class));
        assertEquals(source, packed.unpack(OrderCreated.class));
    }
}
~~~

This example focuses on the Any API. In a real application, add tests for type URLs outside the allowlist, corrupted payloads, size limits, and the JSON parser with TypeRegistry.

## 13. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using Any for a fixed set of payloads | Loses compile-time type checks and increases runtime logic | Use oneof when options are known. |
| Unpacking Any without checking type | Parse errors or handling the wrong message type | Check **is()**, verify allowlist, then **unpack()**. |
| Forgetting to register TypeRegistry when parsing Any JSON | JsonFormat cannot resolve the payload type | Register descriptors of supported types. |
| Using Empty for requests needing an ID or reason | Server lacks data to execute the operation properly | Create a concrete request message. |
| Assuming FieldMask updates data automatically | Misses replace/merge/clear logic and authorization checks | Implement explicit semantics on the server. |
| Ignoring unknown paths in FieldMask | Clients may think the field was updated | Reject or handle according to published contract. |
| Using wrappers for all new scalars | Longer schemas and more complex APIs than necessary | Use optional scalars when only presence is needed. |
| Changing a wrapper to optional on the same field number | Can break wire compatibility | Use a new field or a controlled migration. |

## 14. Practice Exercise

A profile service needs to support extensible events, health checks, and partial updates:

1. Create an **EventEnvelope** containing event_id and **Any payload**; pack a **UserCreated** message and verify the type before unpacking.
2. Write a **Ping** RPC taking and returning **Empty**; explain why the call still has request/response messages.
3. Create an **UpdateProfileRequest** containing UserProfile and FieldMask; update display_name only when the display_name path is present in the mask.
4. Clearly define how repeated labels are replaced with an empty list when the mask contains labels.
5. Create one legacy schema using **BoolValue** and one modern schema using **optional bool**; compare the Java API, JSON, and wire format.
6. Use JsonFormat and TypeRegistry to round-trip an EventEnvelope carrying an Any payload.

**Completion criteria:** select the right WKT by semantics, validate Any types, use Empty properly, apply FieldMask under controlled rules, and understand wrapper compatibility limits.

## 15. Key Takeaways

- **Any** holds a type URL and message bytes; verify type, allowlist, and unpack into the right class.
- **Empty** is a message with no fields, not a non-existent RPC.
- **FieldMask** specifies field paths; the server must define validation and update semantics.
- **Wrappers** provide scalar presence in legacy schemas; for new proto3 schemas, optional scalars are usually preferred.
- ProtoJSON has dedicated mappings for Any, Empty, FieldMask, and wrappers; use JsonFormat when contract compliance is required.
- Never swap WKTs merely because they are all messages: choose based on data semantics and compatibility.

Understanding Any, Empty, FieldMask, and wrappers lets you design flexible Protobuf contracts while maintaining type safety, clean partial updates, and compatibility across Spring gRPC client and server versions.
