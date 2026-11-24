# Evaluating OpenAPI 3.2 Based on Actual Full-Toolchain Support

OpenAPI 3.2 expands API descriptions with streaming media types, HTTP `QUERY`, the query string as a complete parameter, hierarchical tags, and the OAuth 2.0 Device Authorization Flow. However, a specification-valid document is not guaranteed to be handled properly by every parser, validator, documentation UI, or code generator.

When using springdoc-openapi, you must separately evaluate Springdoc's generation capabilities, `swagger-core`'s data model, parsers/validators, Swagger UI, and SDK generators. You cannot conclude the entire toolchain supports OpenAPI 3.2 merely because Swagger UI renders a file or a dependency carries the version number `3.2.0`.

This lesson evaluates the support landscape based on public releases and issues verified on 2026-11-20. Tool status changes across releases; before every upgrade, re-verify the pinned versions in your project and run your API's own compatibility test suite.

## Objectives

After this lesson, you will be able to:

- Distinguish the OpenAPI version from springdoc-openapi, `swagger-core`, and Swagger UI versions.
- Explain the notable changes in OpenAPI 3.2.
- Separately evaluate generation, reading, round-tripping, validation, rendering, and code generation from 3.2 documents.
- Recognize current limitations of Springdoc, `swagger-core`, `swagger-parser`, and OpenAPI Generator.
- Select tools with verified 3.2 support for each stage.
- Design a CI pipeline to catch new fields being dropped or misinterpreted.
- Decide when to stay on OpenAPI 3.1 and when to publish OpenAPI 3.2.
- Build a migration plan without breaking existing clients or API contracts.

## 1. Distinguishing versions before evaluating

The OpenAPI Specification (OAS) is the format describing HTTP API contracts. `springdoc-openapi`, `swagger-core`, Swagger UI, parsers, and generators are products that consume or produce that format. These products' version numbers follow independent release cycles.

Examples:

| Version string | Belongs to | Meaning |
|---|---|---|
| `openapi: 3.2.1` | OpenAPI Specification | Rules and structure of the API document |
| `springdoc-openapi: 3.2.0` | Springdoc | Library integrating Spring Boot and generating documents |
| `swagger-core: 2.2.56` | Swagger Core | Java library containing OpenAPI models, annotations, and read/write logic |
| `swagger-ui: 5.34.0` | Swagger UI | UI for presenting and testing APIs from documents |
| `openapi-generator: 7.27.0` | OpenAPI Generator | Tool for generating SDKs, server stubs, and docs |

Do not infer that `springdoc-openapi 3.2.0` supports OAS 3.2 simply because both strings share `3.2`. Springdoc 3.2.0 is a library release built for Spring Boot 4.1.x; that reflects compatibility between two Spring ecosystem products, not a claim of full OAS 3.2 feature support.

### 1.1. OAS 3.2.0 and OAS 3.2.1

OpenAPI 3.2.0 was published on 2025-09-19. Patch 3.2.1 was published on 2026-09-10. As of 2026-11-20, 3.2.1 is the latest OAS 3.2 release.

OAS follows `major.minor.patch` versioning:

- `major.minor` defines the feature set of the standard.
- `patch` fixes bugs or clarifies wording without introducing a new feature set.
- Tools supporting OAS 3.2 should handle `3.2.x` patches under the same feature set.

Therefore, a tool claiming OAS 3.2.0 support can work with 3.2.1 documents if it follows OAS patch compatibility rules. Still, verify fields fixed or clarified in the patch release.

Example document header declaration:

~~~yaml
openapi: 3.2.1
info:
  title: Product API
  version: 1.0.0
paths: {}
~~~

The `info.version` field is the API version managed by the development team. It is independent of the root `openapi` field.

## 2. Notable features in OpenAPI 3.2

Not every API needs new features. Identify which features deliver value to the current contract and verify tool support for those exact features.

### 2.1. Streaming media types and `itemSchema`

OpenAPI 3.2 describes the structure of each item in sequential streams using `itemSchema`. This is useful for Server-Sent Events (SSE), JSON Lines, JSON Text Sequences, and certain multipart streaming formats.

Example:

~~~yaml
paths:
  /events:
    get:
      summary: Stream events
      responses:
        '200':
          description: Continuous event stream
          content:
            text/event-stream:
              itemSchema:
                type: object
                required:
                  - event
                  - timestamp
                properties:
                  event:
                    type: string
                  timestamp:
                    type: string
                    format: date-time
                  data:
                    type: object
                    additionalProperties: true
~~~

`itemSchema` describes each item in the stream. It is not the schema of a single JSON response. Tools that only understand traditional `schema` may parse the document yet remain unaware of individual event structures.

### 2.2. HTTP `QUERY` and `additionalOperations`

OAS 3.2 adds the `query` operation for HTTP `QUERY`. This method lets you describe queries with a request body, suited for complex search filters without stuffing every criterion into the URL.

~~~yaml
paths:
  /products/search:
    query:
      operationId: searchProducts
      summary: Search products by criteria
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                text:
                  type: string
                categories:
                  type: array
                  items:
                    type: string
                priceRange:
                  type: object
                  properties:
                    minimum:
                      type: number
                    maximum:
                      type: number
      responses:
        '200':
          description: Search results
~~~

`additionalOperations` describes HTTP methods outside fixed fields like `get`, `post`, `put`, `delete`, `patch`, `head`, `options`, and `trace`. For example, an API with a `COPY` method can place the operation inside the `additionalOperations` map.

~~~yaml
paths:
  /products/{id}:
    additionalOperations:
      COPY:
        operationId: copyProduct
        summary: Copy product
        responses:
          '201':
            description: Product copied
~~~

Describing a method in OpenAPI does not make Spring MVC, WebFlux, reverse proxies, WAFs, or API gateways support that method automatically. Verify routing capabilities and runtime behavior separately.

### 2.3. `querystring` parameter

OAS 3.2 adds the `in: querystring` parameter location. This parameter represents the entire query string as a single value, instead of declaring individual key/value pairs with multiple `in: query` parameters.

~~~yaml
parameters:
  - name: filter
    in: querystring
    required: true
    content:
      application/x-www-form-urlencoded:
        schema:
          type: object
          properties:
            status:
              type: string
            includeArchived:
              type: boolean
            page:
              type: integer
~~~

`querystring` may appear at most once in an operation or path item and must not be combined with `in: query` parameters in the same scope. It uses `content` to describe how the entire query string is serialized rather than `schema`/`style` as in regular query parameters.

This feature is easily ignored or mishandled by older tools because the previous parameter model only supported `query`, `path`, `header`, and `cookie`.

### 2.4. Hierarchical tags

Tags in OAS 3.2 gain `summary`, `parent`, and `kind`. These can organize documentation hierarchically, by audience group, or by navigation type.

~~~yaml
tags:
  - name: products
    summary: Products
    kind: nav
  - name: product-search
    summary: Product search
    parent: products
    kind: nav
  - name: partner
    summary: Partner APIs
    kind: audience
~~~

`parent` references a declared parent tag name. Do not create parent/child cycles. `kind` is a classification string; values such as `nav`, `badge`, and `audience` are commonly used in documentation tools.

### 2.5. OAuth2 Device Authorization Flow and metadata

OAS 3.2 adds `deviceAuthorization` for OAuth2 flows, alongside `deviceAuthorizationUrl`, `oauth2MetadataUrl`, and a `deprecated` property for security schemes.

Example:

~~~yaml
components:
  securitySchemes:
    deviceOAuth:
      type: oauth2
      oauth2MetadataUrl: https://auth.example.com/.well-known/oauth-authorization-server
      flows:
        deviceAuthorization:
          deviceAuthorizationUrl: https://auth.example.com/device
          tokenUrl: https://auth.example.com/token
          scopes:
            events:read: Read events
~~~

This describes login flows for devices with limited input interfaces. The authorization server still must implement the actual flow; the OpenAPI declaration only describes the mechanism for clients.

## 3. OAS 3.2 support must be evaluated layer by layer

A tool may recognize the string `openapi: 3.2.1` without understanding new fields. Another tool may render the document yet fail to generate SDKs. Therefore, do not apply a single blanket "3.2 supported" label to the whole system.

| Level | Capability | Verification question |
|---|---|---|
| 1. Recognition | Reads version `3.2.x` | Does it reject the document simply due to the new version? |
| 2. Parsing | Reads JSON/YAML structure into models | Does it read `query`, `itemSchema`, `parent`, and `querystring`? |
| 3. Round-trip | Reads then serializes the document back | Are new fields dropped or structurally altered? |
| 4. Validation | Checks OAS 3.2 and JSON Schema rules | Does it catch invalid field combinations per the standard? |
| 5. Rendering | Displays properly in a portal or Swagger UI | Are hierarchical tags and streaming presented accurately? |
| 6. Generation | Generates SDKs, server stubs, or docs | Do new methods and schemas appear accurately in code? |
| 7. Runtime | Server and client execute the contract | Do the framework, gateway, and SDK send/receive real requests properly? |

A good result at level 5 does not prove levels 2, 3, 4, 6, or 7. Record status per level in your project's compatibility matrix.

## 4. Support status verified on 2026-11-20

The matrix below reflects public documentation, releases, and issues at the time of inspection. "Unconfirmed" means official sources have not yet demonstrated full OAS 3.2 feature support; do not interpret it as full compatibility.

| Component | Published status | Practical assessment |
|---|---|---|
| OpenAPI Specification | OAS 3.2.1 is current | Standard is stable; use 3.2.1 documentation as the reference |
| Swagger UI | 5.32.0 compatibility table lists OAS 3.2.0; Springdoc 3.2.0 bundles Swagger UI 5.34.0 | Can be used to render 3.2 documents, but does not prove Springdoc generates 3.2 |
| Springdoc | OAS 3.2 support issue #3324 remains open | Full OAS 3.2 generation from controllers is unconfirmed |
| swagger-core | README states 3.1 support; PR adding `SpecVersion.V32` and 3.2 models remains open | Do not rely on general `3.x` labels to assume new field support |
| swagger-parser | OAS 3.2 support issue #2248 remains open | This popular Java parser is not yet a confirmed choice for 3.2 documents |
| OpenAPI Generator | 7.27.0 README lists 3.1 as beta and does not list 3.2 | Do not use as default code generator for 3.2 contracts using new features |
| Redocly CLI | 2.82.0 released 2026-11-19; changelog includes OAS 3.2 fixes and features | Can be used to lint, bundle, and process many 3.2 features |
| openapi-processor/openapi-parser | Announces parsing and validation for OAS 3.2, 3.1, 3.0; supports JSON Schema 2020-12 | A Java option to evaluate independent parsing/validation |
| JetBrains IDE | IntelliJ IDEA 2026.3 documentation still notes support up to OAS 3.1 | Editor may report false errors or lack coding assistance for 3.2 |

### 4.1. Springdoc and confusion around version 3.2.0

Springdoc-openapi 3.2.0 was released on 2026-10-24 for the Spring Boot 4.1.x line. This release uses Swagger UI 5.34.0 and includes Springdoc-specific changes.

Meanwhile, the Springdoc project's "Add support for OpenAPI spec 3.2" issue remained open at the time of inspection. Consequently:

- Springdoc 3.2.0 does not mean output has `openapi: 3.2.0`.
- The bundled Swagger UI rendering an external OAS 3.2 file does not prove Springdoc can generate 3.2 models.
- You must inspect the `openapi` field in `/v3/api-docs` and new fields in the actual JSON.

For Spring Boot 3 applications, Springdoc 2.x is the line for Spring Boot 3; do not upgrade to Springdoc 3.x solely hoping to get OAS 3.2. Upgrading Springdoc's major version involves Spring Boot major versions and corresponding dependencies.

### 4.2. Swagger Core and `swagger-parser`

Swagger Core 2.2.56 was released on 2026-11-17. Its README has a compatibility table noting `3.x`, while specific guides still state 2.2.0 onward supports OpenAPI 3.1. Pull request `swagger-core #5326` adding `SpecVersion.V32`, `additionalOperations`, `itemSchema`, `querystring`, and other OAS 3.2 fields remained open at this inspection.

`swagger-parser` has had an open OAS 3.2 support issue since November 2025. Project discussions note the parser needs updates alongside `swagger-core` models. A document with `openapi: 3.2.0` may be rejected by older parsers or fail to read `query` operations.

This explains why a JavaScript-based renderer can support OAS 3.2 while Java libraries used for parsing or code generation still do not.

### 4.3. Swagger UI and rendering tools

Swagger UI 5.32.0 announces compatibility with OAS 3.2.0. Springdoc 3.2.0 embeds Swagger UI 5.34.0, so the rendering layer may be newer than the listed compatibility milestone.

However, Swagger UI only consumes documents. If `/v3/api-docs` generated by Springdoc is still OAS 3.1, the UI will not automatically upgrade the document to 3.2. When testing external 3.2 files, separately check streaming, hierarchical tags, `QUERY`, and `querystring`; a page loading without errors is not enough to prove every feature renders properly.

### 4.4. Redocly CLI and alternative Java parsers

Redocly CLI 2.x has documented 3.2 support progress in its changelog:

- Since 2.65.0, `generate-spec` includes `--openapi-version` and defaults to OAS 3.2.
- 2.64.1 fixed OAuth2 `deviceAuthorization` handling.
- 2.74.0 fixed linting for `components.mediaTypes`, `prefixEncoding`, and `itemEncoding` in 3.2 documents.
- 2.78.0 added `querystring` support for the Respect command.
- 2.82.0 is the current release as of 2026-11-19.

For Java, `openapi-processor/openapi-parser` advertises a parser and JSON Schema validator for OAS 3.2/3.1/3.0, requiring JDK 17+ and using JSON Schema draft 2020-12 for OAS 3.2. This is an option for validating documents independently of `swagger-parser`; still test it against your API's actual structures.

## 5. Do not change only the `openapi` field to upgrade versions

Changing:

~~~yaml
openapi: 3.1.0
~~~

to:

~~~yaml
openapi: 3.2.1
~~~

does not automatically make a document OAS 3.2 compliant. It only changes the version label. If the body contains `itemSchema`, `query`, `additionalOperations`, or `in: querystring`, older tools may reject, ignore, or drop them.

Even if the document does not use new fields yet, a parser that only recognizes up to 3.1 may reject version `3.2.1`. Conversely, forcing a tool to skip version checks may cause it to silently drop a new operation.

### Dangerous failures when forcing older tools to read 3.2

- Parser returns `null` or errors when it does not recognize the version.
- The `query` field is ignored and the SDK lacks the corresponding method.
- `itemSchema` is lost when re-serializing the document.
- `querystring` is converted into a normal `query` parameter, altering request serialization.
- `additionalOperations` are omitted from the document or skipped during operation generation.
- Hierarchical tags are flattened, causing portals to display the wrong structure.
- Validators fail to catch invalid rules because they do not understand new structures.

Do not use validation-bypassing flags such as `--skip-validate-spec` to treat an unsupported document as valid. If a tool does not understand a method or field, skipping validation can drop data without clear errors.

## 6. Evaluating documents with a 3.2-feature fixture

Create a small fixture containing at least the constructs your project intends to use. Do not test compatibility using only a trivial document with no new fields.

Example concise fixture:

~~~yaml
openapi: 3.2.1
info:
  title: OAS 3.2 Compatibility Fixture
  version: 1.0.0
tags:
  - name: events
    summary: Event streams
    kind: nav
  - name: event-details
    summary: Event details
    parent: events
    kind: nav
paths:
  /events:
    get:
      tags:
        - events
      responses:
        '200':
          description: Event stream
          content:
            text/event-stream:
              itemSchema:
                type: object
                properties:
                  event:
                    type: string
                  timestamp:
                    type: string
                    format: date-time
    query:
      operationId: searchEvents
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                eventType:
                  type: string
      responses:
        '200':
          description: Search results
components:
  securitySchemes:
    deviceOAuth:
      type: oauth2
      flows:
        deviceAuthorization:
          deviceAuthorizationUrl: https://auth.example.com/device
          tokenUrl: https://auth.example.com/token
          scopes:
            events:read: Read events
~~~

The fixture above includes new features: hierarchical tags, streaming `itemSchema`, HTTP `QUERY`, and device authorization. You can add an `in: querystring` parameter and `additionalOperations` in a separate fixture to isolate bugs per parser.

### 6.1. Checking parse and round-trip

For each parser tool:

1. Read the OAS 3.2.1 fixture.
2. Verify the model retains `query`, `itemSchema`, `parent`, `kind`, and `deviceAuthorization`.
3. Serialize the model back to JSON or YAML.
4. Re-parse the serialized output.
5. Compare key structures before and after the round-trip.

Do not compare raw text alone because formatters may change key order or line wrapping. Compare parsed data trees and confirm all important fields remain intact.

### 6.2. Checking validation

The validator must understand version 3.2 and the new rules. For `querystring`, test both valid and invalid cases:

- An operation has one `querystring` parameter.
- `querystring` and `query` are not declared simultaneously in the same scope.
- There is no more than one `querystring` parameter.
- `querystring` uses `content` instead of `schema`/`style`.

For `itemSchema`, check the schema of each item in the stream. For tags, verify `parent` exists and forms no cycles. For OAuth2 device flow, check `deviceAuthorizationUrl` and `tokenUrl`.

### 6.3. Checking rendering

Open the fixture in your chosen Swagger UI or portal version. Check:

- Child tags are nested under parent tags.
- `text/event-stream` displays the schema of each item.
- `QUERY` is displayed as a distinct method.
- The request body of `QUERY` appears accurately.
- Device authorization is recognized in security schemes.

If the UI misses rendering a part, compare the source JSON before concluding whether the fault lies in the parser or the UI.

### 6.4. Checking code generation

If using a code generator, verify:

- The generator does not reject `openapi: 3.2.1`.
- `QUERY` is generated into the corresponding method/client call.
- The request body of `QUERY` is preserved.
- Streaming is represented as a return type appropriate for the runtime.
- Operations inside `additionalOperations` are not skipped.
- `querystring` parameters are serialized into the full query string per the described media type.

A passing build does not mean the SDK is correct. Inspect the generated source code and run test requests against a mock server or contract test.

## 7. Springdoc's role when a project needs OAS 3.2

Springdoc is great for auto-generating OpenAPI from controllers, DTOs, and Spring annotations. However, when the model version Springdoc depends on lacks full OAS 3.2 fields, customizers cannot automatically turn arbitrary Java structures into a complete 3.2 model.

Clearly define the contract's source of truth:

### Option A: Keep Springdoc as the generator and stay on OAS 3.1

Choose this option when:

- The API uses standard HTTP constructs already supported by Springdoc.
- `QUERY`, streaming `itemSchema`, `querystring`, or other new fields are not needed.
- Current clients and pipelines rely on `swagger-parser`/OpenAPI Generator.

Keep publishing OAS 3.1.2 (or the 3.1.x version confirmed by your toolchain). There is no need to bump versions merely for a higher number.

### Option B: Maintain a standalone OAS 3.2 contract

Choose this option when the API genuinely needs 3.2 features and Springdoc cannot generate them yet. You can manage the OpenAPI 3.2.1 file as an artifact with its own source and review process, then validate it using a 3.2-capable parser/validator.

When using this option:

- Clearly designate the OAS 3.2.1 file as the published contract.
- Use Springdoc to cross-check endpoints and schemas inferred from the application.
- Maintain drift checks between controllers/runtime and the contract.
- Do not overwrite the OAS 3.2 file with auto-generated 3.1 documents.
- Document manually maintained sections and who owns updating them.

### Option C: Generate a base document then apply controlled transformation

A pipeline can take the OpenAPI generated by Springdoc as a base document and apply a transform/overlay to add 3.2 metadata. This option is appropriate only when:

- The transform uses an OAS 3.2-aware parser/model.
- JSON/YAML text is not modified via global string replacement.
- Every added field has an automated verification test.
- Round-tripping does not drop 3.2 fields.
- The final contract is validated by a 3.2-capable tool.

This is a dedicated pipeline that must be owned and tested. It does not mean Springdoc itself natively supports OAS 3.2.

## 8. Selection matrix by need

| Need | Recommended direction |
|---|---|
| Auto-generate docs from Spring Boot for standard REST | Springdoc with OAS 3.1 |
| Display OAS 3.2.1 files | A 3.2-capable Swagger UI version or verified portal |
| Lint/bundle OAS 3.2 documents | A 3.2-capable Redocly CLI version |
| Parse/validate OAS 3.2 in Java | Evaluate `openapi-processor/openapi-parser` |
| Generate SDKs from OAS 3.2 with `QUERY` or streaming | Do not default to OpenAPI Generator 7.27.0; wait for support or choose another tested generator |
| Use `QUERY` in Spring controllers | Separately verify support across Spring Framework, Spring MVC/WebFlux, gateways, and Springdoc |
| Organize hierarchical tags | Publish only after parsers and renderers preserve `parent`, `summary`, `kind` |
| APIs with SSE/JSONL streaming | Verify `itemSchema`, generators, and streaming runtime independently |

## 9. CI pipeline for OpenAPI 3.2

The pipeline should check the same artifact through every stage, without letting each tool read a different file.

Reference workflow:

~~~text
Source controllers / OpenAPI source
             |
             v
       Generate document
             |
             v
      Parse as OAS 3.2.1
             |
             v
       Validate structure
             |
             v
      Lint and bundle refs
             |
             v
       Render documentation
             |
             v
       Generate SDK / stubs
             |
             v
     Contract and runtime tests
             |
             v
        Publish artifact
~~~

At each step, record the tool version and input file checksum. If a step emits a new file, the next step must consume that exact file and run a test confirming no fields were lost.

### 9.1. Pin tool versions

Do not use `latest` or open version ranges in critical pipelines. Pin:

- Springdoc and Spring Boot.
- Actual resolved `swagger-core`, `swagger-annotations`, and Swagger UI.
- Redocly CLI or parser/validator.
- OpenAPI Generator if used.
- Runtime/browser used to verify rendering.

When upgrading, re-run the fixture containing 3.2 fields. Do not assume a new release supports the new standard just because it has a higher version number.

### 9.2. Example checks with Redocly CLI

With a Redocly CLI 2.x version confirmed to support 3.2:

~~~bash
npx @redocly/cli lint openapi/openapi.yaml
npx @redocly/cli bundle openapi/openapi.yaml --output build/openapi-bundled.yaml
~~~

Pin the CLI in `devDependencies` and lock the npm lockfile so results remain consistent across builds. If using custom rule sets, verify rules do not accidentally strip new fields or forbid valid 3.2 features.

### 9.3. Guarding against dropped fields

Add assertions for critical nodes:

| JSON path | Value to verify |
|---|---|
| `openapi` | `3.2.1` |
| `paths./events.get.responses.200.content.text/event-stream.itemSchema` | Item schema intact |
| `paths./products/search.query` | `QUERY` operation intact |
| `tags[1].parent` | Parent tag intact |
| `components.securitySchemes.deviceOAuth.flows.deviceAuthorization` | Device flow intact |

For `querystring` and `additionalOperations`, add separate fixtures so assertions are not missed by overly simple examples.

## 10. Risk assessment when using unsupported tools

| Practice | Risk |
|---|---|
| Only changing `openapi` from 3.1 to 3.2 | Document claims a standard without conforming to new fields/rules |
| Seeing UI render and concluding the toolchain passes | Parsers, validators, and generators may still fail |
| Using `--skip-validate-spec` | New operations or fields may be silently dropped |
| Parsing then serializing with a 3.1 model | Fields absent from the model may be lost |
| Editing files with regex | Can corrupt `$ref`, YAML, or nested structures |
| Using Springdoc 3.2.0 assuming version parity | Confuses library version with specification version |
| Upgrading all dependencies simultaneously | Hard to pinpoint which component altered the contract |
| Skipping runtime checks for `QUERY`/SSE | Document is valid, yet server/gateway cannot execute it |

## 11. Migration plan from OpenAPI 3.1

When deciding to move to 3.2, roll out through these steps:

1. Inventory clients, SDKs, portals, mock servers, validators, and code generators consuming OpenAPI.
2. Record each tool's current version and verify official compatibility documentation.
3. Choose a 3.2.1 fixture containing the planned features.
4. Test parsing, round-tripping, validation, rendering, and generation independently.
5. Assess the runtime impact of `QUERY`, streaming, `querystring`, and tag hierarchy.
6. Choose the source of truth: Springdoc 3.1, standalone 3.2 document, or transform pipeline.
7. Retain the current 3.1 artifact for comparison and rollback.
8. Test-generate SDKs and inspect differences in methods, schemas, and serialization.
9. Run contract tests against a real server or integration environment.
10. Publish the new document to a pilot group of clients.
11. Monitor parser, rendering, codegen, and live request errors.
12. Migrate all consumers only after every tool meets acceptance criteria.

Do not delete 3.1 documents or replace artifact endpoints actively used by clients before establishing a clear compatibility and versioning plan.

## 12. Comprehensive hands-on exercise

Evaluate a Spring Boot project using Springdoc, Swagger UI, a validator, and OpenAPI Generator:

1. Record the actual versions of Spring Boot, Springdoc, `swagger-core`, Swagger UI, and OpenAPI Generator.
2. Call `/v3/api-docs` and identify which OAS version Springdoc generates.
3. Create an OAS 3.2.1 fixture containing `itemSchema`, `query`, tag hierarchy, and `deviceAuthorization`.
4. Add an `in: querystring` parameter and `additionalOperations` in a second fixture.
5. Open the fixtures in Swagger UI and check the new features.
6. Run Redocly CLI lint/bundle and log warnings.
7. Use a 3.2-capable Java parser to parse, validate, and round-trip.
8. Try the current OpenAPI Generator; record errors, warnings, or dropped fields.
9. Compare findings against each tool's official compatibility documentation.
10. Identify which features Springdoc can auto-generate and which must be managed in a separate 3.2 contract.
11. Write tests confirming fields are not lost after each transformation step.
12. Enter the results into a compatibility matrix and propose a release decision.

### Completion criteria

- [ ] Distinguished OAS 3.2.1 from `springdoc-openapi 3.2.0`.
- [ ] Named at least three new features of OAS 3.2.
- [ ] Maintained a separate support matrix for Springdoc, models, parsers, validators, UI, and generators.
- [ ] Avoided concluding full support based solely on Swagger UI.
- [ ] Parsed and validated the 3.2.1 fixture using tools with confirmed support.
- [ ] Verified round-tripping preserves `itemSchema`, `query`, `querystring`, tag hierarchy, and security flows.
- [ ] Tested the code generator with new operations and schemas.
- [ ] Verified `QUERY`/streaming runtime beyond the documentation.
- [ ] Pinned tool versions in CI and asserted critical fields.
- [ ] Established a migration/rollback plan and contract owner.

## Next steps

After this lesson, combine OpenAPI version management with contract testing, code generation, API governance, and document distribution. When a tool announces OAS 3.2 support, verify the exact release and exact features needed; compatibility in one link does not represent the entire chain.

## References

- [OpenAPI Specification 3.2.1](https://spec.openapis.org/oas/v3.2)
- [OpenAPI 3.2.0 – Revision history and versioning](https://spec.openapis.org/oas/v3.2.0.html)
- [Swagger: launching support for OpenAPI 3.2.0 in the Swagger ecosystem](https://swagger.io/blog/swagger-launches-support-for-openapi-3-2-0/)
- [Swagger UI compatibility table](https://github.com/swagger-api/swagger-ui)
- [Springdoc issue: Add support for OpenAPI spec 3.2](https://github.com/springdoc/springdoc-openapi/issues/3324)
- [Swagger Core – compatibility and releases](https://github.com/swagger-api/swagger-core)
- [Swagger Core PR: OpenAPI 3.2 model support](https://github.com/swagger-api/swagger-core/pull/5326)
- [Swagger Parser issue: Support for OpenAPI Spec 3.2](https://github.com/swagger-api/swagger-parser/issues/2248)
- [OpenAPI Generator – compatibility](https://github.com/OpenAPITools/openapi-generator)
- [Redocly CLI changelog](https://redocly.com/docs/cli/changelog)
- [openapi-processor/openapi-parser](https://github.com/openapi-processor/openapi-parser)
- [IntelliJ IDEA – OpenAPI support](https://www.jetbrains.com/help/idea/openapi.html)
