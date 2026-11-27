# Messages and Fields in proto3

## Learning Objectives

After this lesson, you will be able to:

- Declare a **message** in a **proto3** Protocol Buffers file, name fields, and assign field numbers according to the rules.
- Choose between singular, **optional**, **repeated**, **map**, **oneof**, nested messages, and enums; and understand their corresponding Java types.
- Distinguish between **default values** and **field presence**, especially when updating data over gRPC.
- Use Java classes generated from the schema to create, read, and serialize messages, and to build requests/responses.
- Evolve a schema in a way that minimizes the risk of breaking the contract between a Spring gRPC client and server.

## 1. Where Do Messages Fit in a Spring gRPC Application?

In a Spring gRPC application, the **.proto** file describes the contract between processes: what data is sent and which RPCs accept/return that data. **Protocol Buffers (Protobuf)** defines the data structure and binary encoding format; **gRPC** uses those messages as requests/responses when calling services. The **protoc** compiler along with code-generation plugins generates Java classes for messages and gRPC stubs. Spring application code then works with the generated classes instead of parsing bytes manually.

A **message** is similar to a structured data type. Each **field** is a property with a **type**, **name**, and **number**. For example, a user profile management system needs to send a profile ID, display name, skills, and contact channel; a single message can group all of that information into a unified object.

A typical development flow:

~~~text
profile.proto
    |
    +-- protoc / Java plugin ------> Profile, GetProfileRequest, ...
    |
    +-- gRPC Java plugin ----------> ProfileServiceGrpc (stubs, base class)
                                         |
                              Spring gRPC client/server
~~~

Choosing the right fields in the schema matters more than surface syntax: encoded data relies on **field numbers**, so a decision made today can affect the ability of older client/server versions to read data.

## 2. A Complete proto3 Contract Example

Suppose a profile management service uses a unary RPC to query a profile. The file **src/main/proto/profile.proto** might be defined as follows:

~~~proto
syntax = "proto3";

package learning.profile.v1;

option java_package = "com.example.profile.v1";
option java_multiple_files = true;

import "google/protobuf/timestamp.proto";

enum ProfileStatus {
  PROFILE_STATUS_UNSPECIFIED = 0;
  PROFILE_STATUS_ACTIVE = 1;
  PROFILE_STATUS_SUSPENDED = 2;
}

message Profile {
  string id = 1;
  string display_name = 2;
  optional string nickname = 3;
  repeated string skills = 4;
  map<string, string> labels = 5;
  ProfileStatus status = 6;
  google.protobuf.Timestamp updated_at = 7;

  oneof contact {
    string email = 8;
    string phone = 9;
  }

  message Address {
    string city = 1;
    string country_code = 2;
  }

  Address address = 10;

  // Fields retired in previous versions.
  reserved 11, 15 to 18;
  reserved "legacy_bio";
}

message GetProfileRequest {
  string profile_id = 1;
}

message GetProfileResponse {
  Profile profile = 1;
}

service ProfileService {
  rpc GetProfile(GetProfileRequest) returns (GetProfileResponse);
}
~~~

Key components:

| Component | Meaning |
| --- | --- |
| **syntax = "proto3"** | Selects proto3 grammar. |
| **package** | Namespace of the Protobuf schema; helps avoid name collisions across contracts. |
| **java_package** | Package of the generated Java classes, which can differ from the Protobuf package. |
| **java_multiple_files = true** | Generates top-level types such as **Profile**, **GetProfileRequest**, and **ProfileStatus** as separate Java classes/files. |
| **message Profile** | Data type used to transmit a profile over RPC. |
| **string id = 1** | A field with type **string**, name **id**, and number **1**. |
| **service/rpc** | Describes a gRPC method that takes **GetProfileRequest** and returns **GetProfileResponse**. |

This example illustrates contract structure. The **reserved** section assumes fields 11, 15–18 and the name **legacy_bio** once existed; for a brand-new schema, only declare **reserved** when there are actually numbers/names that must be blocked from reuse.

## 3. Field Numbers: Identity on the Wire

The common syntax of a field is **[type] [name] = [number];**. In the example **string display_name = 2;**, the name **display_name** helps developers read the source code, while **2** is the field's identity when Protobuf encodes the data.

Important rules:

1. Valid numbers range from **1 to 536,870,911**, excluding **19,000–19,999** which are reserved for Protobuf implementations; **0** is invalid.
2. Fields within the **same message** must not share the same number. Nested messages or other messages have their own number scope.
3. Fields **1–15** have tags that are encoded more compactly than fields **16–2047**; smaller numbers should be saved for frequently appearing fields. Do not sacrifice clarity just to optimize before measuring impact.
4. **Never change the number** of a deployed field and **never reuse** a deleted number. Use **reserved** to reserve old numbers or names.
5. Renaming a **field name** while keeping its number usually does not change binary parsing; however, it can break Java code calling old getters/setters or systems using Protobuf JSON. Therefore, you still need to evaluate the impact of renaming.

For example, if an earlier version had a field **string old_note = 11;**, when removing that field, declare **reserved 11;** (and optionally **reserved "old_note";**) to avoid accidentally assigning number 11 to completely different data. You must not declare **reserved** overlapping an active field in the same message.

## 4. Basic Data Types and Default Values

Proto3 has scalar types and structured types. Some common mappings when generating Java code:

| Type in proto3 | Generated Java | Default value when scalar field has no presence |
| --- | --- | --- |
| **string** | **String** | Empty string **""** |
| **bool** | **boolean** | **false** |
| **int32**, **sint32**, **uint32**, **fixed32**, **sfixed32** | **int** | **0** |
| **int64**, **sint64**, **uint64**, **fixed64**, **sfixed64** | **long** | **0L** |
| **float** | **float** | **0.0f** |
| **double** | **double** | **0.0d** |
| **bytes** | **com.google.protobuf.ByteString** | **ByteString.EMPTY** |
| **enum** | Generated Java Enum | Element with number **0** |

Note: **uint32/uint64** are *unsigned* numeric types at the protocol level but are represented by Java's signed **int/long**; when you need to handle the full value range, appropriate unsigned conversion operations must be used. **sint32/sint64** use ZigZag encoding, which is more efficient than **int32/int64** for small negative values; **fixed32/fixed64** have a fixed encoded size. Choose the type based on the actual data range and value distribution.

An **enum** in proto3 must have a first value equal to **0**. A name like **PROFILE_STATUS_UNSPECIFIED** helps express an "unspecified" state when no explicit value is set. You should not implicitly treat 0 as a confirmed business state.

A **message field** such as **Profile address** or **google.protobuf.Timestamp updated_at** has presence semantics: Java generates **hasAddress()** and **hasUpdatedAt()** methods. Calling **getAddress()** returns a default instance when the field is absent, so you need to call **hasAddress()** if you must distinguish "address not sent" from "empty address sent".

## 5. Distinguishing Default, Absent, and Optional

This is the easiest place to introduce bugs when designing partial-update APIs:

~~~proto
message UpdateDisplayNameRequest {
  string profile_id = 1;
  string display_name = 2;
  optional string nickname = 3;
}
~~~

With **display_name** (a regular scalar, implicit presence), Java calling **getDisplayName()** receives **""** both when the client omits the field and when the client sends an empty string. There is no **hasDisplayName()** for this scalar field.

With **optional nickname** (explicit presence), Java provides both **hasNickname()** and **getNickname()**. As a result, the server can distinguish:

| Data sent by client | hasNickname() | getNickname() | Interpretation during partial update |
| --- | --- | --- | --- |
| **nickname** not set | **false** | **""** | Can keep the existing value |
| **nickname = ""** set | **true** | **""** | Can intentionally clear the nickname |
| **nickname = "An"** set | **true** | **"An"** | Update to **An** |

Example in Java:

~~~java
UpdateDisplayNameRequest noChange = UpdateDisplayNameRequest.newBuilder()
    .setProfileId("p-42")
    .build();

UpdateDisplayNameRequest clearNickname = UpdateDisplayNameRequest.newBuilder()
    .setProfileId("p-42")
    .setNickname("")
    .build();

System.out.println(noChange.hasNickname());     // false
System.out.println(clearNickname.hasNickname()); // true
~~~

Do not use **null** as a signal for "no value" when working with setters on generated Protobuf Java code. **Optional** is a schema property, and a Java message object after **build()** is immutable.

Proto3 **does not support the required label**. To require callers to provide a non-empty profile ID, validate it in the application/server. For a scalar that must distinguish absence from its default value, use **optional**, **oneof**, or a wrapper message when the specific model calls for it; message fields already have presence. For complex update APIs, you can combine **FieldMask** to describe exactly which fields need to be modified.

## 6. repeated, map, enum, oneof, and Nested Messages

**repeated** represents a list of 0 or more elements:

~~~proto
repeated string skills = 4;
~~~

Java provides methods such as **addSkills(...)**, **addAllSkills(...)**, **getSkillsList()**, and **getSkillsCount()**. An empty list is the default value; a repeated field by itself does not indicate whether the sender "set an empty list" or omitted the field. Element order is significant when you use a list.

**map** represents a key–value collection:

~~~proto
map<string, string> labels = 5;
~~~

Java provides **putLabels(...)**, **putAllLabels(...)**, **getLabelsMap()**, and **containsLabels(...)**. Map keys can only be an appropriate integer type, **bool**, or **string**; they cannot be **float**, **double**, **bytes**, enum, or message. Map values can be scalar, enum, or message (not directly another map). **Do not rely on map iteration order** as part of the protocol. When duplicate keys appear in incoming data, only one value takes effect.

**oneof** expresses "at most one of the choices" for the same group of data:

~~~proto
oneof contact {
  string email = 8;
  string phone = 9;
}
~~~

If the builder calls **setEmail(...)** and then **setPhone(...)**, the later choice replaces the earlier one. Java generates **getContactCase()** to determine which field is currently selected, even when the field value is set to its default value:

~~~java
Profile profile = Profile.newBuilder()
    .setId("p-42")
    .setEmail("")
    .build();

System.out.println(profile.getContactCase()); // EMAIL
System.out.println(profile.getEmail());       // ""
~~~

When no choice is set, **getContactCase()** returns **CONTACT_NOT_SET**. Do not place **repeated** or **map** directly inside a **oneof**. When processing encoded data that contains multiple oneof choices, the choice encountered last takes effect.

**Nested messages** help group data by context: **Profile.Address** has **city** and **country_code**. Field numbers **1** and **2** in **Address** do not conflict with field numbers **1** and **2** in **Profile**. Avoid nesting too deeply, which makes the contract hard to reuse or read.

**google.protobuf.Timestamp** is a *well-known type* used to transmit timestamps with consistent semantics instead of inventing ad-hoc time string conventions. The .proto file must include the corresponding **import** statement; the Java application uses **com.google.protobuf.Timestamp**.

## 7. Using Generated Java Classes

Once the project's Protobuf/gRPC code generation is configured, **java_multiple_files = true** gives access to classes such as **Profile**, **GetProfileRequest**, **GetProfileResponse**, and **ProfileServiceGrpc** in the chosen Java package.

Create a message using **Builder**:

~~~java
import com.example.profile.v1.Profile;
import com.example.profile.v1.ProfileStatus;

Profile profile = Profile.newBuilder()
    .setId("p-42")
    .setDisplayName("Nguyen An")
    .setNickname("") // Has presence even though it is an empty string.
    .addSkills("Java")
    .addSkills("gRPC")
    .putLabels("team", "platform")
    .setStatus(ProfileStatus.PROFILE_STATUS_ACTIVE)
    .setEmail("an@example.com")
    .setAddress(Profile.Address.newBuilder()
        .setCity("Ha Noi")
        .setCountryCode("VN")
        .build())
    .build();

System.out.println(profile.getDisplayName());  // Nguyen An
System.out.println(profile.getSkillsCount());   // 2
System.out.println(profile.hasNickname());      // true
System.out.println(profile.getContactCase());   // EMAIL
System.out.println(profile.hasAddress());       // true
~~~

**build()** creates an immutable message. To modify an already created instance, use **toBuilder()**, make changes, and call **build()** again. The proto field **display_name** typically becomes the Java getter **getDisplayName()** and builder setter **setDisplayName(...)**; Protobuf still uses field numbers to transmit data.

Byte-level communication relies on that very same schema:

~~~java
byte[] bytes = profile.toByteArray();
Profile decoded = Profile.parseFrom(bytes);

System.out.println(decoded.equals(profile)); // true
~~~

In gRPC, the framework handles request/response serialization. On the client side, you simply build **GetProfileRequest** and invoke the stub; on the server side, you receive the decoded **GetProfileRequest**. Example of server-side RPC handling:

~~~java
import com.example.profile.v1.GetProfileRequest;
import com.example.profile.v1.GetProfileResponse;
import com.example.profile.v1.Profile;
import com.example.profile.v1.ProfileServiceGrpc;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class ProfileEndpoint
        extends ProfileServiceGrpc.ProfileServiceImplBase {

    @Override
    public void getProfile(GetProfileRequest request,
                           StreamObserver<GetProfileResponse> observer) {
        String id = request.getProfileId();
        if (id.isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("profile_id must not be empty")
                .asRuntimeException());
            return;
        }

        Profile profile = Profile.newBuilder()
            .setId(id)
            .setDisplayName("Nguyen An")
            .build();

        observer.onNext(GetProfileResponse.newBuilder()
            .setProfile(profile)
            .build());
        observer.onCompleted();
    }
}
~~~

**ProfileEndpoint** must be registered as a gRPC service according to the bean/binding mechanism of the Spring gRPC configuration in use. This example illustrates reading a field from a request, checking business rules, building a response, and returning **INVALID_ARGUMENT** when input is invalid; security, metadata, deadlines, streaming, and interceptors are handled in other layers/topics.

## 8. Evolving Schemas While Maintaining Compatibility

In distributed systems, clients and servers may have different versions deployed simultaneously. Therefore, changes must be evaluated against the wire format, generated Java code, and any JSON systems in use.

| Change | Assessment and approach |
| --- | --- |
| Adding a new field with an **unused number** | Usually wire-compatible: older versions ignore unknown fields; newer versions must handle the case where the field is absent. |
| Removing a field | Retire that number and add **reserved** for the old number/name. Do not reassign the number to other data. |
| Changing the number of an active field | **Unsafe**: the receiver may interpret it as another field or fail to receive the value. |
| Changing a field's type | May change the wire type or data semantics; only perform after a specific compatibility evaluation—usually better to create a new field. |
| Renaming a field | Can remain binary-compatible if number/type stay the same, but may break Java APIs and field names in JSON exchange. |
| Moving a regular field into a **oneof**, or moving fields between oneofs | Risks data loss or changing presence semantics; must be evaluated carefully with already deployed messages. |
| Adding an enum value | Older receivers may encounter an unrecognized enum number; must have a branch handling unexpected values. Do not reuse retired enum numbers. |

Proto3 usually ignores unknown fields when reading; whether unknown fields are preserved depends on the data path and how messages are re-serialized. In particular, intermediaries converting to JSON or performing manual mapping can lose unknown information, so do not assume every forwarding path preserves them.

For example, a new version needs to add an avatar image:

~~~proto
message Profile {
  // ... fields 1 to 10 remain unchanged ...
  string avatar_url = 12;
  reserved 11, 15 to 18;
  reserved "legacy_bio";
}
~~~

Since field **11** existed historically, keep **reserved 11** and assign **12** to **avatar_url**. Do not attempt to assign a new meaning to number 11, even when the current codebase no longer uses the old field.

## 9. Common Mistakes and How to Self-Check

- **Forgetting the meaning of default values:** **getId() == ""** does not prove the client intentionally sent an empty string. Check business requirements or use explicit presence when appropriate.
- **Treating scalar fields as required:** proto3 has no **required**; validate **id.isBlank()**, length limits, enum ranges, and data validity yourself on the server.
- **Using repeated to express partial updates:** an empty list and an omitted list cannot be distinguished using a repeated field alone; design an additional update mechanism if needed.
- **Forgetting the unspecified enum case:** follow the convention of making element 0 **UNSPECIFIED** and include a branch handling unknown values when interoperating across versions.
- **Changing numbers when renaming fields:** the field number is the wire-level identity; changing a name and changing a number have very different impacts.
- **Relying on map ordering:** maps are for key-based lookup; if ordering has business meaning, use a **repeated** message containing key–value pairs.
- **Accessing a sub-message without checking presence:** use **hasAddress()** or **hasUpdatedAt()** before assuming the nested data was actually sent.

A small unit test should verify both value and presence:

~~~java
import static org.junit.jupiter.api.Assertions.*;

Profile source = Profile.newBuilder()
    .setId("p-42")
    .setNickname("")
    .setPhone("0900000000")
    .build();

Profile result = Profile.parseFrom(source.toByteArray());

assertEquals("p-42", result.getId());
assertTrue(result.hasNickname());
assertEquals("", result.getNickname());
assertEquals(Profile.ContactCase.PHONE, result.getContactCase());
assertFalse(result.hasAddress());
~~~

Similarly, test a request **without setting nickname** to confirm **hasNickname() == false**, and test old/new schema versions with added fields to catch compatibility issues before deploying client and server independently.

## 10. Practice Exercises

Extend the **Profile** contract without modifying any existing field numbers:

1. Add **optional string bio = 13;** to distinguish not updating the bio from intentionally setting an empty bio.
2. Add **repeated string certifications = 14;** to store multiple certifications. Observe the generated Java builder/list methods.
3. Write a **GetProfileResponse** containing a **Profile**, serialize and parse it back, and verify **hasNickname()**, **getContactCase()**, and **getCertificationsList()** after the round-trip.
4. Simulate an update request with **bio** absent and a request setting **bio = ""**; explain why the server must handle them differently.
5. Explain why number **11** must not be used for a new field, even though that number no longer appears among the active fields.

**Expected outcome:** you can distinguish three independent yet closely related concepts: **field names** help developers use the API, **field numbers** protect data exchange across versions, and **presence** determines whether the server knows if the sender actually supplied a value. This is the foundation for designing stable gRPC requests/responses before adding streaming, interceptors, TLS, or reliability policies.
