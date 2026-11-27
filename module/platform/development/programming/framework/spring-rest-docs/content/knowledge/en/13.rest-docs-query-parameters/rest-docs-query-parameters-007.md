# Encoding query values and special characters in Spring REST Docs

## 1. Why is encoding part of the API contract?

Query strings often carry user-supplied values: keywords with spaces, product names containing plus signs, emails with `@`, filters with commas, or Unicode text. For example:

```http
GET /api/products?q=wireless%20earbuds&tag=C%2B%2B&tag=audio HTTP/1.1
Host: api.example.test
Accept: application/json
```

Once the server decodes the query string properly, the values received by the application are:

| Name | Decoded value |
| --- | --- |
| `q` | `wireless earbuds` |
| `tag` (1st) | `C++` |
| `tag` (2nd) | `audio` |

If the client encodes incorrectly, the server can receive a value different from what was intended. A `+` sign gets interpreted as a space, an `&` splits out an extra parameter, and a `#` can start a client-side fragment that is never sent in the HTTP request. Encoding bugs therefore directly affect search, filtering, and the reproducibility of requests from documentation.

In the **SPRING_REST_DOCS** module, Spring REST Docs creates verifiable API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. This lesson in the **Query parameters** chapter explains how to represent query values containing special characters, how to send requests properly in tests, and how to generate the `query-parameters.adoc` snippet describing parameter names and meanings. REST Docs records the sent request; encoding and decoding must be handled correctly by the client, URI builder, and application.

After this lesson, you will be able to:

1. Distinguish query strings, URI components, and percent-encoding.
2. Handle spaces, plus signs, `&`, `=`, `#`, `%`, commas, Unicode, and repeated values.
3. Use a URI builder or query parameter API instead of manual URL string concatenation.
4. Test pre/post-decoding values with MockMvc and generate Spring REST Docs documentation.

## 2. Query string structure and percent-encoding

A URI has the general form:

```text
scheme://authority/path?query#fragment
```

The query part starts after `?` and ends before `#` if a fragment is present. Queries are commonly expressed as `name=value` pairs joined by `&`; the first `=` separates the name from the value. This is a widespread web application convention, and an application may define additional structure inside a value.

Example:

```text
/api/products?q=wireless%20earbuds&category=audio
```

- `?` starts the query.
- `q=wireless%20earbuds` is a name/value pair.
- `&` separates the next pair.
- `%20` is the percent-encoding of byte `0x20`, representing a space in UTF-8/ASCII-compatible encoding.

### 2.1. How does percent-encoding work?

Percent-encoding replaces each byte of the encoded character with `%HH`, where `HH` is two hexadecimal digits. Under UTF-8, a single Unicode character may correspond to multiple bytes and therefore produce multiple `%HH` sequences.

Examples:

| Character/data | Common encoding in queries |
| --- | --- |
| Space | `%20` |
| Plus sign `+` | `%2B` |
| Ampersand `&` | `%26` |
| Equals sign `=` | `%3D` |
| Percent sign `%` | `%25` |
| Hash `#` | `%23` |
| Comma `,` | `%2C` (when component-encoded) |
| Slash `/` | `%2F` (when component-encoded) |
| Letter `ế` | `%E1%BA%BF` in UTF-8 |

Percent-encoding applies to a **component value or name** according to context. Never encode an entire URI with a component-encoding function, because structural delimiters like `:`, `/`, `?`, `&`, and `=` would also be encoded, breaking the URI structure.

### 2.2. Space `%20` and plus `+` are not always identical

This is a common source of bugs:

| Query | When decoded per form URL encoding (`application/x-www-form-urlencoded`) | Meaning |
| --- | --- | --- |
| `q=wireless%20earbuds` | `wireless earbuds` | Percent-encoded space |
| `q=wireless+earbuds` | `wireless earbuds` | `+` is interpreted as a space under form-encoding rules |
| `q=C%2B%2B` | `C++` | Literal plus signs properly encoded |
| `q=C++` | May become `C  ` under form decoding | Two plus signs may be interpreted as two spaces |

The URI query component has no universal decoding rule forcing every framework to treat `+` as in a form body; many web frameworks apply form-decoding rules to query parameters. Therefore:

- To pass a literal plus sign as data, encode it as `%2B`.
- To pass a space, use a URI builder or appropriate encoder; `%20` is unambiguous in URIs.
- Check the behavior of the actual HTTP client and server, especially when the application receives data through different mechanisms.

Do not swap `%20` for `+` or vice versa when writing documentation examples without verifying your project's client behavior.

## 3. Common special characters

### 3.1. `&` and `=`

If a user searches for `rock & roll`, the value must be sent as a single component:

```http
GET /api/search?q=rock%20%26%20roll HTTP/1.1
```

If you send `q=rock & roll` unencoded, `&` can start another parameter. Similarly, when a value contains `=`, encode it as `%3D` if it is not the first separator in a `name=value` pair.

### 3.2. `#`

Fragments are handled on the client side and are not sent as part of the HTTP request target. If a search value literally contains `#spring`, `#` must be encoded as `%23`:

```http
GET /api/search?q=%23spring HTTP/1.1
```

Writing `/api/search?q=#spring` can cause `#spring` to be treated as a fragment instead of data received by the server.

### 3.3. `%`

`%` begins an escape sequence. If the data literally contains a percent character, encode it as `%25`. For example, `discount 20%` is represented as:

```text
q=discount%2020%25
```

The sequence `%2G` is not a valid escape sequence because `G` is not a hexadecimal digit. Do not encode manually by replacing a handful of characters without escaping input `%` characters.

### 3.4. Commas and multi-value formats

If the API defines `sort=price,asc`, the comma may remain unencoded as part of the value:

```text
sort=price,asc
```

Or be encoded as:

```text
sort=price%2Casc
```

Servers typically decode both to the same string `price,asc`, though API clients and gateways may apply their own rules. When a query repeats the same name, such as `sort=price%2Casc&sort=id%2Casc`, each occurrence remains one value for the `sort` name.

### 3.5. Unicode and Vietnamese

The value `điện thoại` becomes multi-byte percent-encoded sequences under UTF-8. Do not manually encode characters by Unicode code point; percent-encoding operates on charset bytes (in practice today, always use UTF-8).

Example URL produced by a URI builder:

```http
GET /api/search?q=%C4%91i%E1%BB%87n%20tho%E1%BA%A1i HTTP/1.1
```

When the server decodes UTF-8 properly, the application receives `điện thoại`. If a proxy, gateway, or application layer decodes it again, characters can be corrupted or turned into a different string. Decode only once according to the framework's contract; avoid calling a manual decoder on values already bound by Spring.

## 4. Query parameter names and query parameter values

Parameter names may also require encoding. For instance, the name `filter[name]` can be represented as:

```text
filter%5Bname%5D=wireless
```

After decoding, the name is `filter[name]`. Spring REST Docs documents **the name the application sees via request binding**, so tests must align the descriptor with the actual name. Do not rewrite `filter[name]` as `filter.name` or `filterName` if the controller does not use that convention.

Key points:

- Both names and values may contain characters that require encoding.
- Do not encode structural `&` and `=` when they delimit pairs, but encode them when they appear inside a component.
- A name can appear multiple times: `tag=java&tag=spring`. Each value must be encoded individually.
- An absent query parameter (`/search`) differs from a present parameter with an empty value (`/search?q=`), and from a whitespace-only value (`/search?q=%20`).
- If the API allows multiple comma-separated values in one component, clearly define how commas inside literal data are handled.

## 5. Using a URI builder instead of manual URL concatenation

Important principle: **let the URI/HTTP client library encode each component**. Never concatenate untrusted data into URLs with `+`.

### 5.1. Spring `UriComponentsBuilder`

Example building a request URI:

```java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

String keyword = "rock & roll C++";

URI uri = UriComponentsBuilder
        .fromPath("/api/search")
        .queryParam("q", "{keyword}")
        .encode()
        .buildAndExpand(keyword)
        .toUri();
```

In the example above, the placeholder is expanded following the builder's component-encoding step. You can use a URI builder in client or controller tests to send data containing spaces, `&`, and `+`; verify the resulting URI with your Spring version.

Another approach when building a URI directly:

```java
URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.test/api/search")
        .queryParam("q", "{value}")
        .buildAndExpand("C++ & Java")
        .encode()
        .toUri();
```

The order of calling `encode()`, `build()`, and `buildAndExpand(...)` affects how templates and expanded values are encoded. For dynamic values, prefer placeholders/variable expansion as shown and inspect the resulting URI rather than assuming all overloads behave identically.

### 5.2. MockMvc

MockMvc provides `queryParam(...)` to construct query strings in requests:

```java
mockMvc.perform(get("/api/search")
        .queryParam("q", "rock & roll C++"));
```

The request builder accepts the value as raw data and builds the query parameter. Do not pre-encode the value to `rock%20%26%20roll%20C%2B%2B` before passing it to `queryParam(...)`; doing so risks **double-encoding** `%` into `%25`.

If using a raw URL:

```java
mockMvc.perform(get("/api/search?q=rock%20%26%20roll%20C%2B%2B"));
```

In the raw URL case, the string is already URL-encoded; do not encode it again. Pick one style per test: pass unencoded values through the query builder API, or pass a properly encoded raw URI.

### 5.3. WebTestClient

With WebTestClient:

```java
webTestClient.get()
        .uri(builder -> builder.path("/api/search")
                .queryParam("q", "rock & roll C++")
                .build())
        .exchange()
        .expectStatus().isOk();
```

The URI builder handles URI construction. In tests, still add assertions confirming the controller receives the properly decoded value, such as checking that the response field `query` equals `rock & roll C++`.

### 5.4. REST Assured

REST Assured also provides an API for passing query parameters:

```java
given()
        .queryParam("q", "rock & roll C++")
        .when()
        .get("/api/search")
        .then()
        .statusCode(200);
```

Use `queryParam(...)` so the library constructs the query string. To document with Spring REST Docs, attach a configured documentation filter from the REST Assured integration; do not manually encode a value and then pass it into an API that encodes again.

## 6. Avoiding double-encoding and multiple decoding

Double-encoding occurs when a value that is already percent-encoded gets encoded a second time:

| Intended value | Encoded once | Encoded a second time |
| --- | --- | --- |
| Space | `%20` | `%2520` |
| Plus sign | `%2B` | `%252B` |
| Percent sign | `%25` | `%2525` |
| Ampersand `&` | `%26` | `%2526` |

For example, when the application expects `C++`:

1. Original value: `C++`.
2. Encoded once properly: `C%2B%2B`.
3. If an encoder runs again, `%` becomes `%25`, producing `C%252B%252B`.
4. The server decodes once and receives `C%2B%2B`, not `C++`.

Common mistakes:

- Calling `URLEncoder.encode(...)` and passing the result into `queryParam(...)`, which encodes again.
- Manually decoding a parameter already bound by Spring.
- Applying `URLDecoder` to an entire URI instead of the specific component to decode.
- Concatenating user input into a URI before encoding and accidentally injecting extra `&name=value` pairs.
- Reading the raw query string, decoding the entire string, and parsing it with custom logic, causing `&` or `=` inside values to be misread as delimiters.

Assign a single component to handle encoding and a single component to handle decoding. In Spring MVC controllers, prefer reading values via framework-bound `@RequestParam` or `MultiValueMap`.

## 7. Writing Spring REST Docs for values with special characters

Suppose the endpoint `GET /api/search` accepts:

- `q`: keyword that may contain spaces, plus signs, `&`, and Unicode.
- `tag`: repeatable name, each value being an independent tag.
- `sort`: value in the form `field,direction`.

Description in Spring REST Docs:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("q")
        .description("UTF-8 keyword; clients encode the component, e.g. rock & roll or C++"),
    parameterWithName("tag")
        .description("Filter tag; may be repeated multiple times, each value encoded separately")
        .optional(),
    parameterWithName("sort")
        .description("Sort criterion as field,direction; the comma is part of the value")
        .optional()
)
```

`description(...)` should state how clients pass the value and what it means after decoding. Spring REST Docs does not automatically display a percent-encoded sample for each value, nor does it check that Unicode data was decoded correctly. Combine descriptors with response assertions or server-side argument assertions when you need to verify values.

### 7.1. Sample controller receiving the query

```java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SearchController {

    @GetMapping("/api/search")
    public SearchResult search(
            @RequestParam("q") String query,
            @RequestParam(name = "tag", required = false) List<String> tags,
            @RequestParam(name = "sort", required = false) List<String> sorts) {

        return new SearchResult(
                query,
                tags == null ? List.of() : tags,
                sorts == null ? List.of() : sorts);
    }
}

record SearchResult(String query, List<String> tags, List<String> sorts) {}
```

A real application can return JSON. Sample response when called with keyword `rock & roll C++`:

```json
{
  "query": "rock & roll C++",
  "tags": ["C++", "audio"],
  "sorts": ["price,asc"]
}
```

The response body contains decoded values; it does not necessarily contain the percent-encoded strings from the URL.

### 7.2. MockMvc/JUnit 5 snippet generation

Documentation test example:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class SearchQueryEncodingDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new SearchController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsSpecialCharactersInQueryValues() throws Exception {
        mockMvc.perform(get("/api/search")
                        .queryParam("q", "rock & roll C++")
                        .queryParam("tag", "C++", "audio")
                        .queryParam("sort", "price,asc"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.query").value("rock & roll C++"))
                .andExpect(jsonPath("$.tags[0]").value("C++"))
                .andExpect(jsonPath("$.tags[1]").value("audio"))
                .andExpect(jsonPath("$.sorts[0]").value("price,asc"))
                .andDo(document("search-query-encoding",
                        queryParameters(
                                parameterWithName("q")
                                        .description("UTF-8 keyword; may contain spaces, &, +"),
                                parameterWithName("tag")
                                        .description("Tag; repeatable and each value is decoded individually")
                                        .optional(),
                                parameterWithName("sort")
                                        .description("Format field,direction; the comma is part of the value")
                                        .optional()
                        )));
    }
}
```

Key highlights:

1. `queryParam("q", "rock & roll C++")` takes the **unencoded value** and lets the MockMvc request builder construct the query parameter.
2. `jsonPath(...)` assertions confirm the controller receives the decoded data, not merely that the request contains a parameter named `q`.
3. Two `tag` values are sent with one `queryParam("tag", "C++", "audio")` call; in documentation, only one descriptor named `tag` is needed.
4. `queryParameters(...)` generates the snippet for parameter names/meanings; snippets do not replace tests for special-character values.

With Gradle configured to output to `build/generated-snippets`, the snippet directory will be:

```text
build/generated-snippets/
  search-query-encoding/
    query-parameters.adoc
    http-request.adoc
    http-response.adoc
    curl-request.adoc
    ...
```

Actual paths depend on your build configuration; Maven typically uses `target/generated-snippets`.

## 8. Including snippets in Asciidoctor/Markdown and CI

An Asciidoctor page can pull the query parameter table directly from the test:

```asciidoc
= Search API

== Search

GET /api/search

=== Query parameters

include::{snippets}/search-query-encoding/query-parameters.adoc[]

=== Request

include::{snippets}/search-query-encoding/http-request.adoc[]

=== Response

include::{snippets}/search-query-encoding/http-response.adoc[]
```

To make the example URI easy to read, you can also include a properly encoded sample request block:

```asciidoc
----
GET /api/search?q=rock%20%26%20roll%20C%2B%2B&tag=C%2B%2B&tag=audio&sort=price%2Casc
----
```

In Asciidoctor, the `{snippets}` attribute is configured to point to Spring REST Docs' snippet directory. With Markdown, select the Markdown template using `TemplateFormats.markdown()` and use an appropriate snippet-merging step; standard Markdown has no built-in `include` mechanism like Asciidoctor.

Build/CI workflow:

1. Declare the Spring REST Docs dependency for MockMvc, WebTestClient, or REST Assured and select a version compatible with Spring Boot/Spring Framework.
2. Configure the snippets directory (e.g. `build/generated-snippets`) as an output of the test task.
3. Configure the Asciidoctor/documentation packaging task to depend on the test task so snippets are always generated prior to rendering.
4. Run tests and publish documentation in CI. If either query-value assertions or documentation tests fail, the pipeline must fail.

Example Gradle command once the project configures the tasks:

```bash
./gradlew test asciidoctor
```

## 9. WebTestClient and REST Assured

### 9.1. WebTestClient

When `webTestClient` is configured with Spring REST Docs, use the URI builder to send raw values:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

webTestClient.get()
        .uri(builder -> builder.path("/api/search")
                .queryParam("q", "rock & roll C++")
                .queryParam("tag", "C++", "audio")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.query").isEqualTo("rock & roll C++")
        .consumeWith(document("search-query-encoding-webclient",
                queryParameters(
                        parameterWithName("q")
                                .description("UTF-8 keyword; may contain &, +, and spaces"),
                        parameterWithName("tag")
                                .description("Repeatable tag; each value is decoded separately")
                                .optional()
                )));
```

### 9.2. REST Assured

With REST Assured, pass unencoded values to `queryParam(...)`:

```java
given()
        .filter(documentationFilter)
        .queryParam("q", "rock & roll C++")
        .queryParam("tag", "C++", "audio")
        .when()
        .get("/api/search")
        .then()
        .statusCode(200)
        .body("query", equalTo("rock & roll C++"));
```

`documentationFilter` must be configured with the `spring-restdocs-restassured` integration and a snippet list containing `queryParameters(...)`. The HTTP call above illustrates sending data and asserting the response; the filter does not infer descriptions automatically.

## 10. Common errors and how to resolve them

| Symptom | Cause | How to resolve |
| --- | --- | --- |
| Server receives `C  ` instead of `C++` | Unencoded `+` was interpreted as a space by a form decoder | Encode `+` as `%2B` or pass the unencoded value to a URI builder |
| Server receives extra unexpected parameters after `rock & roll` | Unencoded `&` inside the value | Use `%26` or a query builder |
| Response returns `%2520` instead of a space | An already-encoded `%20` was encoded a second time | Encode only once; pass unencoded values to `queryParam(...)` |
| `#` never reaches the server | Fragments are not sent in HTTP requests | Encode literal `#` data as `%23` |
| Vietnamese characters become garbled | Mismatched encode/decode charsets or manual multiple decoding | Use UTF-8 and framework URI/HTTP binding |
| MockMvc test passes, yet snippet does not show query encoding as expected | Confusing decoded values with the raw request URI; templates/request formatters have their own display rules | Inspect the request URI and controller assertions; document parameter semantics with descriptors |
| `queryParameters(...)` reports a missing parameter | Used `.param(...)` instead of an actual query string, or wrong descriptor name | Use `.queryParam(...)` and match names to the request |
| Docs describe special characters without tests proving it | Only `description(...)` exists, with no assertion on received values | Assert the response/body or service arguments |

## 11. Practice exercise

Build an API:

```http
GET /api/catalog/search?q=áo%20thun%20C%2B%2B&brand=ACME&brand=North%20Star&tag=summer%26sale HTTP/1.1
```

Contract:

- `q` is a UTF-8 string that may contain spaces and plus signs; omitting it skips keyword filtering.
- `brand` can be repeated; each value is an independent brand.
- `tag` can be repeated; an `&` inside the value is literal data, not a new parameter.
- When a parameter name is present with an empty value, the API rejects it with HTTP 400.

Tasks:

1. Write a controller accepting `q`, `List<String> brand`, and `List<String> tag`.
2. Write a MockMvc test using `queryParam(...)` with **unencoded values**, without pre-encoding; assert the controller receives `áo thun C++`, `North Star`, and `summer&sale`.
3. Write a separate test using a percent-encoded raw URI and compare decoding results.
4. Intentionally try double-encoding `%20` and observe what the server receives; add a regression test preventing this bug.
5. Use `queryParameters(...)` and `parameterWithName(...)` to generate snippets; include the snippet in Asciidoctor and run it with tests in CI.

**Completion criteria:** Special characters and Unicode are transmitted once properly, the application receives exact contract values, repeated query parameters preserve names/values, snippets are generated from test requests, and documentation renders during the build.

## 12. Key takeaways

Percent-encoding encodes the bytes of a URI component; it is not an operation for encoding an entire URL. In particular, plus signs, spaces, `&`, `=`, `#`, `%`, and Unicode must be handled according to context. Use a URI builder or `queryParam(...)` API, and avoid double-encoding or manually decoding framework-bound values. In Spring REST Docs, `queryParameters(...)` documents parameter names and metadata, while HTTP assertions prove decoded values. Combining both keeps API documentation verifiable through tests and maintained in build/CI.

### References

- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring Framework — URI Links](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html)
- [Spring Framework Javadoc — `UriComponentsBuilder`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html)
- [Java SE — `URLEncoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLEncoder.html)
- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)
