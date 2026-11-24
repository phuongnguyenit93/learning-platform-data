# Polymorphism, Discriminator, and Mapping Values to Schemas

An API sometimes accepts or returns multiple data shapes that share a single role. For example, a payment method may be a bank card or a bank transfer; a notification may be an order-created event or an order-cancelled event. If the Java model uses only a parent type, clients still need to know which concrete variant a payload represents in order to read the right properties.

OpenAPI solves this problem with combined schemas such as `oneOf`, `anyOf`, `allOf`, and the `discriminator` field. Springdoc can generate these structures from Java types and Swagger/OpenAPI annotations. Jackson, meanwhile, is responsible for choosing the Java class when deserializing JSON. Both sides must share the same discriminator property name and value mapping so the published contract matches runtime.

## 1. Polymorphism in API Contracts

Polymorphism allows a slot in a request or response to hold one of several data structures. Rather than declaring one object with dozens of optional fields, you define a base type and concrete variants.

For example, `PaymentMethod` is the base type. The API supports two shapes:

- `CardPayment`: card payment, with `token` and `last4`.
- `BankTransferPayment`: bank transfer payment, with `bankCode` and `reference`.

JSON can take one of two forms:

```json
{
  "kind": "card",
  "token": "tok_abc123",
  "last4": "4242"
}
```

Or:

```json
{
  "kind": "bank-transfer",
  "bankCode": "VCB",
  "reference": "ORDER-2026-001"
}
```

The `kind` property indicates which variant the payload uses. Clients can inspect this field to decide how to process the remaining properties.

## 2. Distinguishing `oneOf`, `anyOf`, and `allOf`

OpenAPI offers several ways to combine schemas. Choosing the right operator determines payload validation semantics:

| Keyword | Meaning | Common use case |
| --- | --- | --- |
| `oneOf` | Payload must be valid against **exactly one** schema in the list. | Mutually exclusive variants, such as card or bank transfer. |
| `anyOf` | Payload must be valid against **at least one** schema in the list; may match multiple simultaneously. | Structures that can overlap or payloads that satisfy multiple models. |
| `allOf` | Payload must satisfy **all** schemas in the list. | Combining common properties with extensions, or describing inheritance. |

Example of `oneOf`:

```yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransferPayment'
```

Example of `allOf` combining shared and specific parts:

```yaml
CardPayment:
  allOf:
    - $ref: '#/components/schemas/PaymentBase'
    - type: object
      properties:
        last4:
          type: string
```

`allOf` does not mean selecting a subtype. It merges schema constraints; a payload must satisfy every component. If you need to represent mutually exclusive choices, `oneOf` is usually more suitable.

## 3. Discriminator Helps Identify Variants

`discriminator` specifies the property in the payload used to identify the concrete schema. It has two key parts:

- `propertyName`: name of the distinguishing property, e.g. `kind`.
- `mapping`: maps values appearing in JSON to the corresponding schema.

Example:

```yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransferPayment'
  discriminator:
    propertyName: kind
    mapping:
      card: '#/components/schemas/CardPayment'
      bank-transfer: '#/components/schemas/BankTransferPayment'
```

With this configuration:

- `"kind": "card"` points to the `CardPayment` schema.
- `"kind": "bank-transfer"` points to the `BankTransferPayment` schema.

The left-hand side of `mapping` is the wire-format value in JSON. The right-hand side is the schema name or schema reference. The JSON value does not have to match the Java class name. Explicit mapping keeps contract names stable even when classes or packages are renamed in source code.

Without an explicit mapping, tools may infer an implicit mapping from schema names. That implicit inference is less clear when class names, component names, and discriminator values differ. For public APIs, declare explicit mappings so clients do not have to guess.

The discriminator property should appear in each variant and be required in the payload. If subtype schemas do not document the `kind` field, some client generators or validators may not fully understand the contract, even if Jackson still classifies the JSON at runtime.

## 4. Combining OpenAPI Annotations with Jackson

Springdoc uses `@Schema` annotations to describe OpenAPI structures. Jackson uses `@JsonTypeInfo` and `@JsonSubTypes` to select subtypes when reading or writing JSON. The two annotation sets address two distinct responsibilities.

Defining the base type:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import io.swagger.v3.oas.annotations.media.DiscriminatorMapping;
import io.swagger.v3.oas.annotations.media.Schema;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.EXISTING_PROPERTY,
    property = "kind",
    visible = true
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank-transfer")
})
@Schema(
    name = "PaymentMethod",
    description = "One of the supported payment methods",
    oneOf = {CardPayment.class, BankTransferPayment.class},
    discriminatorProperty = "kind",
    discriminatorMapping = {
        @DiscriminatorMapping(value = "card", schema = CardPayment.class),
        @DiscriminatorMapping(value = "bank-transfer", schema = BankTransferPayment.class)
    }
)
public interface PaymentMethod {}
```

Defining the variants:

```java
@Schema(name = "CardPayment", description = "Card payment")
public record CardPayment(
    @NotBlank
    @Schema(allowableValues = {"card"}, example = "card")
    String kind,

    @NotBlank
    String token,

    @NotBlank
    @Pattern(regexp = "^[0-9]{4}$")
    String last4
) implements PaymentMethod {}
```

```java
@Schema(name = "BankTransferPayment", description = "Bank transfer payment")
public record BankTransferPayment(
    @NotBlank
    @Schema(allowableValues = {"bank-transfer"}, example = "bank-transfer")
    String kind,

    @NotBlank
    String bankCode,

    @NotBlank
    String reference
) implements PaymentMethod {}
```

In the example, `As.EXISTING_PROPERTY` tells Jackson that `kind` is a real property on the subtype and the serializer will write the value from that property. `visible = true` preserves the type id so the deserializer passes it into the record constructor. Each record has a `kind` field, so the value is retained in the object after deserialization. Constraints and `allowableValues` also document the discriminator field as required with a specific value per variant.

Placing the base type in a request:

```java
public record CreatePaymentRequest(
    @NotNull
    @Valid
    PaymentMethod paymentMethod
) {}
```

And using it in a controller:

```java
@PostMapping("/payments")
@Operation(summary = "Create a payment")
ResponseEntity<PaymentResponse> create(
    @Valid @RequestBody CreatePaymentRequest request
) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(paymentService.create(request.paymentMethod()));
}
```

When deserializing `CreatePaymentRequest`, Jackson reads `paymentMethod.kind`, then selects `CardPayment` or `BankTransferPayment` per `@JsonSubTypes`. Springdoc uses `oneOf` and the discriminator mapping to describe the corresponding choice to clients.

## 5. Schema Names and Discriminator Mappings Must Be Consistent

A common error is using a Java class name as a discriminator value without checking the generated schema component. Distinguish three names:

| Component | Example | Role |
| --- | --- | --- |
| Discriminator property name | `kind` | Field name in JSON. |
| Discriminator value | `bank-transfer` | JSON value Jackson uses to select the subtype. |
| Schema name | `BankTransferPayment` | OpenAPI component describing the subtype structure. |

Explicit mapping connects the JSON value to the schema name. If you rename a Java class, the mapping can keep `bank-transfer` for existing APIs. If you change the discriminator value, that is a contract change and can break older clients trying to deserialize new payloads.

You can use `@Schema(name = "...")` to control component names rather than letting the library derive them from class names. After renaming a schema, check `discriminator.mapping` and all `$ref` entries in the specification to ensure they point to existing components.

## 6. When to Use `@JsonTypeName`, `@JsonSubTypes`, and `@DiscriminatorMapping`?

Each annotation has a different role:

| Annotation | Library | Responsibility |
| --- | --- | --- |
| `@JsonTypeInfo` | Jackson | Chooses the strategy for storing type id in JSON and the discriminator property name. |
| `@JsonSubTypes` | Jackson | Registers subtypes and type id values for deserialization/serialization. |
| `@JsonTypeName` | Jackson | Sets the default type id name for a subtype. |
| `@Schema(oneOf = ...)` | Swagger/OpenAPI | Publishes the list of alternative schemas. |
| `@Schema(discriminatorProperty = ...)` | Swagger/OpenAPI | Publishes the distinguishing property. |
| `@DiscriminatorMapping` | Swagger/OpenAPI | Maps a discriminator value to a concrete schema. |

If you already declare subtype names in `@JsonSubTypes.Type(name = "card")`, there is no need to repeat `@JsonTypeName` for the same purpose. `@JsonTypeName` is useful when a subtype carries its own default type id and Jackson configuration is organized differently. Whichever approach you choose, keep type id values identical to OpenAPI mapping keys.

Do not confuse `@DiscriminatorMapping` with Jackson configuration. Adding only OpenAPI mappings will not teach Jackson how to instantiate subtypes. Conversely, adding only `@JsonSubTypes` may work at runtime while leaving the spec without `oneOf` or discriminator mappings for clients.

## 7. Distinguishing Discriminator from Java Inheritance

A discriminator does not require schemas to have a Java inheritance relationship. It is OpenAPI metadata for identifying variants. You can use a discriminator with independent schemas as long as each schema includes the distinguishing property and an appropriate mapping.

When subtypes actually extend a base class, springdoc or Swagger Core may represent shared properties via `allOf`. Example:

```yaml
PaymentBase:
  type: object
  required:
    - kind
  properties:
    kind:
      type: string

CardPayment:
  allOf:
    - $ref: '#/components/schemas/PaymentBase'
    - type: object
      required:
        - token
      properties:
        token:
          type: string
```

Meanwhile, the base schema can list the subtypes via `oneOf`. `allOf` expresses combined structure; `oneOf` expresses concrete choices. Do not substitute one meaning for the other.

## 8. Cases of Mismatched Mappings

Suppose Jackson declares:

```java
@JsonSubTypes.Type(value = CardPayment.class, name = "card")
```

Yet OpenAPI maps:

```yaml
discriminator:
  propertyName: kind
  mapping:
    credit-card: '#/components/schemas/CardPayment'
```

Clients send `"kind": "credit-card"` following the documentation, yet Jackson does not recognize this value because runtime only registers `card`. The request can fail deserialization. Conversely, if Jackson accepts a type id that OpenAPI does not list, documentation fails to reflect runtime capabilities.

Keep the following aligned:

- `propertyName` in OpenAPI must match `property` in `@JsonTypeInfo`.
- Keys in `discriminatorMapping` must match subtype names in `@JsonSubTypes.Type(name = ...)` or Jackson-configured type ids.
- Mapping target schemas must exist in `components.schemas`.
- The discriminator property should be documented in subtypes with appropriate values.
- Subtypes in `oneOf` must describe the payloads runtime actually accepts.

## 9. Verifying the Spec and Runtime Deserialization

For polymorphic APIs, looking only at Swagger UI is not enough. You must test both the specification and Jackson:

1. Open `/v3/api-docs` and locate the base schema `PaymentMethod`.
2. Verify `oneOf` lists `CardPayment` and `BankTransferPayment` accurately.
3. Verify `discriminator.propertyName` is `kind` and `mapping` contains `card` and `bank-transfer` with valid `$ref` targets.
4. Check that each subtype has the `kind` property and required subtype-specific fields.
5. Send a request with `kind: card`; verify Jackson instantiates `CardPayment`.
6. Send a request with `kind: bank-transfer`; verify Jackson instantiates `BankTransferPayment`.
7. Send an unknown type id, missing discriminator, or missing required field; verify the application returns an appropriate input error.
8. Inspect responses to ensure Jackson serializes the right type id and schema structure.

Example simple deserialization test:

```java
@Test
void readsCardPaymentFromDiscriminator() throws Exception {
    String json = """
        {
          "kind": "card",
          "token": "tok_abc123",
          "last4": "4242"
        }
        """;

    PaymentMethod payment = objectMapper.readValue(json, PaymentMethod.class);

    assertThat(payment).isInstanceOf(CardPayment.class);
}
```

This test verifies Jackson configuration. Another test must verify the OpenAPI spec has the right mapping; neither replaces the other.

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Swagger UI shows only the parent schema | `oneOf` not declared or subtypes not discovered | Use `@Schema(oneOf = {...})` and inspect `components.schemas`. |
| Discriminator mapping points to nonexistent schema | Schema name changed or mapping declared wrongly | Use `@Schema(name = ...)` and check every `$ref`. |
| Jackson reports invalid type id | `@JsonSubTypes` lacks the value sent by the client | Synchronize type ids between Jackson and OpenAPI mapping. |
| Discriminator field disappears from subtype object | Jackson uses `visible = false` by default | Use `visible = true` if the subtype needs to bind that field; or design the subtype without storing it. |
| Client generator produces wrong data types | `oneOf`, `allOf`, or discriminator misrepresents the relationship | Inspect schema structure and test target generator with a sample payload. |
| Payload matches multiple subtypes in `oneOf` | Schemas overlap or lack a distinguishing property | Design mutually exclusive subtypes and add a required discriminator with distinct values. |

## 10. Principles of Application

- Use `oneOf` when a payload must belong to exactly one variant; use `anyOf` when multiple schemas may match simultaneously; use `allOf` to combine constraints or describe inheritance structures.
- Use a stable discriminator property such as `kind` or `type`.
- Declare explicit mappings when JSON values differ from schema names or when contracts must stay stable across Java class renames.
- Synchronize `@JsonTypeInfo`, `@JsonSubTypes`, `@Schema`, and `@DiscriminatorMapping`.
- Document the discriminator in subtypes and ensure runtime handles that value properly.
- Verify `/v3/api-docs`, request deserialization, and response serialization as separate steps.
- Do not use a discriminator as an authentication or security check; it only selects how data structure is interpreted.

`discriminator` links the identifying value in JSON to the schema describing each variant. When `oneOf`, OpenAPI mappings, and Jackson configuration agree, clients understand polymorphic payloads and the server deserializes the right subtype. Type id names are part of the public contract, so manage them carefully when changing models.

## References

- [OpenAPI Specification – Composition and Inheritance](https://spec.openapis.org/oas/latest.html)
- [Swagger Annotations – `@Schema` and `@DiscriminatorMapping`](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [Jackson Annotations – Polymorphic Type Handling](https://github.com/FasterXML/jackson-annotations)
- [Springdoc OpenAPI – official documentation](https://springdoc.org/)
