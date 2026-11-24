# How JSON and YAML Documents Differ in Interpretation and UI Rendering

OpenAPI can be represented in either JSON or YAML. These two formats have different syntax, yet when describing the same OpenAPI model they carry the exact same meaning: the same endpoints, HTTP methods, parameters, request bodies, responses, schemas, and security requirements. Springdoc-openapi can serve both representations for automated tools, documentation reviewers, and Swagger UI.

With the `SPRINGDOC_OPENAPI` module, three concerns should be kept distinct: the OpenAPI contract data, how that data is serialized into JSON or YAML, and how Swagger UI reads and renders the contract. File format affects how tools read and process the file; it does not alter API behavior or contract content on its own.

## 1. One OpenAPI Model, Two Serialization Formats

Springdoc collects metadata from Spring controllers, DTOs, annotations, and configuration to build an OpenAPI model. That model can be serialized to JSON or YAML.

With typical default configuration:

| Endpoint | Format |
|---|---|
| `/v3/api-docs` | JSON |
| `/v3/api-docs.yaml` | YAML |

Both endpoints serve the exact same specification. If you convert JSON to YAML with an appropriate parser and read it back into a data structure, the OpenAPI elements carry equivalent meaning. Key ordering, whitespace, braces, and line breaks may differ without changing the contract.

For example, both describe the same operation to fetch an order:

**YAML format**

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: '1.0'
paths:
  /orders/{id}:
    get:
      summary: Get order
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Order found
```

**Equivalent JSON format**

```json
{
  "openapi": "3.0.3",
  "info": {
    "title": "Order API",
    "version": "1.0"
  },
  "paths": {
    "/orders/{id}": {
      "get": {
        "summary": "Get order",
        "parameters": [
          {
            "name": "id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Order found"
          }
        }
      }
    }
  }
}
```

JSON's curly braces, commas, and double quotes are replaced by indentation and colons in YAML. Yet both describe a path `/orders/{id}`, a `get` operation, a required path parameter, and a `200` response.

## 2. Syntax and Readability Differences

JSON represents objects with `{}`, arrays with `[]`, key-value pairs with colons, and elements separated by commas. Property names and string values must be wrapped in double quotes. JSON does not support comments and forbids trailing commas at the end of objects or arrays.

YAML commonly uses indentation to represent structure. Hyphens introduce list items, and colons separate keys from values. YAML supports `#` comments, multiline strings, and multiple scalar styles, making it easier to read when a document has many schemas or long descriptions.

| Criterion | JSON | YAML |
|---|---|---|
| Object structure | `{ ... }` | Indented keys and values |
| Lists | `[ ... ]` | Lines starting with `-` or flow syntax |
| Strings | Double-quoted | Plain, single-quoted, or double-quoted |
| Comments | No standard comment syntax | Uses `#` |
| Multiline strings | Must escape newline characters | Has block scalars `|` and `>` |
| Element separation | Commas | Primarily newlines and indentation |
| Programmatic processing | Built-in parsers widely available | Requires a compatible YAML parser |
| Manual review | Clear for tooling and small structures | Usually compact and readable for long specs |

JSON has strict syntax suited to automation and service-to-service exchange. YAML has fewer structural punctuation characters, making it convenient for authoring and reviewing contracts. Choosing a format should depend on consuming tools, review workflows, and team conventions.

## 3. Syntax Differences That Can Change Meaning

When converting documents between JSON and YAML, pay attention to data types and escaping rules. A file may look reasonable to the human eye while a parser reads it as a different type.

### Strings and Special-Shaped Values

In JSON, strings are always enclosed in double quotes. In YAML, many strings can be written unquoted, yet they should be quoted whenever a value could be mistaken for a boolean, number, null, or contains syntactically meaningful characters.

```yaml
info:
  version: '1.0'
  description: 'Order management API: create, read, and cancel orders.'
paths:
  /orders/{id}:
    get:
      responses:
        '200':
          description: Success
```

In this example, `info.version` is a version string, so quoting `'1.0'` prevents parsers from interpreting it as a number. Response status codes should also be quoted, such as `'200'`, to keep the string keys required by OpenAPI.

Values like `true`, `false`, `null`, `on`, `off`, digit-only strings, or strings containing `:` and `#` must be checked against the YAML version and parser in use. When the intent is a string, wrap it in quotes to express it unambiguously.

### The `#` Character and `$ref` References

In YAML, `#` can start a comment when appearing in certain positions. Therefore, reference values containing `#` should be quoted:

```yaml
schema:
  $ref: '#/components/schemas/OrderResponse'
```

If quotes are omitted and written as `$ref: #/components/schemas/OrderResponse`, a parser may treat everything from `#` onward as a comment and read an empty value. JSON inherently represents this value as a string:

```json
{
  "$ref": "#/components/schemas/OrderResponse"
}
```

### Multiline Strings

YAML supports block scalars. The `|` indicator preserves newlines in the content; the `>` indicator folds lines according to folded-scalar rules. This is helpful when operation or schema descriptions span multiple paragraphs.

```yaml
description: |
  Create a new order.
  The API validates customer data and amount before saving.
```

In JSON, the equivalent content is represented using `\n` escapes:

```json
{
  "description": "Create a new order.\nThe API validates customer data and amount before saving."
}
```

YAML comments let maintainers leave notes in source files, yet comments are not part of the OpenAPI model and usually disappear when a parser reads and re-serializes the document. If information needs to reach API consumers, put it in `description`, `summary`, `example`, or appropriate metadata fields.

## 4. Data Types and Interpretation Rules

JSON has a clear set of data types: object, array, string, number, boolean, and null. YAML has multiple scalar styles and type-resolution rules, so parsers may infer types from how values are written.

Example:

```yaml
example:
  active: true
  retryCount: 3
  customerCode: '00123'
  description: 'Status code: received'
```

In this structure, `active` is a boolean, `retryCount` is a number, and `customerCode` is a string preserving leading zeros. Writing `customerCode: 00123` unquoted can depend on parser/YAML version rules and lose the intended string value.

When defining OpenAPI schemas, types should match actual API data:

- Identifiers can be strings even when containing only digits.
- Postal codes, customer codes, or account numbers are usually strings because they may have leading zeros and are not used in arithmetic.
- Monetary amounts should be described with types and formats matching how the application serializes them; do not silently switch strings to numbers or vice versa when converting formats.
- Boolean fields should be true booleans, not `'true'` strings.
- Empty strings, missing properties, and `null` are distinct states in JSON/OpenAPI; do not conflate them.

With YAML, prefer simple scalars, quote ambiguous strings, and avoid relying on advanced YAML features unless pipeline tools support them uniformly. With JSON, always verify escaping of double quotes, backslashes, and newlines.

## 5. Parsers and Document-Consuming Tools

The format determines which parser is needed before a tool can process the OpenAPI model. Once parsed, tools typically operate on the normalized data structure.

| Tool or Workflow | JSON | YAML |
|---|---|---|
| Browser opening endpoint directly | Usually renders JSON content | May display YAML as plain text |
| JavaScript `JSON.parse` | Reads directly | Cannot read YAML directly |
| YAML parser | Not required | Requires a YAML parser |
| OpenAPI validator | Supported when validator accepts JSON | Supported when validator accepts YAML |
| Git diff | Can have more braces and commas | Often cleaner for nested structures |
| Client or mock server generation | Works if tool supports OpenAPI JSON | Works if tool supports OpenAPI YAML |

Not every tool auto-detects formats in all situations. When calling endpoints or configuring pipelines, supply the exact URL, file extension, or content type expected by the tool. Feeding YAML content to a JSON parser causes an error before the tool even inspects OpenAPI semantics.

For example, in JavaScript:

```javascript
// Read JSON document
const openApiDocument = JSON.parse(jsonText);
```

With YAML, use a YAML parser library to obtain an equivalent object:

```javascript
// Example with yaml package
import { parse } from 'yaml';

const openApiDocument = parse(yamlText);
```

Once parsed, tools can access `openApiDocument.paths`, `openApiDocument.components`, or other fields regardless of the original source syntax.

## 6. How Does Swagger UI Render JSON and YAML?

Swagger UI does not render raw JSON braces or YAML indentation as the API interface. It fetches the OpenAPI document from the configured URL, parses it, and builds the UI from components such as tags, paths, operations, parameters, schemas, responses, and security.

Therefore, when JSON and YAML describe the same OpenAPI model, Swagger UI displays the same operations and corresponding details. Users still see endpoints, descriptions, parameter input forms, request bodies, responses, and Try-it-out buttons according to Swagger UI settings. Whether the source is JSON or YAML does not produce a different business interface.

In default configurations, Swagger UI normally uses the JSON endpoint `/v3/api-docs`. To have the UI read the YAML endpoint, configure the document URL, for example:

```yaml
springdoc:
  swagger-ui:
    url: /v3/api-docs.yaml
```

Check exact property names and how they combine with multi-document lists against your springdoc version. If `springdoc.swagger-ui.urls` is configured, ensure each entry's URL points to the right JSON or YAML endpoint.

Factors that actually affect how Swagger UI renders include:

- `tags` and tag ordering in the document, affecting operation grouping.
- `summary`, `description`, `operationId`, and `deprecated`, affecting operation labels and text.
- `parameters`, `requestBody`, `responses`, and schemas, affecting input forms and request/response details.
- `securitySchemes` and `security`, affecting authentication declarations and Authorize actions.
- Swagger UI configuration, UI version, and how the document is loaded.

If Swagger UI renders differently between JSON and YAML sources, download both, parse them, and compare the OpenAPI models. Differences almost always stem from the content of the two documents, URL configuration, API groups, Swagger UI version, or caching—not the format itself.

## 7. Exporting JSON and YAML from springdoc

Springdoc provides two default endpoints to fetch the document. Each format can be downloaded separately:

```bash
curl.exe -fS http://localhost:8080/v3/api-docs -o openapi.json
curl.exe -fS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
```

If the application changes `springdoc.api-docs.path`, use the new path and its corresponding YAML endpoint. If the application has a context path or reverse proxy prefix, external URLs must include that prefix too.

Documentation for an API group can be configured separately. When it is, fetch that specific group's document instead of the default aggregate document. Swagger UI can also point to one or more document URLs; verify whether each URL is JSON or YAML and which group it maps to.

You do not need two separate sets of annotations just to emit both formats. Controllers, DTOs, and OpenAPI configuration serve as the single source; springdoc serializes that same model to JSON or YAML.

## 8. Choosing a Format by Use Case

Neither format is strictly better in every case. Choose based on how the specification is generated, reviewed, processed, and distributed.

| Scenario | Convenient Choice | Reason |
|---|---|---|
| Storing specs in Git for developer review | YAML | Compact, readable, and supports comments for internal notes |
| Exchanging with systems accepting only JSON | JSON | Works directly with JSON parsers and APIs |
| Processing in JavaScript without extra parsers | JSON | Works with `JSON.parse` |
| Long descriptions, deeply nested schemas | YAML or JSON | YAML is often easier to read; JSON remains valid if tools require it |
| Generating clients, mocks, or contract tests | Either | Pick whichever format the tool supports and standardize in the pipeline |
| Swagger UI integration | Either | The UI reads the parsed OpenAPI model |

A team can store YAML as a review-friendly spec while providing JSON to automated systems. What must stay consistent is that both outputs are generated from the same application build and OpenAPI configuration. Never hand-edit one output separately and let the two formats describe diverging contracts.

## 9. Comparing Two Documents Properly

Comparing raw JSON text against raw YAML text creates many superficial diffs because the two formats use different punctuation. To determine whether the contract truly changed, parse both into a common model and compare the data.

A comparison workflow can proceed as follows:

1. Download JSON and YAML from the same application, profile, and document group.
2. Parse JSON with a JSON parser and YAML with a compatible YAML parser.
3. Canonicalize representation if the diff tool requires it, without stripping meaningful fields.
4. Compare OpenAPI fields such as `openapi`, `info`, `servers`, `paths`, `components`, and `security`.
5. For any diff, determine whether it is a data change or merely key order, string quoting, or formatting.
6. Run an OpenAPI validator and contract tests on the document chosen for distribution.

In JSON, object property order carries no contract semantics. Likewise, do not rely on YAML key order to imply API priority. However, array order is part of the data and can affect how tools render certain elements; do not arbitrarily sort arrays during normalization.

## 10. Common Conversion and Rendering Errors

| Symptom | Cause | How to Fix |
|---|---|---|
| JSON parser fails when reading YAML | Wrong parser for the format | Use a YAML parser or fetch the JSON endpoint |
| YAML parser reads `version` as a number | Unquoted version string | Wrap string values like `'1.0'` in quotes |
| `$ref` becomes an empty value | `#` treated as a YAML comment | Wrap the `$ref` value in quotes |
| Response status code read as a number | Unquoted status code key | Use `'200'`, `'404'`, and string keys |
| JSON invalid after manual edits | Missing comma, bad escaping, or comments/trailing comma | Run a JSON parser and fix syntax |
| YAML fails due to indentation | Tabs used, wrong nesting level, or unquoted scalars | Use consistent spaces and a YAML validator |
| Swagger UI does not update when switching to YAML | UI still loads old JSON URL or cached document | Check document URL, Swagger UI config, and cache |
| Swagger UI renders different operations | Two docs have different content, group, or profile | Parse and compare the OpenAPI models of both |
| Comments vanish after re-export | Comments are not part of the OpenAPI data model | Put published content into `description` or metadata |

## 11. Recommended Workflow for Spring Boot Applications

A practical workflow to keep JSON, YAML, and Swagger UI synchronized:

1. Declare Spring mappings, DTOs, validation, and OpenAPI metadata in source code.
2. Start the application with the profile under test.
3. Fetch `/v3/api-docs` and `/v3/api-docs.yaml`.
4. Parse both formats and confirm the OpenAPI models are equivalent.
5. Run a validator to catch syntax errors and specification structure violations.
6. Verify Swagger UI loads the right URL and displays the expected API groups.
7. Invoke representative endpoints to cross-check requests, responses, and security against the contract.
8. Archive or distribute artifacts by API version while ensuring JSON and YAML come from the same source.

When changing how Swagger UI renders the API, inspect OpenAPI metadata and UI settings. Switching from JSON to YAML changes only the input serialization; it does not alter tags, business group order, endpoint descriptions, or request forms.

## Conclusion

JSON and YAML are two serialization formats of the same OpenAPI model. JSON has strict syntax well suited for automation; YAML is compact, readable, and convenient for manual review. Swagger UI parses the document and renders from the OpenAPI content, so equivalent documents present the same UI information. When working with `springdoc-openapi`, pick format-appropriate parsers, watch scalar types and special characters in YAML, point Swagger UI to the right document URL, and verify equivalence before distributing an API contract.
