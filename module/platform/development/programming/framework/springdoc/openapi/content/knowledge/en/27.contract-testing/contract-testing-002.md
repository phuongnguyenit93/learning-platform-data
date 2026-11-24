# Reading Specifications with a Version-Compatible Parser

An OpenAPI file can be JSON or YAML, yet merely parsing its syntax does not mean a tool understands the contract accurately. The parser must recognize the exact version declared in the `openapi` field, understand that version's constructs, and process `$ref`, schemas, and related components according to the specification rules.

With Springdoc, specifications are typically retrieved from `/v3/api-docs` or `/v3/api-docs.yaml`. You can use a parser in Java tests or pipelines to read the document into an object model, collect warnings/errors, and inspect required elements before running subsequent contract checks.

## 1. Identify the Version Before Choosing a Parser

The top-level `openapi` field in a document indicates the OpenAPI specification version:

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths: {}
```

Do not confuse this field with `info.version`. `openapi` identifies the version of the specification language; `info.version` is the API version assigned by the development team.

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Orders API",
    "version": "2026.11"
  }
}
```

In this example, the document uses OpenAPI 3.1.0 while the published API has version `2026.11`. The parser must support OpenAPI 3.1; never choose a parser based on the `info.version` string.

## 2. Choose a Parser by OpenAPI Version

Parsers differ in which specification versions they support. A library may read OpenAPI 3.0 cleanly yet lack full understanding of JSON Schema 2020-12 in OpenAPI 3.1, or lack support for newer OpenAPI 3.2 constructs.

At the time of writing, official Swagger Parser documentation lists the following key milestones:

| Parser | Documented Scope | Notes |
|---|---|---|
| Swagger Parser 1.x | Swagger/OpenAPI 2.0 on the 1.x branch | Legacy API line; the main repository directs 1.x users to the `v1` branch |
| Swagger Parser 2.1.x | OpenAPI 3.0 and 3.1 | OpenAPI 3.1 support began in 2.1.0; the same 2.x artifact line handles both versions |
| Swagger Parser 2.1.48 | 2.1.x release listed on README/Maven Central at check time | Usable as a dependency example; still check for newer patch releases before pinning |
| openapi-processor/openapi-parser | OpenAPI 3.0, 3.1, and 3.2 | Project publishes a parser and JSON Schema validator for all three versions; requires JDK 17+ |

Swagger Parser 2.1.x supports OpenAPI 3.1 starting from 2.1.0, including parsing, validation, and reference resolution. However, this line's documentation currently advertises support up to 3.1; do not assume parser 2.1.48 automatically supports every OpenAPI 3.2 feature. If a document declares 3.2, choose a parser that explicitly documents 3.2 support and verify the actual features the document uses.

`openapi-processor/openapi-parser` is a Java option documented by its project to support OpenAPI 3.2, 3.1, and 3.0. Project docs state that the parser uses JSON Schema Draft 4 to validate OpenAPI 3.0 schemas and JSON Schema Draft 2020-12 for OpenAPI 3.1/3.2. Evaluate this option separately for its Java API, dependencies, JDK requirements, and CI integration before adopting it.

These support milestones reflect parser project announcements, not a guarantee that every version of Swagger UI, Springdoc, client generator, or other validator supports the exact same feature set. Always inspect the release notes of the exact version pinned in your build.

## 3. Swagger Parser 2.x and OpenAPI 3.1

Swagger Parser 2.x uses the same artifact line to process OpenAPI 3.0 and 3.1. OpenAPI 3.1 support was added in version 2.1.0. OpenAPI 3.1 aligns the Schema Object with JSON Schema Draft 2020-12, so the parser must understand differences such as:

- A schema type may be an array containing `string` and `null`.
- JSON Schema 2020-12 keywords such as `$dynamicRef`, `$dynamicAnchor`, `unevaluatedProperties`, or `prefixItems` may appear.
- `jsonSchemaDialect` can define the document's schema dialect.
- OpenAPI 3.1 can use constructs absent from 3.0, such as `webhooks`.

A parser supporting only OpenAPI 3.0 may reject a 3.1 document or parse it partially without preserving schema semantics. Never rewrite `openapi: 3.1.0` to `3.0.3` just to bypass a parser error; doing so does not convert 3.1 keywords into valid 3.0 constructs.

One easy-to-miss API detail: the Swagger Parser README recommends `OpenAPIParser` to read documents and detect versions. `OpenAPIV3Parser` is a convenience API focused on OpenAPI 3.0 according to the README; do not pick that API for flows that must auto-detect or read OpenAPI 3.1. Follow the API and examples for your exact parser release.

## 4. Adding Swagger Parser to a Java Project

If you only need to read specifications in tests or a CI step, place the dependency in test scope so the parser is not bundled into the service runtime.

Maven:

```xml
<dependency>
    <groupId>io.swagger.parser.v3</groupId>
    <artifactId>swagger-parser</artifactId>
    <version>2.1.48</version>
    <scope>test</scope>
</dependency>
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    testImplementation("io.swagger.parser.v3:swagger-parser:2.1.48")
}
```

Version `2.1.48` is an example verified in Swagger Parser documentation at the time of writing. When upgrading, pin a specific release version and inspect the dependency tree. Springdoc also uses libraries from the Swagger ecosystem; if your application has multiple versions of `swagger-core`, `swagger-models`, or Jackson on the classpath, conflicts can trigger runtime errors or alter parsed models unexpectedly.

Inspect the dependency tree with Maven:

```bash
mvn dependency:tree -Dincludes=io.swagger.parser.v3,io.swagger.core.v3
```

Do not arbitrarily force all Swagger Core dependencies onto a newer version merely to match the parser. Check the compatibility matrix between Springdoc and Swagger Parser, then apply consistent dependency management. When the parser serves only contract tests, test scope or a dedicated CI module reduces impact on the running application.

## 5. Reading OpenAPI JSON/YAML from a File or URL

`OpenAPIParser` can read a document from a file path or URL and return a `SwaggerParseResult`. The result contains both the object model and validation messages.

```java
import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.parser.core.models.ParseOptions;
import io.swagger.v3.parser.core.models.SwaggerParseResult;
import io.swagger.v3.oas.models.OpenAPI;

public final class OpenApiReader {

    private OpenApiReader() {
    }

    public static OpenAPI read(String location) {
        ParseOptions options = new ParseOptions();
        options.setResolve(true);

        SwaggerParseResult result = new OpenAPIParser()
            .readLocation(location, null, options);

        if (result == null || result.getOpenAPI() == null) {
            String diagnostics = result == null || result.getMessages() == null
                ? "Parser returned no OpenAPI model or diagnostics."
                : String.join("\n", result.getMessages());
            throw new IllegalStateException("Failed to read OpenAPI document:\n" + diagnostics);
        }

        if (result.getMessages() != null && !result.getMessages().isEmpty()) {
            result.getMessages().forEach(message ->
                System.err.println("OpenAPI parser: " + message)
            );
        }

        return result.getOpenAPI();
    }
}
```

Calling with a YAML file:

```java
OpenAPI openAPI = OpenApiReader.read("src/test/resources/openapi.yaml");
```

Or with a running Springdoc endpoint:

```java
OpenAPI openAPI = OpenApiReader.read("http://localhost:8080/v3/api-docs");
```

The parser accepts JSON or YAML and uses the document's version field to pick the right logic. When reading from a URL, the test/CI process must be able to reach that host and port; if the endpoint requires authentication, supply credentials via the parser's API rather than making the endpoint public just for tests.

## 6. Inspecting `SwaggerParseResult` Instead of Taking Only the Model

Do not simply call `getOpenAPI()` and assume a successful parse means the document is valid. Check both parts:

- `getOpenAPI()` must return a model so subsequent steps can inspect it.
- `getMessages()` holds warnings or errors detected by the parser during parsing/validation.

Manual check example:

```java
SwaggerParseResult result = new OpenAPIParser()
    .readLocation("src/test/resources/openapi.yaml", null, null);

if (result == null) {
    throw new IllegalStateException("No result returned from parser");
}

if (result.getMessages() != null) {
    result.getMessages().forEach(System.err::println);
}

if (result.getOpenAPI() == null) {
    throw new IllegalStateException("Failed to create OpenAPI model");
}

String version = result.getOpenAPI().getOpenapi();
System.out.println("OpenAPI version: " + version);
```

`getMessages()` can contain both warnings and errors as message strings. A non-null model does not prove every rule passed. Conversely, not every warning carries the same severity. CI should define a clear policy: record all messages, fail when parsing produces no model, and fail or require review when diagnostics appear at project-defined severity levels.

If you need machine-readable severity classification, avoid guessing by searching for words like `warning` or `error` inside message strings. Use a validator with structured result types or a wrapper rule set tested against your exact parser version.

## 7. Reading Springdoc-Generated Specifications in Integration Tests

A practical approach is to boot Spring Boot on a random port, call the API Docs endpoint, and pass the URL to the parser. Example with Spring Boot 3 and JUnit 5:

```java
import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.parser.core.models.SwaggerParseResult;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OpenApiDocumentParsingTest {

    @Value("${local.server.port}")
    int port;

    @Test
    void generatedOpenApiDocumentCanBeRead() {
        String location = "http://localhost:" + port + "/v3/api-docs";

        SwaggerParseResult result = new OpenAPIParser()
            .readLocation(location, null, null);

        assertNotNull(result, "Parser must return a result");
        assertNotNull(
            result.getOpenAPI(),
            () -> result.getMessages() == null
                ? "Failed to create OpenAPI model"
                : String.join("\n", result.getMessages())
        );

        assertEquals("3.1.0", result.getOpenAPI().getOpenapi());
        assertTrue(
            result.getMessages() == null || result.getMessages().isEmpty(),
            () -> String.join("\n", result.getMessages())
        );
    }
}
```

Asserting `3.1.0` only fits when the application is configured to output OpenAPI 3.1. If the application outputs 3.0.x, replace the expected version with your project's chosen value. Asserting zero diagnostics is a strict policy for this example; if the parser emits warnings that have been evaluated and accepted, separate warnings from errors via your project's review process instead of ignoring all messages.

If the documentation endpoint is protected, pass credentials via `AuthorizationValue` and never log the token. If your test uses MockMvc/WebTestClient and already holds the JSON body in memory, use the content-reading API for your parser version or write a temporary test artifact; do not expose a new public endpoint solely so the parser can read the document.

## 8. Distinguishing Parse, Validate, and Resolve `$ref`

These steps are related but not synonymous:

| Task | Purpose | What to Observe |
|---|---|---|
| Parse | Read JSON/YAML and build the object model | Produces an `OpenAPI` model or diagnostics explaining failures |
| Validate | Check OpenAPI/JSON Schema structure and rules supported by the parser | Diagnostics; do not rely solely on a model being created |
| Resolve | Fetch external/relative references and replace them with local component references | `$ref` entries point to components in the resolved model |
| Resolve fully | Replace even local references with the referenced content | More inline models; content may be duplicated |
| Flatten | Move certain inline schemas into components and replace with `$ref` | Component schemas are added and operations reference them |

A successful parse does not prove external `$ref` targets can be fetched. If your contract uses external references, enable resolve in tests to verify those resources are reachable and readable.

## 9. Configuring resolve and resolveFully

Swagger Parser provides `ParseOptions` to control reference handling. Example enabling resolve:

```java
import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.parser.core.models.ParseOptions;
import io.swagger.v3.parser.core.models.SwaggerParseResult;

ParseOptions options = new ParseOptions();
options.setResolve(true);

SwaggerParseResult result = new OpenAPIParser()
    .readLocation("src/test/resources/openapi.yaml", null, options);
```

When resolving external or relative references, the parser can load referenced resources, add resolved entries into `components`, and replace external URLs with local `$ref` pointers. This is useful for catching missing files, broken URIs, or unreachable resources.

`resolveFully` has a stronger effect:

```java
ParseOptions options = new ParseOptions();
options.setResolve(true);
options.setResolveFully(true);

SwaggerParseResult result = new OpenAPIParser()
    .readLocation("src/test/resources/openapi.yaml", null, options);
```

The parser replaces local references with the content of the referenced elements. The resulting model can grow significantly larger as schemas or responses are repeated. Enable this only when a downstream tool requires a dereferenced document; do not enable it merely to "parse more thoroughly."

With OpenAPI 3.1, Swagger Parser uses separate dereferencing logic compared to 3.0. Resolving external and internal references can produce different object models between the two versions. Always inspect the input document and test resolution behavior on your pinned parser version, especially when a pipeline compares or re-serializes documents.

## 10. Flatten and Composed Schemas

`flatten` is helpful when downstream tools need inline schemas moved into `components.schemas`:

```java
ParseOptions options = new ParseOptions();
options.setFlatten(true);

SwaggerParseResult result = new OpenAPIParser()
    .readLocation("src/test/resources/openapi.yaml", null, options);
```

Flattening can generate additional schema components and new `$ref` entries. This is an object model transformation, not a prerequisite for reading a specification.

For `allOf`, `oneOf`, and `anyOf`, `resolveFully` offers the `resolveCombinators` option. When enabled, the parser may merge certain composed schemas into schemas that no longer preserve composition structure in the resolved output. When disabled, `allOf`/`oneOf`/`anyOf` members are preserved in the model.

```java
ParseOptions options = new ParseOptions();
options.setResolve(true);
options.setResolveFully(true);
options.setResolveCombinators(false);
```

If a contract test needs to verify the exact `allOf` or `oneOf` structure advertised by the API, do not use a resolve configuration that strips that structure. Parse the original document or keep `resolveCombinators=false`, depending on the test objective.

## 11. Reading Documents Requiring Authentication or External References

If the OpenAPI document is served behind authentication, Swagger Parser supports passing authorization details when reading a URL.

```java
import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.parser.core.models.AuthorizationValue;
import io.swagger.v3.parser.core.models.SwaggerParseResult;
import java.util.List;

AuthorizationValue auth = new AuthorizationValue(
    "Authorization",
    "Bearer " + System.getenv("OPENAPI_READ_TOKEN"),
    "header"
);

SwaggerParseResult result = new OpenAPIParser().readLocation(
    "https://api.example.com/v3/api-docs",
    List.of(auth),
    null
);
```

Tokens should come from a CI secret store or protected environment variables. Never commit tokens, print header values to logs, or place credentials in URL query strings unless required by a specific protocol.

External `$ref` values can cause the parser to issue network requests to other hosts. Only resolve documents from trusted sources; restrict allowed domains and never let the parser freely fetch URLs supplied by untrusted users. This reduces the risk of SSRF or information leakage via unintended requests.

Do not disable TLS verification to make the parser accept invalid certificates. For internal CAs, install the CA into the truststore or configure proper SSL trust for the CI process. Swagger Parser's `TRUST_ALL` flag bypasses invalid certificates and should not be used in regular pipelines.

## 12. Swagger 2.0 and OpenAPI 3.x

Swagger 2.0 uses the `swagger: "2.0"` field rather than `openapi`. `OpenAPIParser` can read Swagger 2.0 and convert the document into an equivalent OpenAPI 3.0 model before returning it.

This is convenient when handling multiple inputs in one pipeline, but remember the resulting model is no longer a verbatim Swagger 2.0 representation. If your task requires preserving the 2.0 model or using the legacy Swagger Parser 1.x API, use the branch/library built for Swagger 2.0 rather than assuming the 2.x parser keeps the source document unchanged.

When a pipeline accepts both 2.0 and 3.x, record the source version, the converted target version, and any converter-introduced changes. Never compare two documents of different versions directly as though they share the same structure.

## 13. Parsing Does Not Replace Runtime Contract Tests

A parser checks the document and object model against the rules supported by that parser version. It cannot prove that controllers actually return the described responses.

Verification layers should be kept distinct:

| Layer | Question to Answer | Example |
|---|---|---|
| Read document | Can JSON/YAML be read? | Parser builds an OpenAPI model |
| Valid spec | Does the document follow the declared OpenAPI/JSON Schema version? | Parser diagnostics or corresponding validator |
| References | Do `$ref` links resolve? | Enable resolve and check external resources |
| Project rules | Are `operationId`s unique? Is security documented? | Linter or custom rules |
| Runtime contract | Does the API return status/headers/body matching the document? | Send test requests and validate responses |
| Compatibility | Do document changes break existing clients? | Compare spec with baseline and run breaking-change checks |

A document that parses cleanly can still describe the wrong status codes, headers, response bodies, or security for the application. To verify runtime behavior, use request tests with an appropriate request/response validator or provider/consumer contract testing.

## 14. Integrating a Parser into the CI Pipeline

A practical pipeline can run in this order:

1. Start the application with test configuration or generate the OpenAPI artifact at build time.
2. Fetch `/v3/api-docs` or the exported JSON/YAML file.
3. Read the `openapi` field and confirm the version is allowed in the repository.
4. Use a parser supporting that version to parse and collect diagnostics.
5. Resolve `$ref` if the contract uses external/relative references.
6. Run a validator or linter according to project rules.
7. Compare against the baseline to detect breaking changes.
8. Run request/response contract tests against the application.

Shell example downloading the document from Springdoc:

```bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi.json
```

Parser tests can read `target/openapi.json` via `readLocation`. If using a live URL directly, ensure the service is ready before invoking the parser and do not let the test step run before the application binds its port.

Pin the parser version in Maven/Gradle and upgrade intentionally. When upgrading the parser, re-run a fixture suite representing critical document structures: internal/external `$ref`, `allOf`, `oneOf`, nullable schemas, security schemes, callbacks/webhooks, and the JSON Schema keywords your API uses.

## 15. Fixture Matrix for Testing Parser Compatibility

A test that only parses a simple Petstore spec may miss missing parser support for features your project actually uses. Maintain a small fixture suite grouped by version and feature:

| Fixture | Required Content | What to Verify |
|---|---|---|
| OAS 3.0 | `nullable`, `components`, request/response refs | 3.0 parser reads and preserves expected model |
| OAS 3.1 | JSON Schema type union with `null`, `webhooks`, or 2020-12 schemas | Parser understands version 3.1 without dropping key keywords |
| OAS 3.2 | A new feature actually used by the project | Run only with a parser documented to support 3.2 |
| External references | Relative files and external URLs | Resolves in a CI environment with appropriate access |
| Recursive schema | `$ref` pointing back to parent component | Not misreported as a missing reference |
| Composition | `allOf`, `oneOf`, `anyOf`, and discriminator | Model preserves structure when tests inspect composition |
| Protected document | Endpoint requiring a token | Parser sends proper authorization and leaks no secrets |

After parsing, serialize the model back to JSON/YAML and compare semantics or inspect key fields. Byte-for-byte comparison is unnecessary because parsers/serializers may reorder keys, normalize quoting, or reformat without changing semantics.

## 16. Common Pitfalls When Reading Specifications

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Parser reports unsupported version | Parser is older than the document's `openapi` version | Upgrade parser or pick one that supports that version |
| OAS 3.1 fails to parse with 3.0 parser | Using a parser/API that only supports OpenAPI 3.0 | Use Swagger Parser 2.1.0+ and the proper `OpenAPIParser` API |
| OAS 3.2 is not recognized | Current parser has not documented 3.2 support | Choose a 3.2-aware parser such as openapi-processor parser and test required features |
| `getOpenAPI()` returns null | Syntax error, version error, or source read failure | Print `getMessages()`, verify URL/file and JSON/YAML format |
| Model created yet parser reports messages | Document contains warnings or validation issues | Evaluate diagnostics per CI policy; do not ignore all messages |
| External `$ref` fails to resolve | Missing file/URL, DNS, TLS, auth, or wrong base URI | Check resources and credentials; enable resolve in tests |
| Local `$ref` disappears from output | `resolveFully` is enabled | Use normal `resolve` or disable resolveFully if refs must stay |
| `allOf` schemas get merged | `resolveFully` with `resolveCombinators` is enabled | Preserve composition with `resolveCombinators=false` or parse the raw document |
| Swagger 2.0 outputs as OpenAPI 3.0 | 2.x parser auto-converts 2.0 inputs | Note the conversion; use the 1.x parser branch if a 2.0 model is required |
| Parser test hits class conflicts | Multiple Swagger Core/Models versions on classpath | Inspect dependency tree and align dependency management |
| Document URL returns 401/403 | CI did not send credentials | Configure AuthorizationValue or download an authenticated artifact |
| Parser fetches unintended external URLs | External `$ref` points to an untrusted host | Restrict document sources and allowed resolution hosts |

## 17. Checklist for Selecting and Operating a Parser

- [ ] Read the root `openapi` field, without confusing it with `info.version`.
- [ ] Selected parser explicitly documents support for the target OpenAPI version.
- [ ] When using OpenAPI 3.1, parser supports JSON Schema 2020-12 and corresponding reference behavior.
- [ ] When using OpenAPI 3.2, parser is confirmed by docs to support 3.2.
- [ ] Pinned parser version in Maven/Gradle and inspected the dependency tree.
- [ ] Used `OpenAPIParser` appropriately for version auto-detection; avoided 3.0-only convenience APIs for 3.1 documents.
- [ ] Checked both `SwaggerParseResult.getOpenAPI()` and `getMessages()`.
- [ ] CI has a clear policy for warnings and errors.
- [ ] Enabled resolve when external/relative `$ref` verification is needed.
- [ ] Enabled `resolveFully` or `flatten` only when downstream steps require model transformation.
- [ ] Tested `allOf`/`oneOf` and recursive schemas used by the API.
- [ ] Restricted external references to trusted sources and kept TLS verification enabled.
- [ ] Runtime contract tests verify actual requests/responses beyond document parsing.
- [ ] Maintained fixtures covering the OpenAPI versions and features the project uses.

Reading specifications properly starts with identifying the `openapi` version and selecting a parser that supports it. Swagger Parser 2.1.x supports OpenAPI 3.0/3.1, whereas 3.2 documents require a parser documenting 3.2 support. After reading, inspect both the model and diagnostics; resolve references only when test goals require it, since `resolveFully` can alter structure and bloat the document. Finally, separate syntax/spec checks from runtime contract tests to know whether the live API actually conforms to its documentation.

## References

- [Swagger Parser – README and API Usage](https://github.com/swagger-api/swagger-parser)
- [Swagger Parser – OpenAPI 3.1 support](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---OpenAPI-3.1)
- [Swagger Parser – Issue tracking OpenAPI 3.2 support](https://github.com/swagger-api/swagger-parser/issues/2248)
- [openapi-processor/openapi-parser – OpenAPI 3.2, 3.1 and 3.0 parser](https://github.com/openapi-processor/openapi-parser)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Springdoc OpenAPI – Official documentation](https://springdoc.org/)
