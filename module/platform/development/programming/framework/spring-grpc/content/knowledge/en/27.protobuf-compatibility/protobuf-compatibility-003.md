# Reserved Fields to Prevent Reuse

## 1. The Role of reserved in Protobuf

In **SPRING_GRPC**, `.proto` files serve as the contract used to generate Java messages, client stubs, and service base classes. When a field is no longer used, simply deleting its declaration line from the message is not enough to protect the contract in the future. Another developer could accidentally reuse the removed field number or name for a new meaning.

Protobuf provides the **`reserved`** declaration to mark numbers and names that must not be reused within the same message or enum. The compiler will reject any schema declaring a field or value that conflicts with a reservation. As a result, compatibility rules are stored directly inside the schema and checked on every build.

This lesson focuses on declaring and managing `reserved`:

- Reserving field numbers and names after removing a field.
- Reserving a single number, multiple numbers, or a range of numbers.
- Reserving enum numbers and enum names.
- Placing reservations in the right scope when fields belong to a `oneof` or nested message.
- Understanding what the compiler checks versus what still requires CI/review checks.
- Applying a safe field-removal process in shared Protobuf modules.

## 2. Reserve Both Number and Name

Consider the initial message:

```proto
syntax = "proto3";

package catalog.v1;

message Product {
  string sku = 1;
  string legacy_label = 4;
  int64 price_cents = 5;
}
```

After some time, the application no longer uses `legacy_label`. When removing the field, the new schema should reserve both number 4 and the name `legacy_label`:

```proto
syntax = "proto3";

package catalog.v1;

message Product {
  string sku = 1;
  int64 price_cents = 5;

  reserved 4;
  reserved "legacy_label";
}
```

The two declarations protect two distinct identifiers:

| Reservation | What does it prevent? |
| --- | --- |
| `reserved 4;` | Prevents any new field from reusing number 4 |
| `reserved "legacy_label";` | Prevents any new field from reusing the name `legacy_label` |

Both should be declared when removing a field from a released schema. The number is the identifier in the binary wire format; the name affects schema source, generated APIs, and name-based surfaces such as JSON mapping.

`reserved` is not a new field, creates no data on the wire, and generates no Java getters/setters. It is strictly a schema/compiler-level constraint.

## 3. Syntax for Reserving Numbers and Ranges

Inside a message, you can reserve a single number, multiple numbers, or a range:

```proto
message Order {
  string order_id = 1;

  reserved 2;
  reserved 4, 7, 9 to 12;
}
```

`9 to 12` is inclusive of both 9 and 12. Numbers and ranges can be combined in a single declaration:

```proto
message Order {
  reserved 2, 4, 7, 9 to 12;
}
```

When you want to reserve from a number up to the maximum limit, Protobuf supports `to max`:

```proto
message HistoricalRecord {
  string id = 1;

  reserved 2 to max;
}
```

Only use `to max` when you intentionally want to close off the entire remaining range of field numbers. If the message still needs future extensibility, reserving only the exact previously used numbers is more flexible.

Valid field numbers range from 1 to 536,870,911, excluding the range 19,000 through 19,999, which is reserved by Protobuf for internal implementation. Never declare new fields in the forbidden range. Reservation is not a mechanism to legitimize an otherwise disallowed number.

### Rules for Declaring Ranges

- Both ends of a range must be in ascending order.
- Do not declare overlapping ranges or duplicate numbers.
- Do not reserve a number currently in use by another field in the same message.
- Do not assume one message's reservations apply to another message.
- Retain reservations in future schema versions, even if the field has been absent from code for many releases.

## 4. Reserving Field Names

Field names can also be reserved:

```proto
message Customer {
  string customer_id = 1;

  reserved "old_name", "legacy_status";
}
```

Names in `reserved` are `.proto` field names, distinct from Java getter names. For instance, the field `legacy_status` may generate the Java getter `getLegacyStatus()`, but the name to reserve in the schema is `"legacy_status"`.

You can combine name and number reservations:

```proto
message Customer {
  string customer_id = 1;

  reserved 3, 8 to 10;
  reserved "old_name", "legacy_status";
}
```

Do not reserve only the name and forget the number. If you only reserve `"legacy_status"`, someone else can still reuse the old number for a field with a different name and cause old payloads to be interpreted with the new meaning.

Also distinguish field names from custom `json_name` values. Field name reservations prevent reusing `.proto` identifiers; they do not automatically enforce a policy over every JSON alias defined by external gateways or adapters. If the JSON contract has custom aliases, verify and manage them as a separate compatibility surface.

## 5. Reserving Enum Numbers and Enum Names

Enums have numeric values transmitted on the wire. When removing an enum value, you must reserve both its number and name **inside the enum declaration**.

Old schema:

```proto
enum ShipmentState {
  SHIPMENT_STATE_UNSPECIFIED = 0;
  SHIPMENT_STATE_CREATED = 1;
  SHIPMENT_STATE_LEGACY_HOLD = 4;
}
```

New schema:

```proto
enum ShipmentState {
  SHIPMENT_STATE_UNSPECIFIED = 0;
  SHIPMENT_STATE_CREATED = 1;

  reserved 4;
  reserved "SHIPMENT_STATE_LEGACY_HOLD";
}
```

Do not reassign number 4 to `SHIPMENT_STATE_DELIVERED`. An old payload containing numeric value 4 could be misunderstood by a new client as `DELIVERED`, even though the original data meant `LEGACY_HOLD`.

Enums use a similar range reservation syntax:

```proto
enum LegacyCode {
  CODE_UNSPECIFIED = 0;
  CODE_ACTIVE = 1;

  reserved 4, 7 to 9;
  reserved "CODE_RETIRED", "CODE_OLD_PENDING";
}
```

An enum's reservations do not belong in the message containing a field of that enum type. For example, if `Shipment.state` uses `ShipmentState`, the enum's number/name must be reserved inside `ShipmentState`, not inside the `Shipment` message.

## 6. Fields in oneof and Nested Messages

### Fields Removed from oneof

If a member of a `oneof` is removed, place `reserved` at the **enclosing message level**, not inside the `oneof` block:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    string bank_account = 2;
  }

  reserved 3;
  reserved "legacy_wallet_token";
}
```

Here, number 3 and the name `legacy_wallet_token` represent the removed member. When an old payload contains tag 3, the new message no longer has generated APIs for that member; the field becomes unknown. The reservation prevents a future member from reusing that number.

### Nested Messages Have Separate Reservation Scopes

Each message has its own field number namespace:

```proto
message Envelope {
  string request_id = 1;

  reserved 2;
  reserved "legacy_header";

  message Header {
    string source = 1;
    string trace_id = 2;
  }
}
```

`Envelope` reserves number 2 within `Envelope` itself; it does not prohibit `Header` from using number 2. If a field in `Header` is removed, the reservation must be added inside `Header`.

Similarly, a nested enum has its own reservations inside that enum. Place reservations where the field or enum value was originally declared; do not place them on an outer message merely because the outer message encloses it.

## 7. Common Declaration Mistakes

| Mistake | Why it is incorrect | How to fix |
| --- | --- | --- |
| Reserving only the name, not the number | Old number can still be assigned to another field | Reserve both number and name |
| Reserving only the number, omitting the name | Old identifier may be reused in source/schema | Reserve both when removing a field |
| Placing `reserved` inside `oneof` | Reservations are message-level declarations | Move `reserved` outside the `oneof` block |
| Reserving a number used by an active field | Self-contradictory schema | Only reserve numbers of removed fields |
| Placing enum reservations inside a message using the enum | Wrong scope for enum values | Place inside the enum declaration |
| Assuming reservations are global across all messages | Numbers are managed per message | Reserve separately in each message that used the number |
| Deleting reservations after several releases | Old payloads/backups may still be read | Keep reservations long-term |
| Using `reserved` to change an existing field's meaning | Reservations only forbid reusing retired identifiers | Add a new field with a new number and migrate |

A schema change might compile and still break semantics if a reservation is forgotten. The compiler can only block conflicts with numbers/names already declared `reserved`; it cannot automatically know a field existed historically if the current schema drops the reservation.

## 8. Process for Removing Fields and Adding Reservations

When a field is no longer needed in a shared contract, follow this sequence:

1. **Identify field history:** record the message, field number, name, type, and all clients/servers currently using it.
2. **Stop business dependency:** deploy code that no longer requires the field before removing it from the schema if older versions remain active.
3. **Remove the field declaration:** delete the field from the message while keeping all remaining field numbers unchanged.
4. **Reserve number and name:** add both to the exact message.
5. **Handle enums/oneofs:** reserve enum numbers/names inside the enum; reserve `oneof` members at the message level.
6. **Regenerate code:** run `protoc` and compile modules depending on generated artifacts.
7. **Test old payloads:** parse fixtures serialized from the previous schema to confirm no old field is misinterpreted.
8. **Run compatibility checks:** compare the new schema against the released baseline and review the `.proto` diff.
9. **Keep reservations:** do not delete these declarations in subsequent releases.

If you want to replace an old field, add a new field with a never-used number, deploy compatible read/write logic during a transition period, migrate data, and only then remove the old field and reserve its old identifiers.

## 9. Enforcing Reservations via Compiler and CI

`protoc` checks reservations when compiling schemas. For example, if a message already has `reserved 4;` and someone adds `string payment_reference = 4;`, the compiler reports an error because the field uses a reserved number. Likewise, declaring a field with a reserved name is rejected.

A minimal schema compilation step might run:

```bash
protoc \
  --proto_path=src/main/proto \
  --descriptor_set_out=build/catalog-descriptors.pb \
  src/main/proto/catalog.proto
```

Paths are illustrative; CI must use the project's actual include paths and import dependencies. When generating Java, existing code generation steps also invoke `protoc` and catch reservation conflicts.

To prevent forgetting to add a reservation after removing a field, running `protoc` alone is insufficient: the new schema no longer knows the old field existed. CI should compare against the released baseline schema using a breaking-change detection tool, combined with lint rules and `.proto` change reviews. For example, using Buf:

```bash
buf lint
buf breaking --against ".git#branch=main"
```

Buf configuration and rule sets must align with repository policy. Keep the baseline aligned with the released schema; comparing against the wrong branch or only against a history-less working tree can cause breaking-change checks to miss field removals.

There should be two layers of control:

- **Compiler:** rejects schemas reusing already-reserved numbers/names.
- **Schema diff/CI:** detects fields removed without corresponding reservations compared to the previous baseline.

## 10. Review Checklist

Before merging `.proto` changes, verify:

- Removed field number is reserved in the exact message.
- Removed field name is reserved in the same message.
- Removed enum value's number and name are reserved in the corresponding enum.
- Removed `oneof` member is reserved at the message level.
- Reservation ranges do not overlap or include numbers currently in use.
- No newly declared field/value conflicts with reservations.
- Nested messages have their own properly scoped reservations.
- CI runs `protoc`, schema linting, and breaking-change checks against the right baseline.
- Tests or fixtures exist for payloads from old schemas if data is persisted or forwarded.
- Reservations are preserved in the schema across subsequent releases.

In **SPRING_GRPC**, `reserved` acts as a guardrail directly in the schema source to protect retired field numbers and names. Declaring them in the right scope, reserving both numbers and names, and combining compiler checks with schema diffs in CI prevent new fields from accidentally inheriting old identifiers and misinterpreting released payloads.
