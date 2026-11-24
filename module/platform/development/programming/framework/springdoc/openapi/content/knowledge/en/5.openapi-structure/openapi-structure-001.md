# The openapi Field and Specification Format Version

Every OpenAPI Description starts with a root-level OpenAPI Object. The **openapi** field in this object indicates which version of the **OpenAPI Specification (OAS)** the document conforms to. Tools reading the document rely on this value to understand the allowed syntax, object structure, and schema rules.

Example:

~~~yaml
openapi: "3.1.0"
info:
  title: Catalog API
  version: "2026.11"
paths:
  /products:
    get:
      operationId: listProducts
      summary: List products
      responses:
        "200":
          description: Product list
~~~

In the example, `openapi` is the OpenAPI format version; `info.version` is the version of the OpenAPI document according to the Info Object metadata. These two values have no mandatory relationship requiring them to be identical.

This is a distinction to establish right from the start when working with springdoc: the version of the springdoc library, the version of the OpenAPI Specification, and the version of the API/document are different pieces of information.

## 1. What is the openapi field?

`openapi` is a required field in the root-level OpenAPI Object. Its data type is string, and its value must be the OpenAPI Specification version number that the document uses.

Examples:

~~~yaml
openapi: "3.0.4"
~~~

~~~yaml
openapi: "3.1.0"
~~~

~~~yaml
openapi: "3.2.1"
~~~

The values above represent different feature sets of OAS. When a parser reads this field, it can select the right set of rules to interpret paths, components, schemas, security, webhooks, and other objects.

Several important characteristics:

- The field must be at the root level, alongside `info`, `servers`, `paths`, and `components`.
- The field name is case-sensitive; writing `OpenAPI` or `openApi` cannot substitute for `openapi`.
- The value is a version string, not a library name or documentation URL.
- The value must accurately reflect the syntax and features that the document actually uses.
- Do not invent an arbitrary version such as `latest`, `v3`, or `3.1`.

The OpenAPI Specification defines this field as required and recommends that tooling use it to interpret the document. Without `openapi`, a parser cannot determine with certainty which OAS version the document declares.

## 2. Distinguishing Four Types of Versions

In a Spring Boot project, several similar-looking version strings can appear. They have different meanings:

| Information | Example | Meaning |
|---|---|---|
| springdoc library version | 2.10.0 | Java dependency version used to generate OpenAPI |
| OpenAPI Specification version | 3.1.0 | Feature set and format rules of the document |
| info.version | 2026.11 | Version of the OpenAPI document described in the Info Object |
| API release version | v1, v2, or 2026-11 | API versioning convention published by the organization for consumers |

Do not infer that:

- springdoc 3.x necessarily generates `openapi` 3.0.0 or 3.2.0.
- An `/v2/products` API necessarily has `openapi` 2.0.
- `info.version` 3.1.0 means the document uses OAS 3.1.0.
- Upgrading the springdoc version automatically upgrades the OpenAPI Specification version.

For example, an application can use springdoc 2.10.0, generate a document conforming to OAS 3.1.0, and describe OpenAPI document version 2026.11, while the public API is still managed under release v1.

### Role of info.version

`info.version` is a metadata string in the Info Object. According to OAS 3.2.1, it describes the version of the OpenAPI document and differs from:

- The OpenAPI Specification version recorded in `openapi`.
- The version of the API being described.
- The version of the entire OpenAPI Description if the description is split across multiple documents.

In many projects, `info.version` is used by internal convention as the version of the API or documentation release. That should be agreed upon with consumers and pipelines. If the project needs to represent an API release separately, use metadata or an extension with a clear convention instead of mistakenly writing it into the `openapi` field.

Example:

~~~yaml
openapi: "3.1.0"
info:
  title: Catalog API
  version: "2026.11.20"
x-api-release: "v1"
~~~

Here, `x-api-release` is an organization-defined specification extension; tooling should not assume this extension has standard semantics unless configured.

## 3. OpenAPI Specification Version by Major, Minor, and Patch

OAS uses a versioning format of the form:

~~~text
major.minor.patch
~~~

For example, `3.2.1` has:

- Major: 3.
- Minor: 2.
- Patch: 1.

According to OAS versioning rules:

- The `major.minor` part determines the feature set.
- Patch releases fix bugs, clarify content, or update wording; they do not intentionally add a new feature set.
- Tooling supporting OAS 3.2 should be compatible with patch releases in `3.2.x`.
- Tooling should not treat `3.2.0` and `3.2.1` as two different feature sets just because the patch number changes.

This does not mean every older parser automatically understands a newer version. A tool claiming support for 3.1 may reject or incompletely process a 3.2 document, even though patch differences within the same minor usually do not change the feature set.

### Released Versions

As of November 20, 2026, the official specification page lists:

| Branch | Some Versions |
|---|---|
| OpenAPI 3.2 | 3.2.1, 3.2.0 |
| OpenAPI 3.1 | 3.1.2, 3.1.1, 3.1.0 |
| OpenAPI 3.0 | 3.0.4, 3.0.3, 3.0.2, 3.0.1, 3.0.0 |
| Swagger/OpenAPI 2.0 | 2.0 |

OAS 3.2.1 was released on September 10, 2026. It is a patch release of the 3.2 branch, whereas 3.2.0 was the preceding minor feature release.

## 4. Distinguishing Swagger 2.0 from OpenAPI 3.x

Before OpenAPI 3.0, the format was commonly called Swagger Specification 2.0. A Swagger 2.0 document uses the root field:

~~~yaml
swagger: "2.0"
info:
  title: Catalog API
  version: "v1"
paths: {}
~~~

OpenAPI 3.x uses the `openapi` field:

~~~yaml
openapi: "3.0.4"
info:
  title: Catalog API
  version: "v1"
paths: {}
~~~

Do not put both fields into the same document to support both. They belong to two different format versions. When migrating from Swagger 2.0 to OpenAPI 3.x, corresponding structures must be converted, such as:

- `definitions` to `components.schemas`.
- `securityDefinitions` to `components.securitySchemes`.
- `host`, `basePath`, `schemes` to `servers`.
- Body parameter structures to `requestBody`.
- Response and media type structures to the new representation.

Merely changing `swagger: "2.0"` to `openapi: "3.0.0"` is not a valid migration because the remaining objects may still follow the Swagger 2.0 structure.

## 5. Key Format Differences Between OAS 3.0, 3.1, and 3.2

The `openapi` field is not just a display label. It declares that the document uses the corresponding rule set. When changing versions, you must check whether the schemas, fields, and structures in use are appropriate.

### OAS 3.0

OAS 3.0 has a Schema Object based on its own subset of JSON Schema. Some keywords and representations differ from modern JSON Schema.

Nullable example:

~~~yaml
type: string
nullable: true
~~~

### OAS 3.1

OAS 3.1 aligns the Schema Object with JSON Schema Draft 2020-12 and supports JSON Schema vocabularies. Nullability representation shifts to JSON Schema semantics:

~~~yaml
type:
  - string
  - "null"
~~~

In OAS 3.1, `nullable` is no longer the standard OAS 3.0 approach. If you only change the `openapi` field from 3.0 to 3.1 while keeping legacy schemas, you must verify how tooling interprets them.

### OAS 3.2

OAS 3.2 continues to extend and clarify the specification. Tooling must properly support the 3.2 branch to understand the new fields and semantics. Do not use version 3.2 just because it is the newest release if your system's validator, gateway, SDK generator, or API portal does not yet support it.

Principle: the version recorded in `openapi` must match the actual feature set. Do not pick a higher version just to have a newer number, and do not pick a lower version if the document uses features only available in a newer branch.

## 6. JSON/YAML File Format Does Not Determine OpenAPI Version

An OpenAPI document is a JSON object; it can be represented in JSON or YAML. File format and specification version are two independent axes.

The following two files can describe the exact same document:

~~~yaml
openapi: "3.1.0"
info:
  title: Catalog API
  version: "v1"
paths: {}
~~~

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Catalog API",
    "version": "v1"
  },
  "paths": {}
}
~~~

Changing the `.yaml` extension to `.json` does not change the OpenAPI version. Conversely, converting from YAML to JSON does not alter semantics as long as serialization preserves the data.

Field names in OpenAPI are case-sensitive. YAML 1.2 is recommended to maintain round-trip JSON/YAML compatibility; avoid relying on YAML values that cannot be equivalently represented in JSON.

## 7. Minimum Structure of a Document

A typical API document contains these components:

~~~yaml
openapi: "3.1.0"
info:
  title: Catalog API
  summary: Product catalog management API
  description: Provides product lookup and management operations.
  version: "2026.11"
servers:
  - url: https://api.example.com
paths:
  /products:
    get:
      operationId: listProducts
      summary: List products
      responses:
        "200":
          description: Returns product list
components:
  schemas: {}
~~~

Roles:

| Field | Role |
|---|---|
| openapi | OpenAPI Specification version |
| info | Document/API metadata |
| servers | Base URLs that consumers can call |
| paths | HTTP paths and operations |
| components | Reusable schemas, responses, parameters, security schemes, and objects |

In newer OAS versions, the OpenAPI Object may have additional structures such as `webhooks` and other fields. The example above is only a small document to illustrate the placement of `openapi`, not an exhaustive list of every field in OAS 3.2.1.

## 8. How Does springdoc Choose the Generated OpenAPI Version?

springdoc is a Spring Boot integration library for generating OpenAPI documents. The springdoc dependency version does not automatically become the value of the `openapi` field.

According to current configuration documentation, the property:

~~~yaml
springdoc:
  api-docs:
    version: openapi_3_1
~~~

`springdoc.api-docs.version` lets you choose between OpenAPI 3.0 and OpenAPI 3.1. The currently documented default value is `openapi_3_1`.

If you need OAS 3.0:

~~~yaml
springdoc:
  api-docs:
    version: openapi_3_0
~~~

In `application.properties`:

~~~properties
springdoc.api-docs.version=OPENAPI_3_1
~~~

Or:

~~~properties
springdoc.api-docs.version=OPENAPI_3_0
~~~

Verify the supported property and values in the exact springdoc branch you are using. Current documentation lists options 3.0 and 3.1; it has not announced an `OPENAPI_3_2` option. Therefore, you cannot assume that adding `springdoc.api-docs.version=openapi_3_2` will make springdoc generate OAS 3.2.1.

If a project is required to publish OAS 3.2, check whether a newer springdoc release supports it. If not, a controlled document conversion step or another specification generator may be needed; do not edit only the `openapi` field of a 3.1 document to 3.2.1 when the content does not yet conform to OAS 3.2.

## 9. Checking the openapi Value from the springdoc Endpoint

After the application starts, the default endpoints are typically:

~~~text
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

Download the JSON and inspect the fields:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs \
  -o build/openapi.json

jq -r '.openapi, .info.version, .info.title' build/openapi.json
~~~

Example output:

~~~text
3.1.0
2026.11
Catalog API
~~~

The three lines are three different pieces of metadata. The first line is the OAS version; the second line is the document version per the Info Object; the third line is the API title.

Checking with PowerShell:

~~~powershell
$document = Get-Content -Raw -Encoding UTF8 "build/openapi.json" |
    ConvertFrom-Json

$document.openapi
$document.info.version
$document.info.title
~~~

If the endpoint returns YAML, use an appropriate YAML parser to read the fields; do not use simple regexes if the document has comments, anchors, or complex structures.

## 10. Checking Format Version and Structure with a Validator

A validator must support the OAS version declared by the document. For example, do not use a validator that only supports OpenAPI 3.0 to conclude that a 3.2.1 document is invalid.

A verification workflow:

1. Parse JSON/YAML to confirm syntax.
2. Read `openapi` and determine the OAS version.
3. Choose a validator that supports the right major/minor version.
4. Validate structures and objects against the specification.
5. Run a linter according to internal conventions.
6. Re-verify using the Swagger UI, gateway, or code generator actually used by consumers.

Example using Redocly CLI with a tool version pinned in the project:

~~~bash
redocly lint build/openapi.json
~~~

Example using Swagger CLI:

~~~bash
swagger-cli validate build/openapi.json
~~~

Check the documentation of the installed CLI version for its level of OAS 3.1/3.2 support. Not every tool keeps pace with new OAS releases immediately upon publication.

The JSON Schema on `spec.openapis.org` is a helpful validation aid, but the normative text of the specification itself remains the authoritative source if the schema and specification prose disagree.

## 11. Impact on Swagger UI and Code Generators

The `openapi` value helps Swagger UI, API portals, gateways, and code generators select the corresponding parser. If a document declares a version newer than what consumers support, the following may occur:

- Swagger UI reports that it cannot render the definition.
- Some schemas or keywords are ignored.
- A validator rejects the document even though the YAML/JSON parses cleanly.
- A code generator produces missing models or incorrect types.
- A gateway imports the file but skips part of a policy.
- Contract tests interpret requests/responses differently from the server.

Conversely, if a document uses newer features while declaring an older OAS version, consumers may misread or fail to recognize those features.

Before changing `openapi`, check all key consumers:

| Consumer | What to Check |
|---|---|
| Swagger UI | Does the UI version render the OAS version and Schema Object needed? |
| OpenAPI validator | Does it support the right major/minor version? |
| SDK generator | Does it properly generate nullable, union, enum, and references? |
| API gateway | Can it import security, servers, and operations? |
| Contract test | Do the parser and matcher understand the new schemas? |
| API portal | Does it display descriptions, examples, and references accurately? |

Do not change the version in the document before testing against the set of consumers supported by the organization.

## 12. Choosing OAS 3.0 or 3.1 in springdoc

If springdoc currently only provides the two options 3.0 and 3.1, the choice should be based on schema needs and consumer compatibility.

| Criterion | OAS 3.0 | OAS 3.1 |
|---|---|---|
| JSON Schema | OAS 3.0's own subset | Aligned with JSON Schema Draft 2020-12 |
| Nullability | Has `nullable: true` | Uses JSON Schema type/union with `null` |
| Legacy tooling | Often has long-standing coverage | Requires verifying parsers/generators |
| Complex schema expression | Limited in some cases | More flexible thanks to JSON Schema |
| springdoc property | `openapi_3_0` | `openapi_3_1` |

Choose 3.1 when you need JSON Schema semantics and consumers already support it. Choose 3.0 when the organization's gateway, generator, or portal ecosystem still requires 3.0. Do not stay on 3.0 solely because one old tool has not been updated without documenting that limitation.

## 13. Controlled OAS Version Upgrade Process

When upgrading a document from 3.0 to 3.1 or to 3.2:

1. Identify which new features need to be used.
2. Check whether springdoc supports generating the target version.
3. Check Swagger UI, validators, gateways, SDK generators, and portals.
4. Read the migration notes between the two OAS minor/major versions.
5. Convert old schemas and keywords to the new semantics.
6. Generate the document from the application.
7. Verify that the `openapi` field has the expected version.
8. Validate with a tool that supports the target version.
9. Compare semantic diffs and run contract tests.
10. Publish the document and notify consumers if changes affect SDKs/tooling.

Do not perform a migration by search-and-replacing the string `3.0.0` with `3.1.0` or `3.2.1` in a file. The version field only declares semantics; it does not automatically transform schemas or objects.

## 14. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| Using `openapi: "2.0"` | OAS 2.0 uses the field `swagger: "2.0"` | Migrate the structure to OpenAPI 3.x |
| Setting `openapi: "v1"` | This is not a valid OAS version | Use an OAS version such as `3.1.0` |
| Setting `openapi: "3.1"` | Missing the patch component of a standard version string | Use the full version such as `3.1.0` |
| Setting `openapi: "3.2.1"` while using semantically invalid 3.0/3.1 syntax | The version field does not convert the document | Validate and convert objects/schemas per OAS 3.2 |
| Using `info.version` instead of `openapi` | The two fields have different meanings | Keep `openapi` at root and `info.version` in Info Object |
| Assuming springdoc 3.x must generate OAS 3.2 | Library version and OAS version are independent | Check `springdoc.api-docs.version` |
| Renaming `.yaml` extension to `.json` | Does not convert file syntax | Re-serialize using a JSON parser |
| Using an OAS 3.0-only validator for a 3.1/3.2 document | Validator does not understand the target version | Use a tool version with corresponding support |
| Upgrading OAS without checking Swagger UI | The UI may not support new schemas/keywords yet | Test on the exact consumer UI version |
| Changing the version field to silence warnings | May mask real errors or misdeclare semantics | Fix the document per the specification |

## 15. openapi Field Review Checklist

- [ ] The `openapi` field is present on the root object.
- [ ] The field name is written in exact lowercase `openapi`.
- [ ] The value is a full version string.
- [ ] The version reflects the actual feature set used by the document.
- [ ] `swagger: "2.0"` is not mixed with OpenAPI 3.x.
- [ ] The springdoc version is not confused with the OAS version.
- [ ] `info.version` is not confused with the OAS version.
- [ ] Consumers have been verified to support the declared OAS version.
- [ ] The validator is pinned and supports the exact version.
- [ ] Schemas use the proper semantics of OAS 3.0/3.1/3.2.
- [ ] Semantic diff and contract tests were run when upgrading versions.
- [ ] The springdoc property was verified in the exact release in use.

## 16. Official References

- [OpenAPI Specification – Version Index](https://spec.openapis.org/oas/): list of versions 3.0, 3.1, 3.2, and schema iterations.
- [OpenAPI Specification 3.2.1](https://spec.openapis.org/oas/v3.2.1.html): meaning of the `openapi` field, `info.version`, major/minor/patch rules, and OpenAPI Object structure.
- [OpenAPI Specification 3.1.0](https://spec.openapis.org/oas/v3.1.0.html): Schema Object and JSON Schema alignment in OAS 3.1.
- [OpenAPI Specification 3.0.4](https://spec.openapis.org/oas/v3.0.4.html): structure and semantics of OAS 3.0.
- [springdoc-openapi Core Properties](https://springdoc.org/core-properties.html): `springdoc.api-docs.version`, default value, and OAS 3.0/3.1 options.
- [springdoc-openapi v2 Properties](https://springdoc.org/v2/core-properties.html): version configuration for the Boot 3 branch.

## Conclusion

The `openapi` field declares the OpenAPI Specification version that the document conforms to. It differs from the springdoc library version and from `info.version`. OAS uses major/minor to define the feature set, while patch mainly fixes bugs and clarifies the specification. As of November 20, 2026, OAS 3.2.1 is the latest release, whereas springdoc currently documents options for generating OAS 3.0 or 3.1. When choosing or upgrading a version, check support across springdoc and all consumers, convert schemas to the right semantics, validate the document, and run contract tests; do not merely change the version string at the root.
