# Using Free-Form Strings Instead of Enums or Meaningful Messages

## 1. Why do free-form strings weaken a contract?

In **SPRING_GRPC**, Protocol Buffers form the contract between client and server. A common design mistake is using `string` for every kind of data: order status, payment type, role, currency unit, event type, or even an entire object serialized as JSON. This looks flexible, but it shifts the burden of defining the contract onto each individual client and server.

For example, a status field might receive values like `"pending"`, `"PENDING"`, `"in_progress"`, `"processing"`, or an unexpected typo. The compiler cannot catch spelling mistakes; the server has to guess the intent; the client has to compare strings and handle unknown values on its own.

Protobuf provides three tools with distinct purposes:

- **string:** free text, identifiers, or opaque values with an open value set.
- **enum:** a finite set of choices with stable names and wire numbers.
- **message:** a structured data type with fields, types, presence, and evolution support.

Choosing the right type lets the schema express intent, generates safer Java code, and supports API evolution. Do not use `string` merely because it is quick to declare or out of a belief that enums/messages make contracts rigid.

## 2. Choose types based on data semantics

A practical rule of thumb:

| Data | Usually appropriate type | Reason |
| --- | --- | --- |
| Display name, description, notes | string | Free-form text |
| Customer ID, order ID | string or message wrapper | Identifier with textual representation |
| Order status with finite values | enum | Compiler and contract know the options |
| Fixed payment types | enum or oneof message | Enum if just a label; oneof if each type has its own payload |
| Address, money, time range | message | Has multiple structured fields |
| Point in time | google.protobuf.Timestamp | Standard time semantics |
| Time duration | google.protobuf.Duration | Clear unit and semantics |
| Externally defined partner codes | string | Value set may be open, outside API control |
| One of several differently structured payloads | oneof containing messages | Represents mutually exclusive choices |

Do not choose types based solely on today's data. Ask: Is the value set finite and governed by the API? Does the data have multiple components that need individual validation? Do clients need compiler assistance when handling cases?

## 3. Use enums for finite value sets

Example of an order status with a contract-managed value set:

```proto
syntax = "proto3";

package commerce.orders.v1;

enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_CONFIRMED = 2;
  ORDER_STATE_SHIPPED = 3;
  ORDER_STATE_CANCELLED = 4;
}

message GetOrderReply {
  string order_id = 1;
  OrderState state = 2;
}
```

Enums allow the schema to explicitly enumerate valid states. Generated Java code can use `OrderState` instead of arbitrary strings:

```java
switch (reply.getState()) {
    case ORDER_STATE_PENDING -> showPending();
    case ORDER_STATE_CONFIRMED -> showConfirmed();
    case ORDER_STATE_SHIPPED -> showShipped();
    case ORDER_STATE_CANCELLED -> showCancelled();
    case ORDER_STATE_UNSPECIFIED, UNRECOGNIZED ->
        handleUnknownState();
}
```

Enum names in code give IDE/compiler support for rename/refactor and reduce typos. Still, the client must include a branch for unknown values because the server may be upgraded before the client.

Do not use an enum if values are arbitrarily created by tenants or partners and the server cannot control the list. In such cases, a validated `string` or a separate resource/catalog may be more appropriate.

## 4. Enum numbers on the wire are part of the contract

Protobuf binary transmits the enum's integer number, not its symbol name. Therefore:

- Do not change the number of a published enum value.
- Do not reassign a deleted number to a new meaning.
- Do not use `0` for a real business state; reserve it for `*_UNSPECIFIED` or a safe default.
- When removing an enum value, mark both its number and name as `reserved`.
- Only add new values with new numbers.
- Avoid negative numbers; encoding can be less efficient and yields no contract benefit.

Example when retiring an old state:

```proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_CONFIRMED = 2;

  reserved 3;
  reserved "ORDER_STATE_LEGACY";
}
```

Do not reuse number `3` for a new state. An older client might still persist or forward number `3`; if the new server reassigns that number to another meaning, the same wire value will be misinterpreted.

Beyond binary wire compatibility, ProtoJSON typically serializes enums using symbol names. Renaming an enum can affect JSON clients, logs, configs, or data stored as JSON even when wire numbers stay unchanged. Consider both binary and JSON contracts when renaming.

## 5. Unknown enum values and forward compatibility

Proto3 supports open enum semantics: a message can carry a numeric enum value unknown to code generated from an older schema. In Java, the enum getter can return `UNRECOGNIZED`; the numeric accessor preserves the received number.

Example:

```java
OrderState state = reply.getState();

if (state == OrderState.UNRECOGNIZED) {
    int rawValue = reply.getStateValue();
    log.warn("Unknown order state number: {}", rawValue);
    handleUnknownState();
}
```

Older clients should not assume an enum only contains values known at compile time. Decide explicitly:

- For display-only states, show a generic "new status" and disallow unrecognized actions.
- For states affecting financial/safety decisions, fail closed or require a client upgrade.
- Never coerce `UNRECOGNIZED` into `PENDING` or a default value with side effects.
- If a proxy/adapter reads and re-serializes messages, preserve unknown numeric values when forwarding is needed.

For client requests, the server must also validate numeric enum values. Unknown values can arrive when a newer client talks to an older server; do not treat them as valid options by default.

## 6. When is `string` still the right choice?

`string` is appropriate when values are free-form text or an open set not fully controlled by the API:

- User names, descriptions, or notes.
- Identifiers issued by external systems.
- Provider codes that can be added without releasing a new schema.
- Open-standard locale tags or currency codes, which still require validation.
- Search queries or filter expressions if the contract defines clear syntax.

Even when using `string`, semantics must remain clear:

- Bound length and encoding.
- Define trimming/case sensitivity/normalization rules.
- Distinguish empty from absent when necessary.
- Validate format and namespace.
- Do not use a display label as a stable identifier.
- Do not use localized translated strings as machine-readable values.

For example, "Confirmed" (localized display text) should not be the status value in the contract. Use a stable enum and let the client translate labels by locale.

## 7. Use messages for structured data

A string like `"12.50 USD"` packs an amount and currency into a single string. The client must parse it, handle decimal separators, locales, and rounding rules. A message represents each part explicitly:

```proto
message Money {
  string currency_code = 1;
  int64 units = 2;
  int32 nanos = 3;
}

message InvoiceReply {
  string invoice_id = 1;
  Money total = 2;
}
```

The `Money` message lets you validate currency code, units, and nanos separately. Do not use `float`/`double` for monetary amounts requiring decimal precision. Semantics of `units`/`nanos` must be defined consistently, including sign rules and precision.

Similarly, do not pack an address into a comma-separated string if clients/servers need to manipulate individual components. Use an `Address` message with street, locality, region, `postal_code`, and `country_code`.

## 8. Use standard messages for timestamps and durations

Do not pass timestamps as custom-formatted strings like `"19/11/2026 10:30"`. Strings can be ambiguous regarding timezone, locale, and format.

Use standard types:

```proto
import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

message Reservation {
  string reservation_id = 1;
  google.protobuf.Timestamp starts_at = 2;
  google.protobuf.Duration duration = 3;
}
```

`Timestamp` represents an instant; `Duration` represents a span of time. The server must still validate ranges and business semantics, such as ensuring start time is not too far in the past or duration does not exceed booking limits.

Do not use strings for types with standard messages just for readability in JSON. Protobuf JSON mapping already defines representations for `Timestamp` and `Duration`.

## 9. Use `oneof` when choices have different payloads

An enum only represents a label. If each choice requires its own data, use `oneof` with corresponding messages:

```proto
message CardPayment {
  string payment_token = 1;
}

message BankTransfer {
  string bank_account_reference = 1;
}

message WalletPayment {
  string wallet_provider = 1;
  string wallet_reference = 2;
}

message PaymentMethod {
  oneof method {
    CardPayment card = 1;
    BankTransfer bank_transfer = 2;
    WalletPayment wallet = 3;
  }
}
```

If using `string type = "CARD"` paired with an arbitrary JSON payload, the server must parse and validate field combinations manually; the compiler has no idea which payload matches which type. `oneof` represents the choice directly in the schema and generated API.

The server must still check when no `oneof` member is selected and validate the chosen member's payload. When adding a new member, older clients need a policy for unknown choices.

Do not use `oneof` for fields that can coexist simultaneously. Choose structures based on actual semantics.

## 10. Do not stuff JSON into strings to bypass schema design

Another anti-pattern is defining:

```proto
message Event {
  string type = 1;
  string payload_json = 2;
}
```

This turns Protobuf into a thin envelope; the actual payload has no Protobuf schema. Consequences:

- The compiler generates no types for the payload.
- Wrong field names or wrong types are only caught at runtime.
- Clients must parse JSON and manage versions manually.
- Validation and field presence become fragmented.
- Schema registries/Protobuf tooling cannot inspect payload contents.
- Logs/metrics become harder to analyze and risk exposing sensitive data.

If an event has known payload types, use `oneof` with concrete messages. If genuinely dynamic payloads by type URL are needed, consider `google.protobuf.Any` with a clear type registry and versioning policy. `Any` is not a dumping ground for arbitrary JSON and still requires clients/servers to understand the packed types.

## 11. Request enums must be validated on the server

An enum field can receive the default `*_UNSPECIFIED` value or an unknown numeric value. The server should not blindly treat every non-zero value as valid.

Example:

```java
public void validate(CreateOrderRequest request) {
    OrderPriority priority = request.getPriority();

    if (priority == OrderPriority.UNRECOGNIZED) {
        throw new RequestValidationException(
            "priority contains an unsupported value"
        );
    }

    if (priority == OrderPriority.ORDER_PRIORITY_UNSPECIFIED) {
        throw new RequestValidationException(
            "priority must be specified"
        );
    }
}
```

Map validation exceptions to `INVALID_ARGUMENT` at the gRPC boundary. Do not pass unsupported numeric values into a `switch` lacking default/`UNRECOGNIZED` handling.

If a server needs to forward an unrecognized enum value to another service, preserve the numeric value instead of converting through a domain enum and losing it. Forward only when the contract permits and never trigger side effects based on semantics not understood.

## 12. Field presence: an empty string is not always the same as absent

In proto3, scalar fields with implicit presence return default values when omitted. For `string`, the getter returns an empty string; for `enum`, the getter returns numeric `0`.

If the API must distinguish "caller omitted the field" from "caller sent an empty/default value", use `optional` or an appropriate message wrapper:

```proto
message UpdateCustomerRequest {
  string customer_id = 1;
  optional string display_name = 2;
}
```

The server can check `hasDisplayName()`:

- Absent: keep the current name.
- Present but empty: clear the name if the contract allows.
- Present with value: update the name.

For enums, `optional` may be necessary if absent has different semantics from `*_UNSPECIFIED`. Message fields have presence per Protobuf semantics; clearly define patch/update behavior.

Do not assume an empty string means "no change" unless the contract explicitly specifies so.

## 13. Validation, defaults, and business semantics

Stronger data types do not eliminate validation. An enum can still be `UNSPECIFIED` or `UNRECOGNIZED`; a message can still omit a business-required field; a string can still fail format checks.

Separate the layers:

- **Schema type:** Protobuf guarantees data conforms to string, enum, or message.
- **Structural validation:** checks presence, length, range, and field combinations.
- **Domain validation:** checks whether values make sense in business terms.
- **Authorization:** checks whether the caller is permitted to use that option/resource.

For example, a payment method may be schema-valid, yet that tenant does not have that wallet provider enabled. That is a business precondition or permission policy, not a Protobuf parse failure.

Do not use an enum as an access control list in place of authorization. Enum values describe options; permission to use an option must be checked on the server.

## 14. Evolving schemas safely

When replacing a string with an enum/message, treat it as a contract change:

1. Identify semantics and string values actually in use.
2. Normalize aliases/casing/typos before choosing enum values.
3. Pick stable enum names and numbers; reserve `0` for `UNSPECIFIED`.
4. Add the new field with a new field number, keeping the old field during transition.
5. Server can read both old and new fields during migration, with explicit precedence rules.
6. Migrate clients in waves to the new field.
7. Monitor usage of the old field and unknown enum values.
8. Deprecate/remove the old field only after all consumers have migrated.
9. When removing a field/enum value, reserve the corresponding field number/name and enum number/name.

Never change the type of an active field at the same field number from `string` to `enum`/`message`. The binary wire type or semantics will become incompatible; add a new field or version the API.

Enum names can be serialized in ProtoJSON, so renaming also requires migration and compatibility review.

## 15. Testing contracts and generated Java

Tests should cover:

| Scenario | What to verify |
| --- | --- |
| Known enum value | Client/server interpret semantics correctly |
| Enum UNSPECIFIED | Server rejects or handles per default contract |
| Unknown numeric enum value | Client does not crash; server handles per policy |
| Removed enum number | Old number is not reused; reserved is declared |
| Misspelled string | Validation catches it if field has a closed vocabulary |
| Message missing required field | Structural/domain validation behaves properly |
| oneof with no member selected | Server handles absent case |
| oneof with a new member | Older client has a safe fallback |
| ProtoJSON enum name change | JSON consumer compatibility verified |
| Both old and new fields present | Migration precedence is consistent |
| Unknown field forwarded | Value is preserved if proxy must retain it |

Test through a real gRPC server to verify status codes and generated code behavior. Add schema compatibility checks in CI to prevent changing field numbers, reusing enum numbers, or making incompatible wire-type changes.

## 16. Review checklist

- `string` is used only for free text, identifiers, or genuinely open vocabularies.
- Finite API-governed option sets are represented by `enum`.
- Multi-component/typed structures are represented by `message`.
- Mutually exclusive payload variants use `oneof` when appropriate.
- Enum number `0` is `*_UNSPECIFIED` or a safe default.
- Published enum numbers are never changed or reused.
- When deleting an enum value, both number and name are reserved.
- Clients handle `UNRECOGNIZED`/unknown enum values.
- Server validates request enums and does not arbitrarily accept `UNSPECIFIED`.
- JSON strings are not used as schema-less payloads when payloads have stable structure.
- Standard types like `Timestamp`/`Duration` are used where semantics match.
- Field presence/default semantics are defined for updates/patches.
- Migrations do not change a field's type at the same field number.
- Binary/ProtoJSON compatibility tests and generated Java tests exist.

In **SPRING_GRPC**, using free-form strings for everything strips the contract of vocabulary, structure, and early checks. Use `enum` for finite choices, `message` for structured data, and `string` for free text/identifiers or genuinely open values. Combine presence, validation, and Protobuf evolution rules so clients and servers share the exact same semantics across versions.
