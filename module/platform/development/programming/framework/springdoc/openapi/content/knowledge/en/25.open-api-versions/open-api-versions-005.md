# Differences in Composition Types, Numeric Constraints, and Schema Keywords

OpenAPI 3.0 and OpenAPI 3.1 both support schema composition keywords such as `allOf`, `oneOf`, `anyOf`, and `not`, yet how several data types and constraints are represented has changed substantially. OpenAPI 3.0 uses a custom Schema Object subset based on an older JSON Schema; OpenAPI 3.1 aligns the Schema Object with JSON Schema Draft 2020-12 and adds many standard keywords.

The most common differences encountered when upgrading are `nullable` and `exclusiveMinimum`/`exclusiveMaximum`. In OpenAPI 3.0, `nullable` is a boolean flag and exclusive bounds are also booleans paired with `minimum`/`maximum`. In OpenAPI 3.1, `null` is a data type declarable inside `type`, while exclusive bounds take numeric values directly.

When using springdoc-openapi, you must know which OpenAPI version the document is generated in, inspect the output schema at `/v3/api-docs`, and verify that downstream tools understand the keywords used. Changing the specification version does not automatically ensure the runtime API has changed or that every client generator is compatible.

## 1. OpenAPI version and API version are two separate concepts

An OpenAPI document has an `openapi` field to indicate the specification format version, such as `3.0.3` or `3.1.0`. The `info.version` field describes the version of the published API.

~~~yaml
openapi: 3.1.0
info:
  title: Product API
  version: 2.4.0
~~~

In the example:
- `openapi: 3.1.0` is the syntax and data model version of the OpenAPI document.
- `info.version: 2.4.0` is the API version following the product's release convention.

Upgrading a document from OpenAPI 3.0 to 3.1 does not require changing endpoint URLs, API versions, or running payloads. However, the new schema may be interpreted differently by validators, gateways, or code generators, so you should verify the contract and the tools consuming the document.

## 2. `allOf`, `oneOf`, `anyOf`, and `not`

Composition keywords allow combining multiple schemas to describe an instance. They have distinct logical meanings:

| Keyword | Validity condition | Interpretation |
|---|---|---|
| `allOf` | Instance must be valid against all subschemas | Intersection of schemas |
| `oneOf` | Instance must be valid against exactly one subschema | Only one branch matches |
| `anyOf` | Instance must be valid against at least one subschema | One or more branches match |
| `not` | Instance must not be valid against the specified schema | Negation of a schema |

These keywords exist in both OpenAPI 3.0 and 3.1. Importantly, they describe validation rules. They do not automatically create a Java class hierarchy, automatically convert JSON into the right DTOs, or replace the application's deserialization logic.

### 2.1. `allOf`: all subschemas must be satisfied

Suppose every product has an ID and a name; physical products add weight:

~~~yaml
components:
  schemas:
    Product:
      type: object
      required: [id, name]
      properties:
        id:
          type: string
        name:
          type: string

    PhysicalProduct:
      allOf:
        - $ref: '#/components/schemas/Product'
        - type: object
          required: [weightKg]
          properties:
            weightKg:
              type: number
              minimum: 0
~~~

A `PhysicalProduct` instance must satisfy both `Product` and the supplemental schema object. It needs `id`, `name`, and `weightKg`; properties must satisfy their respective types and constraints.

`allOf` is commonly used to reuse schemas or describe components that apply together. It can be used for inheritance-like modeling, though remember it is a validation intersection, not a command telling Java to create a subclass.

### 2.2. `oneOf`: exactly one branch is valid

A payment can use a card or a bank transfer:

~~~yaml
components:
  schemas:
    Payment:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransferPayment'

    CardPayment:
      type: object
      required: [method, cardToken]
      properties:
        method:
          type: string
          enum: [card]
        cardToken:
          type: string

    BankTransferPayment:
      type: object
      required: [method, bankAccount]
      properties:
        method:
          type: string
          enum: [bank_transfer]
        bankAccount:
          type: string
~~~

A valid instance must match exactly one of the two schemas. If a payload satisfies both branches simultaneously, `oneOf` is still invalid. Therefore, branches should be designed so they are distinguishable, typically via a discriminator property with distinct values.

### 2.3. `anyOf`: one or more branches are valid

If a search object can contain one or more criteria, `anyOf` can express the requirement that at least one subschema is valid:

~~~yaml
SearchFilter:
  anyOf:
    - $ref: '#/components/schemas/NameFilter'
    - $ref: '#/components/schemas/CategoryFilter'
~~~

A payload can satisfy both `NameFilter` and `CategoryFilter` and remain valid. If business rules require strictly one filter kind, use `oneOf` and ensure the branches do not overlap.

### 2.4. `not`: excluding a data shape

`not` can express that a value must not match the specified schema. For instance, a field must not be an empty string:

~~~yaml
NonEmptyValue:
  type: string
  not:
    const: ""
~~~

The `const` keyword belongs to JSON Schema and is supported in OpenAPI 3.1. If OpenAPI 3.0 compatibility is needed, use a representation fitting the 3.0 keyword set, such as `minLength: 1` for a non-empty string.

## 3. Discriminator helps pick branches without changing validation logic

With polymorphic schemas, `discriminator` indicates which property helps clients or tools identify the concrete schema. Example:

~~~yaml
Payment:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransferPayment'
  discriminator:
    propertyName: method
    mapping:
      card: '#/components/schemas/CardPayment'
      bank_transfer: '#/components/schemas/BankTransferPayment'
~~~

`propertyName` identifies the differentiating field; `mapping` maps field values to schemas. The `method` value in the payload must be consistent with the corresponding schema.

`discriminator` helps tools understand polymorphic selection, but it does not make an invalid payload valid. `oneOf` still requires exactly one subschema to be satisfied. The backend also needs Jackson configuration or an appropriate deserialization mechanism if receiving polymorphic payloads.

If `discriminator` is used, ensure:
- The discriminating field exists in each branch's schema.
- Field values are distinct enough to identify the branch.
- Mappings point to valid component schemas.
- Request examples demonstrate accurate discriminator values.
- The project's code generators and serializers support the chosen polymorphism approach.

## 4. `allOf` and `additionalProperties` when combining schemas

A subtle error occurs when setting `additionalProperties: false` in a base schema and then extending it with `allOf`:

~~~yaml
BaseProduct:
  type: object
  properties:
    id:
      type: string
  additionalProperties: false

PhysicalProduct:
  allOf:
    - $ref: '#/components/schemas/BaseProduct'
    - type: object
      properties:
        weightKg:
          type: number
~~~

Under schema evaluation rules, `BaseProduct` only knows about the `id` property. When the base schema closes `additionalProperties`, it may treat `weightKg` as an undeclared property and reject the payload, even though the second schema defines that property.

With OpenAPI 3.1, JSON Schema provides `unevaluatedProperties`, allowing properties to be handled after schemas are combined:

~~~yaml
BaseProduct:
  type: object
  properties:
    id:
      type: string

PhysicalProduct:
  allOf:
    - $ref: '#/components/schemas/BaseProduct'
    - type: object
      properties:
        weightKg:
          type: number
  unevaluatedProperties: false
~~~

This approach can close the schema after composition branches have evaluated properties. The base schema must not itself set `additionalProperties: false`, because that keyword would reject `weightKg` right inside the base branch before the outer schema applies `unevaluatedProperties`. Check whether your validator and code generator support `unevaluatedProperties`.

If OpenAPI 3.0 compatibility is required, design schema composition so `additionalProperties` is not closed too early. You can place the closing constraint on the complete schema or repeat the necessary structure depending on the contract, then check it with a 3.0-compatible validator.

## 5. `nullable` in OpenAPI 3.0 and the `null` type in OpenAPI 3.1

This is a crucial syntax difference when moving from 3.0 to 3.1.

### OpenAPI 3.0

OpenAPI 3.0 uses `nullable: true` alongside a `type`:

~~~yaml
Product:
  type: object
  properties:
    description:
      type: string
      nullable: true
~~~

The `description` property can hold a string or `null`. If `nullable: true` is removed, a `string`-typed property does not accept `null` per the schema description.

### OpenAPI 3.1

OpenAPI 3.1 represents `null` as a JSON Schema type:

~~~yaml
Product:
  type: object
  properties:
    description:
      type: [string, 'null']
~~~

You can use `anyOf` if a more complex type needs to be expressed:

~~~yaml
description:
  anyOf:
    - type: string
    - type: 'null'
~~~

In OpenAPI 3.1, do not continue relying on `nullable: true` as the standard 3.0 way. Use a type union containing `null` or equivalent composition.

Also distinguish an omitted property from a property with a `null` value:
- If the property is not in `required`, clients can omit the property entirely.
- If the property is in `required` and the schema permits `null`, clients must send the property, though its value can be `null`.
- If the property is in `required` and the schema forbids `null`, clients must send a valid non-null value.

`required` controls property presence; `nullable` in 3.0 or the `null` type in 3.1 controls accepted values.

## 6. `exclusiveMinimum` and `exclusiveMaximum` change data types

In OpenAPI 3.0, `exclusiveMinimum` and `exclusiveMaximum` are booleans. They make `minimum` or `maximum` an exclusive bound.

For example, quantity must be greater than 0 and less than 100:

~~~yaml
quantity:
  type: integer
  minimum: 0
  exclusiveMinimum: true
  maximum: 100
  exclusiveMaximum: true
~~~

The equivalent condition is `0 < quantity < 100`.

In OpenAPI 3.1, exclusive bounds take numeric thresholds directly:

~~~yaml
quantity:
  type: integer
  exclusiveMinimum: 0
  exclusiveMaximum: 100
~~~

Do not copy the 3.0 structure verbatim into 3.1. In 3.1, boolean values for `exclusiveMinimum` or `exclusiveMaximum` are no longer valid JSON Schema types. Conversely, putting direct numeric values into a 3.0 document does not conform to the 3.0 Schema Object.

Comparison table:

| Meaning | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Greater than 0 | `minimum: 0` + `exclusiveMinimum: true` | `exclusiveMinimum: 0` |
| Greater than or equal to 0 | `minimum: 0` | `minimum: 0` |
| Less than 100 | `maximum: 100` + `exclusiveMaximum: true` | `exclusiveMaximum: 100` |
| Less than or equal to 100 | `maximum: 100` | `maximum: 100` |

## 7. Common numeric constraints

OpenAPI supports several keywords to bound numeric values. Most share the same meaning in 3.0 and 3.1, except for how exclusive bounds are represented.

| Keyword | Meaning | Example |
|---|---|---|
| `minimum` | Minimum value, inclusive | `minimum: 0` |
| `maximum` | Maximum value, inclusive | `maximum: 100` |
| `exclusiveMinimum` | Exclusive lower bound | `exclusiveMinimum: 0` in 3.1 |
| `exclusiveMaximum` | Exclusive upper bound | `exclusiveMaximum: 100` in 3.1 |
| `multipleOf` | Value must be a multiple of the given number | `multipleOf: 0.01` |

Example of a price greater than 0 with a step of 0.01:

~~~yaml
price:
  type: number
  exclusiveMinimum: 0
  multipleOf: 0.01
~~~

This is OpenAPI 3.1 syntax. For OpenAPI 3.0, represent the lower bound with `minimum: 0` and `exclusiveMinimum: true`.

`multipleOf: 0.01` describes the mathematical condition of the schema; it does not replace exact monetary types in the application. For money, consider `BigDecimal` and explicit scale/rounding rules instead of using `double` or `float` as the primary calculation type.

### 7.1. Integer and number

- `integer` describes whole numbers.
- `number` describes numbers that may have fractional parts.
- `format` values such as `int32`, `int64`, `float`, and `double` provide representation hints for tools.

Example:

~~~yaml
quantity:
  type: integer
  format: int32
  minimum: 1

unitPrice:
  type: number
  format: double
  minimum: 0
~~~

Do not confuse `format` with a constraint. `minimum` and `maximum` set value bounds; `format` is representation metadata. Format checking strictness can vary across validators and code generators.

## 8. Other constraint groups and compatibility

Besides numeric constraints, the Schema Object has keywords for strings, arrays, and objects:

| Group | Keyword | Effect |
|---|---|---|
| String | `minLength`, `maxLength` | Bounds length |
| String | `pattern` | Requires matching a regular expression |
| Array | `minItems`, `maxItems` | Bounds element count |
| Array | `uniqueItems` | Requires distinct elements |
| Object | `required` | Requires properties to be present |
| Object | `minProperties`, `maxProperties` | Bounds property count |
| Object | `additionalProperties` | Controls unlisted properties |
| Schema | `enum` | Restricts to a set of values |
| Schema | `const` | Accepts only a single fixed value in JSON Schema, used with OpenAPI 3.1 |

Example:

~~~yaml
ProductInput:
  type: object
  required: [name, tags]
  properties:
    name:
      type: string
      minLength: 2
      maxLength: 80
      pattern: '^[A-Za-z0-9 -]+$'
    tags:
      type: array
      minItems: 1
      maxItems: 10
      uniqueItems: true
      items:
        type: string
  additionalProperties: false
~~~

`pattern` uses regular expression syntax following JSON Schema rules; do not assume every Java, JavaScript, and validator regex engine behaves identically on extended features.

In OpenAPI 3.1, many keywords from JSON Schema 2020-12 can be used, such as `const`, `if/then/else`, `dependentRequired`, `prefixItems`, and `unevaluatedProperties`. Before using these keywords, check your project's toolchain. A validator supporting OpenAPI 3.1 may understand them while an older code generator or API gateway ignores or handles them incompletely.

## 9. `readOnly`, `writeOnly`, and request/response validation

`readOnly` and `writeOnly` are useful annotations when a model is used in both requests and responses:

~~~yaml
User:
  type: object
  properties:
    id:
      type: string
      readOnly: true
    password:
      type: string
      writeOnly: true
    displayName:
      type: string
~~~

- `readOnly: true` indicates the property is returned in responses but should not be sent in requests.
- `writeOnly: true` indicates the property is sent in requests but should not be returned in responses.

These annotations help describe the contract, yet they do not automatically guarantee Jackson strips properties or the backend rejects invalid data. If requests and responses have markedly different rules, consider separate DTOs to avoid a shared schema causing confusion.

## 10. Declaring composition with Springdoc and Swagger annotations

Composition can be described with annotations on DTOs or properties. Example using `@Schema(oneOf = ...)` for a polymorphic payload:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    oneOf = {
        CardPaymentRequest.class,
        BankTransferRequest.class
    },
    discriminatorProperty = "method"
)
interface PaymentRequest {
}

@Schema(name = "CardPayment")
record CardPaymentRequest(
    String method,
    String cardToken
) {
}

@Schema(name = "BankTransferPayment")
record BankTransferRequest(
    String method,
    String bankAccount
) {
}
~~~

Annotation attributes and discriminator generation capabilities may depend on the `swagger-core` version bundled with springdoc. After building, inspect the actual OpenAPI document to confirm `oneOf`, component `$ref`, schema names, and discriminator mapping match expectations.

For complex schemas or 3.1 JSON Schema keywords not yet fully expressible via annotations, you can customize the OpenAPI model using `OpenApiCustomizer` or declare an appropriate static schema. Ensure the customizer runs on the right document/group and does not overwrite other schemas unintentionally.

Do not assume putting `@Schema(oneOf = ...)` is enough for Jackson to automatically deserialize the right subtype. Application polymorphic type handling configuration—such as `@JsonTypeInfo`/`@JsonSubTypes` or a custom deserializer—is a separate concern.

## 11. Choosing OpenAPI 3.0 or 3.1 with springdoc-openapi

Modern springdoc lines support generating OpenAPI 3.1 documents and allow configuring the document version via `springdoc.api-docs.version` if the library version in use supports that property.

Example choosing OpenAPI 3.1:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

If the downstream ecosystem only supports OpenAPI 3.0, you can choose:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

After changing the configuration, access `/v3/api-docs` and check the top field of the document:
- `openapi: 3.1.0` when 3.1 is chosen.
- `openapi: 3.0.x` when 3.0 is chosen.

Supported enum/property names depend on the springdoc version. If the configuration has no effect, check the exact version's documentation and actual dependencies rather than assuming the application switched standards.

When migrating from 3.0 to 3.1:
1. Check schemas with `nullable: true` and convert them to an appropriate `null` representation.
2. Convert `exclusiveMinimum`/`exclusiveMaximum` from booleans to numeric thresholds.
3. Check added 3.1 JSON Schema keywords.
4. Verify composition, `discriminator`, and `$ref`.
5. Run version-appropriate validators and code generators.
6. Compare client SDKs or contract tests before and after the switch.

If broad compatibility must be maintained, keep publishing 3.0 until document-consuming tools support 3.1. If JSON Schema 2020-12, union types with `null`, or new keywords are needed, choose 3.1 and test the entire pipeline.

## 12. Testing schemas with a concrete example

Suppose a product creation endpoint requires price greater than 0, quantity from 1 to 100, and a nullable description. With OpenAPI 3.1:

~~~yaml
openapi: 3.1.0
info:
  title: Product API
  version: 1.0.0
paths:
  /products:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        "201":
          description: Created
components:
  schemas:
    CreateProductRequest:
      type: object
      required: [name, price, quantity]
      properties:
        name:
          type: string
          minLength: 2
          maxLength: 80
        price:
          type: number
          exclusiveMinimum: 0
          multipleOf: 0.01
        quantity:
          type: integer
          minimum: 1
          maximum: 100
        description:
          type: [string, 'null']
~~~

Cases to test:

| Payload | Result per schema |
|---|---|
| `price: 12.50`, `quantity: 2`, `description: null` | Valid if `name` satisfies length |
| `price: 0` | Invalid due to exclusive minimum |
| `price: 12.505` | Invalid because not a multiple of 0.01 |
| `quantity: 0` | Invalid because less than minimum |
| `quantity: 101` | Invalid because greater than maximum |
| `quantity` omitted | Invalid because property is in `required` |
| `description: null` | Valid because schema accepts the `null` type |

If converting this schema to OpenAPI 3.0, two changes are needed: `description` uses `nullable: true` with `type: string`; `price` uses `minimum: 0` and `exclusiveMinimum: true`.

## 13. Common mistakes

**Using `nullable: true` in OpenAPI 3.1 as standard syntax.** Convert to `type: [string, 'null']` or composition with `type: 'null'`.

**Using `exclusiveMinimum: 0` in OpenAPI 3.0.** In 3.0, `exclusiveMinimum` is a boolean and must accompany `minimum`.

**Using boolean `exclusiveMinimum` in OpenAPI 3.1.** In 3.1, the value is a numeric threshold; booleans no longer conform to the schema.

**Confusing `oneOf` with `anyOf`.** `oneOf` demands exactly one branch; `anyOf` only needs at least one branch.

**Treating `allOf` as Java inheritance.** `allOf` is a validation intersection; separate DTO/deserializer configuration is needed to map to a class hierarchy.

**Assuming `discriminator` automatically selects subtypes and validates payloads.** Discriminator is metadata assisting schema identification; validation still follows composition schemas.

**Closing `additionalProperties` in a base schema then extending with `allOf`.** The base schema may reject properties defined in another branch. For 3.1, consider `unevaluatedProperties`; for 3.0, redesign where the schema is closed.

**Using 3.1 keywords while publishing a 3.0 document.** Check the `openapi` field and validators to ensure syntax matches the version.

**Only checking that the document renders in Swagger UI.** Successful UI rendering does not prove every keyword is understood by validators or code generators. Inspect schema output and downstream tools.

**Using `float`/`double` for money just because the schema declares `number`.** The schema describes the contract; choosing exact Java types and calculation rules still belongs to application design.

## 14. Checklist before publishing OpenAPI

- [ ] Distinguished `openapi` from `info.version`.
- [ ] Chosen OpenAPI 3.0 or 3.1 based on client, validator, and gateway capabilities.
- [ ] Used `allOf`, `oneOf`, `anyOf`, and `not` with accurate semantics.
- [ ] `oneOf` branches do not overlap unexpectedly.
- [ ] `discriminator` property and mapping match the schemas.
- [ ] Did not use 3.0 `nullable` instead of the `null` type in 3.1.
- [ ] `exclusiveMinimum`/`exclusiveMaximum` match the version's expected type.
- [ ] Tested `multipleOf`, `minimum`, and `maximum` with boundary values.
- [ ] Checked `required` independently from `null` acceptance.
- [ ] Evaluated the impact of `additionalProperties` inside composition.
- [ ] Used 3.1 JSON Schema keywords only when the toolchain supports them.
- [ ] Checked `readOnly`/`writeOnly` and request/response schemas.
- [ ] Inspected `/v3/api-docs` to confirm version and schema output.
- [ ] Ran appropriate validators, contract tests, and code generators.
- [ ] Compared clients or contracts before and after changing versions.

## References

- [OpenAPI Specification 3.0.3 – Schema Object](https://spec.openapis.org/oas/v3.0.3.html#schema-object): Schema Object and limits in OpenAPI 3.0.
- [OpenAPI Specification 3.1.1 – Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object): JSON Schema Draft 2020-12 integration in OpenAPI 3.1.
- [JSON Schema 2020-12 – Validation](https://json-schema.org/draft/2020-12/json-schema-validation): semantics of numeric, string, array, and object constraints.
- [JSON Schema – Combining schemas](https://json-schema.org/understanding-json-schema/reference/combining): `allOf`, `anyOf`, `oneOf`, and `not`.
- [springdoc-openapi](https://springdoc.org/): configuring OpenAPI versions and generating documents from Spring Boot.
- [Swagger Core – Schema annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): annotation attributes for describing schemas.
