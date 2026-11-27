# Masking Links with Sensitive Parameters

## 1. Objectives and Context

REST APIs may return hypermedia links or callback URLs containing query parameters. Some values are public data such as page, size, and sort; others may be authorization codes, signed URLs, reset tokens, invitation tokens, session references, or personal data. If Spring REST Docs writes the raw response into a snippet, sensitive values can appear in committed or published documentation.

Spring REST Docs provides the **maskLinks** preprocessor to mask the href of hypermedia links in request/response content. It is important to distinguish this from masking every query parameter in the request URI. **replacePattern** replaces request/response content; **modifyUris** modifies the scheme, host, and port. When you need to hide query parameters in a request URI, use synthetic test data or a custom request preprocessor.

This lesson belongs to the **Security** chapter of the **SPRING_REST_DOCS** module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generates snippets for requests, responses, payloads, parameters, and headers; compiles Asciidoctor/Markdown; and integrates with build/CI pipelines.

After this lesson, you will be able to identify sensitive query parameters; use maskLinks for hypermedia hrefs; distinguish maskLinks, replacePattern, and modifyUris; choose synthetic values; write a custom OperationRequestPreprocessor when needed; inspect all snippets; and add leak checks to CI.

## 2. Locations to Review

Example hypermedia response:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    },
    "payment": {
      "href": "https://pay.example.test/checkout?order=42&state=opaque-state"
    }
  }
}
~~~

Common categories:

| Location | Example | Handling Approach |
| --- | --- | --- |
| Hypermedia href | _links.payment.href | maskLinks or custom content transform. |
| Request query | access_token=... | Synthetic value or custom request preprocessor. |
| Callback URL | code=...&state=... | Synthetic authorization code, mask if needed. |
| Signed URL | X-Amz-Signature=... | Do not publish an active URL. |
| Reset/invitation link | token=... | Do not publish a usable token. |
| Pagination | page=0&size=20 | Usually kept to describe the contract. |
| Filter/sort | status=PAID&sort=createdAt | Keep if it contains no PII/secrets. |

Not every query parameter is sensitive. Over-masking reduces the usefulness of examples; under-masking can publish usable credentials.

## 3. maskLinks: Masking the href of Hypermedia Links

Spring REST Docs provides Preprocessors.maskLinks() and an overload accepting a replacement string. The preprocessor locates hypermedia links in request/response content and replaces the href with the masked value.

Response before masking:

~~~json
{
  "_links": {
    "self": {
      "href": "https://internal.example.test/orders/42"
    },
    "cancel": {
      "href": "https://internal.example.test/orders/42/cancel?ticket=private-value"
    }
  }
}
~~~

Apply to the response:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.maskLinks;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

.andDo(document("orders-get",
    preprocessResponse(maskLinks())
));
~~~

Using a custom placeholder:

~~~java
.andDo(document("orders-get",
    preprocessResponse(maskLinks("[LINK]"))
));
~~~

Link relations can still be documented using link descriptors:

~~~java
.andDo(document("orders-get",
    links(
        linkWithRel("self").description("Current order"),
        linkWithRel("cancel").description("Order cancellation link if permitted")
    ),
    preprocessResponse(maskLinks())
));
~~~

The links snippet configuration and response preprocessing must use the exact static imports for your project. The goal is to preserve the meaning of the rel without exposing hrefs containing tokens or internal hosts.

## 4. maskLinks Does Not Mask Every URL

maskLinks processes the href of recognized hypermedia links in request/response content. It is not a general-purpose filter for every query string in the request URI, every URL in text or logs, or custom JSON fields not recognized as hypermedia links.

Example request line:

~~~http
GET /oauth/callback?code=authorization-code-secret&state=opaque-state HTTP/1.1
~~~

This is the operation's request URI, not an href in a HAL response. Attaching maskLinks only to the response will not mask this query string.

Similarly, a plain string JSON field such as redirectUrl may not be treated as a hypermedia link. If the field contains a signed URL, you must use a synthetic fixture or process the content appropriately.

## 5. Distinguishing the Preprocessors

| Preprocessor | Primary Scope | What Not to Assume |
| --- | --- | --- |
| maskLinks() | Hrefs of hypermedia links in content | Does not mask every query string in the request URI. |
| replacePattern(pattern, replacement) | Replaces patterns in request/response content | Does not modify the URI object by default. |
| modifyUris() | Changes scheme, host, and port | Does not remove query parameters or path segments. |
| modifyHeaders() | Adds, sets, or removes headers | Does not mask URLs in the request line or body. |
| Custom OperationPreprocessor | Custom logic on the request/response operation | Must test output and preserve the contract. |

modifyUris is useful when tests run on localhost/random port while docs require a canonical host. This API focuses on scheme, host, and port; do not use it to mask query parameters.

replacePattern is useful for body text, such as redirectUrl in JSON, but the API defines it as a content replacement mechanism. When you need to modify the request URI stored separately on the operation, use synthetic query values or a custom request preprocessor.

## 6. Preferring Synthetic Query Values

The simplest and safest approach is for documentation tests to use non-functional synthetic values:

~~~java
mockMvc.perform(get("/oauth/callback")
        .queryParam("code", "DOCS_AUTH_CODE")
        .queryParam("state", "DOCS_STATE"))
    .andExpect(status().isOk())
    .andDo(document("oauth-callback"));
~~~

Use this approach only if the endpoint accepts test fixtures and does not call a real authentication system. DOCS_AUTH_CODE must be generated specifically for tests, not taken from an OAuth provider.

For signed URLs, do not use real signatures to generate snippets. Mock the service to return a synthetic URL or an expired fixture. The documentation still demonstrates the query parameter names and URL shape without providing reusable credentials.

If a query parameter is part of the contract, keep its name and describe its meaning, replacing only the value:

~~~text
?page=0&size=20&status=PAID&access_token=[REDACTED]
~~~

Keep pagination and filters so the documentation remains useful. For state, verify its semantics: it may be a secret/correlation value or a public business state.

## 7. Custom Request Preprocessor for Query URIs

If a URI is constructed with dynamic values that cannot be replaced in test fixtures, you can write an OperationRequestPreprocessor to produce a sanitized documentation request.

Steps:

1. Receive the OperationRequest before REST Docs renders snippets.
2. Read the URI and parse query parameters.
3. Preserve public keys according to an allowlist.
4. Replace values of sensitive keys such as code, token, state, and signature.
5. Build a new OperationRequest with the processed URI, preserving method, headers, body, and request parts.
6. Return the new request to the documentation step.

Illustrative pseudocode, not a copy-paste implementation:

~~~java
OperationRequestPreprocessor redactQueryParameters =
    request -> {
        URI original = request.getUri();
        URI sanitized = redactSensitiveQueryValues(original);

        // Create a new OperationRequest using the API/factory for your version.
        // Preserve method, headers, content, multipart parts, and cookies.
        return createSanitizedRequest(request, sanitized);
    };
~~~

redactSensitiveQueryValues and createSanitizedRequest are helpers implemented by the application. None of the built-in preprocessors described above guarantees arbitrary removal of query parameters from the request URI.

In a real implementation, check the OperationRequest and OperationRequestFactory APIs for your exact Spring REST Docs version. Preserve percent-encoding, duplicate query keys, valueless parameters, ordering if needed, and URI fragments. Avoid concatenating query strings with naive string replacement because it can break encoding.

### 7.1. Masking Only Sensitive Keys

Example input:

~~~text
?page=0&size=20&status=PAID&access_token=secret
~~~

Expected result:

~~~text
?page=0&size=20&status=PAID&access_token=[REDACTED]
~~~

Keep pagination and filters. For state, verify its semantics before masking.

## 8. URLs in Response Bodies

A response may contain a URL in a regular field:

~~~json
{
  "redirectUrl": "https://pay.example.test/checkout?session=private-session&order=42",
  "expiresIn": 300
}
~~~

If the URL is a JSON string rather than a hypermedia href, maskLinks might not recognize it. You can use a synthetic fixture, replacePattern on the response content, or a custom JSON-aware content modifier.

~~~java
Pattern sensitiveSession =
    Pattern.compile("session=[^&\"\\s]+");

.andDo(document("payment-session",
    preprocessResponse(
        replacePattern(sensitiveSession, "session=[REDACTED]")
    )
));
~~~

The illustrative pattern can replace the session query value in a JSON string or text response. You must test escaping and URL encoding. For complex JSON, parsing JSON and replacing the exact property is usually clearer than a generic regex.

## 9. Normalizing Host and Path in Test Environments

modifyUris can normalize the scheme, host, and port:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    )
));
~~~

This preprocessor does not remove query parameters and does not replace path segments. If the path contains a reset token or sensitive customer identifier, use a synthetic fixture or a custom request preprocessor.

## 10. Applying to Each HTTP Test Client

### 10.1. MockMvc

~~~java
mockMvc.perform(get("/oauth/callback")
        .queryParam("code", "DOCS_AUTH_CODE")
        .queryParam("state", "DOCS_STATE"))
    .andExpect(status().isOk())
    .andDo(document("oauth-callback",
        preprocessResponse(maskLinks("[LINK]"))
    ));
~~~

Response hypermedia hrefs are masked; request query values are safe because synthetic fixtures are used. If a test uses real query values, the URI must be processed separately.

### 10.2. WebTestClient

~~~java
webTestClient.get()
    .uri(uriBuilder -> uriBuilder
        .path("/oauth/callback")
        .queryParam("code", "DOCS_AUTH_CODE")
        .queryParam("state", "DOCS_STATE")
        .build())
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("oauth-callback-webflux",
        preprocessResponse(maskLinks())
    ));
~~~

Use non-functional test values. If the response contains signed hypermedia hrefs, mask them before writing the snippet or use a response fixture without a real signature.

### 10.3. REST Assured

~~~java
given(specification)
    .queryParam("code", "DOCS_AUTH_CODE")
    .queryParam("state", "DOCS_STATE")
    .filter(document("oauth-callback-restassured",
        preprocessResponse(maskLinks())
    ))
.when()
    .get("/oauth/callback")
.then()
    .statusCode(200);
~~~

The specification needs to configure the server/base URI, port, and REST Docs context. Do not take a callback URL or authorization code from an active OAuth flow as a sample.

## 11. Testing Masking Results

Use a dedicated sentinel to verify that no sensitive values appear in generated snippets:

~~~java
private static final String SECRET_QUERY_VALUE =
    "DOCS_ONLY_QUERY_SECRET_4c91";
~~~

After tests generate the snippets, scan the entire output directory and assembled pages:

~~~java
assertThat(allGeneratedDocumentation)
    .doesNotContain(SECRET_QUERY_VALUE)
    .doesNotContain("session=private-session");
~~~

Check http-request, curl-request, httpie-request, query parameter snippets, custom request snippets, assembled Markdown/Asciidoctor, and rendered HTML.

For hypermedia responses, verify that the href is masked and relation descriptors remain intact. For query URIs, verify that public keys remain intact and secret values have been replaced.

## 12. CI: Blocking Query/Link Secrets Before Publishing

~~~mermaid
flowchart TD
    A["HTTP tests with synthetic URL values"] --> B["Apply maskLinks / custom preprocessor"]
    B --> C["Generate all snippets"]
    C --> D["Assemble API documentation"]
    D --> E["Scan sentinels and signed URL patterns"]
    E --> F{"Sensitive value found?"}
    F -->|Yes| X["Fail CI"]
    F -->|No| G["Render docs and validate links"]
    G --> H{"Render checks pass?"}
    H -->|No| X
    H -->|Yes| I["Publish"]
~~~

CI should:
1. Use synthetic query values and URL fixtures.
2. Attach maskLinks for hypermedia links that need masking.
3. Use a custom request preprocessor if queries in the request URI need replacement.
4. Scan generated snippets and assembled docs with sentinels.
5. Check curl/HTTPie, body snippets, and rendered HTML.
6. Fail the build if a real signed URL/token appears.
7. Never print raw secrets in logs.
8. Publish only after scans and rendering pass.

If a URL with a real signature has already been committed or published, revoke the credential or regenerate the signed URL according to policy. Deleting files from the workspace does not revoke signatures or erase CI artifacts and Git history.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Hypermedia href still exposed | maskLinks not attached to the response operation | Check the response preprocessor and output. |
| Query token remains in request line | maskLinks does not process general request URIs | Use synthetic values or a custom request preprocessor. |
| replacePattern does not change URI | It modifies content, not the URI object in general | Process the request URI separately. |
| modifyUris does not mask query | It changes scheme/host/port | Mask queries by key using an appropriate approach. |
| redirectUrl in JSON still exposed | Plain string field is not a hypermedia link | Use a synthetic fixture, body replacement, or JSON modifier. |
| Public parameters disappear | Masked the entire query string | Replace only the values of sensitive keys. |
| URL broken after regex | Percent-encoding/duplicate keys not preserved | Parse the URI/query properly. |
| Request snippet clean but curl leaks | Checked only one file | Scan all operation output. |
| Clean locally, CI has secret | CI fixtures/credentials differ | Use synthetic data and identical preprocessing. |
| Link relation loses meaning | Masked the entire link object | Mask only href, keeping rel and description. |

## 14. Practice Exercise

Create a hypothetical API:

- GET /api/orders returns _links.self, _links.next, and _links.payment.
- GET /oauth/callback accepts code and state.
- The payment response contains a redirectUrl with a session query parameter.

Steps to perform:

1. Write HTTP tests with synthetic URL/query values.
2. Apply maskLinks to hypermedia responses.
3. Verify that link descriptors still describe rels even though hrefs are masked.
4. Verify that request queries use synthetic values.
5. If a dynamic request URI must be replaced, implement a custom OperationRequestPreprocessor matching your project's API version.
6. Mask session in redirectUrl using a fixture, body replacement, or JSON-aware modifier.
7. Inspect HTTP, curl, HTTPie, query parameter snippets, and response bodies.
8. Scan assembled docs and rendered HTML with sentinels.
9. Run a clean CI build and fail if a secret is detected.
10. Document clearly which parameters are public and which are replaced with placeholders.

**Completion criteria:** distinguish hypermedia hrefs from request query URIs; use maskLinks within its proper scope; do not mistake replacePattern/modifyUris for a general query filter; preserve public parameters; mask signed URLs/tokens; and have a CI leak check before publishing.

## References

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring REST Docs — OperationRequestPreprocessor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/OperationRequestPreprocessor.html)
- [OWASP — Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
