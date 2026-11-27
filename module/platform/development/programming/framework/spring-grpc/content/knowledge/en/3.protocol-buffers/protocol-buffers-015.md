# Reserved Numbers and Reserved Names

## Learning Objectives

After this lesson, you will be able to:

- Explain why released field numbers and field names must be protected after deletion.
- Use **reserved numbers** and **reserved names** in proto3 messages and enums.
- Declare a single retired number, multiple numbers, or a range of numbers.
- Distinguish the effect of reserved from **deprecated**, unknown fields, and runtime data validation.
- Plan schema changes to prevent legacy data from being interpreted as new fields or enum values.

## 1. Why Is reserved Needed?

In Protocol Buffers, the **field number** is a field's identifier on the binary wire. The field name is used in the schema, generated Java code, descriptors, ProtoJSON, and tools such as FieldMask. When a released field is deleted, both the old number and old name can still exist in stored data or un-upgraded clients.

Suppose the initial version has:

~~~proto
message Customer {
  string customer_id = 1;
  string legacy_code = 2;
}
~~~

After removing legacy_code, if number 2 is reused for a new field:

~~~proto
message Customer {
  string customer_id = 1;
  string account_reference = 2;
}
~~~

An older client still sends field number 2 with the meaning of legacy_code. The new server can read those exact bytes as account_reference if the wire type matches. Legacy data is then misinterpreted under the new meaning without necessarily throwing a parse error.

To prevent this, Protobuf provides the **reserved** keyword. It records retired numbers or names so the compiler rejects reusing them within the same message or enum scope.

## 2. What Do Reserved Numbers and Reserved Names Protect?

The two kinds of reservation address two different risks:

| Reservation | Protects | If omitted |
| --- | --- | --- |
| **Reserved number** | Field identity on the binary wire or enum number | Legacy data may be interpreted as a new field/value. |
| **Reserved name** | Name in schema, generated API, ProtoJSON, and FieldMask paths | Old name may be assigned to a new field, causing confusion or changing JSON/text semantics. |

Therefore, when removing a released field, you normally must reserve **both the number and the name**. Reserving only the number still allows reusing the old name with a new number; reserving only the name still allows reusing the old number with a new name.

Field names are not encoded directly into binary Protobuf, yet they remain an important part of the contract across other layers. For example, JSON may use **legacyCode**, and FieldMask may contain the path **legacy_code**.

## 3. reserved Syntax in Messages

Inside a message, you can reserve one number, multiple numbers, or a range of numbers:

~~~proto
message Customer {
  string customer_id = 1;
  string account_reference = 3;

  reserved 2;
  reserved "legacy_code";
}
~~~

The example above keeps number 2 and the name legacy_code from being reused inside the Customer message.

You can combine multiple numbers or ranges in a single statement:

~~~proto
message Customer {
  string customer_id = 1;

  reserved 2, 5, 9 to 12;
  reserved "legacy_code", "old_region";
}
~~~

The two statements have distinct forms:

- A reserved statement containing numbers and number ranges.
- A reserved statement containing quoted names.

Do not mix numbers and names in the same reserved statement. A range such as **9 to 12** is inclusive on both ends: 9, 10, 11, and 12.

## 4. Reserved Numbers in Enums

Enums can also reserve numbers and names. This matters because enums are transmitted as integers on the wire:

~~~proto
enum CustomerState {
  CUSTOMER_STATE_UNSPECIFIED = 0;
  CUSTOMER_STATE_ACTIVE = 1;
  CUSTOMER_STATE_SUSPENDED = 3;

  reserved 2;
  reserved "CUSTOMER_STATE_LEGACY";
}
~~~

If number 2 and name CUSTOMER_STATE_LEGACY were previously used, the reservation prevents new schemas from reassigning them to another state.

Proto3 enums must have a first value equal to 0. Do not delete or reserve the default value 0 if the enum still needs to satisfy this rule; normally keep a value such as **UNSPECIFIED = 0**.

You can reserve multiple numbers or a range:

~~~proto
enum PaymentState {
  PAYMENT_STATE_UNSPECIFIED = 0;
  PAYMENT_STATE_PENDING = 1;
  PAYMENT_STATE_PAID = 2;

  reserved 3, 5 to 8;
  reserved "PAYMENT_STATE_OLD", "PAYMENT_STATE_ARCHIVED";
}
~~~

Enum value names also need to be retained after deletion. Value names are used in source code, descriptors, and ProtoJSON; value numbers are used on the binary wire.

## 5. Scope of reserved

A reservation applies only within the **message or enum where it is declared**:

~~~proto
message Parent {
  reserved 2;

  message Child {
    string child_id = 1;
    string child_note = 2;
  }
}
~~~

reserved 2 in Parent protects only Parent's field numbers. It does not stop Child from using field number 2. Conversely, a reservation inside Child does not affect Parent's fields either.

Similarly, reserved inside an enum protects only that enum's numbers and names. It does not automatically apply to another enum even when both enums live in the same file or package.

When removing a nested field, place the reservation inside that nested message. When removing an enum value, place the reservation inside that enum.

## 6. Valid Field Numbers and Number Ranges

Valid Protobuf field numbers lie in the range **1 to 536,870,911**. Number 0 is invalid. The range **19,000 to 19,999** is reserved by Protobuf implementations and cannot be used as field numbers.

When declaring reserved ranges:

~~~proto
message HistoricalRecord {
  string id = 1;

  reserved 2 to 10;
  reserved 20 to max;
}
~~~

**to max** extends up to the maximum valid field number. Use large ranges when a group of legacy fields has been retired and the organization wants to lock out the entire block.

Do not reserve a wider range than history requires if there are still plans to add fields in that region. Reservations are long-term schema constraints, so choose ranges deliberately and document the rationale in change notes.

For enums, values are 32-bit integers. You can reserve a retired enum number or range, while keeping the enum structure valid—especially the default value 0 in proto3.

## 7. Removing a Field Safely: Before and After Example

Old version:

~~~proto
message UserProfile {
  string user_id = 1;
  string display_name = 2;
  string legacy_region = 3;
  string email = 4;
}
~~~

After legacy_region is no longer supported:

~~~proto
message UserProfile {
  string user_id = 1;
  string display_name = 2;
  string email = 4;

  reserved 3;
  reserved "legacy_region";
}
~~~

If you want to add a new field, pick a number that has never been used:

~~~proto
message UserProfile {
  string user_id = 1;
  string display_name = 2;
  string email = 4;
  string locale = 5;

  reserved 3;
  reserved "legacy_region";
}
~~~

Do not renumber email = 4 to number 3 just because number 3 looks unused in the current schema. Number 3 was previously used, so it must continue to be treated as consumed.

## 8. Removing an Enum Value Safely

Old version:

~~~proto
enum DeliveryState {
  DELIVERY_STATE_UNSPECIFIED = 0;
  DELIVERY_STATE_QUEUED = 1;
  DELIVERY_STATE_SENT = 2;
  DELIVERY_STATE_LEGACY_SENT = 3;
}
~~~

After retiring the old state:

~~~proto
enum DeliveryState {
  DELIVERY_STATE_UNSPECIFIED = 0;
  DELIVERY_STATE_QUEUED = 1;
  DELIVERY_STATE_SENT = 2;

  reserved 3;
  reserved "DELIVERY_STATE_LEGACY_SENT";
}
~~~

If an enum uses **option allow_alias = true** and has multiple names pointing to one number, removing an alias requires special care. If that number is still used by another active name, reserve only the **removed alias name**; do not reserve the number that is still valid.

Never change enum numbers merely to reorder items or rename them. Enum numbers are wire data and may be stored long-term in databases, logs, or message queues.

## 9. How Does reserved Differ from deprecated?

**deprecated** and **reserved** serve two different stages:

~~~proto
message UserProfile {
  string legacy_region = 3 [deprecated = true];
}
~~~

| Mechanism | Meaning | Field still in schema? | Prevents reuse? |
| --- | --- | --- | --- |
| **deprecated = true** | Warns schema users that the field should no longer be used | Yes | No |
| **reserved number/name** | Locks a removed number or name | Corresponding field is gone | Yes, at schema compile time |

A common lifecycle:

1. Mark the old field deprecated and announce the removal plan.
2. Update clients/servers to stop reading/writing that field.
3. Verify critical consumers have migrated.
4. Remove the field from the schema.
5. Reserve both the old number and old name.

**deprecated = true** does not remove Java accessors, stop clients from sending the field, or lock the number. Reserve only after the field has been removed from declarations.

## 10. Reserved Is Not a Runtime Data Filter

A common misconception: **reserved** is primarily a compile-time schema constraint, not a rule that rejects data at runtime.

When a new parser receives binary data from an old client:

- A reserved field number is no longer defined by the new schema; the data may be kept as an **unknown field**.
- The application cannot read it via the old getter because the getter no longer exists in the new Java class.
- The Protobuf runtime can preserve unknown fields when parsing and re-serializing the same message, yet converting through a DTO, JSON, or constructing a new message from known fields alone can drop that data.

For proto3 enums, an undeclared enum number can still be parsed as an **unknown enum value**. Java normally returns **UNRECOGNIZED** from the enum getter and preserves the original number via **getXxxValue()**. Reservations do not automatically make the parser reject that number.

If the server no longer accepts a legacy value, validate and reject it at the application layer and map it to an appropriate gRPC error. Do not rely on reserved to perform business validation.

## 11. Field Names Are Also Part of the Contract

Field names do not appear in binary tags, yet they affect many other interfaces:

- Generated Java APIs, such as **getLegacyRegion()** and **setLegacyRegion()**.
- ProtoJSON, such as **legacyRegion**.
- FieldMask paths, such as **legacy_region**.
- Descriptors, reflection, and schema documentation tools.
- Protobuf text format and schema manipulation tools.

If you reserve only number 3 yet reuse the name legacy_region for a new field at number 5, legacy JSON containing legacyRegion could be interpreted as the new field. If you reserve only the name yet reuse number 3, legacy binary data could be interpreted as the new field.

Therefore, when a released field is removed, reserve both identifiers. For enums as well, reserve both the number and name of the retired value.

## 12. Verifying Reservations During Development

The **protoc** compiler raises an error if a schema declares a field number or name inside a reserved region:

~~~proto
message UserProfile {
  string user_id = 1;

  reserved 3;
  reserved "legacy_region";

  // The following two declarations must be rejected by the compiler:
  // string new_region = 3;
  // string legacy_region = 5;
}
~~~

You can validate schemas via the code-generation step in the build. When validating standalone, run **protoc** with the proper include paths:

~~~bash
protoc \
  --proto_path=src/main/proto \
  --descriptor_set_out=build/schema.pb \
  customer/profile.proto
~~~

The command succeeds only if the schema and dependencies are valid. In CI, run schema/code-generation checks to catch accidental number or name reuse before merging.

A schema evolution test suite should verify:

1. Removed fields or enum values have both number and name reserved.
2. New fields do not use numbers previously released.
3. New enums do not reuse old numbers, even when old names are no longer in source.
4. New field names do not reuse reserved names.
5. Old clients sending legacy data are handled per the defined unknown field/enum policy.
6. ProtoJSON and FieldMask do not accidentally map old names to new fields.

## 13. Common Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Removing a field without reserving its number | Old number may be reused and corrupt binary meaning | Reserve released numbers. |
| Reserving only the number, omitting the name | Old name can be reused for another field | Reserve the name too. |
| Reserving only the name, omitting the number | Old number can be assigned to a new field | Reserve the number too. |
| Mixing numbers and names in one reserved statement | Invalid schema | Split into separate reserved statements. |
| Placing reserved in a parent message for a child message's field | Does not protect the right scope | Place it inside the message/enum that owns the field. |
| Assuming reserved blocks old clients from sending data | Unknown data still reaches runtime | Validate and handle on the server. |
| Using deprecated instead of reserved after deletion | Numbers and names can still be reused | Remove the field, then reserve both number and name. |
| Reserving an enum number that still has an active alias | Schema conflicts with the remaining enum value | Reserve only the removed alias name if the number stays in use. |

## 14. Practice Exercise

Old version of a contract:

~~~proto
message Account {
  string account_id = 1;
  string legacy_number = 2;
  string owner_name = 3;
}

enum AccountState {
  ACCOUNT_STATE_UNSPECIFIED = 0;
  ACCOUNT_STATE_OPEN = 1;
  ACCOUNT_STATE_OLD = 2;
  ACCOUNT_STATE_CLOSED = 3;
}
~~~

Design the new version according to these requirements:

1. Remove legacy_number and reserve both field number 2 and the name legacy_number.
2. Add external_reference with a new number; do not reuse number 2.
3. Remove enum value ACCOUNT_STATE_OLD, reserving number 2 and the corresponding name.
4. Keep enum default value 0 intact.
5. Explain what happens when the new server parses binary sent by an old client containing field number 2.
6. Explain why reserved does not automatically reject unknown fields at runtime.
7. Write a schema example that intentionally reuses a reserved number or name and predict the compiler error.

**Completion criteria:** the new schema does not reuse legacy identifiers, reservations sit in the proper scope, and you can separately explain impacts on binary wire, Java API, ProtoJSON, and runtime data.

## 15. Key Takeaways

- **Field numbers** identify fields on the binary wire; never reuse a released number.
- **Field names** affect Java source, ProtoJSON, FieldMask, and descriptors; never reuse a retired name.
- When removing a field or enum value, reserve **both number and name** in the exact owning message/enum.
- You can reserve multiple numbers, ranges, and multiple names; numbers and names must be in separate statements.
- **deprecated** warns against continued use; **reserved** locks identifiers after removal.
- Reserved protects the schema at compile time and does not replace runtime unknown field/enum checks.

Using reserved numbers and reserved names properly lets Protocol Buffers contracts evolve safely, prevents historical data from being misinterpreted as new fields, and preserves consistency across Spring gRPC client and server versions.
