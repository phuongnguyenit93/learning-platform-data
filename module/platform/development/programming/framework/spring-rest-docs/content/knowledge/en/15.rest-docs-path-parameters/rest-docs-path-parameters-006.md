# Encoding path segments and special characters

## Lesson Objectives

In a REST API, a path parameter is typically written as **{assetKey}** in the URI template **/api/assets/{assetKey}**. When values only contain letters, digits, and hyphens, things are straightforward. However, when a value contains **spaces, accented characters, %, &, ?, #, /, or ;**, how the URI is constructed and how the server interprets the path can change the request outcome.

In the **SPRING_REST_DOCS** module, the goal is to produce verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**. This lesson focuses on **encoding path segments** properly, writing tests for edge cases, and using **pathParameters(...)** to generate snippets. Those snippets can then be included in **Asciidoctor/Markdown** documentation and the build/CI pipeline.

After this lesson, you will be able to:

- Distinguish a **URI template**, a **path variable value**, a **percent-encoded URI**, and the **decoded value** at the controller.
- Explain UTF-8 encoding with **%HH** notation and why spaces in a path typically become **%20**.
- Distinguish encoding for a **path segment** from the **application/x-www-form-urlencoded** mechanism commonly used in forms and queries.
- Use **UriComponentsBuilder** to expand template variables and encode values at the right stage.
- Identify the risks of an **encoded slash (%2F)**, segment delimiter **;**, **?**, **#**, percent signs, and dot segments.
- Create MockMvc tests that generate **path-parameters.adoc**, while verifying URI encoding in separate tests.
- Design end-to-end tests through an HTTP server/proxy for encoding-sensitive paths.

## 1. What is a path segment?

Consider the path:

~~~text
/api/assets/guide-2026/versions/3
~~~

The **path segments** are separated by forward slashes (**/**):

~~~text
api | assets | guide-2026 | versions | 3
~~~

The endpoint's URI template can be:

~~~text
/api/assets/{assetKey}/versions/{version}
~~~

In this case, **guide-2026** is the value of **assetKey** and **3** is the value of **version**. Each variable is designed to occupy **one segment** of the path.

| Component | Example | Meaning |
| --- | --- | --- |
| URI template | **/api/assets/{assetKey}** | Pattern used to build requests and document variable names |
| Raw value | **Báo cáo Q4** | Business data before encoding |
| Encoded path | **/api/assets/B%C3%A1o%20c%C3%A1o%20Q4** | URI representation using percent-encoding for characters that need escaping |
| Value expected by controller | **Báo cáo Q4** | String decoded by the server/framework and bound to **@PathVariable** |

The **variable name** in Spring REST Docs remains **assetKey** in all cases. Do not write **parameterWithName("Báo cáo Q4")** or **parameterWithName("B%C3%A1o...")**, because those are *values*, not the variable name in the URI template.

## 2. Percent-encoding and UTF-8

URIs have a set of characters with structural meaning. To represent characters that cannot be used literally at a given position, an HTTP client can encode them as **%HH** sequences, where **HH** is two hexadecimal digits representing **one byte**.

When a Unicode character is UTF-8 encoded, it may occupy multiple bytes; each byte is represented by its own percent-encoded sequence. For example:

- The character **á** in UTF-8 has two bytes **C3 A1**, so it is typically written as **%C3%A1** in a URI.
- An ASCII space has hex code **20**, so it can be written as **%20**.
- The **&** character has hex byte **26**, so when encoded it becomes **%26**.

Thus, **Báo cáo Q4** has the encoded path segment form:

~~~text
B%C3%A1o%20c%C3%A1o%20Q4
~~~

This is an example of UTF-8 encoding. Some characters are *not required* to be encoded in every URI component; exact encoding depends on the character position and the URI construction method. For **values substituted into a URI template**, use strict encoding from a URI builder to prevent data from being misinterpreted as path syntax.

### 2.1. Special characters table in paths

Suppose each value is placed into **one variable** in the template **/api/assets/{assetKey}**, then strictly encoded when expanding the URI template:

| Original value | Representation in segment | Notes |
| --- | --- | --- |
| **guide-2026** | **guide-2026** | Letters, digits, and hyphens usually do not need escaping |
| **Báo cáo Q4** | **B%C3%A1o%20c%C3%A1o%20Q4** | UTF-8 for accented letters; **%20** for spaces |
| **A&B** | **A%26B** | Encodes **&** inside the value |
| **question?draft** | **question%3Fdraft** | Unescaped **?** can start the query part |
| **release#2** | **release%232** | Unescaped **#** can start a client-side fragment |
| **50%done** | **50%25done** | **%** must be encoded so it is not mistaken for an escape sequence |
| **A+B** | **A%2BB** | Preserves **+** as data, avoiding confusion with form encoding rules |
| **part;draft** | **part%3Bdraft** | **;** has special meaning in certain path handling schemes |
| **folder/file** | **folder%2Ffile** | Encoded slash remains a sensitive case and may be rejected by servers/proxies |

The values in this table describe **strict encoding** of URI-template variables. They do not guarantee that every reverse proxy and servlet container will accept and return the exact same value when receiving URLs with special characters.

### 2.2. Do not use form encoding rules for path segments

**java.net.URLEncoder** primarily produces representations following the **application/x-www-form-urlencoded** convention, where spaces usually become **+**:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String encoded = URLEncoder.encode(
    "Báo cáo Q4", StandardCharsets.UTF_8);
// Partial result: B%C3%A1o+c%C3%A1o+Q4
~~~

In a **path**, a plus sign can be a literal character with its own meaning and is not always interpreted as a space. Therefore, **do not use URLEncoder as a general tool for encoding path segments**. Use a URI builder that understands URI components.

In the query part, plus signs can also be handled differently depending on the API/client and form-decoding rules. When you need to represent a value accurately, use your HTTP client's query parameter methods instead of manual URL string concatenation.

## 3. Encode values before or after expanding the URI template?

A common pitfall is confusing **data values** with **URI template syntax**. Suppose an asset key genuinely contains **folder/file** and is expected to occupy *one* variable **{assetKey}**. If you substitute this key directly into a path string:

~~~java
String key = "folder/file";
String url = "/api/assets/" + key;
// /api/assets/folder/file
~~~

The resulting URL has **two segments** after **/api/assets/** rather than one segment. A route that only matches **/api/assets/{assetKey}** will normally not match that request.

### 3.1. Using UriComponentsBuilder

With Spring Framework:

~~~java
import org.springframework.web.util.UriComponentsBuilder;

String key = "Báo cáo Q4&Sales";

String encodedPath = UriComponentsBuilder
    .fromPath("/api/assets/{assetKey}")
    .encode()
    .buildAndExpand(key)
    .toUriString();

// /api/assets/B%C3%A1o%20c%C3%A1o%20Q4%26Sales
~~~

In this example, **encode()** is called on the **builder before buildAndExpand(...)**. This is an important way to strictly encode URI template variable values: reserved characters inside the **value** are escaped so they are unlikely to be parsed as URI structure.

When you need a URI object to send a request:

~~~java
import java.net.URI;

URI uri = UriComponentsBuilder
    .fromPath("/api/assets/{assetKey}")
    .encode()
    .buildAndExpand("Báo cáo Q4&Sales")
    .toUri();
~~~

Using **URI** directly when the client API supports it reduces the risk of another layer re-encoding an already escaped string.

### 3.2. Why be careful with the order of encode and expand?

These are two different concepts:

- **Encoding the URI template before expansion:** the URI builder clearly knows where variables are, so it can strictly escape reserved characters inside **values**.
- **Encoding the entire URI after inserting values:** at that point some reserved characters may be treated as valid URI syntax—for instance, **/** may be kept as a path separator.

For values containing **/**, **;**, or other reserved characters, these two approaches can produce different outputs. Prefer URI template expansion APIs and test the exact request path on your target Spring/client version.

### 3.3. Never encode twice

Suppose the original value is **Báo cáo**. After encoding, it becomes:

~~~text
B%C3%A1o%20c%C3%A1o
~~~

If you pass this **already-encoded** string as a **raw value** into a URI builder that applies encoding, the **%** character may be escaped to **%25**, resulting in:

~~~text
B%25C3%25A1o%2520c%25C3%25A1o
~~~

This is **double encoding**. A server that decodes once will see literal percent signs and escape sequences instead of the original business value.

Rule of thumb: **manage values in unencoded form**, and let **a single layer handle URI encoding**. If you already have a valid **URI** object, pass it using overloads that accept **URI** when appropriate, avoiding round-tripping through strings and expanding/encoding a second time.

## 4. Special characters requiring context-specific handling

### 4.1. Question mark (?) and hash (#)

In a URL:

~~~text
/api/assets/report?draft
/api/assets/report#v2
~~~

**?** marks the start of the query string; **#** marks a fragment. Fragments are typically handled by the client and **are not sent to the server** in the HTTP request target.

If **report?draft** or **report#v2** is genuinely the value of *one path segment*, it must be encoded when constructing the URI:

~~~text
/api/assets/report%3Fdraft
/api/assets/report%23v2
~~~

Do not manually concatenate values containing **?** and **#** into a URL, because the request may then reach a different resource than the caller intended.

### 4.2. Percent sign (%) and invalid escapes

The **%** character starts a **%HH** escape sequence. For example, **%20** means a space byte when decoded appropriately. A sequence like **%G1** is not a valid escape.

If a business value contains a literal **%**, such as **50%done**, its URI representation can be **50%25done**. Avoid manual string manipulation such as finding and replacing **%**, which easily introduces double-encoding bugs or allows multi-pass decoding across layers.

Requests with malformed percent-escapes may be rejected by HTTP clients, proxies, or servers **before reaching the controller**. Test the actual deployed system's behavior instead of assuming errors are always handled by the controller.

### 4.3. Forward slash (/) and encoded slash (%2F)

Within a single segment, **/** is the trickiest case because it inherently separates path segments:

~~~text
/api/assets/folder/file       # Two segments: folder, file
/api/assets/folder%2Ffile     # Intended to represent one value containing /
~~~

Even though a URI builder can produce **%2F**, there is no guarantee every piece of infrastructure treats it identically:

1. Reverse proxies, firewalls, or servlet containers may **reject encoded slashes**.
2. One layer might decode **%2F** into **/** before Spring performs route matching.
3. Behavior may differ between the MockMvc test environment and the application running behind a real HTTP server.
4. Decoding at the wrong layer or decoding multiple times can cause discrepancies in routing and access control.

**Design recommendation:** if an ID might contain **/**, consider choosing a segment-safe ID format, using an alternative identifier, or designing a different API. Do not assume slash encoding works uniformly across all configurations.

Avoid accidentally allowing paths like **../**, **%2E%2E%2F**, or variants that can become path traversal after decoding. If a path value is used for file access, always enforce destination path validation at the storage layer and perform authorization checks rather than relying solely on encoding.

### 4.4. Semicolon (;) and dot (.)

**;** can be tied to mechanisms such as **matrix variables/path parameters** in certain frameworks or routing rules; that differs from REST Docs' term **path parameter**, which refers to **{...}** variables.

If **;** is part of a business code, let the URI builder encode the value and test against a real server. If unnecessary, prefer slugs/IDs with safe characters only.

A **.** inside a name like **report.v2** usually causes no trouble. However, path segments equal to **.** or **..** have special meaning during URI normalization. Do not use **.** or **..** as path segment identifiers if the system could process them as directory navigation.

## 5. Sample controller and API contract

Example of an API looking up an asset by key:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AssetController {

    @GetMapping("/api/assets/{assetKey}")
    AssetResponse getAsset(@PathVariable("assetKey") String assetKey) {
        return new AssetResponse(assetKey);
    }
}

record AssetResponse(String assetKey) {}
~~~

The sample controller returns the bound value for illustration. In a real implementation, you need a service to check existence, enforce access control, and enforce character conventions for **assetKey**.

One practical contract is requiring asset keys to be **slugs** containing only letters, digits, and hyphens. With this constraint, callers never need to send spaces or **/** in the path; accented display names are stored in a separate property, such as **displayName**.

~~~text
GET /api/assets/quarterly-report-2026

{
  "assetKey": "quarterly-report-2026",
  "displayName": "Q4 2026 Report"
}
~~~

This is often the simplest choice for widely used APIs: a stable **identifier key** in the path and a rich Unicode **display name** in the JSON response.

If the contract requires Unicode IDs with spaces, document how clients must construct URIs and write end-to-end tests confirming the received value matches the original value.

## 6. Generating snippets with MockMvc and separate encoding tests

The example uses **Java 17+**, **JUnit 5**, **Spring Boot 3.x**, and **spring-restdocs-mockmvc**. With Gradle and Spring Boot's version-managing BOM:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

### 6.1. Test generating path parameter documentation

Create **AssetDocumentationTest.java** in the same package as **AssetController**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AssetController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class AssetDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentAssetKey() throws Exception {
        mockMvc.perform(
                get("/api/assets/{assetKey}", "quarterly-report-2026")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.assetKey")
                .value("quarterly-report-2026"))
            .andDo(document("asset-get",
                pathParameters(
                    parameterWithName("assetKey")
                        .description("Asset key in a single path segment; "
                            + "use a slug, e.g. quarterly-report-2026")
                )
            ));
    }
}
~~~

Here **get(...)** is statically imported from **RestDocumentationRequestBuilders** to preserve the **URI template** and variable name **assetKey** for REST Docs. This matters because **pathParameters(...)** needs the variable name to match against **parameterWithName("assetKey")**.

**Do not write** descriptors with URL-encoded values: the snippet describes the meaning of **assetKey**, while the sample request table is generated by REST Docs from the executed request.

The output directory is expected to contain:

~~~text
build/generated-snippets/asset-get/
├── path-parameters.adoc
├── http-request.adoc
├── http-response.adoc
└── curl-request.adoc
~~~

The list above illustrates several snippets; actual configurations may generate additional files.

### 6.2. Pure test verifying URI encoding output

You should have a separate test verifying the **generated URI string** before requests traverse the network:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.web.util.UriComponentsBuilder;

import static org.assertj.core.api.Assertions.assertThat;

class AssetUriEncodingTest {

    @Test
    void encodeUnicodeSpaceAndAmpersandInTemplateVariable() {
        String path = UriComponentsBuilder
            .fromPath("/api/assets/{assetKey}")
            .encode()
            .buildAndExpand("Báo cáo Q4&Sales")
            .toUriString();

        assertThat(path).isEqualTo(
            "/api/assets/B%C3%A1o%20c%C3%A1o%20Q4%26Sales");
    }

    @Test
    void encodeLiteralPercentOnce() {
        String path = UriComponentsBuilder
            .fromPath("/api/assets/{assetKey}")
            .encode()
            .buildAndExpand("50%done")
            .toUriString();

        assertThat(path).isEqualTo("/api/assets/50%25done");
    }
}
~~~

These two tests verify **the URI construction step**; they do not prove a reverse proxy will accept every request containing percent-encoding. If an endpoint permits Unicode values or reserved characters in IDs, add integration tests routed through the **same server/proxy** used in deployment.

### 6.3. Verifying a value after server decoding

With a contract accepting **Báo cáo Q4** as an asset key, an integration test must verify that the string received at the controller is no longer **B%C3%A1o%20...**. End-to-end HTTP testing can follow this flow:

1. Invoke the URI builder with the raw value **Báo cáo Q4**.
2. Observe that the request target contains the segment **B%C3%A1o%20c%C3%A1o%20Q4**.
3. Verify the handler receives the exact string **Báo cáo Q4**.
4. Verify the JSON response or business data contains the exact string.
5. Test routing and responses through the reverse proxy/ingress if the API is exposed behind those layers.

Do not assume MockMvc simulates every URI decoding rule of a servlet container or reverse proxy. Keep URI construction tests separate, controller tests separate, and real deployment tests for sensitive characters.

## 7. WebTestClient and REST Assured

The same **parameterWithName(...)** descriptor is used across all three HTTP test clients. The differences lie in how URIs are built and how **document(...)** is attached.

### 7.1. WebTestClient

When **WebTestClient** has Spring REST Docs configured (e.g., via **documentationConfiguration(...)**), a test with a safe slug can look like:

~~~java
webTestClient.get()
    .uri("/api/assets/{assetKey}", "quarterly-report-2026")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("asset-webtestclient",
        pathParameters(
            parameterWithName("assetKey")
                .description("Slug identifying the asset")
        )
    ));
~~~

In this example, **document(...)** belongs to **WebTestClientRestDocumentation**. If complex values require encoding, build the URI using the client's URI builder API; inspect the actual URI sent over HTTP instead of assuming all **uri(...)** overloads encode identically.

### 7.2. REST Assured

With a **RequestSpecification spec** configured with REST Docs:

~~~java
given(spec)
    .filter(document("asset-rest-assured",
        pathParameters(
            parameterWithName("assetKey")
                .description("Slug identifying the asset")
        )
    ))
    .pathParam("assetKey", "quarterly-report-2026")
    .when()
    .get("/api/assets/{assetKey}")
    .then()
    .statusCode(200);
~~~

Here **document(...)** belongs to **RestAssuredRestDocumentation**. **pathParam(...)** assigns the **request value**, while **parameterWithName(...)** describes the **variable name**. For values containing **%**, **/**, or Unicode characters, inspect and test REST Assured's URL encoding configuration rather than concatenating pre-encoded URLs with URI templates.

## 8. Bringing encoding documentation into snippets and Asciidoctor

API consumers need to know **allowed ID formats** and **how to pass** values containing special characters. Writing only "Asset key" may not be enough.

A helpful descriptor:

~~~java
pathParameters(
    parameterWithName("assetKey")
        .description("Asset slug consisting of ASCII letters, digits, and "
            + "hyphens; e.g. quarterly-report-2026")
)
~~~

If the API **actually permits** Unicode names and spaces, adjust the description to match the contract, e.g.: "Asset key; clients must UTF-8 percent-encode the value within a single path segment". At the same time, include HTTP tests proving the published cases work through the deployed system.

Example **src/docs/asciidoc/index.adoc** file:

~~~asciidoc
= Asset API
:toc: left

== Get asset by key

GET /api/assets/{assetKey}

The asset key must follow the conventions listed in the table below.

=== Path parameters

include::{snippets}/asset-get/path-parameters.adoc[]

=== HTTP request

include::{snippets}/asset-get/http-request.adoc[]

=== HTTP response

include::{snippets}/asset-get/http-response.adoc[]
~~~

Gradle Groovy DSL example when the **org.asciidoctor.jvm.convert** plugin is installed:

~~~groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
~~~

In CI, run tests to generate snippets before the documentation build step, and publish only if both tests and Asciidoctor succeed. A specific test should fail when a variable name changes from **{assetKey}** to **{fileKey}** without updating the descriptor. Dedicated encoding tests help detect unintended changes to URL builders.

REST Docs typically generates AsciiDoc snippets. If a project publishes Markdown docs, a converter or embedding mechanism compatible with your Markdown builder is required, because **include::...[]** is not standard Markdown syntax.

## 9. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| URL with spaces or accented characters is rejected | Unencoded string inserted into URL | Use a URI builder with UTF-8 and template-variable encoding |
| Controller receives **+** instead of space | Used **URLEncoder** for a path | Use path segment encoding that produces **%20** for spaces |
| Received value literally contains **%20** instead of space | Double encoding or processing layer did not decode as expected | Trace raw value, transmitted URI, and number of encode/decode passes |
| **/api/assets/folder/file** fails to match single variable **{assetKey}** | **/** creates an extra path segment | Avoid **/** inside IDs or design a different path structure |
| Request containing **%2F** blocked at proxy | Intermediary layer restricts encoded slashes | Test real infrastructure; consider safe IDs instead of loosening protections blindly |
| String **report#v2** arrives at server as just **report** | Everything after **#** is treated as a fragment | Encode the hash sign as **%23** inside the value |
| String **report?draft** interpreted as query | **?** was not escaped | Encode **?** inside the value as **%3F** |
| Request with **%G1** rejected before controller | Malformed percent-escape syntax | Use a URI builder; do not assemble **%HH** manually |
| Spring REST Docs reports missing or unexpected path parameter | Descriptor uses wrong name or request lost URI template | Use **RestDocumentationRequestBuilders** and **parameterWithName("assetKey")** |
| Snippet is right but endpoint fails in production | Decoding differences between MockMvc and proxy/container | Add integration tests running over the same HTTP path as production |
| Code containing **..** resolves outside intended directory | Unsafe path normalization or file-path handling | Validate/canonicalize paths and restrict access at service/storage layer |

## 10. Hands-on exercise

You need to document the endpoint:

~~~text
GET /api/reports/{reportKey}
~~~

Suppose two groups of report keys are allowed:

- **Safe keys:** **report-Q4-2026**, using only ASCII letters, digits, and hyphens.
- **Unicode keys:** **Báo cáo Q4**, containing spaces and accented Vietnamese characters.

Perform the following:

1. Write a controller using **@PathVariable("reportKey") String reportKey** that returns JSON containing the received key.
2. Write a MockMvc test using **RestDocumentationRequestBuilders.get("/api/reports/{reportKey}", "report-Q4-2026")**, verifying HTTP 200 and generating **report-get/path-parameters.adoc**.
3. Write a separate test for **UriComponentsBuilder**. Given the raw value **Báo cáo Q4**, verify the generated path is **/api/reports/B%C3%A1o%20c%C3%A1o%20Q4**.
4. Add tests with **report#2**, **50%done**, and **A&B** to observe **%23**, **%25**, and **%26**.
5. Test against a real HTTP server/proxy for Unicode keys (if the API claims to support them), verifying the controller receives the exact string **Báo cáo Q4**.
6. Explain why **folder/report** is difficult to support in a single path segment, even when a URI builder produces **folder%2Freport**.
7. Include the path parameters snippet alongside HTTP request/response snippets in **index.adoc** and run the test → Asciidoctor workflow in build/CI.

Suggested descriptor:

~~~java
pathParameters(
    parameterWithName("reportKey")
        .description("Report key; if containing Unicode or spaces, "
            + "clients must safely encode it within the path segment")
)
~~~

**Completion criteria:** documentation test generates the snippet with the exact **reportKey** variable; URI encoding tests verify special cases; the API contract only claims support for tested formats; documentation builds cleanly from snippets.

## Key Takeaways

**Encoding path segments** prevents URI data from being misinterpreted as delimiters or URL control components. Keep values unencoded, expand URI templates and encode via a URI builder at the proper stage; watch out for UTF-8, **%20**, **%25**, and especially **%2F**. **Spring REST Docs** uses **pathParameters(...)** to verify variable names and generate documentation from HTTP tests, while encoding/decoding correctness must be tested across clients, controllers, and deployed HTTP layers. Combine both types of tests in build and CI so documentation accurately reflects the API contract.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs RequestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/request/RequestDocumentation.html), [Spring Framework: URI Links](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html), [RFC 3986: URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986).
