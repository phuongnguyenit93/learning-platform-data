# Field Numbers and Wire Compatibility

## Learning Objectives

After this lesson, you will be able to:

- Explain why the **field number** is a data field's identity in Protocol Buffers encoding, and how the **wire type** participates in forming a tag.
- Read basic byte-level examples to distinguish field number, encoding type, length, and value.
- Evaluate compatibility between gRPC client/server versions when adding, removing, renaming, changing types, or regrouping fields.
- Use **reserved** and multi-version deployment strategies to prevent misinterpreting legacy data.
- Design tests for proto3 contracts in the Spring gRPC ecosystem, covering binary data and JSON conversion cases.

## 1. Why Do Field Numbers Matter in Spring gRPC?

In **SPRING_GRPC**, a **.proto** file is the shared contract between client and server. The **protoc** tool generates Java message classes; the gRPC plugin generates stubs and base classes for unary or streaming RPCs. The Spring application calls methods on the generated Java classes, while gRPC transmits data encoded with Protocol Buffers.

Consider a message:

~~~proto
syntax = "proto3";

message Order {
  string order_id = 1;
  int64 total_cents = 2;
  string note = 3;
}
~~~

Each field has three parts: a **type** (e.g., **string**), a **name** (e.g., **order_id**), and a **number** (e.g., **1**). The name helps with reading the schema and generates Java methods like **getOrderId()**; the number is what identifies the field on the binary wire. Therefore, changing a name and changing a number do not have the same consequences.

In practice, you cannot assume every application is running the same contract version: mobile apps may update slowly, multiple Spring Boot instances may roll out sequentially, and Protobuf data may be persisted to be read later. **Wire compatibility** is the ability of one side to correctly read bytes encoded by a different schema version, within the bounds of Protobuf's encoding rules.

Compatibility at the byte level is an important condition, yet **not sufficient**: a message can still decode successfully while business logic misinterprets it—for instance, changing a currency unit from **cents** to **dollars** while keeping the same field.

## 2. Tags Are Formed from Field Number and Wire Type

In Protobuf's binary format, each field is encoded with a **tag** and its corresponding data payload. A tag is a varint integer computed by the formula:

~~~text
tag = (field_number << 3) | wire_type

field_number = tag >> 3
wire_type    = tag & 0b111
~~~

The lower three bits of the tag identify the **wire type**; the remaining bits identify the **field number**. The wire type describes how to read the bytes that follow, not the full logical type in the .proto file.

| Wire type | Number | Common data | How it is read |
| --- | ---: | --- | --- |
| **VARINT** | **0** | **int32**, **int64**, **uint32**, **uint64**, **sint32**, **sint64**, **bool**, enum | Variable-length integer |
| **I64** | **1** | **fixed64**, **sfixed64**, **double** | Exactly 8 bytes |
| **LEN** | **2** | **string**, **bytes**, nested messages, packed **repeated** scalar elements | Read varint length, then read that many bytes |
| **I32** | **5** | **fixed32**, **sfixed32**, **float** | Exactly 4 bytes |

Wire types **3** and **4** are start/end group from the legacy group mechanism; do not use groups when designing new proto3 schemas. The wire type does not reflect whether a field is declared **optional**, what its name is, or what its business semantics are.

Example:

~~~proto
message Example {
  int32 count = 1;
  string label = 2;
}
~~~

When **count = 7** and **label = "A"**, one binary encoding is:

~~~text
08 07 12 01 41
|  |  |  |  |
|  |  |  |  +-- ASCII character "A" (0x41)
|  |  |  +----- String length: 1 byte
|  |  +-------- Tag 0x12 = 18 = (2 << 3) | 2
|  +----------- count value: 7
+-------------- Tag 0x08 = 8 = (1 << 3) | 0
~~~

If **label** moves from field number **2** to number **16**, the string's tag becomes **0x82 0x01** instead of **0x12**:

~~~text
// label = "A" at field number 2
12 01 41

// label = "A" at field number 16
82 01 01 41
~~~

Two fields can have the exact same name and the exact same **string** type, yet the reader still sees them as **two different fields** because their numbers differ. Having the same value format does not make them compatible.

### What Is a Varint?

Varint encodes an integer in 7-bit payload groups; the high bit of each byte indicates whether another byte follows. Smaller numbers generally take fewer bytes. This is how both tags and integer values of wire type 0 fields are encoded.

The size of a **tag** depends on the field number:

| Field number | Typical tag size |
| --- | --- |
| **1–15** | 1 byte |
| **16–2047** | 2 bytes |
| **2048** and above | 3 bytes or more |

Therefore, reserve numbers **1–15** for frequently occurring fields, especially in messages sent repeatedly over streaming RPCs. However, this is an optimization on the **tag**, not a guarantee that the entire field takes only one byte. Its value and length still occupy additional bytes; optimize only when necessary and backed by measurements.

## 3. Field Number Assignment Rules

When assigning field numbers in proto3, follow these rules:

1. **Valid numbers:** from **1** to **536,870,911** (i.e., **2²⁹ − 1**), excluding the range **19,000–19,999** reserved by Protobuf. **0**, negative numbers, and out-of-range numbers are invalid.
2. **Unique within the same message:** you cannot define two fields with the same number in a single message, even if they belong to different **oneof** blocks. Other messages have their own number space.
3. **Stable for the lifetime of the contract:** once any client, server, or stored data uses a field, keep that number for the same meaning.
4. **Never reuse retired numbers:** mark old numbers with **reserved**. You can also reserve old names so the compiler throws an error if someone later creates a field with the same name.
5. **Do not rely on declaration order:** field number **10** can be written before field number **2** in the .proto file; the number, not the line position, determines wire identity.

Invalid example:

~~~proto
message InvalidOrder {
  string id = 1;
  int64 amount = 1;    // Error: duplicate field number
  string memo = 19000; // Error: number in reserved range
}
~~~

Valid example leaving gaps for future use:

~~~proto
message Order {
  string id = 1;
  int64 amount_cents = 2;
  string note = 10;
  reserved 3, 4, 6 to 9;
  reserved "old_note";
}
~~~

This assumes the numbers and names in **reserved** in this example were previously used. For a brand-new contract, there is no need to place **reserved** arbitrarily when there is no data history or specific need to block reuse.

## 4. Two Versions of an Order Contract

Suppose an order service has a unary RPC **GetOrder**. Version **v1** is already in use by many clients:

~~~proto
// order.proto — version v1
syntax = "proto3";

package learning.orders.v1;
option java_package = "com.example.orders.v1";
option java_multiple_files = true;

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
}

message Order {
  string order_id = 1;
  int64 total_cents = 2;
  OrderStatus status = 3;
  string legacy_coupon = 4;
}

message GetOrderRequest {
  string order_id = 1;
}

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (Order);
}
~~~

Later, the system retires the legacy coupon code and adds an updatable customer note. Version **v2** preserves existing fields and adds the new field:

~~~proto
// order.proto — version v2; compiled separately from v1
syntax = "proto3";

package learning.orders.v1;
option java_package = "com.example.orders.v1";
option java_multiple_files = true;

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
}

message Order {
  string order_id = 1;
  int64 total_cents = 2;
  OrderStatus status = 3;

  reserved 4;
  reserved "legacy_coupon";

  optional string customer_note = 5;
}

message GetOrderRequest {
  string order_id = 1;
}

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (Order);
}
~~~

The two versions illustrate changes to **the same contract** over time, so you must not compile two files with the same Protobuf identifiers and package simultaneously in a single code-generation run. In a real system, each client/server binary version is compiled with its corresponding version of the schema.

Key changes:

- **order_id = 1**, **total_cents = 2**, and **status = 3** keep their numbers, types, and meanings.
- **legacy_coupon = 4** is no longer written in v2; both number **4** and name **legacy_coupon** are **reserved** to prevent developers from reusing them.
- **customer_note = 5** is a new field, using **optional** to distinguish omitting the note from intentionally sending an empty note.

Note: **reserved** only forbids redeclaring the field in the new schema. It does **not** prevent older client versions from continuing to send field 4 on the wire.

## 5. Backward Compatibility and Forward Compatibility

The two checking directions are commonly used as follows:

- **Backward compatibility:** a **newer** reader still correctly reads data created by an **older** version.
- **Forward compatibility:** an **older** reader still reasonably handles data created by a **newer** version.

Some references use the terms from different perspectives; when discussing within a team, specify **who writes and who reads** rather than relying solely on terminology.

For the Order example:

| Sender | Receiver | Behavior at the binary Protobuf level |
| --- | --- | --- |
| v1 | v1 | Fields 1–4 are read according to schema v1. |
| v1 | v2 | v2 reads 1–3; field 4 becomes an **unknown field** since it was removed from schema v2. |
| v2 | v1 | v1 reads 1–3; field 5 is an **unknown field** because v1 does not yet know **customer_note**. |
| v2 | v2 | v2 reads 1–3 and can detect the presence of **customer_note = 5**. |

An **unknown field** does not mean binary data is necessarily lost immediately upon parsing. In the standard Protobuf Java runtime, unknown fields can be retained in the message object and written back out when serialized to binary. However, v1 application code **cannot access field 5 via generated getters**, and if the data passes through JSON conversion, DTO mapping, or manual message reconstruction, unknown fields may be stripped.

Therefore, adding a new field is usually **wire-structurally compatible**, but **does not guarantee** that old clients can see or properly process the new information.

### New Fields Are Not Automatically Required

If a v2 server starts requiring every client to send **customer_note**, v1 clients will be unable to comply and may receive business errors even though request parsing succeeds. Proto3 does not support the **required** label; required-field rules must be managed at the business layer with a client upgrade plan.

In Spring gRPC, data validation failures can return the **INVALID_ARGUMENT** status. That RPC status describes the processing outcome, whereas **wire compatibility** describes the ability to decode requests/responses; the two concerns must be tested separately.

## 6. Which Changes Are Safe, Which Are Risky?

| Schema change | Assessment | Explanation |
| --- | --- | --- |
| Adding a new field with an **unused number** | Usually wire-safe | Old readers ignore unknown fields; new readers must accept the field being absent. |
| Removing a field and adding **reserved** for number/name | Can be wire-compatible | New versions will not misinterpret old data under a new meaning; still check whether business logic depends on the removed field. |
| Changing a **field name**, keeping number and type | Usually preserves binary compatibility | Can break Java source code, names in Protobuf JSON, and systems using reflection/schemas. |
| Changing a **field number** | **Unsafe** | Old and new peers identify it as two different fields. |
| Reusing a deleted number | **Unsafe** | Old data bytes may be interpreted under the new meaning. |
| Changing **int32** to **int64** | Same wire type, but requires value limits | Both use varint, yet old readers may receive values outside **int32** range and truncate/overflow. |
| Changing **int32** to **sint32** | **Value-unsafe** | Despite sharing wire type 0, **sint32** uses ZigZag encoding so the same bytes represent different numbers. |
| Changing **string** to **bytes** | Must not be assumed safe by default | Both use wire type 2, but UTF-8 validation and binary data semantics differ; can break parsers/logic. |
| Changing **float** to **fixed32** | **Semantically unsafe** | Both use wire type 5 but represent values completely differently. |
| Adding an **enum** value | Usually wire-compatible, carries business risk | Old clients may not know the new numeric value; must handle unrecognized values. |
| Moving multiple existing fields into a **oneof** | Risky | Old messages could hold those fields simultaneously; oneof keeps only one choice. |
| Changing **repeated** to singular or vice versa | Requires case-by-case review; usually avoid | Changes value multiplicity and merge behavior, even when some cases share a wire type. |
| Changing a field's unit or meaning | **Business-unsafe** | Encoding still decodes, but data is misinterpreted. |

Avoid concluding that **two types with the same wire type** are naturally interchangeable. For instance, UTF-8 character strings, arbitrary byte sequences, nested messages, and packed number lists all use wire type **2**, yet their contents are decoded under very different rules.

### Open Enums in proto3

Example v3 addition:

~~~proto
enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
  ORDER_STATUS_REFUNDED = 3;
}
~~~

An older proto3 Java runtime preserves the number **3** via **getStatusValue()**, while **getStatus()** returns **UNRECOGNIZED** if the old Java enum has not declared that member. Business code must handle unrecognized cases instead of assuming only **PENDING** and **PAID** exist.

Do not reuse retired enum numbers; you can use **reserved** inside enum definitions. Enum value **0** should mean **UNSPECIFIED/UNKNOWN**, since that is the default value of a proto3 enum field without explicit presence.

## 7. Field Presence Also Affects Compatibility Behavior

In proto3, regular scalar fields have **implicit presence**: from the getter's viewpoint, you cannot distinguish an unsent field from a field set to its default value. For example, **string note = 3;** returns **""** in both cases.

With:

~~~proto
optional string customer_note = 5;
~~~

Generated Java has **hasCustomerNote()** to check presence. The following two messages differ in presence information:

~~~java
Order withoutNote = Order.newBuilder()
    .setOrderId("o-42")
    .build();

Order withEmptyNote = Order.newBuilder()
    .setOrderId("o-42")
    .setCustomerNote("")
    .build();

System.out.println(withoutNote.hasCustomerNote());   // false
System.out.println(withEmptyNote.hasCustomerNote()); // true
System.out.println(withEmptyNote.getCustomerNote()); // ""
~~~

In the binary encoding, an **optional** string field number **5** set to an empty string can still appear with tag **0x2A** (field 5, wire type 2) and length **0x00**:

~~~text
2A 00
|  |
|  +-- String data length: 0
+----- Tag: (5 << 3) | 2 = 42 = 0x2A
~~~

If the field is not set, those two bytes do not appear. **Do not treat a default value as proof that the field was sent.** For partial updates, use explicit presence or **google.protobuf.FieldMask**, along with clear rules distinguishing "do not update" from "clear value".

Switching a scalar between implicit and explicit presence may not change the wire type, yet it still changes merge/serialization behavior and application update logic. Therefore, always test default-value cases.

## 8. repeated Fields and Packed Encoding

Proto3 defaults to **packed** for **packable repeated scalar types** such as **int32**, **bool**, **enum**, and **float**. Given the field:

~~~proto
message Basket {
  repeated int32 quantities = 3;
}
~~~

Suppose the list is **[1, 2]**:

~~~text
Unpacked:
18 01 18 02
|     |
+-----+-- Same tag 0x18 = (3 << 3) | 0 for each value

Packed (default in proto3):
1A 02 01 02
|  |  |  |
|  |  +--+-- Two varint values 1 and 2
|  +-------- Payload length: 2
+----------- Tag 0x1A = (3 << 3) | 2
~~~

Compliant Protobuf parsers accept both **packed** and **unpacked** representations for repeated fields of packable types. You can instruct the code generator to write unpacked format using **[packed = false]**:

~~~proto
repeated int32 quantities = 3 [packed = false];
~~~

This flexibility does **not** mean you can arbitrarily change **repeated** to **singular**: singular represents only one value; multi-element information will no longer be interpreted as originally intended. **string**, **bytes**, message, and map are not packable scalars.

## 9. Removing Fields with reserved and Managing History

Suppose an older version used:

~~~proto
string legacy_coupon = 4;
~~~

You can go through a transition phase where the field still exists but should no longer be used:

~~~proto
string legacy_coupon = 4 [deprecated = true];
~~~

Depending on the code generator, the **deprecated** annotation warns API users; it does **not** remove the field from the wire format. After removing dependent logic, the new version moves to:

~~~proto
reserved 4;
reserved "legacy_coupon";
~~~

The two lines mean different things:

- **reserved 4;** protects the binary identity **4**, preventing someone else from declaring a new field that reuses that number.
- **reserved "legacy_coupon";** prevents redeclaring the same name in the schema. Field names are not encoded onto the binary wire; reserving the name helps prevent confusion during development.

If multiple fields are removed, the syntax can combine numbers/ranges:

~~~proto
reserved 4, 7, 10 to 12;
reserved "legacy_coupon", "old_reference";
~~~

Only use numbers/names corresponding to the actual history of the message. **reserved** belongs to each individual message and does not automatically apply to other messages.

For long-lived persisted data, maintain enough schema history to know what each number once meant. Years later, a field that no longer appears in current source code may still exist in stored bytes, backups, or un-upgraded clients.

## 10. Generated Java Code and Unknown Field Preservation

From schema v2, **protoc** generates the **Order** class in package **com.example.orders.v1**. Example application code:

~~~java
import com.example.orders.v1.Order;
import com.example.orders.v1.OrderStatus;

Order source = Order.newBuilder()
    .setOrderId("o-42")
    .setTotalCents(12500L)
    .setStatus(OrderStatus.ORDER_STATUS_PAID)
    .setCustomerNote("")
    .build();

byte[] bytes = source.toByteArray();
Order decoded = Order.parseFrom(bytes);

System.out.println(decoded.getOrderId());        // o-42
System.out.println(decoded.getTotalCents());     // 12500
System.out.println(decoded.hasCustomerNote());   // true
System.out.println(decoded.getCustomerNote());   // ""
~~~

When a Java program compiled with **v1** reads a message containing field **5** sent by v2, it has no **getCustomerNote()** getter. With the standard Protobuf Java runtime, you can inspect unknown data via **getUnknownFields()**:

~~~java
// Conceptual example: variable orderV1 is an Order generated from schema v1.
boolean hasUnknownField5 =
    orderV1.getUnknownFields().asMap().containsKey(5);
~~~

The snippet above must run against the **v1 Order** class and an actual payload containing field 5; you cannot run two class versions with the exact same name/package for v1 and v2 simultaneously in a simple single Java module. When rebuilding a message from scratch with a new builder, copying only known fields, or converting through JSON, unknown fields can be dropped. Consequently, a proxy that reads and rewrites Protobuf will not necessarily preserve all data from newer versions across all processing flows.

To verify this in practice, set up **two independent client/server versions** or two code-generation sets in separate test modules/packages, exchange payloads between them, and compare results. Do not just serialize and parse using the same version and claim the schema is compatible.

## 11. Binary Wire, JSON, and Java API Are Three Different Layers

The gRPC protocol normally transmits binary Protobuf. However, real systems may add a REST gateway, JSON logging, or external storage:

| Communication layer | What determines compatibility |
| --- | --- |
| **Protobuf binary** | Field number, wire type, decoding rules, and field semantics |
| **Protobuf JSON** | Field name/JSON name, numeric formatting, enums, default/presence, and unknown field handling policy |
| **Generated Java API** | Package, message names, enums, field names, and getter/setter/builder methods |
| **Business logic** | Units of measure, required conditions, default values, new states, and field meaning |

For example, renaming **order_id** to **id** while keeping **= 1** and type **string** usually still reads old binary payloads. However, Java changes **getOrderId()** to **getId()** and Protobuf JSON by default changes the property name from **orderId** to **id** unless a custom JSON name is configured. Old Java code will fail to compile when updating generated classes; JSON consumers may also fail to find the expected property.

Similarly, adding a new enum value can cause a **switch** branch in business code to fail to handle the unfamiliar state, even though the binary parser preserves the number. Contract updates must be evaluated across the exact data paths the system uses.

## 12. Workflow for Changing Contracts When Deploying Spring gRPC

A practical workflow for evolving from v1 to v2:

1. **Audit existing fields:** identify numbers, types, names, meanings, and stored data. For retired fields, record history before marking **reserved**.
2. **Add new fields:** pick an unused number (e.g., **5**), appropriate field type, and presence. Do not renumber fields 1–3 just to make the schema look tidy.
3. **Generate code independently and verify:** compile the .proto and Java classes at each version; confirm client/server code uses the intended types. Avoid packaging two definitions with the same full name in a single binary.
4. **Evaluate both communication directions:** feed payloads from v1 to a v2 reader and from v2 to a v1 reader; inspect decoded values, unknown fields, and business code reactions.
5. **Deploy according to dependency order:** typically update readers before senders start relying on new fields, while continuing to support requests from older clients. With rolling deployments, test while both instance versions coexist.
6. **Monitor after deployment:** track **INVALID_ARGUMENT** and **INTERNAL** RPC errors, parse errors, failed request rates, latency, and client traffic split by version. Note that metadata, deadlines, TLS, and interceptors belong to other RPC/operational layers, yet still affect incident diagnostics.
7. **Remove old logic only when conditions are met:** evaluate active clients, long-lived stored data, and rollback capability. Always keep old field numbers in **reserved**.

If a change requires an entirely new data unit or meaning, you can create a **new field with a new number**, migrate data during a transition period, and then retire the old field. For sweeping changes across multiple RPCs, consider a newly versioned contract/service rather than forcing superficial binary compatibility.

## 13. What Should Compatibility Testing Cover?

A round-trip test within the same schema verifies basic encoding/decoding, but will not catch multi-version compatibility bugs. For Spring gRPC, include at least the following groups:

| Test | What to verify |
| --- | --- |
| **v1 → v2** | Data created by v1 still decodes existing fields; new v2 fields have sensible values/presence when omitted. |
| **v2 → v1** | v1 reads shared fields accurately; handles unknown fields without causing logic errors. |
| **Default values** | Unsent scalars, scalars set to default values, and **optional** scalars set to default values behave as designed. |
| **New enums** | Old code handles unrecognized values; never misinterprets an enum number as another state. |
| **Repeated/packed** | Readers accept the peer version's valid encoding while preserving element count and order. |
| **JSON/gateway** | JSON names, enums, 64-bit integers, unknown fields, and binary–JSON conversion match the public contract. |
| **gRPC integration** | Client and server on different versions invoke unary/streaming RPCs, receive proper statuses/trailers, and suffer no data misinterpretation. |

A short test for presence using **v2** Java code:

~~~java
import static org.junit.jupiter.api.Assertions.*;

Order source = Order.newBuilder()
    .setOrderId("o-42")
    .setCustomerNote("")
    .build();

Order restored = Order.parseFrom(source.toByteArray());

assertTrue(restored.hasCustomerNote());
assertEquals("", restored.getCustomerNote());
assertEquals("o-42", restored.getOrderId());

Order missingNote = Order.newBuilder()
    .setOrderId("o-43")
    .build();

assertFalse(missingNote.hasCustomerNote());
~~~

This test proves presence within the same v2 schema; to test **wire compatibility**, add payload fixtures generated by each schema version and run them against an independent reader of the other version.

## 14. Practice Scenario

A development team is modifying the **Payment** message:

~~~proto
// Current version
message Payment {
  string payment_id = 1;
  int64 amount_cents = 2;
  string currency = 3;
  string reference = 4;
}
~~~

The product team makes four proposals:

1. Change **amount_cents = 2** to **double amount = 2** because they want to display decimal amounts.
2. Rename **payment_id = 1** to **payment_code = 1**, keeping type **string**.
3. Add **optional string failure_reason = 5**.
4. Remove **reference = 4**, and reuse number **4** for **bool is_refunded = 4**.

Classify the risk level of each proposal across all three perspectives: **binary wire**, **Java/JSON API**, and **business semantics**. Then write a safer revised schema, keeping existing numbers and using **reserved** for the retired field.

**Verification hints:**

- **double** uses wire type **1**, whereas **int64** uses wire type **0**; beyond encoding differences, there are also precision and unit-change risks.
- Renaming while keeping number/type may not alter binary encoding, but it changes the Java getter and default JSON property name.
- Adding **failure_reason = 5** does not force old clients to know the new field, yet the server must still handle the case where that field is absent.
- Reusing number **4** for boolean data can cause old/new versions to misinterpret or drop data. The safer approach is to retire number 4, keep it in **reserved**, and assign a new number for **is_refunded**.

## 15. Key Principles to Remember

- **Field numbers determine identity on the wire**; numbers must be unique within each message, stable, and never reused after deletion.
- **Tag = (field number << 3) | wire type**; sharing a wire type does not mean two fields share the same semantics.
- **Adding a field** is usually structurally binary-safe if a new number is used, though older readers may ignore the new data.
- **reserved** protects numbers/names in the new schema; it does not erase historical data and cannot stop old clients from emitting the corresponding bytes.
- **Test both directions across multiple versions**, and also evaluate Java APIs, Protobuf JSON, presence, and business requirements.

Mastering field numbers and wire compatibility allows you to evolve Protocol Buffers contracts while keeping Spring gRPC services stable when unary or streaming clients and servers are upgraded independently. It is also the foundation for designing reliable monitoring and integration testing before taking services into production.
