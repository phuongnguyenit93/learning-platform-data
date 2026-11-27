# Verifying Multipart Requests and Non-JSON Responses

## Learning Objectives

In **Spring Cloud Contract**, HTTP contracts written in **Groovy DSL** or **YAML DSL** align behavior between a **producer** (the service providing an API) and a **consumer** (the service calling the API). From contracts, the tool generates **producer contract tests** to verify the implementation and **stubs** for consumers to run with **Stub Runner**. When wired into CI, teams catch incompatible interface changes before deployment.

Within the **HTTP Testing** chapter, this lesson focuses on two scenarios that are typically trickier than `application/json`:

1. **`multipart/form-data` requests:** a multi-part body that may carry text fields, filenames, and file contents.
2. **Non-JSON responses:** the producer returns `text/plain`, XML, or raw file bytes instead of a JSON object.

After this lesson, you will be able to:

- Distinguish **part name**, **filename**, **per-part Content-Type**, and **boundary** in multipart payloads.
- Write a Groovy contract for a multipart request and text response, and understand what generated producer tests and stub mappings must verify.
- Express `text/plain`, `application/xml`, and `application/octet-stream`/`application/pdf` responses in appropriate Groovy or YAML DSL.
- Choose between **exact matching**, **XPath matchers**, or **byte-level matching** per the committed interface.
- Test error cases such as missing parts, unsupported MIME types, and empty responses.
- Separate **contract testing boundaries** from tests for streaming, payload size limits, security, networking, and real file storage.
- Build a reliable producer tests → stub artifact → Stub Runner consumer tests → CI workflow.

## 1. Running Example: Uploading Evidence and Downloading a Receipt

Suppose **Document Service** is the producer and **Checkout Service** is the consumer. Checkout needs to attach delivery evidence, then read the stored result or download a receipt.

An illustrative API design:

| Interaction | HTTP request | Request body | Success response |
|---|---|---|---|
| Upload evidence | `POST /api/attachments` | `multipart/form-data` containing `category` and `file` | `201 Created` with ID as `text/plain` |
| Read receipt | `GET /api/attachments/ATT-101/receipt` | No body | `200 OK` with XML |
| Download file content | `GET /api/attachments/ATT-101/content` | No body | `200 OK` with `application/octet-stream` bytes |
| Check upload error | `POST /api/attachments` missing `file` | Business-invalid multipart | `400 Bad Request` with text error code if API publishes one |

These are **illustrative conventions**, not Spring Cloud Contract default endpoints. In a real project, statuses, MIME types, file limits, and response shapes must be agreed upon by producer and consumer.

### Overall Verification Flow

~~~mermaid
flowchart LR
    C["Groovy/YAML contract"] --> G["Generate producer test"]
    C --> M["Generate stub mapping"]
    F["Test data + real controller/app"] --> G
    G --> P["Producer contract test"]
    M --> A["Stub artifact"]
    A --> R["Stub Runner"]
    R --> U["Consumer test with real HTTP client"]
    P --> CI["CI: verify exact revision"]
    U --> CI
~~~

Remember: **producer contract tests** verify that the real producer responds per the contract; **consumer tests** with Stub Runner verify that the consumer sends valid requests and handles simulated responses per the contract. Both results complement rather than replace each other.

## 2. Multipart Is a Collection of Parts, Not a JSON Body

With `multipart/form-data`, the body is split into parts using a **boundary**. Each part has its own headers and content.

Illustrative request:

~~~http
POST /api/attachments HTTP/1.1
Content-Type: multipart/form-data; boundary=AaB03x
Accept: text/plain

--AaB03x
Content-Disposition: form-data; name="category"

receipt
--AaB03x
Content-Disposition: form-data; name="file"; filename="proof.txt"
Content-Type: text/plain

signed by recipient
--AaB03x--
~~~

Here:

- The outer `Content-Type` header identifies the request as multipart and declares `boundary=AaB03x`.
- Part `category` is a text field with value `receipt`.
- Part `file` has **field name** `file`; its `filename` is `proof.txt`.
- The Content-Type of the **file part** is `text/plain`, which is distinct from the Content-Type of the **entire request**.
- The file part's body is the bytes of the string `signed by recipient`.

The example uses a text file for readability. For PDFs or images, the file part contains bytes not displayable in Markdown.

### Four Easy-to-Confuse Concepts

| Concept | Example | What happens if wrong? |
|---|---|---|
| **Part name** | `file` | Controller reading `@RequestPart("file")` may report a missing part |
| **Filename** | `proof.txt` | File metadata is wrong; naming or file-type rules may fail |
| **Part MIME type** | `text/plain` | Producer may reject or mis-decode the part's data |
| **Boundary** | `AaB03x` | Parser cannot split the body properly if header and body disagree |

**Boundary is not a business field.** HTTP clients normally generate a fresh boundary on each multipart request. Never turn a random boundary string into a fixed API commitment. If a test or stub accidentally hard-codes the boundary, valid multipart requests created by another HTTP client may fail to match.

### Multipart vs. Raw Binary Upload

The following two requests are not equivalent:

~~~http
PUT /api/attachments/ATT-101/content HTTP/1.1
Content-Type: application/octet-stream

<raw file bytes>
~~~

~~~http
POST /api/attachments HTTP/1.1
Content-Type: multipart/form-data; boundary=...

<one or more multipart parts>
~~~

The line `<raw file bytes>` illustrates the concept, not literal characters sent over the wire. **Raw binary** places the file's bytes directly in the HTTP body; **multipart** wraps one or more parts with metadata. Switching from one format to the other is a **breaking request contract change**, even though both are called "file upload."

## 3. Writing a Multipart Contract in Groovy DSL

Suppose the producer returns an ID string after accepting the upload:

~~~http
HTTP/1.1 201 Created
Content-Type: text/plain;charset=UTF-8
Location: /api/attachments/ATT-101

ATT-101
~~~

An illustrative Groovy contract at `src/test/resources/contracts/attachments/uploadTextFile.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Upload multipart evidence and return text ID'

    request {
        method 'POST'
        url '/api/attachments'

        headers {
            contentType('multipart/form-data;boundary=AaB03x')
            accept('text/plain')
        }

        multipart(
            category: 'receipt',
            file: named(
                name: 'proof.txt',
                content: 'signed by recipient',
                contentType: 'text/plain'
            )
        )
    }

    response {
        status 201
        headers {
            contentType('text/plain;charset=UTF-8')
            header('Location', '/api/attachments/ATT-101')
        }
        body('ATT-101')
    }
}
~~~

In Groovy DSL, `multipart(...)` describes form parts; `named(...)` describes a file part with filename, content, and MIME type. This is a **small fixture** for verifying communication, not a real PDF file. The example uses an explicit boundary to explain the wire format and verify request generation; when applying this in practice, inspect the **actual generated test and mapping** to confirm header matching does not hard-code the boundary when clients may vary it.

### Reading Each Component Properly

| DSL | Described data | What to verify |
|---|---|---|
| `method 'POST'` | HTTP method | Test sends `POST`; stub does not mistakenly match `GET` |
| `url '/api/attachments'` | Request path | Path or context path is not unintentionally altered |
| `contentType('multipart/form-data;boundary=...')` | Overall request MIME | Right boundary for generated request; stub matches valid requests |
| `category: 'receipt'` | Form field | Part is sent and received by controller under the exact name |
| `file: named(...)` | File part | Field `file`, filename, part MIME, and content |
| `response.status 201` | HTTP status | Producer does not silently switch to `200` |
| `Location` | URI of newly created file | Producer/consumer agree on URI per interface |
| `body('ATT-101')` | Raw response string | Consumer receives **plain text**, not a JSON string |

You can keep the filename fixed because a fixture targets a specific case. If consumers need to send varying filenames, design appropriate matchers and add consumer tests for those variants. Never assume a single fixture proves every filename or file type is supported.

### Note on YAML DSL for Multipart

Spring Cloud Contract also supports YAML DSL; however, **multipart matcher/file part** structures in YAML are not written by copying Groovy's `multipart(...)` and `named(...)` functions verbatim into YAML. Use the YAML schema **matching your project's Spring Cloud Contract version** when declaring multipart. In this lesson, Groovy is chosen to present multipart most clearly; the YAML examples below focus on **non-JSON responses**, where the body can be expressed directly as a string or file.

Never keep two contracts for the same request just to "have both Groovy and YAML" if doing so produces overlapping stub mappings.

## 4. What Must the Producer Set Up to Test Multipart?

An accurate contract is not enough if **generated tests fail to reach the right controller**. Example Spring MVC producer with a real controller accepting a form field and a file part:

~~~java
package com.example.document;

import java.io.IOException;
import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class AttachmentController {

    private final AttachmentService service;

    public AttachmentController(AttachmentService service) {
        this.service = service;
    }

    @PostMapping(
        path = "/api/attachments",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<String> upload(
            @RequestParam("category") String category,
            @RequestPart("file") MultipartFile file) throws IOException {

        String id = service.save(
            category,
            file.getOriginalFilename(),
            file.getContentType(),
            file.getBytes()
        );

        return ResponseEntity
            .created(URI.create("/api/attachments/" + id))
            .contentType(MediaType.parseMediaType("text/plain;charset=UTF-8"))
            .body(id);
    }
}
~~~

`AttachmentService` is a project-defined interface, for example:

~~~java
package com.example.document;

public interface AttachmentService {
    String save(
        String category,
        String filename,
        String contentType,
        byte[] content
    );
}
~~~

The code above illustrates the **real controller** that generated tests must verify; it is not a complete application. In production, the service must authenticate, enforce size limits, validate MIME/content, and store files safely. In tests, a deterministic fake service can return ID `ATT-101`.

### Base Test Class with MockMvc

Suppose the Maven/Gradle plugin is configured to generate tests in `MOCKMVC` mode extending `com.example.document.contract.DocumentContractBase`:

~~~java
package com.example.document.contract;

import com.example.document.AttachmentController;
import com.example.document.AttachmentService;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;

import java.nio.charset.StandardCharsets;

public abstract class DocumentContractBase {

    @BeforeEach
    protected void setUp() {
        AttachmentService fake = (category, filename, type, bytes) -> {
            if (!"receipt".equals(category)
                    || !"proof.txt".equals(filename)
                    || !"text/plain".equals(type)
                    || !"signed by recipient".equals(
                            new String(bytes, StandardCharsets.UTF_8))) {
                throw new IllegalArgumentException("Unexpected fixture");
            }

            return "ATT-101";
        };

        RestAssuredMockMvc.standaloneSetup(
            new AttachmentController(fake)
        );
    }
}
~~~

This class wires the **real controller** with a fake `AttachmentService` and attaches it to RestAssuredMockMvc. If the generated test sends the wrong form field, filename, or content, the fake logic or controller fails to satisfy the contract. Thus, fixture data must **match exactly** the data generated from the contract.

**However, there are limits:** a fake service does not prove real file storage code works, nor does it test streaming or virus scanning. If the application uses validators, filters, security, `@ControllerAdvice`, or custom converters, `standaloneSetup` may not initialize those components. When you need to verify them, consider `WebApplicationContext`, a full Spring Boot test, or an integration test with a real server.

### Do You Need a Separate Multipart Unit/Integration Test?

Yes, when consumers need guarantees around **bytes, metadata, size limits, or parsing errors**. Beyond generated contract tests, a controller test can use Spring MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class AttachmentControllerTest {

    private MockMvc mockMvc; // Created in project setup.

    @Test
    void acceptsExpectedMultipartParts() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
            "file", "proof.txt", "text/plain",
            "signed by recipient".getBytes(java.nio.charset.StandardCharsets.UTF_8)
        );

        mockMvc.perform(multipart("/api/attachments")
                .file(file)
                .param("category", "receipt")
                .accept(MediaType.TEXT_PLAIN))
            .andExpect(status().isCreated())
            .andExpect(content().string("ATT-101"))
            .andExpect(header().string("Location", "/api/attachments/ATT-101"));
    }
}
~~~

This is an **illustrative template requiring `mockMvc`, controller, and fake service setup before running**; it is not a complete test class. Such tests are useful for debugging when generated producer tests fail over form fields or serialization, yet must not replace generated contract tests in the pipeline.

## 5. `text/plain` Responses: Do Not Turn Strings into JSON

A common mistake is thinking every text-looking response body is JSON. The following two responses **differ on the wire**:

~~~http
HTTP/1.1 201 Created
Content-Type: text/plain;charset=UTF-8

ATT-101
~~~

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

"ATT-101"
~~~

In the first case, the body is the UTF-8 bytes of `ATT-101`. In the second case, the body is a **JSON string**, including the JSON quotation marks. A consumer reading raw text can break if the producer switches to a JSON string.

### Groovy DSL

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Return attachment code as text'

    request {
        method 'GET'
        url '/api/attachments/ATT-101/id'
    }

    response {
        status 200
        headers {
            contentType('text/plain;charset=UTF-8')
        }
        body('ATT-101')
    }
}
~~~

### Equivalent YAML DSL

~~~yaml
description: 'Return attachment code as text'
request:
  method: GET
  url: '/api/attachments/ATT-101/id'
response:
  status: 200
  headers:
    Content-Type: 'text/plain;charset=UTF-8'
  body: 'ATT-101'
~~~

Both representations target a **raw text response**. Pick one of the two contracts per scenario in your build.

### What to Verify?

- Accurate status, such as `200` or `201` per the interface.
- Accurate text `Content-Type`, including charset if committed.
- Body is the right plain string without added JSON quotes.
- No trailing newline/whitespace if the interface specifies a verbatim string.
- Consumer decodes UTF-8 properly, especially for accented text or non-ASCII characters.

For dynamic values (like a newly generated ID each call), use a **response matcher** so generated producer tests check a pattern (`ATT-[0-9]+`) while stubs return a fixed `ATT-101`. Matchers must match the committed format; if the consumer depends on an exact literal body, never use an overly broad regex like `.*`.

### Multi-Line Responses

For plain-text reports or CSV, YAML block scalars can represent newlines:

~~~yaml
response:
  status: 200
  headers:
    Content-Type: 'text/plain;charset=UTF-8'
  body: |-
    Order: ORD-101
    Status: ACCEPTED
~~~

`|-` preserves the newline between the two lines while stripping the trailing newline. `|` handles trailing newlines differently. For text responses, even a single trailing newline byte difference can fail strict-equality assertions; choose based on the real interface, not YAML formatting habits.

## 6. XML Responses: Verify Content with XML, Not JSONPath

Suppose Checkout fetches the receipt:

~~~http
GET /api/attachments/ATT-101/receipt HTTP/1.1
Accept: application/xml
~~~

Producer returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/xml;charset=UTF-8

<receipt>
  <attachmentId>ATT-101</attachmentId>
  <status>STORED</status>
  <createdAt>2026-01-15T08:30:00Z</createdAt>
</receipt>
~~~

In XML:

- `<attachmentId>` content is a text node.
- `<status>` carries business meaning; consumers may branch on `STORED`.
- `createdAt` can vary, yet its format must remain stable.
- If XML namespaces exist, XPath expressions must account for those namespaces.

### Groovy DSL with XPath Matchers

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Return stored XML receipt'

    request {
        method 'GET'
        url '/api/attachments/ATT-101/receipt'
        headers {
            accept('application/xml')
        }
    }

    response {
        status 200
        headers {
            contentType('application/xml;charset=UTF-8')
        }
        body('''<receipt>
  <attachmentId>ATT-101</attachmentId>
  <status>STORED</status>
  <createdAt>2026-01-15T08:30:00Z</createdAt>
</receipt>''')

        bodyMatchers {
            xPath('/receipt/attachmentId/text()', byRegex('ATT-[0-9]+'))
            xPath('/receipt/status/text()', byRegex('STORED'))
            xPath('/receipt/createdAt/text()',
                byRegex('[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'))
        }
    }
}
~~~

`body` is an **XML string**; `xPath(...)` lists the nodes to verify. XPath matching works well when the producer may change indentation or formatting without **altering XML semantics**. However, a regex timestamp matcher only checks **shape**—it does not prove every calendar date/time is valid.

In this contract, the fixed sample XML can still be used to produce stubs for consumers. Generated producer tests should verify the declared XPath rules rather than forcing the producer to match exact whitespace and the sample timestamp. Inspect your plugin version's actual generated tests to confirm.

### YAML DSL: XML Body with Block Scalar and Matchers

~~~yaml
description: 'Return stored XML receipt'
request:
  method: GET
  url: '/api/attachments/ATT-101/receipt'
  headers:
    Accept: 'application/xml'
response:
  status: 200
  headers:
    Content-Type: 'application/xml;charset=UTF-8'
  body: |-
    <receipt>
      <attachmentId>ATT-101</attachmentId>
      <status>STORED</status>
      <createdAt>2026-01-15T08:30:00Z</createdAt>
    </receipt>
  matchers:
    body:
      - path: '/receipt/attachmentId/text()'
        type: by_regex
        value: 'ATT-[0-9]+'
      - path: '/receipt/status/text()'
        type: by_regex
        value: 'STORED'
~~~

YAML `body: |-` produces an XML string; `matchers.body` declares the XPaths generated tests must verify. Only two matchers are shown here for illustration; if consumers tightly depend on `createdAt` format, add a matching matcher or test.

### XML Namespaces, Encoding, and Common Pitfalls

A response may use namespaces:

~~~xml
<r:receipt xmlns:r="urn:example:receipt">
  <r:attachmentId>ATT-101</r:attachmentId>
</r:receipt>
~~~

The XPath `/receipt/attachmentId/text()` in the earlier example **will not automatically match** a document with this namespace. When designing contracts, use namespace-aware XPath or `local-name()` / `namespace-uri()` techniques appropriately; never strip namespaces from XML fixtures just to make tests pass.

Other points to verify:

1. Does the XML match the API's expected element and attribute structure?
2. Is `Content-Type` `application/xml` or another agreed media type?
3. Do the actual bytes use a charset matching the header and XML declaration?
4. When responses have dynamic parts, are matchers sufficiently strict?
5. If the consumer validates XML digital signatures, would whitespace/canonicalization changes affect it?

**Never use JSONPath for XML.** When you need to check XSDs, signatures, schemas, or cross-node business rules, add schema/integration tests; a handful of XPath matchers do not prove an entire document is valid.

## 7. Binary Responses: Match Bytes Instead of Text

Suppose the consumer downloads file content:

~~~http
GET /api/attachments/ATT-101/content HTTP/1.1
Accept: application/octet-stream
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="proof.bin"

<raw original file bytes>
~~~

The text inside `<...>` is illustrative only: the real body is **bytes**, not a character string sent over the wire. If the producer returns a PDF, use `application/pdf`; if PNG, use `image/png`. Pick the MIME type matching the committed interface.

### Groovy DSL: `fileAsBytes(...)`

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Download attachment content as bytes'

    request {
        method 'GET'
        url '/api/attachments/ATT-101/content'
    }

    response {
        status 200
        headers {
            contentType(applicationOctetStream())
            header('Content-Disposition',
                'attachment; filename="proof.bin"')
        }
        body(fileAsBytes('proof.bin'))
    }
}
~~~

`fileAsBytes('proof.bin')` tells Spring Cloud Contract to read **bytes from the fixture file** instead of reading it as text. The file must actually exist in the resource folder referenced by the contract, for example:

~~~text
src/test/resources/contracts/attachments/
├── downloadContent.groovy
└── proof.bin
~~~

In this study guide, paths are examples for readers to **create in their practice project**; this Markdown lesson itself does not generate binary files.

### YAML DSL: `bodyFromFileAsBytes`

~~~yaml
description: 'Download attachment content as bytes'
request:
  method: GET
  url: '/api/attachments/ATT-101/content'
response:
  status: 200
  headers:
    Content-Type: 'application/octet-stream'
    Content-Disposition: 'attachment; filename="proof.bin"'
  bodyFromFileAsBytes: 'proof.bin'
~~~

For this YAML, place `proof.bin` at a relative path readable by the tool. Key distinction:

| Purpose | Groovy | YAML | Scope |
|---|---|---|---|
| **Text** file content | `body(file('receipt.xml'))` | `bodyFromFile: 'receipt.xml'` | XML, text, JSON |
| **Binary** file content | `body(fileAsBytes('proof.bin'))` | `bodyFromFileAsBytes: 'proof.bin'` | Raw bytes not coerced into String |

Never use `bodyFromFile` for binary files assuming every byte stays intact; text processing can alter encodings or corrupt data. For binary payloads, verify generated tests, stub mappings/responses, and the actual bytes received by the consumer.

### Assertions Recommended for Binary Responses

If the interface guarantees **byte-for-byte** equivalence, verify by comparing the byte array against the fixture or computing a byte checksum. If the interface only commits to **a valid format** rather than an identical static file, tests should verify meaningful properties such as:

- Valid `Content-Type`.
- `Content-Disposition` and filename if the consumer depends on them.
- Body contains valid format bytes/headers (e.g., PDF magic bytes).
- Content can be read/decoded by an appropriate parser.
- Published hashes/checksums or metadata match the received bytes.

Do not force a producer to return an identical PDF byte stream when internal timestamps/metadata vary unless the interface promises byte-for-byte determinism. For large files, write dedicated streaming and memory tests instead of stuffing tens of megabytes into contract fixtures.

## 8. Empty and Error Responses: Do Not Conflate Scenarios

Non-JSON responses do not mean **status** and **shape** can be ignored.

| Scenario | Example response | Meaning |
|---|---|---|
| Create evidence, return text ID | `201` + `text/plain` body `ATT-101` | Response body is a string |
| Create evidence, no body | `201` with `Location` header, no body | Client reads URI from header |
| Delete succeeds | `204 No Content` | No response body |
| ID does not exist | `404` + error body per API policy | Resource error |
| Unsupported upload MIME | `415 Unsupported Media Type` | Consumer must change upload format |
| Multipart missing part | `400 Bad Request` or API-defined code | Request violates published rule |
| Upload exceeds limit | `413 Content Too Large` | Size limit exceeded; do not blindly retry identical payload |
| Storage infra error | `503` or API-defined choice | Transient failure, distinct from not found |

These are **reference design choices**; exact status codes and error bodies must be agreed upon. Never assume Spring Cloud Contract picks `400` vs. `415` on behalf of your application.

### Multipart Error Contract: Missing `file` Part

A scenario to verify if consumers depend on it:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Multipart missing file is rejected'

    request {
        method 'POST'
        url '/api/attachments'
        headers {
            contentType('multipart/form-data;boundary=AaB03x')
        }
        multipart(
            category: 'receipt'
        )
    }

    response {
        status 400
        headers {
            contentType('text/plain;charset=UTF-8')
        }
        body('FILE_PART_REQUIRED')
    }
}
~~~

This scenario assumes the producer returns a deterministic error when `file` is missing. In Spring MVC, binding errors may be mapped by the framework to a default status; to return the exact body `FILE_PART_REQUIRED`, the app may need `@ControllerAdvice`. The base test must configure that exception handler; otherwise, generated tests will observe a different error body.

### `204` Has No Body

~~~yaml
description: 'Delete attachment succeeds'
request:
  method: DELETE
  url: '/api/attachments/ATT-101'
response:
  status: 204
~~~

Do not add `body: ''` or JSON `null` just to "fill in the blank." `204 No Content` and `200 OK` with an empty body are two distinct interfaces. Consumer tests must differentiate them whenever application logic relies on specific behavior.

## 9. Verifying What Generated Producer Tests Actually Check

Once Spring Cloud Contract Verifier and the appropriate plugin are configured, generated tests typically appear in:

~~~text
Maven:
  target/generated-test-sources/contracts/

Gradle:
  build/generated-test-sources/contracts/
~~~

Exact class names, test frameworks, assertion syntax, and output paths depend on plugin version and configuration; check **build logs** if paths differ.

For the multipart → `201 text/plain` contract, a reviewer should inspect the generated test file and confirm:

1. The request actually uses `POST /api/attachments`.
2. `Content-Type` header and **multipart parts** are built properly, including `category`, field name `file`, filename, and content bytes.
3. The request hits the **real producer controller/application in the test environment**, not a stub.
4. The response assertion checks `201`.
5. `Content-Type` header is `text/plain` per convention and `Location` matches.
6. The body assertion treats `ATT-101` as a **raw string** rather than parsing it as a JSON object.
7. The test **executed**, not skipped or missed by the test runner.

A condensed description of the expected generated test (**pseudocode**, not guaranteed verbatim generator output):

~~~text
GIVEN producer base test has registered AttachmentController

WHEN
  POST /api/attachments with multipart/form-data
  part category = "receipt"
  part file:
    filename = "proof.txt"
    content-type = "text/plain"
    content = bytes("signed by recipient")

THEN
  HTTP status == 201
  header Content-Type is text/plain;charset=UTF-8
  header Location == "/api/attachments/ATT-101"
  raw response body == "ATT-101"
~~~

If a generated test checks only status while skipping a field the consumer depends on, inspect the DSL, matchers, test mode, and plugin configuration. **Never edit generated test files manually** assuming the contract improved; the generator will overwrite them on the next build.

### For XML

Verify the generated producer test uses **XPath / XML conditions** at the right nodes rather than searching for the string `"STORED"` anywhere in the response. Regexes on IDs must not accept empty IDs, wrong prefixes, or invalid characters.

### For Binary

Verify response bytes are read/generated accurately from fixtures with the right MIME/headers. If a test checks only status `200` without reading bytes, it does not prove consumers can download a valid file. However, if bytes intentionally vary, format-level assertions may be needed instead of strict byte equality; never force a matcher tighter than the API commitment.

## 10. Inspecting Stub Mappings and Running Consumer Tests

Stub Runner uses stub artifacts generated from contracts, typically containing **WireMock mappings** for HTTP. For multipart, mappings may specify conditions on method, URL, headers, and parts. How generators encode these conditions varies by version; inspect the JSON mapping inside the actual artifact.

An **abbreviated WireMock mapping illustrating the concept**:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/attachments",
    "multipartPatterns": [
      {
        "matchingType": "ALL",
        "headers": {
          "Content-Disposition": {
            "contains": "name=\"file\""
          }
        },
        "bodyPatterns": [
          {
            "equalTo": "signed by recipient"
          }
        ]
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "text/plain;charset=UTF-8",
      "Location": "/api/attachments/ATT-101"
    },
    "body": "ATT-101"
  }
}
~~~

**Note:** the mapping above only illustrates fields to watch for; do not assume it is verbatim JSON produced from the contract in section 3. Actual mappings may include multiple `multipartPatterns`, conditions on filename, `Content-Type`, field `category`, and different body representations. Inspect **the exact packaged mapping** rather than copying an illustrative mapping as proof.

### Questions Consumer Tests Must Answer

- Does Checkout's real client build the multipart request with exact field names `category` and `file`?
- Is `filename` sent in a way Document Service accepts?
- Does the HTTP client generate a valid dynamic boundary, and does the stub match that request?
- Does the consumer read raw text `ATT-101` without attempting JSON deserialization?
- Does the consumer process XML with an XML parser or binary payloads via a byte stream?
- When receiving `400`/`415`, does the consumer surface the proper error rather than treating it as a timeout?
- Does the test genuinely call **Stub Runner with the right artifact version** rather than accidentally calling a live producer?

**Never hard-code stub ports or versions into the production application.** Consumer client configuration must switch to the stub URL during tests while pointing to the real producer URL in deployed environments.

### For XML or Binary Stubs

- XML stubs must return the exact `Content-Type` and XML body the consumer can parse.
- Binary stubs must return **raw bytes**, not a Base64 string unless the API publishes Base64.
- If the consumer downloads files as streams, tests must consume to EOF and verify resources close/clean up when needed.
- When using `Content-Disposition`, consumers must never blindly trust arbitrary filenames to write into unvalidated filesystem paths. That is an application security concern alongside contracts.

## 11. Multipart and Non-JSON: Changes Most Likely to Break Compatibility

| Producer change | Risk to consumer | Appropriate check |
|---|---|---|
| Rename part `file` to `attachment` | Client still sends `file`; producer reports missing part | Contract request matcher, generated test, and consumer Stub Runner test |
| Switch API from multipart to raw binary | Completely different body framing | Real request tests and contract change review |
| Drop `category` or change optional to required | Older consumers omit required field | Missing-field contract and compatibility review |
| Change `text/plain` to JSON string | Client reading ID gets extra quotes or parse error | MIME check and byte/string response verification |
| Change `application/xml` to JSON | Consumer XML parser cannot read it | Contract content type + XPath/consumer parsing |
| Add XML namespace or rename element | Client XPath/serialization breaks | Namespace-aware XPath and consumer test |
| Change `application/octet-stream` to Base64 text | Received bytes differ from published format | Byte-level assertion + consumer decode test |
| Drop `Content-Disposition` or change filename policy | Download logic breaks | Header assertion and consumer download test |
| Change `201` to `200` or `204` | Consumer takes wrong branch or loses body | Status, header, and body contract tests |
| Drop upload limits while swapping parser | Very large files cause system failures | Integration, memory, security, and performance tests |

**A green producer test against a new contract does not mean older consumers are compatible.** If a team changes the implementation and Groovy/YAML DSL in the same commit, new generated tests can still pass. Run consumer tests with the **candidate stub from that exact revision**, and plan upgrades for breaking changes.

## 12. What Contract Tests Do Not Prove on Their Own

For multipart and file handling, supplementary tests are often crucial:

| Property | What basic contract tests protect | When additional tests are needed |
|---|---|---|
| Part name / filename / MIME | Scenarios declared in DSL | Special parsers, multilingual filenames, file policies |
| File content | A single small fixture | Large files, streaming, checksums, corruption |
| Size limits and timeouts | Specific case if declared | Stress/performance/network tests |
| Virus/malware, path traversal | Not guaranteed automatically | Security validation tests |
| Durable file storage | Fake services may skip persistence | Persistence/integration tests |
| Content-Disposition | Sample header can be checked | Sanitizing filenames before consumer writes files |
| XML validity | Select XPath/regex assertions | XSDs, complex namespaces, signatures, parser security |
| Retries on upload failure | Single contract call is insufficient | Idempotency and resilience tests |
| Cross-service compatibility | Protects declared cases | Legacy consumers, versioning, deployment contracts |

For example, if a producer reads uploads via `MultipartFile.getBytes()`, tests with tiny files pass easily, yet memory spikes on real multi-hundred-MB files. That is an upload/streaming architecture concern that contract stubs cannot verify.

Similarly, XML parsers must be hardened against external entities (XXE), and file uploads must validate content types, lengths, and storage paths; a status/body contract test does not replace these security checks.

## 13. Designing a Verification Matrix Before Writing Many Fixtures

Instead of creating dozens of unclear files, start from the **behavior branches consumers actually use**:

| ID | Request / response | Meaning for Checkout | Primary test type |
|---|---|---|---|
| `UPLOAD_TEXT_OK` | Multipart `category` + text file → `201 text/plain` | Reads ID and Location | Producer contract + consumer Stub Runner |
| `UPLOAD_FILE_MISSING` | Multipart missing `file` → `400` | Displays actionable user error | Producer contract + consumer Stub Runner |
| `UPLOAD_BAD_MIME` | Unsupported file part MIME → `415` | Does not retry identical file | Contract if published + validation test |
| `DOWNLOAD_RECEIPT_XML` | `GET` → `200 application/xml` | Parses ID and status | Producer contract with XPath + consumer test |
| `DOWNLOAD_CONTENT_BIN` | `GET` → `200 application/octet-stream` | Reads file bytes | Binary producer contract + consumer download test |
| `DELETE_NO_CONTENT` | `DELETE` → `204` no body | Does not attempt JSON/XML parse | Producer contract + consumer test |
| `LARGE_UPLOAD` | File exceeds size limit | Rejects safely without OOM | Integration/performance/security test |
| `CORRUPT_XML` | Invalid XML or wrong namespace | Reports appropriate error | Parser/integration + error contract if committed |

This scenario set is **a recommendation**, not a mandate that every API return identical `415` or `400` codes. Each entry must reflect actual producer and consumer agreements.

### Keeping Fixtures Small Yet Representative

- Text part: `receipt`, file `proof.txt`, content `signed by recipient` are clear and readable.
- XML: a receipt with ID, status, timestamp; include namespaces if the real API uses them.
- Binary: a small deterministic file committed alongside contracts, never random files from developer machines.
- Errors: stable error codes and statuses without relying on stack traces or internal paths.
- For dynamic data, place matchers accurately while keeping **concrete sample values on the stub side** so consumer tests remain reproducible.

## 14. CI: From DSL to Same-Revision Stubs

A reliable pipeline can be structured as follows:

~~~mermaid
sequenceDiagram
    participant Dev as Developer / PR
    participant Gen as Contract generator
    participant Prod as Producer test
    participant Art as Candidate stub artifact
    participant Cons as Consumer test
    Dev->>Gen: Update DSL and fixtures
    Gen->>Prod: Generate multipart/non-JSON HTTP tests
    Prod->>Prod: Call controller/app, assert response
    alt Producer tests pass
        Gen->>Art: Generate and package same-revision stub
        Art->>Cons: Stub Runner loads exact artifact
        Cons->>Cons: Call via real HTTP client
    else Producer tests fail
        Prod-->>Dev: Block merge/release
    end
    Cons-->>Dev: Compatibility result
~~~

Minimum pipeline checks:

1. **DSL discovered:** Groovy/YAML files sit in the expected directory and the plugin actually generates tests.
2. **Fixtures exist:** referenced XML/text/binary files have valid paths inside build resources.
3. **Generated tests executed:** never treat a green build with `0 tests` as success.
4. **Multipart requests accurate:** method, URL, parts, `Content-Type`, and producer parsing.
5. **Responses have the right shape:** text is not JSON-quoted, XML has valid structure, and binary bytes stay intact where committed.
6. **Stub artifact pinned:** explicit group/artifact/version/classifier or build ID, avoiding stale cached artifacts.
7. **Consumer tests use real client:** confirm the app sends multipart and handles non-JSON responses.
8. **Compatibility review:** any change to MIME, part names, XML schemas, binary encoding, or status/headers is evaluated against deployed consumers.

A real CI pipeline may include Maven `./mvnw verify` on the producer once the plugin is configured properly, followed by stub publishing and consumer tests via Stub Runner. With Gradle, run the corresponding tasks for your project's plugin version. **This lesson describes the workflow** rather than running a build on a sample project.

## 15. Practice Exercise: Catching Contract and Consumer Bugs

### Scenario

The Checkout team has a client sending:

~~~text
POST /api/attachments
Content-Type: multipart/form-data; boundary=<client-generated>
parts:
  category = receipt
  file (filename=proof.txt, Content-Type=text/plain)
    = signed by recipient
~~~

The producer previously published:

~~~text
201 Created
Content-Type: text/plain;charset=UTF-8
Location: /api/attachments/ATT-101
body: ATT-101
~~~

However, a PR proposes:

- Renaming part `file` to `document`.
- Dropping `Location`.
- Returning JSON `{"id":"ATT-101"}` with `Content-Type: application/json`.
- Updating both the DSL and producer code together; all new generated tests pass.
- Not running consumer tests.

**Questions:**

1. Which changes can break Checkout?
2. Why do the new generated producer tests still pass?
3. Which artifacts should you inspect to verify what the PR's stub actually describes?
4. If Checkout's HTTP client still sends part `file`, what check is required?
5. If the response shifts from plain text to JSON, what is a safer migration plan?

### Answer Hints

1. **All three interface changes warrant inspection.** Part name, `Location` header, and response MIME/shape are details consumers may rely on.
2. New generated tests only prove the producer implementation matches the **new contract** for described scenarios; they do not prove existing consumers upgraded.
3. Inspect the **Groovy/YAML DSL**, **generated producer tests**, **WireMock mappings** inside the candidate stub, and producer test reports.
4. Run consumer tests with **Stub Runner pointing to the exact candidate stub** to verify whether the real client's multipart request matches and how the consumer handles the response.
5. Maintain the old interface during a transition window, add a new endpoint/version, or coordinate a controlled rollout; the choice depends on versioning policy and consumer inventory.

### Extended Exercises on XML and Binary

**XML:** a response adds a default namespace `xmlns="urn:example:receipt"`, while the old XPath uses `/receipt/attachmentId/text()`. Explain why the XPath stops matching and propose a fix aligned with the published namespace.

**Binary:** the producer returns Base64 text of a file with `Content-Type: text/plain` instead of raw `application/octet-stream` bytes. If the consumer reads an `InputStream` and saves raw bytes directly, is this change compatible? Design a test verifying received bytes, MIME type, and checksum.

### Self-Check Questions

- Why is boundary a transport detail rather than a business field to hard-code?
- How does part name differ from filename?
- How does a `text/plain` body `ATT-101` differ from an `application/json` body `"ATT-101"`?
- When should you use XPath matchers instead of exact XML text matching?
- How does `fileAsBytes` differ from `file`?
- Why shouldn't `204 No Content` carry a fake JSON body?
- Does a generated producer test with fake storage prove real file persistence works?
- How do you verify consumer tests are using the exact stub artifact from the updated contract?

## 16. Key Takeaways

**Multipart requests and non-JSON responses must be verified at the right data layer.** For multipart, contracts must specify exact **part names, filenames, part MIME types, and content** while avoiding accidental coupling to random boundaries. For `text/plain`, protect **strings and charsets**; for XML, protect **structure, namespaces, and XPath**; for binary, protect **bytes, `Content-Type`, and metadata** per interface commitments.

Spring Cloud Contract generates **producer tests** and **stubs** for described behaviors; Stub Runner lets consumers test request construction and response decoding. When CI uses the exact same revision of contracts/stubs and adds integration tests for streaming, storage, security, and large files, teams gain reliable evidence to catch incompatible HTTP API changes.
