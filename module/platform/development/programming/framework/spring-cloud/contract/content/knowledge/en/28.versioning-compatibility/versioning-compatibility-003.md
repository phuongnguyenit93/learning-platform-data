# Renaming, Removing Fields, and Changing Data Types

## Lesson Objectives

In **Spring Cloud Contract**, producers and consumers agree on HTTP or messaging behavior using the **Groovy/YAML DSL**. Contract Verifier generates producer-side tests; stub artifacts let consumers verify their code via **Stub Runner**. One of the most common causes of API incompatibility is schema changes: **renaming fields, removing fields, or changing data types** in requests, responses, or message events.

These changes often look minor in code: renaming `name` to `displayName`, dropping a long-unused `legacyCode`, or switching `amount` from string to number. Yet consumers may depend on the field's name, type, null semantics, or unit. A new producer may compile and its generated producer tests may still PASS, while old consumers fail to deserialize the response or send requests that the producer rejects.

The lesson **"Renaming, Removing Fields, and Changing Data Types"** belongs to the **Versioning and Compatibility** chapter. It focuses on assessing impact by communication direction, organizing phased migrations, and using Spring Cloud Contract to verify supported consumer versions.

After this lesson, you will be able to:

- Distinguish compatible changes from breaking changes across **requests**, **responses**, and **message events**.
- Separately evaluate renames, field removals, type changes, requiredness changes, nulls, and units.
- Design an **expand – migrate – contract** strategy so multiple services can deploy independently.
- Use Jackson to support reading both old and new field names during the transition period.
- Write contract scenarios for producers and run consumer tests against stubs of relevant versions.
- Build a producer–consumer compatibility matrix and CI gates before removing old fields.
- Identify cases where "adding a field" can still break old consumers.

> **Core Principle:** Compatibility depends on data direction and actual consumer behavior. "Adding a field" is usually easier to make compatible than "changing a field type", yet not every consumer ignores unknown fields. No schema change should be assumed safe merely because the producer compiles.

## 1. Looking at Changes from Both Sender and Receiver Sides

An API has two directions:

- **Request:** the consumer sends data; the producer receives and deserializes it.
- **Response:** the producer sends data; the consumer receives and deserializes it.

Message events share the same relationship: the producer emits an event, and one or more consumers receive it. A change can be safe in one direction while breaking the other.

~~~mermaid
flowchart LR
    C["Consumer"] -->|"Request body"| P["Producer"]
    P -->|"Response body"| C
    P -->|"Message event"| M["Broker / destination"]
    M --> C2["Other consumer"]
~~~

For example, a consumer calls:

~~~http
POST /api/customers
Content-Type: application/json

{
  "customerId": "CUS-1001",
  "name": "An"
}
~~~

The producer returns:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "id": "CUS-1001",
  "name": "An"
}
~~~

If `name` is renamed to `displayName`, you must ask:

1. Does the producer still accept the old request?
2. Which response does the new producer return to old consumers?
3. Can new consumers read responses from the old producer?
4. Does any consumer store this field in a database, event, report, or business rule?
5. Is there a strict parser rejecting unknown fields?
6. Is there a message consumer subscribed to and processing old events?

**Never apply a single blanket "backward compatible" conclusion to both requests and responses.**

## 2. Schema Change Assessment Matrix

The following table serves as a practical guide; final outcomes depend on parsers, validation, contracts, and consumer versions.

| Change | Request to Producer | Response to Consumer | Common Risks |
| --- | --- | --- | --- |
| Add optional field | Usually compatible if producer ignores/accepts new field properly | Usually compatible if consumer ignores unknown fields | Strict unknown-field parser, validation |
| Add required field | Old consumers may omit it | Old consumers may not understand or lack a value | Missing data, deserialization |
| Rename field | New producer must continue accepting old name during transition | Old consumers still read old name | Missing property, null, validation fail |
| Remove field | New producer may reject old requests | Old consumers cannot find the field | Dependent business logic or DTOs |
| String → number | Old producer may reject numbers or coerce differently | Old consumers may fail to read number | Type mismatch, precision |
| Number → string | Old producer may fail to parse string | Old consumers may fail to parse string | Coercion hides bugs, lost semantics |
| Object → scalar/array | Old request shape no longer parses | Old consumer DTO no longer matches | Structural breaking change |
| Optional → required | Old consumers may not supply field | Producer must guarantee field is always present | 400/validation failure |
| Non-null → null | Request validation/logic may reject it | Consumer dereferences null | NullPointerException |
| Null → missing | Producer stops sending explicit null | Consumer distinguishes absent vs. null | Defaulting/patch semantics |
| Change unit/format | Producer misinterprets old values | Consumer misinterprets new data | Business bug even though type unchanged |

### Response and Request Changes Are Asymmetric

- For **requests**, the producer is the receiver. The new producer can support both old and new fields so consumers can roll out gradually.
- For **responses**, the consumer is the receiver. The new consumer can read both names, but the new producer must consider whether old consumers reject the new field.
- For **events**, consumers may deploy slowly and not upgrade simultaneously. Support for the old schema or a versioned destination is needed for a transition window.

## 3. Renaming a Field: Effectively Deleting One Name and Adding Another

Suppose the API currently returns:

~~~json
{
  "id": "CUS-1001",
  "name": "An"
}
~~~

The new version wants to use:

~~~json
{
  "id": "CUS-1001",
  "displayName": "An"
}
~~~

An old consumer may have this DTO:

~~~java
public class CustomerResponse {
    private String id;
    private String name;

    public String getId() { return id; }
    public String getName() { return name; }
    public void setId(String id) { this.id = id; }
    public void setName(String name) { this.name = name; }
}
~~~

If the producer removes `name` immediately, old consumers may receive `name == null`. If the consumer uses `name` as the order title, the display name vanishes even though the HTTP status is still 200.

**Renaming is not a cosmetic operation.** At the wire contract level, one old field was deleted and one new field was added.

### Mandatory Questions Before Renaming

- Which consumers are reading the old name?
- Do consumers have strict parsers for unknown fields?
- Do consumers use the old name in business logic or persistence?
- Are old consumers still sending the old name in requests?
- Can both names be retained during a transition period?
- If both cannot be retained, is a new API version or message version needed?

## 4. Strategy for Renaming a Field in a Request

Suppose consumers send `name` while the new producer wants to use `displayName`.

**The producer is the receiver of requests**, so rollout can proceed in this order:

1. Producer accepts both `name` and `displayName`.
2. New consumers gradually switch to sending `displayName`.
3. Monitor which requests still send `name`.
4. Once no supported consumer sends the old name, plan to deprecate `name`.
5. Remove the old alias after the deprecation period and verification.

### DTO Using Jackson to Read an Alias

~~~java
package com.example.customers.api;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class CreateCustomerRequest {

    private String customerId;

    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

With appropriate Jackson configuration:

- `displayName` is the primary property name.
- `name` is an accepted alias when deserializing requests.
- When serializing this object, the primary property is written as `displayName`.

**`@JsonAlias` supports alternative names when reading data**; it does not emit two fields in JSON output. Verify the behavior of your actual Jackson version and DTO accessors.

### What If a Request Sends Both Names?

For example:

~~~json
{
  "name": "An",
  "displayName": "Bình"
}
~~~

Do not rely on field ordering or "whichever field appears last wins" behavior. Define an explicit policy:

- Reject if both have different values.
- Or prefer the new name and record a metric for the old name.
- Or allow both only if their values are equal.

For important data, explicitly validate conflicts so you do not silently store the wrong name.

## 5. Strategy for Renaming a Field in a Response

For responses, **the consumer is the receiver**, so the producer must account for old consumers.

A transitional response might contain both:

~~~json
{
  "id": "CUS-1001",
  "name": "An",
  "displayName": "An"
}
~~~

This is safe for old consumers only if they **ignore unknown fields**. Some consumers configure Jackson strictly to reject unknown properties. In that case, adding `displayName` can still break old consumers.

### Two Options

**Option A — Old consumers are tolerant**

1. Deploy consumers capable of reading both `name` and `displayName` while the producer still sends only `name`.
2. Update all supported consumers.
3. Producer starts sending both fields.
4. New consumers prefer `displayName` and fall back to `name`.
5. Monitor usage of the old field.
6. After all consumers have migrated, the producer stops sending `name`.
7. Once no old producer responses remain, consumers can remove the fallback.

**Option B — Old consumers are strict**

If old consumers reject unknown fields, you cannot assume dual-write is safe. You can:

- Upgrade all strict consumers before the producer adds the new field.
- Separate endpoint versions `/v1` and `/v2`.
- Use media type/version negotiation.
- For events, emit the new schema on a separately versioned destination/topic.

Do not add a new field to a shared response without knowing how old consumers' parsers handle unknown fields.

## 6. Consumers Can Read Both Old and New Names

A consumer DTO can use `@JsonAlias`:

~~~java
package com.example.checkout.api;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class CustomerView {

    private String id;

    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

This consumer can deserialize both the old response `{"name":"An"}` and the new response `{"displayName":"An"}`, provided Jackson is compatibly configured.

### Testing Both Data Forms

~~~java
@Test
void readsLegacyName() throws Exception {
    CustomerView view = objectMapper.readValue(
        "{\"id\":\"CUS-1001\",\"name\":\"An\"}",
        CustomerView.class
    );

    assertThat(view.getDisplayName()).isEqualTo("An");
}

@Test
void readsNewDisplayName() throws Exception {
    CustomerView view = objectMapper.readValue(
        "{\"id\":\"CUS-1001\",\"displayName\":\"An\"}",
        CustomerView.class
    );

    assertThat(view.getDisplayName()).isEqualTo("An");
}
~~~

These are **unit tests for deserialization**. Add consumer integration tests using stub artifacts to prove the HTTP client and business code actually work with producer responses.

## 7. Removing a Field: Check Both Direct and Indirect Dependencies

A field may be used in many places within a consumer:

- Deserialized into a DTO.
- Stored in a database or cache.
- Used in an `if`/`switch` condition.
- Forwarded to another service.
- Included in a message/event.
- Exported to reports or audit logs.
- Used to construct an idempotency key.
- Used as input for rules/feature flags.

For example, the producer wants to remove `legacyCode`:

~~~json
{
  "id": "CUS-1001",
  "name": "An",
  "legacyCode": "C-7788"
}
~~~

New response:

~~~json
{
  "id": "CUS-1001",
  "name": "An"
}
~~~

An old consumer may still compile because its DTO contains `legacyCode`, yet receive `null`. The bug may appear only when business logic executes.

### Removing a Field Can Be Breaking Even When Consumer Deserialization Succeeds

For example:

~~~java
if ("VIP".equals(customer.getLegacyCode())) {
    applyPriorityShipping();
}
~~~

If the field disappears, the condition no longer evaluates to true. The HTTP request/response still succeeds, yet business behavior has changed.

**You must audit actual field usage impact, not just compilation/deserialization.**

## 8. Safe Field Removal Process

Follow this process:

1. **Discover:** locate consumers and data flows depending on the field.
2. **Deprecate:** announce that the field will be retired, specifying timeline and replacement.
3. **Observe:** measure request usage or consumer response telemetry if available.
4. **Migrate:** move consumers to the replacement field.
5. **Verify:** run consumer tests against the new producer stub and assert business outcomes.
6. **Remove:** stop sending/accepting the old field after supported consumers have migrated.
7. **Clean up:** delete unused DTO properties, matchers, fixtures, mappings, and documentation.

### Do Not Rely Only on Request Logs

For requests, the producer can count how many requests still contain `legacyCode`. For responses, the producer cannot tell whether consumers read a field merely by sending the response. You need consumer-side telemetry, a consumer inventory, or an owner-backed migration deadline.

If reliable telemetry is unavailable, require a **consumer list and migration confirmation** before deletion.

## 9. Changing Data Types: Same Field Name Does Not Mean Same Contract

Example:

**V1 — `amount` is a string**

~~~json
{
  "orderId": "ORD-1001",
  "amount": "125000"
}
~~~

**V2 — `amount` is a number**

~~~json
{
  "orderId": "ORD-1001",
  "amount": 125000
}
~~~

An old consumer DTO:

~~~java
public class OrderResponseV1 {
    private String orderId;
    private String amount;
    // getters/setters
}
~~~

A new consumer might define `BigDecimal amount`. Yet if the producer changes the type directly on the same field, old consumers may:

- Reject it due to a type mismatch.
- Coerce the number to a string depending on Jackson settings.
- Parse it with different semantics.
- Lose precision if using `double` instead of an appropriate decimal type.

**Do not rely on implicit coercion to claim compatibility.** Contracts must assert the exact JSON type.

## 10. Use a New Field When Changing Types

Instead of changing the type under the same name, you can expand the schema:

~~~json
{
  "orderId": "ORD-1001",
  "amountText": "125000",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

The name `amountMinor` should clearly express the unit (e.g., VND, cents, minor unit) per domain. Avoid an ambiguously named new field if consumers cannot tell how to interpret it.

Workflow:

1. Consumers support reading both new and old fields.
2. Producer adds the new field while keeping the old field during transition.
3. New consumers prefer the new field.
4. Verify consistency between the two fields according to published rules.
5. Monitor old consumers.
6. Retire the old field after the deprecation window.

As with renaming, **dual-write is safe only if old consumers do not reject the new field**. If parsers are strict, migrate consumers first or version the response/event.

## 11. Data Types Can Change Semantics Even When JSON Type Stays Identical

Some changes cannot be caught by simple type checks:

| Field | Before | After | Risk |
| --- | --- | --- | --- |
| `amount` | VND | Thousands of VND | Both are numbers, yet unit changed |
| `createdAt` | ISO-8601 UTC | Local time string | Timezone/offset lost |
| `duration` | Seconds | Milliseconds | Value off by 1,000x |
| `status` | `PAID` | `SETTLED` | Enum/business state changed |
| `phone` | E.164 | Free-form string | Validation and normalization |
| `id` | String keeping leading zeros | Number | Leading zeros lost |
| `percentage` | 0–100 | 0–1 | Same number, different semantics |
| `amount` | Exact decimal | Floating point | Calculation rounding errors |

### Timestamp Example

V1:

~~~json
{"createdAt":"2026-11-24T09:30:00Z"}
~~~

V2:

~~~json
{"createdAt":1795512600000}
~~~

Both may represent the same instant, yet differ in JSON type and unit. Old consumers expecting an ISO string may fail or misinterpret it.

If a transition is needed, introduce a clearly named new field:

~~~json
{
  "createdAt": "2026-11-24T09:30:00Z",
  "createdAtEpochMillis": 1795512600000
}
~~~

The epoch value must be computed accurately from the published instant and timezone. Do not copy an example number and treat it as a valid timestamp without verifying it.

## 12. Changing Nullability, Optionality, and Requiredness

These three responses are different:

~~~json
{"middleName": null}
~~~

~~~json
{}
~~~

~~~json
{"middleName": ""}
~~~

- **Explicit null:** the field is present with no value.
- **Missing:** the field does not appear.
- **Empty string:** the field contains an empty string.

Consumers may handle them differently. For example, a PATCH API might interpret missing as "no change", null as "clear the value", and empty string as "set empty string".

### Changes Requiring Evaluation

- Optional → required: old consumers may omit the request field.
- Required → optional: producer/consumer must define fallback/default behavior.
- Non-null → nullable: consumers may dereference null.
- Null → omitted: consumers may apply a different default.
- Empty → null: may alter validation/business rules.

Do not treat `@JsonInclude(NON_NULL)` as a harmless formatting tweak if consumers depend on explicit nulls.

## 13. Changing Objects, Arrays, and Enums

### Object Changed to Array

V1:

~~~json
{
  "address": {
    "city": "HCMC",
    "country": "VN"
  }
}
~~~

V2:

~~~json
{
  "address": [
    {"city": "HCMC", "country": "VN"}
  ]
}
~~~

A consumer DTO with an `Address` field cannot by default deserialize a JSON array into an object. This is a structural breaking change.

### Enum Adding a Value

The producer adds `REFUNDED` to the `status` field. A consumer using an exhaustive switch or strict enum parser may fail even though the JSON type is still a string.

Check how the consumer handles **unknown enum values**. A fallback such as `UNKNOWN` can be used if semantics allow, but never silently map every new state into an existing business state.

### Collection Changes

- Object to array.
- Array to object.
- Nullable/empty-allowed array changed to requiring at least one element.
- Changing meaningful ordering of an array.
- Changing element type.

All of these must be specified and tested as schema changes, not merely DTO refactors.

## 14. Distinguishing Compatibility by Request/Response Direction

The following table helps prevent false conclusions:

| Change | New Producer Receiving Request from Old Consumer | Old Consumer Reading Response from New Producer |
| --- | --- | --- |
| Add optional field | Potentially compatible if producer accepts old requests | Potentially compatible if consumer ignores unknown fields |
| Rename field | Needs alias/dual-read of old name | Needs producer to keep old name or consumer to support both |
| Remove field | May fail if producer still requires old field | Consumer may receive null/missing and break logic |
| Change type | May fail deserialization or coerce | May fail deserialization or misinterpret |
| Optional to required | Old consumer omits field | New producer omitting field may break consumer |
| Nullability change | Validation may reject old requests | Consumer may dereference null |

**A change is compatible only when both sides involved have behavior supporting it throughout the deployment window.**

## 15. Event/Message Schemas Require Extra Caution

With HTTP, you can version endpoints or adjust header negotiation. With messaging, consumers may process events slowly, replay from a broker, or receive old events for a long time.

Old event example:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "CUSTOMER_UPDATED",
  "name": "An"
}
~~~

New event:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "CUSTOMER_UPDATED",
  "displayName": "An"
}
~~~

If old consumers still subscribe to the same topic with a strict parser, dual-write can break them. Options:

- Deploy tolerant consumers first.
- Keep the old field in events until consumers have migrated.
- Use a versioned event type or a new destination.
- Controlled dual-publishing with duplicate/idempotency handling.
- Enforce schema registry/policies if the messaging platform uses a schema registry.

### Event Replay Makes Deprecation Harder

Consumers may replay old events months later. Removing the field from new consumer code can prevent old replays from deserializing. Determine **retention, replay windows, and archives** before dropping old schema support.

Never assume an event published today is only processed today.

## 16. Versioning APIs and Events When Safe Transition Is Not Possible

When a change is too large, versioning can be cleaner than dual-read/dual-write.

HTTP example:

~~~text
GET /api/v1/customers/CUS-1001
GET /api/v2/customers/CUS-1001
~~~

V1 response:

~~~json
{
  "id": "CUS-1001",
  "name": "An"
}
~~~

V2 response:

~~~json
{
  "id": "CUS-1001",
  "displayName": "An"
}
~~~

For events:

~~~text
customers.updated.v1
customers.updated.v2
~~~

Or explicit event type/version inside the payload:

~~~json
{
  "eventType": "CUSTOMER_UPDATED",
  "schemaVersion": 2,
  "displayName": "An"
}
~~~

### Choosing a Versioning Strategy

| Strategy | Suitable When | Cost |
| --- | --- | --- |
| Dual-read/dual-write | Small changes, tolerant consumers | Transitional code and cleanup |
| Versioned endpoint | HTTP clients need independent migration | Maintaining multiple routes |
| Versioned media type | API already uses content negotiation | Client/server must support negotiation |
| Versioned topic/event type | Message consumers deploy slowly | Multiple destinations/consumer groups |
| New field alongside old | Extensible schema | Larger payload, needs deprecation |

You do not need to version every optional field addition. However, if the same field changes type or semantics, **a new field/new version** is usually easier to manage than an in-place silent change.

## 17. YAML Contracts for Old and New Responses

V1 contract example:

~~~yaml
description: "V1 returns customer name via the name field"
name: get_customer_v1
request:
  method: GET
  url: /api/v1/customers/CUS-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: CUS-1001
    name: An
~~~

V2 contract:

~~~yaml
description: "V2 returns customer name via the displayName field"
name: get_customer_v2
request:
  method: GET
  url: /api/v2/customers/CUS-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: CUS-1001
    displayName: An
~~~

These two contracts illustrate two versioned endpoints. If your project uses the same endpoint with dual-write, write scenarios matching actual behavior instead of copying both V1/V2 endpoints if the API does not provide them.

### What Does Producer Verification Check?

Generated producer tests will verify:

- V1 still returns the `name` field while V1 is supported.
- V2 returns the `displayName` field.
- Fields and JSON types match the contract.
- Endpoints/methods/statuses/headers match.

If the producer already removed the V1 route, the V1 contract test must FAIL — that is an intentional signal to handle per the deprecation plan, not to delete the test just to make CI green.

## 18. Request Contracts: Producer Must Accept the Old Name During Transition

A V1 request:

~~~yaml
description: "Create customer with legacy name field"
name: create_customer_legacy_name
request:
  method: POST
  url: /api/customers
  headers:
    Content-Type: application/json
  body:
    customerId: CUS-1001
    name: An
response:
  status: 201
  body:
    id: CUS-1001
~~~

A V2 request:

~~~yaml
description: "Create customer with new displayName field"
name: create_customer_display_name
request:
  method: POST
  url: /api/customers
  headers:
    Content-Type: application/json
  body:
    customerId: CUS-1002
    displayName: Bình
response:
  status: 201
  body:
    id: CUS-1002
~~~

When the producer supports both, both producer scenarios must PASS. This proves the server accepts both agreed request forms.

### If the Producer Accepts Only the New Name

The generated V1 test will fail when sending `name`. If old supported consumers remain, this is a breaking change. Do not remove the V1 contract until a deprecation decision and confirmed consumer inventory are in place.

## 19. Contracts for Data Type Changes

V1:

~~~yaml
description: "V1 returns amount as a string"
name: get_order_v1
request:
  method: GET
  url: /api/v1/orders/ORD-1001
response:
  status: 200
  body:
    id: ORD-1001
    amount: "125000"
    currency: VND
~~~

V2 uses a new field and explicit semantics:

~~~yaml
description: "V2 returns amountMinor as an integer"
name: get_order_v2
request:
  method: GET
  url: /api/v2/orders/ORD-1001
response:
  status: 200
  body:
    id: ORD-1001
    amountMinor: 125000
    currency: VND
~~~

In the V2 example, `amountMinor`'s unit must be clearly defined in API documentation. Do not assume `125000` always means 125,000 VND if the domain has other minor units.

### Contract Tests Must Distinguish JSON Types

The following bodies are different:

~~~json
{"amount":"125000"}
~~~

~~~json
{"amount":125000}
~~~

If an old consumer expects a string and the new producer returns a number at the same field, the V1 consumer contract must be kept to catch the breaking change until the consumer upgrades or a new API version is chosen.

## 20. Consumer Contract Tests with Stub Runner

Producer-generated tests verify **the producer fulfills the contract**. Consumer tests must verify **consumer code works with the producer's stubs**.

An HTTP consumer test example configuring Stub Runner:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.customers:customer-service:2.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CustomerClientContractTest {

    @Autowired
    private CustomerClient customerClient;

    @Test
    void readsCustomerDisplayName() {
        CustomerView view =
            customerClient.getCustomer("CUS-1001");

        assertThat(view.getDisplayName()).isEqualTo("An");
    }
}
~~~

This is an **illustrative skeleton**; it requires client wiring, endpoint/port matching Stub Runner, imports, and project test dependencies. The stub must contain a mapping matching the request sent by the client.

### Testing Multiple Stub Generations

During migration, a new consumer may need to run against:

- Old producer stub (`name` field).
- Transitional producer stub (both `name` and `displayName` if consumer tolerance allows).
- New producer stub (`displayName` field).

The goal is to confirm the dual-reading consumer actually handles every still-supported version. Testing only against the new stub will not catch a consumer that lacks a fallback for the old producer.

## 21. Producer–Consumer Compatibility Matrix

A simple matrix for a response rename:

| Producer Response | Old Consumer Reading Only `name` | New Consumer Reading Both |
| --- | --- | --- |
| Old producer (`name` only) | PASS | PASS |
| Dual-write producer | PASS if consumer tolerates unknown fields | PASS |
| New producer (`displayName` only) | FAIL | PASS |

If the old consumer is strict on unknown fields, the dual-write cell may **FAIL**. In that case, upgrade strict consumers before the producer emits the extra field, or use a versioned endpoint/topic.

### Matrix for a Request Rename

| Consumer Request | Old Producer Accepting Only `name` | New Producer Accepting Both | New Producer Accepting Only `displayName` |
| --- | --- | --- | --- |
| Old consumer sends `name` | PASS | PASS | FAIL |
| New consumer sends `displayName` | FAIL | PASS | PASS |

These two matrices show why you must **migrate in the direction of data flow**. A single rollout order cannot fit every scenario.

## 22. The Expand – Migrate – Contract Process

This is the rollout strategy for schema changes when producer and consumers do not deploy simultaneously.

~~~mermaid
flowchart TD
    A["Current: only old field"] --> B["EXPAND: support old + new"]
    B --> C["MIGRATE: consumers switch to new field"]
    C --> D["OBSERVE: no supported consumer uses old field"]
    D --> E["CONTRACT: remove old field"]
    E --> F["Verify old contracts retired intentionally"]
~~~

### For a Request Rename

1. **Expand producer:** accept both old and new names.
2. **Migrate consumers:** update request DTOs/clients to send the new name.
3. **Observe:** count requests still using the old name.
4. **Contract producer:** stop accepting the old name once consumers have migrated.
5. Delete the alias and V1 request contract per deprecation policy.

### For a Response Rename

1. **Migrate consumers first:** consumers read both old and new names while the producer still sends only the old name.
2. Verify all strict consumers have been upgraded.
3. **Expand producer:** start sending the new name; optionally retain the old name during dual-write.
4. **Migrate consumers:** shift business logic to prefer the new name.
5. **Observe:** verify supported consumer versions are reading the new field.
6. **Contract producer:** stop sending the old name.
7. Once no old supported producers remain, consumers can remove the fallback.

If consumers are strict on unknown fields, do not enable dual-write before upgrading them or switching to a separate API version.

### For a Type Change

1. Add a new field with explicit type/semantics.
2. Consumers read both old and new fields.
3. Producer emits both if old consumers are tolerant; otherwise, version it.
4. Consumers migrate to the new field.
5. Monitor usage and reconcile values between the two fields.
6. Retire the old field after migration completes.

**Do not change a field's type in-place while old consumer versions are still supported**, unless a clear version negotiation mechanism exists.

## 23. Monitoring Usage and Deprecation

Do not delete a field simply because you updated your DTO. Gather evidence:

- Request metrics for the old field: is any consumer still sending it?
- Consumer inventory: which services deserialize or use the old field?
- Event replay policy: can old events still be replayed?
- Consumer release versions: are old versions still running?
- Logs/metrics: can you observe the fallback path?
- API owners: who approves the end-of-support date?

### Measuring Fallback Usage on the Consumer

A dual-reading consumer can record a metric:

~~~java
if (requestUsesLegacyName) {
    migrationMetrics.incrementLegacyNameUsage();
}
~~~

This is illustrative pseudocode; metrics should avoid logging PII or high-cardinality values. The goal is to count **hits on the legacy compatibility path**, not to log customer names.

### Deprecation with Owner and Deadline

A deprecation plan should document:

- Old field and replacement field.
- Producer/consumer owners.
- Warning start date.
- Minimum version required to upgrade.
- Observation period with zero usage.
- Plan for handling non-migrating consumers.
- Removal date and rollback strategy.

If consumer usage cannot be measured reliably, use a versioned API/event or a clearly agreed support window.

## 24. Message Contracts and Schema Evolution

For events, a schema version can be added:

~~~yaml
description: "Customer updated event V2"
label: customer_updated_v2
outputMessage:
  sentTo: customers.updated.v2
  headers:
    contentType: application/json
  body:
    eventId: EVT-CUS-1001
    eventType: CUSTOMER_UPDATED
    schemaVersion: 2
    customerId: CUS-1001
    displayName: An
~~~

An older message contract can continue describing V1:

~~~yaml
description: "Customer updated event V1"
label: customer_updated_v1
outputMessage:
  sentTo: customers.updated.v1
  headers:
    contentType: application/json
  body:
    eventId: EVT-CUS-1001
    eventType: CUSTOMER_UPDATED
    schemaVersion: 1
    customerId: CUS-1001
    name: An
~~~

### A Version Field Does Not Create Compatibility by Itself

`schemaVersion: 2` is meaningful only if producers/consumers actually route or process by version. It does not magically make an old parser accept a new payload.

For message migration, you can:

- Keep consumers supporting V1 and V2.
- Use a separate topic/destination for V2.
- Perform controlled dual-publishing during transition.
- Ensure idempotency when the same business action is emitted across two event versions.
- Retain V1 replay logic for the required duration.

Do not dual-publish without a deduplication strategy; consumers may process the same business event twice.

## 25. Situations Where Dual-Write Should Not Be Used

Dual-write is useful, but not always safe:

- Old consumers are strict on unknown fields.
- New and old fields have different semantics and cannot represent the same value.
- The old field contains PII no longer permitted to be emitted.
- Large data substantially increases payload size/cost.
- The producer cannot guarantee consistency between the two fields.
- Event replay causes both schemas to persist longer than the migration period.
- Security policies forbid retaining the old field.

In these cases, consider **versioned endpoints, media types, topics, or event types**. If the old field must be removed immediately due to security/privacy, execute an urgent migration plan in coordination with consumer owners; do not prolong deprecation merely for convenience.

## 26. Common Anti-Patterns

| Anti-Pattern | Consequence | Better Approach |
| --- | --- | --- |
| Rename field and deploy producer first | Old consumers receive null/missing | Producer dual-reads for requests; consumer dual-reads first for responses |
| Delete field because "nobody seems to use it" | Misses indirect consumers | Inventory and telemetry |
| Change string to number on same field | Old consumers fail to parse or coerce wrongly | New field or versioned contract |
| Add response field without checking strict parsers | Old consumers reject unknown property | Upgrade consumers first or version |
| Use default values to hide missing fields | Business logic receives fake data | Distinguish missing/null and validate |
| Keep aliases forever | Confusing contracts and DTOs | Deprecation owner/deadline |
| Test only the new producer | Unknown whether old consumers can read it | Consumer matrix against new stub |
| Test only new consumer against new stub | Fails to catch missing fallback for old producer | Test old and new stubs |
| Delete V1 contract to turn CI green | Loses regression proof | Approved retirement after migration |
| Emit both old and new fields without precedence | Contradictory payload | Validate consistency |
| Dual-publish events without idempotency | Business logic executes twice | Event ID/deduplication |
| Change unit while keeping field name/type | Business calculation errors | New field name/semantics, documentation, and tests |

## 27. End-to-End Migration Example

Suppose Customer Service returns `name` and wants to migrate to `displayName`.

### Initial State

Producer response:

~~~json
{"id":"CUS-1001","name":"An"}
~~~

Consumer V1 DTO has only `name`.

### Phase A — Upgrade Consumers First

Consumer V2 DTO:

~~~java
public class CustomerView {
    private String id;

    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;

    // getters/setters
}
~~~

Consumer V2 still works with the old producer response. Consumer tests against stub V1 must PASS.

### Phase B — Producer Dual-Write

Producer response:

~~~json
{
  "id": "CUS-1001",
  "name": "An",
  "displayName": "An"
}
~~~

Consumer V2 reads `displayName` and falls back to `name`. Strict-parser V1 consumers must be upgraded first or given a separate V1 route.

### Phase C — Consumer Migration

Consumer business logic uses only `displayName`. Fallback metrics for `name` drop to zero across supported consumers.

### Phase D — Producer Drops the Old Field

Producer response:

~~~json
{
  "id": "CUS-1001",
  "displayName": "An"
}
~~~

Generated producer tests for the new contract PASS. Consumer V2 tests against the new stub PASS.

### Phase E — Clean Up Consumer Fallback

Once no V1 or dual-write producers remain within supported scope, consumers can remove `@JsonAlias("name")` and legacy tests. Clearly record the date the V1 contract was retired.

**Do not skip Phase A if V1 consumers are still strict**: adding `displayName` in a dual-write response can break old consumers before they have a chance to migrate.

## 28. Verifying Type Changes with Consumer Tests

Suppose the producer adds `amountMinor` while keeping string `amount`.

Consumer V2 can support:

~~~java
public class OrderView {
    private String orderId;
    private String amount;

    @JsonProperty("amountMinor")
    private Long amountMinor;

    public long effectiveAmountMinor() {
        if (amountMinor != null) {
            return amountMinor;
        }
        return Long.parseLong(amount);
    }

    // getters/setters
}
~~~

This is only a simplified example. In production, you must:

- Define currency/unit.
- Check for overflow.
- Specify rounding/scale.
- Handle null/missing/invalid strings.
- Never parse an invalid value and silently default to zero.
- Include clear validation and error handling.

Consumer tests should run against:

- Stub V1 containing only `amount`.
- Transitional stub containing both `amount` and `amountMinor`.
- Stub V2 containing only `amountMinor` if the consumer must support V2.

If the consumer only needs to support V2 after a major release, state that compatibility boundary explicitly instead of keeping fallbacks indefinitely.

## 29. Catching Breaking Changes in CI

~~~mermaid
flowchart TD
    A["PR changes DTO/contract"] --> B["Review schema diff"]
    B --> C["Classify request/response/message"]
    C --> D["Producer generated contract tests"]
    D --> E{"Old + new scenarios PASS?"}
    E -->|No| X["BLOCK / migration incomplete"]
    E -->|Yes| F["Package immutable stub artifact"]
    F --> G["Consumer matrix: old/new consumers"]
    G --> H{"Required consumer cells PASS?"}
    H -->|No| X
    H -->|Yes| I["Telemetry/deprecation gate"]
    I --> J{"Old field usage = 0 in supported scope?"}
    J -->|No| K["Keep compatibility path"]
    J -->|Yes| L["Approve contract/removal"]
~~~

### Producer CI

- Generate and run contract scenarios for both old and new fields during transition.
- Verify JSON types, null/missing behavior, and field presence.
- Ensure the producer accepts old/new requests where committed.
- Verify responses/events still include fields needed by old consumers.
- Record producer commit and contract revision.

### Consumer CI

- Run consumer code against the old producer stub.
- Run consumer code against the transitional producer stub.
- Run consumer code against the new producer stub.
- Assert business outcomes, not merely successful deserialization.
- Clearly mark which consumer versions remain supported.
- Never reuse stub caches/SNAPSHOTs with different bytes without recording provenance.

### Removal Gate

Do not remove an old field if:

- Any supported consumer still uses it.
- The old contract is still an acceptance criterion.
- The message replay window has not ended.
- Sufficiently reliable telemetry/inventory is missing.
- Rollback cannot restore the old response/schema.

## 30. Sample Rollout Matrix

A migration record can be designed by the team:

~~~yaml
change:
  field_old: name
  field_new: displayName
  direction: response
  producer: customer-service

compatibility:
  old_producer_old_consumer: PASS
  old_producer_new_consumer: REQUIRED
  dual_write_producer_old_consumer: CHECK_UNKNOWN_FIELD_POLICY
  dual_write_producer_new_consumer: REQUIRED
  new_producer_new_consumer: REQUIRED

migration:
  consumers_dual_read_deployed: false
  producer_dual_write_enabled: false
  legacy_usage_observed: true
  removal_approved: false
~~~

This is **team-defined migration metadata**, not a default Spring Cloud Contract configuration file. Values must be updated from real CI results, telemetry, and owner approvals.

### Do Not Treat `NOT_RUN` as `PASS`

In the matrix, unexecuted cells must be marked `NOT_RUN` or `BLOCKED`. Never mark PASS simply because a consumer team has not yet provided tests.

## 31. PR Review Process for Renames, Removals, or Type Changes

Reviewers should ask:

1. Is the field in a request, response, or event?
2. Which consumers use the old field?
3. Does the change alter JSON type or semantics?
4. Are there strict unknown-property deserializers?
5. Is missing/null/default behavior defined?
6. Is compatibility preserved with old producer/consumer versions?
7. Do old contract scenarios still run?
8. Do consumer Stub Runner tests use the exact new stub?
9. If dual-writing, are both fields consistent?
10. If dual-publishing, is idempotency protected?
11. Does telemetry prove the old field is no longer used?
12. Are owner, deadline, and rollback strategy defined?

A PR that updates only DTOs without updating contract/consumer tests can miss breaking changes. Conversely, a PR that deletes old contracts just to make tests PASS is not proof that migration is complete.

## 32. Practice Exercises

### Exercise A — Renaming a Response Field

The producer renames `name` to `displayName`. Old consumers only have the `name` field.

**Task:** describe at least two safe rollout approaches and the preconditions for each.

**Hint:** consumer dual-read first; producer dual-write if old consumers are tolerant; or endpoint versioning if consumers are strict.

### Exercise B — Renaming a Request Field

Old consumers send `name`; new consumers send `displayName`.

**Task:** in what order must the producer roll out?

**Hint:** producer accepts both first, then migrate consumers, measure legacy usage, and finally remove the alias.

### Exercise C — Removing a Response Field

The producer wants to delete `legacyCode`, yet one consumer uses it to decide shipping priority.

**Task:** why is successful compilation insufficient? What evidence must be collected?

**Hint:** consumer/business usage inventory, consumer tests, telemetry, and owner confirmation.

### Exercise D — String to Number

`amount` changes from `"125000"` to `125000`.

**Task:** list consumer failure modes and propose a schema transition.

**Hint:** type mismatch/coercion/precision; a new field with explicit unit or a new API version.

### Exercise E — Adding a Response Field

The producer adds `displayName`, but an old consumer enables strict unknown properties.

**Task:** why can adding a field still be breaking? Propose a rollout.

**Hint:** upgrade consumers to be tolerant first, or split into a versioned endpoint.

### Exercise F — Null to Missing

The producer changes `middleName: null` to omitting the field altogether.

**Task:** find a business semantics example where the two cases differ.

**Hint:** PATCH, defaulting, explicit clear, and fallback logic.

### Exercise G — Changing Units Without Changing Type

`duration` remains a number but changes from seconds to milliseconds.

**Task:** can a type-only contract test detect this? What should be added?

**Hint:** semantic/value ranges, a new field or versioned documentation; specific unit tests.

### Exercise H — Event Replay

A new consumer drops the `name` field, yet the broker/archive still contains V1 events being replayed.

**Task:** what time windows must the migration account for?

**Hint:** retention, replay window, consumer version support, and V1 schema handler.

### Exercise I — Dual-Write and Strict Parser

The producer emits both `name` and `displayName`. An old consumer rejects unknown fields.

**Task:** should dual-write be enabled?

**Hint:** not before strict consumers are upgraded or a separate route/version exists.

### Exercise J — Consumer Matrix

There are three consumer versions: Checkout 1.8, Checkout 2.0, and Portal 4.1. The producer is about to remove `legacyCode`.

**Task:** design a test matrix and criteria for removing the field.

**Hint:** each supported consumer version runs against the new stub; `NOT_RUN` is not `PASS`; require telemetry/inventory.

### Exercise K — Conflicting Request Aliases

A request contains both `name` and `displayName` with different values.

**Task:** design a validation policy.

**Hint:** reject conflicts or define explicit precedence; never rely on JSON property order.

### Exercise L — Expanding an Enum

The producer adds status `REFUNDED`. An old consumer parses enums strictly.

**Task:** is this a data type change? Can it break consumers?

**Hint:** JSON type remains string, yet the value set changed; test unknown enum handling.

## 33. Checklist Before Removing an Old Field or Changing Schema

### Impact Assessment

- [ ] Identified whether the field is in a request, response, or message event.
- [ ] Identified all supported consumers and versions.
- [ ] Checked direct and indirect field usage in business logic.
- [ ] Distinguished missing, null, and empty fields.
- [ ] Checked strict/lenient deserialization in consumers.
- [ ] Verified type, format, unit, precision, and enum semantics.
- [ ] Checked retention/replay windows if the field belongs to an event.

### Migration Design

- [ ] Added a new field or versioned endpoint/topic if semantics/type change significantly.
- [ ] Producer accepts both old and new request names before consumers send the new name.
- [ ] Consumers dual-read before the producer changes the response.
- [ ] Dual-write enabled only when old consumers tolerate unknown fields.
- [ ] If strict consumers exist, planned version routing or upgrading consumers first.
- [ ] Defined a policy for requests sending both fields simultaneously.
- [ ] Assigned owner, deadline, telemetry, and rollback plan.
- [ ] No dual-publishing of events without an idempotency strategy.

### Contracts and Testing

- [ ] Producer contracts describe old and new requests/responses/events during transition.
- [ ] Generated producer tests verify field names and JSON types.
- [ ] Consumer Stub Runner tests use the exact stub versions.
- [ ] Old and new consumer versions run in the compatibility matrix.
- [ ] Business assertions verify outcomes, not just successful deserialization.
- [ ] Negative tests catch missing/wrong-type/null/unknown-enum cases where appropriate.
- [ ] Stub artifacts have traceable versions, contract revisions, and checksums.
- [ ] Old contracts are retired only after approval, never deleted just to turn CI green.

### Conditions for Field Removal

- [ ] No supported consumer depends on the old field.
- [ ] Request usage/consumer telemetry has been evaluated.
- [ ] Message replay window and archive requirements have expired or been handled.
- [ ] Required consumer versions PASS against the new schema.
- [ ] Rollback and deprecation completion are documented.
- [ ] CI gate blocks if any required compatibility cell has not run.

## Conclusion

Renaming fields, removing fields, and changing data types are **wire contract** changes, not mere DTO refactors. They must be evaluated by request/response/message direction, parser behavior, and actually active consumer versions. In particular, even adding a new field can break strict consumers; changing types can let parser coercion hide semantic errors; and deleting a field can break business logic even while HTTP still returns 200.

With Spring Cloud Contract, retain old scenarios during migration, add scenarios for the new schema, run generated producer tests, package stub artifacts with provenance, and verify consumer versions using Stub Runner. Remove old fields only when **consumer inventory, telemetry, contract tests, and owner approval** all confirm migration is complete.

**Key Takeaway:** *Producers accept old/new requests before consumers switch; consumers read old/new responses before producers change; type or semantic changes deserve explicit fields/versions; and old compatibility paths are removed only after every supported consumer is verified.*
