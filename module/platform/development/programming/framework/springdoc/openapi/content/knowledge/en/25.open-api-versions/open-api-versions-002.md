# Choosing OpenAPI 3.0 or 3.1 Output by Supported Branch

Springdoc-openapi can generate specifications targeting OpenAPI 3.0 or OpenAPI 3.1. Choosing the version directly affects how the Schema Object represents data types, `null` values, numeric constraints, and examples. Therefore, this choice must be based on the capabilities of contract-consuming tools such as Swagger UI, API gateways, validators, code generators, and API management platforms.

When working with Spring Boot, four concepts must be separated:

| Version | Example | Meaning |
|---|---|---|
| Spring Boot | 3.5.x or 4.1.x | The application's runtime platform. |
| springdoc-openapi | 2.10.x or 3.2.x | The library that reads controllers and generates documents. |
| OpenAPI Specification | 3.0.x or 3.1.x | The specification language version recorded in the `openapi` field. |
| API version | `info.version: 2.4.0` | The contract/API version managed by the product. |

Changing `springdoc.api-docs.version` only changes the generated specification version. It does not automatically upgrade Spring Boot, change endpoint versions, or replace an API versioning process.

## 1. OpenAPI 3.0 and 3.1 serve the same goal

Both versions describe:

- `paths` and HTTP operations.
- Request parameters, request bodies, and responses.
- Schemas, enums, validation constraints, and examples.
- Authentication, security schemes, and security requirements.
- Tags, servers, callbacks, links, and reusable components.

The most notable difference lies in the Schema Object. OpenAPI 3.0 uses a JSON Schema subset adapted for OpenAPI. OpenAPI 3.1 aligns the Schema Object with JSON Schema Draft 2020-12, enabling more modern JSON Schema types and keywords.

This makes OpenAPI 3.1 more expressive for schemas, but it also requires validators, code generators, API gateways, or catalogs to understand the new JSON Schema dialect.

### 1.1. Do not confuse specification version with API version

A document might look like this:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: 2.4.0
~~~

- `openapi: 3.1.0` indicates that the document follows the OpenAPI 3.1 branch.
- `info.version: 2.4.0` is the API version published by the product team.

If the API moves from 2.4.0 to 2.5.0 while still using OpenAPI 3.1, only `info.version` changes. If the integration team switches parsers from OpenAPI 3.0 to 3.1 without changing the API contract, the `openapi` field changes while `info.version` can remain unchanged.

### 1.2. Specification patch versions

The OpenAPI Initiative releases patch versions such as 3.0.4 or 3.1.2. They still belong to the 3.0 or 3.1 branch. The springdoc property selects the 3.0/3.1 mode; do not use this property to request a specific patch such as `3.1.2`.

After configuring it, inspect the actual `openapi` field in JSON/YAML to see the exact patch version the library generates.

## 2. Differences in the Schema Object

Schema changes directly affect code generators and validators. The table below summarizes common differences when moving from 3.0 to 3.1:

| Topic | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Schema foundation | JSON Schema subset adapted for OAS. | Greater compatibility with JSON Schema Draft 2020-12, plus OpenAPI keywords. |
| Null values | Uses `nullable: true` alongside a `type`. | Uses `"null"` in the `type` list or an equivalent JSON Schema structure. |
| Multiple data types | `type` takes a single type. | `type` can be an array of types, e.g. `[string, "null"]`. |
| `exclusiveMinimum` | Boolean combined with `minimum`. | Direct numeric value. |
| Examples in Schema Object | Single `example`. | JSON Schema `examples`; `example` in Schema Object is deprecated. |
| JSON Schema keywords | Supports only the keyword subset defined by OAS 3.0. | Supports JSON Schema 2020-12 keywords/dialect and OAS extensions. |

Not every `example` field needs to be changed to `examples`. The Media Type Object and Parameter Object still have their own OpenAPI ways of describing examples. When migrating, identify the exact location of the keyword instead of doing a global string replacement.

## 3. Representing null values

This is the most common difference in schemas generated from Java/Kotlin DTOs.

### 3.1. OpenAPI 3.0 uses `nullable`

Example of a string property that can accept `null`:

~~~yaml
type: object
properties:
  nickname:
    type: string
    nullable: true
~~~

In OpenAPI 3.0, `nullable` is an OAS-specific keyword. It must accompany an explicitly declared `type`. Do not write `type: null` or `type: [string, null]` using standard JSON Schema syntax.

### 3.2. OpenAPI 3.1 uses union types

Equivalent schema in OpenAPI 3.1:

~~~yaml
type: object
properties:
  nickname:
    type:
      - string
      - "null"
~~~

`null` is a JSON Schema data type. This representation aligns with JSON Schema Draft 2020-12 and can be processed directly by modern JSON Schema validators.

### 3.3. Optional and nullable are two different concepts

A property not listed in `required` can be omitted. A nullable property can appear with the value `null`.

~~~yaml
type: object
required:
  - id
properties:
  id:
    type: string
  nickname:
    type:
      - string
      - "null"
~~~

In the example above:

- `id` must be present.
- `nickname` can be omitted.
- If `nickname` is present, its value can be a string or `null`.

Do not use `nullable` or a union type as a substitute for `required`. Check both aspects when comparing DTOs against actual JSON.

## 4. Numeric constraints change in OpenAPI 3.1

OpenAPI 3.0 uses a Boolean for `exclusiveMinimum` and `exclusiveMaximum`, combined with `minimum`/`maximum`.

~~~yaml
# OpenAPI 3.0
type: number
minimum: 10
exclusiveMinimum: true
maximum: 100
exclusiveMaximum: false
~~~

In OpenAPI 3.0, this example means the value must be greater than 10 and less than or equal to 100.

OpenAPI 3.1 uses direct numeric values:

~~~yaml
# OpenAPI 3.1
type: number
exclusiveMinimum: 10
maximum: 100
~~~

Do not keep the 3.0 Boolean syntax when migrating schemas to 3.1. Check constraints generated from Bean Validation such as `@DecimalMin`, `@DecimalMax`, `@Min`, and `@Max`, then verify the resulting JSON Schema expresses the exact business rule.

## 5. Examples in the Schema Object

In OpenAPI 3.0, the Schema Object commonly uses `example`:

~~~yaml
type: string
format: email
example: developer@example.com
~~~

OpenAPI 3.1 aligns with JSON Schema `examples`:

~~~yaml
type: string
format: email
examples:
  - developer@example.com
  - support@example.com
~~~

However, `example` still appears in other places in OpenAPI, such as the Media Type Object. For example:

~~~yaml
content:
  application/json:
    example:
      id: "d4a8f9"
      nickname: null
~~~

When migrating, distinguish the Schema Object from the Example Object/Media Type Object. Use `examples` for the Schema Object per JSON Schema, while media type payload examples follow the corresponding OpenAPI structure.

## 6. JSON Schema 2020-12 expands expressive power

OpenAPI 3.1 allows taking advantage of many JSON Schema keywords, such as:

- `if`, `then`, `else` to describe conditional schemas.
- `prefixItems` for tuples/arrays with per-position element schemas.
- `contentEncoding` and `contentMediaType` to describe encoded content.
- `$schema` or `jsonSchemaDialect` to identify the dialect when it needs to be explicit.
- Other JSON Schema keywords permitted by the dialect.

Example of a conditional schema:

~~~yaml
type: object
required:
  - paymentMethod
properties:
  paymentMethod:
    type: string
    enum: [card, bank_transfer]
  cardToken:
    type: string
  bankAccount:
    type: string
if:
  required:
    - paymentMethod
  properties:
    paymentMethod:
      const: card
then:
  required:
    - cardToken
else:
  required:
    - bankAccount
~~~

This schema states that when `paymentMethod` is `card`, the object must have `cardToken`; otherwise, the object must have `bankAccount`. Verify that client-side validators and code generators support these keywords before using them in a published contract.

### 6.1. File uploads and content metadata

OpenAPI 3.0 commonly describes binary uploads with:

~~~yaml
type: string
format: binary
~~~

OpenAPI 3.1 can leverage `contentMediaType` and `contentEncoding` from JSON Schema. Example of base64 content:

~~~yaml
type: string
contentEncoding: base64
contentMediaType: image/png
~~~

For multipart requests, you still need to accurately describe the media type, each part, and the payload structure. Do not replace all file upload schemas merely because you switched to 3.1; choose the representation that matches the actual wire format and client parser capabilities.

## 7. Configuring the output version in springdoc

Springdoc provides the property `springdoc.api-docs.version` to choose OpenAPI 3.0 or 3.1. Current property documentation lists the default as `openapi_3_1`.

### 7.1. Choosing OpenAPI 3.1

In `application.yml`:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

This is appropriate when all downstream tools already support OpenAPI 3.1 and the application needs schema capabilities from JSON Schema 2020-12.

### 7.2. Choosing OpenAPI 3.0

If the API gateway, validator, code generator, or developer portal only supports 3.0, configure:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

The values `OPENAPI_3_0` and `OPENAPI_3_1` select the document's serialization/schema mode. Do not manually edit the `openapi` field after generation to fake a different version; the Schema Objects may still carry the syntax of the original version.

### 7.3. Using profiles for environments or deployment groups

If a deployment group needs OpenAPI 3.0 for legacy system compatibility, you can configure it by profile:

~~~yaml
# application.yml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

~~~yaml
# application-legacy-contract.yml
springdoc:
  api-docs:
    version: OPENAPI_3_0
~~~

Only the active profile determines that instance's output mode. This approach works well when running two separate deployments or pipelines. Do not expect a single instance to dynamically emit two different dialects just by changing a query parameter.

## 8. Choosing a springdoc version compatible with Spring Boot

The springdoc library version must be compatible with the Spring Boot major/minor line before choosing OpenAPI 3.0 or 3.1.

According to the springdoc project's compatibility matrix at the time of writing:

| Spring Boot | Corresponding springdoc branch | Notes |
|---|---|---|
| 4.1.x | springdoc 3.1.x – 3.2.x | Use the springdoc 3.x branch. |
| 4.0.x | springdoc 3.0.x | Use the springdoc 3.x branch. |
| 3.5.x | springdoc 2.8.x – 2.10.x | Use the springdoc 2.x branch. |
| 3.4.x | springdoc 2.7.x – 2.8.x | Use the springdoc 2.x branch. |
| 3.3.x | springdoc 2.6.x | Use the springdoc 2.x branch. |
| 3.2.x | springdoc 2.3.x – 2.5.x | Use the springdoc 2.x branch. |
| 3.1.x | springdoc 2.2.x | Use the springdoc 2.x branch. |
| 3.0.x | springdoc 2.0.x – 2.1.x | Use the springdoc 2.x branch. |
| Spring Boot 2.x/1.x | springdoc 1.x | Legacy branch; check support status and v1 documentation. |

The matrix can change across releases. When upgrading, check the current compatibility matrix instead of simply picking the latest springdoc version. Springdoc 2.x is built for Spring Boot 3; springdoc 3.x is for Spring Boot 4.

### 8.1. Springdoc version does not determine API version

For example, an application using Spring Boot 3.5, springdoc 2.10, and OpenAPI 3.1:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

If a legacy client needs OpenAPI 3.0, you can switch the property to `OPENAPI_3_0` without changing the API `info.version`. However, if you need a feature exclusive to OAS 3.1, you must re-evaluate schemas and downstream tools before downgrading to 3.0.

## 9. Choosing 3.0 or 3.1 based on compatibility

Do not choose 3.1 merely because it is springdoc's current default. List the systems consuming the document:

| Component | What to verify |
|---|---|
| Swagger UI | Does the version in use properly render OpenAPI 3.1 and the new Schema Object? |
| API gateway | Does it import, validate, and transform OpenAPI 3.1? |
| OpenAPI parser | Does the parser properly recognize `openapi: 3.1.x` and JSON Schema 2020-12? |
| Code generator | Does the generator handle `type: [string, "null"]`, conditional schemas, and `examples` correctly? |
| Contract testing | Does the tool validate 3.1 schemas and related dialects? |
| API catalog/portal | Does the catalog display 3.1 schemas, nullable fields, and examples accurately? |
| Published client SDKs | Does changing the schema alter model nullability or generated code? |

### 9.1. When to choose OpenAPI 3.0

Choose 3.0 when:

- The API gateway or API catalog only accepts OAS 3.0.
- The client generator does not yet support JSON Schema 2020-12.
- The contract testing system is locked to a 3.0 validator.
- Integration partners have standardized on 3.0 schemas and cannot upgrade yet.
- The API's schemas do not require new JSON Schema keywords.

OpenAPI 3.0 still meets most common REST API description needs. There is no need to change versions just to alter a label in the document.

### 9.2. When to choose OpenAPI 3.1

Choose 3.1 when:

- All primary consumers already support OAS 3.1.
- You need to describe `null` using JSON Schema type unions.
- You need conditional schemas or JSON Schema 2020-12 keywords.
- You need to share schemas with the JSON Schema ecosystem with minimal translation.
- You want to standardize the contract on the newer dialect and can test the entire pipeline.

OpenAPI 3.1 can improve schema accuracy, but only when consuming tools interpret the schema according to the intended contract.

## 10. Process for migrating from OpenAPI 3.0 to 3.1

Changing the property is only the first step. A migration should go through these steps:

1. **Inventory consumers**: list Swagger UI, gateways, parsers, generators, contract tests, API catalogs, and client SDKs.
2. **Check compatibility**: verify tool versions support OpenAPI 3.1 and JSON Schema Draft 2020-12.
3. **Generate the 3.1 document**: set `springdoc.api-docs.version=OPENAPI_3_1` in a test environment.
4. **Compare schemas**: inspect `nullable`, union types, `exclusiveMinimum`, `exclusiveMaximum`, `example`, and `examples`.
5. **Review JSON Schema keywords**: confirm new keywords do not cause validators or generators to misinterpret contracts.
6. **Validate the specification**: use a validator that supports OAS 3.1, not a configuration that only understands OAS 3.0.
7. **Test-generate SDKs**: compare models, nullability, enums, and data types between both outputs.
8. **Run contract tests**: test valid and invalid payloads against the new schema.
9. **Check Swagger UI and API gateway**: import, render, authorize, and test requests.
10. **Controlled release**: archive the new artifact, record both spec version and API version, and prepare a rollback plan.

### 10.1. Comparing two generated documents

Save two artifacts from the same application revision:

- `openapi-3.0.json`
- `openapi-3.1.json`

Then compare:

- The `openapi` field.
- `components.schemas` and `$ref` entries.
- Nullable fields.
- Numeric and string constraints.
- Examples in Schema Objects and Media Type Objects.
- Request/response content.
- Security schemes.
- Server URLs and paths.

Do not rely solely on a text diff because key ordering or pretty-printing may differ. Parse both documents, compare their structures, and run the appropriate validator for each version.

## 11. Verifying output with MockMvc

An integration test can verify that springdoc is serving the configured OpenAPI branch.

Example verifying OpenAPI 3.1:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "springdoc.api-docs.version=OPENAPI_3_1"
})
@AutoConfigureMockMvc
class OpenApiVersionContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesOpenApi31Document() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi", startsWith("3.1.")));
    }
}
~~~

To test 3.0, replace the property with `OPENAPI_3_0` and the matcher with `startsWith("3.0.")`. Use a prefix instead of hardcoding the patch version because the patch may depend on the springdoc/`swagger-core` version.

### 11.1. Verifying YAML output

Springdoc typically provides both JSON and YAML:

- JSON: `/v3/api-docs`
- YAML: `/v3/api-docs.yaml`

Both outputs can be fetched in CI:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
curl -fsS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
~~~

Parse both and verify the `openapi` field and corresponding schemas. Do not test only JSON if the artifact published to partners is YAML, or vice versa.

### 11.2. Verifying `info.version` independently

In the same test suite, you can verify the API release version:

~~~java
mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.info.version").value("2.4.0"));
~~~

This test verifies the API version. It does not replace testing `$.openapi` because the two fields have different meanings.

## 12. Common mistakes

- **Changing `info.version` to choose OpenAPI 3.1**: `info.version` is only the API version; use `springdoc.api-docs.version`.
- **Manually editing `openapi` after generation**: schemas may still carry the syntax of the old dialect.
- **Keeping `nullable: true` as if it were standard JSON Schema 2020-12**: switch to a type union containing `"null"` when schemas use 3.1 syntax.
- **Keeping `exclusiveMinimum: true` in 3.1**: 3.1 uses direct numeric values.
- **Replacing every `example` with `examples`**: only the Schema Object has this difference; Media Type Objects and other locations must be handled according to their own structures.
- **Only checking that Swagger UI renders**: successful UI rendering does not prove gateways, validators, and code generators understand the schema correctly.
- **Upgrading springdoc without checking Spring Boot**: the springdoc major version must match Spring Boot's compatibility matrix.
- **Assuming springdoc 3.x means OpenAPI 3.1**: the library version and specification version are two separate choices.
- **Using an OAS 3.0 parser to validate a 3.1 document**: the parser may reject or ignore new keywords.
- **Not testing YAML**: valid JSON does not guarantee the published YAML artifact is valid.
- **Ignoring published SDKs**: changes in nullability or schemas can affect generated models and client logic.
- **Assuming springdoc supports every newest OpenAPI version**: check the property and serialization capabilities of the exact library branch before picking a dialect.

## 13. Note on OpenAPI 3.2

The OpenAPI Initiative has released the OpenAPI 3.2 branch. However, the `springdoc.api-docs.version` property in current springdoc documentation describes two choices: `OPENAPI_3_0` and `OPENAPI_3_1`.

Do not set `OPENAPI_3_2` or manually edit the `openapi` field to `3.2.x` if the springdoc and Swagger Core versions in use do not yet support OAS 3.2 serialization and schemas. When 3.2 is needed, check the release notes and documentation of the libraries, parsers, UI, and generators before building a pipeline.

## 14. Process for choosing a project's version

1. **Identify the Spring Boot line** currently running.
2. **Select the compatible springdoc branch** for that Boot line.
3. **Check the `springdoc.api-docs.version` property** on that branch.
4. **List all consumers** of the OpenAPI JSON/YAML.
5. **Choose 3.0** if legacy system compatibility is required; choose 3.1 when all consumers support the new schema format.
6. **Configure profiles** to test or publish artifacts in the selected dialect.
7. **Validate both JSON and YAML** using a tool that understands the exact OAS version.
8. **Compare schemas and SDKs** before changing the contract.
9. **Record both the API version and spec version** in artifacts/release notes.
10. **Monitor compatibility** when upgrading Spring Boot, springdoc, Swagger UI, or code generators.

## 15. Review checklist

- [ ] Distinguished Spring Boot version, springdoc version, OpenAPI version, and `info.version`.
- [ ] Springdoc branch is compatible with the Spring Boot version in use.
- [ ] `springdoc.api-docs.version` is intentionally set to `OPENAPI_3_0` or `OPENAPI_3_1`.
- [ ] Verified the `openapi` field in output JSON/YAML.
- [ ] Nullable and required schemas are represented properly.
- [ ] `exclusiveMinimum` and `exclusiveMaximum` match the dialect.
- [ ] `example`/`examples` are placed in the correct OpenAPI Object locations.
- [ ] Validators and parsers support the selected version.
- [ ] Swagger UI and API gateway render/import properly.
- [ ] Code generator creates models with proper nullability and data types.
- [ ] Contract tests cover both valid and invalid payloads.
- [ ] Both JSON and YAML are checked if both formats are published.
- [ ] Artifacts explicitly record both API version and OpenAPI specification version.
- [ ] Did not manually alter the `openapi` field to fake a dialect not yet supported by the library.

## 16. References

- [springdoc-openapi – Core properties](https://springdoc.org/core-properties.html)
- [springdoc-openapi v2 – Core properties](https://springdoc.org/v2/core-properties.html)
- [springdoc-openapi – Compatibility matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-springdoc-openapi-with-spring-boot)
- [springdoc-openapi GitHub README](https://github.com/springdoc/springdoc-openapi)
- [OpenAPI Initiative – Specification versions](https://spec.openapis.org/oas/)
- [OpenAPI 3.1 – Upgrading from OpenAPI 3.0](https://learn.openapis.org/upgrading/v3.0-to-v3.1.html)
- [Swagger – OpenAPI 3.0 Data Types](https://swagger.io/docs/specification/v3_0/data-models/data-types/)
- [Swagger – OpenAPI 3.1 Specification](https://swagger.io/specification/v3.1/)

Choosing OpenAPI 3.0 or 3.1 is a decision about the contract language and ecosystem compatibility. Pick the right springdoc branch for Spring Boot, set `springdoc.api-docs.version`, verify schemas against the corresponding dialect, and validate JSON/YAML with the actual tools that will consume the document. Keep `info.version` independent to manage the API lifecycle without conflating it with the specification version.
