# Masking Tokens and Hosts with Preprocessors

## 1. Practice Objectives

In an HTTP operation, REST API documentation may capture many values that need sanitization: `Authorization` headers, API keys, session cookies, access/refresh tokens in JSON, query values, internal hostnames, and dynamic test environment ports. A single preprocessor does not handle every data region. You must choose the right tool based on where the data lives:

- **modifyHeaders()**: set or remove request/response headers.
- **replacePattern()**: replace patterns in request/response content, typically body text.
- **modifyUris()**: normalize URI scheme, host, and port.
- **maskLinks()**: mask `href` values of hypermedia links recognized in content.

This lesson belongs to the **Capstone Practice** chapter of the **SPRING_REST_DOCS** module. The module produces verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generates snippets for requests, responses, payloads, parameters, and headers; assembles Asciidoctor/Markdown; and integrates into the build and CI.

This practice combines those techniques in a verifiable workflow. The desired outcome is snippets that still express the API contract without exposing credentials or internal environment addresses.

After this lesson, you will be able to:

- Classify sensitive data by header, body, and URI.
- Replace `Authorization`/API keys/cookies with placeholders.
- Mask tokens/passwords in JSON bodies.
- Normalize hosts and ports of request/response URIs.
- Mask hypermedia `href` values while preserving link relations.
- Identify when query parameters require synthetic values or a custom request preprocessor.
- Scan all snippets and rendered documentation before publishing.

## 2. Preparing the Scenario and Synthetic Data

Suppose the service has an endpoint that retrieves an order and returns hypermedia links:

**Request**

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.internal.cluster.local:8087
Authorization: Bearer DOCS_ONLY_ACCESS_TOKEN
X-Api-Key: DOCS_ONLY_API_KEY
Cookie: JSESSIONID=DOCS_ONLY_SESSION
Accept: application/json
~~~

**Response**

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Set-Cookie: SESSION=DOCS_ONLY_RESPONSE_SESSION; Path=/; HttpOnly; Secure

{
  "id": 42,
  "status": "PAID",
  "accessToken": "DOCS_ONLY_RESPONSE_TOKEN",
  "_links": {
    "self": {
      "href": "http://orders.internal.cluster.local:8087/api/orders/42"
    },
    "payment": {
      "href": "http://payments.internal.cluster.local:8092/checkout?ticket=DOCS_ONLY_TICKET"
    }
  }
}
~~~

The `DOCS_ONLY_*` values are synthetic sentinels, not real credentials. Use sentinels to verify redaction: if any sentinel value remains in the generated output, the check must fail.

### 2.1. Creating a Handling Table Before Writing Code

| Data | Location | Handling |
| --- | --- | --- |
| Bearer token | Request `Authorization` | Set a placeholder or remove the header. |
| API key | Request `X-Api-Key` | Set a placeholder or remove the header. |
| Session cookie | Request `Cookie` | Remove the header. |
| Response session | Response `Set-Cookie` | Remove or set a placeholder. |
| `accessToken` | JSON response body | `replacePattern` or a JSON-aware modifier. |
| Internal host/port | URI | `modifyUris` to normalize scheme/host/port. |
| Hypermedia `href` | JSON HAL links | `maskLinks` if masking all `href` values. |
| Query `ticket` | Request URI or `href` | Synthetic value; custom URI preprocessor if request URI needs replacement. |

This table helps you choose the right API. Do not apply a single blanket regex across the entire HTTP dump and assume every data category is masked.

## 3. Normalizing Host and Port with `modifyUris()`

In tests, the server may run on `localhost` or a random port; recorded request/response URIs may contain internal addresses. Spring REST Docs provides `modifyUris()` to replace scheme, host, and port.

Example normalizing the request URI to a documentation host:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.test")
        .removePort()
)
~~~

If you want to set a fixed port, use the corresponding port configuration on `ModifyUrisOperationPreprocessor` instead of `removePort`.

### 3.1. Limitations of `modifyUris()`

`modifyUris()` handles URI components such as scheme, host, and port. Do not treat it as a tool to:

- Remove query parameters.
- Replace tokens in a JSON body.
- Replace `Authorization`/`Cookie` headers.
- Replace path segments.
- Find every URL inside free-text responses.

Example URI with a query:

~~~text
http://orders.internal.cluster.local:8087/oauth/callback?code=DOCS_ONLY_CODE
~~~

After normalizing the host/port, the `code` query parameter can still remain intact. Use a synthetic value in the test or a custom request preprocessor if you need to replace queries in the request URI.

### 3.2. Normalizing the Host Does Not Necessarily Mean Masking the Host

If a public/sandbox hostname is part of the API usage guide, replacing the internal host with the documentation host can be more helpful than masking the entire URI. If the endpoint is strictly for internal docs, you can use an internal hostname approved for that audience. Decide based on classification and audience.

## 4. Masking Request Headers with `modifyHeaders()`

Set placeholders for `Authorization` and the API key, while removing the session cookie:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

preprocessRequest(
    modifyHeaders()
        .set("Authorization", "Bearer <access-token>")
        .set("X-Api-Key", "<api-key>")
        .remove("Cookie")
)
~~~

Header names still appear so readers know what the API requires. The values are replaced with non-functional placeholders.

If documentation does not need to show sensitive header names, remove them:

~~~java
preprocessRequest(
    modifyHeaders()
        .remove("Authorization")
        .remove("X-Api-Key")
        .remove("Cookie")
)
~~~

Choose `set` or `remove` based on the documentation's purpose. Do not remove `Content-Type`, `Accept`, or other contract headers if readers need them to call the API.

## 5. Handling Response Headers

Responses may issue session cookies or tokens in custom headers. Use a separate response preprocessor:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

preprocessResponse(
    modifyHeaders()
        .remove("Set-Cookie")
        .remove("X-Internal-Trace")
)
~~~

If you need to explain cookie attributes, replace the value while keeping the attributes:

~~~java
preprocessResponse(
    modifyHeaders()
        .set("Set-Cookie", "SESSION=<session-id>; Path=/; HttpOnly; Secure")
)
~~~

Do not expect a request preprocessor to sanitize response headers automatically. Both request and response directions must be configured separately.

## 6. Masking Tokens in the Body with `replacePattern()`

Example response body:

~~~json
{
  "id": 42,
  "status": "PAID",
  "accessToken": "DOCS_ONLY_RESPONSE_TOKEN",
  "refreshToken": "DOCS_ONLY_REFRESH_TOKEN"
}
~~~

You can use a regex targeting specific string fields:

~~~java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

private static final Pattern TOKEN_FIELDS = Pattern.compile(
    "(\"(accessToken|refreshToken)\"\\s*:\\s*\")[^\"]*(\")"
);

preprocessResponse(
    replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3")
)
~~~

Expected result:

~~~json
{
  "id": 42,
  "status": "PAID",
  "accessToken": "[REDACTED]",
  "refreshToken": "[REDACTED]"
}
~~~

The pattern must match the actual payload. This illustrative regex is for simple JSON strings; if the body contains escaped quotes, complex nested structures, or multiple media types, use a JSON-aware `ContentModifier` to parse, replace the exact properties, and serialize back.

### 6.1. Do Not Confuse Body Replacement with Header Replacement

`replacePattern()` processes request/response content. It does not operate directly on the header collection. For `Authorization`, `Cookie`, or `Set-Cookie`, use `modifyHeaders().set/remove()`.

Looking only at the final `http-request` file, headers and body may sit side by side in the same snippet text. That does not mean the two regions are processed by the same API.

## 7. Masking Hypermedia `href` with `maskLinks()`

HAL responses may contain `href` values with internal hostnames or query tickets. If the goal is to mask all hypermedia `href` values, use `maskLinks()`:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.maskLinks;

preprocessResponse(
    maskLinks("[LINK]")
)
~~~

`maskLinks()` targets `href` values of hypermedia links recognized in content. Link relations such as `self`, `payment`, and `cancel` can still be documented with `links` descriptors.

### 7.1. When to Use `maskLinks` vs. `modifyUris`?

| Need | Choice |
| --- | --- |
| Mask every `href` in hypermedia links | `maskLinks()` |
| Replace internal host with public/sandbox host | `modifyUris()` if the URI is within preprocessor scope |
| Remove `Authorization`/`Cookie` | `modifyHeaders()` |
| Replace token fields in JSON | `replacePattern()` or `ContentModifier` |
| Mask query values in request URI | Synthetic test values or custom request preprocessor |
| Mask URLs inside plain JSON strings | Fake fixtures, `replacePattern`, or JSON-aware modifier |

If you need to keep URLs so readers understand the structure, normalizing host/port can be appropriate. If an `href` contains a usable signed URL, mask the entire `href` or use a fixture without a real signature.

## 8. Combining Preprocessors in One Operation

One operation can apply request and response preprocessors at the same time:

~~~java
.andDo(document("orders-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-Api-Key", "<api-key>")
            .remove("Cookie"),
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    ),
    preprocessResponse(
        modifyHeaders()
            .remove("Set-Cookie")
            .remove("X-Internal-Trace"),
        replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3"),
        maskLinks("[LINK]"),
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    )
));
~~~

This is an illustrative configuration. Imports, overloads, and combination order must match your project's Spring REST Docs version. If `maskLinks()` is used, `href` values may already be replaced with a placeholder; `modifyUris()` afterward has no concrete host left to normalize. Choose one appropriate way to handle links instead of applying both redundantly.

### 8.1. Extracting Shared Helpers

You can centralize header policies:

~~~java
private static OperationRequestPreprocessor sanitizeRequest() {
    return preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-Api-Key", "<api-key>")
            .remove("Cookie"),
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    );
}

private static OperationResponsePreprocessor sanitizeResponse() {
    return preprocessResponse(
        modifyHeaders().remove("Set-Cookie"),
        replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3")
    );
}
~~~

Then attach the helpers to operations:

~~~java
.andDo(document("orders-get",
    sanitizeRequest(),
    sanitizeResponse()
));
~~~

Placing policies in helpers reduces the risk of an operation forgetting redaction. For endpoints with HAL responses or sensitive links, add `maskLinks` or dedicated custom logic.

## 9. Handling Query Parameters and URL Text

`modifyUris()` is not a query masking tool; `maskLinks()` does not mask general request URIs. For queries containing tokens, prefer safe test fixtures:

~~~java
mockMvc.perform(get("/oauth/callback")
        .queryParam("code", "DOCS_ONLY_CODE")
        .queryParam("state", "DOCS_ONLY_STATE"))
    .andExpect(status().isOk())
    .andDo(document("oauth-callback"));
~~~

If the request URI must be built from dynamic values, write a custom `OperationRequestPreprocessor` to parse the URI, replace the values of the specific sensitive keys, and build a new request using your REST Docs version's API/factory. Preserve encoding, duplicate keys, method, headers, and body.

If a URL appears inside a JSON field such as `redirectUrl`, use fake fixtures, `replacePattern` on response content, or a JSON-aware modifier. Do not assume `maskLinks` recognizes every string URL.

## 10. MockMvc Integration Example

~~~java
mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer DOCS_ONLY_ACCESS_TOKEN")
        .header("X-Api-Key", "DOCS_ONLY_API_KEY")
        .cookie(new Cookie("JSESSIONID", "DOCS_ONLY_SESSION")))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        preprocessRequest(
            modifyHeaders()
                .set("Authorization", "Bearer <access-token>")
                .set("X-Api-Key", "<api-key>")
                .remove("Cookie"),
            modifyUris()
                .scheme("https")
                .host("api.example.test")
                .removePort()
        ),
        preprocessResponse(
            modifyHeaders().remove("Set-Cookie"),
            replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3"),
            maskLinks("[LINK]")
        )
    ));
~~~

The test uses `DOCS_ONLY_*` sentinels so a leak check can detect if a preprocessor is forgotten. If the request/response URI still contains an internal host, add `modifyUris()` to the corresponding operation direction.

## 11. Applying to WebTestClient and REST Assured

### 11.1. WebTestClient

~~~java
webTestClient.get()
    .uri("/api/orders/42")
    .header("Authorization", "Bearer DOCS_ONLY_ACCESS_TOKEN")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-get-webflux",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            modifyUris().scheme("https").host("api.example.test").removePort()
        ),
        preprocessResponse(
            modifyHeaders().remove("Set-Cookie"),
            replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3"),
            maskLinks("[LINK]")
        )
    ));
~~~

Use the WebTestClient REST Docs filter/configuration matching your version. Check the snippets generated by the exact filter running in the test.

### 11.2. REST Assured

~~~java
given(specification)
    .header("Authorization", "Bearer DOCS_ONLY_ACCESS_TOKEN")
    .filter(document("orders-get-restassured",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            modifyUris().scheme("https").host("api.example.test").removePort()
        ),
        preprocessResponse(
            modifyHeaders().remove("Set-Cookie"),
            replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3"),
            maskLinks("[LINK]")
        )
    ))
.when()
    .get("/api/orders/42")
.then()
    .statusCode(200);
~~~

Configure the REST Assured documentation filter according to your project's context. Do not take tokens from production environments or browser sessions as fixtures.

## 12. Verifying Generated Snippets with Sentinels

After running tests, scan the entire output directory and assembled docs. Sentinels should be unique, easy-to-find strings:

~~~text
DOCS_ONLY_ACCESS_TOKEN
DOCS_ONLY_API_KEY
DOCS_ONLY_SESSION
DOCS_ONLY_RESPONSE_TOKEN
DOCS_ONLY_TICKET
orders.internal.cluster.local
payments.internal.cluster.local
~~~

Assertion example:

~~~java
assertThat(allGeneratedDocumentation)
    .doesNotContain("DOCS_ONLY_ACCESS_TOKEN")
    .doesNotContain("DOCS_ONLY_API_KEY")
    .doesNotContain("DOCS_ONLY_SESSION")
    .doesNotContain("DOCS_ONLY_RESPONSE_TOKEN")
    .doesNotContain("DOCS_ONLY_TICKET")
    .doesNotContain("orders.internal.cluster.local")
    .doesNotContain("payments.internal.cluster.local");
~~~

If hosts were normalized, verify that the expected public host remains. If hypermedia `href` values were masked, verify that the `[LINK]` placeholder and link relation descriptors are still present.

Scan these output types:

- `http-request` and `http-response`.
- `curl-request` and `httpie-request`.
- `request-body` and `response-body`.
- Request/response headers and parameters.
- Custom snippets.
- Assembled Markdown/Asciidoctor.
- Rendered HTML and uploaded CI artifacts.

Do not inspect only a single request snippet file.

## 13. CI Gate for Redaction and Host Normalization

~~~mermaid
flowchart TD
    A["HTTP tests with synthetic secrets"] --> B["Apply header preprocessors"]
    B --> C["Apply body and URI preprocessors"]
    C --> D["Generate all snippets"]
    D --> E["Assemble and render docs"]
    E --> F["Scan secret sentinels and internal hosts"]
    F --> G{"Leak found?"}
    G -->|Yes| X["Fail build"]
    G -->|No| H["Validate snippets and links"]
    H --> I{"All checks pass?"}
    I -->|No| X
    I -->|Yes| J["Review artifact"]
    J --> K["Publish approved docs"]
~~~

CI needs to:

1. Run clean HTTP tests with synthetic values.
2. Generate snippets using the operation's preprocessors.
3. Assemble and render the documentation.
4. Scan for sentinel tokens, API keys, session IDs, and internal hostnames.
5. Verify expected public hosts/placeholders.
6. Fail the build if any sentinel remains in the output.
7. Avoid printing raw secrets into logs when reporting errors.
8. Upload/publish artifacts only after scans and reviews pass.

A secret scanner complements the sentinel check. Never allowlist real values just to make the pipeline pass.

## 14. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `Authorization` remains in snippet | Only used `replacePattern` on the body | Use `modifyHeaders` set/remove. |
| JSON token still remains | Only masked headers | Use `replacePattern` or `ContentModifier`. |
| Internal host remains in request | Only normalized the response | Preprocess both request and response directions properly. |
| Query token remains after `modifyUris` | `modifyUris` only changes scheme/host/port | Synthetic query value or custom URI preprocessor. |
| Hypermedia `href` still has signature | Did not use `maskLinks` or fake response fixture | Mask `href` or replace with a safe fixture. |
| Malformed JSON | Regex does not handle escaping/nesting | Use a JSON-aware `ContentModifier`. |
| Contract header disappears | Removed a header that should be documented | Set a placeholder instead of removing. |
| Public hostname also gets masked | Applied `maskLinks` too broadly | Choose `modifyUris` if link structure should be kept. |
| Only HTTP snippet is clean, curl still has token | Scanned only one file | Scan the entire operation output. |
| Passes locally, fails in CI | CI fixture/host differs from local | Use synthetic fixtures and identical build configuration. |
| Build uses stale snippets | Wrong task dependency/output configuration | Clean output and run tests before rendering. |

## 15. Capstone Exercise

Complete documentation for two operations:

- `GET /api/orders/42`: requires a Bearer token, optional API key, session cookie may appear; response contains HAL links.
- `POST /api/orders`: request body contains `customerEmail` and `clientReference`; response contains a temporary `accessToken` for a business flow.

Tasks:

1. Write HTTP tests using MockMvc, WebTestClient, or REST Assured.
2. Use distinct sentinels for `Authorization`, API key, `Cookie`, body tokens, and internal hosts.
3. Use `modifyHeaders()` to replace/remove request and response headers.
4. Use `replacePattern()` or `ContentModifier` to mask tokens/PII in the body.
5. Use `modifyUris()` to normalize URI scheme, host, and port.
6. Use `maskLinks()` for hypermedia `href` values that need masking; keep link relations.
7. Use synthetic values for query parameters; if needed, write a custom request URI preprocessor.
8. Generate all snippets and assemble Markdown/Asciidoctor.
9. Scan generated snippets, final docs, and rendered HTML.
10. Intentionally remove each preprocessor one by one to verify the sentinel check catches leaks.
11. Run a clean CI build and publish only when all gates pass.

**Completion criteria:** documentation retains required method/path, headers, and body contract; tokens/cookies/API keys are replaced or removed in the right regions; internal hosts are normalized; hypermedia `href` values are masked within the right scope; query secrets do not leak; all generated output is scanned and CI blocks publishing if a leak is detected.

## References

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url)
