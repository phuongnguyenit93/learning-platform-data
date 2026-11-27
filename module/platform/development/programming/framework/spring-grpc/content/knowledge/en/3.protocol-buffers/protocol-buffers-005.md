# Optional Fields in proto3

## Learning Objectives

After this lesson, you will be able to:

- Explain what **field presence** is and distinguish an **unsent** field from a field **set to its default value** in Protocol Buffers proto3.
- Declare **optional** on scalar and enum fields, understanding the differences from regular fields, message fields, **oneof**, **repeated**, and **map**.
- Use the **hasXxx()**, **getXxx()**, **setXxx()**, and **clearXxx()** methods of Protobuf Java to write accurate handling logic.
- Design partial-update requests for Spring gRPC services, including intentionally setting an empty string, 0, or **false**.
- Verify binary serialization results, ProtoJSON, message merging, and compatibility across schema versions.

## 1. Why Is optional Needed in Spring gRPC Applications?

In **SPRING_GRPC**, clients and servers exchange requests/responses defined by a **Protocol Buffers** contract. The **protoc** tool generates Java classes from the .proto file; the gRPC plugin generates stubs and base classes for unary or streaming RPC methods. The Spring application processes decoded messages and applies business rules before returning results.

Suppose a client sends a command to edit profile information:

- Does not send **display_name**: keep the current name.
- Sends **display_name = ""**: intentionally clear the display name (if business rules permit).
- Does not send **is_public**: keep the current visibility setting.
- Sends **is_public = false**: switch the profile to private mode.

If the server only calls **getDisplayName()** or **getIsPublic()** on regular proto3 scalar fields, it cannot tell whether the sender intentionally set an empty string/**false**, or omitted the field completely. This is the **field presence** problem.

**Optional** in proto3 lets the server know whether a scalar/enum field has been set, even when the set value equals the default. This is especially important for **PATCH** requests, partial updates, configuration options, user details, and data where 0 carries business meaning.

## 2. Distinguishing Value and Presence

Consider the following schema:

~~~proto
syntax = "proto3";

message UpdateProfileRequest {
  string profile_id = 1;
  string display_name = 2;
  optional bool is_public = 3;
}
~~~

**display_name** is a scalar with **implicit presence**. When calling **getDisplayName()**, Java returns an empty string if the field has not been set, and also returns an empty string if the field was set to an empty string. The generated Java API does not include **hasDisplayName()** for this declaration style.

**is_public** is a scalar with **explicit presence** thanks to the **optional** label. Java generates:

- **getIsPublic()**: returns the boolean value, defaulting to **false** if the field is absent.
- **hasIsPublic()**: **true** if the sender or builder actually set the field, even when set to **false**.
- **setIsPublic(boolean)** on the builder: sets the value and marks the field present.
- **clearIsPublic()** on the builder: clears presence, causing **hasIsPublic()** to become **false**.

| Case | Value read | Can you tell if the field was set? |
| --- | --- | --- |
| **string display_name** not sent | **""** | No, due to implicit presence. |
| **string display_name** set to **""** | **""** | Indistinguishable from not sent. |
| **optional bool is_public** not sent | **false** | Yes: **hasIsPublic() == false**. |
| **optional bool is_public** set to **false** | **false** | Yes: **hasIsPublic() == true**. |
| **optional bool is_public** set to **true** | **true** | Yes: **hasIsPublic() == true**. |

**A default value does not mean no data was sent.** With optional, value and presence are two properties that must be checked separately.

## 3. optional Syntax and Allowed Types

Proto3 declares optional by placing the **optional** keyword before the field type:

~~~proto
syntax = "proto3";

package learning.profile.v1;

option java_package = "com.example.profile.v1";
option java_multiple_files = true;

enum Visibility {
  VISIBILITY_UNSPECIFIED = 0;
  VISIBILITY_PUBLIC = 1;
  VISIBILITY_PRIVATE = 2;
}

message ProfileSettings {
  optional string nickname = 1;
  optional bool notifications_enabled = 2;
  optional int32 max_sessions = 3;
  optional int64 storage_limit_bytes = 4;
  optional double score_threshold = 5;
  optional Visibility visibility = 6;
  optional bytes avatar_hash = 7;
}
~~~

All fields above have **hasXxx()** when Java code is generated. The optional label also works with many other proto3 scalar types such as **uint32**, **sint64**, and **fixed32**.

**Do not use optional for repeated or map:**

~~~proto
message InvalidSettings {
  // Invalid syntax:
  // optional repeated string tags = 1;
  // optional map<string, string> labels = 2;
}
~~~

Empty lists and maps cannot express the difference between **not sent** and **intentionally sending an empty structure** using repeated/map alone. If the problem requires that distinction, design an additional mechanism to express the update action, such as a wrapper message, **oneof**, or **FieldMask**.

**Proto3 has no required label.** The optional label does not mean a field must be sent; rather, it expresses that a field may be absent **and** the receiver can detect that fact. Constraints such as profile_id must be non-empty, session counts must be positive, or nickname must not exceed a length limit must be enforced at the business layer.

### Message Fields Already Have Presence

With a nested message:

~~~proto
message Address {
  string city = 1;
}

message UpdateAddressRequest {
  string profile_id = 1;
  Address address = 2;
}
~~~

Generated Java includes **hasAddress()** even without adding **optional**, because message fields in proto3 already have explicit presence. **getAddress()** returns a default instance when the field is absent; call **hasAddress()** if you need to know whether the client actually sent an address.

Writing **optional Address address = 2;** in proto3 brings no new API-level presence benefit: for regular message fields, presence already exists. To model **multiple data type choices**, use **oneof** rather than adding optional to every choice.

## 4. Default Values of optional in Java

An absent optional scalar field still returns a default value when calling its getter:

| proto3 type | Default value when unset | Presence API |
| --- | --- | --- |
| **optional string** | **""** | **hasXxx()** |
| **optional bool** | **false** | **hasXxx()** |
| **optional int32**, **optional int64** and related integer types | **0** | **hasXxx()** |
| **optional float**, **optional double** | **0.0** | **hasXxx()** |
| **optional bytes** | **ByteString.EMPTY** | **hasXxx()** |
| **optional enum** | Enum value numbered **0** | **hasXxx()** |

Example:

~~~java
import com.example.profile.v1.ProfileSettings;

ProfileSettings untouched = ProfileSettings.newBuilder().build();

System.out.println(untouched.getNickname());               // ""
System.out.println(untouched.hasNickname());               // false
System.out.println(untouched.getNotificationsEnabled());  // false
System.out.println(untouched.hasNotificationsEnabled());  // false
System.out.println(untouched.getMaxSessions());           // 0
System.out.println(untouched.hasMaxSessions());           // false
~~~

When the builder invokes a setter, the field becomes present even if set to the default value:

~~~java
ProfileSettings explicitDefaults = ProfileSettings.newBuilder()
    .setNickname("")
    .setNotificationsEnabled(false)
    .setMaxSessions(0)
    .build();

System.out.println(explicitDefaults.hasNickname());             // true
System.out.println(explicitDefaults.hasNotificationsEnabled()); // true
System.out.println(explicitDefaults.hasMaxSessions());          // true
~~~

Do not use **getMaxSessions() == 0** to conclude the field is absent. If 0 is a valid action, such as disabling access, doing so can corrupt data updates.

## 5. has, set, clear, and toBuilder

The Protobuf Java builder provides operations to set and clear presence. A message after **build()** is immutable; to modify it, create a new builder or use **toBuilder()**.

~~~java
ProfileSettings original = ProfileSettings.newBuilder()
    .setNickname("An")
    .setNotificationsEnabled(true)
    .build();

ProfileSettings cleared = original.toBuilder()
    .clearNickname()
    .setNotificationsEnabled(false)
    .build();

System.out.println(original.hasNickname());              // true
System.out.println(original.getNickname());              // "An"

System.out.println(cleared.hasNickname());               // false
System.out.println(cleared.getNickname());               // ""
System.out.println(cleared.hasNotificationsEnabled());   // true
System.out.println(cleared.getNotificationsEnabled());   // false
~~~

**clearNickname()** removes the field's presence; it does not mean setting nickname to an empty string. If a business operation needs to **erase the stored value**, a request can adopt the convention **setNickname("")** to indicate clearing; whereas **clearNickname()** on a request builder creates the case of **not sending nickname**.

Do not pass **null** to scalar Java setters generated by protoc to express absence. Use **clearXxx()** or omit calling the setter. Conventions using **null** in other Java DTO layers must be explicitly converted before building a Protobuf message.

## 6. How Does optional Change Binary Content?

Field number and wire type determine a field's tag during serialization. With scalars **without presence**, default values are usually omitted during encoding; with **optional**, a field set to its default value is still encoded to preserve presence information.

Standalone example:

~~~proto
syntax = "proto3";

message PresenceSample {
  optional string title = 1;
  optional bool enabled = 2;
  optional int32 count = 3;
}
~~~

When creating a message with all three fields set to their default values:

~~~java
PresenceSample sample = PresenceSample.newBuilder()
    .setTitle("")
    .setEnabled(false)
    .setCount(0)
    .build();

byte[] bytes = sample.toByteArray();
// One valid encoding:
// 0A 00 10 00 18 00
~~~

Explanation:

| Bytes | Meaning |
| --- | --- |
| **0A 00** | Field **1**, wire type **2** (length-delimited), string length **0**. |
| **10 00** | Field **2**, wire type **0** (varint), boolean value **false**. |
| **18 00** | Field **3**, wire type **0** (varint), integer value **0**. |

If **no fields are set**, the message can be encoded as an empty byte array. In practice, Protobuf does not require fields to appear in declaration order; when testing, parse or compare field semantics rather than assuming every serializer produces the exact same byte order.

After parsing:

~~~java
PresenceSample restored = PresenceSample.parseFrom(bytes);

System.out.println(restored.hasTitle());   // true
System.out.println(restored.hasEnabled()); // true
System.out.println(restored.hasCount());   // true
~~~

**Optional does not make a field required and does not change the scalar type's wire type.** It adds presence semantics, especially when the value equals the default.

## 7. Designing Partial-Update Requests for Spring gRPC

Suppose a profile has a display name, public visibility mode, and maximum login count. Contract:

~~~proto
syntax = "proto3";

package learning.profile.v1;
option java_package = "com.example.profile.v1";
option java_multiple_files = true;

message UpdateProfileRequest {
  string profile_id = 1;
  optional string display_name = 2;
  optional bool is_public = 3;
  optional int32 max_logins = 4;
}

message UpdateProfileResponse {
  bool updated = 1;
}

service ProfileService {
  rpc UpdateProfile(UpdateProfileRequest)
      returns (UpdateProfileResponse);
}
~~~

Each optional field captures the difference between **do not request an update** and **request an update with a specific value**. For example, a client wants to keep the name, turn off public visibility, and set the limit to 0:

~~~java
UpdateProfileRequest request = UpdateProfileRequest.newBuilder()
    .setProfileId("p-42")
    .setIsPublic(false)
    .setMaxLogins(0)
    .build();

System.out.println(request.hasDisplayName()); // false
System.out.println(request.hasIsPublic());     // true
System.out.println(request.getIsPublic());     // false
System.out.println(request.hasMaxLogins());    // true
System.out.println(request.getMaxLogins());    // 0
~~~

The server checks presence **before** updating:

~~~java
// Example business logic; repository is assumed to provide profile lookup/save.
void applyUpdate(UpdateProfileRequest request, ProfileEntity entity) {
    if (request.hasDisplayName()) {
        entity.setDisplayName(request.getDisplayName());
    }
    if (request.hasIsPublic()) {
        entity.setPublic(request.getIsPublic());
    }
    if (request.hasMaxLogins()) {
        entity.setMaxLogins(request.getMaxLogins());
    }
}
~~~

Here **ProfileEntity** is an illustrative domain type, not a generated Protobuf class. Entity setters must obey the real system's data rules.

If code only wrote **if (request.getIsPublic())**, setting **false** would be ignored. If code unconditionally wrote **entity.setDisplayName(request.getDisplayName())**, a request updating only privacy would accidentally erase the old name. Checking **hasXxx()** solves both bugs.

### Unary RPC Implementation Form

A simple server snippet illustrating reading presence and returning gRPC statuses:

~~~java
import com.example.profile.v1.ProfileServiceGrpc;
import com.example.profile.v1.UpdateProfileRequest;
import com.example.profile.v1.UpdateProfileResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class ProfileEndpoint
        extends ProfileServiceGrpc.ProfileServiceImplBase {

    private final ProfileRepository repository;

    public ProfileEndpoint(ProfileRepository repository) {
        this.repository = repository;
    }

    @Override
    public void updateProfile(
            UpdateProfileRequest request,
            StreamObserver<UpdateProfileResponse> observer) {

        if (request.getProfileId().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("profile_id must not be empty")
                .asRuntimeException());
            return;
        }

        ProfileEntity entity = repository.findById(request.getProfileId());
        if (entity == null) {
            observer.onError(Status.NOT_FOUND
                .withDescription("profile not found")
                .asRuntimeException());
            return;
        }

        if (request.hasDisplayName()) {
            entity.setDisplayName(request.getDisplayName());
        }
        if (request.hasIsPublic()) {
            entity.setPublic(request.getIsPublic());
        }
        if (request.hasMaxLogins()) {
            entity.setMaxLogins(request.getMaxLogins());
        }

        repository.save(entity);
        observer.onNext(UpdateProfileResponse.newBuilder()
            .setUpdated(true)
            .build());
        observer.onCompleted();
    }
}
~~~

**ProfileRepository** and **ProfileEntity** here are application components you implement yourself. Register **ProfileEndpoint** with the server according to your Spring gRPC integration mechanism; the example focuses solely on optional semantics and does not cover server configuration or transaction management.

**Deadlines**, metadata, interceptors, TLS, retries, and streaming are other aspects of gRPC: they do not change how **hasXxx()** works, though a production system still must enforce update permissions, input validation, persistence transactions, and RPC error handling.

## 8. How Does optional Differ from oneof?

**Optional** expresses a single field that may or may not be sent. **Oneof** expresses a group of choices where at most one choice can be set at a time.

~~~proto
message ContactUpdate {
  string profile_id = 1;

  oneof channel {
    string email = 2;
    string phone = 3;
  }
}
~~~

In Java:

~~~java
ContactUpdate update = ContactUpdate.newBuilder()
    .setEmail("")
    .build();

System.out.println(update.getChannelCase()); // EMAIL
System.out.println(update.getEmail());       // ""
~~~

Oneof has its own presence by selected branch. If the builder calls **setEmail(...)** then **setPhone(...)**, the later branch replaces the earlier one. Use **optional** when multiple fields must be updated **independently** in one request; use **oneof** when only **one** option may be chosen, such as updating email *or* phone number per the business model.

Do not declare **optional** directly inside a oneof branch: oneof syntax already expresses presence. For scalar types needing independent presence, optional is usually cleaner than creating multiple single-field oneofs.

## 9. optional and Well-Known Wrapper Types

Before proto3 supported optional for scalars, a common way to express presence was **wrapper messages** like **google.protobuf.StringValue** or **google.protobuf.BoolValue**:

~~~proto
syntax = "proto3";
import "google/protobuf/wrappers.proto";

message OldStyleSettings {
  google.protobuf.StringValue nickname = 1;
  google.protobuf.BoolValue enabled = 2;
}
~~~

Wrappers are **message fields**, so they have **hasNickname()** and **hasEnabled()**. For new proto3 schemas using binary APIs, **optional string** and **optional bool** are usually simpler and avoid extra wrapper message layers.

Do not replace an already released wrapper with an optional scalar on **the same field number** just because both have presence. A wrapper's wire encoding is a nested message (length-delimited), whereas optional bool is a varint, and the Java getter types also differ. That is a significant wire change—use a new field or build an appropriate migration plan.

If an API must distinguish multiple states like **no change**, **set value**, and **clear data** where an empty string is still a valid value, a standalone optional is not enough to express every action. You can use a **oneof** containing command messages, an explicit clear flag, or a **FieldMask** with documented semantics.

## 10. optional in ProtoJSON

When converting a message to ProtoJSON with **JsonFormat**, a scalar field with explicit presence set to its default value is still emitted to preserve the fact that it was set. For example:

~~~proto
message Preferences {
  optional string nickname = 1;
  optional bool enabled = 2;
}
~~~

Cases:

| Message | Typical JSON |
| --- | --- |
| No fields set | **{}** |
| nickname set to empty string | **{"nickname":""}** |
| enabled set to false | **{"enabled":false}** |
| Both set | **{"nickname":"","enabled":false}** |

In Java:

~~~java
import com.google.protobuf.util.JsonFormat;

Preferences preferences = Preferences.newBuilder()
    .setNickname("")
    .setEnabled(false)
    .build();

String json = JsonFormat.printer().print(preferences);
System.out.println(json);

Preferences.Builder parsed = Preferences.newBuilder();
JsonFormat.parser().merge(json, parsed);
System.out.println(parsed.hasNickname()); // true
System.out.println(parsed.hasEnabled());  // true
~~~

**Note on null:** For regular optional scalar fields, JSON **null** is accepted by the ProtoJSON parser as **field not set**. Therefore, do not use JSON null to express updating to an empty string or requesting deletion when the contract has not explicitly defined it:

~~~json
{
  "nickname": null
}
~~~

This payload is not equivalent to **{"nickname":""}** in presence. When partial updates through a JSON gateway are required, agree on a policy for missing fields and null, and test against the exact parser used by the gateway.

Do not equate **ProtoJSON** with JSON automatically generated by a library like Jackson from Protobuf Java objects; general mapping mechanisms can produce different results. In applications, use **JsonFormat** when official compatibility with the Protobuf JSON format is required.

## 11. Merge Semantics: Why Does optional Affect Updates?

In Protobuf, **merge** combines messages of the same type. When a scalar field has **implicit presence**, a default value is typically not treated as set data to merge into the destination. With **optional**, a default value still has presence and can therefore overwrite a previous value.

Example:

~~~proto
message Patch {
  optional int32 retry_limit = 1;
}
~~~

~~~java
Patch original = Patch.newBuilder()
    .setRetryLimit(5)
    .build();

Patch resetToZero = Patch.newBuilder()
    .setRetryLimit(0)
    .build();

Patch merged = original.toBuilder()
    .mergeFrom(resetToZero)
    .build();

System.out.println(merged.hasRetryLimit()); // true
System.out.println(merged.getRetryLimit()); // 0
~~~

If **retry_limit** were only an **int32** without optional, a source message with value 0 could not carry explicit presence as above; merging could leave 5 intact. This is why explicit presence matters for operations that reset configurations to **0**, **false**, or an empty string.

For **message fields**, merging combines submessage contents rather than replacing the whole submessage. For **repeated fields**, merging typically appends elements. Thus, do not assume message merging is a complete business PATCH operation for all field types; design dedicated update logic if you need to replace lists, delete nested data, or enforce domain constraints.

## 12. FieldMask When optional Is Not Enough

Google Protobuf provides the well-known type **google.protobuf.FieldMask** to explicitly list which fields are being updated. This mechanism is particularly suitable when a request contains deeply nested messages or needs to reset default values while bounding the scope of changes.

Example contract:

~~~proto
syntax = "proto3";
import "google/protobuf/field_mask.proto";

message UserProfile {
  string display_name = 1;
  bool is_public = 2;
  repeated string labels = 3;
}

message PatchProfileRequest {
  string profile_id = 1;
  UserProfile profile = 2;
  google.protobuf.FieldMask update_mask = 3;
}
~~~

A client wanting to change public status can send **profile.is_public = false**, while putting the path **is_public** into **update_mask**. When absent from the mask, a field is not updated even if its getter returns a default value.

Here the server must define and execute patch rules for fields in the mask—especially how to replace repeated fields, handle submessages, and handle invalid paths. **FieldMask** does not call repositories or replace data by itself; it is part of the contract for the application to interpret.

Choose the design based on requirements:

| Situation | Usually suitable representation |
| --- | --- |
| Independently updating a few scalar fields | **optional scalar** |
| Choosing one of several alternatives | **oneof** |
| Updating multiple fields/nested fields by path | **FieldMask** |
| Distinguishing setting a value from a separate delete command | **oneof** with explicit commands, or a contract with update_mask and clear rules |
| Lists requiring add/remove/replace-all operations | Dedicated RPC/command or update_mask with clear merge/replace rules |

## 13. optional and Multi-Version Compatibility

When adding a new field:

~~~proto
message User {
  string id = 1;
  optional string nickname = 2;
}
~~~

Old clients do not know field **2** and can skip it when reading binary Protobuf. The new server must accept requests from old clients without nickname; you cannot require every request to immediately include the new field just because the schema was updated.

When changing an existing **string nickname = 2** field to **optional string nickname = 2**, the field number and wire type do not change. This is generally compatible with respect to the **binary format**. However:

- Old versions with implicit presence normally **do not serialize** the default value **""**. New versions cannot infer whether an old sender intentionally set an empty string or not.
- New versions with optional can serialize **""** to record presence. Old readers read the string value but lack the **hasNickname()** API, and when re-serializing may drop the default value.
- Merging, message equality, and business updates can behave differently because **present default** differs from **absent** in the new version.
- Code generators/language runtimes must be recent enough to understand proto3 optional syntax and provide the corresponding presence API.

Therefore, do not just check whether **parseFrom(...)** throws an error. Test **absent**, **present with default**, and **present with non-default** data in both directions between old and new versions.

For a Spring gRPC service running multiple instances during rolling deployments, a new client might call an old server or vice versa. If new logic depends on a newly added field, you must have a strategy for tolerating the missing field during transition. This applies to both unary and streaming RPCs, differing only in how requests arrive over time.

## 14. Testing Field Presence and Round-Trip

To ensure optional works according to contract, test at minimum:

1. Field not set: **hasXxx()** returns **false** and getter returns default value.
2. Field set to default: **hasXxx()** returns **true**, value still equals default.
3. Field set to non-default: both presence and value are accurate.
4. **clearXxx()** on builder: removes presence.
5. Binary and ProtoJSON serialize/parse: preserves presence when the field is set to default.
6. Merging two messages: a default value with presence is still applied.
7. gRPC integration: the server leaves unrequested fields untouched and accurately updates fields set to **false**, **0**, or **""**.

JUnit 5 example using **ProfileSettings** from section 3:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.profile.v1.ProfileSettings;
import com.google.protobuf.util.JsonFormat;
import org.junit.jupiter.api.Test;

class ProfileSettingsTest {

    @Test
    void preservesExplicitDefaultsAcrossBinaryRoundTrip() throws Exception {
        ProfileSettings source = ProfileSettings.newBuilder()
            .setNickname("")
            .setNotificationsEnabled(false)
            .setMaxSessions(0)
            .build();

        ProfileSettings decoded =
            ProfileSettings.parseFrom(source.toByteArray());

        assertTrue(decoded.hasNickname());
        assertEquals("", decoded.getNickname());
        assertTrue(decoded.hasNotificationsEnabled());
        assertFalse(decoded.getNotificationsEnabled());
        assertTrue(decoded.hasMaxSessions());
        assertEquals(0, decoded.getMaxSessions());
    }

    @Test
    void distinguishesAbsentAndClearedValues() {
        ProfileSettings absent = ProfileSettings.newBuilder().build();
        ProfileSettings present = absent.toBuilder()
            .setNickname("")
            .build();
        ProfileSettings cleared = present.toBuilder()
            .clearNickname()
            .build();

        assertFalse(absent.hasNickname());
        assertTrue(present.hasNickname());
        assertFalse(cleared.hasNickname());
    }

    @Test
    void preservesExplicitDefaultInProtoJson() throws Exception {
        ProfileSettings source = ProfileSettings.newBuilder()
            .setNotificationsEnabled(false)
            .build();

        String json = JsonFormat.printer().print(source);
        assertTrue(json.contains("\"notificationsEnabled\""));

        ProfileSettings.Builder parsed = ProfileSettings.newBuilder();
        JsonFormat.parser().merge(json, parsed);
        assertTrue(parsed.hasNotificationsEnabled());
        assertFalse(parsed.getNotificationsEnabled());
    }
}
~~~

In real integration tests, you can use gRPC in-process or test infrastructure appropriate for your Spring gRPC stack, and invoke RPCs via a client stub. Testing gRPC statuses on invalid data (such as **INVALID_ARGUMENT**) is separate from testing field presence. The sample tests above illustrate API usage and do not replace running the actual project's build and test suite.

## 15. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using **getIsPublic() == false** to infer the client omitted the field | Explicit request to turn off public mode is ignored | Check **hasIsPublic()** |
| Always updating every field from request getters | Overwrites existing data because getters return defaults | Only update fields with presence or listed in FieldMask |
| Calling **clearNickname()** to express a delete-nickname command | Request becomes "nickname not sent" | Use **setNickname("")** if contract defines empty as delete, or a dedicated delete command |
| Thinking optional means required input | Server accepts invalid missing business data | Validate required rules at the application layer |
| Using **optional repeated** or **optional map** | Invalid schema | Use wrapper message/FieldMask/explicit update commands |
| Assuming JSON **null** equals an empty string | Update or clear signal is lost | Check ProtoJSON rules, absence conventions, and null handling |
| Changing a wrapper message to an optional scalar on the same number | Risks breaking wire compatibility | Create a new field or follow a migration plan |
| Only testing serialize and parse with the same schema | Misses bugs when client/server use different versions | Run fixtures and readers across at least two versions |
| Assuming mergeFrom performs PATCH for every field type | Incorrect handling of nested messages and repeated fields | Design update/FieldMask logic per data type |

## 16. Practice Exercise

A user configuration service needs to support these operations:

- Change the display name, allowing setting the name to an empty string.
- Enable or disable notifications.
- Set the maximum number of login sessions, including 0 (interpreted as disabling access).
- Ignore fields the client does not want to update.

Tasks:

1. Write an **UpdateSettingsRequest** message with a **user_id** field and three corresponding optional scalars.
2. Build a request that only **turns off notifications** and **sets max_sessions = 0**; verify **hasNotificationsEnabled()** and **hasMaxSessions()** are both **true**, while **hasDisplayName()** is **false**.
3. Serialize the request to bytes, parse it back, and verify presence is preserved.
4. Print ProtoJSON using JsonFormat, observe keys containing **false** and **0**; try parsing JSON where a field has value **null** to analyze the difference.
5. Write an **applyUpdate** function that only modifies the entity for fields that are present.
6. Create a fixture from a schema version without **optional** for an existing field, then try reading and re-serializing it with the new version to evaluate presence differences.

Suggested schema:

~~~proto
syntax = "proto3";

message UpdateSettingsRequest {
  string user_id = 1;
  optional string display_name = 2;
  optional bool notifications_enabled = 3;
  optional int32 max_sessions = 4;
}
~~~

If the application also needs to distinguish a **delete command** from **setting a valid empty value**, propose extending the contract with a **oneof** containing separate operations or adding a **FieldMask** with clear update rules.

## 17. Key Takeaways

- **Optional in proto3** for scalars/enums provides **explicit presence**: knowing whether a field was set, even when equal to its default value.
- Getters still return defaults when the field is absent; to determine presence, use **hasXxx()**.
- Builder **setXxx(default)** marks the field present, while **clearXxx()** removes presence.
- Message fields inherently have presence; repeated/map do not use optional; oneof expresses mutually exclusive choices.
- Optional helps build simple PATCHes, while complex deletions, lists, and nested messages may require **FieldMask** or dedicated update commands.
- When evolving schemas, test binary, ProtoJSON, merge semantics, and client/server compatibility—not just compilation.

Using optional fields properly makes Spring gRPC requests/responses safer: the server distinguishes **no update** from **updating to a default value**, preventing accidental data loss when serving multiple client versions in unary and streaming RPC systems.
