# oneof Changes and Their Impact

## 1. What Problem Does oneof Solve?

In **SPRING_GRPC**, Protobuf messages typically contain independent fields. However, some models require only one representation to be active at a time—for example, a payment method being a card, bank transfer, or digital wallet. Protobuf provides **`oneof`** to describe a group of mutually exclusive fields.

When one member of a `oneof` is set, all other members in the same group are cleared in the message object being built. This mechanism lets the generated API express the active selection clearly and avoids states where multiple branches are simultaneously set in the same message instance.

Changing a `oneof` after a schema has been released requires careful evaluation. A `oneof` group does not emit a separate tag on the wire; each member is still encoded with its own field number and wire type. Consequently, some changes preserve binary parsing while altering how the application interprets the message.

This lesson focuses on how `oneof` is represented in schemas, on the binary wire, and in the generated Java API; the impact of adding, removing, and renaming members; risks when moving fields into or out of a group; presence, default values, and unknown members; and safe testing/rollout when clients and servers run mismatched versions.

## 2. oneof Structure on the Wire

Example payment message:

```proto
syntax = "proto3";

package payment.v1;

option java_multiple_files = true;
option java_package = "dev.example.payment.v1";

message BankTransfer {
  string iban = 1;
}

message WalletPayment {
  string wallet_id = 1;
}

message PaymentMethod {
  oneof method {
    string card_token = 1;
    BankTransfer bank_transfer = 2;
    WalletPayment wallet = 3;
  }
}
```

`oneof method` is a logical grouping in the schema. The binary payload does not transmit the group name `method`; if `bank_transfer` is chosen, the wire message contains field number 2 with the wire encoding of `BankTransfer`.

This leads to two principles:

- Renaming the `oneof` group does not by itself change the binary tags of its members.
- Changing the field number or type of a member alters that field's wire contract, even if the member stays in the same group.

Members of a `oneof` cannot be `repeated` or `map`. If a branch needs multiple elements, wrap a `repeated` or `map` field inside a nested message.

## 3. Generated Java API and Selection State

Protobuf Java generates APIs for each member as well as for the group as a whole. Example:

```java
PaymentMethod method = PaymentMethod.newBuilder()
    .setCardToken("card-token-123")
    .build();

assertEquals(
    PaymentMethod.MethodCase.CARD_TOKEN,
    method.getMethodCase()
);
```

If the builder subsequently sets another member, the previous member is cleared:

```java
PaymentMethod method = PaymentMethod.newBuilder()
    .setCardToken("card-token-123")
    .setWallet(
        WalletPayment.newBuilder()
            .setWalletId("wallet-42")
            .build()
    )
    .build();

assertEquals(
    PaymentMethod.MethodCase.WALLET,
    method.getMethodCase()
);
```

In this example, `WALLET` is the active member; `card_token` is no longer set. The generated API typically provides getters/setters for each member, `getMethodCase()` to inspect which member is selected, a case enum with one entry per member plus `METHOD_NOT_SET`, and `clearMethod()` to clear the current selection.

Do not rely solely on reading a member's getter to determine which branch is selected. A scalar getter returns a default value when that member is not selected. Use `getMethodCase()` or presence accessors to clearly distinguish states.

A scalar member explicitly set to its default value—for instance, an empty string—remains the selected member. `oneof` provides explicit presence for its members: `getMethodCase()` still returns `CARD_TOKEN`, even though `getCardToken()` is an empty string. This is an important difference compared to proto3 scalars with implicit presence outside a `oneof`.

## 4. Adding a New Member to oneof

Suppose schema v1 has two options:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    BankTransfer bank_transfer = 2;
  }
}
```

Schema v2 adds a digital wallet using a new field number:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    BankTransfer bank_transfer = 2;
    WalletPayment wallet = 3;
  }
}
```

For binary Protobuf, this is usually a parse-compatible change if existing members remain unchanged and a never-used field number is chosen. However, old clients do not yet know about `wallet`:

- When client v1 parses a payload containing field 3, the parser treats that field as unknown.
- Client v1's `getMethodCase()` returns `METHOD_NOT_SET`, because none of the members known to v1 generated code is set.
- The Java Protobuf runtime normally preserves unknown fields when parsing and re-serializing a message; however, mapping to a DTO, constructing a new message, or converting through JSON can drop that field.
- Client v1 cannot call a getter to read `wallet_id` or know what the new option means.

This creates a subtle trap: `METHOD_NOT_SET` can mean either the sender selected no method, or the sender selected a new member unknown to the old client. Business logic must not automatically treat both situations as identical.

### Request and Response Directions

| Version flow | Behavior |
| --- | --- |
| New server sends new member → old client | Old client sees `METHOD_NOT_SET`; new member is an unknown field |
| Old server sends old member → new client | New client recognizes old member normally |
| New client sends new member → old server | Old server does not recognize selection; handler may see `METHOD_NOT_SET` |
| Old client sends old member → new server | New server recognizes old selection normally |

If the new member appears in responses, old clients need a safe fallback. If the new member is sent in requests, supporting servers must be deployed before enabling clients to send that member. With multiple replicas, only enable the feature once every server receiving traffic has been upgraded.

## 5. Removing a Member from oneof

If an option is no longer supported, remove the member declaration while reserving both its field number and name on the message enclosing the `oneof`:

```proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    BankTransfer bank_transfer = 2;
  }

  reserved 3;
  reserved "wallet";
}
```

Reservations sit at the message level, outside the `oneof` block. Never place `reserved` inside `oneof`.

Reasons to reserve:

- Old payloads may still contain field number 3.
- Old clients/servers may continue sending the removed member during rollout.
- If number 3 were assigned to another member, old payloads could be interpreted as the new choice.
- The old name should also never be reused for another field in the same message.

When a member is removed, the new parser may keep the old field as an unknown field, while the new generated API no longer has a getter or case for that member. Do not rely on unknown-field preservation to keep a retired business feature alive.

If an old choice needs to be replaced, add a new member with a new number, support both during a transition period, migrate consumers, and only then remove the old member and reserve its old identifiers.

## 6. Moving Independent Fields into a oneof

This is a high-risk change because the old schema allowed multiple fields to be set simultaneously, whereas the new schema permits only one member in the group.

Schema v1:

```proto
message Contact {
  string email = 1;
  string phone = 2;
}
```

Schema v2 groups both fields into a `oneof`:

```proto
message Contact {
  oneof contact_method {
    string email = 1;
    string phone = 2;
  }
}
```

An old payload can contain both field 1 and field 2 because schema v1 allowed it. When the v2 parser reads the message, both fields belong to the same `oneof`; according to parsing rules, whichever member appears last on the wire is the selection kept. The other member's value is no longer accessible through the generated API.

Therefore, email and phone data coexisting in old payloads can be partially lost when read with the new schema. This change can only be considered when the system guarantees no producer sends multiple fields together and historical stored data already satisfies that invariant.

Before moving fields into a `oneof`:

1. Audit all producers and stored payloads.
2. Measure/verify whether any message contains multiple fields at once.
3. Deploy code that writes at most one member during a transition period.
4. Clean up or migrate old data containing multiple fields.
5. Change the schema only after the invariant is proven and guarded by tests.

Do not rely solely on the new generated builder automatically clearing the previous member; old producers may have already serialized payloads containing both fields.

## 7. Moving Fields Out of a oneof

Moving members out of a `oneof` turns them into independent fields in the new schema:

Schema v1:

```proto
message Contact {
  oneof contact_method {
    string email = 1;
    string phone = 2;
  }
}
```

Schema v2:

```proto
message Contact {
  string email = 1;
  string phone = 2;
}
```

Payloads produced under schema v1 have at most one member selected, so the v2 parser can read that field as an independent field. However, during a mixed-version period, a v2 producer might start sending both email and phone. A v1 consumer still treats the two fields as a `oneof`; if both appear on the wire, it keeps only whichever member is parsed last.

Consequently, moving fields out of a `oneof` is safe in a mixed-version system only if new producers maintain the invariant of sending at most one field until every old consumer has been upgraded. To send multiple fields simultaneously, wait until all consumers understanding the old schema are decommissioned, or introduce a new message/version with clear semantics.

Beyond wire behavior, the generated API also changes: v2 clients receive independent getters/setters instead of `getContactMethodCase()` and the old group methods. Code calling the generated API must be updated.

## 8. Renaming a Member or the oneof Group Name

The `oneof` group name and member names are not encoded directly into binary tags. If you only rename a member while keeping its field number, type, and semantics, that member's binary wire encoding stays unchanged.

Example:

```proto
message PaymentMethod {
  oneof method {
    string card_credential = 1;
    BankTransfer bank_transfer = 2;
  }

  reserved "card_token";
}
```

Renaming `card_token` to `card_credential` at number 1 preserves the binary tag, yet changes the generated Java API such as `getCardToken()` to `getCardCredential()`, and the corresponding case enum constant changes as well. Reserve the old name to prevent reuse.

Renaming the group `method` likewise does not alter member tags, but changes the accessor and case enum names generated for the group. This remains a source/API change for code using the generated classes.

JSON mapping uses member field names, not the `oneof` group name as a wrapper by default. Thus, renaming a member can change the JSON key. If the old JSON key must be preserved, consider `json_name` and test against the actual Protobuf JSON printer/parser or gateway.

## 9. Presence, Unknown Members, and Safe Handling

An application must distinguish three situations:

1. No member was sent.
2. A known member was sent with a default value, such as an empty string.
3. A new member was sent by another version, unknown to the current client.

In the generated API, case 1 normally returns `METHOD_NOT_SET`; case 2 returns the corresponding case such as `CARD_TOKEN` even if the getter returns an empty string. Case 3 can also return `METHOD_NOT_SET` on an old client, yet the binary payload contains an unknown field.

If case 3 needs diagnostics in Java, you can inspect the message's unknown fields for the field number known from the new schema, but reading unknown fields should not become the primary business contract. More reliable approaches are capability/version negotiation or designing explicit fallbacks.

For payment choices, access permissions, or transaction types, never interpret `METHOD_NOT_SET` as a default method authorized to execute a transaction. Return an appropriate domain error or require client/server version alignment.

Unknown fields can be lost when:

- Converting a Protobuf message to a DTO and constructing another message.
- Manually mapping only members known to the current generated code.
- Serializing through JSON with a parser that rejects or drops unfamiliar fields.
- A gateway or intermediary uses an old schema to rebuild the message.

If a service acts as a proxy, test round-trip behavior through the actual intermediary and format.

## 10. Testing oneof Changes Between Old and New Schemas

Compiling the new schema alone is insufficient. Keep generated types from schema v1 as fixtures and test both compatibility directions.

| Scenario | What to verify |
| --- | --- |
| v2 adds member → v1 parse | v1 sees `METHOD_NOT_SET`, does not crash; unknown field handled per policy |
| v1 old member → v2 parse | v2 receives the expected old member |
| v1 two independent fields → v2 moves into oneof | Confirm which member wins and whether data is lost |
| v2 drops oneof and sends both fields → v1 parse | v1 keeps only last member; tests prove producer omits dual fields while old readers exist |
| v2 renames member → v1 parse | Binary field number/type is still read accurately |
| v1 parse then re-serialize | Whether unknown member is preserved across the target runtime/intermediary |
| JSON/gateway | Whether old/new keys and unknown-field policies behave properly |

Example test for adding a new member:

```java
// PaymentMethodV2 has member wallet = 3.
// PaymentMethodV1 only knows card_token and bank_transfer.
PaymentMethodV2 newMessage = PaymentMethodV2.newBuilder()
    .setWallet(
        WalletPayment.newBuilder()
            .setWalletId("wallet-42")
            .build()
    )
    .build();

byte[] payload = newMessage.toByteArray();

PaymentMethodV1 oldMessage = PaymentMethodV1.parseFrom(payload);

assertEquals(
    PaymentMethodV1.MethodCase.METHOD_NOT_SET,
    oldMessage.getMethodCase()
);
```

Class names v1/v2 are illustrative. To keep the same Protobuf package/message identity while compiling old and new generated Java simultaneously, place fixtures in separate Java modules/packages or separate artifacts. Do not alter the wire package merely to avoid class collisions in tests.

In addition to message-level tests, run integration tests with old client/new server and new client/old server. Check RPC statuses, business fallbacks, and how old servers handle requests carrying new members.

## 11. Rollout Process for oneof Changes

A safe process separates schema changes from feature activation timing:

1. **Identify the change:** adding, removing, renaming, moving into, or moving out of `oneof`; list affected member numbers/types.
2. **Audit producers/consumers:** locate all clients, servers, jobs, queue consumers, and stored payloads.
3. **Protect wire identity:** keep numbers/types for existing members; use never-used numbers for new members.
4. **Prepare fallbacks:** old clients must handle unknown members safely; old servers must not receive requests with new members before supporting them.
5. **Roll out readers/servers:** deploy code capable of reading the new schema and handling the required options.
6. **Roll out writers/clients:** only after readers support it, enable sending new members or sending multiple fields after leaving a `oneof`.
7. **Migrate data:** clean up old payloads containing multiple fields if independent fields were moved into a `oneof`.
8. **Remove old members:** reserve numbers and names at the message level; retain reservations long-term.
9. **Observe:** monitor `METHOD_NOT_SET`, unknown fields, domain errors, parse errors, and fallback occurrences.

If you cannot guarantee the invariant that at most one field is sent, do not move independent fields into the same `oneof`. You can create a new message or add a new field/branch with a new number to represent the state without losing legacy data.

## 12. Review Checklist

- Existing members preserve field numbers, types, and semantics.
- New members use never-used numbers.
- Removed members have both numbers and names reserved at the message level.
- No `repeated` or `map` fields are placed directly inside `oneof`.
- Moving fields into `oneof` was checked against old payloads with multiple members set.
- Moving fields out of `oneof` preserves the single-field invariant while old consumers remain.
- Code handles `METHOD_NOT_SET`, default-valued members, and unknown members safely.
- Generated Java API changes have been updated in consumers.
- JSON keys, `FieldMask`, reflection, and intermediaries have been reviewed if used.
- Bidirectional v1/v2 fixtures and integration tests are in place.
- Readers are rolled out before writers when new requests or new semantics depend on server support.
- Schema lint/breaking checks ran against the released baseline.

In **SPRING_GRPC**, `oneof` is both a selection rule in the generated API and a factor in how the parser processes multiple fields on the wire. Adding a member can cause old clients to see `METHOD_NOT_SET`; moving independent fields into a `oneof` can drop values if old payloads contain multiple fields; moving fields out can cause old readers to retain only the last member. Evaluate wire behavior, source APIs, stored data, and rollout order before altering the schema.
