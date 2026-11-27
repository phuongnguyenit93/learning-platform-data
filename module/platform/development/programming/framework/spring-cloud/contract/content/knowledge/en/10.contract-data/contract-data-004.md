# Bodies from JSON, XML, or Binary Resource Files

## 1. Why Load Bodies from Files?

When building **Spring Cloud Contract** suites, a contract between producer and consumer typically describes both the request conditions and the response the consumer expects. For small payloads, you can write the body inline in the Groovy or YAML DSL. However, if the payload is a long JSON invoice, an XML document with multiple namespaces, an image, a PDF, or a binary file, inline bodies become hard to read, hard to diff, and error-prone.

Spring Cloud Contract supports **loading body content from resource files**:

- For JSON, XML, and text data: Groovy uses `file('...')`; YAML uses `bodyFromFile`.
- For content that must remain intact as **raw bytes**: Groovy uses `fileAsBytes('...')`; YAML uses `bodyFromFileAsBytes`.

The key point is that the resource file is **read when the tooling processes the contract** to generate producer tests and stubs; it is not a path that the HTTP consumer reads on its own when calling the API. Therefore, the path must match the project containing the DSL, and the resource must be present during the build.

This lesson belongs to the **Contract Data** chapter of the `SPRING_CLOUD_CONTRACT` module. The goal is to author HTTP/messaging contracts with realistic bodies using Groovy/YAML DSL for producer test generation, stub packaging, Stub Runner execution, and detecting incompatible API changes in CI.

After this lesson, you will be able to:

1. Distinguish inline bodies, text-file-backed bodies, and binary-file-backed bodies.
2. Place fixture files at the right path relative to the contract file.
3. Write request/response examples using JSON files in both Groovy and YAML DSL.
4. Use XML files and XPath matchers to verify dynamic values.
5. Use PDF/image/byte-stream files in contracts without mistakenly converting them to Strings.
6. Diagnose missing files, wrong media types, encoding issues, stale fixtures, and mismatched stub contents.
7. Design a safe, versioned, and reproducible fixture management approach in CI.

> **Principle:** Choose the file reference mechanism based on the **actual data type of the body**, not on whether the file is long or short. JSON/XML are usually structured text content; PDFs, images, ZIPs, and other opaque data must be handled as bytes.

## 2. Four Ways to Declare a Body

| Case | Groovy DSL | YAML DSL | When to use |
| --- | --- | --- | --- |
| Body declared inline as structure | `body(orderId: 'ORD-123')` | `body:` with fields | Small, readable payloads |
| Body as an inline text string | `body('{"status":"PAID"}')` | `body: '{"status":"PAID"}'` | Short text or raw JSON |
| Body loaded from a text file | `body(file('response.json'))` | `bodyFromFile: response.json` | Large JSON, XML, or text |
| Body loaded from a binary file | `body(fileAsBytes('receipt.pdf'))` | `bodyFromFileAsBytes: receipt.pdf` | PDF, images, ZIP, byte streams |

`file(...)` and `fileAsBytes(...)` are Spring Cloud Contract DSL constructs. They are not `new File(...)` or `Files.readAllBytes(...)` calls that developers write manually.

For example, for a JSON response:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationJson())
    }
    body(file('order-response.json'))
}
~~~

This means: the contents of `order-response.json` are placed into the contract's **response body**.

For a PDF response:

~~~groovy
response {
    status OK()
    headers {
        header('Content-Type', 'application/pdf')
    }
    body(fileAsBytes('receipt.pdf'))
}
~~~

The second snippet keeps the body as **bytes**. Do not load a PDF via `file('receipt.pdf')` and treat it as text; text decoding can corrupt binary data.

### 2.1. A file-backed body is not returning a file path

These two declarations are not equivalent:

~~~groovy
// Sends the literal filename string in the HTTP body
body('receipt.pdf')
~~~

~~~groovy
// Sends the raw byte contents of the file
body(fileAsBytes('receipt.pdf'))
~~~

In the first example, the client receives the text `receipt.pdf` when passed as a literal. In the second example, the client receives the binary content embedded into the stub/verification according to the contract configuration.

### 2.2. Contract files and data files have distinct roles

The **contract file** defines the request, response, status, headers, and matching rules. The **data file** only supplies content for a specific body. Data placed in a contract does not by itself define all API behavior: the producer must still accept the agreed method/path and return the agreed status/headers.

## 3. Directory Layout and How Spring Cloud Contract Resolves Files

An illustrative layout for the `Order Service` producer:

~~~text
order-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── orders/
                    ├── create_order.groovy
                    ├── create-order-request.json
                    ├── create-order-response.json
                    ├── get_invoice.groovy
                    └── invoice-sample.pdf
~~~

If `create_order.groovy` contains:

~~~groovy
body(file('create-order-request.json'))
~~~

the filename is resolved **relative to the directory containing the contract**, i.e., `src/test/resources/contracts/orders/` in the layout above. It is not resolved relative to the current terminal working directory or Java package directory.

You can use a subdirectory for data files as long as the reference path is accurate:

~~~text
contracts/
└── orders/
    ├── create_order.groovy
    └── fixtures/
        ├── request.json
        └── response.json
~~~

Inside `create_order.groovy`:

~~~groovy
request {
    method 'POST'
    url '/api/orders'
    body(file('fixtures/request.json'))
}
~~~

**Never use an absolute path on one developer's machine**, such as `C:\Users\dev\Desktop\request.json`. CI and other teammates' machines will not have that path. Resources must be stored alongside contract sources or supplied deterministically by the build.

### 3.1. Fixture naming conventions

Maintainable practices:

- Use **behavior-oriented** names, such as `create-order-success-request.json` and `create-order-success-response.json`.
- Do not share a single fixture across scenarios with different business meanings just to save a few lines.
- When multiple contracts truly need the same payload, reusing a file is fine, but understand that editing the shared file affects **all** referencing contracts.
- Version files or organize under `v1`/`v2` directories when multiple wire formats are supported concurrently.
- Treat fixture files as part of the **committed interface**, requiring code review just like DSL files.

## 4. JSON Example: Using Files for Both Request and Response

Suppose the consumer sends a create-order command:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
~~~

### 4.1. Request JSON file contents

Sample file `create-order-request.json`:

~~~json
{
  "customerId": "CUS-7",
  "items": [
    {"sku": "BOOK-1", "quantity": 2, "unitPrice": 50000},
    {"sku": "PEN-3", "quantity": 1, "unitPrice": 10000}
  ],
  "note": "Deliver during business hours"
}
~~~

### 4.2. Response JSON file contents

Sample file `create-order-response.json`:

~~~json
{
  "orderId": "ORD-123",
  "status": "CREATED",
  "currency": "VND",
  "totalAmount": 110000,
  "accepted": true
}
~~~

Both payloads above are self-contained examples meant for **fixture files** in a hands-on project. In a real implementation, create the files at the paths agreed upon with the contract.

### 4.3. Groovy DSL file

`create_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('create_order_from_json_file')
    description('Consumer creates an order from JSON and receives an order ID')

    request {
        method 'POST'
        url '/api/orders'

        headers {
            contentType(applicationJson())
            accept(applicationJson())
        }

        body(file('create-order-request.json'))
    }

    response {
        status CREATED()

        headers {
            contentType(applicationJson())
        }

        body(file('create-order-response.json'))
    }
}
~~~

Here:

1. `request.body(file(...))` loads the JSON from the file into the **request** section of the contract; the stub uses this payload to determine request matching conditions per generated rules.
2. `response.body(file(...))` loads the JSON from the file into the **response** section; the generated producer test uses it as the expectation, and the stub serves it as the sample response to the consumer.
3. `Content-Type: application/json` and `Accept: application/json` are part of the HTTP agreement; a `.json` file extension does not add these headers automatically.
4. `status CREATED()` is HTTP `201`, independent of whether the body comes from a file or inline syntax.

Keep in mind: when the request body contains concrete values, the contract may match those values according to its generated configuration. If the consumer is allowed to send varying values, configure appropriate matchers or add dedicated scenarios; **loading a body from a file does not automatically make matching flexible**.

### 4.4. Equivalent YAML DSL configuration

To express the same interaction in YAML, use `bodyFromFile`:

~~~yaml
name: create_order_from_json_file
description: Consumer creates an order from JSON and receives an order ID
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
    Accept: application/json
  bodyFromFile: create-order-request.json
response:
  status: 201
  headers:
    Content-Type: application/json
  bodyFromFile: create-order-response.json
~~~

`bodyFromFile` belongs to `request` or `response` depending on indentation. The two fields share the same name yet serve opposite roles because they sit on **opposite communication directions**.

Do not use both `body` and `bodyFromFile` in the same request/response unintentionally: a single body should have a **single clear source of truth**. When you need to customize a few dynamic values, pair appropriate matchers with sample data rather than declaring conflicting bodies.

## 5. Why JSON from a File Still Needs Type and Structure Checks

These two files do not share the same schema:

~~~json
{"quantity": 2, "paid": true, "items": []}
~~~

~~~json
{"quantity": "2", "paid": "true", "items": {}}
~~~

The differences include:

- `quantity` changed from number to String.
- `paid` changed from boolean to String.
- `items` changed from empty array `[]` to empty object `{}`.

A strongly typed consumer expecting `int`, `boolean`, or `List<Item>` may fail to deserialize the second structure. Therefore, JSON fixtures must preserve **exact types and nesting levels**, not merely field names.

### 5.1. Dynamic values in JSON files

A sample JSON file might contain:

~~~json
{
  "orderId": "ORD-123",
  "status": "CREATED",
  "createdAt": "2026-11-24T02:00:00Z"
}
~~~

However, the real producer may generate a different `orderId` or `createdAt`. If the contract requires byte-for-byte literals, verification will fail on valid variations.

Spring Cloud Contract supports **response body matchers**. You can keep the sample body loaded from a file while declaring matchers for specific key fields:

~~~groovy
response {
    status CREATED()
    headers {
        contentType(applicationJson())
    }

    body(file('create-order-response.json'))

    bodyMatchers {
        jsonPath('$.orderId', byRegex('ORD-[0-9]+'))
        jsonPath('$.status', byEquality())
    }
}
~~~

This example assumes the file contains `orderId` and `status` as shown. `byRegex` checks the ID format; `byEquality` protects the committed business status.

If you add a matcher for `createdAt`, you **must update the fixture** to include that field and choose an appropriate temporal validation strategy. An overly broad matcher lets consumer-breaking changes slip through; an overly rigid matcher breaks tests on valid dynamic data.

### 5.2. A file-backed body does not automatically cover every array size

If the fixture contains two `items` elements, do not assume the generated test automatically verifies arbitrary array lengths. A contract protects only what the DSL and matchers are configured to verify. For variable-length collections, consider type matchers, element-count checks, required-field checks, or integration tests as needed.

### 5.3. File formatting and pre-commit checks

Before committing a fixture, verify:

- JSON is syntactically valid, with no trailing commas.
- Numbers, Booleans, Nulls, Strings, Objects, and Arrays have the right types.
- Currency units and timestamp formats are agreed upon.
- Which fields are required, optional, or allowed to be absent.
- Which values are stub sample data vs. unbreakable commitments.

**A larger fixture does not mean a better contract.** Structures should be clear enough for the consumer to understand and selective enough for the producer to evolve without breaking real expectations.

## 6. XML from Files: Preserving Structure, Namespaces, and Media Type

Some systems integrate with legacy enterprise applications, payment partners, or SOAP/XML endpoints. In XML, elements, attributes, namespaces, text nodes, and element order can all carry business meaning.

Example `invoice-request.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<InvoiceRequest>
  <OrderId>ORD-123</OrderId>
  <IncludeDetails>true</IncludeDetails>
</InvoiceRequest>
~~~

Example `invoice-response.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
  <InvoiceId>INV-777</InvoiceId>
  <OrderId>ORD-123</OrderId>
  <Currency>VND</Currency>
  <Amount>110000</Amount>
</Invoice>
~~~

### 6.1. Groovy DSL referencing XML files

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_invoice_from_xml_file')

    request {
        method 'POST'
        url '/api/invoices/lookup'

        headers {
            contentType(applicationXml())
            accept(applicationXml())
        }

        body(file('invoice-request.xml'))
    }

    response {
        status OK()

        headers {
            contentType(applicationXml())
        }

        body(file('invoice-response.xml'))
    }
}
~~~

Here `file(...)` is appropriate because XML is stored as **text**. Spring Cloud Contract supports HTTP XML bodies as `String` or `GString`, and supports XML verification via XPath matchers. When referencing a file, the DSL reads its text contents into the body.

### 6.2. Equivalent YAML DSL

~~~yaml
name: get_invoice_from_xml_file
request:
  method: POST
  url: /api/invoices/lookup
  headers:
    Content-Type: application/xml
    Accept: application/xml
  bodyFromFile: invoice-request.xml
response:
  status: 200
  headers:
    Content-Type: application/xml
  bodyFromFile: invoice-response.xml
~~~

Do not attach `application/json` out of habit from testing JSON APIs. An XML request/response must declare the media type both parties actually use, such as `application/xml` or an agreed custom XML media type.

### 6.3. Using XPath to handle dynamic XML values

If `InvoiceId` varies per run, you can declare matchers:

~~~groovy
response {
    status OK()
    headers {
        contentType(applicationXml())
    }

    body(file('invoice-response.xml'))

    bodyMatchers {
        xPath('/Invoice/InvoiceId/text()', byRegex('INV-[0-9]+'))
        xPath('/Invoice/Currency/text()', byEquality())
    }
}
~~~

Unlike JSONPath (`jsonPath`), XML uses **`xPath`**. Spring Cloud Contract provides XPath body matchers such as `byRegex` and `byEquality`, whereas `byType()` is not supported for XPath according to the reference documentation. Do not copy `byType()` from JSON examples into XML contracts.

**XPath with namespaces:** if the XML uses a default `xmlns` or prefixes, XPath expressions must handle namespaces explicitly or select nodes using `local-name()`/`namespace-uri()` appropriately. For instance, a plain `/Invoice/InvoiceId/text()` XPath will not automatically match if the actual elements belong to a namespace omitted from the expression.

### 6.4. Whitespace and encoding in XML

XML documents can differ in whitespace, line breaks, attribute ordering, and namespace prefixes while remaining semantically equivalent under XML parsing. Conversely, some elements contain text where whitespace is significant. Contracts should focus on the **semantics the consumer depends on**, using appropriate XPath matchers when byte-for-byte comparison is too brittle.

If the file declares `encoding="UTF-8"`, save it with the matching encoding. For XML using specialized charsets, carefully verify the build environment, charset headers, and real application deserialization.

## 7. Binary Bodies: PDF, Images, ZIP, and Byte Streams

Binary data is not a String. A PDF file contains raw bytes where decoding as UTF-8 can lose data or alter contents. That is why Spring Cloud Contract provides **file as bytes**.

### 7.1. Contract for downloading a PDF

Directory structure:

~~~text
src/test/resources/contracts/documents/
├── download_receipt.groovy
└── receipt-sample.pdf
~~~

File `download_receipt.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('download_receipt_pdf')

    request {
        method GET()
        url('/api/documents/DOC-7/pdf')

        headers {
            accept('application/pdf')
        }
    }

    response {
        status OK()

        headers {
            header('Content-Type', 'application/pdf')
            header('Content-Disposition',
                   'attachment; filename="receipt.pdf"')
        }

        body(fileAsBytes('receipt-sample.pdf'))
    }
}
~~~

Explanation:

- `fileAsBytes('receipt-sample.pdf')` is the crucial distinction: the tooling uses the **raw bytes of the file**, not treating the PDF as XML/JSON or text.
- `Content-Type: application/pdf` announces the actual media type.
- `Content-Disposition` illustrates a contract for the download filename; only constrain this if the consumer actually depends on that header.
- Never declare `application/json` for a PDF document.
- Binary contents usually require a small, deterministic fixture that can be committed and packaged in the build.

If a document is personalized per customer or stamped with a timestamp, **comparing the entire PDF byte-for-byte** may be too strict. Only use exact binary fixtures when byte identity is genuinely the commitment to enforce; if the requirement is “a valid document of the right type with the right business content”, combine an HTTP header contract with integration/domain tests that inspect PDF contents using a PDF library.

### 7.2. YAML DSL for PDF

~~~yaml
name: download_receipt_pdf
request:
  method: GET
  url: /api/documents/DOC-7/pdf
  headers:
    Accept: application/pdf
response:
  status: 200
  headers:
    Content-Type: application/pdf
    Content-Disposition: 'attachment; filename="receipt.pdf"'
  bodyFromFileAsBytes: receipt-sample.pdf
~~~

The `bodyFromFileAsBytes` field sits inside `response`, corresponding to Groovy's `body(fileAsBytes(...))`.

### 7.3. Binary upload in a request

An endpoint may accept a raw PDF upload as `application/pdf`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('upload_pdf_document')

    request {
        method POST()
        url('/api/documents')

        headers {
            header('Content-Type', 'application/pdf')
        }

        body(fileAsBytes('upload-sample.pdf'))
    }

    response {
        status CREATED()
    }
}
~~~

Equivalent YAML:

~~~yaml
name: upload_pdf_document
request:
  method: POST
  url: /api/documents
  headers:
    Content-Type: application/pdf
  bodyFromFileAsBytes: upload-sample.pdf
response:
  status: 201
~~~

**Note:** This is a **raw binary body** upload, not `multipart/form-data`. With multipart uploads, the body is wrapped in boundaries and part headers; use the appropriate multipart DSL/configuration rather than loading raw file bytes and treating them as the entire multipart envelope.

### 7.4. Is application/octet-stream mandatory?

No. `application/octet-stream` is a generic type for binary data, whereas `application/pdf`, `image/png`, or `application/zip` identify specific file formats. Choose the exact media type published by the API:

| Data | Typical header | Body declaration |
| --- | --- | --- |
| PDF | `application/pdf` | `fileAsBytes('receipt.pdf')` |
| PNG | `image/png` | `fileAsBytes('photo.png')` |
| ZIP | `application/zip` | `fileAsBytes('archive.zip')` |
| Unspecified byte stream | `application/octet-stream` | `fileAsBytes('payload.bin')` |
| JSON text | `application/json` | `file('response.json')` |
| XML text | `application/xml` | `file('response.xml')` |

A fixture file's extension **does not set headers automatically**; you must declare headers explicitly in the contract.

## 8. Comparing Text Files and Binary Files

| Criterion | `file(...)` / `bodyFromFile` | `fileAsBytes(...)` / `bodyFromFileAsBytes` |
| --- | --- | --- |
| Target data kind | Text content | Byte sequence |
| Typical files | JSON, XML, text | PDF, PNG, ZIP, bin |
| Structural matcher support | JSONPath or XPath when format matches | Cannot run JSONPath/XPath directly on opaque bytes |
| Risk if chosen wrongly | Can corrupt binary into garbled text | Loses structural checks for JSON/XML |
| Stub contents | Text/body from fixture | Binary payload from fixture |
| Use case | Testing APIs returning structured data | Testing APIs transferring/downloading files or opaque payloads |

**Quick rule of thumb:** If you can open the file and read it as a properly encoded JSON/XML/text document, usually use `file(...)`. If it is an image, PDF, ZIP, or a format not meant to be read as text, use `fileAsBytes(...)`.

Do not arbitrarily base64-encode binary data into a JSON body unless the **API actually defines base64 as a String field**. That is a different interface: the consumer then receives JSON/text containing base64 and decodes it itself, rather than receiving raw bytes.

## 9. File-Backed Bodies in Messaging Contracts

Spring Cloud Contract also supports messaging contracts. When `Payment Service` emits a `PaymentAuthorized` event, the payload may be large enough to extract into a JSON file.

Example message body from a file:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description('Publish payment authorized event')
    label 'paymentAuthorized'

    input {
        triggeredBy('publishAuthorizedPayment()')
    }

    outputMessage {
        sentTo('payments.authorized')

        headers {
            header('contentType', 'application/json')
        }

        body(file('payment-authorized.json'))
    }
}
~~~

Illustrative contents of `payment-authorized.json`:

~~~json
{
  "eventType": "PaymentAuthorized",
  "orderId": "ORD-123",
  "paymentId": "PAY-7",
  "currency": "VND",
  "amount": 110000
}
~~~

Producer verification for messaging still requires a base class providing the `publishAuthorizedPayment()` trigger and a configured message-observation mechanism. Having the JSON file alone does not guarantee the producer actually sends to the right destination or sets the right headers.

If the message payload is binary, Spring Cloud Contract allows using the corresponding file-as-bytes methods. However, binder, serializer, broker, and message verifier configuration must match your system. **Contract tests do not by themselves prove at-least-once delivery, retries, event ordering, or idempotency**; those properties require integration/resilience tests.

## 10. File-Backed Data, Versioning, and Consumer Contracts

A fixture file is part of the contract suite, not the “source of truth” for every producer entity. Editing this file changes what the producer test verifies and what the stub returns.

For example, suppose the producer changes:

~~~json
{
  "orderId": "ORD-123",
  "status": "PAID"
}
~~~

to:

~~~json
{
  "id": "ORD-123",
  "status": "PAID"
}
~~~

If consumers still read `orderId`, this change breaks the API. Never edit a fixture file merely to make generated tests pass while ignoring consumer impact.

### 10.1. Changes that typically require review

| Fixture change | Compatibility risk | How to handle |
| --- | --- | --- |
| Rename or remove a field read by consumer | High | Keep old field, coordinate migration, or introduce a new version |
| Change number to String | High when consumer is strongly typed | Align schema, update contract only with agreement |
| Add a new field ignored by consumer | Usually compatible | Confirm consumer parsers tolerate unknown fields |
| Change `items: []` to `items: null` | Can break processing branches | Review null/optional policy |
| Change XML namespace | High for namespace-aware XPath/serializers | Treat as an interface change and test consumers |
| Change downloaded file format from PDF to PNG | High if consumer expects PDF | Update media type and versioned contract |
| Update sample PDF with new timestamp but same semantics | Can cause false failures if compared byte-for-byte | Pick a deterministic fixture or test business content at another layer |
| Move file path without updating DSL | Build fails during test/stub generation | Move file and update references in the same commit |

### 10.2. Why fixtures must be committed to source control

Generated tests and stubs must be reproducible. If a contract references a file that exists only on the author's laptop, CI cannot build an equivalent contract.

A contract-related change should include all necessary parts:

1. Groovy/YAML DSL file.
2. JSON/XML/binary fixture files referenced by the DSL.
3. Compatible base test class and scenario setup data.
4. Producer code changes needed to satisfy the new behavior.
5. Consumer/stub verification if contract semantics changed.

Never commit real data containing personal information, tokens, or sensitive internal documents as fixtures. Create **synthetic data** with equivalent structure and strip unnecessary metadata.

### 10.3. Verify payloads when publishing stubs

The stub artifact consumed via Stub Runner must faithfully reflect the body the consumer will process. If the DSL references a PDF or JSON file that is missing from the stub generation/packaging step, consumer tests may lack the expected response. Inspect the generated artifact itself rather than only checking that the source file exists.

## 11. Common Issues with File-Backed Bodies

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Cannot find `response.json` | Wrong relative path, file not committed | Place file next to contract or fix relative path |
| Passes locally, fails on CI | Absolute path, case sensitivity, ignored file | Commit fixture to source control with consistent names/paths |
| Mismatched `Content-Type` | Header declares wrong body format | Use the agreed JSON/XML/PDF media type |
| Downloaded PDF/image is corrupted | Read binary via `file(...)` or handled as text | Use `fileAsBytes(...)` or `bodyFromFileAsBytes` |
| JSON fails to parse | Trailing comma, invalid quotes, wrong encoding | Fix sample JSON content |
| XML fails to parse | Malformed XML, namespace/encoding mismatch | Check XML document and producer serializer |
| XPath matcher finds no node | Wrong hierarchy or namespace | Adjust XPath to match actual XML |
| Generated test fails on random ID | Fixture uses overly strict fixed ID | Add meaningful matcher while keeping stub sample |
| Generated test fails on timestamp inside PDF | Binary fixture is not byte-identical across runs | Separate semantic checks from byte identity |
| Stub returns static response for all requests | Request matcher too broad while sample body is fixed | Tighten matcher, use response templating if appropriate, or add contracts |
| No tests generated | Plugin misconfigured, wrong contracts path | Check test generation step and executed test count |
| Editing one fixture breaks multiple contracts | Single file reused in many places | Check all referencing contracts; split fixtures if needed |
| Binary payload too large | Slow builds/stubs or bloated artifacts | Use the smallest fixture that still represents the commitment |
| Using binary DSL for multipart requests | Missing boundary/part metadata | Design a dedicated multipart contract |

### 11.1. Distinguishing fixture errors from compatibility regressions

If a producer test returns `404` because record `ORD-123` is missing from the test environment, the issue is likely fixture setup. If the test returns `200` but lacks the `orderId` field the consumer expects, it may be a breaking change.

Inspect in order:

1. Is the Contract DSL parsed and compiled?
2. Do all referenced files exist in the right locations?
3. Are the body fixtures valid in syntax, encoding, schema, and media type?
4. Does the generated request hit the intended endpoint with the right data state?
5. Where does the actual producer response/message differ?
6. Does the consumer depend on that difference?

Never edit generated test files directly to fix errors, as that code is regenerated from the DSL. The durable fix is to adjust the contract, fixture, base class/setup, or producer code according to cross-team compatibility decisions.

## 12. Integrating File-Backed Data into Producer Verification and CI

Typical integration flow:

~~~mermaid
flowchart TD
    DSL["Groovy/YAML contract"] --> GEN["Generate tests and stubs"]
    FIX["JSON/XML/PDF fixture"] --> GEN
    GEN --> TEST["Run producer verification"]
    TEST --> CHECK{"Producer behavior matches?"}
    CHECK -- "No" --> FAIL["Build fails; inspect contract/fixture/producer"]
    CHECK -- "Yes" --> PUBLISH["Package and publish versioned stub"]
    PUBLISH --> CONSUMER["Consumer tests via Stub Runner"]
~~~

In a Maven project configured with the Spring Cloud Contract plugin and base class:

~~~bash
./mvnw -B clean verify
~~~

In a Gradle project configured with the corresponding plugin and test task:

~~~bash
./gradlew clean build
~~~

These two commands are illustrative. They only verify contracts if **DSL files and fixtures are discovered, and generated tests are compiled and executed**. A green build that generated zero contract tests must be investigated.

### 12.1. Minimal CI workflow

- **Verify data sources:** declared `.json`, `.xml`, and `.pdf` files exist with exact casing and are included in the build.
- **Generate producer tests:** run the plugin and inspect logs for tests generated from contracts.
- **Execute producer verification:** confirm status, headers, and body match samples/matchers.
- **Package stubs:** publish artifacts only from producers that passed required verification.
- **Verify consumers:** run client tests via Stub Runner with the exact stub version, including binary downloads if that is part of the public interface.
- **Review breaking changes:** before accepting fixture updates, identify which consumers are impacted.

### 12.2. Verifying a stable binary response

For `GET /api/documents/DOC-7/pdf`:

- Contract tests can enforce `200`, `Content-Type`, and raw body bytes matching the fixture.
- Supplemental tests can check that the PDF opens cleanly and has the right page count or business metadata.
- If the PDF changes on every render (timestamp, internal object IDs, object ordering), exact byte fixtures may be unsuitable as the primary verification condition.

Thus, contracts protect the **file transfer interface**, while document generation logic and business correctness belong in the appropriate test layer.

## 13. Practice: A Service Returning JSON, XML, and PDF

Suppose `Document Service` exposes three independent endpoints:

| Endpoint | Expectation | Fixture files |
| --- | --- | --- |
| `POST /api/documents` | Accepts JSON metadata, returns `201` and JSON ID | `create-request.json`, `create-response.json` |
| `GET /api/documents/DOC-7/metadata.xml` | Returns XML metadata, `200` | `metadata-response.xml` |
| `GET /api/documents/DOC-7/file` | Returns raw PDF, `200` | `document-sample.pdf` |

### 13.1. Requirement A — Prepare files

In your practice project, create:

~~~text
src/test/resources/contracts/documents/
├── create_document.groovy
├── create-request.json
├── create-response.json
├── get_document_metadata.groovy
├── metadata-response.xml
├── download_document.groovy
└── document-sample.pdf
~~~

Sample content for `create-request.json`:

~~~json
{
  "title": "Purchase order",
  "customerId": "CUS-7",
  "format": "PDF"
}
~~~

Sample content for `create-response.json`:

~~~json
{
  "documentId": "DOC-7",
  "status": "CREATED"
}
~~~

Contents of `metadata-response.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Document>
  <DocumentId>DOC-7</DocumentId>
  <Format>PDF</Format>
  <Status>READY</Status>
</Document>
~~~

`document-sample.pdf` must be a **real PDF file**, created by your team for testing. Do not put plain text like “PDF test” into a `.pdf` file and assume it is a valid PDF document.

### 13.2. Requirement B — Write three contracts

- Document creation contract: declare `body(file('create-request.json'))` and `body(file('create-response.json'))`.
- XML contract: response header `application/xml` and `body(file('metadata-response.xml'))`.
- PDF contract: response header `application/pdf` and `body(fileAsBytes('document-sample.pdf'))`.

Each contract needs its own name, method, URL, and appropriate status.

### 13.3. Suggested XML contract

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('document_metadata_xml')

    request {
        method GET()
        url('/api/documents/DOC-7/metadata.xml')
    }

    response {
        status OK()
        headers {
            contentType(applicationXml())
        }
        body(file('metadata-response.xml'))
        bodyMatchers {
            xPath('/Document/DocumentId/text()', byEquality())
        }
    }
}
~~~

### 13.4. Suggested PDF contract

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('document_pdf_download')

    request {
        method GET()
        url('/api/documents/DOC-7/file')
        headers {
            accept('application/pdf')
        }
    }

    response {
        status OK()
        headers {
            header('Content-Type', 'application/pdf')
        }
        body(fileAsBytes('document-sample.pdf'))
    }
}
~~~

### 13.5. Breaking-change drill

Run producer verification for the authored contracts, then test these mutations one by one:

1. Rename JSON response field `documentId` to `id` while the consumer still expects `documentId`.
2. Rename XML node `<DocumentId>` to `<Id>` while the contract XPath stays unchanged.
3. Change the PDF `Content-Type` to `application/json`.
4. Replace the PDF with plain text while keeping the `.pdf` extension.
5. Change `fileAsBytes('document-sample.pdf')` to a non-existent filename.

Record at which stage each failure occurs: contract parsing, test generation, producer verification, or consumer stub test. For mutation 4, **detection depends on matchers/fixtures and supplemental checks**; if the bytes are wrong yet the contract criteria do not validate PDF validity, add appropriate tests rather than assuming contract tests cover everything.

### 13.6. Self-assessment questions

1. Why must you use `fileAsBytes(...)` for a PDF instead of `file(...)`?
2. For what kinds of data do `bodyFromFile` and `bodyFromFileAsBytes` differ?
3. What error can happen if an XML file uses a namespace prefix that differs from an XPath written without namespace awareness?
4. If the producer returns a random ID, how should you write the fixture and matcher?
5. If one JSON file is referenced by 5 contracts, how many contracts are affected by editing that file?
6. Why can running only Stub Runner without producer verification miss a producer that breaks the API?
7. Why can a PDF response from a small fixture be a better example than committing a 50 MB report?

**Answer hints:** Binary data requires preserving exact bytes; JSON/XML are structured text; XPath must match namespaces; dynamic data needs a stable sample plus a matcher; shared fixtures affect every referencing contract; stubs only simulate what was declared; small, deterministic fixtures keep CI fast and easy to review.

## 14. Checklist Before Finalizing a File-Backed Contract

- [ ] Determined whether the body is **text** (JSON/XML) or **binary** (PDF/image/ZIP).
- [ ] Groovy uses `file(...)` or `fileAsBytes(...)` for its intended purpose.
- [ ] YAML uses `bodyFromFile` or `bodyFromFileAsBytes` in the right `request`/`response` section.
- [ ] Fixture files sit at a path relative to the **directory containing the contract**.
- [ ] No machine-specific absolute paths are used.
- [ ] Files exist in source control and CI with exact case-sensitive filenames.
- [ ] HTTP method, URL, status, `Content-Type`, and `Accept` match the real interface.
- [ ] JSON and XML fixtures are valid in syntax and encoding.
- [ ] JSONPath/XPath matchers check only what the consumer needs and account for dynamic data.
- [ ] For namespaced XML, XPath expressions handle namespaces properly.
- [ ] For binary payloads, sample data is deterministic, small, and in the real format.
- [ ] Raw binary uploads are not confused with `multipart/form-data`.
- [ ] No sensitive info or real customer data is placed in fixtures.
- [ ] Generated producer tests are generated **and executed**; builds fail on contract-protected breaking changes.
- [ ] Stubs are packaged from verified producers and consumed at the right version via Stub Runner.
- [ ] Properties outside contract test scope (PDF content quality, broker retries, deep business logic) have supplemental tests.

## 15. References

- [Spring Cloud Contract — Common Top-Level Elements, Passing Values from Files](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/common-top-elements.html): `file(...)`, `bodyFromFile`, `fileAsBytes(...)`, `bodyFromFileAsBytes`, and relative path rules.
- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): HTTP body declarations, headers, XML bodies, XPath matchers, and namespaces.
- [Spring Cloud Contract — Contract DSL Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matchers and producer/consumer value differences.
- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): test generation configuration, stub management, and build lifecycle integration.

**Takeaway:** **File-backed bodies** keep contracts focused on communication behavior instead of stuffing huge payloads inline into the DSL. Use `file(...)`/`bodyFromFile` for JSON, XML, and text; use `fileAsBytes(...)`/`bodyFromFileAsBytes` for binary data. Keep fixtures at relative paths, versioned, with accurate media types and matchers where needed; run producer verification and publish stubs in CI to protect consumers from incompatible API changes.
