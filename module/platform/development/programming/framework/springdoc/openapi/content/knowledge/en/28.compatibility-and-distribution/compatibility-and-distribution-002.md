# Renaming, Removing, or Adding Required Properties

Changing a property in OpenAPI can directly impact clients sending requests or reading responses. Three common operations are renaming a property, removing a property, and changing the list of required properties. They may look minor in a Java DTO, yet they can break deserialization, validation, client SDK generation, or contract testing.

To evaluate compatibility accurately, determine whether the property is on the request or response side, who is making the change, and in which direction old clients/servers interact with the new version. Adding an optional field to a response is usually easy to keep compatible with old clients, whereas adding a required field to a request can cause every client not yet sending that field to be rejected. Renaming is essentially removing the old name and adding a new name, so it usually requires a transition period.

This lesson uses the OpenAPI Schema Object and Spring Boot examples to build a framework for evaluating changes. The goal is to help API publishing teams create clear migration plans, verify them with contract tests, and avoid breaking active clients.

## 1. What is a property in an API contract?

In a JSON object, a property is a name-value pair. For example:

~~~json
{
  "id": "ORD-1001",
  "customerName": "An",
  "note": "Deliver during business hours"
}
~~~

This object has three properties: `id`, `customerName`, and `note`. OpenAPI describes them in a Schema Object:

~~~yaml
type: object
properties:
  id:
    type: string
  customerName:
    type: string
  note:
    type: string
~~~

The schema describes which properties are allowed or expected in a payload. The `required` list at the object level determines which properties must appear. If a property is not in `required`, JSON Schema treats it as optional by default.

Changing a property can affect:

- Request bodies sent by clients to the server.
- Response bodies returned by the server to clients.
- Object-style parameters, such as query parameters grouped with a Parameter Object.
- Shared schemas referenced by multiple operations.
- Auto-generated models in Java, TypeScript, Kotlin, or other languages.
- Consumer contracts and runtime validation rules.

Therefore, before modifying a DTO or annotation, identify every operation that uses that schema.

## 2. Distinguishing missing, null, and populated properties

These three states are not the same:

~~~json
{}
~~~

The property does not appear in the object.

~~~json
{
  "middleName": null
}
~~~

The property appears, but its value is null.

~~~json
{
  "middleName": "Minh"
}
~~~

The property appears with a concrete value.

In JSON Schema, `required` checks for the presence of the property name. It does not automatically forbid `null`. To forbid `null`, the property's schema must not accept the `null` type.

OpenAPI 3.1 example of a required property that cannot be null:

~~~yaml
type: object
properties:
  customerId:
    type: string
required:
  - customerId
~~~

Example of a required property that allows null:

~~~yaml
type: object
properties:
  middleName:
    type:
      - string
      - "null"
required:
  - middleName
~~~

Example of an optional property that cannot be null if present:

~~~yaml
type: object
properties:
  note:
    type: string
~~~

In OpenAPI 3.0, nullability is commonly expressed using `nullable: true` combined with `type`. In OpenAPI 3.1, the JSON Schema model is used, such as `type` containing `string` and `null`.

Do not infer that an optional property is synonymous with nullable. Nor should you infer that a `required` property must always have a non-null value.

## 3. `required` is declared at the object level

Example:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
    note:
      type: string
    priority:
      type: integer
  required:
    - customerId
~~~

In this schema:

- `customerId` must appear.
- `note` may be omitted.
- `priority` may be omitted.

To make `note` required, add `note` to the `required` list:

~~~yaml
required:
  - customerId
  - note
~~~

Do not place `required: true` inside an individual property's schema. `required` is an array of property names belonging to the parent object schema.

A property with `default` does not automatically become `required` either. `default` describes a default value; it does not change property presence rules and does not guarantee that the server or client will automatically populate that value.

## 4. Evaluating compatibility by request and response direction

Requests and responses have opposite data flow directions:

~~~text
Client  ---- request ---->  API server
Client  <--- response ---  API server
~~~

When changing a request schema, ask how old clients send payloads to the new server. When changing a response schema, ask how old clients process the new response.

| Change | Request: client sends to server | Response: server sends to client |
|---|---|---|
| Add optional property | Old clients not sending the new field usually continue working | Old clients can usually ignore the new field |
| Add required property | May cause the new server to reject payloads from old clients | New server commits to always sending the field; old clients can ignore it, though strict validators may need updating |
| Remove property | Old clients still sending the removed field may be rejected or lose effect | Old clients reading the removed field may fail or lose data |
| Optional to required | Breaking change for clients not yet sending the field | Stronger server guarantee; usually a relaxing/safe change for consumers, but check validators/codegen |
| Required to optional | Server accepts more payloads missing the field; usually compatible with clients | Breaking change because clients are no longer guaranteed to always receive the field |
| Rename | Old clients send the old name; new server must support forwarding/bridging | Old clients read the old name; new server needs to keep emitting the old name during migration |

This is a contract-level assessment. Actual compatibility also depends on how serializers, deserializers, validators, gateways, and client SDKs handle unknown or missing properties.

## 5. Distinguishing backward compatibility and forward compatibility

Two concepts are frequently confused:

- **Backward compatibility:** existing clients continue working with the new server.
- **Forward compatibility:** new clients can work with the old server.

Example of adding an optional property to a request schema:

- Old clients do not send the new property. The new server still accepts old payloads if the property is genuinely optional.
- New clients send the new property to the old server. The old server may ignore or reject unknown properties depending on Jackson and validation configuration.

Therefore, a change can be backward-compatible without being forward-compatible.

For responses:

- The new server adds a response property. Old clients usually keep working if they ignore unknown fields.
- New clients expect the new property but call the old server. The old server does not send that property, which can cause new clients to see null, validation errors, or processing errors.

When declaring a change compatible, specify the compatibility direction and the scope of supported consumers.

## 6. Adding an optional property to a request

Suppose the API currently accepts:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
  required:
    - customerId
~~~

The new version adds `note` without adding `note` to `required`:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
    note:
      type: string
      maxLength: 500
  required:
    - customerId
~~~

Old clients still send:

~~~json
{
  "customerId": "CUS-100"
}
~~~

This payload remains valid under the new schema. New clients can additionally send `note`:

~~~json
{
  "customerId": "CUS-100",
  "note": "Call before delivery"
}
~~~

This is usually a backward-compatible change on the provider side. However, verify whether the old server accepts the new field if new clients might call back to an old server.

If the DTO uses Jackson configured to reject unknown properties, new clients sending `note` to an old server may receive deserialization errors. Therefore, do not claim bidirectional compatibility when adding an optional request property without testing runtime behavior.

## 7. Adding a required property to a request

Suppose the old request only required `customerId`. The new version adds `channel` and marks it required:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
    channel:
      type: string
      enum:
        - web
        - mobile
        - partner
  required:
    - customerId
    - channel
~~~

Old clients still send:

~~~json
{
  "customerId": "CUS-100"
}
~~~

This payload is no longer valid because `channel` is missing. The server may return 400 after validation fails.

This is a breaking change for old clients. Simply adding a field to a DTO and marking it required in OpenAPI can alter the contract even when Java code still compiles cleanly.

If the server can infer `channel` from authentication details or another source, consider keeping the property optional and applying a default in the business layer. If `channel` must genuinely be supplied by the client, a migration phase or a new API version is needed.

## 8. Removing a property from a request

Suppose the request previously accepted `legacyCode`:

~~~yaml
CreateOrder:
  type: object
  properties:
    customerId:
      type: string
    legacyCode:
      type: string
~~~

When `legacyCode` is removed from the schema, old clients may still send:

~~~json
{
  "customerId": "CUS-100",
  "legacyCode": "OLD-77"
}
~~~

Behavior depends on configuration:

- If Jackson ignores unknown properties, the request may still succeed, but `legacyCode` has no effect.
- If Jackson rejects unknown properties, the request may fail deserialization.
- If the server still relied on `legacyCode` for business decisions, removing the field from the DTO may change behavior.

Thus, removing a property from a request is not always safe just because old clients can send extra data. You must check the unknown-property policy and the business meaning of the field.

If the property is obsolete, mark it `deprecated` in the schema, document replacement guidance, and continue accepting it for a period before removal.

## 9. Removing a property from a response

Suppose the old response is:

~~~yaml
Order:
  type: object
  properties:
    id:
      type: string
    total:
      type: number
    customerName:
      type: string
~~~

Clients may read `customerName` to display the order. If the server removes this property, old clients may:

- Display blank information.
- Encounter null when accessing the deserialized model.
- Fail when code assumes the value is always present.
- Be unable to perform features that depend on `customerName`.

This is usually a breaking change for consumers, even when `customerName` is not in the response schema's `required` list. Optional means the server may omit the field, not that clients definitely do not use it.

For published responses, check actual usage, consumer contracts, and support policies before removing a field. If a field is no longer needed, mark it `deprecated` first and remove it in a planned release.

## 10. Adding an optional property to a response

The new response may add:

~~~yaml
Order:
  type: object
  properties:
    id:
      type: string
    total:
      type: number
    estimatedDelivery:
      type:
        - string
        - "null"
      format: date
~~~

Old clients receive the extra `estimatedDelivery` without needing to use it. For consumers that ignore unknown fields, this is usually an additive and backward-compatible change.

However, some clients are generated from closed schemas, use validators with `additionalProperties: false`, or configure deserializers to fail on unknown properties. Those clients may reject the new response.

When an API has diverse consumers, test published SDKs and representative contract tests. If strict clients must be supported, consider versioning or an explicit compatibility mechanism.

## 11. Adding a required property to a response

When the server adds a property and guarantees it will always send it:

~~~yaml
Order:
  type: object
  properties:
    id:
      type: string
    total:
      type: number
    currency:
      type: string
  required:
    - id
    - total
    - currency
~~~

For old clients, the new server sends an additional `currency` field. Consumers can usually ignore it, so the change is generally backward-compatible if clients tolerate unknown properties.

In the opposite direction, new clients generated from the new schema may expect `currency` to always be present. If those clients call an old server that does not send `currency`, that assumption breaks.

In addition, consumer-side validators might validate old responses against the new schema and report missing `currency`. Distinguish between a new server making a stronger guarantee and new clients being able to work with an old server.

## 12. Optional to required in a response

This is a change that strengthens the server's guarantee:

~~~yaml
type: object
properties:
  id:
    type: string
  trackingUrl:
    type: string
required:
  - id
  - trackingUrl
~~~

If the new server genuinely always returns `trackingUrl`, old clients that already tolerated the field can continue working. However:

- Old consumer contracts may allow the field to be absent, so they need no change.
- New consumers may rely on the new guarantee and omit missing-field handling.
- Old servers may still omit `trackingUrl`.
- Diff tools may classify this as a notable schema change even though the new server runtime only strengthens a guarantee.

In multi-version deployments, clarify whether new clients must call old servers. If so, clients still need fallback handling for missing fields until all old servers reach end-of-life.

## 13. Required to optional in a response

Suppose `id` was previously always present:

~~~yaml
type: object
properties:
  id:
    type: string
required:
  - id
~~~

The new version removes `id` from `required`. From that point on, the contract permits responses without `id`.

Clients that relied on the guarantee that `id` always appears may fail when the server returns a payload missing the field. This is a breaking change in the response guarantee.

If the server still sends `id` in every current response, the change may not cause immediate failures. Yet the new schema now allows weaker behavior, and consumers no longer have the guarantee. Contract diffs should warn when response guarantees are relaxed.

Do not inspect only current sample payloads. The contract must describe every response the server is permitted to return in the future.

## 14. Renaming a property is removing the old name and adding a new name

Suppose `customerName` is renamed to `customerDisplayName`:

~~~yaml
properties:
  customerDisplayName:
    type: string
~~~

For old clients, `customerName` has disappeared. For new clients, `customerDisplayName` may not exist on old servers. This is an incompatible change if replaced directly.

Do not treat renaming as merely an internal refactoring. The JSON property name is part of the public contract. Even if a Java field is renamed, if Jackson still serializes it under the old name, the wire contract has not changed; conversely, changing `@JsonProperty` can change the contract even if the Java field is untouched.

Before renaming, determine:

- The actual JSON names before and after the change.
- Whether the property appears in requests, responses, or both.
- Which consumers send or read the old name.
- Whether both names can be supported concurrently during a transition period.
- Whether a new API version is required.

## 15. Migration for renaming a request property

A transition strategy can be split into phases:

**Phase 1: Accept both the old and new names.**

~~~json
{
  "customerName": "An",
  "customerDisplayName": "An"
}
~~~

The server accepts either name. If both appear together, clear rules are needed: reject conflicting values, or define a precedence order. Do not let arbitrary deserialization order decide the data.

**Phase 2: Publish the new name and mark the old name `deprecated`.**

~~~yaml
properties:
  customerName:
    type: string
    deprecated: true
    description: Use customerDisplayName instead. The old name is scheduled to be discontinued in API v2.
  customerDisplayName:
    type: string
~~~

During this phase, new clients switch to sending the new name; the server still accepts the old name.

**Phase 3: Monitor usage of the old name.**

Record safe metrics or logs to see which clients still send `customerName`. Avoid logging personal data just to track property names.

**Phase 4: Remove according to versioning policy.**

After the notice period and once consumers have migrated, remove the old name in a planned release. If you cannot verify that all consumers have upgraded, retain legacy support longer or release a new API version.

## 16. Migration for renaming a response property

For responses, the server controls the serialized names. Both properties can be emitted simultaneously during a transition period:

~~~json
{
  "id": "ORD-1001",
  "customerName": "An",
  "customerDisplayName": "An"
}
~~~

OpenAPI can describe:

~~~yaml
properties:
  customerName:
    type: string
    deprecated: true
    description: Use customerDisplayName.
  customerDisplayName:
    type: string
required:
  - customerName
  - customerDisplayName
~~~

It is not strictly necessary to mark both required. To preserve the guarantee for old clients, keep `customerName` always present in the response until the migration window ends. The new name can be added and moved into `required` once the server guarantees the value is always available.

When removing the old name, check client telemetry, SDK downloads, consumer-driven contracts, and support policies. Consistency between the two fields holding the same value must also be maintained throughout the transition period.

## 17. Using `oneOf` or `anyOf` when accepting one of two names

In some contracts, you can describe a payload requiring either the old or new property:

~~~yaml
type: object
properties:
  customerName:
    type: string
  customerDisplayName:
    type: string
anyOf:
  - required:
      - customerName
  - required:
      - customerDisplayName
~~~

`anyOf` allows at least one of the two properties to appear. If you want exactly one name, you can use `oneOf`, but consider payloads containing both fields: they will match both simple branches and be rejected.

The example above only describes presence. If you need to forbid both fields simultaneously or require identical values when both appear, more complex conditional schemas or server-side business validation may be necessary.

The OpenAPI Schema Object supports composition, though not all client generators represent these conditions cleanly in generated model code. Test codegen and runtime validation before adopting this as a primary migration strategy.

## 18. Marking a property `deprecated` in OpenAPI

You can mark an obsolete property:

~~~yaml
properties:
  legacyStatus:
    type: string
    deprecated: true
    description: This field will be replaced by status in API v2.
  status:
    type: string
~~~

`deprecated` is metadata that helps documentation and tooling recognize that a property should not be used for new integrations. By itself, it does not:

- Reject requests containing the property.
- Stop serializing the property in responses.
- Emit runtime warnings.
- Remove the property from the DTO.
- Migrate data to the new property.

The server must implement migration behavior in code. OpenAPI only publishes the status and guidance for consumers.

Clearly state the replacement name, expected end-of-support date, affected versions, and how clients should migrate. If no exact date is set, describe the removal criteria rather than promising an uncertain milestone.

## 19. Mapping changes to Spring Boot DTOs

Request DTO example:

~~~java
public class CreateOrderRequest {

    @NotBlank
    private String customerId;

    private String note;

    // getters and setters
}
~~~

Controller:

~~~java
@PostMapping("/orders")
public ResponseEntity<OrderResponse> createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    // handle business logic
    return ResponseEntity.status(HttpStatus.CREATED).body(result);
}
~~~

`@NotBlank` expresses a non-null, non-empty, non-whitespace-only string constraint when Bean Validation is enabled. `@Valid` on the request body instructs Spring to trigger validation on the DTO in the appropriate flow.

To add explicit OpenAPI metadata, you can use:

~~~java
@Schema(description = "Customer ID", requiredMode = Schema.RequiredMode.REQUIRED)
@NotBlank
private String customerId;
~~~

And for an optional field:

~~~java
@Schema(description = "Delivery note", requiredMode = Schema.RequiredMode.NOT_REQUIRED)
private String note;
~~~

Enum names and annotation APIs must match the `swagger-annotations` version in use. Inspect the generated OpenAPI JSON rather than assuming an annotation always produces the exact `required`, `nullable`, or `deprecated` attributes under every configuration.

## 20. Bean Validation, Jackson, and OpenAPI are not a single layer

The three mechanisms have distinct roles:

| Mechanism | Role |
|---|---|
| OpenAPI Schema | Describes the contract for clients and tools |
| Bean Validation | Validates data after the request is bound into an object |
| Jackson | Converts JSON to Java objects and vice versa |

Examples:

- `required` in OpenAPI describes that the property must be present.
- `@NotNull` or `@NotBlank` can validate values after deserialization.
- Jackson decides which JSON properties are bound, ignored, or rejected.

For Java primitive fields such as `int` or `boolean`, missing JSON properties may produce default values `0` or `false`. `@NotNull` cannot detect that case because primitives cannot hold `null`. If you need to distinguish missing from `0`/`false`, use wrapper types, constructor binding, or an appropriate presence-checking mechanism.

Conversely, a `String` field becomes `null` when JSON omits the property. `@NotBlank` will detect it if validation is invoked. However, if the controller omits `@Valid` or the validation dependency is not configured, the constraint may not be enforced.

Therefore, OpenAPI changes and runtime behavior changes must be tested separately.

## 21. Unknown properties and Jackson compatibility

When a client sends a property that the server DTO does not declare, Jackson can:

- Ignore the unknown property under common default configurations.
- Reject deserialization if fail-on-unknown-properties is enabled.
- Behave differently when using custom deserializers or a custom `ObjectMapper` configuration.

This is especially important when adding a property to a request schema. A new client sending that property to an old server may succeed if the old server ignores it, but fail if the old server rejects it.

It can be configured at the class level:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public class CreateOrderRequest {
    private String customerId;
}
~~~

This annotation allows ignoring properties not mapped by the DTO. This is a runtime behavior decision, not proof that every unknown property is safe to ignore. If the new field carries business meaning, an old server ignoring it may produce results different from what the client expects.

Do not enable ignore-unknown-properties mechanically if the API needs to catch typos or invalid data. Choose an intentional policy and test it.

## 22. `required` in responses and actual runtime data

If OpenAPI marks a response property as `required`, the server must ensure the property appears in every response conforming to that schema.

Example:

~~~yaml
OrderResponse:
  type: object
  properties:
    id:
      type: string
    total:
      type: number
  required:
    - id
    - total
~~~

If the Java DTO has `total` set to `null` and Jackson is configured to omit null properties, the response may omit `total` even though OpenAPI marks it `required`. The contract and runtime then diverge.

Check the following factors:

- Is the field value always populated before serialization?
- Does Jackson use `NON_NULL` or `NON_EMPTY` causing properties to be omitted?
- Does a custom serializer rename or strip properties?
- Does entity-to-DTO mapping skip fields in certain branches?
- Do error responses use a different schema?

For responses, write integration tests verifying the actual JSON output, not just annotations or generated schemas.

## 23. Changing `required` in shared schemas

A schema in `components.schemas` can be referenced by many operations:

~~~yaml
components:
  schemas:
    Customer:
      type: object
      properties:
        id:
          type: string
        displayName:
          type: string
~~~

If `displayName` is added to `required`, every operation using `Customer` inherits that change. This can affect both requests and responses depending on where it is referenced.

For example, `Customer` used in:

- Create-order request.
- Order-detail response.
- Customer-list response.
- Nested schema of `Order`.

A single shared `required` change can create breaking changes across multiple operations simultaneously. If requests and responses have different needs, consider splitting schemas:

~~~yaml
components:
  schemas:
    CustomerInput:
      type: object
      properties:
        displayName:
          type: string
      required:
        - displayName
    CustomerView:
      type: object
      properties:
        id:
          type: string
        displayName:
          type: string
      required:
        - id
        - displayName
~~~

Splitting schemas helps the contract clearly express what data clients may send and what data the server commits to return. Do not reuse a single schema merely to reduce class count when request and response semantics differ.

## 24. Contract tests for property changes

Test both the schema and actual payloads:

| Case | What to verify |
|---|---|
| Old request without new property | New server still handles it if the new field is optional |
| Request missing newly required property | Server rejects it according to status/validation contract |
| Request sending old name during migration | Server still accepts and maps it correctly |
| Request sending new name | Server handles it correctly |
| Request sending both old and new names | Conflict rule is enforced |
| New response includes new property | Value and data type are correct |
| Response missing property committed as `required` | Test fails |
| Response still emits `deprecated` property | Old and new names remain consistent during transition |

With Spring MVC, you can use `MockMvc` or real HTTP tests. With WebFlux, use `WebTestClient`. Tests must verify status, JSON paths, and response content.

Example verifying an old request remains valid after adding an optional property:

~~~java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": "CUS-100"
            }
            """))
    .andExpect(status().isCreated());
~~~

Example testing a newly required field:

~~~java
mockMvc.perform(post("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "customerId": "CUS-100"
            }
            """))
    .andExpect(status().isBadRequest());
~~~

Adjust examples to match the application's actual response statuses and exception handlers.

## 25. Consumer-driven contracts and testing old clients

OpenAPI diffs show that a schema changed, but cannot always tell whether actual clients depend on a property.

Consumer-driven contract tests can capture each consumer's expectations:

- Consumer A needs `customerName` in the response.
- Consumer B only uses `id` and `total`.
- Consumer C sends `legacyCode` in the request.
- Consumer D has already switched to `customerDisplayName`.

When changing or removing a property, run provider verification against registered contracts. This helps identify which consumers still depend on old names or `required` assumptions.

If an organization maintains multiple client SDKs, test at least all still-supported SDK versions. A schema change can be compatible with hand-written clients while incompatible with models generated by OpenAPI Generator.

## 26. Checking breaking changes in CI

A pipeline can compare the current OpenAPI document against the released baseline:

~~~text
Generate OpenAPI from Spring Boot
          |
          v
Parse and validate current document
          |
          v
Compare with released baseline
          |
          v
Classify property changes
          |
          v
Run provider/consumer contract tests
          |
          v
Approve compatible change or require versioning
~~~

Changes that should be flagged:

- A property is removed.
- A property is added to `required`.
- A property is removed from `required`.
- A property changes type, format, or enum.
- A property is renamed.
- A property changes from nullable to non-null or vice versa.
- A response field is removed or may be absent.
- A new request field is required.

Diff tools may classify a change as breaking under general rules. The team still needs to evaluate the request/response context and compatibility direction. Do not dismiss warnings merely because the current application still returns sample payloads successfully.

The baseline must be the document from a published or accepted release. Using a file from another development branch as the baseline may yield diff results that do not reflect the contract consumers actually rely on.

## 27. Versioning strategy when compatibility cannot be maintained

If you must rename a property, remove a property, or add a required request property without transition support, a versioning plan is needed.

Options:

- Create a new versioned endpoint, such as `/api/v2/orders`.
- Use media types or a version header if the organization already has clear conventions.
- Maintain v1 during the support window and migrate consumers to v2.
- Announce the v1 end-of-support date and migration instructions.

Do not change the semantics of a property while keeping the same API version without notice. For instance, if `amount` previously meant pre-tax total and is changed to post-tax total while keeping the same name and type, this is a semantic contract change even though schema diffs may not detect it.

Versioning separates contracts, but increases operational cost because multiple versions must be maintained. Only create a new version when a change truly cannot remain compatible or when product policy requires it.

## 28. Safe migration workflow

When you need to change a property in a published API:

1. Identify whether the property is in requests, responses, or both.
2. List operations and schemas using the property.
3. Determine which direction of client/provider compatibility must be preserved.
4. Check usage telemetry and consumer contracts.
5. Add the new name as optional if possible.
6. Continue accepting or emitting the old name during the transition period.
7. Mark the old property `deprecated` and document the replacement name.
8. Implement runtime mapping, conflict rules, and validation.
9. Update SDKs, documentation, and examples for consumers.
10. Run contract tests with both old and new payloads.
11. Monitor usage of the old name and missing-field cases.
12. Remove the old name or change `required` only after meeting support policy requirements.
13. If requirements cannot be met, release a new API version and maintain the old version for the committed duration.

At every stage, the OpenAPI document must accurately describe current runtime behavior. Do not advertise a property as `required` before the server actually enforces it; likewise, do not merely mark a property `deprecated` if the server has already stopped supporting it while docs still promise acceptance.

## 29. Common mistakes

| Change | Misconception | Consequence |
|---|---|---|
| Add request property | Assuming old servers always ignore unknown fields | New clients may be rejected by old servers |
| Add required request property | Treating it as an additive change | Old clients missing the field get 400 |
| Remove request property | Assuming clients sending unknown fields have no impact | Strict servers may reject; legacy logic may be lost |
| Remove response property | Assuming an optional property is unused | Old clients lose data or fail |
| Rename property | Renaming only the Java field | JSON contract may change unintentionally via Jackson |
| `required` to optional in response | Assuming relaxing schema is safe | Clients lose the guarantee that the field always appears |
| optional to `required` in response | Assuming all new clients calling old servers will work | Old servers may not send the new field |
| `required` and nullable | Treating both concepts as identical | Missing fields and null fields are handled incorrectly |
| Using `default` | Thinking the server auto-fills the value | Requests missing the field may still be invalid |
| Marking `deprecated` | Thinking the server stops accepting or returning the field | Runtime continues behaving as before if code is unchanged |
| Editing shared schema | Not reviewing all operations | A single change propagates to multiple requests/responses |
| Running schema diff only | Skipping real payload tests | Misses Jackson, validation, and consumer differences |

## 30. Key takeaways

- Evaluating property changes requires distinguishing requests from responses.
- `required` checks presence; nullability controls whether `null` values are allowed.
- Properties omitted from `required` are optional by default.
- Adding an optional request field usually keeps old clients working with the new server, while new clients calling an old server still depend on the unknown-property policy.
- Adding an optional response field is usually compatible with consumers that ignore unknown fields.
- Adding a required request field is a breaking change for old clients not yet sending the field.
- Removing a response property can break clients reading it, even if the property was previously optional.
- Renaming equals removing the old name and adding a new name; use a dual-read/dual-write phase or a new version.
- `deprecated` is documentation metadata only and does not automatically alter runtime behavior.
- OpenAPI, Bean Validation, and Jackson must be tested separately and kept consistent.
- Shared schemas can propagate changes across many operations; separate request and response schemas when semantics differ.
- Use OpenAPI diffs, integration tests, and consumer-driven contracts before releasing.
- When compatibility cannot be preserved, version the API and provide a clear migration plan.

To safely rename, remove, or add required properties, first determine the data direction and compatibility direction. Keep the old name during the transition period, mark it `deprecated`, verify Jackson/Bean Validation behavior, and validate with contract tests using both old and new payloads. If a change prevents existing clients from satisfying the contract, release a new API version according to the published support policy.
