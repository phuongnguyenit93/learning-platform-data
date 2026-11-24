# `jsonSchemaDialect` and JSON Schema Keywords to Cross-Check When Using 3.1

OpenAPI 3.1 significantly changes how data is described compared to OpenAPI 3.0: the Schema Object is built on JSON Schema Draft 2020-12 and can use corresponding JSON Schema keywords. Therefore, when reading or generating OpenAPI 3.1 documents, you must distinguish the OpenAPI version from the dialect used to interpret each Schema Object.

The top-level **jsonSchemaDialect** field declares the default dialect for Schema Objects in the document. If a schema resource has a **$schema** keyword at its root, the dialect there can override the default. Additionally, keywords such as **type**, **const**, **prefixItems**, **unevaluatedProperties**, **dependentRequired**, and **if/then/else** carry JSON Schema 2020-12 semantics. Using the wrong dialect or carrying 3.0 syntax straight into 3.1 can cause validators, code generators, and documentation tools to interpret schemas differently than intended.

## 1. Distinguishing OpenAPI version and JSON Schema dialect

OpenAPI and JSON Schema solve two different layers of concerns:

| Component | Question answered |
|---|---|
| `openapi` field | Which OpenAPI Specification version does the document conform to? |
| `jsonSchemaDialect` field | Which JSON Schema dialect are Schema Objects interpreted under by default? |
| `$schema` keyword in a schema resource | Which dialect does that specific schema resource use? |

For example, a document can declare:

~~~yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
~~~

The `openapi` value is the OpenAPI version. The `jsonSchemaDialect` value is the URI identifying the dialect for Schema Objects. The two values do not replace each other: changing `openapi` from `3.0.3` to `3.1.0` alone does not automatically interpret schemas written with new keywords properly.

The OpenAPI 3.1 Schema Object is a superset of JSON Schema Draft 2020-12, adding OpenAPI-specific keywords and rules. Therefore, do not assume every Schema Object in an OpenAPI document is equivalent to a pure JSON Schema without supplemental vocabularies.

## 2. Key differences between OpenAPI 3.0 and 3.1

OpenAPI 3.0 uses a custom schema subset closer to older JSON Schema drafts. OpenAPI 3.1 shifts to a model based on JSON Schema Draft 2020-12.

| Topic | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Schema foundation | OAS 3.0 Schema Object subset | JSON Schema Draft 2020-12 and OAS vocabulary |
| `jsonSchemaDialect` | Not present | Present on the OpenAPI Object |
| Null type | Typically uses `nullable: true` with `type` | Uses `type` with `null` value or composition |
| `exclusiveMinimum` | Boolean combined with `minimum` | Numeric value as exclusive threshold |
| `exclusiveMaximum` | Boolean combined with `maximum` | Numeric value as exclusive threshold |
| Tuple arrays | No 2020-12 `prefixItems` | Uses `prefixItems` and `items` |
| Conditional schemas | Limited to subset | Has `if`, `then`, `else` |
| Unevaluated properties/items | Not supported with 2020-12 semantics | Has `unevaluatedProperties` and `unevaluatedItems` |
| Reusable subschemas | `components/schemas` and `$ref` | Also includes `$defs`, `$anchor`, and JSON Schema mechanisms |

Do not mix syntax from the two generations. For example, in OAS 3.0, `exclusiveMinimum` is typically written as a Boolean flag alongside `minimum`. In JSON Schema 2020-12, `exclusiveMinimum` is a number. A schema valid in one generation may be rejected or misinterpreted in the other.

## 3. What is `jsonSchemaDialect`?

`jsonSchemaDialect` is a top-level property of the OpenAPI Object. It provides the default dialect for Schema Objects in the document when a schema resource does not declare its own dialect using `$schema`.

The default dialect of OpenAPI 3.1 is:

~~~yaml
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
~~~

This URI identifies the OAS base dialect. That dialect combines the required JSON Schema vocabularies with OpenAPI Schema Object extensions.

If `jsonSchemaDialect` is omitted, OpenAPI 3.1 uses the default OAS base dialect. Declaring it explicitly can help readers and some tools clearly identify the document's intent, though it is not required when using the default.

`jsonSchemaDialect` is not a URL for Swagger UI to fetch the document, nor is it an API server URL. It is a dialect identifier, not a request-handling endpoint.

## 4. Declaring a dialect at the document level

Example of an OpenAPI 3.1 document:

~~~yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
info:
  title: Store API
  version: 1.0.0
paths: {}
components:
  schemas:
    Product:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
      required:
        - id
        - name
~~~

In this example, any Schema Object that does not declare its own `$schema` uses the default dialect specified by `jsonSchemaDialect`. The document remains an OpenAPI document; the dialect only affects how schemas are interpreted, without changing paths, operations, or HTTP methods.

If using an OpenAPI generator tool, inspect the output document instead of only looking at configuration files. Verify that the `openapi` field is actually `3.1.x` and `jsonSchemaDialect` has the expected value or is applied by default.

## 5. Overriding the dialect with `$schema`

A schema resource can declare `$schema` at its root to select a specific dialect:

~~~yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
components:
  schemas:
    ExternalContract:
      $schema: https://json-schema.org/draft/2020-12/schema
      type: object
      properties:
        contractId:
          type: string
      required:
        - contractId
~~~

In this example, `$schema` at the root of `ExternalContract` overrides the document's default dialect for that schema resource. When choosing a pure JSON Schema dialect, consider OpenAPI-specific supplemental keywords such as `discriminator`, `xml`, or `externalDocs`: pure JSON Schema validators may not understand their OpenAPI semantics.

Do not place `$schema` arbitrarily on every child property. `$schema` is used to specify the dialect at the root of a schema resource; a subschema referenced independently by URI can be a separate schema resource with its own base URI rules.

## 6. JSON Schema 2020-12 keyword groups

Commonly used keywords can be grouped as follows:

| Group | Representative keywords | Purpose |
|---|---|---|
| Core and identification | `$schema`, `$id`, `$ref`, `$anchor`, `$dynamicRef`, `$dynamicAnchor`, `$defs` | Selecting dialects, identifying, and reusing schemas |
| Types and values | `type`, `enum`, `const` | Restricting types or value sets |
| Strings | `minLength`, `maxLength`, `pattern`, `format` | String constraints and format hints |
| Numbers | `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf` | Numeric value bounds |
| Arrays | `items`, `prefixItems`, `contains`, `minItems`, `maxItems`, `uniqueItems` | Describing array elements and structure |
| Objects | `properties`, `patternProperties`, `required`, `additionalProperties` | Describing object properties |
| Dependencies and evaluation | `dependentRequired`, `dependentSchemas`, `unevaluatedProperties`, `unevaluatedItems` | Dependency constraints and controlling unevaluated parts |
| Composition | `allOf`, `anyOf`, `oneOf`, `not` | Combining multiple schemas |
| Conditionals | `if`, `then`, `else` | Selecting schemas conditionally |
| Content | `contentEncoding`, `contentMediaType`, `contentSchema` | Describing encoded data or specific media types |

The list above covers commonly used keyword groups, not all of JSON Schema 2020-12. When using advanced vocabularies, verify the dialect and level of support in validators, code generators, and downstream tools.

## 7. `type`, `enum`, and `const`

`type` restricts data types. JSON Schema 2020-12 has the basic types: `object`, `array`, `string`, `number`, `integer`, `boolean`, and `null`.

~~~yaml
type: object
properties:
  quantity:
    type: integer
  unitPrice:
    type: number
  active:
    type: boolean
  note:
    type: [string, "null"]
~~~

`type` can be a single string or an array of accepted types. This is useful when a field can hold multiple types, especially `null`.

`enum` restricts values to a list:

~~~yaml
status:
  type: string
  enum:
    - pending
    - paid
    - cancelled
~~~

`const` restricts to a single fixed value:

~~~yaml
kind:
  const: physical
~~~

There is no need to use a single-element `enum` if `const` expresses the intent more clearly. Also do not confuse `const` with `default`: `const` is a value constraint; `default` is only an annotation describing an expected default value and does not automatically populate request data.

## 8. String constraints and the `format` keyword

Common string keywords:

- `minLength` and `maxLength` bound length.
- `pattern` validates strings against a regular expression.
- `format` describes semantic formats such as `date`, `date-time`, `email`, `uri`, or `uuid`.
- `contentEncoding` and `contentMediaType` describe string encoding and content media type.

Example:

~~~yaml
email:
  type: string
  format: email
  maxLength: 254
code:
  type: string
  minLength: 3
  maxLength: 12
  pattern: "^[A-Z0-9]+$"
createdAt:
  type: string
  format: date-time
~~~

`format` must be understood carefully. In JSON Schema 2020-12, `format` defaults to the annotation vocabulary; enforcing `format` as an assertion depends on the vocabulary and validator configuration. Therefore, declaring `format: email` alone does not guarantee every runtime validator rejects malformed email strings.

If format rules are business requirements, verify that the validator enables format assertion or add validation at the application layer. Do not rely on `format` as the sole validation mechanism.

## 9. Numeric constraints and exclusive bounds

Common numeric keywords:

- `minimum` and `maximum` set inclusive bounds.
- `exclusiveMinimum` and `exclusiveMaximum` set exclusive bounds.
- `multipleOf` requires the value to be a multiple of a given number.

Example in JSON Schema 2020-12:

~~~yaml
price:
  type: number
  exclusiveMinimum: 0
  multipleOf: 0.01
quantity:
  type: integer
  minimum: 1
  maximum: 1000
discountRate:
  type: number
  minimum: 0
  maximum: 1
~~~

In this example, `price` must be greater than 0 and a multiple of 0.01. `quantity` lies in the range 1 to 1000. `discountRate` accepts both 0 and 1.

Compared to OpenAPI 3.0, `exclusiveMinimum` and `exclusiveMaximum` change from Boolean to numeric values. Do not write legacy syntax such as:

~~~yaml
minimum: 0
exclusiveMinimum: true
~~~

in a 3.1 schema. The corresponding syntax is `exclusiveMinimum: 0`.

## 10. Arrays in Draft 2020-12: `items` and `prefixItems`

In JSON Schema 2020-12, `items` describes the schema applied to the remaining array elements. `prefixItems` describes positional schemas for a tuple.

Homogeneous array:

~~~yaml
tags:
  type: array
  items:
    type: string
  minItems: 1
  uniqueItems: true
~~~

Tuple with positional elements:

~~~yaml
coordinates:
  type: array
  prefixItems:
    - type: number
    - type: number
  items: false
  minItems: 2
  maxItems: 2
~~~

In the second example, the first and second elements are numbers; `items: false` forbids additional elements. `minItems` and `maxItems` force the array to have exactly two elements.

Other keywords:

- `contains` requires at least one element matching a subschema.
- `minContains` and `maxContains` bound how many elements match `contains`.
- `unevaluatedItems` controls elements not yet evaluated after applying related schemas.
- `uniqueItems` requires no duplicate elements under JSON Schema equality.

Do not use the array-form `items` syntax from older JSON Schema drafts to describe tuples in 2020-12. Use `prefixItems`.

## 11. Objects: `properties` and `additionalProperties`

Common object keywords:

- `properties` defines schemas for specifically named properties.
- `patternProperties` applies schemas based on regular expressions matching property names.
- `required` lists required property names.
- `additionalProperties` controls properties not described by `properties` or `patternProperties`.
- `propertyNames` validates the names of properties.
- `minProperties` and `maxProperties` limit the number of properties.

Example:

~~~yaml
type: object
properties:
  id:
    type: string
  name:
    type: string
    minLength: 1
required:
  - id
  - name
additionalProperties: false
~~~

In the example, `id` and `name` are required, and the object cannot contain properties outside those two declared names. If `additionalProperties` is omitted, JSON Schema permits extra properties by default.

`required` is a list of property names at the object level, not a flag placed on individual properties. Putting `required` inside a child schema does not make the parent object's property required.

## 12. `dependentRequired` and `dependentSchemas`

JSON Schema 2020-12 can describe dependencies between properties:

- `dependentRequired` requires certain other properties to exist when a given property is present.
- `dependentSchemas` applies an additional schema when the triggering property is present.

Example of `dependentRequired`:

~~~yaml
type: object
properties:
  paymentMethod:
    type: string
  cardToken:
    type: string
dependentRequired:
  paymentMethod:
    - cardToken
~~~

If the object has `paymentMethod`, then `cardToken` must also exist. This is a one-way dependency as declared; if the reverse direction is needed, it must be declared separately.

Example of `dependentSchemas`:

~~~yaml
type: object
properties:
  businessAccount:
    type: boolean
dependentSchemas:
  businessAccount:
    properties:
      taxCode:
        type: string
    required:
      - taxCode
~~~

When `businessAccount` is present, the supplemental schema applies and requires `taxCode`. Keep in mind that `dependentSchemas` triggers on the presence of the property, not on whether its value is `true` or `false`.

## 13. `unevaluatedProperties` and `unevaluatedItems`

`additionalProperties` only considers properties evaluated within the current schema object. When using composition such as `allOf` or `$ref`, you may need to control unevaluated properties across the entire combined result. JSON Schema 2020-12 provides `unevaluatedProperties` and `unevaluatedItems` for this case.

Example:

~~~yaml
type: object
allOf:
  - properties:
      id:
        type: string
    required:
      - id
  - properties:
      name:
        type: string
    required:
      - name
unevaluatedProperties: false
~~~

The schema requires `id` and `name` across two `allOf` branches while rejecting any remaining unevaluated properties. This is often cleaner than placing `additionalProperties: false` inside a sub-branch when valid properties are declared in another branch.

`unevaluatedProperties` and `unevaluatedItems` depend on JSON Schema's evaluation-tracking mechanism. Some older code generators or validators may lack full support; test with the exact tools you plan to use.

## 14. Combining schemas with `allOf`, `anyOf`, `oneOf`, and `not`

Composition keywords allow building schemas out of smaller schemas:

| Keyword | Meaning |
|---|---|
| `allOf` | Data must be valid against all subschemas |
| `anyOf` | Data must be valid against at least one subschema |
| `oneOf` | Data must be valid against exactly one subschema |
| `not` | Data must not be valid against the subschema |

Example:

~~~yaml
Payment:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransfer'
~~~

`oneOf` requires data to match strictly one of the two schemas. If a payload matches both `CardPayment` and `BankTransfer`, it is invalid under `oneOf`. If the intent is only to match at least one kind, consider `anyOf`.

`allOf` is often used to combine constraints or base models. However, `allOf` is not always equivalent to Java class inheritance. It is an intersection of schemas: data must satisfy every branch.

## 15. `if`, `then`, and `else`

JSON Schema 2020-12 supports conditional schemas:

~~~yaml
type: object
properties:
  accountType:
    type: string
    enum:
      - personal
      - business
  taxCode:
    type: string
if:
  properties:
    accountType:
      const: business
  required:
    - accountType
then:
  required:
    - taxCode
else:
  properties:
    taxCode:
      not: {}
~~~

If `accountType` is `business`, then `taxCode` is required. The `else` branch here forbids `taxCode` with any value. If business logic merely ignores `taxCode` instead of forbidding it, no constraint is needed in `else`.

When using `if`, include the condition property in `required` inside the `if` schema if you want to distinguish a missing property. If you only use `properties` with `const` without requiring the property to be present, the `if` schema can still pass when the object lacks that property.

## 16. Annotation keywords and OpenAPI-specific keywords

Not every keyword in a Schema Object is used to reject payloads. Many keywords only provide information for documentation or tools.

| Keyword | Common role |
|---|---|
| `title`, `description` | Describes the schema |
| `default` | Described default value |
| `examples` | Data examples per JSON Schema |
| `deprecated` | Marks a schema or property as deprecated |
| `readOnly` | Property primarily returned in responses |
| `writeOnly` | Property primarily sent in requests |
| `xml` | Metadata for XML representation in OpenAPI |
| `externalDocs` | External documentation link |
| `discriminator` | Assists subtype selection in OpenAPI polymorphic models |
| `example` | Legacy OAS keyword in Schema Object; deprecated in OAS 3.1 in favor of `examples` |

`default` does not automatically populate request values or modify data. `readOnly` and `writeOnly` help describe data direction, but do not automatically replace server-side sensitive data protection logic. For example, marking `password` as `writeOnly` does not guarantee the server will omit `password` if the DTO or serializer still outputs that field.

In JSON Schema, `examples` is an annotation containing an array of examples. In OpenAPI's Media Type Object, the `examples` property is a map of named examples with its own structure. Do not confuse the two locations.

## 17. Is `format` an annotation or an assertion?

`format` typically expresses semantic formatting of data, for example:

~~~yaml
birthDate:
  type: string
  format: date
website:
  type: string
  format: uri
traceId:
  type: string
  format: uuid
~~~

Under JSON Schema 2020-12, the `format-annotation` vocabulary is the default; `format-assertion` is a separate vocabulary and may be optionally implemented. Consequently, a validator may accept an improperly formatted string even when the schema has `format: date-time`.

When strict validation is required:

1. Identify the validator used to check payloads.
2. Verify whether the validator supports format assertion or enable the corresponding mode.
3. Verify the required formats are implemented.
4. Add tests with both valid and invalid values.
5. Keep application runtime validation consistent with the OpenAPI contract.

Do not assume Swagger UI or every code generator enforces `format` as a data validator.

## 18. Null in OpenAPI 3.1

OpenAPI 3.1 uses the JSON Schema model for `null`. Instead of using `nullable: true` as in OAS 3.0, you can declare:

~~~yaml
middleName:
  type:
    - string
    - "null"
~~~

Or use composition:

~~~yaml
middleName:
  anyOf:
    - type: string
    - type: "null"
~~~

An enum can also contain `null`:

~~~yaml
status:
  type:
    - string
    - "null"
  enum:
    - active
    - inactive
    - null
~~~

`nullable` is not a standard JSON Schema 2020-12 keyword. When migrating schemas from 3.0 to 3.1, convert the `nullable` intent into a type union or appropriate composition. Do not mechanically leave both `nullable: true` and a type union expecting every tool to interpret them identically.

## 19. `$id`, `$ref`, `$anchor`, and `$defs`

Identification and reference keywords enable schema reuse:

- `$id` identifies a schema resource and affects the base URI used to resolve relative references.
- `$ref` references another schema by URI.
- `$anchor` names an anchor point within a schema resource.
- `$defs` holds subschemas that can be referenced internally.
- `$dynamicAnchor` and `$dynamicRef` support dynamic references in certain recursive or extensible schemas.

Example using `$defs`:

~~~yaml
$defs:
  Identifier:
    type: string
    minLength: 1
type: object
properties:
  id:
    $ref: '#/$defs/Identifier'
  parentId:
    $ref: '#/$defs/Identifier'
~~~

In OpenAPI, `components.schemas` is also the standard place to define shared schemas:

~~~yaml
components:
  schemas:
    ProductId:
      type: string
      minLength: 1
~~~

Then reference it via:

~~~yaml
schema:
  $ref: '#/components/schemas/ProductId'
~~~

`$defs` is typically useful for internal structure within a schema resource. `components.schemas` fits models shared at the OpenAPI document level, referenced across requests, responses, or multiple operations.

## 20. `$ref` and siblings in OpenAPI 3.1

In a Schema Object, `$ref` is a JSON Schema keyword. Under JSON Schema 2020-12 semantics, sibling keywords next to `$ref` can still apply:

~~~yaml
schema:
  $ref: '#/components/schemas/Product'
  description: Product returned in the list.
~~~

This differs from how many developers are used to OpenAPI 3.0 Reference Objects, where sibling properties of `$ref` were generally ignored or lacked the same semantics. Distinguish:

- `$ref` inside a Schema Object: follows JSON Schema semantics of the active dialect.
- Reference Objects at other OpenAPI positions: follow the Reference Object rules of the OpenAPI version.

Do not assume every occurrence of `$ref` handles siblings identically. Identify the structural position of `$ref` before writing `description`, `summary`, or additional fields next to it.

## 21. Example of a complete OpenAPI 3.1 contract

The following example uses OAS 3.1's default dialect, nullable schemas, numeric constraints, and shared schemas:

~~~yaml
openapi: 3.1.0
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
info:
  title: Store API
  version: 1.0.0
paths:
  /api/orders:
    post:
      operationId: createOrder
      summary: Create order
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrder'
      responses:
        '201':
          description: Order has been created.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
components:
  schemas:
    CreateOrder:
      type: object
      additionalProperties: false
      properties:
        customerId:
          type: string
          minLength: 1
        note:
          type:
            - string
            - "null"
          maxLength: 500
        items:
          type: array
          minItems: 1
          items:
            $ref: '#/components/schemas/OrderLine'
      required:
        - customerId
        - items
    OrderLine:
      type: object
      additionalProperties: false
      properties:
        productId:
          type: string
        quantity:
          type: integer
          minimum: 1
        unitPrice:
          type: number
          exclusiveMinimum: 0
      required:
        - productId
        - quantity
        - unitPrice
    Order:
      allOf:
        - $ref: '#/components/schemas/CreateOrder'
        - type: object
          properties:
            id:
              type: string
            createdAt:
              type: string
              format: date-time
          required:
            - id
            - createdAt
~~~

This example illustrates the contract structure. In real applications, inspect schemas after springdoc generates them, especially if schemas derive from DTOs, Jackson annotations, or Bean Validation. Do not assume Java annotations automatically generate every advanced JSON Schema keyword accurately.

## 22. Impact on Springdoc and runtime validation

springdoc generates OpenAPI documents from controllers, DTOs, Swagger annotations, and partial framework metadata such as Jackson or Bean Validation. The ability to represent JSON Schema keywords depends on the springdoc version, `swagger-core`, and how data models are declared.

Points to distinguish:

- OpenAPI Schema describes the contract clients should follow.
- Spring Bean Validation checks declared constraints when triggered in the processing flow.
- Jackson controls JSON serialization/deserialization.
- JSON Schema validators validate instances according to the supported dialect and vocabulary.

Declaring a keyword in OpenAPI does not automatically make Spring MVC or WebFlux enforce that rule. For instance, `unevaluatedProperties: false` in the document does not automatically block unknown properties unless runtime has a validator enforcing that schema.

If server-side data constraints are needed, use appropriate validation such as `jakarta.validation` with `@Valid`, custom constraints, or an explicitly integrated JSON Schema validator. Then verify that the OpenAPI contract describes the same rules as runtime.

## 23. Checking downstream tools and dialects

A document may be valid under OAS 3.1 while downstream tools still support only part of JSON Schema 2020-12. Areas requiring careful checks include:

- `prefixItems` and tuple arrays.
- `unevaluatedProperties` and `unevaluatedItems`.
- `dependentSchemas` and `dependentRequired`.
- `$dynamicRef` and `$dynamicAnchor`.
- `if/then/else`.
- Format assertions.
- `$ref` siblings and URI resolution.
- OAS vocabularies such as `discriminator`, `xml`, and `readOnly`/`writeOnly`.

Before using advanced keywords in a public API, verify:

1. The OpenAPI version and `jsonSchemaDialect` of the document.
2. Whether the validator supports the corresponding dialect and vocabularies.
3. Whether Swagger UI renders the schema properly.
4. Whether code generators produce the expected data types and validations.
5. Whether gateways, contract testing tools, or API catalogs preserve the keywords.
6. Whether the pipeline tests valid and invalid payloads under the exact dialect.

Do not use an old JSON Schema validator to conclude a 2020-12 schema is invalid. Conversely, do not conclude a schema is valid just because an OpenAPI parser accepts the document: the parser may only check OpenAPI structure without enforcing all JSON Schema constraints on payloads.

## 24. Verification workflow for 3.1 schemas

A practical verification workflow:

1. Confirm the document has an `openapi` field in the `3.1.x` line.
2. Check `jsonSchemaDialect`; if omitted, note the default OAS base dialect.
3. Find schema resources containing `$schema` to identify overrides.
4. Cross-check used keywords against JSON Schema Draft 2020-12.
5. Verify `nullable` has been converted to the `null` type or composition.
6. Verify `exclusiveMinimum`/`exclusiveMaximum` use numeric values.
7. Verify tuple arrays use `prefixItems` rather than legacy array-form `items`.
8. Verify `$ref`, `$id`, `$anchor`, `$defs`, and base URI resolution.
9. Run an OpenAPI validator to confirm document structure.
10. Run a dialect-compatible JSON Schema validator to test payloads.
11. Check format assertions if business rules depend on formatting.
12. Test Swagger UI and the code generators used in the project.
13. Compare OpenAPI documents before and after changing DTOs or dependencies.

When testing payloads, prepare both valid and invalid cases. For example, for `quantity` with `minimum: 1`, verify 1 is accepted and 0 is rejected. For `additionalProperties: false`, test an object with an undeclared property. For `oneOf`, test both a payload matching exactly one branch and one matching multiple branches.

## 25. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Confusing `openapi` with `jsonSchemaDialect` | Choosing the wrong way to interpret Schema Objects | Check the OpenAPI version and dialect separately |
| Carrying `nullable: true` from OAS 3.0 to 3.1 | JSON Schema validators may ignore or handle it differently | Use a type union with `null` or composition |
| Using Boolean `exclusiveMinimum` | Wrong data type for Draft 2020-12 | Set `exclusiveMinimum` to a numeric threshold |
| Using array-form `items` for tuples | Uses legacy draft syntax | Move positional schemas to `prefixItems` |
| Using `additionalItems` in a 2020-12 schema | Tools may misunderstand tuple intent | Use `prefixItems`, `items`, and `unevaluatedItems` appropriately |
| Assuming `format` is always enforced | Malformed payloads may still be accepted | Check `format-assertion` and runtime validation |
| Treating `default` as auto-populated | Clients or servers do not automatically receive that value | Handle defaults in application logic if needed |
| Placing `required` inside a property | Parent object is not constrained as expected | Place `required` on the object schema containing the property |
| Using `additionalProperties: false` inside individual `allOf` branches | Properties declared in another branch may be rejected | Consider `unevaluatedProperties` on the combined schema |
| Confusing `$defs` with `components.schemas` | References point to the wrong location | Use the right JSON Pointer for each area |
| Assuming all `$ref` siblings follow the same rules | Descriptions or metadata get ignored | Distinguish Schema Objects from Reference Objects |
| Document is valid, yet runtime accepts bad payloads | Schema is only a contract without a runtime validator | Integrate Bean Validation or a JSON Schema validator |
| Code generator ignores new keywords | Client models fail to reflect constraints | Check 2020-12 support or pick a compatibility strategy |

## 26. Takeaways

- `openapi` determines the OpenAPI version; `jsonSchemaDialect` determines the default dialect for Schema Objects.
- OAS 3.1 defaults to `https://spec.openapis.org/oas/3.1/dialect/base`.
- `$schema` at the root of a schema resource can override the default dialect.
- The OAS 3.1 Schema Object is based on JSON Schema Draft 2020-12 and includes OpenAPI-specific vocabularies.
- Use `type`, `enum`, and `const` to restrict types and values.
- `format` defaults primarily to an annotation; verify format assertion if validators must reject malformed data.
- Use `type` containing `null` instead of `nullable: true` when writing 3.1 schemas.
- Use `prefixItems` for tuple arrays; `items` describes remaining elements.
- `exclusiveMinimum` and `exclusiveMaximum` take numeric values in Draft 2020-12.
- `dependentRequired`, `dependentSchemas`, `unevaluatedProperties`, `if/then/else`, and composition help express complex rules.
- Distinguish internal `$defs` from OpenAPI-level `components.schemas`.
- `$ref` in a Schema Object has JSON Schema semantics; Reference Objects in other OpenAPI positions have their own rules.
- A valid OpenAPI document does not prove runtime automatically enforces every JSON Schema keyword.
- Test the dialect, validators, Swagger UI, code generators, and sample payloads before publishing the contract.

When using OpenAPI 3.1, identify the dialect first before evaluating keywords in a Schema Object. Cross-check syntax against JSON Schema 2020-12, properly migrate differences from OpenAPI 3.0, and verify that downstream tools support the vocabularies used. Finally, validate the generated contract and runtime validation using real payloads.
