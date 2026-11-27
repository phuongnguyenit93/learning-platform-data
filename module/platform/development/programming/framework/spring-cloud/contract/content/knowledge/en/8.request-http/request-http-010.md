# String, XML, and Binary Request Bodies

## Learning Objectives

In **Spring Cloud Contract**, an HTTP contract describes the request that a **consumer** sends to a **producer**, along with the response the producer commits to return. Contracts can be declared using **Groovy DSL** or **YAML DSL**, then used to generate producer-side tests, create stubs, and allow the consumer to run tests with **Stub Runner**.

In the **Request HTTP** chapter, this lesson focuses on request bodies that are **not regular JSON objects**. After this lesson, you will be able to:

- Distinguish plain-text, JSON-string, XML, and binary-byte bodies at the HTTP protocol level.
- Choose the proper `Content-Type`, charset, `body` representation, and matching granularity.
- Write Groovy/YAML contracts for `text/plain`, `application/xml`, and `application/octet-stream`.
- Use `xPath(...)` with XML and `fileAsBytes(...)` / `bodyFromFileAsBytes` with binary files.
- Distinguish raw binary requests from `multipart/form-data` requests containing file parts.
- Integrate these cases into generated producer tests, stub tests, and CI without accidentally corrupting or altering data.

## 1. What Is an HTTP Request Body Actually?

At the HTTP layer, the body is a **sequence of bytes** sent after the headers. The content format of the body is defined by the protocol/application; the `Content-Type` header tells the producer which format to decode the data with. Common cases:

| Request Type | Typical `Content-Type` | Body on the Wire | How to Describe in a Contract |
|---|---|---|---|
| Plain text | `text/plain; charset=UTF-8` | Bytes encoded from a string | `body('...')` or `body: '...'` |
| JSON string | `application/json` | JSON text including the JSON string's quotes | Valid JSON string; do not confuse with raw text |
| XML | `application/xml` or `text/xml` per API | XML text bytes, possibly with namespaces | XML as a String/GString in Groovy; YAML block scalar in YAML DSL |
| Direct binary | `application/octet-stream`, `application/pdf`, `image/png`, … | File/payload bytes, possibly non-UTF-8 | `fileAsBytes('...')` or `bodyFromFileAsBytes: ...` |
| Multipart | `multipart/form-data; boundary=...` | Multiple parts, each with its own headers and body | `multipart(...)` with appropriate part descriptions |

Two easily confused concepts:

- **Content-Type** describes the format of the **body being sent**. `Accept` describes the **response format the consumer wants to receive**. A consumer can easily send XML while requesting that the producer return JSON.
- **A string in source code** is not synonymous with **the data type on HTTP**. A Java/Groovy string can be serialized as raw text, XML, or JSON; looking at a `body(...)` call alone is not enough to know its semantics without checking headers and actual payload bytes.

For example, the two requests below are **different**:

~~~http
POST /api/notes HTTP/1.1
Content-Type: text/plain; charset=UTF-8

hello
~~~

~~~http
POST /api/notes HTTP/1.1
Content-Type: application/json

"hello"
~~~

The first case carries the bytes of the word `hello`. The second case is a **JSON string**, with literal quotation marks in the JSON text. If the contract and producer do not align, text that looks like "hello" can be handled by two different converters.

### Running Example

Suppose **Document Service** is the producer, and **Checkout Service** is the consumer needing to send a note, an XML order, or a PDF file. We design three illustrative endpoints:

| Endpoint | Purpose | Request Body | Response |
|---|---|---|---|
| `POST /api/notes` | Send a delivery note | Raw UTF-8 text | `202 Accepted`, JSON confirmation |
| `POST /api/orders/xml` | Submit an order in XML | XML | `202 Accepted`, JSON confirmation |
| `PUT /api/attachments/ATT-101/content` | Upload file content | File bytes | `204 No Content` |

Endpoint names, payloads, and statuses are **conventions of this illustrative system**, not Spring Cloud Contract defaults.

## 2. String Bodies: `text/plain`

### Interface Design

Consumer sends a delivery note:

~~~http
POST /api/notes HTTP/1.1
Content-Type: text/plain; charset=UTF-8
Accept: application/json

Deliver after 18:00
~~~

Producer returns:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"accepted":true}
~~~

Here, the body is **plain text**, not a JSON object with a `message` field. The consumer depends on three things: the request is `POST /api/notes`, the string is transmitted in UTF-8, and the success response has status `202` with JSON `accepted`.

### Groovy DSL for Raw Text

Save this example to a file such as `src/test/resources/contracts/notes/acceptNote.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Accept text delivery note'

    request {
        method 'POST'
        url '/api/notes'
        headers {
            contentType('text/plain;charset=UTF-8')
            accept(applicationJson())
        }
        body('Deliver after 18:00')
    }

    response {
        status 202
        headers {
            contentType(applicationJson())
        }
        body(
            accepted: true
        )
    }
}
~~~

`body('Deliver after 18:00')` specifies the sample value in the request body. When generating the stub, Spring Cloud Contract uses the request conditions to recognize the scenario; when generating the producer test, it sends the matching request and verifies the response.

If the producer accepts **any valid note**, one fixed example is not enough to test variants. You can add contracts for empty, overly long, or special-character notes; depending on requirements, use DSL matchers instead of binding to one exact literal value.

### Equivalent YAML DSL

~~~yaml
description: 'Accept text delivery note'
request:
  method: POST
  url: '/api/notes'
  headers:
    Content-Type: 'text/plain;charset=UTF-8'
    Accept: 'application/json'
  body: 'Deliver after 18:00'
response:
  status: 202
  headers:
    Content-Type: 'application/json'
  body:
    accepted: true
~~~

YAML `body: 'Deliver after 18:00'` has type **string**. Note that `response.body.accepted: true` is a **boolean**, not the string `'true'`.

### Empty Strings and Absent Bodies

The following three cases must be distinguished contractually:

| Case | Meaning |
|---|---|
| Raw text with content `hello` | Request carries 5 ASCII/UTF-8 bytes for `hello` |
| Body of length 0 | May be an empty string; valid or error behavior depends on the API |
| No body sent | May be handled differently by the framework than sending an empty body |

At the business layer, the producer may **accept an empty note**, **reject with `400`**, or **allow requests with no body**. Align on each case used by the consumer and create verification contracts; do not assume they are always equivalent.

## 3. Multi-Line Strings, Newlines, and Charsets

Plain text is sometimes CSV, logs, or multi-line notes. If a contract matches verbatim, **newlines and trailing whitespace** can determine whether a request matches.

### YAML Block Scalars

~~~yaml
# Keep the newline between lines, strip the trailing newline.
body: |-
  Deliver after 18:00
  Leave package at security desk
~~~

Comparison:

| YAML Syntax | Primary Effect |
|---|---|
| `|-` | Keeps newlines between lines, strips trailing newline |
| `|` | Keeps a single trailing newline per clip rule |
| `>` | Folds regular newlines into spaces |
| `> -` *(written together as `>-`)* | Folds lines and strips trailing newline |

For example, using `body: |` instead of `body: |-` can cause the parser to append an **extra trailing newline byte**. If the consumer sends a body without that newline and the stub requires an exact match, tests can fail.

In Groovy, multi-line strings can be expressed as:

~~~groovy
body('''Deliver after 18:00
Leave package at security desk''')
~~~

Triple single quotes are **Groovy** syntax, not YAML syntax. In both DSLs, inspect the parsed value, especially leading/trailing newlines introduced while formatting code.

### Charset and Byte Length

Vietnamese text (or other non-ASCII characters) means the **byte** count in UTF-8 does not necessarily equal the **character** count. When exchanging contracts:

- Specify the charset when the format is text; in this example use `text/plain;charset=UTF-8`.
- Never substitute the OS default encoding for UTF-8.
- If the body contains Unicode, test with a real consumer client rather than eyeballing the DSL file.
- Distinguish `LF` vs. `CRLF` line endings when the system requires exact byte matching. When byte-exactness is not required, consider appropriate matchers or normalization instead of hardcoding.
- `Content-Length` is the **byte length of the body on the wire**, not the character count. Usually let the HTTP client calculate this header automatically.

## 4. XML Bodies: Preserve Structure and Semantics, Avoid Accidental Matching

XML is common in enterprise integrations, SOAP, and legacy APIs. Unlike JSON maps, XML has **elements, attributes, text nodes, namespaces**, and potentially schema-significant element ordering.

Example request:

~~~http
POST /api/orders/xml HTTP/1.1
Content-Type: application/xml; charset=UTF-8
Accept: application/json

<order>
  <orderId>ORD-101</orderId>
  <quantity>2</quantity>
</order>
~~~

The producer should read this body as **XML**, not a JSON string. In Spring Cloud Contract, an XML body is passed to `body` as a **String/GString**. When checking specific elements, use **XPath matchers** (`xPath`) rather than JSONPath.

### Groovy DSL: XML Request and XPath

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Receive XML order'

    request {
        method 'POST'
        url '/api/orders/xml'
        headers {
            contentType('application/xml;charset=UTF-8')
            accept(applicationJson())
        }
        body('''<order>
  <orderId>ORD-101</orderId>
  <quantity>2</quantity>
</order>''')

        bodyMatchers {
            xPath('/order/orderId/text()', byRegex('ORD-[0-9]{3}'))
            xPath('/order/quantity/text()', byRegex('[1-9][0-9]*'))
        }
    }

    response {
        status 202
        headers {
            contentType(applicationJson())
        }
        body(
            accepted: true
        )
    }
}
~~~

The `xPath(...)` lines identify match targets inside the XML: `orderId` has the form `ORD-` + three digits, and `quantity` holds a positive integer represented as text. In XML, content between tags is initially **text**; `quantity` being an integer comes from the schema/deserializer, not automatically from XML itself.

**Important:** how the generated stub uses matchers for incoming requests and how the generated producer test sends the sample value are two distinct sides. Consumer tests must still send valid XML that the producer can actually process, and producer contract tests must be configured to spin up the required controller/service.

### YAML DSL: XML with Block Scalar

~~~yaml
description: 'Receive XML order'
request:
  method: POST
  url: '/api/orders/xml'
  headers:
    Content-Type: 'application/xml;charset=UTF-8'
    Accept: 'application/json'
  body: |-
    <order>
      <orderId>ORD-101</orderId>
      <quantity>2</quantity>
    </order>
  matchers:
    body:
      - path: '/order/orderId/text()'
        type: by_regex
        value: 'ORD-[0-9]{3}'
      - path: '/order/quantity/text()'
        type: by_regex
        value: '[1-9][0-9]*'
response:
  status: 202
  headers:
    Content-Type: 'application/json'
  body:
    accepted: true
~~~

`|-` keeps the XML body free of an unintended trailing newline; `matchers.body` applies XPath rules. The YAML file must have valid indentation; `body` here is **one XML string**, not a YAML mapping describing elements.

### Important Considerations with XML

1. **Well-formedness:** XML must have valid tag structure; characters like `&` in text must be written as `&amp;` unless an appropriate mechanism is used.
2. **Namespaces:** `<ns:order xmlns:ns="urn:example:orders">` differs from `<order>` without a namespace. An XPath unaware of namespaces can return empty results. For default namespaces, XPath often needs registered prefixes or `local-name()`/`namespace-uri()` conditions.
3. **Whitespace:** indentation, newlines, and text nodes can affect matchers. Verify the values consumers care about instead of assuming two XML payloads need only look visually similar.
4. **Attributes and ordering:** XML attribute order usually carries no semantics; element order can matter per schema. Do not turn attribute ordering into a contract rule unless consumers rely on it.
5. **Encoding:** the header charset and `<?xml version="1.0" encoding="UTF-8"?>` declaration, if present, must match the actual bytes sent.
6. **Parser security:** the producer must configure its XML parser safely, especially against external entity loading/XXE. A contract test with valid XML does not test attack vectors.

**Do not use `byType()` as a substitute for XML matchers:** Spring Cloud Contract's XPath matchers support types such as regex/equality, whereas `byType()` is not a supported option for XML XPath matchers. When XSD schema validation or complex business rules need checking, add appropriate tests outside the basic contract.

## 5. Binary Request Bodies: Do Not Force Files into Strings

A PDF file, image, or arbitrary binary payload can contain bytes that are not valid UTF-8 characters. Reading it as a `String` or pasting it into YAML/Groovy text can alter the data:

- Bytes get transcoded or replaced with replacement characters.
- Newlines get normalized.
- Backslashes or escape-like sequences get interpreted.
- Base64 text gets mistakenly treated as **raw data**, causing the producer to receive **base64 characters** instead of the original bytes.

In HTTP, a **raw binary upload** looks like:

~~~http
PUT /api/attachments/ATT-101/content HTTP/1.1
Content-Type: application/octet-stream

<binary byte sequence of the document>
~~~

The line inside angle brackets is just a visual placeholder for readers, **not the literal body**. The real body consists of the file's bytes, with no `<` or `>` added unless they are part of the file.

### Groovy DSL: `fileAsBytes(...)`

Spring Cloud Contract supports reading file contents as bytes via `fileAsBytes`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Receive binary file'

    request {
        method 'PUT'
        url '/api/attachments/ATT-101/content'
        headers {
            contentType(applicationOctetStream())
        }
        body(fileAsBytes('upload.pdf'))
    }

    response {
        status 204
    }
}
~~~

`upload.pdf` is a **binary fixture file** placed in the project alongside the contract where the DSL can reference it. This file must actually exist when running contract test/stub generation. Example directory layout:

~~~text
src/test/resources/contracts/attachments/
├── uploadContent.groovy
└── upload.pdf
~~~

`fileAsBytes('upload.pdf')` reads the **file's bytes**, not the filename string as the body. For formats accepting only PDF, the API may publish `application/pdf` instead of `application/octet-stream`; agree on this between producer and consumer.

### YAML DSL: `bodyFromFileAsBytes`

~~~yaml
description: 'Receive binary file'
request:
  method: PUT
  url: '/api/attachments/ATT-101/content'
  headers:
    Content-Type: 'application/octet-stream'
  bodyFromFileAsBytes: 'upload.pdf'
response:
  status: 204
~~~

Assuming the YAML is saved at:

~~~text
src/test/resources/contracts/attachments/
├── uploadContent.yml
└── upload.pdf
~~~

In Spring Cloud Contract's DSL, `bodyFromFileAsBytes` points to the file containing bytes. The path is resolved relative to the contract location per the tool's conventions, not relative to whichever directory a terminal command runs from.

### How Does `file(...)` Differ from `fileAsBytes(...)`?

| Purpose | Groovy DSL | YAML DSL | What to Remember |
|---|---|---|---|
| Read content from a text/JSON/XML file | `body(file('request.xml'))` | `bodyFromFile: request.xml` | Choose when content is handled as text |
| Read exact bytes of a binary file | `body(fileAsBytes('upload.pdf'))` | `bodyFromFileAsBytes: upload.pdf` | Avoid converting binary to string and re-encoding |

**Do not assume `bodyFromFile: upload.pdf` preserves every byte.** For binary payloads, use the dedicated byte-reading API.

With `204 No Content`, the producer returns no response body. If the API needs to return metadata about the uploaded file, design `201 Created` or `200 OK` with a JSON response, and agree on it explicitly; do not attach a JSON body to `204`.

## 6. When the Response Is Also Binary

A file-download API sometimes has a bodyless `GET` request whose **response is bytes**. The same `fileAsBytes` / `bodyFromFileAsBytes` technique can be used in the **response**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Download binary file'

    request {
        method 'GET'
        url '/api/attachments/ATT-101/content'
    }

    response {
        status 200
        headers {
            contentType(applicationOctetStream())
        }
        body(fileAsBytes('download.pdf'))
    }
}
~~~

Equivalent YAML:

~~~yaml
description: 'Download binary file'
request:
  method: GET
  url: '/api/attachments/ATT-101/content'
response:
  status: 200
  headers:
    Content-Type: 'application/octet-stream'
  bodyFromFileAsBytes: 'download.pdf'
~~~

These two examples simply illustrate the **reusability of the byte-reading mechanism**. In the HTTP request lesson, the main focus remains distinguishing raw text/XML/binary request bodies so the producer receives them properly. `download.pdf` must also exist at the path referenced by the contract.

When the consumer processes a downloaded file, tests should verify bytes/content-type/file properties per business rules (such as checksum, magic bytes, or file readability) rather than checking only the HTTP status.

## 7. Raw Binary vs. `multipart/form-data`

Learners often mistakenly treat every file-upload request as `application/octet-stream`. In reality there are two distinct communication styles:

~~~mermaid
flowchart TD
    A["Consumer needs to send a file"] --> B{"Which upload style does the API expect?"}
    B -->|Raw body| C["A sequence of bytes<br/>Content-Type: application/octet-stream or specific MIME"]
    B -->|Form upload| D["multipart/form-data<br/>Has boundary and parts"]
    C --> E["fileAsBytes / bodyFromFileAsBytes"]
    D --> F["multipart(...)<br/>Describe part names, files, content types"]
~~~

**Raw binary** sends the payload's bytes directly as the body. **Multipart** is a multi-part structure that can mix text fields with files. Each part can have its own `Content-Disposition` and `Content-Type`; the overall `Content-Type` header carries a `boundary` parameter separating parts.

Illustrative multipart wire format:

~~~http
POST /api/attachments/multipart HTTP/1.1
Content-Type: multipart/form-data; boundary=AaB03x

--AaB03x
Content-Disposition: form-data; name="description"

Proof of delivery
--AaB03x
Content-Disposition: form-data; name="file"; filename="proof.txt"
Content-Type: text/plain

signed by recipient
--AaB03x--
~~~

This shows a **text part + text-content file part** for easy inspection. If the file were a real image/PDF, the file part's content would be binary bytes. The boundary header indicates how parts are separated; actual boundaries may vary per HTTP client request.

Spring Cloud Contract provides the `multipart(...)` DSL. Groovy example for a file part **using illustrative text data**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Receive form with text file'

    request {
        method 'POST'
        url '/api/attachments/multipart'
        headers {
            contentType('multipart/form-data;boundary=AaB03x')
        }
        multipart(
            description: 'Proof of delivery',
            file: named(
                name: 'proof.txt',
                content: 'signed by recipient',
                contentType: 'text/plain'
            )
        )
    }

    response {
        status 201
    }
}
~~~

The example aims to show **field name, filename, content, and part MIME type**. It does not verify a byte-for-byte PDF upload. For real files, check binary multipart support in your DSL version and add dedicated integration tests if the producer must preserve exact file bytes or metadata.

**Do not switch a raw binary API to multipart or vice versa without updating contracts and consumers.** That is a breaking request-format change, even though both APIs conceptually "accept a file."

## 8. Designing Matchers Without Over-Locking Details

Matchers describe **the constraints consumer and producer must commit to**, rather than pinning every byte when unnecessary.

| Body Type | What to Verify | What to Watch Out For |
|---|---|---|
| Raw text | Valid content or pattern, charset, empty/length rules | Spaces, trailing newlines, Unicode; overly loose matchers |
| XML | Key elements/attributes/XPaths, namespaces, business values | Verbatim XML matching when serializers alter indentation or attribute order |
| Raw binary | Fixture bytes or committed characteristics, `Content-Type`, size limits | Converting to string, comparing base64 as raw bytes, oversized fixtures |
| Multipart | Field names, filenames, per-part content types, required data | Dynamic boundaries, part order when unspecified by API, overlooking file part checks |

For instance, if the API only requires XML `orderId` in the right format and a positive `quantity`, **XPath matchers** express the intent much better than requiring the entire XML to match every space. Conversely, when receiving digitally signed XML where changing bytes or canonicalization breaks signature verification, tests must respect the signing protocol's exact requirements.

For PDFs or images, a small, deterministic fixture keeps generated tests fast. However, **one valid fixture does not by itself prove** the system handles all files, sizes, and transmission failures. Empty files, oversized payloads, wrong MIME types, corrupted PDFs, and bad checksums require additional tests aligned with the business agreement.

## 9. Designing Error Responses for All Three Request Types

The same endpoint may return different errors depending on the cause. For example:

| Request | Scenario | Possible Agreed Response | Meaning to Consumer |
|---|---|---|---|
| `text/plain` | Note too long | `413 Content Too Large` or `400 Bad Request` per API policy | Shorten input or notify user |
| `application/xml` | Malformed XML | `400 Bad Request` + `INVALID_XML` | Do not resend the same unfixed body |
| `application/xml` | Well-formed XML missing required element | `422 Unprocessable Content` or `400` per convention | Fix business data |
| `application/octet-stream` | Unsupported MIME type | `415 Unsupported Media Type` | Switch to an allowed file format |
| Raw binary/multipart | File exceeds size limit | `413 Content Too Large` | Report size limit and block upload |
| Any upload | Temporary infrastructure error | `503 Service Unavailable` if specified by API | Consumer considers retrying per policy |

Status codes and application errors in the table are **illustrative suggestions**, not automatically imposed by Spring Cloud Contract. Once producer and consumer agree on the choices, each important case should have **its own contract** or appropriate test scenario.

Avoid returning XML parser stack traces or internal file-storage paths in error bodies. Error contracts should expose machine-readable codes (`INVALID_XML`, `FILE_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, …) and a stable structure consumers can handle.

## 10. From Contract to Generated Tests, Stubs, and CI

~~~mermaid
sequenceDiagram
    participant Dev as Developer / CI
    participant C as Groovy/YAML contract
    participant P as Producer test
    participant S as Stub artifact
    participant U as Consumer test
    Dev->>C: Define text/XML/binary request
    C->>P: Generate producer contract test
    P->>P: Send real request per contract
    alt Producer complies
      P-->>S: Build/package verified stub
      S-->>U: Stub Runner runs exact stub version
      U->>U: Send request with real client
    else Wrong body, headers, or response
      P-->>Dev: Build fails, investigate mismatch
    end
~~~

### Producer Side

The producer configures **Spring Cloud Contract Verifier** and its plugin, places contracts under the directory read by the build, and sets up the base test class/environment.

- For raw text, generated tests send requests matching the defined `Content-Type` and `body`.
- For XML, generated tests send the sample XML; matchers can verify required behavior.
- For binary, fixture files must be present before running test and stub generation. Do not reference filenames in the DSL and forget to commit them in the build.

A passing generated test only proves the producer satisfies **the described scenarios**; it does not automatically prove every valid payload or production network condition.

### Consumer Side

The consumer uses **Spring Cloud Contract Stub Runner** to download or launch the producer's stub at a defined coordinate/version. Consumer tests must use the **application's real HTTP client**:

- Send raw text via the client with the right `Content-Type`, without serializing it as a JSON string.
- Send XML with accurate namespaces and charset.
- Send file bytes using proper mechanisms (e.g., resource/byte array) rather than converting through `String`.
- Read and process success/error responses per contract.

**A passing consumer test against a stub does not prove the real producer is right**, because stubs are simulated data. Conversely, a passing producer test does not prove the consumer uses the API properly. To catch incompatible API changes, CI must run both sides with matching contract/stub versions.

### Minimal CI Workflow

1. Verify Groovy/YAML contract files and text/binary fixtures are committed at valid paths.
2. Generate and execute generated producer tests using your project's Spring Cloud Contract version.
3. Only after producer tests pass, package/publish candidate stubs with explicit coordinates and version.
4. Run consumer tests using Stub Runner against **that exact candidate stub**.
5. When changing `Content-Type`, encoding, XML schema/namespace, or switching raw binary ↔ multipart, evaluate compatibility with consumers still on older versions before releasing.

Never use an uncontrolled `latest` artifact in CI and conclude tests verified the exact producer version about to be deployed.

## 11. Common Errors and Fixes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Producer returns `415` when consumer sends note | Body is raw text while `Content-Type` is `application/json` | Publish and send proper `text/plain;charset=UTF-8` |
| Stub does not match text request | Trailing newline, spaces, or encoding mismatch | Inspect body after YAML/Groovy parsing and real HTTP bytes |
| Contract XML fails to parse | Unescaped XML body, unclosed tags, raw `&` character | Fix XML/encoding, verify with a proper XML parser |
| XPath matcher fails to find element | XML namespace or XPath mismatch | Check prefix, namespace URI, and `local-name()` if needed |
| Confusing XML matcher results | Using JSONPath or `byType()` as with JSON | Use XPath and matchers supported by the DSL |
| PDF arrives corrupted at producer | Binary converted to String or base64 confusion | Use `fileAsBytes` / `bodyFromFileAsBytes`, inspect real bytes |
| Stub generation build fails missing file | Binary fixture absent or wrong relative path | Place file beside contract at the right path and commit fixture |
| Server cannot read multipart file | Consumer sent raw binary or wrong part name/boundary | Verify `multipart/form-data` and each part |
| Consumer test passes yet deployment fails | Test uses old stub or didn't run real client | Pin stub version, inspect the real client and producer pipeline |
| Build runs very slowly due to huge fixtures | Contract embeds unnecessarily heavy payloads | Use small representative fixtures, pair with separate size/perf tests |

## 12. Exercises: Choosing Body Representations

### Scenario A: Consumer Sends a Tracking Code

API `POST /api/tracking/codes` accepts a tracking code as raw text `000987`, which may have leading zeros.

**Recommended choice:**

~~~yaml
request:
  method: POST
  url: '/api/tracking/codes'
  headers:
    Content-Type: 'text/plain;charset=UTF-8'
  body: '000987'
response:
  status: 202
~~~

**Explanation:** `'000987'` is a string with leading zeros. Writing unquoted `body: 000987` in YAML can make the parser infer another type. If the endpoint expects raw text, do not send a JSON string `"000987"` as a JSON payload.

### Scenario B: Consumer Sends Namespaced XML

Request body:

~~~xml
<o:order xmlns:o="urn:example:orders">
  <o:id>ORD-105</o:id>
  <o:quantity>3</o:quantity>
</o:order>
~~~

**Question:** Will XPath `/order/id/text()` always find the ID?

**Answer:** No. The XML uses namespace `urn:example:orders`, so XPath must handle namespaces. For example, a prefix-free approach uses `local-name()` and `namespace-uri()` for the target nodes. When designing contracts, use XPath compatible with the real namespace and test Spring Cloud Contract's parser/matcher.

### Scenario C: Consumer Uploads a PDF File

Producer exposes `PUT /api/attachments/ATT-105/content` accepting raw PDF bytes.

**Choose the appropriate representation:**

~~~yaml
request:
  method: PUT
  url: '/api/attachments/ATT-105/content'
  headers:
    Content-Type: 'application/pdf'
  bodyFromFileAsBytes: 'sample.pdf'
response:
  status: 204
~~~

Place `sample.pdf` at a relative path resolvable by the contract DSL and keep the file as **binary bytes**. If a new interface replaces `application/pdf` with `multipart/form-data` without migrating consumers simultaneously, that is an incompatible request change.

### Self-Check Questions

1. Why don't `Content-Type` and `Accept` share the same meaning?
2. Why can `body: |-` differ from `body: |` when testing text?
3. How do XML namespaces affect XPath matchers?
4. Why shouldn't you pass a PDF via `body: '...'` like a regular string?
5. How do `bodyFromFile` and `bodyFromFileAsBytes` differ?
6. Why must producer contract tests and consumer stub tests use the same revision/version?
7. Do raw binary and multipart produce the same HTTP request body?

## 13. References and Takeaways

Official Spring Cloud Contract documentation describes [HTTP contracts and XML/XPath](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html), as well as [reading payloads from files as text or bytes](https://docs.spring.io/spring-cloud-contract/docs/current/reference/htmlsingle/index.html) and the [YAML DSL schema](https://docs.spring.io/spring-cloud-contract/reference/yml-schema.html). Double-check syntax for your active **Spring Cloud Contract version** before copying examples directly into a project.

**HTTP request bodies are not JSON by default.** For raw text, align on encoding and newlines; for XML, verify structure, namespaces, and XPath; for binary data, preserve bytes with `fileAsBytes` or `bodyFromFileAsBytes`; for multipart, describe parts accurately. Spring Cloud Contract turns these agreements into generated tests on the producer and stubs on the consumer. Using the right stub versions in CI catches incompatible request/response changes early.
