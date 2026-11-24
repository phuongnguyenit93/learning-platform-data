# Do Not Simply Bump the `openapi` Field Without Properly Converting the Content

The `openapi` field at the top of a document states which version of the **OpenAPI Specification (OAS)** the document conforms to. It does not automatically transform underlying structures, alter the running API contract, or serve as the API's release version number. Consequently, when upgrading a document from OpenAPI 3.0 to 3.1, merely changing `openapi: 3.0.3` to `openapi: 3.1.2` can produce a document carrying a new version label while still containing Schema Objects written under legacy rules.

The key difference lies in the Schema Object: OpenAPI 3.1 aligns with JSON Schema Draft 2020-12, whereas OpenAPI 3.0 uses a custom-adapted JSON Schema subset. Several keywords change their representation and certain ways of describing data are no longer accurate under 3.1. You must convert the content, re-validate the document, and test consuming tools before publishing.

## 1. Understanding version fields properly

An OpenAPI document carries several version pieces with different meanings:

| Field | Example | Meaning |
|---|---|---|
| `openapi` | `3.1.2` | OpenAPI Specification version the document conforms to |
| `info.version` | `2026.4` or `2.7.0` | Version of the OpenAPI document itself |
| Deployed API version | `v1`, `v2` in paths or release policy | Contract/API version exposed by the system; managed by its own convention |
| springdoc version | `2.x`, `3.x` | Document-generating library version, dependent on the Spring Boot line |

According to the specification, `openapi` and `info.version` do not substitute for one another. `openapi` helps tools pick the right rules for parsing the document; `info.version` identifies the version of the document. `info.version` also does not dictate `/v1` or `/v2` URLs, upgrade the server version, or automatically signal a compatibility change in the API.

Example:

~~~yaml
openapi: 3.1.2
info:
  title: Customer API
  version: 2.4.0
servers:
  - url: https://api.example.com/v2
paths:
  /customers:
    get:
      responses:
        '200':
          description: Customer list
~~~

In this example, `3.1.2` is the specification version; `2.4.0` is the document version set by the release team; `/v2` is the version in the API's base path. These three values can evolve independently according to product management policies.

## 2. OpenAPI versions use major, minor, and patch

OpenAPI uses `major.minor.patch` numbering. The `major.minor` portion defines the specification's feature set; the `patch` portion primarily fixes bugs or clarifies text without adding a new feature set. Therefore, patches in the same line such as 3.1.0, 3.1.1, and 3.1.2 all belong to the 3.1 feature set.

At the time of writing, relevant specification lines include:

| Line | Migration significance |
|---|---|
| OpenAPI 2.0 | Legacy format using the root field `swagger: '2.0'` |
| OpenAPI 3.0.x | Schema Object based on a JSON Schema keyword subset adapted for OAS 3.0 |
| OpenAPI 3.1.x | Aligns Schema Object with JSON Schema Draft 2020-12; requires conversion when coming from 3.0 |
| OpenAPI 3.2.x | Adds new features atop 3.1; official guides describe 3.1→3.2 as backward-compatible |

OpenAPI 3.2.1 is the latest specification release at the time of writing. It is a patch release of the 3.2 line. When picking a target version, distinguish bumping a patch within the same feature set from moving to a minor release that introduces new rules and capabilities.

## 3. Why does upgrading from 3.0 to 3.1 require updating Schema Objects?

OpenAPI 3.0 does not use full modern JSON Schema semantics. It defines its own Schema Object with several keywords and rules differing from JSON Schema. OpenAPI 3.1 aligns the Schema Object closely with JSON Schema Draft 2020-12 while adding OpenAPI-specific vocabularies.

This is beneficial because schemas can express richer data constraints and integrate better with the JSON Schema ecosystem. However, tools expecting 3.0 documents may fail to understand new keywords, while 3.1 documents still containing old keywords may no longer carry the intended meaning.

A string replacement on the document's top field does not accomplish any of the following:

- Converting `nullable` into a data type containing `null`.
- Converting the representations of `exclusiveMinimum` and `exclusiveMaximum`.
- Distinguishing `example` in a Schema Object from `example` in a Media Type Object.
- Converting file/binary descriptions into representations suitable for JSON Schema.
- Declaring or verifying the JSON Schema dialect when documents reference external schemas.
- Confirming that validators, Swagger UI, code generators, and API gateways understand the new feature set.

## 4. Converting `nullable` to a data type with `null`

In OpenAPI 3.0, `nullable: true` was used to allow `null` values:

~~~yaml
CustomerName:
  type: string
  nullable: true
~~~

In OpenAPI 3.1, use the `type` keyword with a list of data types including `null`:

~~~yaml
CustomerName:
  type:
    - string
    - 'null'
~~~

For properties in an object:

~~~yaml
Customer:
  type: object
  properties:
    displayName:
      type:
        - string
        - 'null'
    email:
      type: string
~~~

`displayName` can accept a string or `null`; `email` only accepts a string. If a property is not in the `required` list, the property can also be omitted. Distinguish these two states:

- **Optional:** the client may omit sending the property.
- **Nullable:** the property may appear with the value `null`.

These two concepts are not identical. Only add `null` to `type` when the runtime contract genuinely accepts `null` values.

### Case of schemas referenced via `$ref`

For a reusable schema, the nullable representation in 3.1 can use `anyOf` to combine the component with a `null` branch:

~~~yaml
properties:
  billingAddress:
    anyOf:
      - $ref: '#/components/schemas/Address'
      - type: 'null'
~~~

In OpenAPI 3.0, `nullable` only takes effect when `type` is explicitly declared in the same Schema Object. Thus, you cannot assume merely placing `nullable: true` next to a `$ref` makes the reference nullable. When migrating schemas involving composition or references, inspect the actual 3.0 structure first and express the appropriate union in 3.1.

Do not modify the `Address` component to be nullable if only `billingAddress` allows `null`; doing so would change semantics everywhere `Address` is referenced.

## 5. Converting `exclusiveMinimum` and `exclusiveMaximum`

In OpenAPI 3.0, these two keywords are booleans modifying `minimum` and `maximum`:

~~~yaml
age:
  type: integer
  minimum: 18
  exclusiveMinimum: true
~~~

This means the value must be greater than 18, excluding 18 itself.

In OpenAPI 3.1, `exclusiveMinimum` takes the numeric threshold directly:

~~~yaml
age:
  type: integer
  exclusiveMinimum: 18
~~~

Similarly, convert:

~~~yaml
price:
  type: number
  maximum: 100
  exclusiveMaximum: true
~~~

into:

~~~yaml
price:
  type: number
  exclusiveMaximum: 100
~~~

If `exclusiveMinimum` or `exclusiveMaximum` in the 3.0 document is `false`, keep the corresponding `minimum` or `maximum` and drop the boolean flag. Never mechanically turn every boolean into a number; read each pair of keywords to preserve inclusive versus exclusive bounds accurately.

## 6. Converting `example` in Schema Objects to `examples`

In OpenAPI 3.0, a Schema Object can use `example`:

~~~yaml
CustomerStatus:
  type: string
  enum:
    - ACTIVE
    - SUSPENDED
  example: ACTIVE
~~~

In OpenAPI 3.1, use the JSON Schema `examples` keyword with an array value:

~~~yaml
CustomerStatus:
  type: string
  enum:
    - ACTIVE
    - SUSPENDED
  examples:
    - ACTIVE
    - SUSPENDED
~~~

In OAS 3.1, the older `example` field in Schema Objects is retained for compatibility but marked deprecated; `examples` is preferred per JSON Schema. Therefore, migrating to `examples` is a recommended cleanup when standardizing 3.1 schemas, though understand this is a recommended change rather than assuming every 3.1 validator strictly rejects the legacy `example` field.

There is a very common pitfall during conversion: not every `example` field in OpenAPI 3.0 should become an `examples` array.

| Location | Handling when migrating 3.0→3.1 |
|---|---|
| Schema Object | Convert `example` to a JSON Schema `examples` array |
| Media Type Object in `requestBody`/`responses` | `example` and `examples` remain fields of the Media Type Object; keep the corresponding object structure |
| Example Object referenced via `$ref` | Keep the Example Object structure; do not turn it into a JSON Schema array |

For instance, `examples` on a Media Type Object is a named map:

~~~yaml
content:
  application/json:
    examples:
      standard:
        summary: Regular customer
        value:
          name: An
      corporate:
        summary: Corporate customer
        value:
          name: Minh Phat Company
~~~

This is not the array-structured `examples` inside a Schema Object. Identify the keyword's location before converting.

## 7. Updating file and binary data descriptions

OpenAPI 3.0 typically describes file uploads using `type: string` and `format: binary`:

~~~yaml
requestBody:
  required: true
  content:
    application/octet-stream:
      schema:
        type: string
        format: binary
~~~

OpenAPI 3.1 uses JSON Schema concepts such as `contentEncoding` and `contentMediaType` to describe encoded content and media types. For bodies sent directly as `application/octet-stream`, migration guides illustrate:

~~~yaml
requestBody:
  required: true
  content:
    application/octet-stream: {}
~~~

For Base64 strings:

~~~yaml
schema:
  type: string
  contentEncoding: base64
  contentMediaType: image/png
~~~

For a file part in multipart:

~~~yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        properties:
          file:
            type: string
            contentMediaType: application/octet-stream
~~~

Do not convert every `format: binary` into the exact same empty schema or the same `contentEncoding`. Determine whether the actual data is a raw byte stream, a Base64 string, or a multipart part with its own media type. Check how client serializers send payloads and how the server reads files so the document reflects the real wire format.

## 8. JSON Schema dialects and new keywords

OpenAPI 3.1 supports declaring the default dialect for Schema Objects via `jsonSchemaDialect`. If unspecified, OAS 3.1 uses OpenAPI 3.1's base dialect, built on JSON Schema Draft 2020-12 and OpenAPI's vocabulary.

Explicit declaration example:

~~~yaml
openapi: 3.1.2
jsonSchemaDialect: https://spec.openapis.org/oas/3.1/dialect/base
info:
  title: Customer API
  version: 2.4.0
paths: {}
components:
  schemas:
    CustomerFilter:
      type: object
      properties:
        age:
          type: integer
          minimum: 0
~~~

There is no need to add `jsonSchemaDialect` if only using the default dialect. This field is helpful when teams want to declare the dialect explicitly or apply custom schema rules. If referencing external schemas, `$schema` can be declared inside those schema documents to specify their dialect.

Once on 3.1, schemas can use JSON Schema 2020-12 keywords such as `if`, `then`, `else`, `prefixItems`, `contains`, and others suited to the data model. Still, only use them when validators, renderers, and code generators in your pipeline understand them. A spec-valid document whose keywords are ignored by older toolchains can still produce broken SDKs or docs.

## 9. Complete Schema Object migration example

Suppose a 3.0 document describes a customer:

~~~yaml
openapi: 3.0.3
info:
  title: Customer API
  version: 2.4.0
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
          example: Nguyen An
        age:
          type: integer
          minimum: 18
          exclusiveMinimum: true
~~~

After converting to 3.1.2:

~~~yaml
openapi: 3.1.2
info:
  title: Customer API
  version: 2.4.0
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
          type:
            - string
            - 'null'
          examples:
            - Nguyen An
        age:
          type: integer
          exclusiveMinimum: 18
~~~

This example illustrates the core schema changes. File descriptions must be handled separately according to exact media types and actual data transport as shown in the previous section.

## 10. Migrating from OpenAPI 2.0 requires a separate step

OpenAPI 2.0 documents use the root field:

~~~yaml
swagger: '2.0'
~~~

Do not change this field to:

~~~yaml
openapi: 3.1.2
~~~

OpenAPI 2.0 and OpenAPI 3.x differ in request body structure, response content, servers, security, and many other components. Convert Swagger 2.0 documents to OpenAPI 3.0 first, then perform the 3.0→3.1 migration.

You can use conversion tools such as `swagger2openapi` to produce an OpenAPI 3.0 draft. After conversion, still review items that cannot be fully inferred from the old document, such as server URLs, media types, schemas, security, and custom extensions.

## 11. How is migrating from OpenAPI 3.1 to 3.2 different?

Not every version bump requires a Schema Object overhaul like 3.0→3.1. OpenAPI Initiative migration guides describe moving from 3.1 to 3.2 as backward-compatible: existing 3.1 documents can continue working when updating the version field to 3.2, provided the document is genuinely valid and the toolchain supports 3.2.

At the time of writing, the latest release is 3.2.1. A migration from 3.1 to 3.2 can start with:

~~~yaml
openapi: 3.2.1
~~~

Yet do this only when validators, Swagger UI/renderers, code generators, API gateways, and consuming systems already support 3.2. If adopting new 3.2 features, add the corresponding structures and verify every consumer.

Notable new capabilities in 3.2 include:

- Hierarchical tags with `parent`, `kind` classification, and `summary` labels.
- HTTP `QUERY` method and additional operations.
- `querystring` parameter location.
- Sequential/streaming data descriptions with `itemSchema` and media types such as `application/jsonl`, `application/json-seq`.
- OAuth 2.0 Device Authorization flow and related metadata.
- Improvements to `discriminator` and data examples.

If the document only uses 3.1 features and the entire toolchain supports 3.2, updating the version can be a reasonable step. If migrating from 3.0, never use this reasoning to skip mandatory 3.1 Schema Object changes.

## 12. Configuring the OpenAPI version generated by springdoc

When springdoc generates an OpenAPI document from Spring Boot controllers, you can select the specification version using:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Or select OpenAPI 3.0:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

In current springdoc configuration docs, `springdoc.api-docs.version` selects OpenAPI 3.0 or 3.1; the published default is `openapi_3_1`. This setting controls which specification version springdoc generates from the application.

Points to remember:

- This configures documents generated by springdoc, not a generic converter for arbitrary static OpenAPI files.
- Changing the value to 3.1 does not automatically guarantee application annotations, customizers, or custom schemas conform to JSON Schema 2020-12.
- Current springdoc property docs publish choices for 3.0 and 3.1; do not manually set `OPENAPI_3_2` or edit output to `openapi: 3.2.1` while the library has not announced support.
- If a system needs OpenAPI 3.2, verify that the springdoc version and bundled `swagger-core` library officially support it before designing a 3.2 release pipeline.

After changing the configuration, fetch `/v3/api-docs` again and inspect the `openapi` field, Schema Objects, request bodies, responses, security, and components. Do not confirm only that the first line of the document changed.

## 13. Safe migration workflow

A repeatable migration workflow should include these steps:

1. **Save baseline:** save the current OpenAPI document and record `openapi`, `info.version`, document generation source, and consumers.
2. **Choose target:** determine whether moving to 3.1 or 3.2; verify validators, Swagger UI, code generators, gateways, and portals support the target.
3. **Classify source:** identify whether the document is springdoc-generated, hand-authored, or assembled from multiple `$ref` files.
4. **Convert deliberately:** use appropriate tools to generate a draft, then review `nullable`, exclusive bounds, schema examples, binary payloads, and dialects.
5. **Update version:** change the `openapi` field only after contents have been converted for the target. Keep `info.version` aligned with the team's document release policy.
6. **Validate:** run parsers, target-compatible validators, and organizational lint rules; check both external references and reused schemas.
7. **Compare contract:** diff paths, HTTP methods, parameters, required flags, request bodies, responses, media types, security, and schemas before/after.
8. **Test consumers:** render in Swagger UI, test-generate SDKs, run contract tests, and check gateways/API portals.
9. **Publish:** archive the validated OpenAPI artifact, attach version tags, and document changes; do not overwrite the baseline without a rollback plan.

If the document is auto-generated by springdoc, update annotations/models/customizers in source code so the output is accurate. Do not maintain a hand-edited OpenAPI file inside the build directory if the next build will overwrite it.

## 14. What to check after migration?

Verify layer by layer to catch defects at the right spot:

| Verification layer | Question |
|---|---|
| Syntax | Can the JSON/YAML be parsed cleanly? |
| OpenAPI structure | Do required fields and objects match the target version's structure? |
| Schema semantics | Do nullability, bounds, examples, binary, and composition keep their meaning? |
| References | Do `$ref`, `$id`, `$schema`, and external schemas resolve properly? |
| Contract | Did operations, parameters, responses, security, or media types change unexpectedly? |
| Toolchain | Do Swagger UI, validators, code generators, and API gateways understand the target version? |
| Runtime | Do real requests/responses match the published schema? |

A validator reporting valid only confirms part of the picture. It does not prove that code generators produce compatible SDKs or that the server runtime enforces the contract properly. Check the document, consuming tools, and API behavior together.

### Checking contract changes with a diff

After generating the new document, compare two versions with normalized key ordering:

~~~text
openapi-before.yaml
openapi-after.yaml
~~~

Review changes that could affect consumers:

- Properties previously required are now optional, or vice versa.
- Schemas previously rejecting `null` now accept `null`.
- Numeric bounds shifted from inclusive to exclusive, or vice versa.
- Request/response media types changed.
- Security requirements or OAuth scopes changed.
- Paths, methods, or response statuses disappeared.
- References fail to resolve or components were dropped from the document.

If contract changes appear, decide whether they are intentional changes or migration bugs before publishing.

## 15. Common mistakes

| Symptom | Possible cause | Fix |
|---|---|---|
| Validator reports `nullable` unsupported | 3.0 schema not converted to a type with `null` | Convert `nullable: true` into a `type` array or appropriate union schema |
| Integer schema accepts wrong boundary values | Incorrect conversion of `exclusiveMinimum`/`exclusiveMaximum` | Pair `minimum`/`maximum` with old boolean flags and convert to numeric values |
| Swagger UI fails to show examples | Mistakenly turned Media Type Object `example` into Schema Object array or vice versa | Check the example's location before converting |
| File upload displays wrongly | Converted `format: binary` without distinguishing raw bytes, Base64, or multipart | Describe the exact media type and actual encoding |
| One validator accepts, yet code generator fails | Generator lacks support for target OpenAPI/JSON Schema | Upgrade tool version or restrict feature set until supported |
| `$ref` fails to resolve after splitting files | Base URI, `$id`, or relative paths changed | Check resolution from the entry document and each schema document |
| Springdoc still outputs OpenAPI 3.1 when 3.2 is desired | Current property only publishes 3.0/3.1 options | Do not edit header manually; verify springdoc and `swagger-core` versions supporting 3.2 |
| `info.version` changed while `openapi` did not | Confused document version with specification version | Manage the two fields independently |
| 3.1 document labeled 3.2 rejected by older tools | Consumers do not support OAS 3.2 yet | Publish target only when the full toolchain supports it, or provide separate compatible artifacts |
| 3.0 document labeled 3.1 while schemas still use old keywords | Only edited the `openapi` field | Perform Schema Object migration and re-validate |

## 16. Checklist before bumping versions

- [ ] Identified the exact document source: springdoc, hand-written file, or multi-part document.
- [ ] Distinguished `openapi`, `info.version`, and deployed API version.
- [ ] Identified whether migrating 2.0→3.0, 3.0→3.1, or 3.1→3.2.
- [ ] If moving from 3.0 to 3.1, handled `nullable`, exclusive bounds, Schema Object examples, and binary content.
- [ ] Reviewed JSON Schema dialects and external references.
- [ ] Confirmed the toolchain supports the target version.
- [ ] If using springdoc, selected `OPENAPI_3_0` or `OPENAPI_3_1` per documented capabilities.
- [ ] Did not manually label output as 3.2 if springdoc does not yet support it.
- [ ] Ran parsers, validators, and linters on the final artifact.
- [ ] Diffed paths, operations, parameters, schemas, media types, and security.
- [ ] Tested rendering, SDK generation, and contract tests.
- [ ] Saved a baseline and prepared a rollback plan.

## 17. Official references

- [OpenAPI Specification 3.2.1](https://spec.openapis.org/oas/latest.html) — meanings of `openapi`, `info.version`, major/minor/patch versioning, and current Schema Object.
- [Upgrading from OpenAPI 3.0 to 3.1](https://learn.openapis.org/upgrading/v3.0-to-v3.1.html) — steps to migrate `nullable`, exclusive bounds, schema examples, binary content, and JSON Schema dialect.
- [Upgrading from OpenAPI 3.1 to 3.2](https://learn.openapis.org/upgrading/v3.1-to-v3.2.html) — backward compatibility and gradual adoption of new 3.2 features.
- [OpenAPI Specification v3.1.2](https://spec.openapis.org/oas/v3.1.2.html) — official specification for the 3.1 line.
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — `springdoc.api-docs.version` property, supported 3.0/3.1 values, and document settings.
- [swagger2openapi](https://github.com/Mermade/swagger2openapi) — tool to convert Swagger 2.0 to OpenAPI 3.x; validate and review output after conversion.

Upgrading an OpenAPI version changes the contract description read jointly by validators, Swagger UI, code generators, and integrating systems. Convert schema semantics before changing the version label; then validate the document and test the entire toolchain. For 3.1→3.2, you can begin by updating the version field when the 3.1 document is already valid and tools support 3.2; for 3.0→3.1, resolve JSON Schema differences before publishing.
