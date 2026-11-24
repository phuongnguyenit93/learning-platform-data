# Distinguishing Schema Composition from Java Class Inheritance

In an API with multiple related DTOs, Java models and OpenAPI schemas may describe similar structures while operating under different rules. Java uses class inheritance, interfaces, and object composition to organize source code. OpenAPI uses schema composition keywords such as <code>allOf</code>, <code>oneOf</code>, and <code>anyOf</code> to describe conditions a JSON payload must satisfy.

When springdoc-openapi generates documentation from controllers and DTOs, you should not assume that <code>extends</code> in Java is equivalent to <code>allOf</code> in OpenAPI. You must understand the semantics of each composition keyword, how Jackson selects types when reading polymorphic JSON, and how to declare <code>@Schema</code> so documentation accurately reflects the HTTP contract.

## 1. Two Different Conceptual Layers

Java inheritance is a relationship between types in a program. A subclass receives accessible members from its superclass, can override methods, and can be used where the supertype is expected.

OpenAPI composition is a relationship between schemas. It specifies that a JSON instance must satisfy one or more component schemas. Composition itself does not create Java classes, inherit methods, or determine how Jackson instantiates objects.

| Concept | Java | OpenAPI |
|---|---|---|
| Inheritance | <code>class Child extends Parent</code> | No <code>extends</code> operator |
| Combining structures | A class has a field referencing another object | Object property containing <code>$ref</code> |
| Satisfying multiple structures | An object must conform to multiple program types/contracts | <code>allOf</code> |
| Choosing exactly one variant | Interface or polymorphic superclass with runtime mechanism | <code>oneOf</code> |
| Accepting one or more variants | Java type and processing logic decide | <code>anyOf</code> |
| Selecting subclass when reading JSON | Jackson or another deserialization mechanism | <code>discriminator</code> aids documentation and variant identification |

The three schema composition keywords have distinct semantics:

- <code>allOf</code>: the instance must be valid against **all** listed schemas.
- <code>oneOf</code>: the instance must be valid against **exactly one** listed schema.
- <code>anyOf</code>: the instance must be valid against **at least one** listed schema; it may satisfy multiple simultaneously.

These are data validation conditions, not syntax for describing Java class relationships.

## 2. allOf: Data Must Satisfy All Schemas

<code>allOf</code> combines schemas via intersection. An object is accepted when it satisfies each component schema.

For example, multiple event types share an ID and timestamp:

~~~yaml
components:
  schemas:
    BaseEvent:
      type: object
      required:
        - eventId
      properties:
        eventId:
          type: string
          format: uuid
        occurredAt:
          type: string
          format: date-time

    OrderCreatedEvent:
      allOf:
        - $ref: "#/components/schemas/BaseEvent"
        - type: object
          required:
            - orderId
          properties:
            orderId:
              type: string
            total:
              type: number
              minimum: 0
~~~

A valid payload for <code>OrderCreatedEvent</code>:

~~~json
{
  "eventId": "550e8400-e29b-41d4-a716-446655440000",
  "occurredAt": "2026-11-20T10:30:00Z",
  "orderId": "ORD-100",
  "total": 1250.50
}
~~~

The payload must include <code>eventId</code> per the <code>BaseEvent</code> schema, and must also include <code>orderId</code> per the second schema. <code>allOf</code> does not merge properties into a new class automatically; validators check the same payload against each referenced schema.

### 2.1. allOf Is Not a Property Overriding Mechanism

Do not view <code>allOf</code> as Java inheritance with field overriding in subclasses. If two schemas declare the same property with conflicting types or constraints, an instance may be unable to satisfy both.

The following example creates an unsatisfiable condition for <code>code</code>:

~~~yaml
allOf:
  - type: object
    properties:
      code:
        type: string
  - type: object
    properties:
      code:
        type: integer
~~~

A JSON value cannot be both a string and an integer. This schema does not describe overriding a type from string to integer; it describes the intersection of the two types.

If two parts describe the same field, keep their types and constraints consistent. If the goal is two distinct data variants, use <code>oneOf</code> or <code>anyOf</code> depending on acceptance rules.

### 2.2. allOf and Java Inheritance

Java can use a base class to share fields:

~~~java
import java.time.Instant;
import java.util.UUID;

abstract class BaseEvent {
    private UUID eventId;
    private Instant occurredAt;
}

class OrderCreatedEvent extends BaseEvent {
    private String orderId;
    private java.math.BigDecimal total;
}
~~~

springdoc-openapi and swagger-core can represent Java inheritance models using <code>allOf</code>, depending on DTO types, annotations, and the model converter version. However, the generated output does not guarantee that every <code>extends</code> relationship will produce an identical <code>allOf</code> structure. Inspect the actual JSON document.

When you want to explicitly publish composition, you can declare <code>allOf</code> in the OpenAPI schema or use the <code>allOf</code> attribute on <code>@Schema</code>:

~~~java
import java.time.Instant;
import java.util.UUID;

import io.swagger.v3.oas.annotations.media.Schema;

class BaseEventSchema {
    UUID eventId;
    Instant occurredAt;
}

class OrderCreatedFields {
    String orderId;
    java.math.BigDecimal total;
}

@Schema(allOf = {BaseEventSchema.class, OrderCreatedFields.class})
class OrderCreatedEventSchema {
}
~~~

This is metadata for describing the schema. It does not make <code>OrderCreatedEventSchema</code> inherit the fields or methods of the listed classes. If you want inheritance in Java, declare <code>extends</code> separately in Java code.

## 3. oneOf: Data Must Match Exactly One Schema

Use <code>oneOf</code> when a request or response has multiple variants, and each payload may belong to only one variant.

Example of a payment system accepting cards or bank transfers:

~~~yaml
components:
  schemas:
    PaymentRequest:
      oneOf:
        - $ref: "#/components/schemas/CardPaymentRequest"
        - $ref: "#/components/schemas/BankTransferRequest"
      discriminator:
        propertyName: paymentType
        mapping:
          card: "#/components/schemas/CardPaymentRequest"
          bank-transfer: "#/components/schemas/BankTransferRequest"

    CardPaymentRequest:
      type: object
      required:
        - paymentType
        - token
      properties:
        paymentType:
          type: string
          enum: [card]
        token:
          type: string

    BankTransferRequest:
      type: object
      required:
        - paymentType
        - bankAccount
      properties:
        paymentType:
          type: string
          enum: [bank-transfer]
        bankAccount:
          type: string
~~~

Card payment payload:

~~~json
{
  "paymentType": "card",
  "token": "tok_123"
}
~~~

Bank transfer payload:

~~~json
{
  "paymentType": "bank-transfer",
  "bankAccount": "00123456789"
}
~~~

<code>oneOf</code> requires the payload to match exactly one subschema. If two subschemas are too broad and both accept a payload, that payload becomes invalid for matching more than one branch.

<code>discriminator</code> indicates which property identifies the variant and maps values to their corresponding schemas. It assists documentation and deserialization tools, yet does not replace defining subschemas or the <code>oneOf</code> condition.

## 4. anyOf: Data Must Match at Least One Schema

<code>anyOf</code> fits when data is allowed to satisfy one or more schemas in the list.

For example, a contact field may be an email or a phone number:

~~~yaml
components:
  schemas:
    ContactValue:
      anyOf:
        - type: string
          format: email
        - type: string
          pattern: "^\\+?[0-9]{8,15}$"
~~~

A payload such as <code>dev@example.com</code> matches the email branch. A phone number string matches the pattern branch. If a string satisfied both schemas, <code>anyOf</code> would still accept it because at least one valid branch suffices.

Quick comparison:

| Composition | Condition | Example usage |
|---|---|---|
| <code>allOf</code> | All schemas are valid | Shared base combined with additional constraints |
| <code>oneOf</code> | Exactly one schema is valid | One of several payment or event types |
| <code>anyOf</code> | At least one schema is valid | Data that may satisfy multiple acceptance rules |

Do not replace <code>oneOf</code> with <code>anyOf</code> just to make schemas pass validation more easily. Doing so can alter the contract: a payload matching two <code>oneOf</code> branches that should be rejected would be accepted by <code>anyOf</code>.

## 5. Java Inheritance, Composition, and JSON Polymorphism

In Java, there are three common ways to organize models:

**Inheritance:** a subclass uses <code>extends</code> to inherit members of a superclass.

~~~java
class Person {
    String name;
}

class Employee extends Person {
    String employeeCode;
}
~~~

**Composition in Java:** a class holds another object as a field. This is a has-a relationship:

~~~java
class Address {
    String city;
    String postalCode;
}

class Customer {
    String customerId;
    Address address;
}
~~~

In OpenAPI, has-a composition is described by a property with a schema reference:

~~~yaml
Customer:
  type: object
  properties:
    customerId:
      type: string
    address:
      $ref: "#/components/schemas/Address"
~~~

Do not use <code>allOf</code> merely because one DTO contains another DTO.

**Polymorphism:** a variable typed as a supertype or interface can point to multiple subtypes. When receiving JSON, the application needs a rule to determine the concrete type for deserialization. This is where Jackson polymorphism and OpenAPI <code>oneOf</code>/<code>discriminator</code> must align.

## 6. Aligning Jackson Polymorphism with OpenAPI

Jackson can use <code>@JsonTypeInfo</code> and <code>@JsonSubTypes</code> to select a subclass based on a property in JSON. OpenAPI can use <code>oneOf</code> and <code>discriminator</code> to publish the same rule to clients.

Example payment interface:

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import io.swagger.v3.oas.annotations.media.DiscriminatorMapping;
import io.swagger.v3.oas.annotations.media.Schema;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "paymentType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPaymentRequest.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransferRequest.class, name = "bank-transfer")
})
@Schema(
    name = "PaymentRequest",
    oneOf = {CardPaymentRequest.class, BankTransferRequest.class},
    discriminatorProperty = "paymentType",
    discriminatorMapping = {
        @DiscriminatorMapping(value = "card", schema = CardPaymentRequest.class),
        @DiscriminatorMapping(value = "bank-transfer", schema = BankTransferRequest.class)
    }
)
public interface PaymentRequest {
}
~~~

Two implementations:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record CardPaymentRequest(
    @Schema(allowableValues = {"card"})
    String paymentType,
    String token
) implements PaymentRequest {
}

public record BankTransferRequest(
    @Schema(allowableValues = {"bank-transfer"})
    String paymentType,
    String bankAccount
) implements PaymentRequest {
}
~~~

Controller accepting the interface:

~~~java
@PostMapping("/payments")
ResponseEntity<Void> createPayment(
        @RequestBody PaymentRequest request) {
    // Process according to the variant deserialized by Jackson
    return ResponseEntity.accepted().build();
}
~~~

In the example:

- <code>@JsonTypeInfo</code> specifies that the <code>paymentType</code> property is used to select the type when Jackson reads JSON.
- <code>@JsonSubTypes</code> maps the values <code>card</code> and <code>bank-transfer</code> to the corresponding Java classes.
- <code>@Schema(oneOf = ...)</code> describes the two possible schemas in OpenAPI.
- <code>discriminatorProperty</code> and <code>discriminatorMapping</code> describe the same variant selection rule for documentation tools.

Values in Jackson and OpenAPI must match. If Jackson uses <code>bank-transfer</code> while the discriminator mapping uses <code>transfer</code>, documentation and runtime assume two different contracts. Test sample JSON with both Swagger UI and the actual endpoint.

## 7. Representing Composition with @Schema Annotations

The <code>@Schema</code> annotation has attributes for composition:

| Attribute | Purpose |
|---|---|
| <code>allOf</code> | Lists schemas that data must satisfy simultaneously |
| <code>oneOf</code> | Lists schemas where data must match exactly one |
| <code>anyOf</code> | Lists schemas where data must match at least one |
| <code>discriminatorProperty</code> | Name of the property distinguishing variants |
| <code>discriminatorMapping</code> | Maps discriminator values to schemas |

Example of an interface with two variants:

~~~java
@Schema(
    oneOf = {CardPaymentRequest.class, BankTransferRequest.class},
    discriminatorProperty = "paymentType"
)
public interface PaymentRequest {
}
~~~

For complex models, you can use an `OpenAPI` bean or <code>OpenApiCustomizer</code> to adjust generated schemas. This helps when automatic model converters produce structures that do not match the contract or when you need to add explicit <code>allOf</code>, <code>oneOf</code>, <code>anyOf</code>, and discriminator mappings.

Do not place <code>@Schema(oneOf = ...)</code> on a type and assume Jackson automatically knows how to deserialize it. Swagger annotations describe documentation; Jackson requires separate polymorphic configuration or custom deserializers.

## 8. Important Note on additionalProperties When Using allOf

A frequent mistake is setting <code>additionalProperties: false</code> on a base schema and then extending it with <code>allOf</code>. In JSON Schema, <code>additionalProperties</code> only evaluates properties declared within that same schema. Thus, the base schema may treat new properties declared in another branch as disallowed.

Example prone to error:

~~~yaml
Base:
  type: object
  properties:
    id:
      type: string
  additionalProperties: false

Child:
  allOf:
    - $ref: "#/components/schemas/Base"
    - type: object
      properties:
        detail:
          type: string
~~~

A payload with both <code>id</code> and <code>detail</code> can be rejected by the <code>Base</code> schema because <code>detail</code> is not declared inside the <code>Base</code> branch itself.

In OpenAPI 3.0, the simple solution is not closing the object on the base schema when it still needs to be extended with <code>allOf</code>, or defining the final schema as a flattened object. If unknown properties must be rejected, redesign the schema and verify with an OAS 3.0-compatible validator.

OpenAPI 3.1 is based on JSON Schema 2020-12 and provides <code>unevaluatedProperties</code>, which can be placed on the outermost schema to restrict properties after all <code>allOf</code> branches have been evaluated:

~~~yaml
Child:
  allOf:
    - $ref: "#/components/schemas/Base"
    - type: object
      properties:
        detail:
          type: string
  unevaluatedProperties: false
~~~

Use <code>unevaluatedProperties</code> only when the document is genuinely OpenAPI 3.1 and validators in your system support this keyword. Do not put JSON Schema 2020-12 keywords into an OAS 3.0 document expecting all tools to interpret them the same way.

## 9. Choosing the Right Composition

Start from the data rules the API accepts:

| Contract requirement | How to model |
|---|---|
| An object must have shared fields and additional constraints | <code>allOf</code> |
| A payload is exactly one of the known types | <code>oneOf</code> |
| A payload is accepted if it satisfies at least one group of rules | <code>anyOf</code> |
| An object has a field holding another object | Property with <code>$ref</code> |
| A Java interface has multiple implementations | Typically described with <code>oneOf</code> and a discriminator if JSON has a type field |
| A Java subclass extends a superclass | May be represented with <code>allOf</code>, but inspect the generated schema |

Do not use <code>allOf</code> just to mimic inheritance. Do not use <code>oneOf</code> if variants can be valid simultaneously. Do not use `anyOf` when the contract requires a single variant.

## 10. Inspecting Schemas Generated by springdoc

After starting the application, fetch the JSON specification:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Check the following items:

1. <code>allOf</code>, <code>oneOf</code>, or <code>anyOf</code> appears at the expected position in the schema.
2. Every <code>$ref</code> points to an existing component without unexpected circular references.
3. <code>oneOf</code> branches are genuinely mutually exclusive for valid payloads.
4. Discriminator property and mapping match the values Jackson uses.
5. Inherited Java properties appear in the final schema.
6. <code>additionalProperties</code> does not accidentally reject properties from other branches.
7. Downstream tools such as Swagger UI, validators, and code generators read the published structure properly.

Test both documentation and runtime behavior:

- Send a valid payload for each variant.
- Send a payload missing a required property.
- Send a payload with an unsupported discriminator.
- Send a payload matching multiple <code>oneOf</code> branches simultaneously to confirm rejection.
- Send a payload matching a single <code>anyOf</code> branch to confirm acceptance.
- Test actual Jackson deserialization rather than just reading the schema.

## 11. Common Pitfalls

**Treating `allOf` as `extends`.** <code>allOf</code> is schema intersection. It does not create Java inheritance and does not override fields.

**Using `allOf` for has-a relationships.** If <code>Order</code> contains <code>Address</code>, declare an <code>address</code> property referencing the <code>Address</code> schema; do not use <code>allOf</code>.

**Using `oneOf` for overlapping schemas.** A payload matching two branches is invalid under <code>oneOf</code>. Adjust the schemas or choose <code>anyOf</code> if the contract permits matching multiple branches.

**Assuming a discriminator validates payloads automatically.** A discriminator helps identify variants, yet subschemas must still describe valid properties and constraints.

**Jackson and OpenAPI using different variant names.** Synchronize <code>@JsonSubTypes</code>, <code>discriminatorMapping</code>, and the distinguishing property's enum/constant values.

**Putting `additionalProperties: false` in a base schema.** With <code>allOf</code>, the base branch can reject fields declared by child branches. Redesign the schema for your OAS version.

**Assuming springdoc always generates `allOf` for every `extends`.** Output depends on model converters, annotations, and library versions. Inspect <code>/v3/api-docs</code> instead of relying on Java structure alone.

## 12. Pre-Publication Checklist

- [ ] Determined whether the relationship is inheritance, has-a composition, or polymorphism.
- [ ] <code>allOf</code> is used only when instances must satisfy all schemas.
- [ ] <code>oneOf</code> is used only when instances must match exactly one branch.
- [ ] <code>anyOf</code> is used when matching at least one branch suffices.
- [ ] Discriminator mapping matches the subtype values used by Jackson.
- [ ] <code>@Schema</code> annotations accurately describe the contract without being confused with runtime configuration.
- [ ] No <code>additionalProperties: false</code> in a base branch accidentally blocks extended fields.
- [ ] Verified <code>$ref</code> entries and schemas generated by springdoc.
- [ ] Tested deserializing and validating actual payloads for every variant.

## References

- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): <code>allOf</code>, <code>oneOf</code>, <code>anyOf</code>, and discriminator.
- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html): JSON Schema 2020-12 integration and schema keywords.
- [JSON Schema – Combining Schemas](https://json-schema.org/understanding-json-schema/reference/combining): semantics of <code>allOf</code>, <code>anyOf</code>, and <code>oneOf</code>.
- [JSON Schema – Object](https://json-schema.org/understanding-json-schema/reference/object): <code>properties</code>, <code>additionalProperties</code>, and <code>unevaluatedProperties</code>.
- [Jackson Annotations – JsonTypeInfo](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonTypeInfo.html): configuring subtype resolution when reading/writing JSON.
- [Swagger Core – Schema annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): declaring composition and discriminator via <code>@Schema</code>.
- [springdoc-openapi](https://springdoc.org/): generating and customizing OpenAPI specs from Spring Boot.
