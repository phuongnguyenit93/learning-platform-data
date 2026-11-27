# Multi-value cookies and encoding

## Lesson Objectives

An HTTP request can carry multiple cookies, each holding a name/value pair. Additionally, a single cookie sometimes contains structured data such as a list of permissions, preferences, or identifiers. Both cases must be designed and documented clearly. If you simply join multiple values with a delimiter without an encoding convention, the client and server may parse the data differently.

This lesson belongs to the **Cookies** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into builds and CI.

After this lesson, you will be able to:

- Distinguish multiple cookies in a single request from multiple value parts inside one cookie.
- Understand the structure of the **Cookie** header and multiple **Set-Cookie** headers.
- Choose conventions for representing lists or structured data in a cookie.
- Encode and decode cookie values consistently, avoiding delimiter bugs and double encoding.
- Use **requestCookies(...)**, **responseCookies(...)**, and **cookieWithName(...)** to document each cookie.
- Write MockMvc tests verifying multi-named cookies, encoded values, and decoded results.
- Use REST Docs to describe cookie names/purposes while verifying actual values with assertions.
- Keep cookies concise and safe, and keep sensitive data out of snippets.

## 1. Two different meanings of “multi-value cookie”

Before designing, distinguish between:

**Multiple cookies in one request:** the request contains multiple independent cookie pairs, typically separated by semicolons in the **Cookie** header.

~~~http
GET /api/profile
Cookie: locale=vi; display-mode=compact; region=apac
~~~

**One cookie containing multiple data parts:** there is only one cookie name, but the value represents multiple items according to an application convention.

~~~http
Cookie: feature-flags=beta~search~compact
~~~

In the second example, **feature-flags** is a single cookie; **beta**, **search**, and **compact** are data items inside the value after the application decodes and parses it.

| Model | Example | Documentation |
| --- | --- | --- |
| Multiple independent cookies | **locale=vi** and **display-mode=compact** | One descriptor per name in **requestCookies(...)** |
| One cookie containing a list | **feature-flags=beta%2Csearch** | One descriptor for **feature-flags**, clearly describing the value format |
| One cookie containing structured data | **preferences=...** | One descriptor for **preferences**, describing the value encoding/schema |

Do not call **locale**, **display-mode**, and **region** three values of the same cookie. They are three distinct cookies.

## 2. Cookie structure in HTTP

Clients send cookies in the **Cookie** header. Each pair has a name and value; multiple pairs are typically separated by semicolons:

~~~http
Cookie: locale=vi; display-mode=compact
~~~

Servers issue cookies in the response using the **Set-Cookie** header. Each cookie is sent in a separate `Set-Cookie` header:

~~~http
HTTP/1.1 200 OK
Set-Cookie: locale=vi; Path=/; Secure; SameSite=Lax
Set-Cookie: display-mode=compact; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Do not combine multiple **Set-Cookie** headers into one header separated by commas. The **Expires** attribute can contain a comma inside the date string, so joining them can cause parsers to misinterpret cookie boundaries.

In Spring REST Docs, each cookie is described with **cookieWithName(...)**:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Preferred client language code"),
    cookieWithName("display-mode")
        .description("UI mode saved by the client")
)
~~~

If the server returns two cookies:

~~~java
responseCookies(
    cookieWithName("locale")
        .description("Language code saved for subsequent visits"),
    cookieWithName("display-mode")
        .description("UI mode saved for subsequent visits")
)
~~~

**responseCookies(...)** describes cookies by name; **http-response.adoc** shows the recorded `Set-Cookie` headers. The two complement each other.

## 3. Character rules and why encoding is needed

A cookie value is not an arbitrary data zone like a JSON body. Cookie syntax restricts certain characters, such as spaces, semicolons, commas, double quotes, backslashes, and control characters. Unicode characters should also not be placed directly into a cookie value without an encoding convention.

Some characters that easily cause errors:

| Raw data | Problem if placed directly in cookie value | Encoded representation example |
| --- | --- | --- |
| **hello world** | Space is not in the standard `cookie-octet` set | **hello%20world** |
| **a;b** | The **;** character may be parsed as a cookie separator | **a%3Bb** |
| **a,b** | Comma is not in the standard `cookie-octet` set | **a%2Cb** |
| **a"b** | Double quote is not in the standard `cookie-octet` set | **a%22b** |
| **đăng nhập** | Contains Unicode and a space | **%C4%91%C4%83ng%20nh%E1%BA%ADp** |
| **50%** | Percent sign may be mistaken for an escape sequence | **50%25** |

The strings in the last column illustrate **UTF-8 percent-encoding**. This is a common application-layer convention and does not mean every HTTP client or servlet container automatically percent-decodes cookie values. Client and server must agree on the same encode/decode scheme.

**The Cookie header is neither a query string nor a form body.** Do not assume that plus signs will be decoded into spaces like some `application/x-www-form-urlencoded` decoders do.

## 4. Choosing how to represent a multi-part cookie

When a cookie holds a list or structured data, pick an explicit format rather than ad-hoc string concatenation.

### 4.1. Delimiter-separated list

Example convention for a list of feature flags, separated by a tilde (**~**), an allowed character in cookie values:

~~~text
feature-flags=beta~search~compact
~~~

If the delimiter can appear inside an element, you must escape/encode elements before joining, or choose a format with a standard parser. Otherwise, a value like **sales,west** cannot be distinguished as one element or two elements.

A strict convention:

1. Encode each element using UTF-8 percent-encoding.
2. Join the encoded elements with the agreed delimiter—in this example, a tilde (**~**).
3. When reading, split on the delimiter first, then decode each element exactly once.
4. Validate empty values, duplicates, length, and allowed value sets.

~~~text
Raw values:        ["beta", "sales,west", "tìm kiếm"]
Per element:       ["beta", "sales%2Cwest", "t%C3%ACm%20ki%E1%BA%BFm"]
Cookie value:      beta~sales%2Cwest~t%C3%ACm%20ki%E1%BA%BFm
After split/decode:
                   ["beta", "sales,west", "tìm kiếm"]
~~~

This is an **application-defined convention**. Document it in the contract and implement the same parser across all clients and servers.

### 4.2. Encoded JSON

If the cookie data is genuinely structured, JSON can be an option:

~~~json
{"theme":"dark","locale":"vi","flags":["beta","search"]}
~~~

Do not send raw arbitrary JSON in a cookie value. Serialize it as UTF-8, then encode according to the chosen convention (percent-encoding or Base64URL). Illustrative example using unpadded Base64URL:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String json = """
    {"theme":"dark","locale":"vi","flags":["beta","search"]}
    """.trim();

String encoded = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(json.getBytes(StandardCharsets.UTF_8));
~~~

Base64URL produces characters better suited for cookie values in many cases, but it is **not encryption**. Anyone holding the cookie can still Base64-decode it. Never store secret data in a cookie merely because it is encoded.

If a cookie value grows large due to JSON, lists, or data repeated across many requests, consider storing the data server-side and sending only a short identifier in the cookie. Because cookies are sent with many requests, large sizes increase bandwidth overhead and can hit client/server limits.

### 4.3. Multiple independent cookies instead of one complex cookie

If values have different lifecycles or purposes, splitting into separate cookies can be easier to manage:

~~~http
Cookie: locale=vi; display-mode=compact
~~~

Splitting cookies makes sense when clients can update each choice independently, when each value has a different `Path`/`Domain`/`Max-Age` or security policy, or when the API needs to document each value as a separate contract.

Keeping one composite cookie makes sense when data items always change together and share a stable schema. Avoid creating too many small cookies if they are only meaningful when used together.

## 5. Percent-encoding vs. Base64URL: making the right choice

| Approach | Best suited for | Pros | Notes |
| --- | --- | --- | --- |
| UTF-8 percent-encoding | Text strings, delimiters, and special characters | Partially human-readable, clear byte representation | Client/server must agree on decoding; **%** must be encoded when it is literal data |
| Base64URL | Binary blobs or serialized JSON | Avoids many delimiter characters in cookie values | Increases size; not security encryption |
| Delimiter-separated list | Simple value sets, restricted characters | Easy to read | Pick a valid cookie-value delimiter and escape when it appears inside elements |
| Separate cookie per value | Independent options | Easy to document and update individually | Increases number of cookies sent per request |

Avoid using **URLEncoder** as a general-purpose cookie encoder. `URLEncoder` produces `application/x-www-form-urlencoded` format, where spaces usually become plus signs. Cookie values do not automatically follow that rule. Use an encoding function matching your application's published cookie convention, or use Base64URL when representing byte data.

Never encode a value twice. If the raw value is **a;b**, one pass of percent-encoding yields **a%3Bb**; encoding the percent sign again produces **a%253Bb**. After one decode pass, the server still receives **a%3Bb** instead of **a;b**.

## 6. Implementing encode/decode at the application layer

The example below uses a simple convention: the **feature-flags** cookie is a list of UTF-8 percent-encoded elements separated by a tilde (**~**). That character belongs to the `cookie-octet` set. The code illustrates application logic; in production, use a battle-tested encoding library or shared parser rather than rolling your own general percent-encoder.

### 6.1. Example creating a cookie value

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import org.springframework.web.util.UriUtils;

class FeatureCookieCodec {

    String encode(List<String> flags) {
        return flags.stream()
            .map(value -> UriUtils.encode(value, StandardCharsets.UTF_8))
            .collect(java.util.stream.Collectors.joining("~"));
    }
}
~~~

**UriUtils.encode(...)** encodes data according to Spring's URI rules; confirm that the retained character set complies with your application's cookie contract. If you need strict adherence to `cookie-octet`, inspect the output and add validation before placing the value into a `Cookie`.

### 6.2. Example decoding with validation

Add the following method to **FeatureCookieCodec** above:

~~~java
List<String> decode(String cookieValue) {
    if (cookieValue == null || cookieValue.isBlank()) {
        return List.of();
    }

    return Arrays.stream(cookieValue.split("~", -1))
        .map(value -> UriUtils.decode(value, StandardCharsets.UTF_8))
        .toList();
}
~~~

For invalid input, the decoder may throw an exception; the API should catch the error and return a response per the contract rather than silently ignoring malformed data.

In production systems, add limits on item count, total length, per-element length, allowed character sets, duplicate/empty-element handling policies, and error responses for invalid escape sequences.

## 7. Documenting multi-value cookies with Spring REST Docs

Spring REST Docs documents **cookie names**; it does not automatically understand schemas inside values. Example for a cookie containing a list:

~~~java
requestCookies(
    cookieWithName("feature-flags")
        .description("List of feature flags separated by ~; each element is UTF-8 percent-encoded")
)
~~~

If a request sends multiple independent cookies:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Preferred language code, for example vi"),
    cookieWithName("display-mode")
        .description("UI mode, for example compact"),
    cookieWithName("feature-flags")
        .description("List of feature flags separated by ~; elements are UTF-8 percent-encoded")
)
~~~

If a response returns multiple cookies:

~~~java
responseCookies(
    cookieWithName("locale")
        .description("Language saved for subsequent visits"),
    cookieWithName("display-mode")
        .description("Saved UI mode"),
    cookieWithName("feature-flags")
        .description("List of feature flags separated by ~ per the API convention")
)
~~~

Do not turn each element of **feature-flags** into multiple descriptors with the same name. The descriptor is for the **feature-flags** cookie; the list schema should be explained in the description or a dedicated prose section.

### 7.1. Combining cookies with response fields

If the API also returns the list in a JSON body, document the body with **responseFields(...)**:

~~~java
document("profile-preferences",
    requestCookies(
        cookieWithName("feature-flags")
            .description("List of feature flags, UTF-8 percent-encoded")
    ),
    responseFields(
        fieldWithPath("enabledFeatures")
            .description("Feature flags after the server decodes the cookie")
    )
)
~~~

Cookie descriptors and payload descriptors describe two different data locations. Do not use **requestFields(...)** for cookies because cookies are not in the JSON request body.

## 8. MockMvc test example with multi-named cookies and encoded values

The example uses **Java 17+**, **Spring Boot 3.x**, **JUnit 5**, and **spring-restdocs-mockmvc**.

### 8.1. Controller reading cookies

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriUtils;

@RestController
class PreferenceController {

    @GetMapping("/api/preferences")
    PreferenceView getPreferences(
            @CookieValue(name = "locale", defaultValue = "vi") String locale,
            @CookieValue(name = "feature-flags", required = false) String featureFlags) {

        List<String> flags = featureFlags == null || featureFlags.isBlank()
            ? List.of()
            : Arrays.stream(featureFlags.split("~", -1))
                .map(value -> UriUtils.decode(value, StandardCharsets.UTF_8))
                .toList();

        return new PreferenceView(locale, flags);
    }
}

record PreferenceView(String locale, List<String> enabledFeatures) {}
~~~

This is an illustrative parser for the stated delimiter contract. Real applications should validate input, limit item count/length, and handle exceptions on invalid encoding.

### 8.2. Test generating the request-cookies snippet

~~~java
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PreferenceController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PreferenceCookieEncodingTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsMultipleCookiesAndEncodedListValue() throws Exception {
        mockMvc.perform(get("/api/preferences")
                .cookie(
                    new Cookie("locale", "vi"),
                    new Cookie("feature-flags",
                        "beta~sales%2Cwest~t%C3%ACm%20ki%E1%BA%BFm")
                )
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi"))
            .andExpect(jsonPath("$.enabledFeatures[0]").value("beta"))
            .andExpect(jsonPath("$.enabledFeatures[1]").value("sales,west"))
            .andExpect(jsonPath("$.enabledFeatures[2]").value("tìm kiếm"))
            .andDo(document("preferences-cookie-list",
                requestCookies(
                    cookieWithName("locale")
                        .description("Preferred language code"),
                    cookieWithName("feature-flags")
                        .description("List of feature flags; UTF-8 percent-encoded elements separated by ~")
                )
            ));
    }
}
~~~

The MockMvc test sends two independent cookies. The **feature-flags** cookie holds a single value containing three items separated by `~`. The item with an internal comma is encoded as **%2C**, while Vietnamese text is UTF-8 encoded. Tilde `~` is chosen because it belongs to `cookie-octet`; never use a raw comma as a cookie delimiter.

The Servlet API and MockMvc manage cookies as individual objects. When testing with a real HTTP client, the `Cookie` header on the wire consists of multiple `name=value` pairs separated by semicolons; inspect actual requests if you need to verify network-level encoding.

### 8.3. Testing a multi-value response cookie

If the server returns a cookie containing a list, the controller can create one cookie:

~~~java
Cookie features = new Cookie(
    "feature-flags",
    "beta~sales%2Cwest~t%C3%ACm%20ki%E1%BA%BFm");
features.setPath("/");
features.setHttpOnly(true);
features.setSecure(true);
response.addCookie(features);
~~~

Documentation:

~~~java
responseCookies(
    cookieWithName("feature-flags")
        .description("List of feature flags; elements are UTF-8 percent-encoded and separated by ~")
)
~~~

Tests should assert the actual cookie value and can use **responseCookies(...)** to generate **response-cookies.adoc**. If the value contains sensitive data, use dummy test values or appropriate preprocessing before writing snippets.

## 9. Combining encoding with security and size limits

Encoding is not security encryption:

- Percent-encoding merely converts bytes into **%HH** notation; anyone reading the cookie can still decode it.
- Base64URL only changes representation; it does not protect confidentiality or integrity.
- Cookies can be modified client-side unless the server uses an appropriate signing/authentication mechanism.

Never store sensitive data or authorization permission lists in client-editable cookies without server-side signing and verification. For sessions/authentication, prefer cookies carrying unpredictable session identifiers with authorization data controlled server-side.

Cookies also have size and count limits depending on browsers, servers, and infrastructure. RFC 6265 specifies minimums that user agents should support, but you should not design an API to rely on an exact limit across all browsers. Keep cookies small, avoid repeating large JSON payloads on every request, and verify limits in your deployment environment.

When multiple cookies are set in the same response, each cookie needs its own **Set-Cookie** with appropriate `Path`/`Domain`/`Secure`/`SameSite`. Cookies with the same name but different `Path` or `Domain` can coexist on the client; servers should avoid ambiguous designs when reading them.

## 10. Integrating snippets into Asciidoctor and CI

After tests generate **preferences-cookie-list**, the expected snippet structure is:

~~~text
build/generated-snippets/
└── preferences-cookie-list/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-cookies.adoc
~~~

In **src/docs/asciidoc/preferences.adoc**:

~~~asciidoc
= Preferences API
:toc: left

== Get user preferences

GET /api/preferences

=== Request cookies

include::{snippets}/preferences-cookie-list/request-cookies.adoc[]

=== HTTP request

include::{snippets}/preferences-cookie-list/http-request.adoc[]

=== HTTP response

include::{snippets}/preferences-cookie-list/http-response.adoc[]

The feature-flags cookie holds a list of feature flags. Elements are individually UTF-8 percent-encoded and separated by ~; the server splits first and then decodes each element once.
~~~

Gradle Groovy DSL example when the **org.asciidoctor.jvm.convert** plugin is configured:

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

In CI, run tests before Asciidoctor. Tests should verify that decoded values match expected data; documentation must clearly state the delimiter, charset, and encode/decode order. Inspect request snippets as well to make sure no secret values or oversized cookies are published.

If the final output is Markdown, use a compatible converter or embedding mechanism; **include::{snippets}/...[]** is Asciidoctor syntax, not standard Markdown.

## 11. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Request has multiple cookies but table only has one row | Only declared one descriptor | Declare each name in **requestCookies(...)** |
| A list cookie is mistaken for multiple cookies | Confused a value delimiter with the cookie separator | Distinguish semicolons between cookies from application-defined delimiters inside values |
| Element containing a comma splits incorrectly | Did not encode delimiters inside elements | Encode delimiters inside elements before joining |
| Corrupted Unicode values | Client and server use different charsets | Standardize on UTF-8 and check bytes/encoded values |
| Plus sign unexpectedly turns into a space | Used form decoding on a cookie | Specify percent-decoding or Base64URL explicitly; never assume plus-sign rules |
| Value still contains **%20** after reading | Not decoded or decoded at the wrong layer | Decode exactly once at the designated boundary |
| Value **%2520** appears | Double encoding | Keep raw data until encoding; never re-encode an already encoded value |
| Cookie rejected by server | Contains spaces, semicolons, commas, or characters outside `cookie-octet` | Encode/validate values before issuing |
| REST Docs reports mismatched descriptor | Wrong cookie name or mixed up request/response | Match the actual name and descriptor group |
| Cookie too large or request header too long | Stuffed too much data into cookies | Trim data, split appropriately, or store server-side |

## 12. Practice exercise

Design an endpoint:

~~~text
GET /api/catalog
~~~

Cookie contract:

- **locale** is a separate cookie with value **vi** or **en**.
- **feature-flags** is a single cookie containing a list of feature flags.
- **feature-flags** elements are individually UTF-8 percent-encoded and joined with `~`.
- The server splits the list first and decodes each element exactly once.

Test values:

~~~text
Elements:     ["beta", "sales,west", "tìm kiếm"]
Cookie value: beta~sales%2Cwest~t%C3%ACm%20ki%E1%BA%BFm
~~~

Requirements:

1. Write a parser for **feature-flags** and validate empty inputs, delimiters, invalid escapes, and duplicate items.
2. Write a MockMvc test sending both **locale** and **feature-flags**.
3. Assert that the JSON response contains all three elements after decoding.
4. Use **requestCookies(...)** with two separate descriptors for **locale** and **feature-flags**.
5. Add a response test issuing **feature-flags** and using **responseCookies(...)**.
6. Clearly document UTF-8 charset, delimiter, split/decode order, and length limits.
7. Include cookie snippets in Asciidoctor and run `test → asciidoctor` in CI.

**Completion criteria:** multiple cookies are properly distinguished from a list cookie; encoded values are decoded accurately once; descriptors match each name; snippets and documentation specify the cookie schema clients must follow.

## Key Takeaways

A request can carry multiple independent cookies, while a single cookie can hold a list or structured data under an application-specific convention. **requestCookies(...)** and **responseCookies(...)** document each cookie by name; they do not automatically understand schemas inside values. Cookie values have character restrictions, so choose a valid `cookie-octet` delimiter, specify encoding such as UTF-8 percent-encoding or Base64URL, define decode order, and enforce size limits. Encoding is not security encryption and does not replace server-side signing/verification. Test encoded values via MockMvc, generate snippets with Spring REST Docs, and document the convention clearly in Asciidoctor/CI.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [RFC 6265: HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265), and [RFC 4648: Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648).
