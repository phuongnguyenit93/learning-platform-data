# Nested Messages and Nested Enums

## Learning Objectives

After this lesson, you will be able to:

- Declare **nested messages** and **nested enums** in proto3.
- Reference nested types properly from other messages and understand their name scoping.
- Use generated Java types such as **Customer.Address** and **Customer.State**.
- Distinguish the presence of a nested message from the default value of a nested enum.
- Decide when to nest data types and when to promote them to top-level types for reuse.
- Evaluate the impact of renaming, moving, or extending nested types on Spring gRPC contracts.

## 1. When Should You Nest a Message or Enum?

In **SPRING_GRPC** contracts, Protobuf messages define request and response structures for RPCs. A message may contain child data that only makes sense within its context. For example, **Customer** has an **Address** and a **State**; that address and state belong to the customer model.

Proto3 lets you declare a **message** or **enum** inside another message. The nested type's name scope is tied to the enclosing message, helping group related types and avoiding polluting the package-level namespace with every name.

Consider a nested type when:

- The child type only has meaning within one parent message, such as **Customer.Address**.
- The enum type describes a property specific to the parent message, such as **Customer.State**.
- You want schema readers to immediately see the relationship between the parent and child structures.

Use top-level types when multiple messages or multiple services need to reuse the same type, or when the child type has become an independent concept in the business domain.

## 2. Declaring Nested Messages and Nested Enums

Example:

~~~proto
syntax = "proto3";

package learning.customer.v1;

option java_package = "com.example.customer.v1";
option java_multiple_files = true;

message Customer {
  string customer_id = 1;
  string display_name = 2;
  Address address = 3;
  State state = 4;

  message Address {
    string street = 1;
    string city = 2;
    string country_code = 3;
  }

  enum State {
    STATE_UNSPECIFIED = 0;
    STATE_ACTIVE = 1;
    STATE_SUSPENDED = 2;
  }
}
~~~

In the schema:

- **Address** is a message declared inside **Customer**.
- **State** is an enum declared inside **Customer**.
- Fields **address** and **state** use those nested types directly within the enclosing message.
- Field numbers of **Address** start at 1 within the Address message scope; they do not collide with fields 1–4 of Customer.
- Enum **State** has its own number domain; its first value must be 0 per proto3 rules.

Nested types do not automatically inherit fields, enum values, or data from the parent message. **Customer.Address** is an independent message with its own schema; **Customer** simply holds a field of that type.

## 3. Name Scope and Referencing Nested Types

Inside the enclosing message itself, you can use the short name:

~~~proto
message Customer {
  Address address = 1;

  message Address {
    string city = 1;
  }
}
~~~

From another message in the same package, prefix with the parent message name:

~~~proto
message CustomerSearchResult {
  Customer.Address primary_address = 1;
  Customer.State customer_state = 2;
}
~~~

The fully qualified Protobuf type name also includes the package. With package **learning.customer.v1**, the corresponding symbols are:

- **learning.customer.v1.Customer**
- **learning.customer.v1.Customer.Address**
- **learning.customer.v1.Customer.State**

These are names in the Protobuf namespace, not necessarily identical to the Java package. **java_package** specifies the generated Java package; it does not change the package or fully qualified symbol names in the Protobuf schema.

### Avoiding Enum Value Collisions

Enum value names are placed in the enclosing scope of the enum, not in an isolated namespace named after the enum. Therefore, when multiple enums exist in the same package or message, use prefixes:

~~~proto
message Customer {
  enum State {
    STATE_UNSPECIFIED = 0;
    STATE_ACTIVE = 1;
  }

  enum VerificationState {
    VERIFICATION_STATE_UNSPECIFIED = 0;
    VERIFICATION_STATE_PENDING = 1;
    VERIFICATION_STATE_VERIFIED = 2;
  }
}
~~~

Names like **STATE_ACTIVE** and **VERIFICATION_STATE_VERIFIED** prevent collisions when more enums are added. Never give two enum values the same name within one enclosing scope.

## 4. What Java Types Are Generated for Nested Types?

With **java_package = "com.example.customer.v1"**, Java code accesses nested types through the enclosing message class:

- **Customer** is the parent message class.
- **Customer.Address** is the child message class.
- **Customer.State** is the child enum.

**java_multiple_files = true** generates top-level classes like **CustomerSearchResult** into separate Java files, while nested types are still referenced through their enclosing class.

Example creating a message:

~~~java
import com.example.customer.v1.Customer;

Customer.Address address = Customer.Address.newBuilder()
    .setStreet("12 Nguyen Hue")
    .setCity("Ho Chi Minh City")
    .setCountryCode("VN")
    .build();

Customer customer = Customer.newBuilder()
    .setCustomerId("C-42")
    .setDisplayName("Nguyen An")
    .setAddress(address)
    .setState(Customer.State.STATE_ACTIVE)
    .build();

System.out.println(customer.getAddress().getCity());
System.out.println(customer.getState());
~~~

A nested message has its own builder and is immutable after **build()**, just like a top-level message. You can construct it directly from a child builder inside the parent builder:

~~~java
Customer customer = Customer.newBuilder()
    .setCustomerId("C-42")
    .setAddress(Customer.Address.newBuilder()
        .setCity("Da Nang")
        .setCountryCode("VN"))
    .build();
~~~

For the enum, use the parent-prefixed name such as **Customer.State.STATE_ACTIVE**. Do not create a manual Java enum to replace the generated enum if the Protobuf message still uses the original enum type.

## 5. Presence of Nested Messages vs. Default Values of Nested Enums

A nested message field has **explicit presence** even without declaring **optional**:

~~~proto
message Customer {
  Address address = 1;

  message Address {
    string city = 1;
  }
}
~~~

Java provides **hasAddress()**:

~~~java
Customer absent = Customer.newBuilder().build();

Customer presentEmpty = Customer.newBuilder()
    .setAddress(Customer.Address.getDefaultInstance())
    .build();

System.out.println(absent.hasAddress());       // false
System.out.println(presentEmpty.hasAddress()); // true
System.out.println(absent.getAddress().getCity()); // ""
~~~

**getAddress()** returns a default instance when the field is absent. Therefore, do not check null to determine presence; use **hasAddress()**.

A regular nested enum field is a scalar enum and uses **implicit presence**:

~~~proto
message Customer {
  State state = 1;

  enum State {
    STATE_UNSPECIFIED = 0;
    STATE_ACTIVE = 1;
  }
}
~~~

If **state** is unset, **getState()** returns **STATE_UNSPECIFIED**, and there is no **hasState()**. If you need to distinguish not sent from explicitly setting 0, declare **optional State state = 1;**; Java will then generate **hasState()**.

Do not confuse **nested** with **optional**: nested describes declaration placement and name scoping; optional describes presence of a scalar/enum field. The two features solve different problems.

## 6. Using Nested Types in gRPC Requests/Responses

Nested types can be referenced from requests, responses, and other messages:

~~~proto
message GetCustomerRequest {
  string customer_id = 1;
}

message GetCustomerResponse {
  Customer customer = 1;
}

message UpdateCustomerAddressRequest {
  string customer_id = 1;
  Customer.Address address = 2;
}

service CustomerService {
  rpc GetCustomer(GetCustomerRequest) returns (GetCustomerResponse);
  rpc UpdateAddress(UpdateCustomerAddressRequest)
      returns (GetCustomerResponse);
}
~~~

**UpdateCustomerAddressRequest** uses **Customer.Address** to reuse the exact child type instead of defining a second nearly identical **Address**. If the address belongs strictly to the Customer model, this keeps the relationship clear in the schema.

When using the Java stub, the request can be built as follows:

~~~java
import com.example.customer.v1.Customer;
import com.example.customer.v1.UpdateCustomerAddressRequest;

UpdateCustomerAddressRequest request =
    UpdateCustomerAddressRequest.newBuilder()
        .setCustomerId("C-42")
        .setAddress(Customer.Address.newBuilder()
            .setCity("Can Tho")
            .setCountryCode("VN"))
        .build();
~~~

You do not need a separate service or Spring boilerplate class to use nested types. They are simply generated data types; server and client use them like any other Protobuf message.

## 7. When Should a Nested Type Move to Top-Level?

Initially **Customer.Address** might only be used inside Customer. Later, the system needs the same address structure for Supplier, Branch, and DeliveryDestination. At that point, consider promoting it to a top-level message:

~~~proto
message Address {
  string street = 1;
  string city = 2;
  string country_code = 3;
}

message Customer {
  string customer_id = 1;
  Address address = 2;
}

message Supplier {
  string supplier_id = 1;
  Address address = 2;
}
~~~

Moving from **Customer.Address** to **Address** changes the **fully qualified Protobuf name** and the Java type (**Customer.Address** becomes **Address**). Source code referencing the old type must be updated; descriptors and tools relying on fully qualified names also see a different symbol.

If the internal field structure remains identical, the binary payload of the message field may still be readable because the outer field remains length-delimited and the inner message contents share the same field numbers/types. However, renaming a type must not be treated as completely harmless: systems using **google.protobuf.Any** type URLs, descriptors, reflection, schema registries, or JSON mappings can depend on the type name.

Selection guidelines:

| Keep nested | Promote to top-level |
| --- | --- |
| Only meaningful inside the parent message | Multiple messages/services need to reuse it |
| No independent lifecycle or contract | Can be managed, versioned, or documented independently |
| Parent name clarifies context | The type name has become a general concept |
| Changes normally move with the parent message | Multiple teams need to evolve the type separately |

Avoid nesting too deeply just to organize files. Each nesting level lengthens type names and can make reuse, searching, and versioning harder.

## 8. Evolving Nested Messages and Enums Across Versions

Basic compatibility rules still apply:

- When adding a field to a nested message, choose an unused number within **that nested message itself**.
- When removing a field, reserve its old number and name in the corresponding nested message.
- Never change released enum numbers; when removing a value, reserve both number and name in the enum.
- When adding an enum value, older clients may receive **UNRECOGNIZED** in Java; use **getXxxValue()** if the raw number must be preserved.
- Renaming or moving a nested type changes its fully qualified symbol and Java API, even if the internal binary structure does not change.

Example extending **Customer.Address**:

~~~proto
message Customer {
  Address address = 3;

  message Address {
    string street = 1;
    string city = 2;
    string country_code = 3;
    optional string postal_code = 4;

    reserved 5;
    reserved "legacy_region";
  }
}
~~~

**postal_code = 4** is added with a new number within **Address**. **reserved 5** and **reserved "legacy_region"** take effect only inside **Address**; they do not reserve number 5 or that name inside **Customer**.

If an older version does not know **postal_code**, it can skip the new field on the binary wire. The new server must handle the case where the field is absent, especially if the application uses it to determine delivery zones.

## 9. Testing Nested Types in Java

Some useful tests:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.customer.v1.Customer;
import org.junit.jupiter.api.Test;

class CustomerNestedTypeTest {
    @Test
    void buildsAndParsesNestedMessage() throws Exception {
        Customer source = Customer.newBuilder()
            .setCustomerId("C-42")
            .setAddress(Customer.Address.newBuilder()
                .setCity("Da Nang")
                .setCountryCode("VN"))
            .setState(Customer.State.STATE_ACTIVE)
            .build();

        Customer parsed = Customer.parseFrom(source.toByteArray());

        assertTrue(parsed.hasAddress());
        assertEquals("Da Nang", parsed.getAddress().getCity());
        assertEquals(Customer.State.STATE_ACTIVE, parsed.getState());
    }

    @Test
    void distinguishesAbsentAndEmptyNestedMessage() {
        Customer absent = Customer.newBuilder().build();
        Customer emptyAddress = Customer.newBuilder()
            .setAddress(Customer.Address.getDefaultInstance())
            .build();

        assertFalse(absent.hasAddress());
        assertTrue(emptyAddress.hasAddress());
    }
}
~~~

The first test confirms nested messages and enums build and parse properly. The second test proves an absent nested message differs from one that is present but empty. When modifying schemas, add fixtures from older versions to verify clients/servers across versions still read data and handle unknown enums.

## 10. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Referencing **Address** from another message without the **Customer.** prefix | Compiler cannot find the type in the current scope | Use **Customer.Address** or the appropriate fully qualified name. |
| Assuming nested types inherit a separate Java package | Wrong imports or class names | Check **java_package**; nested types are accessed via the parent message class. |
| Using generic enum value names like **ACTIVE** in multiple enums | Name collisions in the enclosing scope | Use prefixes such as **CUSTOMER_STATE_ACTIVE**. |
| Assuming nested enums have default presence | Cannot distinguish absent field from 0 | Use **optional** if **hasState()** is needed. |
| Checking null on a nested message | Misses default instance behavior | Use **hasAddress()**. |
| Nesting a type shared by many services | Increases coupling to the parent message | Consider a top-level message. |
| Moving a nested type without updating descriptors/Java | Source code or reflection tools fail | Evaluate fully qualified symbols, Java APIs, and dependent systems. |

## 11. Practice Exercise

Design a **Device** message with:

- A nested **Network** message containing **ip_address**, **port**, and **optional string dns_name**.
- A nested **ConnectionState** enum with **UNSPECIFIED = 0**, **DISCONNECTED = 1**, and **CONNECTED = 2**.
- **network** and **connection_state** fields in **Device**.
- An external **UpdateDeviceRequest** message reusing **Device.Network**.

Tasks:

1. Write the complete proto3 schema and identify the fully qualified names of **Device.Network** and **Device.ConnectionState**.
2. Create a **Device** using the Java builder, setting network and state CONNECTED.
3. Compare **hasNetwork()** with **getConnectionState()** when the fields are unset.
4. Serialize/parse the message and inspect the nested message.
5. Explain why **ConnectionState** value 0 does not prove the client sent the field.
6. Suggest when **Network** should be promoted to a top-level message if multiple services share it.

## 12. Key Takeaways

- **Nested messages/enums** group data types within a parent message's scope; their fully qualified names include the parent name.
- In Java, nested types are accessed through the parent message class, such as **Customer.Address** and **Customer.State**.
- Nested message fields inherently have presence; regular nested enum fields remain scalar enums with implicit presence.
- Enum values need clear names and 0 meaning **UNSPECIFIED**; prefixes prevent name collisions.
- Only nest types tightly tied to the parent message; consider top-level for widely reused types.
- When renaming or moving a nested type, check Java APIs, descriptors, reflection, **Any type URLs**, and cross-version clients/servers.

Designing nested messages and nested enums properly keeps Protocol Buffers contracts aligned with the business domain, keeps Java APIs readable, and helps Spring gRPC services evolve safely over time.
