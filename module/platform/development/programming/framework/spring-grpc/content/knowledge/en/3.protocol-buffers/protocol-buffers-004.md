# Field Names, JSON Names, and Reserved Fields

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **field name** in a .proto file, **JSON name** in ProtoJSON, and **field number** in binary Protocol Buffers data.
- Apply the **lower_snake_case** naming convention, understand how **lowerCamelCase** is formed, and use the **json_name** option when needed.
- Explain why renaming a field can preserve binary compatibility while altering the Java API and JSON contract.
- Declare **reserved numbers** and **reserved names** when removing fields to prevent reusing historical identities.
- Test message contracts in a Spring gRPC environment where clients/servers and JSON tools run across different versions.

## 1. How Do Field Name, JSON Name, and Field Number Differ?

In the **SPRING_GRPC** module, Protocol Buffers files define data structures that are generated into Java classes and exchanged via unary or streaming RPCs. gRPC typically uses **binary** Protobuf encoding. However, requests/responses are also sometimes exported as **ProtoJSON** for REST gateways, logging, testing, or external system integrations.

Consider:

~~~proto
message Customer {
  string customer_id = 1;
}
~~~

| Concept | In the example | What is it used for? |
| --- | --- | --- |
| Field name | **customer_id** | Identifies the field in .proto, descriptors, and the generated Java API. |
| Default JSON name | **customerId** | Property key when exporting the message with ProtoJSON. |
| Field number | **1** | Identity of the field on the binary wire. |

With standard Java code generation settings, this field gets the getter **getCustomerId()** and builder method **setCustomerId(...)**. Binary Protobuf writes tags using the **field number** and wire type; it does not write the string name **customer_id** into each message.

These three concepts are not interchangeable. Renaming a field while keeping **number 1** and type **string** usually still reads old bytes. Conversely, changing number 1 to number 10 can break binary communication even though the field name and JSON look unchanged. This distinction is critical when multiple versions of Spring gRPC clients and servers are deployed independently.

## 2. Field Naming Conventions in proto3

Protobuf recommends writing field names in **lower_snake_case**: lowercase letters with underscores between words.

~~~proto
message Customer {
  string customer_id = 1;
  string display_name = 2;
  string preferred_language = 3;
  int64 points_balance = 4;
}
~~~

These names describe the data itself, rather than temporary variable names or how a specific UI renders them. Prefer **amount_cents** if amounts are counted in cents, **created_at** for creation timestamps, and **preferred_language** for the preferred language. Avoid overly broad names like **data** or **value** when a message holds multiple concepts.

When authoring schemas:

1. Each field has a **unique name** within the same message. Names currently marked **reserved** cannot be redeclared.
2. Identifiers must be valid in .proto syntax: must not start with a digit, and must not use schema language keywords.
3. Keep naming conventions consistent across messages. Avoid alternating between **customer_id**, **customerID**, and **CustomerId** for the same concept.
4. Do not casually rename a released field. Even if the binary wire does not change, generated Java code, documentation, reflection, and JSON tools may depend on the old name.
5. When the content or unit of data changes, do not merely rename the field to hide a business difference. Consider using a new field with a new number.

A name in .proto also appears in **descriptors**, generated code documentation, and Protobuf's text format (**TextFormat**). Thus, field names remain a contract surface worth managing even though they do not appear directly in binary payloads.

## 3. How Are Default JSON Names Generated?

Under ProtoJSON rules, **lower_snake_case** field names are normally converted to **lowerCamelCase**:

| Name in .proto | Default ProtoJSON key | Java getter |
| --- | --- | --- |
| **customer_id** | **customerId** | **getCustomerId()** |
| **display_name** | **displayName** | **getDisplayName()** |
| **preferred_language** | **preferredLanguage** | **getPreferredLanguage()** |
| **points_balance** | **pointsBalance** | **getPointsBalance()** |
| **is_verified** | **isVerified** | **getIsVerified()** |

Example:

~~~proto
message Customer {
  string customer_id = 1;
  string display_name = 2;
}
~~~

A message with corresponding values can be exported as:

~~~json
{
  "customerId": "C-42",
  "displayName": "Nguyen An"
}
~~~

The **ProtoJSON parser** accepts both the JSON name and the original .proto name for the same field. Thus, for the schema above, both the key **customerId** and the key **customer_id** can be parsed into field number 1. This is a property of the ProtoJSON parser, not a guarantee that every custom JSON library behaves the same way.

Do not send both **customerId** and **customer_id** simultaneously in a single object to represent the same field. Doing so creates duplicate data that may be rejected by the parser or handled unpredictably. An API's output should consistently use a single key name.

JSON also has specific rules for **values**: **int64** types are exported as decimal strings to avoid precision loss in environments using IEEE-754 floating-point numbers; enums are typically exported by name. Therefore, when testing JSON compatibility, verify both keys and values.

## 4. Customizing JSON Names with json_name

If a public JSON contract already uses a different spelling, you can set the exact key using the **json_name** option:

~~~proto
syntax = "proto3";

package learning.customers.v1;

option java_package = "com.example.customers.v1";
option java_multiple_files = true;

message Customer {
  string customer_id = 1 [json_name = "customerID"];
  string display_name = 2;
  optional string preferred_language = 3;
  int64 points_balance = 4;
}
~~~

In this case, ProtoJSON output uses **customerID** instead of **customerId**. Everything else remains unchanged:

- The field in .proto is still named **customer_id**.
- The field number is still **1**.
- The Java getter and setter are still **getCustomerId()** and **setCustomerId(...)**.
- Binary gRPC communication does not send the new JSON name; it still identifies the field by number 1.

Example of a valid JSON payload:

~~~json
{
  "customerID": "C-42",
  "displayName": "Nguyen An",
  "preferredLanguage": "vi",
  "pointsBalance": "9007199254740993"
}
~~~

The value of **pointsBalance** is a string because the .proto type is **int64**. The fact that Java uses **long** does not make ProtoJSON output this 64-bit integer as a JSON number by default.

Use **json_name** deliberately, such as when conforming to an already deployed JSON key. For new APIs, default JSON names are usually easier to maintain. Adding unnecessary custom rules makes schemas harder to read and increases collision risks.

### Watch Out for Colliding JSON Names

Two fields with different names in .proto can still produce the same JSON name:

~~~proto
// Conflict illustration example; do not use as a deployment schema.
message BadNaming {
  string user_id = 1;
  string userId = 2;
}
~~~

These two names risk both mapping to **userId** in ProtoJSON. **protoc** checks for JSON name collisions according to compiler rules; even if a particular syntax variation were accepted, you should never create two fields competing for one JSON key. When using an explicit **json_name**, also avoid colliding with the JSON name of another field.

## 5. Complete gRPC Contract Illustrating Naming

A complete example for a service retrieving customer information:

~~~proto
syntax = "proto3";

package learning.customers.v1;

option java_package = "com.example.customers.v1";
option java_multiple_files = true;

message Customer {
  string customer_id = 1 [json_name = "customerID"];
  string display_name = 2;
  optional string preferred_language = 3;
  int64 points_balance = 4;

  // Assume these fields previously existed in an old schema.
  reserved 5, 7 to 9;
  reserved "legacy_nickname";
}

message GetCustomerRequest {
  string customer_id = 1 [json_name = "customerID"];
}

message GetCustomerResponse {
  Customer customer = 1;
}

service CustomerService {
  rpc GetCustomer(GetCustomerRequest) returns (GetCustomerResponse);
}
~~~

**package** is the Protobuf schema namespace; **java_package** determines the package of the generated Java classes. **java_multiple_files = true** allows top-level types to be generated into separate Java classes. Setting **json_name** does not affect RPC signatures or how gRPC transmits requests/responses.

In a Java client:

~~~java
import com.example.customers.v1.GetCustomerRequest;
import com.example.customers.v1.GetCustomerResponse;
import com.example.customers.v1.CustomerServiceGrpc;

// Assume the channel has already been configured and provided to the client.
CustomerServiceGrpc.CustomerServiceBlockingStub stub =
    CustomerServiceGrpc.newBlockingStub(channel);

GetCustomerResponse response = stub.getCustomer(
    GetCustomerRequest.newBuilder()
        .setCustomerId("C-42")
        .build());

String displayName = response.getCustomer().getDisplayName();
~~~

The Spring gRPC server also uses getters from the generated messages to read requests. Configuring stubs, TLS, metadata, deadlines, statuses, and interceptors belongs to the communication and operational layers; they do not alter Protobuf naming rules.

## 6. Using JsonFormat in Java

Applications can use **com.google.protobuf.util.JsonFormat** from the **protobuf-java-util** library, at a version compatible with the Protobuf runtime. This is the tool for serializing/parsing **ProtoJSON**, unlike using a generic JSON serializer that only inspects Java class getters.

~~~java
import com.example.customers.v1.Customer;
import com.google.protobuf.util.JsonFormat;

Customer customer = Customer.newBuilder()
    .setCustomerId("C-42")
    .setDisplayName("Nguyen An")
    .setPreferredLanguage("vi")
    .setPointsBalance(9007199254740993L)
    .build();

String json = JsonFormat.printer().print(customer);
System.out.println(json);
// Output contains the "customerID" key per the declared json_name.

Customer.Builder builder = Customer.newBuilder();
JsonFormat.parser().merge(json, builder);
Customer restored = builder.build();

System.out.println(restored.getCustomerId());         // C-42
System.out.println(restored.hasPreferredLanguage());  // true
~~~

If emitting the original .proto field names is required, you can use:

~~~java
String protoNamedJson = JsonFormat.printer()
    .preservingProtoFieldNames()
    .print(customer);
// Keys will then be "customer_id", "display_name", ...
~~~

This option affects how JSON is printed at the application boundary; it does not modify the schema or field numbers. Parties exchanging JSON must agree on the naming convention before depending on it.

When parsing, the library accepts both the configured JSON name and the original .proto name. However, when encountering an **unknown key**, the parser throws an error by default. Java provides an option to ignore it:

~~~java
Customer.Builder builder = Customer.newBuilder();
JsonFormat.parser()
    .ignoringUnknownFields()
    .merge(jsonFromOtherVersion, builder);
~~~

Only ignore unknown fields if the contract permits discarding that information. When binary Protobuf data is read and then converted to JSON, unknown fields from newer versions may be lost in the intermediate step; do not assume data is always preserved.

## 7. Renaming a Field While Keeping Its Number

Suppose an API previously released message v1:

~~~proto
message Customer {
  string customer_id = 1;
  string display_name = 2;
}
~~~

Due to internal terminology requirements, the development team plans to rename **display_name** to **full_name**:

~~~proto
// Example v2 — compiled separately from v1.
message Customer {
  string customer_id = 1;
  string full_name = 2 [json_name = "displayName"];
  reserved "display_name";
}
~~~

Comparison:

| Perspective | Result |
| --- | --- |
| Binary wire | Field **2** is still a **string**; old bytes usually decode to the same value. |
| Outgoing ProtoJSON | **json_name** preserves the **displayName** key just like v1. |
| Incoming ProtoJSON | v2 accepts **displayName** and the new .proto name **full_name**; do not assume the old alias **display_name** is still accepted. |
| Java API | Getter **getDisplayName()** becomes **getFullName()**; call sites must be updated. |
| Descriptor, TextFormat | Schema name has changed; tools looking up by the old name may be affected. |
| Reserved name | Prevents redeclaring the .proto name **display_name** in the message. |

**Do not reserve number 2** in this case, because the new field **full_name** still uses number 2. Reserving the old name helps control the rename; keeping the number and type preserves binary identity.

In many cases, changing the display label in the frontend or DTO is enough. Keeping the .proto name reduces the number of places to modify, especially when multiple clients use generated Java classes. If the JSON API truly needs to change a key, plan client upgrades and contract tests accordingly.

**json_name is not an unlimited alias system.** It declares a primary JSON name for the current field; the parser also accepts the current .proto name, but does not automatically retain every historical .proto name.

## 8. How Do Reserved Fields Protect the Contract?

The **reserved** keyword marks **field numbers** or **field names** that are no longer allowed to be used in a message. This mechanism is useful when removing a field that was previously sent over the network or stored in a database, queue, or backup.

Previous version:

~~~proto
message Customer {
  string customer_id = 1;
  string legacy_nickname = 5;
  int32 old_score = 7;
}
~~~

New version:

~~~proto
message Customer {
  string customer_id = 1;

  reserved 5, 7;
  reserved "legacy_nickname", "old_score";

  string display_name = 2;
}
~~~

**reserved 5, 7** prevents anyone from reusing numbers 5 or 7 for new data. This is critical protection for binary compatibility: an old client may still send bytes carrying number 5 or 7 after the server has upgraded.

**reserved "legacy_nickname", "old_score"** prevents an engineer from accidentally reusing an old .proto name with a different meaning. Field names do not appear in standard binary Protobuf, yet they still matter for JSON, generated code, and documentation. When removing a released field, it is usually best to reserve **both the number and the name**.

### Reserved Is Not a Data-Deletion Mechanism

Reserved is only a rule **at schema compile time**:

- It does not delete old fields from stored data bytes.
- It does not stop an old client from continuing to send that field.
- It does not automatically migrate old values to a new field.
- It does not force a gRPC parser to return an error when encountering the old field number; that field may become an **unknown field**.
- It does not turn the old JSON name into a valid alias for another field.

Protobuf Java can preserve unknown fields when parsing and re-serializing binary data. However, DTO mapping, JSON conversion, or manual message reconstruction can strip them. Therefore, historical data and old clients must be managed with a real upgrade plan.

## 9. Reserved Syntax: Numbers, Ranges, and Names

Inside a message, you can reserve individual numbers or ranges:

~~~proto
message Event {
  string event_id = 1;
  reserved 2, 4 to 6, 10;
  reserved "legacy_owner", "old_payload";
}
~~~

**4 to 6** includes 4, 5, and 6. Valid Protobuf field numbers range from **1** to **536,870,911**, excluding **19,000–19,999** reserved for Protobuf implementations.

Names and numbers must be placed in **separate reserved statements**, not mixed:

~~~proto
// Valid:
reserved 2, 5 to 8;
reserved "old_name", "retired_code";

// Invalid:
// reserved 2, "old_name";
~~~

The statements illustrating the syntax above must be placed **inside a message**, not directly at the file top level. Likewise, you cannot reserve a number or name that already belongs to an active field. Fields inside a **oneof** must still respect the name and number scope of their enclosing message.

Reserved is scoped per message: number 5 reserved in **Customer** does not prevent message **GetCustomerRequest** from using number 5. In a brand-new unused schema, do not preemptively declare a bunch of reserved numbers just to guess the future; reserve numbers/names based on history or a concrete design decision.

## 10. Why Must You Keep Both Reserved Number and Reserved Name?

| What needs protection | Reserve old number | Reserve old name |
| --- | --- | --- |
| Prevent a new field from reusing the same number in binary | **Yes** | No |
| Prevent a new field from reusing the .proto name | No | **Yes** |
| Reduce the risk of old binary data being read with a new meaning | **Directly** | Indirectly |
| Prevent old clients from sending bytes with the removed number | No | No |
| Automatically reject old JSON keys | No | No |
| Map old JSON to a new field | No | No |

Consider this mistake: old field **string old_email = 3** is removed, but the new schema only reserves the name and then adds **string phone = 3**. Because both use number 3 and the same binary string encoding, historical email data could be misinterpreted by the new server as a phone number. **Reserving the name cannot prevent this bug**.

A more accurate schema:

~~~proto
message Contact {
  reserved 3;
  reserved "old_email";

  string phone = 4;
}
~~~

If the old field was named **old_email**, the default JSON name was **oldEmail**. **reserved "old_email"** protects the identifier name in .proto, not a blocklist for all JSON keys. The JSON parser still processes incoming keys according to the current schema and unknown-fields policy.

## 11. Reserved in Enums

In proto3 enums, values have an **enum number** and an **enum name**. If you retire a state, do not reuse the old number or name for another state:

~~~proto
enum CustomerState {
  CUSTOMER_STATE_UNSPECIFIED = 0;
  CUSTOMER_STATE_ACTIVE = 1;
  CUSTOMER_STATE_PAUSED = 2;

  reserved 3, 5 to 7;
  reserved "CUSTOMER_STATE_LEGACY";
}
~~~

The example assumes the reserved values existed historically. A proto3 enum must have its first element numbered **0**; a name like **UNSPECIFIED** helps represent the unspecified default state.

In binary Protobuf, enums are transmitted as numbers; in ProtoJSON, enums are normally written by **name**. Therefore, changing an enum number can break binary interpretation, while changing an enum name can break JSON clients relying on the old string name. Reserving enum numbers and names helps avoid accidental reuse, though it does not automatically migrate historical data.

## 12. Comparing Schema Changes Across Compatibility Layers

| Change | Binary Protobuf | JSON, Java code, and business logic |
| --- | --- | --- |
| Rename field, keep number and type | Usually keeps ability to read old bytes. | May change JSON name, getters/setters, and descriptors. |
| Change **json_name** only | Binary unchanged. | Exported JSON key changes; old clients may break. |
| Change field number, keep name and type | Not reliably compatible. | JSON looks the same, but binary treats it as a different field. |
| Add a new field with an unused number | Usually binary-structurally safe. | Old clients lack the getter or do not know the new JSON key. |
| Remove field and reserve number/name | New parser may treat old field as unknown. | Java code loses the getter; old JSON may contain unrecognized keys. |
| Reuse old number for a new meaning | Dangerous, can misinterpret data. | Clients may produce incorrect business values. |
| Rename enum, keep number | Binary can remain intact. | Name-based JSON enums may break old contracts. |

**Binary compatibility does not mean source-code compatibility.** A contract might decode bytes properly yet fail to compile the Java application after a getter changes. Conversely, a JSON system may break due to a changed JSON key while pure binary Protobuf gRPC calls continue operating normally.

For Spring gRPC services, you must also verify business rules such as application-required fields, default values, enum states, and how the server returns **INVALID_ARGUMENT**. Those are additional requirements, independent of whether field numbers are valid.

## 13. Strategies for Changing a Released Field

Suppose the system previously used:

~~~proto
message Customer {
  string display_name = 2;
}
~~~

There are three main options:

**Keep the old name if the meaning has not changed.** When you want to adjust UI presentation, update the frontend or DTO labels; keeping the .proto identifier minimizes churn across Java code, ProtoJSON, and schema tools.

**Rename in .proto while preserving the old JSON name when required.** You can use:

~~~proto
message Customer {
  string full_name = 2 [json_name = "displayName"];
  reserved "display_name";
}
~~~

This preserves the field number and exported JSON key, though you still need to update Java call sites and check JSON inputs using the old .proto name.

**Create a new field if the meaning changed.** If it previously stored a display name and now you want a legal name following different rules, use a new field:

~~~proto
message Customer {
  string display_name = 2 [deprecated = true];
  string legal_name = 6;
}
~~~

During the transition period, the server can read both fields, log client versions, and clearly define precedence when both are present. Once you are certain nothing depends on the legacy data, remove the old field and reserve it:

~~~proto
message Customer {
  reserved 2;
  reserved "display_name";
  string legal_name = 6;
}
~~~

The **deprecated** annotation only marks an API as no longer recommended; it does not alter wire encoding and does not automatically migrate data.

## 14. Testing with JsonFormat and Multiple Versions

A test using **JUnit 5** and the complete schema from section 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.customers.v1.Customer;
import com.google.protobuf.util.JsonFormat;
import org.junit.jupiter.api.Test;

class CustomerJsonTest {
    @Test
    void acceptsJsonNameAndOriginalProtoName() throws Exception {
        Customer original = Customer.newBuilder()
            .setCustomerId("C-42")
            .setDisplayName("Nguyen An")
            .build();

        String json = JsonFormat.printer().print(original);
        assertTrue(json.contains("\"customerID\""));
        assertTrue(json.contains("\"displayName\""));

        Customer.Builder parsed = Customer.newBuilder();
        JsonFormat.parser().merge(
            "{\"customer_id\":\"C-42\",\"display_name\":\"Nguyen An\"}",
            parsed);

        assertEquals(original, parsed.build());
    }
}
~~~

This test proves the parser understands the original .proto name and the printer uses the JSON name of the current schema. However, a test within **the same version** is not sufficient to conclude upgrade compatibility.

To test changes in a real project:

1. Save binary payloads produced by **client/schema v1**, then read them with **reader v2**; also test the reverse direction.
2. Save ProtoJSON v1 samples, run the v2 parser; confirm old JSON keys are still supported or have a migration path.
3. Check Java getters/setters and clients building with code generated from v1/v2.
4. Test omitted fields, optional fields set to default values, and unknown fields/enums.
5. Run integration tests across different Spring gRPC client and server versions, observing actual data, statuses, and behavior during gradual rollouts.

Protoc can catch static errors such as duplicate field numbers, **reserved** violations, or name collisions. However, the compiler cannot know business history or what data old clients have persisted. That requires change documentation and test fixtures.

## 15. Common Mistakes

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Treating the .proto name as the default JSON name | JSON API uses unexpected keys. | Learn the lowerCamelCase rule and verify JsonFormat output. |
| Renaming a field and testing only binary gRPC | Misses Java API, JSON, and descriptor breakage. | Test every contract layer. |
| Reserving only the old name | The old field number could be reused and cause binary misinterpretation. | Reserve both the number and the name of removed fields. |
| Reusing an old name for a different meaning | Documentation and old clients can get confused. | Reserve retired names. |
| Using json_name to mask semantic differences | JSON keeps the old key while values change meaning. | Create a new field if values no longer share the same meaning. |
| Thinking reserved deletes bytes or blocks old clients | Historical data still arrives as unknown fields. | Plan transitions and test them. |
| Ignoring unknown JSON fields to hide all errors | Key typos or contract shifts go unnoticed. | Use ignoringUnknownFields only under an explicit policy. |

## 16. Practice Exercise

An order service initially has the schema:

~~~proto
syntax = "proto3";

message Order {
  string order_id = 1;
  string customer_name = 2;
  string legacy_coupon = 3;
  int64 total_cents = 4;
}
~~~

Requirements for the next version:

1. Keep number **1** and .proto name **order_id**, but export ProtoJSON with the key **orderID**.
2. Change the UI display label for **customer_name** while keeping the same data meaning. Explain why renaming the field in the schema may not be necessary.
3. Remove **legacy_coupon**, while protecting **number 3** and **name legacy_coupon**.
4. Add **optional string delivery_note** on an unused field number; distinguish omitted from empty string.
5. Explain the consequence if someone reuses number **3** for **bool is_priority = 3**.
6. Write a ProtoJSON test confirming the **orderID** key, the parser's acceptance of **order_id**, and **hasDeliveryNote()** before/after setting an empty string.

A schema meeting the structural requirements:

~~~proto
syntax = "proto3";

message Order {
  string order_id = 1 [json_name = "orderID"];
  string customer_name = 2;
  reserved 3;
  reserved "legacy_coupon";
  int64 total_cents = 4;
  optional string delivery_note = 5;
}
~~~

This is still a **JSON contract change** for clients expecting the **orderId** key. When a REST gateway or external clients exist, test and plan the JSON key migration before release.

## 17. Key Takeaways

- **Field name** identifies a field in .proto, **JSON name** identifies the ProtoJSON property, and **field number** identifies the field in binary Protobuf.
- .proto names should use **lower_snake_case**; ProtoJSON defaults to **lowerCamelCase**. Use **json_name** when an explicit JSON name is genuinely needed.
- Changing a .proto name can stay binary-compatible if number/type remain unchanged, but does not guarantee Java code, JSON, or descriptor compatibility.
- **Reserved numbers** prevent reusing old numbers; **reserved names** prevent reusing old .proto names. When removing a released field, normally keep both.
- **Reserved** is a compile-time schema constraint, not a runtime data deletion or migration mechanism.
- Contract change testing must cover **binary**, **ProtoJSON**, **Java code**, and **application semantics**, especially when Spring gRPC clients and servers upgrade independently.

Understanding field names, JSON names, and reserved fields helps you design Protocol Buffers contracts capable of evolving across versions while keeping Spring gRPC services stable from unary to streaming RPCs.
