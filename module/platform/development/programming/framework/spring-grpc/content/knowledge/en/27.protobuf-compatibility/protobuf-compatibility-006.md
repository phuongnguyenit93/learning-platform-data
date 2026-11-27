# Adding Enum Values and Old Clients

## 1. Why Does Adding an Enum Value Require Testing Old Clients?

In **SPRING_GRPC**, a Protobuf enum represents a set of values with stable identifying numbers. When adding a new status such as `PAYMENT_STATE_REVERSED`, a new server may send this numeric value in responses while many clients are still running code generated from the old schema.

At the binary level, enums are encoded using their numeric values. Therefore, adding an enum value with a new number usually preserves the ability to parse messages. However, **being able to parse does not mean old clients understand the meaning**. A client may encounter an enum value unknown to its generated code; if old logic assumes only the previously declared states exist, it may skip branches, return incorrect results, or cause business errors.

This lesson focuses on numeric enum values and wire stability, old client behavior when receiving new enum values, differences between proto3 open enums and proto2 closed enums, how generated Java code represents unknown values, rollout order, and testing with old generated clients.

## 2. Enums Are Transmitted by Numeric Value

Example schema v1:

```proto
syntax = "proto3";

package payment.v1;

option java_multiple_files = true;
option java_package = "dev.example.payment.v1";

enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_CAPTURED = 2;
  PAYMENT_STATE_FAILED = 3;
}

message PaymentReply {
  string payment_id = 1;
  PaymentState state = 2;
}
```

The name `PAYMENT_STATE_CAPTURED` makes code readable, but the binary payload carries the numeric value `2`. Enum names are not sent as strings in binary messages.

Schema v2 might add a value:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_CAPTURED = 2;
  PAYMENT_STATE_FAILED = 3;
  PAYMENT_STATE_REVERSED = 4;
}
```

Adding `PAYMENT_STATE_REVERSED = 4` does not alter the numbers of existing values. A v1 client still receives numeric value 4 on the wire; what matters is how the v1 runtime and generated code represent the unknown numeric value and how application logic handles it.

Basic rules:

- Each enum value has its own numeric value within the enum, unless intentionally aliasing with `allow_alias`.
- Never change the number of a released enum value.
- Never reuse the number of a removed value; reserve both its number and name.
- In proto3, the first value must have number 0 and should represent the default/unspecified state.
- Do not use numeric value 0 as a successful business state if the field might be omitted or unset by the sender.

## 3. Old proto3 Clients Receiving Unknown Enum Values

Proto3 uses **open enum semantics**: the parser preserves unknown enum numeric values rather than stripping them from the field. The generated Java API provides both an enum getter and an integer getter.

Suppose client v1 only knows values 0 through 3, while server v2 returns state number 4. With proto3 generated Java code:

- `getStateValue()` returns the actual numeric value received, which is `4` in this example.
- `getState()` returns `PaymentState.UNRECOGNIZED` because the v1 generated enum has no constant for number 4.
- The old client lacks the constant `PAYMENT_STATE_REVERSED`, yet it can still detect and record the unknown numeric value.

Example:

```java
PaymentReply reply = paymentStub.getPayment(
    GetPaymentRequest.newBuilder()
        .setPaymentId("PAY-42")
        .build()
);

PaymentState state = reply.getState();
int rawState = reply.getStateValue();

if (state == PaymentState.UNRECOGNIZED) {
    log.warn("Unknown payment state value: {}", rawState);
    return mapToSafeFallback(rawState);
}

return mapKnownState(state);
```

`mapToSafeFallback` is application logic that must be defined according to business requirements. Do not call `state.getNumber()` when `state` is `UNRECOGNIZED`; use `getStateValue()` to obtain the original numeric value.

How to handle it depends on the enum's purpose. For display-only statuses, the client might render "New status" and log it. For statuses affecting money, access control, or workflows, the fallback must fail safely: never assume an unknown status means success, paid, or permitted to proceed.

## 4. Why Must Enum Switches Have a Fallback Branch?

Old client code is often written when only a fixed set of enum values is known:

```java
switch (reply.getState()) {
    case PAYMENT_STATE_PENDING:
        return "Pending";
    case PAYMENT_STATE_CAPTURED:
        return "Captured";
    case PAYMENT_STATE_FAILED:
        return "Failed";
    case UNRECOGNIZED:
        return "Unsupported status";
    case PAYMENT_STATE_UNSPECIFIED:
    default:
        return "Unspecified";
}
```

The `UNRECOGNIZED` branch handles numeric values unknown to the generated code. The `UNSPECIFIED` branch handles value 0, which is typically the default or unset state. These two cases are different:

- `UNSPECIFIED`: a real enum constant defined in the schema.
- `UNRECOGNIZED`: a numeric value with no matching constant in the running generated code.

Do not collapse all cases into a default success branch. For critical logic, fail closed or transition to an undetermined state requiring further handling, rather than permitting sensitive operations based on an unknown value.

If the client uses a switch expression, ensure it includes an `UNRECOGNIZED`/default branch matching the generated API and Java language version in use. The goal is for old code to remain safe when the server extends the enum.

## 5. Proto2 Closed Enums vs. Proto3 Open Enums

Not all Protobuf schemas handle unknown enums identically.

| Characteristic | proto3 open enum | proto2 closed enum |
| --- | --- | --- |
| Undeclared numeric value | Preserved as an unknown enum value on the field | Typically stored in unknown fields rather than becoming a known field value |
| Java enum getter | Can return `UNRECOGNIZED` | Usually returns the default enum value if the field has no known value |
| Presence | Proto3 enum scalars default to implicit presence unless marked `optional` | Enum fields have presence according to proto2 rules |
| Accessing unknown numeric value | Proto3 generated Java API has `getXValue()` | Observation depends on generated API/runtime; unknown value usually sits in unknown fields |

With a proto2 closed enum, an old client might not see the new value via the enum getter; the field may appear unset while the numeric tag sits in unknown fields. When the message is re-serialized, the runtime can preserve the unknown data, yet application logic still does not recognize the new state.

Therefore, you cannot mechanically apply proto3's `UNRECOGNIZED` pattern to proto2. If your system uses proto2 schemas or mixed syntax, verify the specific generated API and runtime by testing with an unknown numeric value.

## 6. Adding Enum Values Is Wire-Compatible Yet Can Break Business Logic

Adding a new enum value is generally considered compatible at the binary wire level because existing values retain their numeric numbers and parsers can handle unknown numeric values according to their syntax/runtime. Still, application code may not be compatible.

Some examples:

- Old client uses `switch` and treats any state outside the three known cases as a programming bug.
- Old client maps `UNRECOGNIZED` to `PAYMENT_STATE_UNSPECIFIED`, causing dashboards to lose the distinction between a new state and missing data.
- A workflow treats every state other than `FAILED` as `CAPTURED`, leading to misprocessing when `REVERSED` arrives.
- Old or new client sends the new enum in a request, and an old server fails to understand its meaning and falls back to default handling.

This is the difference between **wire compatibility** and **behavioral compatibility**. The schema may parse cleanly while business decisions still go wrong.

## 7. New Clients Sending New Values to Old Servers

The reverse direction must also be controlled. Client v2 has the constant `PAYMENT_STATE_REVERSED` and sends numeric value 4 in a request to server v1.

With a proto3 open enum, server v1 can parse the message and retain the unknown numeric value. However, v1 generated code and server logic lack the constant to perform the new behavior. It may receive `UNRECOGNIZED` and raw number 4; if old code lacks a safe branch, it may ignore or misprocess the request.

With a proto2 closed enum, the unknown value is usually placed in unknown fields and the enum field appears to have no known value set. Server v1 may use the default value if code does not check presence.

Therefore:

- Do not let new clients send new values to old servers before servers are capable of handling them.
- If requests carry a new enum value, roll out supporting servers first before enabling clients to send that value.
- If the server runs multiple replicas, ensure every replica receiving traffic supports the new value before enabling the feature flag.
- If necessary, use a capability RPC or feature negotiation to confirm server support.

## 8. Safely Adding Enum Values

When a new state is needed, follow this sequence:

1. Choose a numeric value never previously used in the enum.
2. Keep the numbers and meanings of all existing enum values unchanged.
3. Add the new value with a clearly prefixed name consistent with the existing enum.
4. Update the server to recognize and handle the new value.
5. Audit old clients: ensure safe fallbacks exist for unknown values, especially in security/financial/workflow logic.
6. Deploy servers first if clients will send the new value in requests.
7. Only enable sending/consuming the new state once relevant servers and consumers are ready.
8. When removing an enum value in the future, reserve both its number and name inside the enum.

Example enum v2:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_CAPTURED = 2;
  PAYMENT_STATE_FAILED = 3;
  PAYMENT_STATE_REVERSED = 4;
}
```

Never change the numbers of `PENDING`, `CAPTURED`, or `FAILED` to "reorder" the list. Declaration order is not a versioning mechanism; numeric values are part of the wire contract.

## 9. Testing with Old Generated Clients

The most critical test is using code generated from the old schema to parse messages containing the new enum number.

With proto3, you can assert:

```java
// Generated class from schema v1, knowing only enum values 0..3.
PaymentReply oldClientReply = PaymentReply.parseFrom(
    newServerPayload
);

assertEquals(4, oldClientReply.getStateValue());
assertEquals(
    PaymentState.UNRECOGNIZED,
    oldClientReply.getState()
);
```

In real tests, v1 and v2 generated code may share the same fully qualified class name. Place them in separate fixture modules/packages or distinct artifact versions to avoid class collisions; do not alter the Protobuf wire package just to sidestep test conflicts.

The test suite should cover:

| Test | What to verify |
| --- | --- |
| v2 serialize → v1 parse | Old proto3 client retains the numeric value and receives `UNRECOGNIZED` |
| v1 serialize → v2 parse | New server/client reads old enum values accurately |
| v2 client → v1 server | Old server handles unknown values via a safe fallback |
| v1 client → v2 server | Old client does not crash when responses contain the new enum |
| Unexpected unknown numeric value | Never defaults to success or granted access |
| Proto2 if still in use | Verify presence and unknown-field behavior with the actual generated runtime |

Beyond message-level tests, include integration tests over real gRPC stubs to verify serialization, server methods, and statuses end-to-end. Test client mapping logic separately to prove `UNRECOGNIZED` never triggers unsafe actions.

## 10. Keeping Enum Numbers Stable and Reserving Removed Values

Never reuse a removed numeric value. Example:

```proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_CAPTURED = 2;

  reserved 3;
  reserved "PAYMENT_STATE_FAILED";

  PAYMENT_STATE_REVERSED = 4;
}
```

The reservation resides inside the enum. It prevents other developers from assigning number 3 or the name `PAYMENT_STATE_FAILED` to a new state. Do not delete the reservation just because the state no longer appears in code; old payloads, events, and backups may still contain that numeric value.

For enums with aliases (`allow_alias = true`), multiple names can intentionally share a number. However, aliases are not a substitute for migration and must be strictly controlled; never reassign historical numbers to different meanings.

## 11. Common Mistakes

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Old client fails to recognize new state | Generated enum lacks new constant | Handle `UNRECOGNIZED`, log raw numeric value, and fall back |
| Old client treats new state as unspecified | Logic merges unknown with value 0 | Distinguish `UNSPECIFIED` from unknown numeric values |
| `switch` misses new enum value | Missing fallback branch | Add `UNRECOGNIZED`/default and test |
| Old server misprocesses request | Client sent new value too early | Roll out server first, gate with capability/feature flag |
| Proto2 client cannot see new enum value | Closed enum stores numeric value in unknown fields | Inspect presence and unknown fields per runtime |
| Dashboard shows incorrect status | Metric mapping knows only old enum constants | Add an unknown bucket and safely preserve raw number |
| Old enum value interpreted as new state | Numeric value was reused | Reserve number/name and run schema breaking checks |

Do not log sensitive data alongside raw enum values if payloads contain user-identifying information. Raw numeric values are helpful for diagnostics, but bound cardinality if used as metric labels; never create a new time series for every arbitrary value.

## 12. Checklist Before Releasing a New Enum Value

- New numeric value has never been used and is not in a reserved range.
- Numbers and meanings of existing enum values remain unchanged.
- Value 0 remains an appropriate unspecified/default state.
- Old proto3 clients handle `UNRECOGNIZED` and raw numeric values safely.
- Old proto2 clients, if any remain, have been verified for closed-enum/presence behavior.
- Old servers do not receive requests with the new value before supporting logic is deployed.
- New servers are fully rolled out before enabling clients to send the new value.
- All switches, mappings, dashboards, and workflows have unknown fallbacks.
- Tests exist for old generated clients parsing new responses and for the reverse request direction.
- Removed enum values have both numbers and names reserved.

With **SPRING_GRPC**, adding an enum value generally preserves binary parsing as long as existing numeric values stay unchanged, yet old clients still may not understand the new value's meaning. Unknown enums must be handled safely, rollout order must be controlled by request/response direction, and tests must run against generated code from released schemas.
