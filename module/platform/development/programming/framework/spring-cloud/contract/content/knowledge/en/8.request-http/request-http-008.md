# Form URL-Encoded and Character Encoding

## 1. Problem and Objectives

In **Spring Cloud Contract (SCC)**, an HTTP contract describes the request conditions sent by the **consumer**, along with the response the **producer** must return. Contracts written in **Groovy DSL** or **YAML DSL** are used to generate **producer tests** and **stubs**. The consumer can run **Stub Runner** against candidate stubs; CI brings both sides together to detect incompatible API changes.

Not every HTTP request carries JSON. Traditional HTML forms, certain login APIs, order confirmations, and legacy integrations send data in **`application/x-www-form-urlencoded`** format. If a contract accidentally describes JSON, or confuses `+` with a space, the generated request can differ from the consumer's request even when the data looks visually similar.

This lesson focuses on **form URL-encoded HTTP requests and character encoding**: rules for converting name/value pairs into a body, how to write contracts, how to send forms from Spring, and how to verify producers and consumers.

After this lesson, you will be able to:

1. Distinguish form URL-encoded from JSON, query parameters, and multipart.
2. Explain how spaces, plus signs, special characters, and Vietnamese characters are encoded using UTF-8.
3. Write Groovy and YAML contract examples with **encoded string bodies**.
4. Build requests with `RestClient` and `MultiValueMap` without double-encoding.
5. Inspect generated producer tests and stubs to catch discrepancies in **Content-Type**, bytes, charset, and matching conditions.
6. Design CI checks that catch incompatible changes for form consumers still in use.

## 2. Where Does Form URL-Encoded Sit in HTTP?

Suppose Checkout Service needs to send a recipient name, delivery note, and quantity to Inventory Service:

~~~http
POST /api/reservations/preview HTTP/1.1
Host: inventory.example.test
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept: application/json

fullName=Tr%E1%BA%A7n+V%C4%83n+A&note=Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh&quantity=2
~~~

The body above carries **three name–value pairs**:

| Field Name | Pre-Encoded Value | Data in Body |
|---|---|---|
| `fullName` | `Trần Văn A` | `Tr%E1%BA%A7n+V%C4%83n+A` |
| `note` | `Khuyến mãi 10% & giao nhanh` | `Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh` |
| `quantity` | `2` | `2` |

When receiving the proper `Content-Type` and charset, the server decodes the body to recover the original values. Form fields are inherently transmitted as **strings**; Spring MVC can convert the string `"2"` into an `int` for a controller parameter.

This is form URL-encoded data inside the **request body**. Although the syntax resembles a URL query string, its location and contract usage are completely different: the path remains `/api/reservations/preview`; the name–value pairs after the blank HTTP line form the **body**.

## 3. Encoding Rules for `application/x-www-form-urlencoded`

Basic model:

~~~text
encode(name1)=encode(value1)&encode(name2)=encode(value2)&...
~~~

For each name and value separately:

1. Convert the Unicode string into bytes using the chosen charset, typically **UTF-8**.
2. Leave safe characters unencoded per form-encoding rules.
3. Represent **spaces** with the `+` sign.
4. Represent bytes needing escaping as `%HH` (two hex digits).
5. Join each name and value with `=`; join pairs with `&`.

Note: `&` and `=` characters **inside values** must be encoded before joining, since those two characters also serve as delimiters.

### Common Conversion Table

| Original Data | Form-Encoded | Why? |
|---|---|---|
| `hello world` | `hello+world` | Space becomes `+` |
| `a+b` | `a%2Bb` | **Literal** plus sign becomes `%2B` |
| `a&b` | `a%26b` | `&` inside a value must not become a field separator |
| `a=b` | `a%3Db` | `=` inside a value must not become a name/value separator |
| `10%` | `10%25` | Literal `%` becomes `%25` |
| `a+b&c=d` | `a%2Bb%26c%3Dd` | Each special character is encoded |
| `Cà phê sữa` | `C%C3%A0+ph%C3%AA+s%E1%BB%AFa` | UTF-8: Vietnamese diacritics produce multi-byte sequences |
| `a+b@example.com` | `a%2Bb%40example.com` | Both `+` and `@` are escaped |

**Three values to distinguish:**

~~~text
name=Minh+Anh        -> "Minh Anh"
name=Minh%20Anh      -> "Minh Anh"  (after form decoding)
name=Minh%2BAnh      -> "Minh+Anh"
~~~

In form URL-encoded data, both `+` and `%20` can decode to a **space**, yet their byte sequences on the wire are not identical. A **stub matching the raw body** may treat them as different. During verification, clarify whether the contract requires **decoded form values** or a **byte-for-byte body representation**.

## 4. UTF-8 and Vietnamese: From Characters to Bytes

Suppose the recipient value is **`Trần Văn A`**. Some characters are encoded as follows:

- `T`, `r`, `n`, `V`, `A`: ASCII characters, left unchanged.
- `ầ`: multi-byte UTF-8, written as a sequence of `%HH`, specifically `%E1%BA%A7`.
- `ă`: encoded as `%C4%83`.
- Space: converted to `+`.

Result:

~~~text
Trần Văn A
    ↓ application/x-www-form-urlencoded, UTF-8
Tr%E1%BA%A7n+V%C4%83n+A
~~~

For **`Khuyến mãi 10% & giao nhanh`**:

~~~text
Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh
~~~

Crucially, each Unicode character is converted to **UTF-8 bytes before percent-encoding**. You cannot compute `%HH` directly from the four hex digits of a Unicode code point.

### Charset and Reproducibility

Typical header:

~~~http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
~~~

Charset policy must be consistent across **client, server, generated tests, and Stub Runner**. Not every client sends `charset` explicitly; some implementations default to UTF-8. If the contract requires `charset=UTF-8`, inspect the actual outgoing request too.

Do not assume visually identical text always has identical Unicode bytes. An accented letter can sometimes exist as a **precomposed character** or as a **base character + combining mark**. For contracts requiring exact byte matching, teams should standardize normalization such as NFC; at the business level, verifying decoded values is usually preferred.

## 5. Distinguishing Four Easily Confused Formats

| Data Format | Content-Type / Location | Example | Characteristics |
|---|---|---|---|
| **Form URL-encoded** | `application/x-www-form-urlencoded` in **body** | `name=Minh+Anh&qty=2` | Name–value pairs, encodes punctuation and spaces |
| **Query parameters** | Portion after `?` in URL | `/items?name=Minh%20Anh` | Data lives in URL, declared separately under `queryParameters` |
| **JSON** | `application/json` in body | `{"name":"Minh Anh","qty":2}` | Supports string/number/boolean/object/array types |
| **Multipart** | `multipart/form-data; boundary=...` in body | Parts with headers and boundaries | Commonly used for file uploads or mixed payloads |

The same `qty` field has text value `"2"` in a form body, whereas in JSON it can be number `2`. Do not let generated tests accidentally send JSON when the real consumer sends a form.

A particularly common mistake is putting form fields into SCC's `queryParameters`:

~~~yaml
# WRONG example when the intent is a POST form in the body:
request:
  method: POST
  urlPath: /api/reservations/preview
  queryParameters:
    fullName: Trần Văn A
    quantity: "2"
~~~

This snippet describes **URL query parameters**, which does not turn the request into a form URL-encoded body. If the API actually reads form fields from the body, describe the **body and Content-Type**.

## 6. Groovy DSL Contract with a URL-Encoded Body

A clear way to represent a **fixed form payload** is placing the encoded form string inside `body(...)` while declaring `Content-Type`.

Illustrative file: `src/test/resources/contracts/reservation/preview-reservation.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout sends form to preview reservation'

    request {
        method POST()
        url '/api/reservations/preview'

        headers {
            header('Content-Type',
                'application/x-www-form-urlencoded; charset=UTF-8')
            header('Accept', 'application/json')
        }

        body(
            'fullName=Tr%E1%BA%A7n+V%C4%83n+A' +
            '&note=Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh' +
            '&quantity=2'
        )
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            fullName: 'Trần Văn A',
            note: 'Khuyến mãi 10% & giao nhanh',
            quantity: 2,
            status: 'ACCEPTED'
        )
    }
}
~~~

**Meaning:**

- **`method POST()` and `url`** specify the producer endpoint.
- **`Content-Type`** requires the request to be interpreted as form URL-encoded with UTF-8.
- **`body(...)`** is a **string** containing the encoded data; not a Groovy map or JSON.
- The response is still **JSON**. Request and response formats do not have to match.
- Sample values are fixed for easy end-to-end verification; if the API accepts many dynamic values, evaluate how your SCC version generates request matchers for **text bodies**.

Some very old versions of Contract Verifier had an issue escaping `&` inside generated tests. If you see the body in generated source turn into `&amp;`, inspect the plugin version and test generation logic rather than altering the contract to accept an improperly HTML-escaped string.

### Why Not Add `bodyMatchers { jsonPath(...) }`?

The form body above is a **delimited text string**, not a JSON document. JSONPath `$.fullName` cannot extract fields from `fullName=...` according to form-encoding rules. Do not apply JSONPath body matchers to a form body merely because field names match. In this lesson, we prefer fixed form examples and verify exact requests; if flexible form matchers are needed, verify SCC/WireMock support in your project version and inspect the generated stub mapping.

## 7. Equivalent Declaration in YAML DSL

If the team uses YAML instead of Groovy, `body` should be written as a **scalar string** containing the encoded form string:

~~~yaml
description: Checkout sends form to preview reservation
name: preview_reservation_form

request:
  method: POST
  url: /api/reservations/preview
  headers:
    Content-Type: application/x-www-form-urlencoded; charset=UTF-8
    Accept: application/json
  body: 'fullName=Tr%E1%BA%A7n+V%C4%83n+A&note=Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh&quantity=2'

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    fullName: Trần Văn A
    note: Khuyến mãi 10% & giao nhanh
    quantity: 2
    status: ACCEPTED
~~~

Single quotes around `request.body` ensure the entire content is read as a string. Avoid using the following YAML map when defining a form body:

~~~yaml
# NOT how to represent a fixed form URL-encoded body:
request:
  body:
    fullName: Trần Văn A
    quantity: 2
~~~

A map has structural semantics different from the form string `fullName=...&quantity=2`; depending on `Content-Type`, SCC may treat it as JSON-like data, altering the bytes received by the producer.

### When the Body Is Very Long

You can consider using a separate resource file via YAML DSL's `bodyFromFile` or Groovy DSL's `body(file(...))` if your version supports loading text payloads that way. That file should contain the **encoded form string**, not JSON just because other examples use that extension. Verify that generated tests and stubs preserve the body verbatim, especially `&`, `+`, and `%` characters.

Do not keep both Groovy and YAML files for the exact same scenario in the project just to compare syntax; they can be compiled into duplicate contracts. The two examples above are **alternatives to each other**.

## 8. Safely Sending Forms from Spring `RestClient`

In Spring applications using **`RestClient`**, prefer sending **unencoded** data via `MultiValueMap<String, String>`. Spring's `FormHttpMessageConverter` performs form encoding instead of developers concatenating strings manually.

~~~java
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

public class ReservationClient {
    private final RestClient restClient;

    public ReservationClient(String baseUrl) {
        this.restClient = RestClient.create(baseUrl);
    }

    public PreviewResponse preview() {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("fullName", "Trần Văn A");
        form.add("note", "Khuyến mãi 10% & giao nhanh");
        form.add("quantity", "2");

        return restClient.post()
                .uri("/api/reservations/preview")
                .contentType(MediaType.parseMediaType(
                        "application/x-www-form-urlencoded; charset=UTF-8"))
                .accept(MediaType.APPLICATION_JSON)
                .body(form)
                .retrieve()
                .body(PreviewResponse.class);
    }

    public record PreviewResponse(
            String fullName, String note, int quantity, String status) {}
}
~~~

Points worth verifying:

1. `form.add("note", "Khuyến mãi 10% & giao nhanh")` uses the **raw string**. The converter handles `%`, `&`, and Vietnamese diacritics.
2. `MultiValueMap` supports **multiple values for the same field name**, unlike `Map<String, String>` which holds only one value per key.
3. The request must specify the form media type; sending `application/json` triggers a different body converter.
4. The quantity field in the form is the string `"2"`, which Spring MVC can convert to `int` during parameter binding.
5. `RestClient` is available in corresponding Spring Framework versions; older projects may use `RestTemplate` or `WebClient`, yet the principle remains delegating encoding to the library.

**Avoid pre-encoding and passing it back into the converter:**

~~~java
// WRONG: already-encoded data can be encoded a second time.
form.add("fullName", "Tr%E1%BA%A7n+V%C4%83n+A");
~~~

If the converter encodes `%` into `%25`, the server will receive something like `Tr%E1%BA%A7n+V%C4%83n+A` after **one** decoding pass instead of `Trần Văn A`. This is a **double encoding** bug.

## 9. How Does a Spring MVC Producer Receive a Form?

A producer can define a controller using `@RequestParam` or `@ModelAttribute` to read form fields. Simple example:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReservationPreviewController {

    @PostMapping(
        path = "/api/reservations/preview",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public PreviewResponse preview(
            @RequestParam("fullName") String fullName,
            @RequestParam("note") String note,
            @RequestParam("quantity") int quantity) {

        return new PreviewResponse(
            fullName, note, quantity, "ACCEPTED");
    }

    public record PreviewResponse(
            String fullName, String note, int quantity, String status) {}
}
~~~

In this scenario, Spring MVC reads the form body, decodes it, and binds `fullName`, `note`, and `quantity` to method parameters. If the contract sends the right body, the producer test will observe the JSON response containing the **decoded Vietnamese text**.

Note: `@RequestParam` in Spring MVC can also read parameters from the URL. To be certain the producer is receiving a **form body**, verify that the request has the right `Content-Type` and an actual body sent, rather than calling the endpoint with `?fullName=...` and assuming the form contract was tested.

If you use `@RequestBody` expecting a regular JSON DTO while the client sends `application/x-www-form-urlencoded`, the JSON converter will not match; that is a protocol mismatch between consumer and producer.

## 10. Testing Requests Manually with `curl`

You can craft manual requests with `curl` against a locally running producer:

~~~bash
curl -X POST \
  'http://localhost:8080/api/reservations/preview' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'fullName=Trần Văn A' \
  --data-urlencode 'note=Khuyến mãi 10% & giao nhanh' \
  --data-urlencode 'quantity=2'
~~~

`--data-urlencode` encodes **raw values** to construct the form body. The shell snippet above uses Bash line continuation; on Windows PowerShell or CMD, adapt quoting/line continuation accordingly and invoke `curl.exe` explicitly if needed.

Check the expected response:

~~~json
{
  "fullName": "Trần Văn A",
  "note": "Khuyến mãi 10% & giao nhanh",
  "quantity": 2,
  "status": "ACCEPTED"
}
~~~

To inspect the exact bytes sent, capture HTTP traces in a safe test environment, e.g. using `curl --trace-ascii` with dummy data. Note that `curl` adds `Content-Type: application/x-www-form-urlencoded` automatically in some modes; if the contract requires a charset, set the header explicitly as shown.

### Manually Sending a Pre-Encoded Body

~~~bash
curl -X POST \
  'http://localhost:8080/api/reservations/preview' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -H 'Accept: application/json' \
  --data-raw 'fullName=Tr%E1%BA%A7n+V%C4%83n+A&note=Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh&quantity=2'
~~~

With `--data-raw`, you supply an **already-encoded body**; do not pass the entire string to `--data-urlencode` again, as `&` delimiters and `%HH` sequences would be re-encoded.

## 11. Matchers, Body Matching, and Stub Flexibility

In SCC, matchers can appear on requests or responses but serve different purposes:

| Side | Purpose | Specifics for Forms |
|---|---|---|
| **Request** | Stub checks whether consumer's request matches the scenario | Body is a form string; must match exact bytes or mapping mechanism |
| **Response** | Generated producer test verifies producer returns right status, headers, body | Response may be JSON; use JSONPath matchers if it is JSON |
| **Client-side logic** | Consumer test verifies client reads response and runs business logic | Use the real HTTP client rather than testing only with `curl` |

In particular, **do not apply JSONPath `$.fullName` to a form body** assuming SCC will parse it like JSON. Inspect how your SCC version generates WireMock mappings for form text. If the project needs to accept multiple equivalent variants of encoding or field ordering, raw-body matching can be overly strict.

For example, these two bodies yield the same decoded data:

~~~text
fullName=Minh+Anh&quantity=2
quantity=2&fullName=Minh%20Anh
~~~

In terms of **form semantics**, both requests have `fullName="Minh Anh"` and `quantity="2"`. In terms of **raw body strings**, they differ in order and space encoding. Therefore:

- If the contract intends to lock down the exact raw body representation, literal matching can be intentional.
- If the contract only aims to verify **decoded name–value pairs**, choose the appropriate form-parameter matching support in your WireMock/SCC version, or add integration tests checking the producer and real HTTP client; never assume SCC normalizes raw bodies automatically.
- Once the stub is generated, inspect the **mapping artifact** to see how it matches the body and which headers it requires.
- Consumer tests should also cover variants with repeated fields, `+`/`%20` spaces, or field order if those are part of compatibility guarantees.

In complex cases, separate two verification layers: contracts assert a **clear sample scenario**, while integration tests verify the encoding variants permitted by the API.

## 12. Edge Cases That Easily Break Compatibility

### 12.1. Literal Plus vs. Space

~~~text
source value:       a+b
encoded value:      a%2Bb
decoded by server:  a+b

source value:       a b
encoded value:      a+b
decoded by server:  a b
~~~

If a client sends an **unescaped** `a+b` in a form body intending a literal plus sign, the server normally decodes it as `a b`. This causes obvious bugs with plus-addressed emails, SKUs containing `+`, or expression strings.

### 12.2. `&` and `=` Inside Values

~~~text
source note: a+b&c=d
wire note:   a%2Bb%26c%3Dd
~~~

Writing `note=a+b&c=d` directly causes the server to split it into two fields `note` and `c`, and turn the plus into a space. This is a **structural request error**, not merely punctuation corruption.

### 12.3. Absent Field vs. Empty Field

~~~text
quantity=2               -> note field is absent
quantity=2&note=          -> note is present, value is empty string
quantity=2&note=%20       -> note is a single space
~~~

The producer may handle these differently, especially when validation specifies `required`, `not blank`, or default values. Write contracts for important cases rather than assuming equivalence.

### 12.4. Multiple Values for the Same Key

~~~text
tag=gift&tag=express&quantity=2
~~~

Form URL-encoded supports **repeating a field name**. In a Spring client, `MultiValueMap` can send multiple values:

~~~java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("tag", "gift");
form.add("tag", "express");
form.add("quantity", "2");
~~~

The producer can receive them via `@RequestParam("tag") List<String> tags` with an appropriate mapping. `Map<String, String>` cannot represent multiple values per key; converting to a regular map drops data.

### 12.5. Line Breaks and Unicode Characters

Newlines, tabs, emojis, or accented characters must be byte-encoded. For example, LF appears as `%0A`; however, a client submitting a textarea may normalize newlines to CRLF before encoding. If a contract must distinguish them precisely, inspect actual requests and agree on normalization rules.

### 12.6. Single Encoding vs. Double Encoding

~~~text
Unicode:          Cà phê sữa
Encoded once:     C%C3%A0+ph%C3%AA+s%E1%BB%AFa
Encoded twice:    C%25C3%25A0%2Bph%25C3%25AA%2Bs%25E1%25BB%25AFa
~~~

The bottom line illustrates the effect of percent-encoding data that was already form-encoded: decoding once on the server leaves literal `%` and `+` characters in the text. Never call `URLEncoder.encode` manually and then pass the result to `FormHttpMessageConverter` if the converter encodes again.

## 13. Java Library When Manually Encoding a Component

When you genuinely need to build part of a form body manually (e.g. for byte-level tests), Java provides `URLEncoder`:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String value = "a+b&c=d";
String encoded = URLEncoder.encode(value, StandardCharsets.UTF_8);

// encoded: a%2Bb%26c%3Dd
~~~

**Important:** `URLEncoder` applies **HTML form encoding** rules, converting spaces to `+`; it is not equivalent in all cases to URI path percent-encoding.

To build a body manually, encode **each name and each value** before joining with `=` and `&`. Never encode the already-concatenated body, because structural delimiters would also be escaped.

~~~java
String body =
    URLEncoder.encode("fullName", StandardCharsets.UTF_8) + "="
    + URLEncoder.encode("Trần Văn A", StandardCharsets.UTF_8)
    + "&"
    + URLEncoder.encode("quantity", StandardCharsets.UTF_8) + "="
    + URLEncoder.encode("2", StandardCharsets.UTF_8);
~~~

In regular application code, **prefer `MultiValueMap` + converter**, as it is less error-prone and supports repeated fields naturally.

## 14. What Generated Producer Tests Must Prove

Suppose the Groovy/YAML contract has been placed in the proper directory and the Spring Cloud Contract build plugin is configured.

Verification flow:

~~~mermaid
flowchart TD
    A["Form contract: POST + headers + raw body"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer test"]
    B --> D["Candidate stub artifact"]
    C --> E["Send real request to producer"]
    E --> F{"Receives form and returns right response?"}
    F -- "No" --> G["Fix config, body, charset, or code"]
    D --> H["Consumer test + Stub Runner"]
    H --> I{"Real client sends proper form?"}
    I -- "No" --> G
    F -- "Yes" --> J["Aggregate CI results"]
    I -- "Yes" --> J
~~~

When opening the generated test, verify specifically:

1. **Method and URL** are `POST /api/reservations/preview`.
2. **Content-Type** of the request is form URL-encoded with the contract's charset.
3. Request body contains **literal `&`** between fields, **`%26`** inside values containing `&`, and expected Unicode encoding.
4. Real producer controller receives and decodes the body properly.
5. Response has status `200`, and JSON contains `Trần Văn A`, `Khuyến mãi 10% & giao nhanh`, and `quantity: 2`.

If the generated test sends a request different from the contract, inspect the test generator of your SCC version, test mode (MockMvc/HTTP/WebTestClient), and base class configuration. For text-body issues, read the **source of the generated test** rather than relying solely on the build exit code.

A green build that **neither generated nor ran** contract tests is not proof that the producer fulfills the contract.

## 15. Stub Runner and Consumer Tests

Once the producer produces a candidate stub, the consumer uses **Stub Runner** to load that artifact. Consumer tests should invoke the **real form client** (e.g. `ReservationClient` using `RestClient`) rather than sending a hand-crafted request tailored to the mapping.

Example Stub Runner configuration in a consumer test:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.2.0-rc1:stubs:8081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class ReservationClientContractTest {
    // Use real ReservationClient pointing to http://localhost:8081.
    // Assert fullName, note, quantity, and status from stub response.
}
~~~

With `LOCAL`, the stub JAR must be installed into the local Maven repository before running tests. If CI splits jobs across runners, use `REMOTE` mode with a configured artifact repository. The version above is illustrative; when checking a PR, use the **exact artifact from the candidate commit** to avoid stale cached versions.

**What to verify in the consumer test:**

- Client sends the form media type, not JSON.
- Client passes **raw strings** to the converter; no double encoding.
- Actual body contains fields and values accepted by the stub.
- Consumer decodes the **JSON response** and uses the business data properly.
- Generated stub mapping reflects the intended request conditions. If an equivalent encoding fails to match the stub, determine whether it is a mapping strictness limitation or an actual consumer bug.

## 16. Which API Changes Can Break Consumers?

| Change | Why Can It Be Breaking? | How to Verify |
|---|---|---|
| Producer switches `consumes` from form to JSON-only | Old consumer still sends `application/x-www-form-urlencoded` and may get 415 | Test with existing form client and candidate producer stub/version |
| Renaming field `fullName` to `recipientName` | Old client does not send the new name; binding/validation may fail | Contract preserves old field; add transition contract |
| Changing `note` from optional to required | Old consumer omitting `note` gets rejected | Add test for request missing `note` |
| Dropping support for repeated `tag` field | Consumer sending multiple values loses data or fails | Test `tag=gift&tag=express` |
| Changing `+` decoding logic or charset | Emails/SKUs with `+`, Vietnamese names may corrupt | Test Unicode, literal plus, and special characters |
| Switching encoding from `+` to `%20` only | Server decodes identically, yet raw-body stub fails to match | Compare decoded fields and WireMock mapping |
| Renaming response JSON field `status` to `state` | Existing consumer may fail to deserialize the field | Run consumer test against candidate stub |

Communication compatibility requires alignment on both **how requests are sent** and **how consumers read responses**. A green producer test after updating to a new contract does not prove old consumers still work.

For major changes like migrating from form to JSON, the safe evolution path is usually **supporting both media types concurrently during a transition window**, testing both old and new clients, and retiring the old format only once no consumers depend on it.

## 17. Common Errors and Troubleshooting

| Symptom | What to Check | Action |
|---|---|---|
| Server receives `"a b"` instead of `"a+b"` | Literal `+` was not encoded as `%2B` | Use form converter or `URLEncoder` per value |
| Server receives `%E1%BA...` instead of Vietnamese text | Client double-encoded or server decoded incorrectly | Pass raw strings to converter; check charset and raw body |
| Controller receives `null` for fields | Wrong `Content-Type`, client sent JSON/query instead of form body, or test mode didn't send real body | Inspect actual HTTP request and controller binding |
| Body turns `&` into `&amp;` in generated test | Escaping bug in test generator/old plugin version | Inspect generated code, upgrade plugin appropriately, avoid HTML-escaping payload |
| Server receives extra unintended fields | `&` inside value was not encoded as `%26` | Encode names and values individually |
| Stub does not match even though real server accepts it | Stub compares raw body, field order, or `+`/`%20` representation differently | Inspect WireMock mapping and actual client raw body |
| CI passes on contract change yet real consumer fails | Stub Runner still uses an old artifact version | Pin candidate version/commit; check stub download logs |
| Error converting `quantity` to `int` | Form sent `two`, empty value, or wrong type | Check validation and create a separate error contract |
| Form does not accept file upload | API expects multipart while client sends URL-encoded | Switch to `multipart/form-data` per API and write separate contract |
| Vietnamese text corrupted after round trip | Inconsistent charset, inconsistent normalization, double encoding | Verify UTF-8 on both ends and bytes in test environment |

Useful diagnostic order: **URL and headers → raw body → percent decoding → controller parameters → generated test → stub mapping → consumer client**.

## 18. Hands-On Exercise: Verifying a Unicode Form

**Context:** Inventory Service accepts a POST form to preview a stock reservation; Checkout Service calls that API with recipient name and note in Vietnamese.

### Round A — Create the Form Contract

1. Write a Groovy or YAML contract for `POST /api/reservations/preview`.
2. Declare `Content-Type: application/x-www-form-urlencoded; charset=UTF-8`.
3. Use values:
   - `fullName = "Trần Văn A"`
   - `note = "Khuyến mãi 10% & giao nhanh"`
   - `quantity = "2"`
4. Encode each value and join the body using form syntax.
5. Declare the JSON response containing the **decoded** values.

**Expected:** generated producer test sends the right body, controller receives proper Vietnamese text, and response satisfies the contract.

### Round B — Verify Consumer's Form Sending

1. Create `ReservationClient` using `MultiValueMap<String, String>`.
2. Put **raw Unicode strings** into the map and let the HTTP converter encode them.
3. Have Stub Runner load the candidate stub from the producer.
4. Run the consumer test with the real client and assert the response.
5. Compare the raw request against the contract, confirming plus signs, percent signs, and ampersands are handled properly.

**Expected:** consumer test proves real code can send the proper form and consume the response.

### Round C — Try a Breaking Change Scenario

1. Rename request field `fullName` to `recipientName` in the producer.
2. Run producer tests against the old contract and observe the mismatch.
3. If you also update the contract to match the producer, generate the new stub and run the old consumer's tests.
4. Propose a plan to support both field names side by side before removing the old name.
5. Try adding a `note` containing a literal plus: `"a+b@example.com"`, verifying it becomes `a%2Bb%40example.com`.

**Submission evidence:** written contract, encoded raw HTTP request, generated test report, candidate stub coordinates, consumer test results, and explanation of root causes for missing encoding or double encoding.

## 19. Checklist Before Merging a Form Contract

- [ ] Request uses the right method, path, and `Content-Type`.
- [ ] Form fields live in the **body** if the API expects a body, not mistakenly placed in query parameters.
- [ ] Unicode strings are UTF-8 encoded per form rules.
- [ ] Spaces, literal plus signs, `&`, `=`, and `%` are handled properly.
- [ ] Client uses `MultiValueMap`/form converter or a verified equivalent encoding approach.
- [ ] No redundant encoding step runs before the HTTP converter processes the data.
- [ ] Absent, empty, and repeated fields are distinguished where business rules require it.
- [ ] Generated producer test actually sends a **form body**, not just query params or JSON.
- [ ] Producer receives and binds decoded fields properly.
- [ ] Stub artifact is generated from the exact candidate contract/commit.
- [ ] Consumer tests use Stub Runner with the **real client** and matching stub version.
- [ ] Equivalent encoding variants are tested if committed by the API.
- [ ] CI blocks release whenever generated producer tests or consumer compatibility tests fail.

## 20. Self-Check Questions

**1. In `application/x-www-form-urlencoded`, how do `+`, `%20`, and `%2B` differ?**

In form values, `+` and `%20` normally decode to a **space**; `%2B` decodes to a **literal plus sign**. A stub inspecting raw bytes can distinguish the three representations.

**2. Why doesn't `note=a+b&c=d` represent a single value `a+b&c=d`?**

Because `+` means space and `&` separates name–value pairs. You must encode the value as `a%2Bb%26c%3Dd` before attaching it after `note=`.

**3. Why shouldn't you write `request.queryParameters` when an API accepts a POST form?**

Query parameters reside in the URL; a POST form resides in the body with its media type. A framework may bind both into similar controller parameters, yet they are **not equivalent at the protocol level** or in consumer requirements.

**4. Why isn't `bodyMatchers.jsonPath('$.fullName', ...)` the default choice for form requests?**

Because `application/x-www-form-urlencoded` has a text body formatted as `key=value&...`, not JSON. JSONPath is defined for JSON structures; you must use form-compatible matching mechanisms and verify the mappings generated by your SCC version.

**5. If consumer tests pass against an earlier stub, is that enough to prove the new producer is compatible?**

No. Tests must pull the **candidate stub generated from the current change's contract/code** to catch changes in fields, `Content-Type`, encoding, or responses.

## 21. References

- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): request/response structure and generating HTTP contracts.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL, matchers, and producer/consumer workflows.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): sending `application/x-www-form-urlencoded` with `RestClient`, `MultiValueMap`, and converters.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): `FormHttpMessageConverter`.
- [HTML Standard — URL-encoded form encoding](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#url-encoded-form-data): encoding/decoding rules for name–value pairs.

Upgrade note: SCC's test generation and stub mapping mechanics can change across plugin versions, especially for text payloads or advanced matchers. Before enforcing raw-body match conditions in CI, inspect the **generated source and stub mapping** of the exact version your project uses.

---

**Key takeaway:** Form URL-encoded consists of **encoded name–value pairs inside the HTTP body**. Spaces, literal plus signs, `&`, `=`, `%`, and UTF-8 determine what values the producer receives. In Spring Cloud Contract, accurately specify **`Content-Type` + raw form body**, run generated producer tests, inspect new stubs, and verify **consumers send real forms** to catch incompatible API changes.
