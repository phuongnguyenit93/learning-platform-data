# oneOf, anyOf, allOf, and not by Validation Condition

OpenAPI schemas can describe simple data using `type` and `properties`, but many contracts need to express logical relationships between structures. A request might belong to exactly one of several variants, satisfy at least one group of conditions, simultaneously meet all shared rules, or be rejected if it matches a forbidden structure.

OpenAPI provides the `oneOf`, `anyOf`, `allOf`, and `not` keywords to express these conditions. Springdoc-openapi can publish them from `@Schema` annotations or from a customized OpenAPI model. These keywords describe data validity rules; they do not automatically configure Jackson, write business logic, or replace runtime validation.

## 1. Logical Meaning of the Four Keywords

| Keyword | Validation condition | Interpretation |
| --- | --- | --- |
| `oneOf` | Matches exactly one subschema | Only one variant is accepted |
| `anyOf` | Matches at least one subschema | One or more variants may be valid together |
| `allOf` | Matches all subschemas | Data must satisfy every group of constraints |
| `not` | Does not match the specified schema | Excludes a structure or set of values |

You can think of them as:

- `oneOf` is XOR: exactly one branch.
- `anyOf` is OR: at least one branch is true.
- `allOf` is AND: all branches are true.
- `not` is negation: the specified branch must be false.

These keywords combine schemas, not operators that Spring automatically executes in controllers. Compatible OpenAPI/JSON Schema validators can use them to check payloads; the application still needs to ensure request handling and actual validation match the published contract.

## 2. oneOf: Exactly One of Multiple Schemas

`oneOf` fits when a request has mutually exclusive variants. For example, a payment method can be a card or a bank transfer. A payload must match exactly one variant.

~~~yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransferPayment'
  discriminator:
    propertyName: kind
    mapping:
      CARD: '#/components/schemas/CardPayment'
      BANK_TRANSFER: '#/components/schemas/BankTransferPayment'

CardPayment:
  type: object
  required: [kind, cardToken]
  properties:
    kind:
      type: string
      enum: [CARD]
    cardToken:
      type: string

BankTransferPayment:
  type: object
  required: [kind, bankAccount]
  properties:
    kind:
      type: string
      enum: [BANK_TRANSFER]
    bankAccount:
      type: string
~~~

Valid request for the card variant:

~~~json
{
  "kind": "CARD",
  "cardToken": "tok_123"
}
~~~

Valid request for the bank transfer variant:

~~~json
{
  "kind": "BANK_TRANSFER",
  "bankAccount": "VN0012345678"
}
~~~

If an object satisfies both `CardPayment` and `BankTransferPayment` simultaneously, `oneOf` fails because two subschemas match. If the object matches no schema, it is also invalid. Therefore, branches should be designed to be mutually exclusive via a discriminator or clear structural constraints.

### Using a Discriminator to Identify Variants

A discriminator helps tools and clients identify which schema corresponds to a property's value. In the example above, `kind=CARD` maps to `CardPayment` and `kind=BANK_TRANSFER` maps to `BankTransferPayment`.

A discriminator does not by itself make schemas mutually exclusive and does not replace the `oneOf` condition. To ensure validation works properly:

- The discriminator property should be required in every subschema.
- Each variant should constrain that property to a distinct value, typically using `enum` in OpenAPI 3.0 or `const` in OpenAPI 3.1.
- The payload must match the structure of the selected schema.

If using Jackson to deserialize polymorphic requests, configure `@JsonTypeInfo` and `@JsonSubTypes` or an equivalent mechanism. OpenAPI annotations only document the contract; they do not automatically teach Jackson which subclass to instantiate.

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import io.swagger.v3.oas.annotations.media.DiscriminatorMapping;
import io.swagger.v3.oas.annotations.media.Schema;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "CARD"),
    @JsonSubTypes.Type(value = BankTransferPayment.class, name = "BANK_TRANSFER")
})
@Schema(
    name = "PaymentMethod",
    oneOf = {CardPayment.class, BankTransferPayment.class},
    discriminatorProperty = "kind",
    discriminatorMapping = {
        @DiscriminatorMapping(value = "CARD", schema = CardPayment.class),
        @DiscriminatorMapping(value = "BANK_TRANSFER", schema = BankTransferPayment.class)
    }
)
public interface PaymentMethod {
}
~~~

The `CardPayment` and `BankTransferPayment` DTOs must be declared as concrete types with fields matching the payload. When using this Jackson configuration, test both serialization and deserialization to confirm the `kind` property is emitted and accepted properly.

## 3. anyOf: Matching One or More Schemas

`anyOf` fits when data can satisfy one condition or multiple conditions simultaneously. For example, contact information may contain an email, a phone number, or both.

~~~yaml
ContactInfo:
  type: object
  properties:
    email:
      type: string
      format: email
    phone:
      type: string
  anyOf:
    - required: [email]
    - required: [phone]
~~~

All of the following payloads are valid:

~~~json
{"email": "dev@example.com"}
~~~

~~~json
{"phone": "+84901234567"}
~~~

~~~json
{"email": "dev@example.com", "phone": "+84901234567"}
~~~

A payload with neither `email` nor `phone` matches no branch and is invalid. A payload with both remains valid because `anyOf` only requires at least one branch to pass.

If you replace `anyOf` with `oneOf`, a payload containing both `email` and `phone` matches two branches and is rejected. This is an important distinction when designing schemas for cases that can occur together.

You can declare this with annotations:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "ContactInfo",
    anyOf = {EmailContact.class, PhoneContact.class},
    description = "Contact information may include an email, phone number, or both."
)
public interface ContactInfo {
}
~~~

When you need to express explicitly that at least one property must be present, verify that the generated schema contains the expected `required` branches. Placing `anyOf` on a class does not automatically guarantee runtime properties are validated correctly.

## 4. allOf: Must Satisfy All Schemas

`allOf` combines multiple schemas using logical AND. The payload must satisfy every subschema simultaneously. This is useful for reusing shared property groups or describing an extended model.

For example, every entity has an `id` and creation timestamp; a product adds a name and price:

~~~yaml
EntityBase:
  type: object
  required: [id, createdAt]
  properties:
    id:
      type: string
      format: uuid
    createdAt:
      type: string
      format: date-time

Product:
  allOf:
    - $ref: '#/components/schemas/EntityBase'
    - type: object
      required: [name, price]
      properties:
        name:
          type: string
        price:
          type: number
          minimum: 0
~~~

`Product` must have `id`, `createdAt`, `name`, and `price`; constraints from both `EntityBase` and the additional object apply.

Composition can be described with annotations:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

@Schema(name = "EntityBase", description = "Common properties of an entity.")
public class EntityBase {
    public UUID id;
    public OffsetDateTime createdAt;
}

@Schema(
    name = "Product",
    description = "Product extending the common properties of an entity.",
    allOf = {EntityBase.class, ProductFields.class}
)
public class Product {
}

@Schema(name = "ProductFields")
public class ProductFields {
    public String name;
    public BigDecimal price;
}
~~~

This example illustrates generating a composed schema from models. In real applications, inspect how springdoc and swagger-core handle component names, `required`, and `properties` when combining `allOf`; you may need to adjust DTOs or OpenAPI configuration to avoid duplicate schemas or unintended references.

### allOf Is Not Simply Java Inheritance

`allOf` is the intersection of schema constraints. It does not create Java inheritance relationships, nor does it configure Jackson. Conversely, Java class inheritance is not always emitted as `allOf`; the result depends on model resolvers, annotations, and configuration.

A common mistake is setting `additionalProperties: false` on a base schema and then using `allOf` to add properties. The base schema can reject properties defined in another branch because they are not listed in the base schema's own `properties`. Review all object-closure rules before combining with `allOf`; in OpenAPI 3.1 you can consider `unevaluatedProperties` once you understand its evaluation scope.

## 5. not: Excluding a Schema

`not` makes the overall schema invalid when an instance matches the schema placed inside `not`. For example, a username must not be one of the reserved names:

~~~yaml
Username:
  type: string
  minLength: 3
  maxLength: 40
  not:
    enum:
      - admin
      - root
      - system
~~~

The values `admin`, `root`, and `system` are excluded. Other names must still satisfy `type`, `minLength`, and `maxLength`.

`not` can also exclude an object structure:

~~~yaml
CreateAccountRequest:
  type: object
  required: [username]
  properties:
    username:
      type: string
    legacyPassword:
      type: string
  not:
    required: [legacyPassword]
~~~

This schema forbids objects containing the `legacyPassword` property. Note that `required` inside the `not` subschema means the subschema matches whenever `legacyPassword` is present; `not` inverts that result.

In swagger-core, `@Schema` supports the `not` attribute in supported versions. You can reference a model representing the excluded structure:

~~~java
@Schema(
    name = "ReservedUsername",
    type = "string",
    allowableValues = {"admin", "root", "system"}
)
public class ReservedUsername {
}

public record CreateAccountRequest(
    @Schema(not = ReservedUsername.class, description = "Username must not be a system name.")
    String username
) {}
~~~

Verify that the swagger-core version bundled with springdoc supports the `not` attribute and that the generated schema has the right `string` type. If annotations cannot express the needed structure, configure the `Schema` model directly via an OpenAPI customizer.

## 6. Combining Keywords to Express Conditions

Keywords can be nested to describe complex contracts. For example, a request might contain `contact` and `payment`; `contact` must have email or phone, while `payment` must belong to exactly one type.

~~~yaml
CheckoutRequest:
  type: object
  required: [contact, payment]
  properties:
    contact:
      $ref: '#/components/schemas/ContactInfo'
    payment:
      $ref: '#/components/schemas/PaymentMethod'
~~~

In this structure:

- `ContactInfo` uses `anyOf` to require at least one contact method.
- `PaymentMethod` uses `oneOf` to choose exactly one payment method.
- Base schemas can use `allOf` to share common properties.
- `not` can exclude disallowed values or structures.

Avoid nesting multiple layers of composition if a simpler schema can express it clearly. Deeper structures are harder for readers, validators, and client generators to support consistently.

## 7. Conditional if/then/else in OpenAPI 3.1

Some rules depend on another property's value, such as requiring `cardToken` when `paymentType` is `CARD` and requiring `bankAccount` when it is `BANK_TRANSFER`. JSON Schema 2020-12 provides `if`, `then`, and `else` to express such conditions.

~~~yaml
PaymentRequest:
  type: object
  properties:
    paymentType:
      type: string
      enum: [CARD, BANK_TRANSFER]
    cardToken:
      type: string
    bankAccount:
      type: string
  required: [paymentType]
  allOf:
    - if:
        properties:
          paymentType:
            const: CARD
        required: [paymentType]
      then:
        required: [cardToken]
        not:
          required: [bankAccount]
    - if:
        properties:
          paymentType:
            const: BANK_TRANSFER
        required: [paymentType]
      then:
        required: [bankAccount]
        not:
          required: [cardToken]
~~~

In the example:

- `paymentType=CARD` requires `cardToken` and forbids `bankAccount`.
- `paymentType=BANK_TRANSFER` requires `bankAccount` and forbids `cardToken`.
- If `paymentType` is missing, the schema rejects the payload because the property is in `required`.

`if`/`then`/`else` and `const` belong to OpenAPI 3.1's Schema Object capabilities. Do not put these keywords into an OpenAPI 3.0 document expecting validators to interpret them as JSON Schema 2020-12. For OpenAPI 3.0, many cases can be expressed with `oneOf` using subschemas that have distinct `enum`/`required` rules.

## 8. Declaring Composition with @Schema in springdoc

Swagger-core's `@Schema` annotation provides common composition attributes:

~~~java
@Schema(oneOf = {CardPayment.class, BankTransferPayment.class})
PaymentMethod payment;

@Schema(anyOf = {EmailContact.class, PhoneContact.class})
ContactInfo contact;

@Schema(allOf = {EntityBase.class, ProductFields.class})
Product product;

@Schema(not = ReservedUsername.class)
String username;
~~~

These examples illustrate attaching subschemas to properties or models. Actual class structures must be designed so each subtype's schema accurately reflects its payload. For complex constraints like `if`/`then`/`else`, nested `not` branches, or conditional schemas, an `OpenAPI` bean/customizer can be easier to control than annotations.

Example customizing the OpenAPI model:

~~~java
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class OpenApiSchemaConfig {

    @Bean
    OpenApiCustomizer reservedUsernameCustomizer() {
        return openApi -> {
            if (openApi.getComponents() == null
                    || openApi.getComponents().getSchemas() == null) {
                return;
            }

            Schema<?> request = openApi.getComponents()
                .getSchemas()
                .get("CreateAccountRequest");
            if (request == null || request.getProperties() == null) {
                return;
            }

            Schema<?> username = (Schema<?>) request.getProperties().get("username");
            if (username != null) {
                Schema<?> reservedNames = new StringSchema();
                reservedNames.setEnum(List.of("admin", "root", "system"));
                username.setNot(reservedNames);
            }
        };
    }
}
~~~

The customizer above locates the `username` property inside the `CreateAccountRequest` schema and attaches a string schema with forbidden enum values to `not`. Component and property names must match the document generated by springdoc. If the schema does not exist yet or its name changes, adjust the lookup point. When customizing models, avoid unintentionally overwriting existing composition or properties and always inspect the JSON output afterward.

## 9. Which Keyword Fits Which Scenario?

| Scenario | Suitable keyword | Reason |
| --- | --- | --- |
| Pay by card or bank transfer, only one allowed | `oneOf` | Exactly one subschema must match |
| User provides email, phone, or both | `anyOf` | Accepts one or multiple conditions |
| DTO has shared properties and specialized properties | `allOf` | All property/constraint groups apply together |
| Forbid usernames `admin` or `root` | `not` | Excludes forbidden values |
| Required field depends on another property | `if`/`then`/`else` in OAS 3.1 | Expresses conditional rules |

Do not choose `oneOf` merely because there are multiple subschemas. If data can satisfy multiple branches simultaneously, `anyOf` accurately reflects the contract. If all constraints must hold, use `allOf`. If you want to forbid a case, use `not` or express valid branches clearly.

## 10. Differences Between OpenAPI 3.0 and 3.1

OpenAPI 3.0 uses a JSON Schema subset for Schema Objects and supports composition keywords such as `oneOf`, `anyOf`, `allOf`, and `not`. OpenAPI 3.1 aligns Schema Objects more closely with JSON Schema 2020-12.

| Capability | OpenAPI 3.0 | OpenAPI 3.1 |
| --- | --- | --- |
| `oneOf`, `anyOf`, `allOf`, `not` | Yes | Yes |
| `discriminator` | Yes | Yes |
| `if`/`then`/`else` | Not part of standard 3.0 Schema Object | Yes, per JSON Schema 2020-12 |
| `const` | Not a standard 3.0 Schema Object keyword | Yes |
| Extended JSON Schema vocabulary | Limited to OAS 3.0 subset | Fuller support per declared dialect |

Before using advanced keywords, inspect the `openapi` field in the JSON/YAML generated by springdoc and verify that your organization's client tools, validators, and gateways support that version. Not all tools interpret composition or OpenAPI 3.1 JSON Schema identically.

## 11. Testing Schema Composition

A composed schema should be tested with payloads representing each branch and edge cases. For `oneOf`, test payloads matching exactly one branch, matching zero branches, and accidentally matching multiple branches. For `anyOf`, test each branch individually and cases where multiple branches match together. For `allOf`, omit each condition in turn to ensure every constraint actually takes effect. For `not`, test both forbidden values and allowed values.

Example checking the generated document:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
curl -sS http://localhost:8080/v3/api-docs.yaml
~~~

Checklist:

1. Are `oneOf`, `anyOf`, `allOf`, or `not` placed on the right schema/property?
2. Does every `$ref` point to an existing component?
3. Are `oneOf` branches mutually exclusive?
4. Do the discriminator property name and mapping match?
5. Do required properties and enums reflect each variant?
6. Does `allOf` suffer from `additionalProperties` or `required` conflicts?
7. Does `not` negate the intended schema?
8. If using `if`/`then`/`else` or `const`, is the document OpenAPI 3.1?
9. Do runtime Jackson and Bean Validation process payloads using the same rules as the documentation?

Swagger UI can render the list of variants, yet UI rendering does not prove payloads are validated or accepted properly by validators or the server. Test with a version-compatible OpenAPI/JSON Schema validator and controller integration tests.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `oneOf` rejects seemingly valid payloads | Payload matches multiple subschemas or none | Make branches mutually exclusive and check `required`/`enum` |
| `anyOf` accepts incomplete data | Subschemas lack `required` or strong enough constraints | Add `required` and necessary constraints to each branch |
| `allOf` disallows extended properties | `additionalProperties: false` in a subschema causes conflict | Revisit object closure; consider an appropriate composition pattern |
| Discriminator displays but Jackson fails to parse | Declared OpenAPI discriminator without polymorphic deserialization | Align `@JsonTypeInfo`, `@JsonSubTypes`, and schema |
| `not` does not behave as expected | Negated schema does not match the intended forbidden values | Test the subschema independently against forbidden values |
| `if`/`then`/`else` unrecognized by tools | Document emitted as OpenAPI 3.0 or validator lacks OAS 3.1 support | Confirm spec version and choose a compatible representation |
| Client generator produces awkward models | Composition is too deep or tool support is limited | Simplify schemas, test target generator, and consider separate endpoints/DTOs |

## 13. Workflow for Designing Conditional Schemas

When modeling a request with multiple shapes or constraints:

1. List all variants and determine whether a payload can belong to one or multiple variants.
2. Use `oneOf` if it must match exactly one branch; use `anyOf` if one or more branches can hold together.
3. Use `allOf` for simultaneous constraints or reused property groups.
4. Use `not` to exclude values or structures; use `if`/`then`/`else` if property-conditional rules are needed and the document is OpenAPI 3.1.
5. Add a `discriminator` when variant identification is needed, and configure Jackson to deserialize the corresponding subtypes.
6. Inspect schemas generated by springdoc and test valid/invalid payloads with a compatible validator.
7. Align Bean Validation, service/domain logic, and runtime error handling with the published rules.

Composition keywords let API contracts express diverse data shapes and complex validation conditions. When you pick the right logical operator and verify both the spec and runtime behavior, clients can tell precisely which payloads are accepted.

## References

- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Discriminator Object](https://spec.openapis.org/oas/latest.html#discriminator-object)
- [JSON Schema – Combining Schemas](https://json-schema.org/understanding-json-schema/reference/combining)
- [JSON Schema – Conditional Schema Validation](https://json-schema.org/understanding-json-schema/reference/conditionals)
- [Swagger Core – @Schema Annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
- [springdoc-openapi – Documentation](https://springdoc.org/)
