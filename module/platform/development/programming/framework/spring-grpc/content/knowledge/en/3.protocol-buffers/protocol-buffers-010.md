# Oneof and Field Selection

## Learning Objectives

After this lesson, you will be able to:

- Use **oneof** to describe a group of fields where at most one choice is set at a time.
- Declare choices using scalars, enums, or nested messages in proto3.
- Use Java APIs such as **getXxxCase()**, **hasXxx()**, **setXxx()**, and **clearXxx()** to read and update selections.
- Understand oneof presence when a field holds a default value, and how oneof is represented in binary Protobuf/ProtoJSON.
- Design gRPC requests with multiple alternative data forms, while evaluating compatibility constraints when modifying a oneof.

## 1. When Is oneof Needed?

In **SPRING_GRPC** contracts, a request sometimes has multiple ways to express the same intent. For example, a payment method can be a card or a bank transfer; a search filter can query by ID or by email; a contact destination can be a phone number or an email address.

If declared as independent fields:

~~~proto
message PaymentRequest {
  CardPayment card = 1;
  BankTransfer bank_transfer = 2;
}
~~~

a message can contain both card and bank_transfer simultaneously, or neither field. The server would have to decide which cases are valid and resolve conflicts itself.

**oneof** directly expresses that a group of alternatives has at most one field set:

~~~proto
message PaymentRequest {
  oneof payment_method {
    CardPayment card = 1;
    BankTransfer bank_transfer = 2;
  }
}
~~~

A message can choose no method at all, or choose one of the methods. If the client sets card and then sets bank_transfer, the card selection is replaced. Oneof lets the schema and Java API express this mutual-exclusion rule instead of leaving every server to infer it.

## 2. Declaring oneof in proto3

The syntax consists of a group name and member fields:

~~~proto
syntax = "proto3";

package learning.payment.v1;

option java_package = "com.example.payment.v1";
option java_multiple_files = true;

message CardPayment {
  string token = 1;
  string last_four = 2;
}

message BankTransfer {
  string bank_code = 1;
  string account_reference = 2;
}

message PaymentRequest {
  string order_id = 1;

  oneof payment_method {
    CardPayment card = 2;
    BankTransfer bank_transfer = 3;
  }
}
~~~

In the schema:

- **payment_method** is the oneof group name, not a separately transmitted field.
- **card** and **bank_transfer** are member fields, each still retaining its own field number.
- Members can be scalars, enums, or messages.
- A oneof can have many options, yet at most one option is present at any given time.
- Field numbers still follow standard Protobuf rules: unique within the message, never 0, and never reusing released numbers.

Oneof does not create an enclosing wrapper message on the binary wire. The selected field is encoded like a regular Protobuf field using its own field number and wire type.

## 3. Which Field Types Can Live Inside a oneof?

A oneof can contain:

- Scalars such as **string**, **bool**, **int32**, **bytes**.
- Enums.
- Messages, including nested messages and well-known types.

You cannot declare **repeated** or **map** directly as a oneof member. Nor can you place the **optional** label before a field inside a oneof; the oneof itself already manages presence of the selection.

Valid example:

~~~proto
syntax = "proto3";

package learning.search.v1;
option java_package = "com.example.search.v1";
option java_multiple_files = true;

message SearchCriterion {
  oneof value {
    string text = 1;
    int64 numeric_id = 2;
    bool active = 3;
  }
}
~~~

If an option needs to be a list, wrap the list in a message:

~~~proto
message StringValues {
  repeated string values = 1;
}

message Filter {
  oneof criterion {
    string exact_value = 1;
    StringValues any_of = 2;
  }
}
~~~

Here **any_of** is a message field inside the oneof; the repeated field lives inside StringValues. This wrapping approach is also useful when an option needs extra metadata or accompanying attributes.

## 4. Java API: Determining the Current Selection

For the **payment_method** oneof, generated Java code includes a case enum indicating the active choice. The case enum name is derived from the group name, such as **PaymentMethodCase**.

Main APIs:

| API | Meaning |
| --- | --- |
| **getPaymentMethodCase()** | Returns the current selection or **PAYMENT_METHOD_NOT_SET**. |
| **getCard()** | Returns the CardPayment message; returns default instance if not selected. |
| **getBankTransfer()** | Returns the BankTransfer message; returns default instance if not selected. |
| **hasCard()**, **hasBankTransfer()** | Checks whether the corresponding member is currently selected. |
| **clearPaymentMethod()** on builder | Clears the current selection of the entire group. |

Exact case constant names are determined by the code generator; in standard Protobuf Java, the case enum has values matching the field names and a value ending in **_NOT_SET**.

~~~java
import com.example.payment.v1.PaymentRequest;
import com.example.payment.v1.CardPayment;

PaymentRequest noMethod = PaymentRequest.newBuilder()
    .setOrderId("O-42")
    .build();

System.out.println(noMethod.getPaymentMethodCase());
// PAYMENT_METHOD_NOT_SET

PaymentRequest cardRequest = PaymentRequest.newBuilder()
    .setOrderId("O-42")
    .setCard(CardPayment.newBuilder()
        .setToken("tok_123")
        .setLastFour("4242"))
    .build();

System.out.println(cardRequest.getPaymentMethodCase()); // CARD
System.out.println(cardRequest.hasCard());              // true
~~~

In the example above, CardPayment and BankTransfer are top-level messages so Java imports them as separate classes. If declared nested inside PaymentRequest, the corresponding Java types would be accessed through the enclosing class.

## 5. Default Values Still Have Presence Inside oneof

A selected scalar member of a oneof still has presence, even when its value equals the default:

~~~proto
message SearchCriterion {
  oneof value {
    string text = 1;
    int32 numeric_id = 2;
    bool active = 3;
  }
}
~~~

The following three messages share identical default getter outputs in some cases, yet have different cases:

~~~java
SearchCriterion absent = SearchCriterion.newBuilder().build();

SearchCriterion emptyText = SearchCriterion.newBuilder()
    .setText("")
    .build();

SearchCriterion falseActive = SearchCriterion.newBuilder()
    .setActive(false)
    .build();

System.out.println(absent.getValueCase());      // VALUE_NOT_SET
System.out.println(emptyText.getValueCase());   // TEXT
System.out.println(falseActive.getValueCase()); // ACTIVE
System.out.println(falseActive.getActive());    // false
~~~

You cannot infer the selection from getter values:

- **getText()** can return an empty string either when text is unselected or when text is selected as an empty string.
- **getActive()** can return false either when active is unselected or when active is selected as false.
- **getNumericId()** can return 0 both when unselected and when selected as 0.

Always check **getValueCase()** or **hasXxx()** to determine the selected member. Oneof provides explicit presence for its members without declaring optional.

## 6. Setting, Replacing, and Clearing a Selection

The builder provides setters for each member. Setting a new member clears the previous member in the same group:

~~~java
SearchCriterion criterion = SearchCriterion.newBuilder()
    .setText("enabled")
    .setNumericId(42)
    .build();

System.out.println(criterion.getValueCase()); // NUMERIC_ID
System.out.println(criterion.getText());      // ""
System.out.println(criterion.getNumericId()); // 42
~~~

After **setNumericId(42)**, the text option is no longer present. To clear the selection:

~~~java
SearchCriterion cleared = criterion.toBuilder()
    .clearValue()
    .build();

System.out.println(cleared.getValueCase()); // VALUE_NOT_SET
~~~

**clearValue()** is the builder method generated from the group name value; for the payment_method group, the corresponding method is **clearPaymentMethod()**.

Clearing a oneof from a request message simply means the message no longer holds that choice. It does not automatically mean deleting stored server data. If an update API needs a delete operation, explicitly specify the meaning of the unselected state or declare an explicit option such as clear.

## 7. Oneof in gRPC Requests

Example customer lookup API allowing lookup by ID or email:

~~~proto
syntax = "proto3";

package learning.customer.v1;

message CustomerLookup {
  oneof key {
    string customer_id = 1;
    string email = 2;
  }
}

message LookupCustomerRequest {
  CustomerLookup lookup = 1;
}

message Customer {
  string customer_id = 1;
  string display_name = 2;
}

service CustomerService {
  rpc LookupCustomer(LookupCustomerRequest)
      returns (Customer);
}
~~~

The server inspects the choice before running the query:

~~~java
switch (request.getLookup().getKeyCase()) {
    case CUSTOMER_ID ->
        findById(request.getLookup().getCustomerId());
    case EMAIL ->
        findByEmail(request.getLookup().getEmail());
    case KEY_NOT_SET ->
        throw invalidArgument("A lookup key is required");
}
~~~

The key benefit is that the server never has to guess which field takes precedence if a client sends multiple criteria; the schema and oneof API constrain selection directly in the message structure.

Since lookup is a message field, it also has its own presence: use **request.hasLookup()** to distinguish omitting the entire lookup message from sending an empty CustomerLookup. Then use **getKeyCase()** to check whether an inner choice was set.

These two checks operate at different levels:

- **hasLookup()** checks whether the child message was set.
- **getKeyCase()** checks which member inside the oneof was selected.

## 8. How ProtoJSON Represents oneof

ProtoJSON does not create a wrapper object named after the oneof group. It emits the selected member field as an ordinary property:

~~~proto
message SearchCriterion {
  oneof value {
    string text = 1;
    int32 numeric_id = 2;
  }
}
~~~

If text is selected:

~~~json
{
  "text": "active"
}
~~~

If numeric_id is selected:

~~~json
{
  "numericId": 42
}
~~~

If no branch is selected, the message may be emitted as an empty object. If a JSON object contains multiple fields belonging to the same oneof, the payload violates the single-branch rule and the ProtoJSON parser may reject the conflict.

In Java, use **JsonFormat** in **protobuf-java-util** to conform to ProtoJSON:

~~~java
import com.google.protobuf.util.JsonFormat;

String json = JsonFormat.printer().print(criterion);

SearchCriterion.Builder builder = SearchCriterion.newBuilder();
JsonFormat.parser().merge(json, builder);
SearchCriterion parsed = builder.build();

System.out.println(parsed.getValueCase());
~~~

Do not confuse the oneof group name with JSON keys. In the example above, JSON contains **text** or **numericId**, not a **value** key.

## 9. Binary Wire and Multiple Members Appearing

Oneof has no tag of its own. When a member is selected, Protobuf serializes that field directly with its own field number and wire type. Thus, binary payloads can be read by an older schema as ordinary fields known to that schema.

If wire data contains multiple members of the same oneof, the parser retains only the last choice encountered in read order. Therefore, never design a producer that emits multiple choices simultaneously and never rely on serialization order to resolve business conflicts.

One point to note for message members: the message's data is encoded as length-delimited like a normal message field. Oneof only adds the selection rule at the schema/runtime level; it does not alter the child payload's encoding format.

## 10. Compatibility Rules When Changing oneof

Oneofs must be managed carefully once a schema is used by clients and servers:

| Change | Risk and how to evaluate |
| --- | --- |
| Adding a new member to a oneof | Old readers do not know the new member and may see the group as unset. Test paths through old clients, especially if messages are converted or reconstructed. |
| Removing a member | New readers lose the API for the old choice; reserve the number and name with **reserved**, and handle legacy data. |
| Moving an existing field into a oneof | Unsafe: old messages could contain multiple fields at once; the new schema retains only one choice. |
| Moving a field out of a oneof | Can alter semantics and allow multiple values simultaneously; requires deliberate migration. |
| Changing a field number | Unsafe; field number is wire identity. |
| Changing field type or meaning | Can break wire or business logic; evaluate separately, usually prefer a new field. |

If you remove a released oneof member, reserve both its number and name in the message:

~~~proto
message Contact {
  oneof destination {
    string email = 1;
    string phone = 2;
  }
}
~~~

After removing phone:

~~~proto
message Contact {
  oneof destination {
    string email = 1;
  }

  reserved 2;
  reserved "phone";
}
~~~

**reserved** prevents the new schema from reusing number 2 or name phone. It does not prevent old clients from continuing to send field 2; the new parser may treat that data as an unknown field. When passing through a JSON gateway or code that manually reconstructs messages, unknown fields can be dropped.

### Why Is Moving Existing Fields Into a oneof Dangerous?

Suppose an older schema had two independent fields:

~~~proto
message LegacyContact {
  string email = 1;
  string phone = 2;
}
~~~

An old message can hold both email and phone. If a new schema groups them into a oneof, the new parser keeps only one choice per oneof rules; the remaining information can be dropped from the new message representation. Therefore, never move active fields into a oneof as a casual refactoring.

## 11. Choosing oneof or Independent Fields?

| Business requirement | Suitable design |
| --- | --- |
| Only one of email or phone is used | **oneof** |
| Email and phone can update independently and coexist | Two independent fields, often with explicit presence if patch is needed |
| Choose one of several structurally different payload types | **oneof** containing messages |
| Hold multiple tags simultaneously | **repeated** |
| Look up values by key | **map** |
| Need to distinguish no change, set value, and clear | Oneof with explicit commands, or FieldMask with defined semantics |

Oneof expresses **at most one choice**, and does not guarantee a choice is present. If business rules require choosing one option, the server still must check the ***_NOT_SET** case and return an appropriate error, such as **INVALID_ARGUMENT**.

## 12. Testing oneof in Java

Tests should verify:

1. A new message with no branch chosen returns ***_NOT_SET**.
2. Setting a branch to a default value still makes that branch present.
3. Setting a second branch replaces the first branch.
4. **clearXxx()** removes the group's entire selection.
5. Binary and ProtoJSON round-trips preserve the exact branch.
6. The server handles requests with no branch chosen as specified by the contract.

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.search.v1.SearchCriterion;
import org.junit.jupiter.api.Test;

class SearchCriterionTest {
    @Test
    void tracksSelectedMemberEvenWhenValueIsDefault() {
        SearchCriterion absent = SearchCriterion.newBuilder().build();
        SearchCriterion selected = SearchCriterion.newBuilder()
            .setActive(false)
            .build();

        assertEquals(
            SearchCriterion.ValueCase.VALUE_NOT_SET,
            absent.getValueCase());
        assertEquals(
            SearchCriterion.ValueCase.ACTIVE,
            selected.getValueCase());
        assertFalse(selected.getActive());
    }

    @Test
    void settingAnotherMemberReplacesPreviousChoice() {
        SearchCriterion criterion = SearchCriterion.newBuilder()
            .setText("enabled")
            .setNumericId(42)
            .build();

        assertEquals(
            SearchCriterion.ValueCase.NUMERIC_ID,
            criterion.getValueCase());
        assertEquals(42, criterion.getNumericId());
    }

    @Test
    void clearRemovesTheWholeChoice() {
        SearchCriterion cleared = SearchCriterion.newBuilder()
            .setText("enabled")
            .clearValue()
            .build();

        assertEquals(
            SearchCriterion.ValueCase.VALUE_NOT_SET,
            cleared.getValueCase());
    }
}
~~~

The **ValueCase** name and **VALUE_NOT_SET** constant in the example are generated from a oneof named value; if you rename the group, the case enum name and builder methods change accordingly. Use the exact API names from the Java classes generated in your project.

## 13. Practice Exercise

Design a **NotificationTarget** message for a notification service. Each notification can only be sent to an email, phone number, or device token:

~~~proto
message NotificationTarget {
  oneof destination {
    string email = 1;
    string phone = 2;
    string device_token = 3;
  }
}
~~~

Tasks:

1. Create a message with no destination selected and inspect **getDestinationCase()**.
2. Set **email = ""** and explain why the email branch is still present.
3. Then set phone on the same builder and confirm email is no longer selected.
4. Use **clearDestination()** to return the message to the unselected state.
5. Serialize/parse binary and ProtoJSON, verifying the branch after round-trip.
6. Write a test where the server rejects requests with **DESTINATION_NOT_SET**.
7. Suppose a webhook option must be added after old clients are already released; explain how old clients might observe the message and which conversion paths could drop the new choice.

**Completion criteria:** explain oneof as a group with at most one active member, use the Java case API accurately, and recognize schema changes that can cause data loss.

## 14. Key Takeaways

- **oneof** groups mutually exclusive fields; at most one member is selected at a time.
- A message may select no member at all; oneof does not automatically make a selection required.
- A selected scalar member retains presence even when its value is **false**, **0**, or an empty string.
- Java uses **getXxxCase()**, **hasXxx()**, member setters, and **clearXxx()**.
- Repeated/map cannot be direct members; wrap them in a message if a collection is needed as an option.
- Never casually move released fields into or out of a oneof; when removing a member, reserve both number and name.

Using oneof in the right places helps Protocol Buffers contracts clearly express alternative choices, reduces conflicting states in requests, and enables Spring gRPC services to process data consistently across client/server versions.
