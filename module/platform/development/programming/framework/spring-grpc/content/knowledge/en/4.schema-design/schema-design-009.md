# Safe Enum Evolution

Enums help gRPC contracts constrain a field to a set of clearly named values, such as payment methods or order states. When a system already has clients and servers running across multiple versions, adding, renaming, or deleting an enum value can affect generated Java code, binary protobuf payloads, and ProtoJSON in different ways.

In **Spring gRPC**, enums should be designed so newer versions can expand without causing older clients to misinterpret values. This lesson focuses on enum numbering rules, proto3 default values, handling unknown values in Java, renaming via aliases, deletion with `reserved`, and phased rollouts across versions.

## 1. Start With a Meaningful Zero Value

In proto3, an enum's first value must equal 0. Reserve this value for an unselected state, commonly named with an UNSPECIFIED suffix:

```proto
syntax = "proto3";

package shop.payment.v1;

option java_package = "com.myshop.grpc.payment.v1";
option java_multiple_files = true;

enum PaymentMethod {
  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;
  PAYMENT_METHOD_BANK_TRANSFER = 2;
}

message PayOrderRequest {
  string order_id = 1;
  PaymentMethod payment_method = 2;
}
```

If a client omits payment_method, the proto3 getter returns the zero value, namely PAYMENT_METHOD_UNSPECIFIED. This lets the server recognize that the request did not select a payment method. Never assign CARD = 0: when a client forgets to send the field, the server might accidentally process it as if the customer chose card payment.

**Enums do not enforce business requirements on their own.** If an operation requires a concrete payment method, the server must reject UNSPECIFIED via validation. If you need to distinguish "field omitted" from "explicitly sent UNSPECIFIED", declare the field as optional PaymentMethod payment_method = 2; and check presence with hasPaymentMethod().

## 2. Adding Enum Values: Usually Wire-Compatible, Not Necessarily Behavior-Compatible

Suppose v1 supports only cards and bank transfers. Later the system adds an e-wallet:

```proto
enum PaymentMethod {
  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;
  PAYMENT_METHOD_BANK_TRANSFER = 2;
  PAYMENT_METHOD_WALLET = 3; // New value
}
```

Enums are encoded by **number**, not symbolic name. Therefore, adding number 3 does not alter how existing values 0, 1, and 2 decode. However, v1 clients do not have the name PAYMENT_METHOD_WALLET; if a v2 server returns number 3, old clients must handle the unknown value.

Proto3 follows an open enum model: unknown numeric values can be preserved in the field. With generated Java code, the enum getter typically returns UNRECOGNIZED while the integer getter preserves the raw number:

```java
PaymentMethod method = response.getPaymentMethod();
int rawValue = response.getPaymentMethodValue();

if (method == PaymentMethod.UNRECOGNIZED) {
    // Do not map the new value to CARD or BANK_TRANSFER.
    logUnknownPaymentMethod(rawValue);
    showUnsupportedPaymentOption();
}
```

Do not confuse UNSPECIFIED with UNRECOGNIZED:

| Case | Meaning |
| --- | --- |
| PAYMENT_METHOD_UNSPECIFIED (number 0) | Default value or client explicitly selected the unspecified state |
| UNRECOGNIZED | The current client lacks an enum constant matching the received number |
| getPaymentMethodValue() | Actual integer value, useful for logging, diagnostics, or forwarding |

### Risks Differ by Call Direction

- **New client → old server:** client sends WALLET = 3; old server does not know its meaning. Proto3 Java can represent this number as UNRECOGNIZED; the old handler must reject or handle it per an explicit policy. Never default to card payment.
- **New server → old client:** server returns WALLET = 3; old client may receive UNRECOGNIZED. The app needs a safe fallback branch instead of crashing or making wrong decisions.
- **New client → new server:** both understand the new value, yet the server must still validate permissions and business rules.

Thus, "binary-compatible enum addition" does not mean every application version supports that feature.

## 3. Handling Unknown Enums in Spring gRPC Java

On the server side, never use a default switch branch to coerce an unrecognized value into a valid method. For example, a handler can inspect the value before processing:

```java
PaymentMethod method = request.getPaymentMethod();

if (method == PaymentMethod.PAYMENT_METHOD_UNSPECIFIED) {
    observer.onError(Status.INVALID_ARGUMENT
            .withDescription("payment_method must be selected")
            .asRuntimeException());
    return;
}

if (method == PaymentMethod.UNRECOGNIZED) {
    int rawValue = request.getPaymentMethodValue();
    observer.onError(Status.INVALID_ARGUMENT
            .withDescription("unsupported payment_method value: " + rawValue)
            .asRuntimeException());
    return;
}

switch (method) {
    case PAYMENT_METHOD_CARD:
        paymentService.payByCard(request);
        break;
    case PAYMENT_METHOD_BANK_TRANSFER:
        paymentService.payByBankTransfer(request);
        break;
    default:
        observer.onError(Status.INVALID_ARGUMENT
                .withDescription("unsupported payment method")
                .asRuntimeException());
        return;
}
```

This snippet illustrates validation and dispatch; in a real handler, paymentService is an application dependency and business errors must be mapped consistently to gRPC status codes. The key point is checking both UNSPECIFIED and UNRECOGNIZED before executing business logic.

On the client side, when reading an enum from a response, decide how to display or report an unsupported option. If the enum number is needed in logs or intermediate systems, read it via getPaymentMethodValue(); do not call getNumber() on UNRECOGNIZED, since that sentinel constant does not represent a concrete domain number.

## 4. Renaming Enum Values: Numbers Stay the Same, Names Are Still Part of the Contract

Suppose PAYMENT_METHOD_BANK_TRANSFER needs to be renamed to PAYMENT_METHOD_WIRE_TRANSFER. If number 2 stays unchanged, binary protobuf still transmits the same integer. However, renaming affects:

- Java source code: the old enum constant disappears from the newly generated API, so code referencing the old name fails to compile.
- ProtoJSON: enums are normally represented by symbolic name; JSON clients sending or expecting the old name can break.
- Descriptors, schema documentation, and name-based tooling: they will observe the new name.

Do not rename directly if JSON clients or external Java code rely on the old name. A transition period can use an alias:

```proto
enum PaymentMethod {
  option allow_alias = true;

  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;
  PAYMENT_METHOD_BANK_TRANSFER = 2 [deprecated = true];
  PAYMENT_METHOD_WIRE_TRANSFER = 2;
}
```

allow_alias = true allows two names to map to the same number. This is a migration tool, not an automatic fix for every client:

- Binary protobuf carries only the number 2; old clients still recognize that number under the old name in their generated code.
- In ProtoJSON and TextFormat, the serialized name for an aliased number depends on **the name appearing first** in the enum declaration. Changing the order can change the emitted JSON string.
- Generated Java enums also map the number to one representative constant; never assume newer clients will always receive the second alias when parsing the number.
- deprecated = true merely warns schema users; it does not migrate clients or remove the old name automatically.

If the API exposes ProtoJSON, verify the exact serialized and parsed strings before reordering aliases. For polyglot clients, keep the old name during the compatibility window and remove it only after confirming consumers have migrated. If legacy JSON behavior cannot be maintained, consider a new endpoint or API version.

## 5. Deleting Enum Values With `reserved`

When a published enum value is no longer used, never reuse its number or name:

```proto
enum PaymentMethod {
  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;

  reserved 2;
  reserved "PAYMENT_METHOD_BANK_TRANSFER";
}
```

`reserved` for enums has two forms:

- reserved 2; reserves the deleted enum number.
- reserved "PAYMENT_METHOD_BANK_TRANSFER"; reserves the deleted name.

Reserve both the number and the name. If you simply delete the declaration and assign number 2 to PAYMENT_METHOD_WALLET, old clients or persisted historical data could misinterpret a bank transfer as a wallet payment. That is a dangerous semantic bug even though the parser still reads the payload cleanly.

You can reserve a range such as 4 to 7; both endpoints are inclusive. Reserve only numbers that were actually used or need protection, and never overlap an active value.

## 6. ProtoJSON Must Be Tested Separately

In binary protobuf, enums travel as numbers. In ProtoJSON, enums are represented by name by default:

```json
{
  "paymentMethod": "PAYMENT_METHOD_CARD"
}
```

Some ProtoJSON mappers/parsers also accept integer representations for enums, yet you must not rely on that to skip testing JSON clients. Specifically:

- Renaming an enum value can prevent JSON clients sending the old name from parsing against the new schema.
- Aliases can accept multiple names on input, while the first declared name is used on serialization.
- Unknown numeric enum values may be preserved in numeric form; unknown symbolic names generally cannot be mapped if the schema does not declare that name.
- JSON gateways or standard JSON libraries may enforce unknown key/value policies that differ from standard ProtoJSON.

If a Spring gRPC service exchanges only binary protobuf between generated stubs, JSON risks may sit outside the primary call path. However, if you have HTTP transcoding, REST gateways, JSON config files, or JSON events, treat JSON as a separate contract surface.

## 7. Phased Rollout for New Enum Values

When adding PAYMENT_METHOD_WALLET, a safe sequence is usually:

1. **Update the schema and server first.** New servers recognize the new value before clients are enabled to send it. Old servers in the fleet can still reject this value.
2. **Roll out across all server instances.** Confirm no old instances still receive requests with the new enum value; route by capability or version if needed.
3. **Update clients with a safe unknown branch.** Old clients must not crash or fall back to the wrong payment method upon receiving the new enum.
4. **Enable the feature selectively.** Allow clients to send the new value only once target servers support it; use feature flags or capability negotiation in distributed rollouts.
5. **Monitor and transition.** Track rejection rates for unknown enums, clients still sending legacy names, and ProtoJSON errors if any.

Never enable a new enum value on clients while a load balancer still routes requests to old servers. For a payment request, having an old server ignore or reject the new method must be handled deliberately; never treat it as a blindly retryable error if the call could have created payment state.

## 8. Schema and Old/New Client Testing

Key test cases:

| Case | Expected outcome |
| --- | --- |
| Enum omitted in proto3 | Server receives UNSPECIFIED and rejects if domain logic requires selection |
| Known enum value sent | Server dispatches to the right method |
| Unknown enum number sent to old server | Server detects UNRECOGNIZED/numeric value and handles per policy without guessing another method |
| New server returns new enum value to old client | Old client handles the unknown branch safely |
| Renamed while keeping number | Binary tests may pass; verify generated Java and ProtoJSON separately |
| Alias added | Verify serialized JSON name, parsing, and representative Java enum constant |
| Value deleted | Compiler rejects redeclaring the reserved number/name |
| Multi-instance rollout | Clients send the new value only once all traffic-serving instances support it |

Example of testing unknown values at the message level:

```java
// bytes generated from a new schema containing PAYMENT_METHOD_WALLET = 3.
PayOrderRequest parsedByOldClient =
        PayOrderRequest.parseFrom(bytesFromNewClient);

assertEquals(
        PaymentMethod.UNRECOGNIZED,
        parsedByOldClient.getPaymentMethod());
assertEquals(3, parsedByOldClient.getPaymentMethodValue());
```

This is only a protobuf parsing check. Integration tests must also verify that the Spring gRPC handler returns the expected status and does not invoke the wrong domain service. If ProtoJSON is used, add JSON fixtures covering the old enum name, the new alias name, and unknown numeric values.

## 9. Checklist Before Modifying an Enum

- [ ] Value 0 is UNSPECIFIED or a safe default state.
- [ ] No published enum value's number is changed.
- [ ] A new enum value uses an unused number and has been evaluated against old clients.
- [ ] Java handlers explicitly handle UNSPECIFIED and UNRECOGNIZED.
- [ ] Unknown values are never coerced into a different business choice.
- [ ] If renaming, generated Java APIs, ProtoJSON, and aliases have been evaluated.
- [ ] If deleting a value, both its number and name are reserved.
- [ ] Server/client rollout is ordered and all server instances can be verified.
- [ ] Binary tests with old/new schemas exist, plus JSON tests if a gateway is present.

**Self-Check**

**Question 1.** Why should a proto3 enum define UNSPECIFIED = 0?

*Answer:* An omitted enum field reads as 0. That value should represent an unselected state rather than accidentally triggering a business action.

**Question 2.** A v2 server adds WALLET = 3; a v1 client receives a response containing 3. How should the Java client handle it?

*Answer:* The enum getter may return UNRECOGNIZED; read the raw number via the `...Value()` getter if needed for logging/diagnostics and display an unsupported state. Never convert it into CARD or BANK_TRANSFER.

**Question 3.** Is renaming an enum value while keeping the same number completely safe?

*Answer:* Compatibility may hold only at the binary number level. Generated Java symbols, descriptors, and ProtoJSON names can change. Evaluate each consumer type and use an alias transition phase when appropriate.

**Question 4.** Can you delete enum value 2 and then assign number 2 to a new value?

*Answer:* No. Reserve number 2 and the old name so previously published payloads are never decoded with a new meaning.

Enums are part of the contract, not merely lists of Java constants. Keep numbers stable, reserve zero for a safe default state, handle unknown values explicitly, and test both binary and JSON representations. Doing so allows Spring gRPC services to expand options without forcing all clients to upgrade at once.
