# Limiting Example and Description Sizes to Keep Documentation Lightweight

An OpenAPI Description can grow very large when an API has many operations, nested schemas, lengthy request/response examples, and descriptions containing long Markdown passages. Large documents increase generation and download times, network transfer costs, memory required to parse JSON/YAML, and the time Swagger UI takes to render the interface. Integrators also struggle to find key information when every operation carries repetitive content.

Keeping the documentation concise does not mean deleting contract information. You need to distinguish what describes the API structure from what is merely illustrative data or lengthy guides, then set deliberate limits on examples, descriptions, schemas, and document scope. Details necessary to understand requests, responses, validation, and security must still be preserved.

This lesson guides you through measuring OpenAPI document size, trimming examples and descriptions, reusing schemas/examples, splitting documentation by API group, optimizing serving, and setting a size budget in CI.

## 1. Why Does Document Size Affect Performance?

Opening Swagger UI typically involves several stages:

~~~mermaid
flowchart TD
    A["Browser opens API docs"] --> B["Download Swagger UI assets"]
    B --> C["Download OpenAPI JSON/YAML"]
    C --> D["Parse document"]
    D --> E["Resolve schemas and references"]
    E --> F["Render tags, operations, models and examples"]
    F --> G["User expands an operation"]
~~~

A large document can increase costs at multiple points:

| Stage | Impact of a Large Document |
|---|---|
| Document generation | Springdoc must analyze metadata and serialize many objects |
| Transfer | More bytes travel across the application, proxy, and browser |
| Parsing | The browser or consuming tool needs additional CPU and memory |
| Rendering | Many operations, schemas, and examples slow down UI rendering |
| CI | Larger artifacts; validators and diffs may run slower |
| Consumer tooling | Code generators or API portals must process more content |

Not all large documents are equally slow. A file with many schemas reused via references may be easier to process than a file with many duplicated inline schemas. A multi-megabyte JSON example can impact download and rendering more than hundreds of short description lines.

## 2. OpenAPI Does Not Impose a Universal Byte Limit

The OpenAPI Specification defines the structure and semantics of a document, but does not establish a universal maximum byte limit that applies to every server, proxy, browser, API portal, or generator.

Practical limits depend on:

- Response size limits allowed by the application and reverse proxy.
- Timeouts and memory limits of the browser or API documentation portal.
- Upload/import limits of the registry or gateway.
- Parsing and rendering capability of the Swagger UI version.
- CI time acceptable for generation, validation, and diffing.
- Network conditions of the development team or consumers.

Therefore, do not impose an arbitrary number like 1 MB or 5 MB across all projects. Measure your current document, determine thresholds appropriate for your consumption environment, track growth trends, and set a reasoned budget.

At least three metrics should be tracked:

1. **Raw size:** byte count of the stored JSON/YAML.
2. **Compressed size:** byte count after gzip or Brotli when transferred over HTTP.
3. **Structural size:** counts of paths, operations, schemas, parameters, and examples in the document.

Compressed size better reflects transfer cost when the server enables compression. Raw size remains important because the browser must parse the content after decompression. Structural size explains why the document is growing.

## 3. Identifying What Causes Document Bloat

Common sources that inflate documentation:

- Request or response examples containing very long data arrays.
- Examples containing base64, images, PDFs, or encoded binary strings.
- Descriptions copying entire user guides, error code tables, or lengthy business documentation.
- Multiple operations repeating the same inline schema.
- DTOs containing many internal fields or fields not part of the public contract.
- Multiple API groups merged into a single document.
- Examples declared repeatedly at the schema, media type, and individual operation levels.
- Names, descriptions, or examples generated dynamically per environment.

Do not simply look at total bytes and cut content blindly. First identify the largest contributor. If examples dominate, trimming examples can sharply reduce size without changing schemas. If schemas are duplicated, reusing components can be more effective. If the document covers multiple independent bounded contexts, splitting into groups can reduce how much data users must download per group.

## 4. Measuring OpenAPI File Size

If the Gradle plugin generates the default file at build/openapi.json, you can measure raw size with PowerShell:

~~~powershell
(Get-Item "build/openapi.json").Length
~~~

Or on Linux/macOS:

~~~bash
wc -c < build/openapi.json
~~~

Measure gzip size to estimate HTTP payload when compression is enabled:

~~~bash
gzip -c build/openapi.json | wc -c
~~~

To compare trends, record metrics alongside the commit, API group, profile, and springdoc version. Do not compare the raw size of a public API against the compressed size of an admin API.

### Counting Operations and Schemas

You can use jq to count operations in JSON:

~~~bash
jq '[.paths[] | keys[] | select(
  . == "get" or . == "post" or . == "put" or
  . == "patch" or . == "delete" or . == "options" or
  . == "head" or . == "trace"
)] | length' build/openapi.json
~~~

Count schema components:

~~~bash
jq '(.components.schemas // {}) | length' build/openapi.json
~~~

These numbers do not replace content inspection. One operation with a massive example can still make a document heavy even with a low operation count.

## 5. Limiting Example Sizes

Examples help readers understand how to send requests and read responses. A good example illustrates the data shape and a typical scenario. It does not need to include all data that could appear in production.

Prefer:

- Using one representative record instead of an array of hundreds of records.
- Choosing short values that remain valid against the schema.
- Keeping only fields needed to illustrate the operation.
- Using one example for the common success flow and adding error examples when they clarify a distinct, important contract.
- Avoiding repeating the same payload in multiple places when a shared example can be referenced.
- Never embedding base64, binary files, or long logs into examples.
- Never using real tokens, cookies, personal data, or production data.

A list response example does not need to contain an entire page of data:

~~~json
{
  "items": [
    {
      "id": "prd-1001",
      "name": "Keyboard",
      "price": 1250000
    },
    {
      "id": "prd-1002",
      "name": "Mouse",
      "price": 450000
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 2
}
~~~

This example illustrates a page with two items. If the API can return thousands of items, document pagination in the schema and description; there is no need to embed thousands of elements into the document.

### Examples Are Not Runtime Data Limits

Shortening an example only changes illustrative content. It does not limit the number of elements the API can return, enable pagination, or restrict request body size. Runtime limits must be enforced in the corresponding controller, validation, service, or server configuration.

Conversely, schema keywords such as minItems, maxItems, maxLength, or maximum are contract constraints. Only declare such constraints when the API actually enforces them; do not add maxItems merely to keep an example short.

## 6. Declaring Concise Examples via Annotations

You can use @Schema to describe a sample value for a field:

~~~java
import java.math.BigDecimal;
import io.swagger.v3.oas.annotations.media.Schema;

public record CreateProductRequest(
    @Schema(
        description = "Product display name.",
        example = "Keyboard"
    )
    String name,

    @Schema(
        description = "Selling price in the store currency.",
        example = "1250000"
    )
    BigDecimal price
) {}
~~~

Field-level examples help readers understand the type and shape of values. Descriptions should explain meaning or important rules rather than repeating the entire example.

For request bodies, use @ExampleObject to describe a payload:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;

@PostMapping("/products")
@Operation(
    summary = "Create product",
    description = "Create a new product in the catalog.",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            examples = @ExampleObject(
                name = "basic-product",
                summary = "Basic product",
                value = """
                    {
                      "name": "Keyboard",
                      "price": 1250000
                    }
                    """
            )
        )
    )
)
public ResponseEntity<ProductResponse> create(
        @org.springframework.web.bind.annotation.RequestBody
        CreateProductRequest request) {
    // ...
}
~~~

In real code, the RequestBody annotation is placed in operation metadata or on the corresponding parameter depending on how the controller is declared. Do not add a large example just to repeat a schema that readers can already see immediately below.

## 7. Reusing Examples Instead of Copying Them

OpenAPI supports declaring shared examples in components and referencing them from multiple operations:

~~~yaml
components:
  examples:
    BasicProduct:
      summary: Basic product
      value:
        name: Keyboard
        price: 1250000
paths:
  /products:
    post:
      requestBody:
        content:
          application/json:
            examples:
              basic:
                $ref: '#/components/examples/BasicProduct'
~~~

Reusing examples avoids duplicating the same payload across multiple operations and allows updating an example in one place. With annotations, you can use an Example Object reference if the swagger-annotations version in use supports the ref attribute.

Do not create a component for every tiny example just to save a few bytes. References add structural indirection that consuming tools must resolve. Only reuse when a payload has shared meaning and is used by multiple operations.

## 8. Moving Very Large Examples Outside the Document

The OpenAPI Example Object provides an externalValue property to point to example content at an external URL. This keeps the OpenAPI document lighter when large sample files must be provided:

~~~yaml
paths:
  /reports/export:
    get:
      responses:
        "200":
          description: Generated report file.
          content:
            application/json:
              examples:
                sample:
                  summary: A sample report
                  externalValue: https://docs.example.com/examples/report-sample.json
~~~

External examples are suitable for:

- Large payloads to be downloaded separately only when a user actually wants to inspect them.
- Multi-line CSV or JSON sample files.
- Fixture suites used in integration guides.
- Binary examples or downloadable files unsuitable for embedding in OpenAPI JSON.

There are several limitations to consider:

- The external URL must be stable, versioned, or managed alongside the release.
- Consumers might not automatically fetch externalValue.
- Swagger UI and API portals may differ in how they support external examples.
- Private URLs might require authentication that browsers or generators lack.
- Documentation can lose self-containment if the example is deleted or the URL changes.

If an example is critical for contract testing, store the fixture in a repository or versioned artifact and verify it in CI. Do not depend on an unmanaged public URL.

## 9. Limiting Description Length

A description should answer the question an integrator needs at that exact spot. A short, concrete description is usually more helpful than a long paragraph repeating the schema.

| Location | What Should Be Described? |
|---|---|
| OpenAPI info.description | API scope, audience, and general conventions |
| Tag description | Business group or resource domain |
| Operation summary | Brief action of the endpoint |
| Operation description | Conditions, processing flow, or special behavior |
| Parameter description | Meaning, format, unit, and how to pass it |
| Schema/property description | Field meaning, business constraints, and units |
| Response description | Conditions under which the status code is returned |

Avoid:

- Copying the field name into the description without adding meaning.
- Pasting an entire how-to guide into every operation.
- Repeating the same authentication instructions in every operation when already documented via security schemes and global policies.
- Embedding stack traces, logs, or long production payloads.
- Using huge Markdown tables for value lists that can be expressed with an enum or a documentation link.
- Using descriptions in place of schemas, required flags, formats, or constraints that OpenAPI can express natively.

There is no universal character limit for descriptions in OAS. Project teams should establish a style guide—such as length limits for summaries, operation descriptions, and property descriptions—and enforce it via reviews or lint rules. Specific thresholds should be grounded in readability and the module's actual data.

## 10. Moving Long Guides to Separate Documentation

If an operation requires multi-step instructions, lengthy business examples, or workflow explanations, keep a concise summary in OpenAPI and place detailed guides in separate documentation.

OpenAPI supports the External Documentation Object at the document, tag, or operation level. Annotation example:

~~~java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.Operation;

@Operation(
    summary = "Create order",
    description = "Create an order from the selected products.",
    externalDocs = @ExternalDocumentation(
        description = "Order lifecycle guide",
        url = "https://docs.example.com/orders/lifecycle"
    )
)
~~~

YAML example:

~~~yaml
paths:
  /orders:
    post:
      summary: Create order
      description: Create an order from the selected products.
      externalDocs:
        description: Order lifecycle guide
        url: https://docs.example.com/orders/lifecycle
~~~

OpenAPI still retains everything required to understand the operation: request, response, parameters, security, and key conditions. External links supplement long guides rather than replacing contract content.

## 11. Reusing Schemas with Components and $ref

If multiple operations use the same structure, use a shared schema component instead of repeating an inline object everywhere.

~~~yaml
components:
  schemas:
    ProductSummary:
      type: object
      required:
        - id
        - name
      properties:
        id:
          type: string
        name:
          type: string
        price:
          type: number
          format: double
paths:
  /products:
    get:
      responses:
        "200":
          description: Product list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ProductSummary'
  /products/{id}:
    get:
      responses:
        "200":
          description: Product details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductSummary'
~~~

Springdoc usually recognizes reused Java models and creates a component schema for referencing. Use dedicated, clearly named DTOs and reuse them when two operations genuinely share the same contract. Do not force every endpoint to share one giant DTO merely to reduce OpenAPI line count.

Shared schemas can alter many operations at once when a DTO changes. Therefore, check semantic diffs and consider separating request models, response models, or view models when their semantics differ.

## 12. Keeping Internal Fields Out of Public Schemas

An internal DTO may hold fields used for persistence, tracing, auditing, or internal processing. If every field appears in OpenAPI, the document becomes larger and may expose structure not intended for consumers.

Design request/response DTOs specifically for the public contract. Only use annotations to hide a field when that field truly does not belong to the contract:

~~~java
public record ProductResponse(
    String id,
    String name,

    @Schema(hidden = true)
    String internalWarehouseKey
) {}
~~~

In the example, internalWarehouseKey is not published in the schema. Hiding a field from OpenAPI does not automatically exclude it from runtime JSON. If the serializer still emits that field, the documentation and actual response will diverge. Configure Jackson or the DTO so the real response does not emit internal data either.

Do not use hidden=true merely to make the document smaller if that field is part of the API that clients need to know about. The goal is to publish the accurate contract, not conceal the contract.

## 13. Splitting Documentation by API Group

If an application serves multiple independent domains such as catalog, orders, and billing, a single document may contain too many operations. springdoc supports GroupedOpenApi to generate separate documents by path or package.

~~~java
import org.springframework.context.annotation.Bean;
import org.springdoc.core.models.GroupedOpenApi;

@Bean
GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .pathsToMatch("/api/catalog/**")
        .build();
}

@Bean
GroupedOpenApi ordersApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .pathsToMatch("/api/orders/**")
        .build();
}
~~~

Group documents are typically served at:

~~~text
/v3/api-docs/catalog
/v3/api-docs/orders
~~~

Splitting groups lets users load only the relevant portion of documentation. Multiple documents can be used in Swagger UI or served as separate URLs for portals and consumers.

Do not split so finely that users must open many documents to understand a simple workflow. Choose boundaries along bounded contexts, consumer groups, or real access permissions. Each group should maintain consistent server URLs, security, and metadata.

## 14. Optimizing Swagger UI Without Altering the Contract

Smaller documents generally help Swagger UI load and parse faster. In addition, you can reduce the amount of content expanded immediately when the UI renders.

Example UI configuration:

~~~yaml
springdoc:
  swagger-ui:
    doc-expansion: none
    default-models-expand-depth: -1
    display-request-duration: true
~~~

Meaning:

- doc-expansion none collapses operations by default.
- default-models-expand-depth -1 hides the default model expansion section.
- display-request-duration displays the duration of Try it out requests.

These options affect how Swagger UI presents the documentation. They do not reduce the byte size of OpenAPI JSON/YAML and do not remove schemas or operations from the contract.

Property names and support may depend on the bundled springdoc/Swagger UI version. Verify them in the documentation for the exact version in use.

## 15. Enabling HTTP Compression for Documentation Endpoints

If the OpenAPI document is large yet must still be served in full, HTTP compression can reduce bytes transferred over the network. With Spring Boot, server compression can be enabled as follows:

~~~yaml
server:
  compression:
    enabled: true
    mime-types:
      - application/json
      - application/yaml
      - text/yaml
    min-response-size: 2KB
~~~

The MIME type list must match the Content-Type actually returned by the endpoint. Inspect response headers and use curl to confirm the server/proxy actually returns Content-Encoding: gzip when the client sends Accept-Encoding: gzip.

Compression reduces transfer payload, but the browser still must decompress and parse the document. It does not solve duplicated schemas, oversized examples, or a UI having to render too many operations.

If a reverse proxy or ingress already compresses responses, avoid configuring multiple layers that cause double compression. Choose one layer responsible for compression and measure the actual size.

## 16. Considering Caching and Static Documentation

If the OpenAPI document does not change per request, consider caching at a reverse proxy or serving a static file generated during release. This reduces repeated document generation and response overhead.

Before caching, determine:

- Does the document vary by Spring profile, tenant, or user?
- Does the docs endpoint require authentication?
- Are groups or server URLs built from forwarded headers?
- Does the cache key include the necessary host, path, and query?
- When a new version is released, is the cache invalidated?

Do not publicly cache a document containing private metadata or content varying by access rights. When using static documentation, tie the file to the commit/release and publish a versioned URL so consumers know which contract they are reading.

## 17. Setting a Size Budget in CI

Setting a size threshold helps detect abnormal document growth. Thresholds should be based on the project's baseline, realistic load, and consuming tool limits.

Bash example:

~~~bash
./gradlew generateOpenApiDocs

bytes=$(wc -c < build/openapi.json)
echo "OpenAPI raw size: $bytes bytes"

if [ "$bytes" -gt "$MAX_OPENAPI_BYTES" ]; then
  echo "OpenAPI document exceeds the configured size budget"
  exit 1
fi

gzip -c build/openapi.json > build/openapi.json.gz
gzip_bytes=$(wc -c < build/openapi.json.gz)
echo "OpenAPI gzip size: $gzip_bytes bytes"
~~~

MAX_OPENAPI_BYTES is a CI variable configured according to the project's budget. Do not take a sample value and treat it as a standard OpenAPI limit.

You can also track operation and schema counts:

~~~bash
operations=$(jq '[.paths[] | keys[] | select(
  . == "get" or . == "post" or . == "put" or
  . == "patch" or . == "delete" or . == "options" or
  . == "head" or . == "trace"
)] | length' build/openapi.json)

schemas=$(jq '(.components.schemas // {}) | length' build/openapi.json)

echo "Operations: $operations"
echo "Schemas: $schemas"
~~~

CI can warn when raw size or gzip size grows beyond allowed bounds. If metrics increase, generate a report or require a reviewer to identify the contributor before blocking merge. Do not automatically strip examples or descriptions just to force a green pipeline.

## 18. Linting Descriptions and Examples Against a Style Guide

Beyond a byte budget, lint rules or scripts can check:

- Summaries that are too long or not a short action phrase.
- Descriptions repeating identical content across many operations.
- Examples containing base64, tokens, or sensitive data.
- Examples that fail to parse as JSON or do not match the schema.
- Descriptions containing log excerpts, stack traces, or irrelevant content.
- Schemas not reused despite sharing the same semantics.
- Operations missing summaries or important response descriptions.

OpenAPI linting tools can support custom rules. Choose rules based on your team's style guide and avoid overly strict limits that leave documentation lacking essential information. A short but vague description can increase integration time even though the document is lighter.

## 19. Common Pitfalls When Optimizing

| Symptom | Cause | Resolution |
|---|---|---|
| Large JSON file despite few operations | Oversized examples or inline schemas | Measure contributors, trim examples, and reuse components |
| Swagger UI opens slowly despite small gzip size | High parse/render CPU or too many operations/schemas | Split groups and collapse UI expansion |
| Descriptions consume significant size | Copying long guides into every operation | Keep summaries, use External Documentation |
| Many nearly identical examples | Repeating payloads across operations | Reuse component examples or keep only distinct examples |
| Documentation missing fields after optimization | Using hidden=true or stripping schemas too broadly | Cross-check public contract and runtime responses |
| External example cannot be opened | Unstable URL or consumer does not resolve it | Version fixtures and verify UI/tool support |
| Compression does not reduce size | Mismatched MIME type or proxy compression disabled | Check Content-Type, Accept-Encoding, and Content-Encoding |
| Group document missing operations | Wrong path/package filters | Check GroupedOpenApi and group URL |
| File grows sharply after upgrading springdoc | Serializer or schema resolution changed | Review semantic diff, component count, and release notes |
| CI reports budget exceeded without clear reason | Only measuring total bytes | Store operation/schema metrics and report changes |

## 20. Step-by-Step Document Optimization Workflow

When an OpenAPI document exceeds its budget or Swagger UI loads slowly:

1. Regenerate the document from a defined profile and group.
2. Measure raw size and compressed size.
3. Count operations and schemas and inspect the diff against baseline.
4. Identify whether examples, descriptions, or schemas contribute most.
5. Trim examples to a single valid representative payload.
6. Move very large fixtures to externalValue or separate documentation where appropriate.
7. Reuse schemas/examples that share the same meaning.
8. Shorten descriptions and move long guides to externalDocs.
9. Split documents by bounded context if users do not need to load the entire API.
10. Configure UI expansion and HTTP compression if needed.
11. Run validators, semantic diffs, and contract tests to ensure no contract information is lost.
12. Update the budget after review; do not automatically raise thresholds for every increase.

After optimizing, re-verify the OpenAPI file and runtime responses. Smaller size is not the sole criterion; the document must still be sufficient for consumers to construct valid requests and understand responses.

## 21. Checklist for Keeping OpenAPI Documents Lightweight

- [ ] Measured raw size and compressed size.
- [ ] Identified profile, group, and commit that generated the snapshot.
- [ ] Examples illustrate typical payloads only and contain no production data.
- [ ] No base64 or large files embedded in examples unless necessary.
- [ ] Examples conform to schemas and parse cleanly.
- [ ] Shared examples are reused when beneficial.
- [ ] Descriptions are concise and do not duplicate schemas or long guides.
- [ ] Long guides are moved to External Documentation.
- [ ] Schema components are reused when contracts are genuinely identical.
- [ ] Public fields are not hidden solely to reduce byte size.
- [ ] API groups are divided along meaningful consumer boundaries.
- [ ] Swagger UI expansion is configured appropriately for document scale.
- [ ] Compression is verified via real response headers.
- [ ] Caching does not expose private documentation or serve stale versions.
- [ ] CI enforces a budget and reports explanations when size grows.
- [ ] Validators, semantic diffs, and runtime contract tests still PASS.

## 22. Conclusion

Keeping an OpenAPI document lightweight starts by measuring raw size, compressed size, and document structure. Use small yet valid examples, concise descriptions in the right places, shared schemas/examples where meaningful, externalValue for large fixtures, and External Documentation for long guides. When an application spans multiple API domains, split GroupedOpenApi by consumer needs; compression and UI expansion only optimize transfer or presentation without altering the contract. Set a budget in CI to catch abnormal growth while running validators, semantic diffs, and contract tests to ensure optimization never strips information clients need.
