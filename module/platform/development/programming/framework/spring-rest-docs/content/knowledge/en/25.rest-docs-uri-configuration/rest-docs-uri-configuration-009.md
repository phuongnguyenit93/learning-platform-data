# Masking Hosts or Replacing URI Patterns

## 1. Learning Objectives

In the SPRING_REST_DOCS module, we create verifiable REST API documentation through HTTP tests with MockMvc, WebTestClient, or REST Assured. Tests send requests, assert responses, and Spring REST Docs generates snippets for requests, responses, payloads, parameters, and headers. These snippets are compiled with Asciidoctor/Markdown and integrated into builds and CI.

Actual requests and responses sometimes contain internal hostnames, test environment domains, URLs with tokens, or long hypermedia links. Documentation needs to illustrate the API structure without necessarily exposing every environment value or private URI. Spring REST Docs provides operation preprocessors to modify the request/response representation before generating snippets.

This lesson focuses on three tools:

- `modifyUris()`: replaces the scheme, host, and port of URIs in an operation.
- `maskLinks()`: masks the `href` of hypermedia links in requests/responses.
- `replacePattern(Pattern, String)`: replaces content matching a regular expression.

After this lesson, you will be able to choose the right tool to normalize hosts, hide hypermedia links, or replace a URI pattern in payloads; combine them with `preprocessRequest(...)`/`preprocessResponse(...)`; and inspect snippets to ensure documentation remains meaningful.

## 2. Why Mask or Replace URIs?

Suppose a test runs against an internal hostname:

~~~http
GET http://orders-service.test.svc.cluster.local:8080/api/orders/42 HTTP/1.1
~~~

The response returns hypermedia links:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "http://orders-service.test.svc.cluster.local:8080/api/orders/42"
    },
    "payment": {
      "href": "http://payments.internal.local/private/txn/93821"
    }
  }
}
~~~

When publishing documentation, you may need to replace the test hostname with a sandbox/public hostname, mask a hypermedia link if clients should discover the API through link relations, or replace transaction IDs and private URI segments with placeholders.

There is no need to alter the actual request or response processed by the application. Preprocessors act on the operation copy that Spring REST Docs prepares to write as snippets.

## 3. Choosing the Right Preprocessor

The three tools solve three different problems:

| Tool | Scope of Change | Suitable Use Case |
| --- | --- | --- |
| modifyUris() | URIs in requests/responses, including request URI, headers, and content with URIs | Replacing host/scheme/port from the test environment with the documented address. |
| maskLinks() | `href` values of hypermedia links | Hiding link URIs so readers focus on link relations and use links returned by the server. |
| replacePattern(...) | Request or response content matching a regex | Replacing a structured URI pattern/path segment/identifier with a placeholder. |

~~~mermaid
flowchart TD
    A["Need to transform URIs in snippets?"] --> B{"Which part needs changing?"}
    B -->|"Scheme / host / port"| C["modifyUris()"]
    B -->|"Hypermedia href"| D["maskLinks()"]
    B -->|"A string/pattern in body"| E["replacePattern()"]
    C --> F["Inspect request/response snippet"]
    D --> F
    E --> F
~~~

If you only want to change a host, do not use a broad regex to replace every URL-like string. If you want to hide hyperlinks, do not delete the entire response body. Choose the preprocessor based on the structure you want to preserve.

## 4. Replacing Hostnames with modifyUris()

`modifyUris()` returns a `UriModifyingOperationPreprocessor`. It can replace the scheme, host, or port of URIs in the request/response operation.

Static imports:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
~~~

Example replacing an internal hostname with a sandbox hostname:

~~~java
preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("sandbox-api.example.com")
        .removePort()
)
~~~

When used in MockMvc:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("sandbox-api.example.com")
                .removePort()
        )
    ));
~~~

The request snippet is recorded with the sandbox address. The actual request destination in MockMvc does not change.

### 4.1. Replacing Host While Keeping Scheme and Port

If you only call `modifyUris().host("sandbox-api.example.com")`, the preprocessor replaces the host and leaves the scheme/port from the source URI. This is useful if the scheme and port are already right, though you should inspect the resulting URL in the snippet because the test environment's port may still remain.

### 4.2. Replacing Scheme, Host, and Port

~~~java
modifyUris()
    .scheme("https")
    .host("api.example.com")
    .port(8443)
~~~

The recorded URI looks like:

~~~text
https://api.example.com:8443/api/orders/42
~~~

If the API uses the default port and you do not want the port displayed, use `removePort()`. Choose the address clients actually need to call; do not replace it with a production hostname if the documentation set is for sandbox.

### 4.3. Normalizing URIs in Responses as Well

Some responses have `Location` headers or hypermedia links containing an internal hostname. You can apply the URI modifier to responses:

~~~java
preprocessResponse(
    modifyUris()
        .scheme("https")
        .host("sandbox-api.example.com")
        .removePort()
)
~~~

`modifyUris()` is designed to modify URIs throughout the operation, not just the request line. It can affect URIs in request/response headers and content. Carefully inspect the modified URIs in snippets, especially when responses contain links to multiple different services.

## 5. Masking Hypermedia Links with maskLinks()

If an API uses HAL or a similar hypermedia format, responses may provide links such as `self`, `next`, or `payment`. `maskLinks()` replaces link `href` values with a default masking symbol, a typographic ellipsis.

Imports:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.maskLinks;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
~~~

Example:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        preprocessResponse(maskLinks())
    ));
~~~

The response snippet still describes the representation structure and link relations, while `href` values are masked.

Before masking:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "payment": {
      "href": "https://payments.example.com/api/payments/93821"
    }
  }
}
~~~

After masking:

~~~json
{
  "_links": {
    "self": {
      "href": "…"
    },
    "payment": {
      "href": "…"
    }
  }
}
~~~

This is useful when you want readers to follow link relations instead of hard-coding URIs. Do not use `maskLinks()` if documentation needs to show the specific URL clients must call; in that case, normalize the URI with `modifyUris()` or intentionally preserve sample links.

### 5.1. Customizing the Replacement String

You can pass a custom replacement string:

~~~java
preprocessResponse(
    maskLinks("[link omitted]")
)
~~~

The snippet will use `[link omitted]` instead of the `href` value. Choose a placeholder that is clear to readers and consistent across operations.

## 6. Replacing URI Patterns with replacePattern()

`replacePattern(Pattern, String)` provides a general mechanism to replace any content matching a regex in requests or responses.

Imports:

~~~java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
~~~

Example response with an internal URI containing a transaction ID:

~~~json
{
  "id": 42,
  "receiptUrl": "https://payments.internal.local/private/transactions/93821"
}
~~~

You can replace the hostname and transaction ID using a specific pattern:

~~~java
preprocessResponse(
    replacePattern(
        Pattern.compile("https://payments\\.internal\\.local/private/transactions/[0-9]+"),
        "https://payments.example.com/transactions/{transactionId}"
    )
)
~~~

The snippet will show the sample URI:

~~~json
{
  "id": 42,
  "receiptUrl": "https://payments.example.com/transactions/{transactionId}"
}
~~~

The regex is applied to the content of the recorded request/response. It does not parse JSON and is not a specialized tool for replacing request-line URIs or header URIs. If the goal is to replace URIs in URI positions recognized by REST Docs, prefer `modifyUris()`. If a URI lives inside a custom body field, `replacePattern(...)` can process that content. The pattern must be specific enough, because any content matching the regex can be replaced, even non-URI text.

### 6.1. Replacing a Path Segment

If the host is already right and only the identifier needs replacing:

~~~java
replacePattern(
    Pattern.compile("/transactions/[0-9]+"),
    "/transactions/{transactionId}"
)
~~~

The output preserves the domain and unrelated path segments:

~~~text
https://payments.example.com/transactions/{transactionId}
~~~

### 6.2. Using Capture Groups in Regex

A pattern can preserve part of the URI:

~~~java
replacePattern(
    Pattern.compile("https://([^/]+)/private/transactions/[0-9]+"),
    "https://$1/transactions/{transactionId}"
)
~~~

Capture group `$1` preserves the matched hostname. This works well when multiple valid hostnames exist and you want to remove the private path segment. When writing the replacement in a Java string, use `$1` for the capture group; escape backslashes in Java regex strings with double backslashes.

## 7. Combining modifyUris() and replacePattern()

A response may contain both a test environment host and a URI path that should be hidden. You can chain both preprocessors inside `preprocessResponse(...)`:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get",
        preprocessResponse(
            modifyUris()
                .scheme("https")
                .host("sandbox-api.example.com")
                .removePort(),
            replacePattern(
                Pattern.compile("/private/transactions/[0-9]+"),
                "/transactions/{transactionId}"
            )
        )
    ));
~~~

Preprocessors are applied in the order passed. `modifyUris()` normalizes the URI first; `replacePattern(...)` then replaces the path pattern in the processed operation content. Verify the final output to make sure the pattern still matches after the first normalization step.

If you want to process both requests and responses, declare the corresponding preprocessor for each side:

~~~java
document("orders/get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("sandbox-api.example.com")
            .removePort()
    ),
    preprocessResponse(
        maskLinks("[link omitted]")
    )
)
~~~

Do not pass a response preprocessor in the request position or vice versa. `document(...)` accepts the request preprocessor first and the response preprocessor second.

## 8. Complete MockMvc Example

The example below illustrates a response with a `self` link and a receipt URL. The test verifies the actual HTTP response, while REST Docs generates a normalized snippet with the transaction ID masked.

~~~java
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class UriMaskingDocumentationTest {

    private final MockMvc mockMvc;

    UriMaskingDocumentationTest(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @Test
    void documentsOrderWithSanitizedUris() throws Exception {
        this.mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andDo(document("orders/get",
                preprocessResponse(
                    modifyUris()
                        .scheme("https")
                        .host("sandbox-api.example.com")
                        .removePort(),
                    replacePattern(
                        Pattern.compile("/private/transactions/[0-9]+"),
                        "/transactions/{transactionId}"
                    )
                )
            ));
    }
}
~~~

This example assumes MockMvc is already configured with the REST Docs filter and the endpoint returns a JSON response containing URIs in links/body. `modifyUris()` replaces the URI scheme/host/port; `replacePattern(...)` replaces the private path segment. The response returned by the endpoint for assertions remains the real response.

If the goal is to mask all hypermedia `href` values rather than replacing a specific URI pattern, use `preprocessResponse(maskLinks())`. There is no need to write custom regexes to parse JSON links.

## 9. Distinguishing URI Replacement and Link Masking

| Need | Choice | Result |
| --- | --- | --- |
| Change host `orders.test.local` to `api.example.com` while keeping the path | `modifyUris().host("api.example.com")` | `href` remains a readable URI accessible under the new domain. |
| Hide target URLs of hypermedia links | `maskLinks()` | `href` is replaced with a placeholder. |
| Hide only a transaction ID inside a URI | `replacePattern(...)` | Preserves URL structure and replaces the ID portion with a sample token. |
| Replace scheme, host, and port together | `modifyUris()` with multiple setters | Processed URIs use the selected authority. |
| Fix a URI string in JSON not recognized as a link | `replacePattern(...)` | Replaces regex-matching text anywhere in the content. |

`maskLinks()` is intended for hypermedia links with an `href` field; `replacePattern(...)` is general string replacement. If the response is custom JSON and the URI resides in `receiptUrl`, `downloadUrl`, or another field, `replacePattern(...)` can be a better fit provided the pattern is sufficiently precise.

## 10. Caution When Using Regex

`replacePattern(...)` does not semantically parse JSON, XML, or URIs. It performs regex-based string replacement on the operation content. Common mistakes:

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Overly broad pattern such as `https://.*` | Replaces multiple unrelated URLs or consumes too many characters. | Constrain the hostname, path segments, and terminating characters. |
| Forgetting to escape dots in hostnames | Regex matches any character instead of literal dots. | Use `\\.` in Java regex strings. |
| Replacing IDs with a digits-only pattern | May replace other business numbers in the body. | Anchor the pattern to a specific path like `/transactions/[0-9]+`. |
| Invalid `$` in replacement | Java regex treats `$1` as a group reference; replacement can fail if the group does not exist. | Verify capture group numbers or use replacement strings without group tokens. |
| Assuming regex replaces only inside one JSON field | The pattern can match anywhere in the content. | Write specific patterns and inspect the entire snippet after processing. |
| Using regex to hide all hypermedia `href`s | Can break JSON structure or replace unrelated URLs. | Use `maskLinks()` for hypermedia links. |

Do not use a preprocessor to mask sensitive data and assume the test data is now safe. Requests and responses still exist during test execution, in logs, and in other systems. Use dummy fixtures for tests and check where data is stored before sharing artifacts.

## 11. Inspecting Snippets After Preprocessing

After tests run, open the corresponding operation snippet, for example:

~~~text
build/generated-snippets/orders/get/http-response.adoc
~~~

Check:

1. Whether the host changed to the right sandbox/public domain.
2. Whether the scheme and port match the documented URI policy.
3. Whether hypermedia `href` values are masked with the expected placeholder.
4. Whether the URI pattern replaced only the intended part without affecting other IDs or paths.
5. Whether JSON/XML remains valid and key payload parts are still readable.
6. Whether response assertions in tests still check the real values rather than post-preprocessing values.

A preprocessor can make snippets cleaner, but it does not replace assertions. Tests must verify the application returns the right response before REST Docs transforms the record for documentation.

## 12. Integrating Asciidoctor and CI

Asciidoctor can include preprocessed request/response snippets:

~~~asciidoc
= Orders API
:snippets: build/generated-snippets

== Get Order

=== HTTP response
include::{snippets}/orders/get/http-response.adoc[]
~~~

Assuming the Asciidoctor plugin is configured, link the documentation build task to tests:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

CI can run:

~~~bash
./gradlew clean test asciidoctor
~~~

Tests verify API behavior; preprocessors produce documentation-ready request/response representations; Asciidoctor assembles fresh snippets. When hostnames or URI formats change, review preprocessed snippets alongside API changes.

With plain Markdown, Asciidoctor's `include::` syntax is not processed automatically. A separate build step is needed to embed snippets or link to generated files.

## 13. Common Errors and How to Fix Them

| Symptom | Cause and Resolution |
| --- | --- |
| Internal host still appears | `modifyUris()` was not applied to the right request/response side, or the URI is in a content format the preprocessor does not recognize. |
| Response URI unchanged while request changed | Preprocessor was only placed in `preprocessRequest(...)`; add `preprocessResponse(...)` if the response also needs normalization. |
| Hypermedia `href` is still long | Use `maskLinks()` in the response preprocessor and verify links follow a supported hypermedia format. |
| Unrelated URLs also replaced | `replacePattern(...)` regex is too broad; narrow the pattern by hostname and path. |
| JSON snippet is no longer valid | Pattern replaced quotes or structural characters; adjust the regex/replacement and re-read the payload. |
| Other IDs masked unintentionally | Pattern matches any number sequence; tie the pattern to a specific path segment. |
| Tests pass even though snippet is masked wrongly | Assertions check the original response; add snippet checks/reviews for important documentation rules. |
| Snippet still contains sensitive data | Did not identify all locations containing the data, or processed response while forgetting request; audit both sides. |

## 14. Practice Exercises

1. Create a HAL response whose `_links.self.href` contains an internal hostname.
2. Use `modifyUris()` to replace scheme/host/port and inspect the snippet.
3. Use `maskLinks()` to replace all `href` values; compare the JSON structure before and after.
4. Set `maskLinks("[link omitted]")` and check how the placeholder renders in the snippet.
5. Create a `receiptUrl` containing a transaction ID; use `replacePattern(Pattern, String)` to replace the ID with `{transactionId}`.
6. Intentionally try a broad regex, observe unintended strings being replaced, and then narrow the pattern.
7. Combine `modifyUris()` and `replacePattern(...)` in one response preprocessor; verify ordering and results.
8. Run `./gradlew clean test asciidoctor` and review response snippets before publishing documentation to CI artifacts.

## 15. Key Takeaways

- `modifyUris()` replaces scheme, host, and port of URIs in request/response operations; use it to normalize environment hostnames.
- `maskLinks()` replaces `href` in hypermedia links with a placeholder; ideal when clients should discover the API via link relations.
- `replacePattern(Pattern, String)` replaces regex-matched content in requests or responses; suited for specific URI patterns/identifiers.
- Use `preprocessRequest(...)` for requests and `preprocessResponse(...)` for responses.
- Keep regexes specific; string preprocessors do not parse JSON/XML structures.
- Preprocessors only modify the record used to generate snippets; they do not alter actual endpoint requests/responses and do not replace assertions.
- Always re-read snippets after processing to verify hosts are normalized, links are masked properly, and payloads remain meaningful.

## 16. References

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): documentation on `maskLinks`, `modifyUris`, `replacePattern`, and preprocessors.
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): factory methods and processing scope of preprocessors.
