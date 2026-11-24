# Testing Compatibility with Parsers, UI, Code Generators, and Testing Tools

An OpenAPI document can be valid under the specification yet still fail to work across the project's full toolchain. A parser may read it while a validator misunderstands certain keywords; Swagger UI may render most operations while skipping new features; a code generator may produce incorrect clients or omit operations; contract tests may verify runtime without catching inaccurate documentation.

Therefore, compatibility testing must cover the **OpenAPI version**, **springdoc-openapi**, **parsers/validators**, **Swagger UI**, **code generators**, and **testing tools**. Do not conclude the entire ecosystem is compatible simply because a Swagger UI page opens successfully.

This article explains how to choose an OpenAPI version, understand differences among 3.0, 3.1, and 3.2, build a compatibility matrix, test downstream tools, structure CI, and upgrade specifications step by step.

## 1. Distinguishing version layers

In a Spring Boot project, multiple independent versions exist:

| Layer | Example | Meaning |
|---|---|---|
| Spring Boot | 3.x or 4.x | Application platform |
| springdoc-openapi | 2.x or 3.x | Library reading Spring metadata and generating OpenAPI |
| OpenAPI Specification | 3.0, 3.1, or 3.2 | Format version of the generated document |
| Swagger Core / swagger-models | 2.x or 3.x | OpenAPI models and annotations used by springdoc |
| Swagger UI | 5.x | UI reading and displaying the document |
| Parser / validator | e.g. `swagger-parser` | Reads, parses, and validates documents |
| Code generator | e.g. OpenAPI Generator | Generates clients or server stubs |
| Contract test tool | Tool checking requests/responses against the spec | Compares documents against runtime behavior |

These versions are not synonymous. `springdoc 3.x` does not mean output documents automatically use OpenAPI 3.2. OpenAPI 3.1 also does not mean the project's Swagger UI, parser, and generator already support all 3.1 features.

When reporting compatibility bugs, record the exact version of every layer. Simply writing “using OpenAPI 3” is not enough to reproduce the issue.

## 2. OpenAPI versions to recognize

OpenAPI uses `major.minor.patch` version strings. Common branches today include:

| Branch | Representative patch version | Key points |
|---|---|---|
| OpenAPI 3.0 | 3.0.4 | Broadly supported by older tools; Schema Object uses a custom JSON Schema subset |
| OpenAPI 3.1 | 3.1.2 | Aligns Schema Object with JSON Schema 2020-12 and changes how `null` is described |
| OpenAPI 3.2 | 3.2.1 | Adds capabilities such as nested tags, extended operation methods, streaming, and document identity |

At the time of writing, OpenAPI 3.2.1 is the latest release; 3.2.0 was published on 2025-09-19 and 3.2.1 is a patch release on 2026-09-10. Patch releases primarily fix bugs and clarify the specification without creating a new feature set within the same minor branch.

Under OpenAPI's versioning convention, `major.minor` defines the feature set. Tools supporting a minor branch should aim for compatibility with patch releases in that branch. Even so, projects still need to run parsers, UI, generators, and tests against the exact published document.

Do not manually bump the `openapi` field in JSON from `3.1.0` to `3.2.1` if the document is still built under the 3.1 model. Changing the version number does not automatically add objects, keywords, or rules from the new version.

## 3. Key differences between OpenAPI 3.0 and 3.1

A major difference lies in the Schema Object.

OpenAPI 3.0 uses a custom JSON Schema subset. For instance, the `nullable` property can be used to describe `null` values:

~~~yaml
type: string
nullable: true
~~~

OpenAPI 3.1 is based on JSON Schema 2020-12. Data types can include `null` using JSON Schema syntax:

~~~yaml
type:
  - string
  - "null"
~~~

This directly impacts parsers, validators, UI, and code generators. An older tool may understand 3.0 `nullable` yet mishandle a 3.1 `type` array containing `null`.

Items to check when migrating from 3.0 to 3.1:

- How `nullable` and union types are represented.
- JSON Schema keywords and dialects.
- `$schema` and `jsonSchemaDialect` if used.
- `exclusiveMinimum`, `exclusiveMaximum`, and constraints.
- `oneOf`, `anyOf`, `allOf`, and `discriminator`.
- `$ref`, anchors, and reference resolution.
- Whether schemas are inline or placed in `components`.
- How client generators map optional, nullable, and enums to the target language.

Do not merely change the `openapi` field value. Re-inspect generated schemas and generated client code.

## 4. Notable additions in OpenAPI 3.2

OpenAPI 3.2 adds several capabilities that older tools may not recognize yet:

- Tags gain `summary`, `parent`, and `kind` to organize documentation hierarchically.
- HTTP `QUERY` is supported as a standard operation method.
- `additionalOperations` allows describing HTTP methods beyond the familiar operation keys.
- `$self` provides document identity/base URI for resolving relative references.
- Enhanced descriptions for streaming and related media types.
- Improvements to examples, `discriminator`, and several other areas.

Example of nested tags:

~~~yaml
tags:
  - name: orders
    summary: Order management
    kind: nav
  - name: order-admin
    parent: orders
    summary: Order administration operations
~~~

Example of a `QUERY` operation:

~~~yaml
paths:
  /orders/search:
    query:
      summary: Query orders by criteria
      responses:
        "200":
          description: Query results
~~~

A parser that only knows OpenAPI 3.1 methods may reject or ignore the `QUERY` operation. Code generators may likewise fail to generate the corresponding method.

Therefore, before adopting new 3.2 features, verify each downstream tool. A document that renders does not prove the code generator understands new operations.

## 5. Checking springdoc-openapi capabilities

springdoc has two responsibilities to distinguish:

1. Compatibility with Spring Boot and Spring Framework versions.
2. Selecting which OpenAPI version the output document uses.

The current Spring Boot and springdoc compatibility matrix is published by major lines:

| Spring Boot | Corresponding springdoc line |
|---|---|
| Spring Boot 4.x | springdoc 3.x |
| Spring Boot 3.x | springdoc 2.x |
| Spring Boot 2.x and 1.x | springdoc 1.8.0; this branch is end-of-life for open-source support |

Current documentation also distinguishes Spring Boot 4.0.x from 4.1.x across springdoc minor releases. Use the compatibility table on the official site at upgrade time rather than pairing arbitrary Boot and springdoc versions.

The `springdoc.api-docs.version` property currently allows selecting OpenAPI 3.0 or 3.1. The default value published in current configuration docs is `openapi_3_1`. There is not yet an `OPENAPI_3_2` option in that property list.

`application.yml`:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Or select 3.0:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Do not invent an `OPENAPI_3_2` value if your springdoc version does not support it. Unsupported settings may be ignored, fail binding as an invalid string, or fail to produce a document matching the intended feature set.

## 6. Note on current OpenAPI 3.2 support in springdoc

At the time of writing, springdoc properties documentation lists OpenAPI 3.0 and 3.1 options. The request to add OpenAPI 3.2 support is still tracked in an upstream issue.

This means:

- Do not assume current springdoc can generate full OpenAPI 3.2 simply because the library has a new major version.
- Do not edit the `openapi` field in JSON after generation to fake 3.2.
- Do not add 3.2 structures to the OpenAPI model if your project's `swagger-core`/`swagger-models` cannot represent them yet.
- If 3.2 features are needed right away, you may need an independent spec-generation pipeline or a 3.2-capable authoring tool.
- If the application relies on springdoc to generate docs, choose 3.0 or 3.1 via the supported property and test consuming tools accordingly.

This reflects status as of 2026-11-20. When upgrading a project, check the changelog and properties of the exact pinned springdoc version because support status can change.

## 7. Building a compatibility matrix for the whole toolchain

A solid matrix records actual versions and test outcomes:

| Component | Pinned version | OAS tested | Outcome |
|---|---|---|---|
| springdoc-openapi | Version in build | 3.0 / 3.1 | Generates document and accurate schemas |
| Swagger UI | Packaged version | 3.1 or 3.2 | Renders operations, security, and schemas |
| Swagger Parser | Version in tests | 3.1 or 3.2 | Parses and resolves references |
| OpenAPI Generator | CLI/plugin version | 3.1 or 3.2 | Validates, generates client, and compiles |
| Contract validator | Pinned version | 3.1 or 3.2 | Validates documents and responses |
| WebTestClient/MockMvc | Spring Boot version | Runtime API | Requests/responses match the contract |

Never write “latest” as a version in the matrix. Use concrete version numbers so CI results are reproducible.

A row should only be marked PASS after testing the constructs the API actually uses. If a tool only reads a simple document without handling `nullable`, `oneOf`, or `QUERY`, record that limitation.

A snapshot of tool status as of 2026-11-20 shows support levels can vary:

| Tool | Published version/status | How to interpret |
|---|---|---|
| springdoc-openapi | Properties currently select only `OPENAPI_3_0` or `OPENAPI_3_1`; OAS 3.2 issue remains open | Do not use springdoc as the OAS 3.2 generation source until a release announces support |
| Swagger UI | Swagger UI 5.32.0 compatibility table lists OAS 3.2.0 | Standalone UI can render 3.2.0; verify the exact WebJar packaged by springdoc |
| Swagger Parser | 2.1.x line supports OAS 3.1 since 2.1.0; release 2.1.48 does not mean 3.2 support | Check the 3.2 issue and release notes before using it as an OAS 3.2 validator |
| OpenAPI Generator | README currently lists OAS 3.1 as beta; stable 7.27.0 does not yet list 3.2 | Do not assume the generator fully handles 3.2 operations or new keywords |

This reflects status observed from upstream docs and repositories at the time of writing, not a guarantee that every configuration or generator target yields identical results. Before every upgrade, re-check release notes and run your project's representative fixtures.

## 8. Swagger UI support can differ from springdoc

Swagger UI is the document display layer. It is not the sole parser, generator, and validator in the pipeline.

Swagger UI 5.32.0 compatibility docs list support for OpenAPI 2.0, 3.0.x, 3.1.x, and 3.2.0. This shows a standalone Swagger UI build can render certain 3.2 documents, but it does not prove springdoc generated 3.2 or that your project's parser/code generator understands the same document fully.

When using Swagger UI packaged with springdoc:

1. Check the actual `swagger-ui` WebJar version in the dependency tree.
2. Verify whether that version supports the OAS published by the API.
3. Open the UI with a document containing the features in use.
4. Check operations, parameters, schemas, security, and examples.
5. Inspect browser console and network tabs when rendering fails.
6. Do not test only a simple GET endpoint.

You can inspect Maven dependencies:

~~~bash
mvn dependency:tree -Dincludes=org.webjars:swagger-ui
~~~

The newest standalone Swagger UI version may differ from the version pulled in by springdoc. If Swagger UI needs upgrading, verify compatibility with springdoc and related dependencies instead of arbitrarily overriding the WebJar.

## 9. Parsers and validators must understand the exact OAS version

Parsers turn JSON/YAML into an OpenAPI object model. Validators check the document against specification rules. Some tools combine both tasks.

Swagger Parser supports OpenAPI 3.1 since the 2.1.0 line. However, 3.1 support does not automatically imply full support for all 3.2 features. OpenAPI 3.2 support has an open request in the `swagger-parser` repository; check the issue status and release notes before picking the tool.

A parser may:

- Reject the document because the version is unrecognized.
- Parse legacy structures while dropping new fields.
- Emit warnings instead of errors.
- Resolve some `$ref` entries without fully handling the JSON Schema dialect.
- Read JSON cleanly while handling YAML differently than expected.

Read both errors and warnings. Do not treat a parser returning an object as proof that the entire document is valid.

If the parser is used inside a Java application, pin the dependency version and write tests with sample documents representing your project's feature set. Do not test only the simplest OpenAPI file.

## 10. Code generators must be tested separately

A code generator can read a document yet still emit code inconsistent with the API's intent.

Possible issues include:

- `nullable` mapped as non-nullable.
- Optional and required misinterpreted.
- Enums or `oneOf` generating inaccurate models.
- `discriminator` failing to map subtypes properly.
- Request bodies or multipart payloads losing encoding.
- Security schemes failing to generate expected client configuration.
- New operation methods omitted.
- Wrong header, cookie, or parameter serialization.
- Streaming responses turned into a regular object.

The OpenAPI Generator README currently marks 3.1 support as beta and does not list 3.2 in its compatibility table. When using this generator, do not assume 3.2 is fully supported just because `validate` or `generate` finishes.

In particular, never use validation-skipping options to force the generator through a document with unsupported features. An unrecognized operation may be omitted from the generated code without creating the expected client method.

After generating a client, compile the generated project and run request/response tests. Successful code generation is only one step in compatibility testing.

## 11. Testing with OpenAPI Generator CLI

You can use the CLI to validate documents and generate a test client:

~~~bash
openapi-generator-cli version
openapi-generator-cli validate -i target/openapi.json
~~~

Generate a test client:

~~~bash
openapi-generator-cli generate \
  -i target/openapi.json \
  -g java \
  -o target/generated-client
~~~

Pin the CLI or Maven/Gradle plugin version. If developers run a newer CLI locally while CI runs an older plugin, results will diverge.

Do not use `--skip-validate-spec` to turn an incompatible document into a PASS. When testing a new feature, create a small fixture, run the pinned parser and generator, and inspect the output code.

A pipeline should archive:

- Generator version.
- Input OpenAPI artifact.
- Validation logs.
- Generated code.
- Compilation results.
- Client test results.

## 12. Testing JSON Schema and `nullable`

When migrating from OAS 3.0 to 3.1, create fixtures for key schemas.

Example nullable property in 3.0:

~~~yaml
type: string
nullable: true
~~~

Equivalent representation in 3.1:

~~~yaml
type:
  - string
  - "null"
~~~

Test at least:

- JSON payload with the field omitted.
- JSON payload with the field set to `null`.
- Required yet nullable field.
- Optional yet non-null field when present.
- Array containing nullable items.
- Nested object with nullable properties.
- `oneOf`/`anyOf` with `null` and `discriminator`.
- `min`/`max`, `pattern`, and `format` constraints.

Optional and nullable are two different concepts. Optional means the property may be absent; nullable means the property may appear with the value `null`. Generators must map both cases accurately to the target language.

Do not inspect only the JSON schema. Generate the client and verify actual data types, serializers, and deserializers.

## 13. Testing UI with representative feature fixtures

Do not rely solely on a huge production API document when investigating UI behavior. Create small OpenAPI fixtures for each key feature:

- Nullable schemas.
- `oneOf` and `discriminator`.
- External references.
- Security requirements.
- Multipart requests.
- Responses with multiple media types.
- Nested tags if using OAS 3.2.
- `QUERY` operations if using OAS 3.2.
- Streaming media types if using OAS 3.2.

Each fixture should have a clear expectation: how the UI must render the operation, schema, or security.

If Swagger UI renders a 3.2 document while a downstream parser fails, record each tool's outcome separately. Do not summarize it as “OAS 3.2 supported” because the system can still fail at code generation or contract testing.

## 14. Distinguishing document validation from runtime contract testing

These two testing groups answer different questions:

| Check | What it verifies |
|---|---|
| OpenAPI schema validation | Does the document follow OAS structure and rules? |
| Parser test | Does the tool read and resolve the document accurately? |
| Swagger UI test | Does the UI render the described features? |
| Code generation test | Do client/server stubs generate properly and compile? |
| Runtime API test | What status, headers, and body does the real app return? |
| Contract test | Do runtime requests/responses align with OpenAPI? |

`WebTestClient` and `MockMvc` test Spring Boot behavior. They do not automatically prove Swagger Parser or OpenAPI Generator understands every feature.

Conversely, an OpenAPI validator does not prove controllers return the right response body. Both document tests and runtime tests are needed.

## 15. Inspecting OpenAPI JSON generated by springdoc

Download the document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi.json
~~~

Check the version:

~~~bash
jq -r '.openapi' target/openapi.json
~~~

Check metadata and paths:

~~~bash
jq '{info: .info, paths: (.paths | keys)}' target/openapi.json
~~~

Check components:

~~~bash
jq '.components.schemas | keys' target/openapi.json
~~~

Check security schemes:

~~~bash
jq '.components.securitySchemes' target/openapi.json
~~~

Do not inspect only the `openapi` field. Verify that keywords and schemas are genuinely compatible with the declared version.

If springdoc is configured for OAS 3.1, tests should verify output is 3.1 and contains no constructs valid only in 3.2. If the pipeline requires OAS 3.2, use a spec-generation source with independently verified 3.2 support.

## 16. Example version and operation test with `WebTestClient`

You can test the document version returned by springdoc:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiCompatibilityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesExpectedOpenApiVersion() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.openapi").isEqualTo("3.1.0");
    }

    @Test
    void publishesExpectedOperation() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.paths['/api/orders'].get").exists()
            .jsonPath(
                "$.paths['/api/orders'].get.responses['200']"
            ).exists();
    }
}
~~~

This example assumes the app selected OAS 3.1 and `/api/orders` exists. If the project uses a different patch or version string per generator requirements, assert the exact version chosen by the project's contract.

Tests should verify important features rather than only the version string. A document declaring 3.1 can still contain invalid schemas or generator-incompatible components.

## 17. Testing the parser in Java

If the project uses Swagger Parser, write a test to parse the exported document:

~~~java
@Test
void parsesGeneratedOpenApiDocument() {
    SwaggerParseResult result =
        new OpenAPIV3Parser().readLocation(
            "target/openapi.json",
            null,
            new ParseOptions()
        );

    assertThat(result.getOpenAPI()).isNotNull();
    assertThat(result.getMessages()).isEmpty();
}
~~~

API names and constructors may vary across parser versions. Use the pinned dependency version and read warnings/messages from the parser.

The test above is meaningful only within the OAS range supported by that parser version. If the parser does not yet support 3.2, do not use this test as evidence of 3.2 compatibility. Use a parser/validator with verified support or keep the document at a version the toolchain understands.

If the parser returns an `OpenAPI` object accompanied by warnings, check whether warnings relate to features in use. Do not bulk-suppress warnings just to make the pipeline green.

## 18. Testing code generators with a real client

After generating the client:

1. Compile the generated source code.
2. Check nullable models, enums, and polymorphism.
3. Check operation methods and URLs.
4. Check serialization of query/path/header parameters.
5. Check auth interceptors and security schemes.
6. Send requests to a test server.
7. Deserialize real responses.
8. Check errors and response statuses.

A client can compile yet still serialize query parameters wrongly or drop headers. Therefore, compilation is not the final testing step.

For new OAS 3.2 features, create minimal fixtures to verify whether the generator retains operations, tags, servers, or media types. If the generator skips a feature, record the limitation and do not publish a client missing operations from its contract.

## 19. Structuring compatibility tests in CI

A pipeline can be broken into stages:

~~~text
Spring Boot test
      |
      v
Generate OpenAPI JSON/YAML
      |
      v
Check declared OAS version
      |
      v
Parser and schema validation
      |
      v
Swagger UI smoke test
      |
      v
Generate client SDK
      |
      v
Compile generated client
      |
      v
Runtime contract tests
      |
      v
Review OpenAPI diff
      |
      v
Publish approved artifact
~~~

Each step must use a pinned tool version. When a step fails, logs must show the tool and version executed.

Example CI commands:

~~~bash
mvn test

curl -fsS http://localhost:8080/v3/api-docs \
  -o target/openapi.json

jq -e '.openapi == "3.1.0"' target/openapi.json

openapi-generator-cli validate -i target/openapi.json

openapi-generator-cli generate \
  -i target/openapi.json \
  -g java \
  -o target/generated-client

mvn -f target/generated-client/pom.xml test
~~~

Commands should be adapted to how the pipeline starts the application, archives artifacts, and manages the generator. If a generator does not support the document version, the pipeline must fail explicitly instead of skipping validation.

## 20. Storing the compatibility matrix alongside build configuration

Store the compatibility matrix in technical documentation or project build metadata:

~~~yaml
openapiCompatibility:
  documentVersion: "3.1.0"
  springBoot: "4.1.x"
  springdoc: "3.2.x"
  swaggerUi: "pinned-version"
  parser: "pinned-version"
  generator: "pinned-version"
  contractTest: "pinned-version"
  verifiedFeatures:
    - nullable
    - oneOf
    - discriminator
    - security
    - multipart
~~~

This is an example internal documentation structure, not a default springdoc property. Replace placeholders with your project's actual versions and list only tested features.

Note that the compatibility matrix can differ across generators. For instance, Java clients and TypeScript clients may handle `nullable` or union types differently. If multiple client languages exist, create tests for each generator target.

## 21. Upgrading OpenAPI 3.0 to 3.1

Perform the upgrade step by step:

1. Lock compatible springdoc and Spring Boot versions.
2. Check current parsers, UI, generators, and contract testing tools.
3. Set `springdoc.api-docs.version` to `OPENAPI_3_1`.
4. Export the new document.
5. Compare `nullable`, `enum`, `oneOf`, `discriminator`, and `$ref` schemas.
6. Run validators and parsers.
7. Render using the exact packaged Swagger UI.
8. Generate clients for all supported languages.
9. Compile and run contract tests.
10. Review the diff and resolve breaking changes before publishing.

If a generator does not yet understand a 3.1 schema, you can keep the document at 3.0 during transition or upgrade the generator. Never silently turn `nullable` into `required` or drop keywords just to make an old tool pass.

## 22. Evaluating before upgrading to OpenAPI 3.2

Upgrading to 3.2 requires evaluating far more than changing a version string:

- Can springdoc generate 3.2 documents yet?
- Does the Swagger Core model represent all needed structures?
- Do parsers and validators understand 3.2?
- Does the Swagger UI bundled in the application support it?
- Do generators preserve `QUERY` operations and `additionalOperations`?
- Can client runtimes execute the new methods?
- Can contract testing tools parse the document?
- Do gateways, API portals, and internal docs accept the new version?

If any link lacks support, you can continue publishing 3.1 for the current pipeline and experiment with 3.2 using separate fixtures. There is no need to adopt 3.2 features just because the new specification is out.

A safe migration path is creating an experimental branch, keeping 3.1 artifacts as the current baseline, and evaluating each new 3.2 feature individually. Switch only after all critical consumers have been verified.

## 23. Common mistakes

| Symptom | Cause to check |
|---|---|
| Swagger UI opens, yet generator fails | UI and generator have different OAS support levels |
| Parser reads document with warnings | Certain keywords or references are not fully processed |
| springdoc still emits 3.1 when 3.2 is wanted | Property currently supports only 3.0 and 3.1 choices |
| Only edited `openapi` field to `3.2.1` | Version header does not turn 3.1 structures into 3.2 |
| Generator omits new operations | Generator/parser does not understand new methods or features |
| Nullable becomes non-nullable in client | 3.0/3.1 JSON Schema difference or generator mapping |
| Client compiles, yet requests fail | Wrong serialization, auth, or parameter mapping |
| CI passes, yet production UI fails | CI uses a different Swagger UI version than the packaged one |
| Local parse succeeds, yet CI fails | Mismatched dependency or plugin versions |
| `--skip-validate-spec` turns pipeline green | Unsupported features may be skipped or mis-generated |
| OAS 3.2 document does not render completely | UI bundle or parser does not yet support new features |
| Patch version treated as new features | Confusing patch releases with minor feature sets |

## 24. Compatibility checklist before release

- [ ] Explicitly recorded Spring Boot and springdoc versions.
- [ ] Selected OpenAPI version using a supported configuration property.
- [ ] Avoided manually editing the `openapi` field to fake a newer version.
- [ ] Verified Schema Object differences between 3.0 and 3.1.
- [ ] Verified the packaged Swagger UI version.
- [ ] Verified parsers and validators read the document cleanly.
- [ ] Ran the code generator with a pinned version.
- [ ] Compiled the generated client.
- [ ] Tested `nullable`, `oneOf`, `discriminator`, and security.
- [ ] Tested new features such as `QUERY` if using OAS 3.2.
- [ ] Verified runtime responses using `WebTestClient` or `MockMvc`.
- [ ] Ran contract tests against the final document.
- [ ] Avoided skipping validation to force tools through.
- [ ] Reviewed OpenAPI diffs and breaking changes.
- [ ] Stored the compatibility matrix alongside the build.
- [ ] CI and release environments use identical tool versions.

## 25. References

- [OpenAPI Specification – latest version](https://spec.openapis.org/oas/latest.html)
- [OpenAPI 3.2.1 – official specification](https://spec.openapis.org/oas/v3.2.1.html)
- [OpenAPI – upgrading from 3.1 to 3.2](https://learn.openapis.org/upgrading/v3.1-to-v3.2.html)
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Compatibility FAQ](https://springdoc.org/faq.html)
- [Swagger UI – Compatibility](https://github.com/swagger-api/swagger-ui)
- [Swagger Parser – OpenAPI 3.1 support](https://github.com/swagger-api/swagger-parser)
- [OpenAPI Generator – Compatibility](https://github.com/OpenAPITools/openapi-generator)
- [OpenAPI Generator – OAS 3.2 support issue](https://github.com/OpenAPITools/openapi-generator/issues/22728)
- [Swagger Parser – OAS 3.2 support issue](https://github.com/swagger-api/swagger-parser/issues/2248)
- [springdoc-openapi – OAS 3.2 support issue](https://github.com/springdoc/springdoc-openapi/issues/3324)

OpenAPI compatibility is a property of the entire toolchain. A document that renders in Swagger UI can still fail in parsers, code generators, or contract tests. Pin versions, maintain a feature matrix, inspect schemas and generated clients, and run runtime contract tests. For OpenAPI 3.2, adopt new features only after confirming springdoc, parsers, UI, generators, and real consumers all support them.
