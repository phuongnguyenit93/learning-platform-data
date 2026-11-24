# JSON Fixtures, Charsets, and Comparison Stability

In Spring Boot testing, a JSON response can be **correct in data yet different in textual representation**. Two JSON objects containing the exact same key–value pairs can differ in key ordering, whitespace, indentation, or Unicode escape notation. Conversely, two strings that look identical on screen can hold different Unicode code points, suffer from wrong character encoding, omit fields, or reorder array elements. If a test compares at the wrong level, it will produce **false reds when formatting changes** or **false greens when the data contract breaks**.

A **JSON fixture** is controlled sample JSON data, typically stored in `src/test/resources`, used as input or expected output for a test. A **charset** defines how bytes map to characters; for JSON exchanged between systems, RFC 8259 requires **UTF-8**. **Comparison stability** demands picking the right strictness: verify JSON content structurally when the contract is semantic data, yet verify raw bytes when there truly is a digital signature, hash, canonicalization, or byte-for-byte payload protocol.

This lesson uses **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5, Jackson, MockMvc, and JSONassert**. The examples distinguish controller slice tests from HTTP integration tests with a real server. They use no database or production APIs. If a project uses Spring Boot 4.x, some dependency packages and test APIs have changed; check version-specific documentation before copying code.

## 1. Learning outcomes

After this lesson, you can:

- Design independent JSON fixtures that are clearly named, small, easy to review, and contract-accurate.
- Distinguish **byte equality**, **string equality**, **JSON structural equality**, and **schema/contract assertions**.
- Understand `application/json`, UTF-8 charset, UTF-8 BOM, newlines, and `\n`, `\"`, `\\`, `\uXXXX` escaping.
- Avoid bugs where Vietnamese text turns into strings like `CÃ  phÃª` or replacement characters `�`.
- Compare Jackson's `JsonNode`, `content().json(...)` with `JsonCompareMode.STRICT/LENIENT`, and JSONPath within their proper boundaries.
- Distinguish object key order from array element order; test `null`, missing, empty string, and empty array data.
- Test numbers, timestamps, timezones, UUIDs, and non-deterministic data without creating flaky tests.
- Write `@WebMvcTest` tests reading classpath fixture files as `byte[]`, parsing via Jackson, and verifying HTTP responses.
- Write `@SpringBootTest(RANDOM_PORT)` HTTP integration tests verifying UTF-8 payloads through a real server.
- Diagnose differences among fixture bugs, encoding bugs, serializer bugs, and business logic bugs.

## 2. One JSON payload can have multiple equivalent representations

These two strings differ character by character:

```json
{"id":7,"title":"Cà phê Việt","tags":["cà phê","sách"]}
```

```json
{
  "tags": ["cà phê", "sách"],
  "title": "Cà phê Việt",
  "id": 7
}
```

Structurally, however, both **objects** have identical fields and values. Member order inside a JSON object is **not considered business ordering**. Comparing the two strings with `assertEquals(json1, json2)` fails solely due to indentation or key order.

Conversely, two arrays:

```json
["BOOK", "PEN"]
```

and:

```json
["PEN", "BOOK"]
```

differ in element order. **A JSON array is an ordered sequence.** If the API specifies "newest first," changing order is a bug to catch. If the API only returns an unordered set, assertions should allow reordering, such as JSONPath combined with Hamcrest `containsInAnyOrder`.

Do not confuse "object-equivalent JSON" with "any difference in JSON can be ignored." These differences still matter:

- Fields deleted, added without permission, or renamed.
- Value `true` turning into `"true"` (boolean to string).
- Number `7` turning into string `"7"`.
- `null` turning into an absent field.
- `["A","B"]` turning into `["B","A"]` when order is contracted.
- Price `216000` turning into `21600`.
- Unicode strings looking identical yet having different normalization forms when consumers use byte/string equality.

## 3. Four comparison levels: choose based on the contract

| Level | What is compared? | Example tools | Use when | Risk |
|---|---|---|---|---|
| **Raw bytes** | Exact byte-for-byte | `assertArrayEquals(byte[], byte[])` | Digital signatures, hashes, canonical JSON, special wire protocols | Too brittle for ordinary JSON responses |
| **Raw text** | Character-by-character after decoding | `assertEquals(String, String)` | Data is text with a mandated formatting | Breaks on whitespace, indent, and key order |
| **JSON structure** | Objects/arrays/values after parsing | `ObjectMapper.readTree`, `JsonNode.equals`, JSONassert | Most HTTP JSON contracts | Requires clear strategy for arrays and numbers |
| **Focused contract** | Selected critical fields/types/absences | `jsonPath`, Jackson predicates, schema validation | Responses with extensible metadata or evolving APIs | Too loose if sensitive fields are missed |

**Default principle:** For typical JSON APIs, start with **structured comparison** or **focused contract assertions**, not `content().string(expectedJson)`.

**True exception:** If the server sends JSON signed over a **specific byte sequence**, a single changed space invalidates the signature; byte equality/canonicalization is then the contract. Never normalize a payload and verify a signature on modified data.

## 4. Where should JSON fixtures live?

In a standard Java Gradle/Maven project:

```text
src/
  main/
    java/
      com/example/fixturejson/
        FixtureJsonApplication.java
        ArticleView.java
        ArticleCatalog.java
        DemoArticleCatalog.java
        ArticleController.java
  test/
    java/
      com/example/fixturejson/
        ArticleControllerFixtureTest.java
        ArticleHttpUtf8IntegrationTest.java
        UnicodeNormalizationTest.java
    resources/
      fixtures/
        article-7.json
```

`src/test/resources/fixtures/article-7.json` lands on the **test runtime classpath** in standard build configurations. Tests load it via `ClassPathResource`; never assume a specific current working directory in CI or IDEs.

**Do:**

- Use explicit paths: `fixtures/article-7.json`.
- Save files as UTF-8 without BOM.
- Choose fixture names reflecting **scenario and version** when variants exist, e.g., `article-paid-v1.json`, `article-with-null-note.json`, or `search-page-2.json`.
- Keep fixtures small enough to review diffs easily; split oversized fixtures by scenario.
- Verify fixtures parse cleanly before using them; syntax errors should fail early.
- Keep expected data **independent of the serializer code under test**; never overwrite fixtures from current responses and treat them as ground truth.

**Do not:**

- Hard-code absolute laptop file paths.
- Place expected output inside production source directories.
- Copy real credentials, tokens, emails, or private data into fixtures.
- Generate expected JSON using the same `ObjectMapper` that serialized the object in the test path and assert equality—that turns the check into a tautology.
- Use one "master" JSON fixture with thousands of fields for every test, causing minor changes to break the whole suite.

## 5. UTF-8 is the byte contract of exchanged JSON

According to **RFC 8259, section 8.1**, JSON text exchanged between systems outside a closed ecosystem must use **UTF-8**. `application/json` does not require a `charset` parameter for clients to know the JSON body is UTF-8 encoded. Network JSON generators **must not add a UTF-8 BOM** at the start of JSON; parsers may tolerate BOMs for compatibility, yet generators must not rely on it.

A valid response can look like:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"title":"Cà phê Việt"}
```

It does not have to include:

```http
Content-Type: application/json;charset=UTF-8
```

Therefore:

- **Verify media type** using `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)` when the contract does not mandate a charset parameter.
- **Verify UTF-8 payload** by reading `byte[]` and decoding with a `CharsetDecoder` configured with **REPORT** on malformed/unmappable data, or parsing bytes directly with Jackson.
- Do not assert `getCharacterEncoding()` equals `"UTF-8"` as a universal requirement for every `application/json` response when the controller/converter sets no explicit charset.
- Do not confuse the **mock servlet response's** `ISO-8859-1` fallback when calling `getContentAsString()` with the actual encoding Jackson wrote to JSON bytes.

### 5.1. Different byte sequences can distort the same Unicode string

The letter `à` in UTF-8 has different bytes from a single-byte Latin-1 encoding. If UTF-8 bytes are decoded as ISO-8859-1, readers see `CÃ `. That is **mojibake**, not Jackson altering business data.

Correct flow:

```text
Java String (Unicode)
    |
    | Jackson JSON serialization (UTF-8 bytes)
    v
HTTP response byte[]
    |
    | Client reads as UTF-8, parses JSON escapes
    v
Java String (Unicode) containing the same content
```

Broken flow:

```text
UTF-8 byte[] --> decoded assuming ISO-8859-1 --> CÃ  phÃª
```

Hence, when debugging garbled Vietnamese text, start from **`byte[]` and media type** rather than jumping to conclusions from strings printed in logs or test reports.

## 6. UTF-8 BOM and external fixtures

A UTF-8 BOM is the three-byte sequence `EF BB BF` at the start of a file, often added by editors or exporters. RFC 8259 states generators **must not** emit a BOM in JSON sent over the network. For local fixtures, the safest practice is **saving UTF-8 without BOM** for consistent tooling.

**Possible symptoms:** one parser handles the BOM while another rejects it; a snapshot looks normal yet the parser reports an unexpected character at position 0. Never strip three bytes blindly from every request and assume the problem is solved: you may hide upstream data corruption or misprocess other encodings.

When you genuinely need to detect a BOM:

```java
// Snippet placed in a test with variable byte[] bytes:
boolean utf8Bom = bytes.length >= 3
        && (bytes[0] & 0xFF) == 0xEF
        && (bytes[1] & 0xFF) == 0xBB
        && (bytes[2] & 0xFF) == 0xBF;

assertFalse(utf8Bom, "Fixture must be UTF-8 without BOM");
```

This is a snippet, not a standalone method/class; `assertFalse` is from JUnit Jupiter. The full test suite also checks for a BOM. If a fixture comes from an external system whose contract permits a BOM, handle it based on the real format rather than an arbitrary rule.

## 7. Escaping and Unicode: read values after parsing

The same string can appear as direct Unicode or JSON escapes:

```json
{"city":"Đà Nẵng"}
```

and:

```json
{"city":"\u0110\u00e0 N\u1eb5ng"}
```

both parse to the string **`Đà Nẵng`**. That is why raw text comparison falsely reports differences on equivalent data.

Important escapes:

| In JSON source | After JSON parser reads | When used |
|---|---|---|
| `\"` | Double quote `"` inside string | String containing quotes |
| `\\` | Single backslash character | Windows paths, regex literals |
| `\n` | Line feed (LF) newline character | Multi-line text |
| `\t` | Tab character | Tabbed text |
| `\r` | Carriage return | Certain line endings |
| `\u00e0` | Character `à` | Valid Unicode escape |
| `\uD83D\uDE00` | Emoji `😀` | Surrogate pair for non-BMP code points |

**Watch escaping layers:** a JSON snippet can be a **file**; a Java string holding JSON adds a **Java escape layer**; a regex adds another layer. When storing fixtures in `src/test/resources/*.json`, do not double-escape quotes just for the Java compiler.

Example **JSON fixture file**, where `summary` contains quotes and a newline:

```json
{
  "summary": "Dòng 1: \"đậm\"\nDòng 2 😀"
}
```

After parsing, the Java string contains **actual quotes and an actual newline**:

```java
String expected = "Dòng 1: \"đậm\"\nDòng 2 😀";
```

This Java line has the required escapes—**one backslash per escape in source code**; Java turns `\n` into LF. **Do not write `\\"` for a quote inside a Java string**: two backslashes before a quote end the string unexpectedly. In a JSON fixture file, `\"` and `\n` are interpreted by the JSON parser.

## 8. Unicode normalization: looking alike does not mean equal

Unicode allows certain characters to be encoded in multiple visually equivalent ways:

- `"é"` can be a single precomposed code point `U+00E9`.
- `"e"` + combining acute accent `U+0301` can look identical to `é`.
- Java `String.equals` compares **code unit sequences**, without automatic Unicode normalization.
- JSON parsers are not obligated to normalize strings; serialization also does not guarantee visually identical forms compare equal.

Example:

```java
import java.text.Normalizer;

String composed = "é";
String decomposed = "e\u0301";

boolean before = composed.equals(decomposed); // false
boolean after = Normalizer.normalize(
        composed, Normalizer.Form.NFC).equals(
        Normalizer.normalize(decomposed, Normalizer.Form.NFC)); // true
```

This is a snippet inside a Java method; the complete test is in section 17.

**Important:** Never silently normalize all data just to make tests pass. For usernames, file paths, search terms, or digital signatures, normalization can be a **business rule** that both sides must agree on. For raw signatures/HMACs, normalizing before verification breaks the signature and must never alter the payload.

## 9. Object key order and array order

In a JSON object, key order is **not data order**. Jackson's `JsonNode` compares objects by field/value mapping regardless of key order. In a JSON array, `ArrayNode` preserves element order and equality checks order.

Example:

```json
{"id":7,"tags":["cà phê","sách"]}
```

versus:

```json
{"tags":["cà phê","sách"],"id":7}
```

are structurally equivalent.

However:

```json
{"id":7,"tags":["sách","cà phê"]}
```

reorders the `tags` array. If `tags` has **no contracted order**, tests can extract `$.tags` and assert Hamcrest `containsInAnyOrder("cà phê", "sách")`. If the API specifies priority ordering, use `contains("cà phê", "sách")` or strict structural JSON comparison.

**Note:** `JsonNode.equals` can also distinguish specific numeric node types based on how Jackson parsed/represented them; do not substitute it for a domain comparator with custom tolerances/semantics. When floats or large IDs matter, choose explicit comparison rules rather than assuming all numeric representations compare equal.

## 10. `null`, missing, empty: four distinct contracts

Suppose an API returns:

```json
{
  "note": null,
  "nickname": "",
  "tags": [],
  "active": false
}
```

Distinguish:

| Representation | Meaning | Jackson assertion |
|---|---|---|
| `"note": null` | Field present, value null | `root.has("note")` and `root.get("note").isNull()` |
| No `note` | Field absent | `!root.has("note")` |
| `"nickname": ""` | Empty string | `root.required("nickname").asText().equals("")` |
| `"tags": []` | Empty array | `root.required("tags").isArray()` and `size()==0` |
| `"active": false` | Boolean false | `root.required("active").isBoolean()` and `!booleanValue()` |

Spring/Jackson can configure `@JsonInclude(Include.NON_NULL)` or a global inclusion policy causing null fields to **be omitted**. If the API contract requires `note: null`, switching to `NON_NULL` is a contract change and tests should turn red. If the contract allows omitting the field, do not force it to always appear.

In MockMvc JSONPath:

- `hasJsonPath()` checks the path is present **including null**.
- `exists()` checks there is a **non-null value**.
- `doesNotExist()` accepts null or an absent non-null value.
- `doesNotHaveJsonPath()` checks the path is **completely absent**, rejecting null as well.

For an object property, `hasJsonPath()` + `doesNotExist()` distinguishes explicit null from missing on a definite path. Jackson's `JsonNode` expresses this rule even more clearly.

## 11. Comparing JSON with `JsonNode` and JSONAssert

### 11.1. Jackson tree equality

```java
JsonNode expected = mapper.readTree(fixtureBytes);
JsonNode actual = mapper.readTree(responseBytes);
assertEquals(expected, actual);
```

This is a snippet, not a full Java class. It ignores whitespace and object key order, while detecting array ordering, field values, and node absence/presence. Ideal when the fixture describes the **entire response contract**.

### 11.2. JSONAssert strict vs lenient

In Spring Framework 6.2, `content().json(expectedJson, JsonCompareMode.STRICT)` and `LENIENT` perform JSON comparison rather than raw string equality, backed by Spring's JSONassert integration.

| Mode | Extra fields in object | Array order | Use when |
|---|---|---|---|
| `STRICT` | Rejected | Enforced | Fixed response schema, preventing unexpected field exposure |
| `LENIENT` | Allowed | Not enforced | Extensible API, checking only key fields |

**STRICT does not mean byte equality.** Indentation and object key order still do not matter. **LENIENT does not mean anything goes:** fields/values listed in `expected` must still match per the comparator.

A strict test against an expected payload with `note: null` catches if the serializer drops the field or sends an empty string. For APIs permitting extensible metadata, combine lenient mode with absence assertions on sensitive fields.

**Easy point of confusion:** some JSONAssert methods compare arrays using mode-specific algorithms and do not magically handle arbitrary unordered arrays of objects. For collections with IDs, match items by key/object per contract or map ID → object before asserting. Do not treat LENIENT as a cure-all for order differences.

### 11.3. JSONPath for a focused contract

```java
mvc.perform(get("/api/articles/{id}", 7L))
        .andExpectAll(
                status().isOk(),
                jsonPath("$.id").value(7),
                jsonPath("$.title").value("Cà phê Việt ☕"),
                jsonPath("$.tags").isArray(),
                jsonPath("$.tags[0]").value("cà phê"));
```

Snippet inside a `@Test` with `MockMvc mvc`, imports, and stubbed collaborator ready. When responses carry extensible metadata, JSONPath makes tests **less brittle** than full strict JSON. However, JSONPath alone misses extra fields; add negative assertions for sensitive fields or schema checks when needed.

## 12. Fixture strategy: input, output, and edge cases

No single fixture file fits every check.

**Input fixtures** are useful for complex request payloads:

- Examples: `order-create-valid.json`, `order-create-missing-name.json`, or `order-create-unknown-currency.json`.
- Inputs must mirror the **request schema** real clients send, never copying server JPA entities.
- Sending `byte[]` from a fixture tests charsets, JSON parsing, and validation across the HTTP boundary.

**Expected output fixtures** describe public responses:

- Contain only permitted fields and reviewed values.
- Omit tokens, dynamic timestamps, or random IDs unless fixed in test.
- Can be versioned alongside the API, e.g. `article-response-v1.json`.
- When contracts allow extensible fields, use partial assertions instead of rigid full-response strictness.

**Negative fixtures** are intentionally invalid:

- Malformed JSON, unsupported media types, wrong field types, special Unicode edge cases.
- Name them after the expected failure, e.g. `invalid-json-trailing-comma.json`.
- Never share one broken input file across a dozen error branches, as failure reasons become ambiguous.

**Regression fixtures** reproduce real sanitized bugs: broken quote escapes, lost newlines, emoji turned into `?`, dropped nulls, wrong monetary values, or leaked sensitive fields. Document the scenario clearly so future maintainers know why the fixture exists.

## 13. When should you avoid creating a separate JSON fixture?

A test with short expectations:

```java
assertEquals("PAID", result.status());
assertEquals(216_000L, result.totalVnd());
```

does not need an `expected-42.json` file if the target is just a domain object. Even with JSON:

```java
mvc.perform(get("/api/health"))
        .andExpect(jsonPath("$.status").value("UP"));
```

one JSONPath suffices when a health contract does not have dozens of fields.

Use fixture files when they genuinely aid **readability, reuse, review, or encoding/schema testing**. Use builders/factories for Java objects when test inputs have many variations. Never use JSON files to avoid writing clear assertions on business outcomes.

## 14. Runnable example: controller, UTF-8 fixture, and two-level tests

We build an article API:

- `GET /api/articles/7` returns `ArticleView` with Vietnamese diacritics, emoji, quotes, newlines, an array, a fixed timestamp, and `note: null`.
- `GET /api/articles/999` returns 404 with an empty body.
- `POST /api/articles/echo` echoes back the deserialized `ArticleView` to test UTF-8 requests and JSON converters (this is a demo endpoint, **not a production pattern** to expose publicly).
- `ArticleCatalog` is a port; the MVC slice test mocks it, while the full HTTP integration test runs the real in-memory adapter.

### 14.1. File structure

```text
src/main/java/com/example/fixturejson/
  FixtureJsonApplication.java
  ArticleView.java
  ArticleCatalog.java
  DemoArticleCatalog.java
  ArticleController.java
src/test/java/com/example/fixturejson/
  ArticleControllerFixtureTest.java
  ArticleHttpUtf8IntegrationTest.java
  UnicodeNormalizationTest.java
src/test/resources/fixtures/
  article-7.json
```

All sources use `package com.example.fixturejson;`. The fixture is named `article-7.json` and must be saved as UTF-8 without BOM. The code blocks in sections 14 through 17 define **complete files** usable in a Spring Boot 3.5 project with the dependencies in section 25. Isolated snippets elsewhere are illustrative only.

### 14.2. Application root

**`src/main/java/com/example/fixturejson/FixtureJsonApplication.java`**

```java
package com.example.fixturejson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FixtureJsonApplication {

    public static void main(String[] args) {
        SpringApplication.run(FixtureJsonApplication.class, args);
    }
}
```

### 14.3. Immutable response DTO

**`src/main/java/com/example/fixturejson/ArticleView.java`**

```java
package com.example.fixturejson;

import java.time.Instant;
import java.util.List;

public record ArticleView(
        long id,
        String title,
        String city,
        String summary,
        List<String> tags,
        Instant publishedAt,
        String note) {
}
```

Why `record`: the DTO has explicit fields, avoids JPA lazy-loading coupling, and Jackson in Spring Boot 3.5 serializes/deserializes Java records cleanly. `Instant` renders as an ISO-8601 string under typical default Boot/Jackson configuration; tests fix the value to avoid runtime clock dependency.

### 14.4. Port for the controller

**`src/main/java/com/example/fixturejson/ArticleCatalog.java`**

```java
package com.example.fixturejson;

import java.util.Optional;

public interface ArticleCatalog {
    Optional<ArticleView> findById(long id);
}
```

### 14.5. In-memory adapter so the full application runs

**`src/main/java/com/example/fixturejson/DemoArticleCatalog.java`**

```java
package com.example.fixturejson;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DemoArticleCatalog implements ArticleCatalog {

    @Override
    public Optional<ArticleView> findById(long id) {
        if (id != 7L) {
            return Optional.empty();
        }

        return Optional.of(new ArticleView(
                7L,
                "Cà phê Việt ☕",
                "Đà Nẵng",
                "Dòng 1: \"đậm\"\nDòng 2 😀",
                List.of("cà phê", "sách"),
                Instant.parse("2026-11-08T10:15:30Z"),
                null));
    }
}
```

**Checking Java escapes:** the literal `"Dòng 1: \"đậm\"\nDòng 2 😀"` contains one `\"` per inner double quote and `\n` for a newline. At runtime, `summary` holds actual quotes, an actual newline, and the emoji. This is **valid Java source syntax**, not double-escaped JSON text.

The adapter has `@Repository` so Spring's full context registers it; it **does not access a database**. Thus the full HTTP test exercises the real implementation without claiming to verify SQL/JPA. In `@WebMvcTest`, this collaborator lies outside the web slice and is replaced by a Mockito mock at the test boundary.

### 14.6. Real HTTP controller

**`src/main/java/com/example/fixturejson/ArticleController.java`**

```java
package com.example.fixturejson;

import java.util.Optional;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/articles")
public class ArticleController {
    private final ArticleCatalog catalog;

    public ArticleController(ArticleCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ArticleView> get(@PathVariable long id) {
        Optional<ArticleView> view = catalog.findById(id);
        return view.map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ArticleView echo(@RequestBody ArticleView view) {
        return view;
    }
}
```

The controller never manually interferes with charsets by calling `String.getBytes()`; Spring MVC and the Jackson HTTP message converter handle JSON serialization. `produces = application/json` and `consumes = application/json` define the media-type contract without forcing a charset parameter in the response header.

The `echo` endpoint exists solely to illustrate request/response round-trip behavior; production apps must apply validation/authorization and never echo untrusted data unnecessarily.

## 15. JSON fixture file: independent data to review

**`src/test/resources/fixtures/article-7.json`**

```json
{
  "id": 7,
  "title": "Cà phê Việt ☕",
  "city": "Đà Nẵng",
  "summary": "Dòng 1: \"đậm\"\nDòng 2 😀",
  "tags": ["cà phê", "sách"],
  "publishedAt": "2026-11-08T10:15:30Z",
  "note": null
}
```

This file must be **saved strictly as UTF-8 without BOM**. Even though the code fence displays `\n`, the JSON source contains **two ASCII characters: backslash and `n`** inside the string; the JSON parser reads them as a **newline character**. Never insert a literal newline inside an unescaped JSON string: JSON forbids raw control character `U+000A` inside strings.

**This is an independent expected payload:** human-reviewed; never generate it inside tests by calling `mapper.writeValueAsString(articleFromProduction)` and treating it as ground truth for the serializer under test.

### 15.1. When a fixture detects an unexpected field

A strict `JsonNode` comparison catches extra fields present in actual yet absent from the fixture, and vice versa. That is valuable for fixed schemas. If the API allows extensible metadata, use a fixture containing only the critical fields with JSONAssert `LENIENT` or JSONPath; never relax a security contract that must be strictly enforced.

## 16. Complete MVC slice test: fixtures, charsets, and stable comparison

**`src/test/java/com/example/fixturejson/ArticleControllerFixtureTest.java`**

```java
package com.example.fixturejson;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.contains;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ArticleController.class)
class ArticleControllerFixtureTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    ArticleCatalog catalog;

    private static ArticleView sample() {
        return new ArticleView(
                7L,
                "Cà phê Việt ☕",
                "Đà Nẵng",
                "Dòng 1: \"đậm\"\nDòng 2 😀",
                List.of("cà phê", "sách"),
                Instant.parse("2026-11-08T10:15:30Z"),
                null);
    }

    private static byte[] fixtureBytes() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("fixtures/article-7.json");
        try (InputStream input = resource.getInputStream()) {
            return input.readAllBytes();
        }
    }

    private static String fixtureText() throws IOException {
        return new String(fixtureBytes(), StandardCharsets.UTF_8);
    }

    private void stubArticle() {
        when(catalog.findById(7L))
                .thenReturn(Optional.of(sample()));
    }

    @Test
    void comparesResponseAsJsonTreeNotRawText()
            throws Exception {
        stubArticle();

        MvcResult result = mvc.perform(get("/api/articles/7")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpectAll(
                        status().isOk(),
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON),
                        jsonPath("$.title").value("Cà phê Việt ☕"),
                        jsonPath("$.tags",
                                contains("cà phê", "sách")))
                .andReturn();

        JsonNode expected = mapper.readTree(fixtureBytes());
        JsonNode actual = mapper.readTree(
                result.getResponse().getContentAsByteArray());

        assertEquals(expected, actual);
        assertEquals("Đà Nẵng", actual.required("city").asText());
        assertTrue(actual.required("id").isIntegralNumber());
        assertTrue(actual.has("note"));
        assertTrue(actual.get("note").isNull());
        assertFalse(actual.has("internalToken"));
    }

    @Test
    void strictStructuralComparisonCatchesUnexpectedFields()
            throws Exception {
        stubArticle();

        mvc.perform(get("/api/articles/7"))
                .andExpect(status().isOk())
                .andExpect(content().json(
                        fixtureText(), JsonCompareMode.STRICT));
    }

    @Test
    void lenientComparisonAllowsAdditionalPublicFields()
            throws Exception {
        stubArticle();

        mvc.perform(get("/api/articles/7"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "id": 7,
                          "title": "Cà phê Việt ☕"
                        }
                        """, JsonCompareMode.LENIENT))
                .andExpect(jsonPath("$.internalToken").doesNotHaveJsonPath());
    }

    @Test
    void decodesActualResponseBytesAsValidUtf8()
            throws Exception {
        stubArticle();

        MvcResult result = mvc.perform(get("/api/articles/7"))
                .andExpect(status().isOk())
                .andReturn();

        byte[] payload = result.getResponse().getContentAsByteArray();

        String decoded = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(payload))
                .toString();

        JsonNode actual = mapper.readTree(decoded);
        assertEquals("Cà phê Việt ☕",
                actual.required("title").asText());
        assertEquals("Dòng 1: \"đậm\"\nDòng 2 😀",
                actual.required("summary").asText());
        assertEquals("Đà Nẵng", actual.required("city").asText());
    }

    @Test
    void acceptsUtf8FixtureRequestAndEchoesSemanticJson()
            throws Exception {
        byte[] requestBytes = fixtureBytes();

        MvcResult result = mvc.perform(post("/api/articles/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(requestBytes))
                .andExpectAll(
                        status().isOk(),
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON))
                .andReturn();

        JsonNode expected = mapper.readTree(requestBytes);
        JsonNode actual = mapper.readTree(
                result.getResponse().getContentAsByteArray());

        assertEquals(expected, actual);
    }

    @Test
    void rejectsMissingArticleWith404AndNoJsonBody()
            throws Exception {
        when(catalog.findById(999L))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/articles/999"))
                .andExpectAll(
                        status().isNotFound(),
                        content().string(""));
    }

    @Test
    void fixtureHasNoBomAndIsParseableJson()
            throws Exception {
        byte[] bytes = fixtureBytes();

        assertTrue(bytes.length > 3);
        boolean bom = (bytes[0] & 0xFF) == 0xEF
                && (bytes[1] & 0xFF) == 0xBB
                && (bytes[2] & 0xFF) == 0xBF;
        assertFalse(bom);

        JsonNode root = mapper.readTree(bytes);
        assertNotNull(root);
        assertEquals("Cà phê Việt ☕",
                root.required("title").asText());
    }

    @Test
    void objectKeyOrderAndWhitespaceDoNotChangeJsonValue()
            throws Exception {
        String compact = """
                {"id":7,"tags":["cà phê","sách"]}
                """;
        String prettyReordered = """
                {
                  "tags": ["cà phê", "sách"],
                  "id": 7
                }
                """;

        assertFalse(compact.equals(prettyReordered));
        assertEquals(mapper.readTree(compact),
                mapper.readTree(prettyReordered));
    }
}
```

### 16.1. Why use `getContentAsByteArray()`?

`MockHttpServletResponse.getContentAsString()` uses the charset declared by the response; if none is declared, the mock response applies a **fallback encoding** (Spring Test has used ISO-8859-1 as default across many versions), which can mangle UTF-8 Vietnamese text. Reading `byte[]` and parsing via Jackson **avoids an unnecessary string-decoding step**.

If you genuinely need a string for debugging:

```java
// Snippet in a test with MvcResult result:
String decodedWithFallback = result.getResponse()
        .getContentAsString(StandardCharsets.UTF_8);
```

The `getContentAsString(Charset fallbackCharset)` overload uses the specified fallback **when the response declares no charset**. To catch invalid UTF-8 instead of emitting replacement characters, use `CharsetDecoder` with `CodingErrorAction.REPORT` as in the full example.

**Do not assert by default that raw responses must contain emoji unescaped**: a serializer may choose JSON escapes while parsers still produce the exact same Unicode string. Tests should verify the **parsed value** and **valid UTF-8 byte sequence**; check specific escaping only when that is part of the contract.

### 16.2. Why do both strict and lenient tests exist?

They illustrate two contract styles:

- `strictStructuralComparisonCatchesUnexpectedFields` guards the **entire JSON fixture**, including `note:null` and the ordered `tags` list.
- `lenientComparisonAllowsAdditionalPublicFields` checks only `id` and `title` while still forbidding `internalToken`. It suits endpoints permitting extensible metadata.
- In real projects, **do not write both tests for every endpoint out of habit**. Pick the level matching the contract, and add focused assertions for special risks.

### 16.3. Why is the echo test insufficient to prove business logic?

`POST /echo` verifies bytes → Jackson deserialize → DTO → Jackson serialize. It can stay green even if production repositories, moderation policies, or access checks are broken, because none of that logic runs along the path. Write separate service/integration tests for business contracts.

### 16.4. Test count and independence

`ArticleControllerFixtureTest` has **8** test methods. Mockito stubbing is set up independently per method; fixture data is read from the classpath without mutation. Tests need no execution ordering. If adding mutable fakes or a database, add dedicated cleanup/fixture isolation.

## 17. Pure Java/JUnit Unicode normalization test

To test a charset/Unicode detail without Spring:

**`src/test/java/com/example/fixturejson/UnicodeNormalizationTest.java`**

```java
package com.example.fixturejson;

import java.text.Normalizer;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class UnicodeNormalizationTest {

    @Test
    void visuallyEqualStringsCanHaveDifferentCodePoints() {
        String composed = "é";
        String decomposed = "e\u0301";

        assertNotEquals(composed, decomposed);

        assertEquals(
                Normalizer.normalize(composed, Normalizer.Form.NFC),
                Normalizer.normalize(decomposed, Normalizer.Form.NFC));
    }
}
```

This test **does not modify data** and does not claim every app must normalize to NFC. It illustrates that **String equality ≠ visual equality**. If the contract specifies normalization, enforce it at the real boundary/service and test with non-BMP inputs, combining marks, Vietnamese diacritics, and matching search/case-folding inputs.

## 18. HTTP integration test: verifying response bytes through a real server

`MockMvc` passes through Spring MVC without **opening a TCP socket**. When you must verify the full Boot context plus HTTP server encode responses properly, use a `RANDOM_PORT` test with a client receiving `byte[]`.

**`src/test/java/com/example/fixturejson/ArticleHttpUtf8IntegrationTest.java`**

```java
package com.example.fixturejson;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = FixtureJsonApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ArticleHttpUtf8IntegrationTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ObjectMapper mapper;

    @Test
    void realHttpResponseMatchesReviewedUtf8Fixture()
            throws Exception {
        ResponseEntity<byte[]> response = rest.getForEntity(
                "/api/articles/7", byte[].class);

        assertEquals(200, response.getStatusCode().value());

        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(MediaType.APPLICATION_JSON
                .isCompatibleWith(contentType));

        byte[] actualBytes = response.getBody();
        assertNotNull(actualBytes);

        JsonNode actual = mapper.readTree(actualBytes);
        JsonNode expected;
        try (InputStream input = new ClassPathResource(
                "fixtures/article-7.json").getInputStream()) {
            expected = mapper.readTree(input);
        }

        assertEquals(expected, actual);
        assertEquals("Đà Nẵng",
                actual.required("city").asText());
    }
}
```

**Differences from the MVC slice:**

- A real embedded HTTP server starts on Boot's random port.
- The full Spring context wires the real `DemoArticleCatalog`, with no Mockito mock for the port.
- The response is received as **raw HTTP body bytes**, without `TestRestTemplate` converting to `String` before Jackson parses it.
- The fixture is read independently by Jackson and compared against the response tree.
- The test proves Spring Boot → controller → demo adapter → Jackson → HTTP server/client works within this model.

**It does not prove production SQL, external HTTP, or authentication**, since the example uses none. With a real database, `RANDOM_PORT` tests require an isolated database and explicit cleanup; `@Transactional` on the JUnit method does not automatically roll back writes committed by server requests running on separate threads/transactions.

## 19. Stability of numbers and JSON fixtures

Numeric data is a common source of false positives and false negatives:

```json
{
  "quantity": 2,
  "priceVnd": 216000,
  "rate": 0.075,
  "bigIdentifier": "9007199254740993"
}
```

- `quantity` is an integer, not string `"2"`.
- `priceVnd` uses integer VND; in real systems, clarify currency, minor units, and rounding policies.
- `rate` is a decimal; using `double` for money or asserting floating-point exact equality can suffer rounding errors.
- `bigIdentifier` uses a string to avoid precision loss in JavaScript clients with safe-integer limits; this is an **API contract decision**, not a rule that all IDs must be strings.
- When Java uses `BigDecimal`, specify how it serializes, whether scale is preserved, and whether comparisons check numeric value or textual representation.

**Example:** `BigDecimal("1.0").equals(BigDecimal("1.00"))` is false due to different scale, even though `compareTo` returns 0. Jackson may choose different numeric node types; `JsonNode` tree equality does not replace a full money-domain comparator. When precision matters, assert using `BigDecimal`/money types with explicit rules rather than just text or `double`.

**Never compute fixture values using non-deterministic or mirrored math in tests and assert against output computed the same way.** Expected values must be independent enough to catch domain bugs.

## 20. Timestamps, timezones, and dynamic data

A fixture containing a hard-coded timestamp:

```json
{
  "publishedAt": "2026-11-08T10:15:30Z"
}
```

is stable because the example uses `Instant.parse("2026-11-08T10:15:30Z")`. If a production service uses `Instant.now()`, the expected value changes on every run.

**Risks:**

- Laptop and CI system default timezones differ.
- `LocalDateTime` has no offset, yet clients mistake it for UTC.
- Serializers may emit epoch milliseconds, ISO text, or different fractional seconds depending on config.
- DB-generated timestamps may differ in precision from the JVM.
- Tests capturing current time before/after an HTTP call suffer races or millisecond skew.

**Solution:** inject `Clock` and use `Clock.fixed(...)` in tests, or supply deterministic fixture timestamps to the domain. If current time is part of the test semantics, assert reasonable range bounds or boundary handling rather than hard-coding `Instant.now()`.

The same applies to UUIDs, `HashMap` order, random numbers, and auto-increment IDs: fix test inputs, use seeded generators where appropriate, or assert invariants/schemas instead of snapshots holding unstable values.

## 21. "Expected" must be independent of the code producing "actual"

An anti-pattern:

```java
// ANTI-PATTERN: same serializer produces expected and actual,
// so serializer config bugs can repeat on both sides.
String expected = mapper.writeValueAsString(serviceResult);
String actual = mapper.writeValueAsString(serviceResult);
assertEquals(expected, actual);
```

This test essentially compares an expression with itself. Another anti-pattern:

```java
// ANTI-PATTERN: snapshot updated from current response
// without reviewing schema/data changes.
Files.writeString(snapshotPath, responseBody);
assertEquals(Files.readString(snapshotPath), responseBody);
```

It always passes even when the response has bugs. **Fixtures should be human-reviewed or generated from an independent source under strict approval.** Tools can draft an initial file, yet expected payloads must be verified before becoming a baseline.

In the runnable code, the input object is stubbed in `@WebMvcTest`, while the JSON fixture in `src/test/resources` is separate text. This tests both the serializer and response shape. However, the slice test still leaves the real `DemoArticleCatalog` untested—hence `ArticleHttpUtf8IntegrationTest`.

## 22. Serializer changes can break contracts even when DTOs stay unchanged

Serialization changes that tests must guard against:

| Change | Possible impact | Which test catches it? |
|---|---|---|
| `@JsonProperty("published_at")` | Field renamed | Strict fixture, JSONPath |
| `@JsonInclude(NON_NULL)` | Omits `note:null` | Strict fixture, `JsonNode.has("note")` |
| Custom naming strategy | `totalVnd` becomes `total_vnd` | Contract JSON tests |
| Timezone/date module | ISO timestamp becomes array/number or different format | Fixture/field assertions |
| Different `ObjectMapper` module | Enum/record/Java Time output changes | Serialization/HTTP tests |
| Security-sensitive DTO field added | Accidentally exposes `internalToken` | Strict fixture or absence assertions |
| Collection order changed | `items` array reordered | Strict array contract or sorted assertions |
| Encoder breaks UTF-8 | Vietnamese characters/emojis corrupted | Raw-byte UTF-8 decoder + parsed values |
| Auto-configuration differs between slice/full context | Mock slice passes, full app returns wrong output | Full HTTP integration test |

**Not every change is a bug.** APIs may permit additive fields, or serializers may alter harmless whitespace. Lock down the **public contract**, not every implementation detail.

## 23. Mistakes that easily make JSON tests flaky

### 23.1. Relying on `HashMap` or DB order

If a JSON array is built from an unordered collection, asserting fixed indices turns red intermittently. Either **define sorting in production** when order is contracted, or use order-insensitive assertions when it is not.

### 23.2. Relying on machine language/locale

Dates, decimal separators, and error messages can depend on `Locale`. When the API contract specifies Vietnamese or English, explicitly set locale/`Accept-Language` or fixed formatters rather than depending on OS locale.

### 23.3. Relying on default timezone

`OffsetDateTime`, `ZonedDateTime`, and `Instant` have different semantics. When a DTO only needs a UTC timestamp, use `Instant` or an explicit zone format. Never compare `LocalDateTime.now()` strings against `Z`.

### 23.4. Mixing file and response charsets

A UTF-8 fixture read with `Files.readString(path)` with API/version-dependent defaults, or a client decoding as ISO-8859-1, breaks characters. Use `Files.readString(path, UTF_8)` for filesystem reads and `ClassPathResource`/`byte[]` for test classpath resources; parse JSON directly from bytes whenever possible.

### 23.5. Modifying fixtures during a test run

Tests that overwrite fixtures/snapshots used as expected data destroy independence. Expected files are **read-only test data**; never rewrite or auto-accept them in CI.

### 23.6. Oversized JSON snapshots

A 5,000-line file holding timestamps, environment URLs, random IDs, and exception stack traces triggers constant false alarms. Split small fixtures per scenario or assert contracted fields. If full snapshots are necessary, normalize dynamic fields using **explicit, reviewed rules**.

### 23.7. Unicode strings looking alike with different code points

A fixture copied from docs might contain combining marks while code produces precomposed characters. `String.equals` fails even though visually they look identical. If the contract mandates a normalized form, normalize in the app and assert; otherwise define the encoding/normalization policy rather than arbitrarily altering tests.

## 24. Layer-by-layer debugging

When a fixture comparison test fails, never immediately update the fixture to match actual. Check in order:

1. **Status/Content-Type:** is the response `200` and `application/json`? If 404/500/HTML error, it is not a charset bug yet.
2. **Actual byte length + UTF-8 decode:** inspect `byte[]`; test with a strict UTF-8 decoder; check for a BOM or invalid sequences.
3. **Parse JSON:** parse both fixture and response with the same parser to confirm both are valid JSON.
4. **Check shape:** did object/array root, missing/null, or field types change?
5. **Check values:** did Vietnamese text, numbers, booleans, or timestamps actually change?
6. **Check order:** is the difference object key order, array order, or formatting? Only array order can be a business contract.
7. **Check expected:** is the independent fixture still accurate per API docs?
8. **Check sources of nondeterminism:** system clock, random values, DB sort, locale, env, profile, timezone, shared data.
9. **Check matcher strictness:** strict JSON, lenient JSON, JSONPath, byte equality, or raw string?
10. **Check test boundary:** did the real service run? Was the fixture derived from actual? Do slice and full contexts differ?

### 24.1. Symptom table

| Symptom | Possible cause | Investigation step |
|---|---|---|
| `CÃ  phÃª` appears | UTF-8 bytes decoded as Latin-1 | Grab `byte[]`, decode cleanly as UTF-8 |
| `�` appears | Invalid byte sequence or decoder replacement | Use `CharsetDecoder.REPORT` |
| Jackson reports unexpected character at start | BOM/wrong encoding/stray character in file | Inspect leading bytes, save UTF-8 without BOM |
| Expected JSON string differs on newline | `\n` escape vs raw line ending or double-escape | Parse both as `JsonNode`, inspect code points |
| `note` disappears | `NON_NULL` or naming/filter | Check `has`, strict fixture, serializer config |
| Test fails after Jackson upgrade | Module/number/time formatting config changed | Inspect tree diff + contract |
| Test fails due to field ordering | Comparing raw text | Switch to structural JSON comparison |
| Test fails due to `tags` ordering | Array order changed | Verify whether order is contracted |
| Fixture values match yet test passes when service is wrong | Business collaborator was mocked | Add real service test or HTTP integration test |
| Timestamp passes intermittently | Using real system clock | Inject fixed clock/stable fixture |
| Passes locally, fails in CI | Different locale/timezone/charset/config | Fix configuration and inspect bytes first |
| JSONassert LENIENT passes despite internal field leak | Extra fields allowed | Use STRICT or absence assertions |
| Every snapshot passes after update | Expected auto-generated from actual | Require independent review of expected data |
| JSON parse error on 204/404 empty body | Test applies JSON matcher to empty body | Assert status + empty content |

## 25. Gradle, running tests, and expected results

In a Gradle project with the Spring Boot plugin/BOM, repositories, and matching Java toolchain configured, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additive configuration snippet**, not a standalone `build.gradle` since it omits `plugins`, `repositories`, and version management. Spring Boot 3.5 `starter-web` brings Jackson, and `starter-test` brings JUnit Jupiter, Spring MVC Test, and Mockito/JSONassert per the version BOM.

Run from the directory containing the Gradle wrapper:

```bash
./gradlew test --tests com.example.fixturejson.ArticleControllerFixtureTest --tests com.example.fixturejson.ArticleHttpUtf8IntegrationTest --tests com.example.fixturejson.UnicodeNormalizationTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.fixturejson.ArticleControllerFixtureTest --tests com.example.fixturejson.ArticleHttpUtf8IntegrationTest --tests com.example.fixturejson.UnicodeNormalizationTest
```

For multi-module projects, run the test task on the right module. Do not copy isolated snippets marked "illustrative" into Java files; the runnable files are listed in sections 14–18.

**Expected results from the described code:**

- `ArticleControllerFixtureTest`: **8** tests covering structural JSON equality, STRICT/LENIENT, UTF-8 decoding, request echo, 404, BOM/fixture validity, and key ordering.
- `ArticleHttpUtf8IntegrationTest`: **1** test over a real HTTP server, real demo adapter, response JSON matching the fixture.
- `UnicodeNormalizationTest`: **1** unit test on Unicode NFC.
- Total: **10 JUnit test methods**. When code, fixtures, and project configuration match the example, Gradle is expected to report `BUILD SUCCESSFUL`. This is an **expected outcome from code review**, not a claim of having executed Gradle on a specific repository.
- There is no fixed business stdout. Server ports, startup logs, and runtimes vary by environment.
- Reports are normally written to `build/reports/tests/test/index.html`; XML results live in the corresponding module's `build/test-results/test/`.

**Note when checking code:** all Java strings with quotes/newlines use **one level of escaping** for Java source; JSON fixtures use one level of escaping for JSON files. Avoid double-escaping when moving between Java literals, JSON text, and Markdown code fences.

## 26. Practice exercises

### Exercise A — Structurally identical yet textually different JSON

Given two JSON objects differing only in whitespace and key order, what does `assertEquals(String,String)` return? What does `JsonNode.equals` return? Explain why only one reflects normal JSON contracts.

**Guided answer:** Raw text differs; parsed object trees are equal because fields/values match.

### Exercise B — UTF-8 and mojibake

A fixture contains `"Cà phê"`, yet a test prints `"CÃ  phÃª"`. Inspect `byte[]` and decode with UTF-8. Should you change the expected fixture to mojibake so the test passes?

**Answer:** No. Identify the wrong decode step, apply UTF-8 properly, and keep the original expected data.

### Exercise C — null or missing?

Expected has `"note": null`, while actual omits `note` completely. How do `has("note")`, `get("note").isNull()`, and `path("note")` behave? Write assertions catching the exact difference per contract.

### Exercise D — array order

Expected tags `["cà phê","sách"]`, actual `["sách","cà phê"]`. If the API specifies priority order, which matcher should you use? If the API specifies no order, which matcher should you use?

**Hint:** `contains` vs `containsInAnyOrder`; full structural equality normally enforces array order.

### Exercise E — choosing STRICT or LENIENT

An API allows adding `metadata` fields while forbidding `internalToken`. Should you use JSONAssert LENIENT with an expected payload containing only `id`/`title`? What extra assertion is required?

**Answer:** You can use LENIENT for extensible contracts, provided you assert `$.internalToken` is **completely absent**, or use schema/policy tests.

### Exercise F — Escaping across two layers

For a Java string containing real quotes and a real newline, write the Java source:

```java
String summary = "Dòng 1: \"đậm\"\nDòng 2";
```

Then write the corresponding JSON fixture:

```json
{"summary":"Dòng 1: \"đậm\"\nDòng 2"}
```

Visually they look similar, yet the **Java compiler** and the **JSON parser** are two separate escape processors. Explain why raw newlines are illegal inside JSON strings.

### Exercise G — Is a fixture generated from responses a good test?

A script captures current production responses and overwrites the fixture before every JUnit run. Tests pass every time. If a response leaks a secret field or returns a wrong amount, will it catch it? Propose a snapshot review workflow with independent expected data.

### Exercise H — Non-deterministic timestamps

A fixture contains `"createdAt": "2026-11-08T10:15:30Z"`; the real service calls `Instant.now()`. The test fails intermittently or constantly. Fix it using a fixed `Clock` or an appropriate invariant assertion, and explain why default timezones also matter.

### Exercise I — How does full HTTP differ from WebMvcTest?

If `ArticleControllerFixtureTest` passes yet production `DemoArticleCatalog` returns the wrong title, will the MVC slice test catch it? Which test in the example runs the real adapter?

**Answer:** The slice uses `@MockitoBean ArticleCatalog`, so it skips the adapter. `ArticleHttpUtf8IntegrationTest` uses the full context and real server, comparing the adapter's response against the fixture.

## 27. Fixture and charset review checklist

- [ ] Fixture has a scenario-reflective path/name inside `src/test/resources`.
- [ ] JSON file is saved as **UTF-8 without BOM** and parses cleanly.
- [ ] Expected data is independently reviewed, not auto-generated from actual right before assertion.
- [ ] I distinguish raw bytes, raw text, JSON tree equality, and focused field assertions.
- [ ] I do not require `charset=UTF-8` in `Content-Type` when the HTTP JSON contract omits it.
- [ ] When checking byte encoding, I fetch `byte[]` and use a UTF-8 decoder with error reporting.
- [ ] I do not rely on `MockHttpServletResponse.getContentAsString()` when fallback charsets could misdecode Vietnamese text.
- [ ] I understand JSON `\"`, `\n` and Java source string `\"`, `\n` are **two separate parser layers**.
- [ ] Literal Unicode and `\uXXXX` are compared by parsed values, not raw textual escapes unless required.
- [ ] I know Unicode normalization does not happen automatically to suit tests.
- [ ] Object key order/whitespace never cause false failures; array order is checked per contract.
- [ ] I verify types, values, nulls, missing fields, and sensitive fields.
- [ ] I choose JSONAssert `STRICT/LENIENT` deliberately.
- [ ] For money and decimals, I enforce explicit numeric contracts rather than reckless `double`/tolerance checks.
- [ ] Timestamps/timezones/locales/random IDs are fixed or asserted via invariants.
- [ ] If the serializer changes naming/dates/enums/modules, tests catch the contract break.
- [ ] I do not claim an MVC slice with mocked services proves all business rules work.
- [ ] I maintain separate integration/adapter tests for boundaries that must run live.
- [ ] Tests are independent, unaffected by execution order or shared mutable fixtures.

**Conclusion:** A good JSON fixture is a **reviewed contract specification**, not a blind copy of a response. RFC 8259 standardizes exchanged JSON on UTF-8; Spring MVC/Jackson lets you verify payloads as bytes and JSON trees without being misled by display or charset fallbacks. When comparing, stay **strict on critical fields, types, values, and absences**, while staying **flexible on whitespace, object key order, and equivalent escape encodings** when raw bytes are uncontracted. Combine slice tests, full-context HTTP tests, and unit tests at their proper boundaries so tests are both stable and effective at catching real bugs.

### Official Reference Documentation

- RFC 8259 — JSON, UTF-8, BOM, Unicode escapes: https://www.rfc-editor.org/rfc/rfc8259
- Spring Framework 6.2 — `MockHttpServletResponse.getContentAsString(Charset)` and `getContentAsByteArray()`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/mock/web/MockHttpServletResponse.html
- Spring Framework 6.2 — `ContentResultMatchers.json(..., JsonCompareMode)`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/test/web/servlet/result/ContentResultMatchers.html
- Spring Boot 3.5 — Testing Spring MVC Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Jackson Databind — `JsonNode` tree model: https://github.com/FasterXML/jackson-databind
