# Enums and Unknown Values

## Learning Objectives

After this lesson, you will be able to:

- Declare proto3 enums with default value **0** and a name expressing an unspecified state.
- Understand that enums are encoded as integers on the Protobuf wire and distinguish an **unknown enum value** from an **unknown field**.
- Read enums in Java via **getXxx()** and **getXxxValue()**, and handle **UNRECOGNIZED** without losing the original integer.
- Recognize how ProtoJSON represents known enums and unknown numeric values.
- Evolve enums safely when Spring gRPC clients/servers deploy on different versions; never reuse retired numbers or names.

## 1. Enums Represent a Finite Set of Values

In **SPRING_GRPC** contracts, Protobuf messages often need to represent states or choices from a predefined set of values: order statuses, payment types, priority levels, or delivery modes. **Enums** assign names to those numeric values so schemas and Java code are readable.

~~~proto
syntax = "proto3";

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
  ORDER_STATUS_CANCELLED = 3;
}

message Order {
  string order_id = 1;
  OrderStatus status = 2;
}
~~~

Instead of sending the string **PAID** in binary Protobuf, the **status** field is encoded as the number **2**. The name **ORDER_STATUS_PAID** helps readers of the schema and source code understand what that number means.

Enums fit when options form a well-defined set managed across versions. If values are arbitrary free-form user strings, do not force them into an enum.

## 2. Rules for Declaring Enums in proto3

Important rules:

1. **The first value must have number 0.** This is the default value of a proto3 enum field without explicit presence.
2. Name the first element **UNSPECIFIED** or **UNKNOWN**, so the default value is never confused with a confirmed business state.
3. Each value has a **name** and a **32-bit integer**. Numbers must be distinct unless aliasing is explicitly enabled.
4. Enum value names are declared in the enclosing scope (package or message), so use a prefix like **ORDER_STATUS_** to avoid colliding with values from other enums.
5. Never change the meaning of a released number and never reuse the number of a removed value.

Example of an enum inside a message:

~~~proto
message Payment {
  enum Method {
    METHOD_UNSPECIFIED = 0;
    METHOD_CARD = 1;
    METHOD_BANK_TRANSFER = 2;
  }

  Method method = 1;
}
~~~

Enum values still require unique names within the enclosing message scope. The prefix convention keeps schemas clear and prevents collisions when enums are declared at package level.

### Aliases When Two Names Share One Number

By default, proto3 does not allow two enum values to share the same number. If you genuinely need to keep two compatible names during a terminology transition, you can enable:

~~~proto
enum Color {
  option allow_alias = true;

  COLOR_UNSPECIFIED = 0;
  COLOR_GREY = 1;
  COLOR_GRAY = 1;
}
~~~

With aliases, when printing a number to an enum name or ProtoJSON, the **first** declared name for that number is typically used. Aliasing creates no new binary value: **COLOR_GREY** and **COLOR_GRAY** are both number 1. Use it only for clear compatibility reasons; otherwise, a single canonical name is easier to manage.

## 3. Default Values and Presence of Enum Fields

With a regular enum field:

~~~proto
message Order {
  OrderStatus status = 1;
}
~~~

If **status** is unset, the Java getter returns **ORDER_STATUS_UNSPECIFIED** (number 0). Regular scalar enum fields use **implicit presence**, so there is no **hasStatus()** to distinguish omitting it from intentionally setting **ORDER_STATUS_UNSPECIFIED**.

If you need to distinguish those two cases, declare:

~~~proto
message UpdateOrderRequest {
  optional OrderStatus requested_status = 1;
}
~~~

Java generates **hasRequestedStatus()**. Before calling the setter on the builder, presence is false; after calling **setRequestedStatus(ORDER_STATUS_UNSPECIFIED)**, presence is true even though the getter still returns member 0.

~~~java
UpdateOrderRequest absent = UpdateOrderRequest.newBuilder().build();

UpdateOrderRequest explicitDefault =
    UpdateOrderRequest.newBuilder()
        .setRequestedStatus(OrderStatus.ORDER_STATUS_UNSPECIFIED)
        .build();

System.out.println(absent.getRequestedStatus());
// ORDER_STATUS_UNSPECIFIED
System.out.println(absent.hasRequestedStatus()); // false

System.out.println(explicitDefault.getRequestedStatus());
// ORDER_STATUS_UNSPECIFIED
System.out.println(explicitDefault.hasRequestedStatus()); // true
~~~

The default value **UNSPECIFIED** should not be automatically interpreted as an action such as cancelling or paying an order. Business logic must decide how to handle an unprovided or unspecified enum state.

## 4. Enums Are Encoded as Numbers on the Protobuf Wire

Enums use wire type **0 (varint)**, just like varint integer types. Enum names are not written into binary Protobuf.

~~~proto
message Order {
  OrderStatus status = 2;
}
~~~

If **status = ORDER_STATUS_PAID** (number 2), the encoded field looks like:

~~~text
10 02
|  |
|  +-- Enum value: 2
+----- Tag: (field_number 2 << 3) | wire_type 0 = 16
~~~

If a newer client sends enum number **99**, the payload can be:

~~~text
10 63
|  |
|  +-- Enum value: 99 (0x63)
+----- Tag of status field number 2, wire type 0
~~~

To a proto3 parser, the number 99 can still be read into the enum field even if the older version's schema has not declared a name for it. This is an **unknown enum value**: the parser knows field number 2 is an enum, but the current schema version has no name for number 99.

This differs from an **unknown field**. An unknown field occurs when the parser does not recognize the field number in a message. With an unknown enum value, the parser recognizes the field and wire type, yet the numeric value lies outside the enum symbols known to the current code.

## 5. How Does Java Handle Unknown Enum Values?

For proto3 enums, generated Java code includes a special element named **UNRECOGNIZED** to represent enum numbers not declared by the current version.

Two APIs to distinguish:

- **getStatus()** returns the Java enum. If the received number is not in the current enum, it returns **OrderStatus.UNRECOGNIZED**.
- **getStatusValue()** returns the raw integer stored in the message, even when the current schema version has no name for that number.

Example when parsing a payload with status field number 99:

~~~java
Order parsed = Order.parseFrom(new byte[] {
    0x10, 0x63
});

System.out.println(parsed.getStatus());
// UNRECOGNIZED

System.out.println(parsed.getStatusValue());
// 99
~~~

If you need to forward or log the data, **do not replace an unknown value with ORDER_STATUS_UNSPECIFIED**. Doing so loses the number 99 and can change the meaning when the message reaches a newer service.

The Java builder has **setStatusValue(int)** to set an enum number directly:

~~~java
Order forwarded = Order.newBuilder()
    .setOrderId("o-42")
    .setStatusValue(99)
    .build();

System.out.println(forwarded.getStatus());      // UNRECOGNIZED
System.out.println(forwarded.getStatusValue()); // 99
~~~

Do not call **OrderStatus.UNRECOGNIZED.getNumber()** to retrieve the original number. **UNRECOGNIZED** is a Java API sentinel, not a specific enum number; calling **getNumber()** on it throws **IllegalArgumentException**. The original number must be obtained from **getStatusValue()** on the message.

For repeated enums, Java provides APIs to read the corresponding raw numbers such as **getStatusesValueList()** alongside the enum list. When processing unknown values in a list, use the integer API so numbers are not lost.

## 6. Writing Business Logic Safely with UNRECOGNIZED

Do not write a switch that handles only known states and silently maps everything else to a default state.

~~~java
switch (order.getStatus()) {
    case ORDER_STATUS_PENDING ->
        handlePending(order);
    case ORDER_STATUS_PAID ->
        handlePaid(order);
    case ORDER_STATUS_CANCELLED ->
        handleCancelled(order);
    case ORDER_STATUS_UNSPECIFIED ->
        handleUnspecified(order);
    case UNRECOGNIZED ->
        handleUnknownStatus(order.getStatusValue());
}
~~~

**handleUnknownStatus(...)** can record metrics/logs, reject operations that require understanding the status, or forward the raw integer to a system with a newer schema. The decision depends on business rules and trust boundaries; never execute actions like payment or cancellation on an unrecognized number.

An explicit check:

~~~java
int rawStatus = order.getStatusValue();
OrderStatus status = order.getStatus();

if (status == OrderStatus.UNRECOGNIZED) {
    // Keep rawStatus for diagnostics or forwarding.
    recordUnknownStatus(rawStatus);
} else {
    processKnownStatus(status);
}
~~~

When an application accepts enums from external clients, validate both known values and state-transition rules. An enum defines the schema's value domain, but does not guarantee a transition like **PENDING → PAID** is valid at the business layer.

## 7. ProtoJSON: Known Enum Names and Unknown Enum Numbers

ProtoJSON normally represents known enums by **name**:

~~~json
{
  "status": "ORDER_STATUS_PAID"
}
~~~

If a message contains an enum number unknown to the current schema version, ProtoJSON can represent that value as an **integer**:

~~~json
{
  "status": 99
}
~~~

The ProtoJSON parser accepts enum integers, including numbers not declared in the current enum. By contrast, a name string absent from the schema version like **ORDER_STATUS_REFUNDED** is usually unrecognized by an old parser. Therefore, when passing a new enum value through JSON to an old consumer, numeric representation can preserve information better than a name string, though it should only be used if the JSON contract and consumers accept that representation.

In Java, you can use **JsonFormat** from **protobuf-java-util**:

~~~java
import com.google.protobuf.util.JsonFormat;

Order order = Order.newBuilder()
    .setOrderId("o-42")
    .setStatusValue(99)
    .build();

String json = JsonFormat.printer().print(order);
// Field status is represented as the number 99 because the current
// enum version has no corresponding name.

Order.Builder builder = Order.newBuilder();
JsonFormat.parser().merge("{\"status\":99}", builder);

Order parsed = builder.build();
System.out.println(parsed.getStatus());      // UNRECOGNIZED
System.out.println(parsed.getStatusValue()); // 99
~~~

Do not equate ProtoJSON with general-purpose Java JSON serializers. Other libraries may not preserve unknown enum numbers or may reject them. When using REST gateways, logging, or JSON persistence, test with the exact serializer/parser running in production.

## 8. Evolving Enums While Maintaining Compatibility

Suppose version v1 has:

~~~proto
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
}
~~~

Version v2 adds a refunded status:

~~~proto
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
  ORDER_STATUS_REFUNDED = 3;
}
~~~

This is generally a **wire-compatible** change: number 3 is encoded as a varint, and the v1 parser still receives that number. However, v1 code has no **ORDER_STATUS_REFUNDED** symbol; proto3 Java returns **UNRECOGNIZED**, while **getStatusValue()** retains number 3.

| Change | Impact |
| --- | --- |
| Add enum value with a new number | Usually binary-compatible; old consumers must handle unknown numbers. |
| Rename enum value, keep number | Binary still carries the same number; Java constant and ProtoJSON string change. |
| Change the number of a released enum value | Can cause old data to be interpreted as another state. |
| Remove enum value and reuse its number | Historical bytes can be misinterpreted. |
| Remove enum value and reserve number/name | Prevents new schemas from accidentally reusing historical values. |

**Do not change the number of a released enum value just to reorder the list.** Declaration order is not business order; numbers are part of the binary contract.

### Deploying Clients and Servers on Different Versions

When a v2 server emits enum value 3 in a response:

- A v2 client knows **ORDER_STATUS_REFUNDED** and can handle it by name.
- A v1 client reads number 3, though Java returns **UNRECOGNIZED**; code must have an explicit handling branch.
- If the v1 client forwards the binary message without manually reconstructing it, the Protobuf runtime can preserve the unknown enum number.
- If the v1 client converts the enum to a string, DTO, or a model permitting only known values, number 3 may be lost or replaced by a default value.

Consequently, adding an enum value alone is not enough to ensure full system compatibility. Test the behavior of old code, JSON gateways, and message-forwarding intermediaries.

## 9. Removing Enum Values with reserved

If an enum value is retired, reserve both its number and name:

~~~proto
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;

  reserved 3, 5 to 7;
  reserved "ORDER_STATUS_LEGACY";
}
~~~

The example assumes numbers 3, 5–7 and the name **ORDER_STATUS_LEGACY** were previously used. **reserved number** prevents reusing numbers on the wire; **reserved name** prevents reusing symbols in the schema. The two statements must be separate—do not mix numbers and names in the same reserved statement.

**reserved** does not prevent old clients from sending a removed enum number. The new proto3 parser can still receive that number as an unknown enum value. If business logic no longer accepts old values, the server must validate and reject or convert them per migration policy; reserved only protects the schema at compile time.

## 10. Testing Unknown Enum Values

A test suite should verify:

1. An unset enum field returns value 0.
2. An optional enum field distinguishes unset from explicitly setting **UNSPECIFIED**.
3. An enum number undeclared in current Java returns **UNRECOGNIZED**, while **getXxxValue()** retains the integer.
4. Binary Protobuf parse and re-serialize does not drop unknown enum numbers.
5. ProtoJSON accepts unknown numeric values and round-trip preserves the number.
6. Business logic never silently turns unknown values into another valid state.

JUnit 5 example for **OrderStatus** from section 1:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.orders.v1.Order;
import com.example.orders.v1.OrderStatus;
import org.junit.jupiter.api.Test;

class OrderStatusTest {
    @Test
    void preservesUnknownNumericEnumValue() throws Exception {
        Order source = Order.newBuilder()
            .setOrderId("o-42")
            .setStatusValue(99)
            .build();

        Order parsed = Order.parseFrom(source.toByteArray());

        assertEquals(OrderStatus.UNRECOGNIZED, parsed.getStatus());
        assertEquals(99, parsed.getStatusValue());

        Order forwarded = Order.parseFrom(parsed.toByteArray());
        assertEquals(99, forwarded.getStatusValue());
    }
}
~~~

For real compatibility testing, generate a fixture from schema v2 containing **ORDER_STATUS_REFUNDED = 3**, then parse it using v1 Java classes without value 3. Testing with a v1 class and a v2 class sharing the same full Java class name should be organized in separate modules/test fixtures to avoid classpath conflicts.

## 11. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Not declaring enum value 0 first | Invalid proto3 schema | Add **UNSPECIFIED = 0**. |
| Treating 0 as a confirmed state | Absent data is misinterpreted | Name it **UNSPECIFIED** and check presence when needed. |
| Calling only **getStatus()** when unknown values must be preserved | Receives **UNRECOGNIZED** and loses original number if replaced with default | Read **getStatusValue()**. |
| Calling **UNRECOGNIZED.getNumber()** | Java throws **IllegalArgumentException** | Read the number from the message with **getStatusValue()**. |
| Adding an enum value without updating old code | Old clients cannot handle the new state | Handle the unknown branch and test multiple versions. |
| Changing the number of a released enum | Old data gets interpreted as a different state | Keep numbers stable and never reuse them. |
| Reserving only the old enum name | Old number can be assigned a new meaning | Reserve both number and name. |
| Converting unknown enums to **UNSPECIFIED** in a proxy | Loses information needed by newer downstream services | Preserve the raw integer and forward when appropriate. |

## 12. Practice Exercise

A shipping system uses the enum:

~~~proto
enum ShipmentStatus {
  SHIPMENT_STATUS_UNSPECIFIED = 0;
  SHIPMENT_STATUS_CREATED = 1;
  SHIPMENT_STATUS_IN_TRANSIT = 2;
  SHIPMENT_STATUS_DELIVERED = 3;
}

message Shipment {
  string shipment_id = 1;
  ShipmentStatus status = 2;
}
~~~

Tasks:

1. Add a **RETURNED** status with a new number without modifying old numbers.
2. Explain what a previous-version client receives when reading a shipment with the new status.
3. Write Java code checking **getStatus()**, **getStatusValue()**, and handling **UNRECOGNIZED**.
4. Serialize a message with enum number 99, parse it back, and prove 99 is not converted to 0.
5. Represent both a known and an unknown state in ProtoJSON; explain the difference between an enum name string and an integer.
6. Suppose status number 4 is removed in the future; write reserved statements for both number 4 and the old enum name.

**Completion criteria:** understand enums as numbers on the wire, handle values unnamed in the current Java version, and propose safe enum evolution for independently deployed clients/servers.

## 13. Key Takeaways

- Proto3 enums must start at **0**, typically named **UNSPECIFIED**.
- Binary Protobuf encodes enums as varint integers; enum names are not sent on the wire.
- Java returns **UNRECOGNIZED** for unknown enum numbers, while **getXxxValue()** preserves the original integer.
- ProtoJSON uses names for known enums and can use numbers for unknown values.
- Adding a new enum value is usually wire-compatible, yet old code must handle unknown values rather than silently turning them into another state.
- When removing an enum value, reserve both **number** and **name**; never reuse released identities.

Understanding enums and unknown values enables Spring gRPC services to evolve contracts safely when clients, servers, and gateways upgrade at different times, while preserving state information that the current version does not yet recognize.
