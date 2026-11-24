# Relationship Between Schema Object and JSON Schema Across Versions

The `Schema Object` describes data structure and validation constraints in OpenAPI. It is used for request bodies, responses, parameters, headers, and reusable models in `components.schemas`. Schema Object syntax changes significantly between OpenAPI 3.0 and 3.1 because the two versions are built on different JSON Schema foundations.

OpenAPI 3.0 supports only a subset based on JSON Schema Wright Draft 00 and adds several OpenAPI-specific keywords. OpenAPI 3.1 moves to JSON Schema Draft 2020-12 as its foundation, while defining a base dialect to add OpenAPI semantics. Consequently, a schema valid in 3.1 may use syntax that validators or code generators supporting only 3.0 will not understand.

When using springdoc-openapi, you must know which version of the document is being generated, understand the key differences in the Schema Object, and inspect the output JSON/YAML before distributing the API contract.

## 1. What does the Schema Object describe?

The Schema Object describes data shapes and data validation rules. For example, a product model can be described as follows:

```yaml
type: object
required:
  - id
  - name
properties:
  id:
    type: string
    format: uuid
  name:
    type: string
    minLength: 1
    maxLength: 120
  price:
    type: number
    minimum: 0
```

This schema specifies that the data is an object, must contain `id` and `name`, `name` is a string with length bounds, and `price` is a non-negative number.

A Schema Object can appear in many places:

- `components.schemas`: reusable model definitions.
- `requestBody.content.<media-type>.schema`: request body structure.
- `responses.<status>.content.<media-type>.schema`: response body structure.
- `parameters[].schema`: data type of query/path/header/cookie parameters.
- `headers.<name>.schema`: data type of response headers.

A schema can be referenced with `$ref` to avoid repeating definitions. OpenAPI also uses composition keywords such as `allOf`, `oneOf`, and `anyOf` to describe complex data types.

## 2. Two different JSON Schema foundations

| Topic | OpenAPI 3.0.x | OpenAPI 3.1.x |
|---|---|---|
| Schema Object foundation | Subset of JSON Schema Wright Draft 00, with OpenAPI extensions | Based on JSON Schema Draft 2020-12 and the OpenAPI base dialect |
| `type` | A single string type, e.g. `string`, `object` | Can be a single type or an array of types |
| Null values | Keyword `nullable: true` | Uses the `null` type per JSON Schema |
| `exclusiveMinimum` | Boolean combined with `minimum` | Standalone numeric value |
| Conditional schemas | Lacks the full set of modern JSON Schema keywords | Has `if`, `then`, `else`, and corresponding 2020-12 keywords |
| `prefixItems` | Not part of the 3.0 Schema Object subset | Supported per JSON Schema 2020-12 |
| `$defs` | Not part of the 3.0 Schema Object keyword set | Can be used to define subschemas per JSON Schema |
| Dialect | Schema structure defined by OpenAPI 3.0 | Has `jsonSchemaDialect` and the ability to specify an appropriate dialect |

Do not merely change the `openapi` field from `3.0.3` to `3.1.0` and keep the schemas unchanged. You must convert keywords with different semantics, check validators, and check document-consuming tools.

## 3. OpenAPI 3.0's Schema Object is a subset

OpenAPI 3.0 does not implement all of JSON Schema. It selects a keyword subset suitable for API descriptions and adds keywords such as `nullable`, `discriminator`, `readOnly`, `writeOnly`, `xml`, and `externalDocs`.

Example of a 3.0 schema object:

```yaml
openapi: 3.0.3
info:
  title: Customer API
  version: 1.0.0
paths: {}
components:
  schemas:
    Customer:
      type: object
      required:
        - id
      properties:
        id:
          type: string
          format: uuid
        displayName:
          type: string
          nullable: true
```

In 3.0, `nullable` is an OpenAPI Schema Object extension. Several newer JSON Schema keywords are not supported in this model. Putting `const`, `$defs`, `prefixItems`, `if/then/else`, or `unevaluatedProperties` into a 3.0 schema may cause validators to report errors or tools to ignore them.

Therefore, when a contract must be consumed by many legacy code generators, OpenAPI 3.0 may be the more compatible choice, provided the schema can be expressed accurately with that version's keyword set.

## 4. OpenAPI 3.1 uses JSON Schema Draft 2020-12

OpenAPI 3.1 aligns the Schema Object much more closely with JSON Schema. A Schema Object is a JSON Schema interpreted under OpenAPI 3.1's base dialect. This dialect is based on JSON Schema Draft 2020-12 and adds OpenAPI-specific rules.

Example of a 3.1 document:

```yaml
openapi: 3.1.0
info:
  title: Customer API
  version: 1.0.0
components:
  schemas:
    Customer:
      type: object
      required:
        - id
      properties:
        id:
          type: string
          format: uuid
        displayName:
          type:
            - string
            - 'null'
paths: {}
```

In this example, `displayName` can be a string or JSON `null`. There is no need to use `nullable: true` as in OpenAPI 3.0.

OpenAPI 3.1 also allows using many JSON Schema 2020-12 keywords such as `$defs`, `$id`, `$anchor`, `prefixItems`, `if`, `then`, `else`, `dependentRequired`, and `unevaluatedProperties`, as long as they follow the semantics of the selected dialect.

## 5. Key difference: `nullable` and the `null` type

This is one of the most error-prone differences when migrating from OpenAPI 3.0 to 3.1.

### OpenAPI 3.0

```yaml
type: object
properties:
  middleName:
    type: string
    nullable: true
```

`nullable: true` allows a `null` value alongside the declared type. Under 3.0 rules, `nullable` only takes effect when `type` is explicitly declared in the same Schema Object.

### OpenAPI 3.1

```yaml
type: object
properties:
  middleName:
    type:
      - string
      - 'null'
```

Or using composition:

```yaml
middleName:
  anyOf:
    - type: string
    - type: 'null'
```

In JSON Schema 2020-12, `null` is a data type. `nullable` is no longer the standard keyword for expressing a union with `null` in a 3.1 Schema Object. Keeping `nullable: true` in a 3.1 document may cause JSON Schema validators to treat it as an undefined annotation or ignore it, resulting in a schema that no longer permits `null` as intended.

### Null differs from an omitted field

`required` and nullability answer two different questions:

| Schema | Meaning |
|---|---|
| Field not in `required`, type is `string` | Field can be omitted; if sent, it must be a string |
| Field in `required`, type is `string` | Field must be present and value must be a string |
| Field not in `required`, type is `string` or `null` | Field can be omitted or sent as `null`/string |
| Field in `required`, type is `string` or `null` | Field must be present, but value can be `null` or string |

Do not use `nullable` or a union with `null` to represent an optional field. To allow a field to be absent, adjust the `required` list.

## 6. Differences in `exclusiveMinimum` and `exclusiveMaximum`

OpenAPI 3.0 uses a Boolean to enable an exclusive bound, whereas OpenAPI 3.1 follows JSON Schema 2020-12 and uses a direct numeric value.

### OpenAPI 3.0

```yaml
type: number
minimum: 0
exclusiveMinimum: true
maximum: 100
exclusiveMaximum: true
```

This schema requires a number greater than 0 and less than 100.

### OpenAPI 3.1

```yaml
type: number
exclusiveMinimum: 0
exclusiveMaximum: 100
```

In JSON Schema 2020-12, `exclusiveMinimum` and `exclusiveMaximum` take numeric values as exclusive thresholds. Do not copy `exclusiveMinimum: true` verbatim from a 3.0 schema to 3.1.

For example, when constraining a price to be greater than 0:

```yaml
# OpenAPI 3.0
type: number
minimum: 0
exclusiveMinimum: true
```

```yaml
# OpenAPI 3.1
type: number
exclusiveMinimum: 0
```

Test values equal to the threshold, below the threshold, and above the threshold when migrating schemas. Incompatible validators may misinterpret the type of this keyword.

## 7. Data types and union types

In OpenAPI 3.0, `type` is a single string value:

```yaml
type: string
```

To represent a value belonging to multiple types, `oneOf` or `anyOf` is typically used:

```yaml
oneOf:
  - type: string
  - type: integer
```

OpenAPI 3.1 under JSON Schema 2020-12 allows `type` to be an array:

```yaml
type:
  - string
  - integer
```

For nullability, you can write:

```yaml
type:
  - string
  - 'null'
```

Although 3.1 syntax is shorter, `oneOf` and `anyOf` remain useful when each branch needs its own schema, description, or discriminator. Do not replace composition with a union type merely to shorten YAML if it loses contract meaning.

## 8. Homogeneous arrays and tuples with `items`/`prefixItems`

Regular array schemas use `items` to describe every element.

OpenAPI 3.0:

```yaml
type: array
items:
  type: string
```

OpenAPI 3.1 still supports this for homogeneous arrays. JSON Schema 2020-12 adds `prefixItems` to describe tuples with positional element types:

```yaml
type: array
prefixItems:
  - type: string
  - type: integer
items: false
minItems: 2
maxItems: 2
```

The 3.1 schema above describes an array with exactly two elements: the first element is a string, the second is an integer, and no additional elements are allowed. `prefixItems` is not part of the OpenAPI 3.0 Schema Object subset.

If an API only returns a list of objects of the same type, `items` is sufficient. Only use tuples when positional order and per-position types are genuinely part of the contract.

## 9. Defining subschemas with `$defs`

OpenAPI 3.0 typically reuses schemas through `components.schemas`:

```yaml
components:
  schemas:
    Address:
      type: object
      properties:
        city:
          type: string
        postalCode:
          type: string
    Customer:
      type: object
      properties:
        address:
          $ref: '#/components/schemas/Address'
```

OpenAPI 3.1 continues to support `components.schemas`, while also allowing JSON Schema `$defs` inside a schema:

```yaml
components:
  schemas:
    Customer:
      type: object
      properties:
        address:
          $ref: '#/components/schemas/Customer/$defs/Address'
      $defs:
        Address:
          type: object
          properties:
            city:
              type: string
            postalCode:
              type: string
```

`$defs` is useful when a large schema needs to define subschemas strictly for internal use within that schema. For models shared across multiple operations, `components.schemas` is usually easier to find and reuse.

## 10. `$ref` and sibling keywords

OpenAPI 3.0 has its own Reference Object rules: a reference object primarily contains `$ref`; other sibling properties are not processed as part of an extended schema. Therefore, you should not write constraints next to `$ref` and expect all 3.0 tools to apply them.

Example of safe composition for 3.0:

```yaml
allOf:
  - $ref: '#/components/schemas/BaseName'
  - type: object
    properties:
      name:
        minLength: 3
```

In a 3.1 Schema Object, `$ref` follows JSON Schema semantics and sibling keywords can participate in schema evaluation together:

```yaml
properties:
  name:
    $ref: '#/components/schemas/Name'
    minLength: 3
```

This applies to `$ref` inside a Schema Object per JSON Schema. Do not confuse it with every Reference Object in OpenAPI, such as parameter or response references; those objects follow OpenAPI's Reference Object rules.

When migrating from 3.0 to 3.1, inspect schemas that place `description`, `summary`, or constraints next to `$ref`. Results may change because 3.1 allows different semantics from 3.0's Reference Object handling.

## 11. Composition with `allOf`, `oneOf`, `anyOf`, and `not`

Composition keywords are supported in both versions, but OpenAPI 3.1 allows broader combinations with JSON Schema keywords.

| Keyword | Meaning |
|---|---|
| `allOf` | Data must be valid against all subschemas |
| `oneOf` | Data must be valid against exactly one subschema |
| `anyOf` | Data must be valid against at least one subschema |
| `not` | Data must not be valid against the subschema |

Example using `oneOf` to describe two forms of payment information:

```yaml
oneOf:
  - $ref: '#/components/schemas/CardPayment'
  - $ref: '#/components/schemas/BankTransfer'
discriminator:
  propertyName: method
  mapping:
    card: '#/components/schemas/CardPayment'
    bank: '#/components/schemas/BankTransfer'
```

`discriminator` is an OpenAPI keyword that helps tools identify the polymorphic branch. It is not a pure JSON Schema keyword. JSON Schema validators determine validity via `oneOf`/`anyOf` and schema constraints; do not assume a validator will use `discriminator` as a replacement for checking subschemas.

## 12. Conditional schemas in OpenAPI 3.1

JSON Schema 2020-12 provides `if`, `then`, and `else` to express constraints dependent on data values.

For example, if the fulfillment method is `pickup`, the object must have `storeId`; if it is `delivery`, the object must have `address`:

```yaml
type: object
properties:
  fulfillment:
    type: string
    enum: [pickup, delivery]
  storeId:
    type: string
  address:
    type: string
required:
  - fulfillment
if:
  properties:
    fulfillment:
      const: pickup
then:
  required:
    - storeId
else:
  required:
    - address
```

These keywords are not part of the OpenAPI 3.0 Schema Object subset. When using 3.1, ensure validators, code generators, and documentation tools understand JSON Schema 2020-12. Swagger UI may display the schema, but it does not necessarily provide full interactive form handling for every conditional constraint.

## 13. `additionalProperties`, `patternProperties`, and `unevaluatedProperties`

`additionalProperties` controls properties not declared in `properties` or matching `patternProperties`. In JSON Schema, if `additionalProperties` is omitted, extra properties are accepted by default.

Example of an object that only allows declared properties:

```yaml
type: object
properties:
  id:
    type: string
  name:
    type: string
additionalProperties: false
```

OpenAPI 3.0 supports `additionalProperties` as a Boolean or Schema Object. OpenAPI 3.1 inherits this usage and also includes `patternProperties`:

```yaml
type: object
patternProperties:
  '^x-[a-z0-9-]+$':
    type: string
additionalProperties: false
```

The 3.1 schema above allows properties whose names start with `x-` and have string values, while rejecting any other undeclared properties.

### Caveat when combining with `allOf`

In schema composition, `additionalProperties: false` can cause surprises because it evaluates properties not declared in the very subschema containing that keyword. A property declared in another `allOf` branch may be treated as additional.

OpenAPI 3.1/JSON Schema 2020-12 provides `unevaluatedProperties` to handle properties not yet evaluated after applying schema composition:

```yaml
allOf:
  - $ref: '#/components/schemas/BaseCustomer'
  - type: object
    properties:
      loyaltyCode:
        type: string
unevaluatedProperties: false
```

This is a capability of modern JSON Schema and is absent from the OpenAPI 3.0 Schema Object subset. Check the validator used by your system before applying it to a production contract.

## 14. Is `format` an annotation or an assertion?

`format` typically describes a specific format for a data type:

```yaml
type: string
format: date-time
```

Common formats include `date`, `date-time`, `uuid`, `email`, `uri`, `hostname`, `ipv4`, `ipv6`, `int32`, and `int64`. Formats help readers, Swagger UI, validators, or code generators better understand the data's meaning.

However, under the JSON Schema 2020-12 model, the `format` keyword defaults to an annotation role; validators may support format assertion mode depending on configuration. Therefore, you should not assume that merely declaring `format: email` means the server already validates email addresses.

If runtime validation is needed, use Bean Validation such as `@Email`, business logic, or an appropriate validator. Springdoc can bring constraints into the schema, but displaying a format in documentation does not automatically activate data validation in controllers.

## 15. OpenAPI-specific keywords in the Schema Object

The 3.1 Schema Object uses both JSON Schema keywords and retains several OpenAPI supplemental keywords to describe APIs.

| Keyword | Role |
|---|---|
| `readOnly` | Read-only property, typically meaningful in responses |
| `writeOnly` | Write-only property, typically meaningful in requests |
| `deprecated` | Marks a schema/property as deprecated |
| `discriminator` | Assists type identification in polymorphic models |
| `xml` | Hints for XML representation |
| `externalDocs` | Links to supplementary documentation |
| `example` | Single example; deprecated in Schema Object 3.1 |

In OpenAPI 3.1, JSON Schema `examples` is an array of examples at the schema level. Distinguish it from `examples` in the Media Type Object, which is a named map to Example Objects.

`readOnly` and `writeOnly` are OpenAPI semantic metadata, not authorization mechanisms or automatic data-stripping rules on the server. For instance, marking `password` as `writeOnly: true` does not mean Jackson or Spring automatically prevents the server from returning the password; the application must use appropriate DTOs/serialization.

## 16. Dialects and `jsonSchemaDialect` in OpenAPI 3.1

OpenAPI 3.1 allows specifying the default dialect for Schema Objects using the `jsonSchemaDialect` field at the OpenAPI document level.

Example:

```yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
info:
  title: Catalog API
  version: 1.0.0
paths: {}
```

If `jsonSchemaDialect` is omitted, OpenAPI 3.1 uses the base dialect specified by the standard. An individual Schema Object can declare `$schema` to specify a different dialect when consistent with OpenAPI 3.1 rules.

The dialect determines how schema keywords are interpreted. When using a custom JSON Schema dialect, ensure validators and document-consuming tools understand that dialect. Not every OpenAPI tool supports every extended vocabulary.

## 17. Reusing schemas in `components.schemas`

For APIs where multiple operations share models, placing schemas in `components.schemas` and referencing them via `$ref` keeps the contract consistent.

```yaml
components:
  schemas:
    Money:
      type: object
      required:
        - amount
        - currency
      properties:
        amount:
          type: number
          minimum: 0
        currency:
          type: string
          minLength: 3
          maxLength: 3
    ProductResponse:
      type: object
      required:
        - id
        - price
      properties:
        id:
          type: string
          format: uuid
        price:
          $ref: '#/components/schemas/Money'
```

Requests and responses can share a schema if their structure and semantics are truly identical. If a request has writable fields that a response must not expose, consider splitting `CreateProductRequest` and `ProductResponse` rather than relying on `readOnly`/`writeOnly` without checking serialization.

## 18. Mapping Schema Objects from Java with springdoc

Springdoc reads Java types, Jackson metadata, Bean Validation, and Swagger annotations to generate Schema Objects. Example DTOs:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.UUID;

@Schema(name = "CreateProductRequest", description = "Product creation payload")
record CreateProductRequest(
        @Schema(description = "Product name", example = "Mechanical keyboard")
        @NotBlank
        @Size(max = 120)
        String name,

        @Schema(description = "Selling price", example = "129.90", minimum = "0.01")
        @DecimalMin("0.01")
        BigDecimal price
) {}

@Schema(name = "ProductResponse", description = "Product information")
record ProductResponse(
        @Schema(description = "Product ID", format = "uuid")
        UUID id,

        @Schema(description = "Product name")
        String name,

        @Schema(description = "Selling price")
        BigDecimal price
) {}
```

In this example, springdoc can infer UUIDs, numbers, `required`, and certain constraints from Java types/Bean Validation. `@Schema` adds descriptions, examples, and metadata that Java types cannot express.

Do not assume every annotation translates into the exact same JSON Schema across all versions. Check the `openapi` version and output schema to see how springdoc translated `nullable`, numeric bounds, or `required`.

## 19. Choosing OpenAPI 3.0 or 3.1 in an application

The version choice depends on the capabilities of both producers and consumers:

| Criterion | Prefer 3.0 | Prefer 3.1 |
|---|---|---|
| Legacy code generators/validators only support 3.0 | Suitable | May be incompatible |
| Need JSON Schema 2020-12 modeling | Insufficient keywords | Suitable |
| Need union types via `type` array | Use composition instead | Directly supported |
| Need `if/then/else`, `$defs`, `prefixItems` | Not in the 3.0 subset | Supported per JSON Schema 2020-12 |
| Client ecosystem already verified for 3.1 | Not required | Can standardize on 3.1 |

With springdoc, the ability to choose OpenAPI 3.0 or 3.1 depends on the springdoc version in use. If the version supports configuring `springdoc.api-docs.version`, you can select the corresponding value, for example:

```yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
```

Property names and supported values should be verified against the documentation for the exact springdoc version in your project. After changing it, check the `openapi` field in `/v3/api-docs`; do not rely solely on the declared configuration.

## 20. Process for migrating schemas from OpenAPI 3.0 to 3.1

When upgrading a document, review the following points:

1. Change the `openapi` field to version 3.1 only after producers and consumers support it.
2. Convert `nullable: true` into a union containing the `null` type or `anyOf`.
3. Convert `exclusiveMinimum: true`/`exclusiveMaximum: true` into the corresponding numeric values.
4. Check whether `type` uses valid type arrays per 3.1.
5. Check `$ref` for sibling keywords; semantics may differ from 3.0 Reference Objects.
6. Inspect schemas using new JSON Schema keywords such as `$defs`, `prefixItems`, `if/then/else`, `patternProperties`, or `unevaluatedProperties`.
7. Review `example` in Schema Objects and consider migrating to `examples` per JSON Schema.
8. Check whether `format` is being asserted by validators or only used as an annotation.
9. Verify `readOnly`, `writeOnly`, and `discriminator` are not mistaken for validation or authorization.
10. Run an OpenAPI validator and a 3.1-compatible JSON Schema validator.
11. Test-generate SDKs and run contract tests with representative clients.
12. Compare actual requests/responses before and after the upgrade.

## 21. Inspecting OpenAPI documents generated by springdoc

Fetch the JSON document:

```bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
```

Check the OpenAPI version:

```bash
jq -r '.openapi' openapi.json
```

Check generated schemas:

```bash
jq '.components.schemas.CreateProductRequest' openapi.json
jq '.components.schemas.ProductResponse' openapi.json
```

Find schemas with `nullable` or exclusive boundaries:

```bash
jq '.. | objects | select(has("nullable") or has("exclusiveMinimum") or has("exclusiveMaximum"))' openapi.json
```

For OpenAPI 3.1, verify:

- `openapi` starts with `3.1`.
- Nullability is represented using the `null` type or appropriate composition.
- `exclusiveMinimum`/`exclusiveMaximum` have numeric values.
- 2020-12 keywords are preserved in the output.
- `$ref` references resolve properly.
- `components.schemas` has no duplicate definitions or broken links.

For OpenAPI 3.0, verify:

- `openapi` starts with `3.0`.
- Nullability uses `nullable` per 3.0 rules.
- Exclusive boundaries use Boolean syntax alongside `minimum`/`maximum`.
- No new JSON Schema keywords appear that 3.0-consuming tools cannot understand.

## 22. Verifying with validators and real consumers

A parseable document does not guarantee schemas carry the expected semantics. Verification should span multiple layers:

| Verification layer | Purpose |
|---|---|
| YAML/JSON parser | Confirms valid document syntax |
| OpenAPI validator | Checks structure and rules of the OpenAPI version |
| JSON Schema validator | Checks Schema Objects against the corresponding dialect |
| Swagger UI | Checks whether the document renders and forms handle schemas sensibly |
| Code generator | Checks whether the generated SDK uses the right data types |
| Contract/integration test | Checks whether the server enforces the same semantics as the contract |

With OpenAPI 3.1, use a validator that supports JSON Schema Draft 2020-12. A validator supporting only OpenAPI 3.0 may fail on 3.1 keywords or ignore certain constraints.

Code generators also vary in support levels. For instance, a generator might parse `type: [string, 'null']` yet generate an unexpected Java type, or lack support for `unevaluatedProperties`. Inspect the generated SDK and test real `null`/optional payloads.

## 23. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| 3.1 schema still uses `nullable: true` | Carried 3.0 syntax into 3.1 | Use a type union with `null` or composition |
| `exclusiveMinimum` fails type validation | Used 3.0 Boolean in a 3.1 schema | Use a numeric value in 3.1 |
| 3.0 validator rejects `$defs` or `prefixItems` | Used JSON Schema 2020-12 keywords in a 3.0 document | Move validator/document to 3.1 or rewrite the schema |
| Nullable field treated as optional | Confused nullability with `required` | Check `type` and the `required` list separately |
| `$ref` sibling constraints are ignored | Tool applies 3.0 Reference Object rules | Use compatible schema composition or upgrade consumers to 3.1 |
| `format: email` does not reject invalid data | Validator has format assertion disabled or format is annotation-only | Use runtime validation and configure the validator appropriately |
| `additionalProperties: false` makes `allOf` schema invalid | Keyword evaluates properties within each subschema | Consider `unevaluatedProperties` in 3.1 or redesign composition |
| Swagger UI displays schema, but forms do not reflect conditionals | UI does not interactively support every JSON Schema keyword | Verify JSON Schema/contract separately; do not infer from UI forms |
| Code generator emits unexpected nullable types | Generator lacks full OpenAPI 3.1 support | Upgrade the generator version or intentionally adjust schemas |
| `readOnly` treated as data protection | Confused OpenAPI metadata with runtime serialization/security | Use DTOs, Jackson, and proper authorization |
| Document declares 3.1, but tools parse as 3.0 | Consumer does not support 3.1 yet | Upgrade consumers or keep the document at 3.0 |

## 24. Design principles

- Always inspect the `openapi` field to know which version the Schema Object follows.
- Treat the 3.0 Schema Object as a JSON Schema subset governed by OpenAPI 3.0 rules, not full modern JSON Schema.
- For 3.1, use JSON Schema 2020-12 syntax and understand OpenAPI's base dialect.
- Convert `nullable` to a union with the `null` type when upgrading from 3.0 to 3.1.
- Convert exclusive boundaries from Booleans to numeric values.
- Distinguish optional fields from fields that permit `null`.
- Use `$ref` and `components.schemas` to reuse models; use `$defs` when internal subschemas are needed in 3.1.
- Understand the difference in `$ref` siblings between a 3.1 Schema Object and an OpenAPI Reference Object.
- Only use 2020-12 keywords when validators, Swagger UI, and code generators support them.
- Treat `format` as metadata until validators/runtime are configured to enforce it.
- Do not treat `readOnly`, `writeOnly`, or `discriminator` as authorization mechanisms.
- Inspect the OpenAPI document, JSON Schemas, SDKs, and actual requests/responses after every version change.

## Conclusion

OpenAPI 3.0's Schema Object is based on an older JSON Schema subset with OpenAPI extensions; OpenAPI 3.1 transitions to JSON Schema Draft 2020-12 with its own base dialect. The most impactful differences when upgrading are `nullable` versus the `null` type, the types of `exclusiveMinimum`/`exclusiveMaximum`, `$ref` semantics, and new keywords such as `$defs`, `prefixItems`, `if/then/else`, or `unevaluatedProperties`. Springdoc can generate Schema Objects from Java types, Jackson, Bean Validation, and Swagger annotations, but the output document still needs verification using compatible validators and consumers. Choose the OpenAPI version based on your entire ecosystem's capabilities, migrate schemas deliberately, and verify the contract against runtime requests and responses.
