# Modifying Headers and Masking Sensitive Data

## 1. Why Process Headers and Sensitive Data?

In the **SPRING_REST_DOCS** module, HTTP tests with MockMvc, WebTestClient, or REST Assured generate snippets from requests/responses. Snippets typically include the request line, headers, and body. This content sometimes contains metadata meant only for operations or values that must not be published:

- Internal headers like `X-Internal-Node`, `X-Debug-Trace`.
- Environment-varying headers like `Date` or `Server`.
- Credentials in `Authorization`, `Cookie`, or session headers.
- API keys, access tokens, refresh tokens, or signatures.
- Personal data or unnecessary information in JSON bodies.

Spring REST Docs provides operation preprocessors to edit the recorded request/response before writing snippets. Two common groups of operations are **modifying headers** and **masking values in the body**.

It is important to understand the boundary: an operation preprocessor acts on the REST Docs record used to generate documentation. It does not remove headers from the sent HTTP request, does not alter the response received by clients, and is not a runtime security measure. If the real API is sending secrets that violate the contract, fix the API or security configuration.

## 2. Operation Preprocessors and Where They Apply

A preprocessor receives the captured operation request/response, edits the record, and returns the result for the snippet generation step.

| API | Role |
| --- | --- |
| `OperationPreprocessor` | Contract for processing an operation request or response |
| `preprocessRequest(...)` | Attaches preprocessors to an operation's request |
| `preprocessResponse(...)` | Attaches preprocessors to an operation's response |
| `modifyHeaders()` | Creates a processor that modifies the header collection |
| `replacePattern(...)` | Replaces text matching a regular expression |
| Custom preprocessor | Implements structural or domain-specific masking rules |

Importing the helpers:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.preprocessRequest;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
```

The request/response helpers in the example belong to the MockMvc integration. With WebTestClient and REST Assured, where preprocessors attach follows their respective integration APIs, though the operation processing principle remains the same.

An operation may process only the request, only the response, or both. Only apply processors on the side containing data that needs adjustment.

## 3. Adding, Replacing, and Removing Headers with modifyHeaders()

`modifyHeaders()` creates a processor to modify the header collection of the recorded request/response. You can add headers, set values, or remove headers.

### 3.1. Replacing Header Values

When you want to keep the header name in documentation without publishing the real value, use a placeholder:

```java
.andDo(document("accounts-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer [REDACTED]")
    )
))
```

Snippets still show that the request carries `Authorization`, while the actual bearer token does not appear. This is appropriate when documentation needs to explain that clients must send credentials.

### 3.2. Removing Headers That Should Not Be Public

Some headers only serve internal infrastructure:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .remove("Date")
            .remove("X-Internal-Node")
            .remove("X-Debug-Trace")
    )
))
```

Those headers no longer appear in response snippets. Only remove headers outside the contract or unhelpful to readers. Do not remove `Content-Type`, `Location`, `ETag`, or `Cache-Control` if clients need to understand API behavior.

### 3.3. Adding Representative Headers

You can normalize a header in the documentation record:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-API-Version", "v1")
            .remove("X-Internal-Node")
    )
))
```

Only add representative values if they reflect the contract. Never invent fake headers that clients do not actually send or receive in the real API.

## 4. Choosing remove vs. set When Handling Sensitive Headers

Suppose the captured request has:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret.signature
X-Request-Id: 1b2c3d4e-5f6a-7b8c
Content-Type: application/json
```

There are two options:

**Remove the header:**

```java
preprocessRequest(
    modifyHeaders().remove("Authorization")
)
```

Use this when you do not want the header to appear in documentation, or when the header only serves internal infrastructure. However, clients reading the documentation may not realize the operation requires authentication.

**Replace the value:**

```java
preprocessRequest(
    modifyHeaders()
        .set("Authorization", "Bearer <access-token>")
        .set("X-Request-Id", "<request-id>")
)
```

This keeps the header structure to document the contract. For public APIs, you should usually mask the value while keeping the header name if it is meaningful to clients.

If `requestHeaders(...)` documents a header, removing that header in a preprocessor can prevent snippets from reflecting the information you need to document. When you want to document a header's presence, keep the name and replace the value.

## 5. Masking Body Values with replacePattern()

Bodies can also contain tokens or data that should not be published:

```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiJ9.real-secret",
  "tokenType": "Bearer",
  "expiresIn": 3600,
  "profile": {
    "email": "lan@example.test"
  }
}
```

`replacePattern(Pattern, String)` replaces text matching a regex in the operation content:

```java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

.andDo(document("auth-token-create",
    preprocessResponse(
        replacePattern(
            Pattern.compile(
                "\"accessToken\"\\s*:\\s*\"[^\"]+\""),
            "\"accessToken\":\"[REDACTED]\"")
    )
))
```

Response snippet after processing:

```json
{
  "accessToken": "[REDACTED]",
  "tokenType": "Bearer",
  "expiresIn": 3600,
  "profile": {
    "email": "lan@example.test"
  }
}
```

The regex specifically targets the `accessToken` property with a JSON string value. Because this is a text replacement, the pattern must match actual whitespace, escaping, and serialization. Avoid overly broad regexes that can corrupt non-sensitive data or JSON structure.

`replacePattern` only masks the documentation record. If the real API returns a token, clients still receive that token over HTTP. Use dummy fixtures; never pull production tokens as test data expecting a preprocessor to always mask them cleanly.

## 6. Masking Multiple Fields While Preserving JSON Shape

Multiple patterns can be combined:

```java
.andDo(document("auth-token-create",
    preprocessResponse(
        replacePattern(
            Pattern.compile(
                "\"accessToken\"\\s*:\\s*\"[^\"]+\""),
            "\"accessToken\":\"[REDACTED]\""),
        replacePattern(
            Pattern.compile(
                "\"refreshToken\"\\s*:\\s*\"[^\"]+\""),
            "\"refreshToken\":\"[REDACTED]\""),
        replacePattern(
            Pattern.compile(
                "\"email\"\\s*:\\s*\"[^\"]+\""),
            "\"email\":\"user@example.test\"")
    )
))
```

Scope each pattern to the field name and value to replace. Do not replace every email if email is example data that the contract wants to keep; a stable dummy fixture can be clearer than masking.

Keeping keys with placeholders generally helps snippets still show the response shape:

```json
{
  "accessToken": "[REDACTED]",
  "refreshToken": "[REDACTED]",
  "expiresIn": 3600
}
```

If a sensitive field does not belong to the public contract, decide whether to drop it from documentation altogether. Masking only changes the value in snippets; it does not make the field vanish from the real response.

## 7. When Regex Is Not Enough: JSON-Aware Custom Preprocessor

Regex works for simple fields, stable names, and consistent JSON serialization. With nested objects, arrays, or varied data types, consider a custom `OperationResponsePreprocessor`:

1. Read the operation body and `Content-Type`.
2. Parse only when the media type is an appropriate JSON type.
3. Parse the body into a JSON tree.
4. Replace values at sensitive paths with placeholders.
5. Serialize JSON back.
6. Return the edited operation to REST Docs.

This approach depends less on whitespace and escaping than regex. However, a custom processor must handle charsets, empty bodies, non-JSON content types, parse failures, and serialization options. Never parse every body as JSON blindly.

Pseudo-code illustrating the idea:

```java
OperationResponsePreprocessor maskSensitiveJsonFields =
        operation -> {
            // Check that Content-Type is application/json.
            // Parse operation.getContent() into JsonNode.
            // Replace accessToken/refreshToken with "[REDACTED]".
            // Re-serialize and return operation with replaced content.
            return operation;
        };
```

This is not directly compilable code. A real implementation must use the operation builder/API of your Spring REST Docs version and include unit tests for nested JSON, arrays, nulls, empty bodies, and malformed JSON.

## 8. Combining Header Modification and Body Masking

An operation may need to process both request and response:

```java
.andDo(document("accounts-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer [REDACTED]")
            .set("X-Request-Id", "<request-id>")
    ),
    preprocessResponse(
        modifyHeaders()
            .remove("X-Internal-Node")
            .remove("X-Debug-Trace"),
        replacePattern(
            Pattern.compile(
                "\"email\"\\s*:\\s*\"[^\"]+\""),
            "\"email\":\"user@example.test\"")
    )
))
```

In this example:

- Request snippet keeps `Authorization` but replaces the token with a placeholder.
- Request ID is normalized so generated diffs remain stable.
- Response snippet drops internal headers.
- Email in the response is replaced with an example address.

If the response body echoes the `Authorization` header, you need to apply a corresponding response preprocessor. Processing the request does not automatically mask the same value in the response.

## 9. Preprocessor Order and Related Snippets

Processor order matters if a later processor reads content changed by an earlier processor. For example, if one step changes `Content-Type`, a downstream formatter or parser may interpret the body differently. If a regex runs before a formatter, the pattern must match the initial body; if the formatter runs first, the pattern must match the formatted representation.

Practical guidelines:

- Normalize unstable data before generating snippets.
- Mask secrets before writing snippets containing that body/header.
- Keep contract headers that need documenting; only remove metadata that should not be public.
- Inspect all snippets for the operation, not just `http-response`.
- Check whether request/response fields, cURL requests, and custom snippets draw data from the same operation.

Preprocessors typically modify the shared operation record that snippets read from. Do not assume a processor only affects a single snippet file.

## 10. MockMvc Example: Masking Authorization and Response Tokens

Example using JUnit Jupiter, MockMvc, and Spring REST Docs. The controller returns a simulated token; the test generates snippets containing placeholders.

```java
import java.util.Map;
import java.util.regex.Pattern;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.preprocessRequest;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class SensitiveDataDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new TokenController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentTokenResponseWithoutRealSecret() throws Exception {
        mockMvc.perform(get("/api/token")
                        .header("Authorization", "Bearer test-secret-value")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andDo(document("token-get",
                        preprocessRequest(
                                modifyHeaders()
                                        .set("Authorization", "Bearer [REDACTED]")
                        ),
                        preprocessResponse(
                                replacePattern(
                                        Pattern.compile(
                                            "\"accessToken\"\\s*:\\s*\"[^\"]+\""),
                                        "\"accessToken\":\"[REDACTED]\"")
                        )
                ));
    }

    @RestController
    static class TokenController {
        @GetMapping(value = "/api/token",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> token() {
            return Map.of(
                    "accessToken", "server-generated-test-secret",
                    "tokenType", "Bearer",
                    "expiresIn", 3600
            );
        }
    }
}
```

In a real project:

- Do not pull production tokens from the environment into tests.
- Do not log unmasked bodies/headers in assertion failures or custom reporters.
- Inspect snippets after running and confirm no original values remain.
- If using `requestHeaders` to document `Authorization`, use a general description like "Bearer access token".
- Add tests for regexes with varying whitespace and escaping.

## 11. Masking in Documentation Does Not Replace API Security

Distinguish these scenarios:

| Scenario | Handling in REST Docs | Handling in API/Runtime |
| --- | --- | --- |
| Token clients must send | Replace value in snippet, keep header and document format | Validate real tokens per contract |
| Demo email/phone | Use dummy fixture or mask in snippet | Enforce access control and data policies |
| Password hash/internal secret must not be returned | Do not include values in snippets | Exclude from DTO/serializer and test for no leaks |
| Internal trace ID | Remove header or replace value in snippet | Evaluate whether the header should be sent externally |
| Real cookie/session | Replace or remove from recorded request | Manage cookies/sessions securely |

If a secret must never appear in HTTP responses, tests must verify it is absent from the real response:

```java
mockMvc.perform(get("/api/profile"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.passwordHash").doesNotExist())
    .andExpect(jsonPath("$.accessToken").doesNotExist());
```

If the requirement is for the key to be completely absent, distinguish that from a key with a `null` value. You can parse the response into a JSON tree and check `has(...)`.

Secrets can also leak in fixtures, test reports, failure logs, HTTP client logging, or other CI artifacts. Use dummy data and control logging from the outset.

## 12. Testing Data Masking

Masking should be verified as part of the documentation test suite:

- Verify snippets do not contain the fixture's secret marker.
- Verify placeholders preserve keys that need documenting.
- Verify contract headers still appear if required by descriptors.
- Verify internal headers have been removed per policy.
- Verify regexes do not accidentally replace non-sensitive fields.
- Test JSON with whitespace, escaped quotes, nested objects, and arrays.
- Verify non-JSON bodies are not misparsed by a custom JSON masker.
- Verify Asciidoctor includes the freshly generated snippets.

Place an easily recognizable dummy marker in fixtures to search for in output. Never use real secrets even with preprocessors configured; a single misconfiguration must never write real credentials into artifacts.

## 13. Asciidoctor and CI Integration

Asciidoctor includes snippets by identifier:

```adoc
= Token API
:snippets: build/generated-snippets

== Retrieve Token

=== HTTP request
include::{snippets}/token-get/http-request.adoc[]

=== HTTP response
include::{snippets}/token-get/http-response.adoc[]
```

The build should run documentation tests before Asciidoctor so snippets are generated from current tests. You can add an artifact check step to scan for original secret markers. This check should inspect both generated snippets and rendered documentation, as custom templates may emit output differently from default snippets.

CI should fail if secret markers still appear, contract headers are accidentally deleted, snippets are stale, regexes alter the wrong fields, or API leak-prevention tests fail.

Do not use post-publish secret-scrubbing scripts as the primary solution. Mask directly in operation preprocessing before writing snippets and keep verification tests in place.

## 14. Common Errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| `Authorization` disappears from snippet | Used `remove` when header needed documenting | Use `set` with a placeholder |
| Token remains in response snippet | Only masked request or wrong regex | Apply response preprocessor and test output |
| Broken JSON body | Regex too broad or invalid replacement | Narrow pattern; consider JSON-aware processor |
| Valid email replaced by mistake | Pattern too broad | Use dummy fixture or specific pattern/path |
| Contract header missing | Removed header required by descriptor | Replace value instead of removing |
| Internal header still appears | Processed wrong side (request/response) | Choose the right operation preprocessor |
| API still returns password hash | Confused snippet masking with security | Fix DTO/serialization and test real response |
| Unstable snippet diffs | Request ID, `Date`, or token changes each run | Normalize values in recorded operation |
| Secret appears in test report | Failure/logger printed raw exchange | Use dummy fixtures and restrict HTTP logging |
| Subsequent preprocessor does not match | Order changed representation | Inspect data after each step |

## 15. Practice Exercise

Use a token retrieval endpoint and a profile retrieval endpoint:

1. Create a request with a simulated `Authorization`. Use `modifyHeaders().set(...)` to replace the value in snippets while keeping the header.
2. Add `X-Internal-Node` to the response. Use `remove(...)` if the header does not belong to the public contract.
3. Try `set(...)` with a placeholder and compare when documentation needs to show the header exists.
4. Return JSON with `accessToken` and `refreshToken`; use `replacePattern(...)` to replace them with `[REDACTED]`.
5. Create fixtures with varied whitespace/escaping; verify regex masks cleanly without breaking JSON.
6. Add an email; decide whether to use dummy data or mask it in snippets.
7. Create a response with `passwordHash`. Write assertions confirming the API does not send that field.
8. Combine header modification and body masking in the same operation; inspect both request and response.
9. Generate snippets and search for secret markers across all `generated-snippets`; fail the build if markers remain.
10. Include masked snippets in Asciidoctor and review the final artifact.

**Completion criteria:** you know how to use `modifyHeaders()` to add/set/remove headers on the REST Docs record; mask bodies with `replacePattern(...)` or custom operation preprocessors; distinguish `remove` from placeholders; understand preprocessors do not secure HTTP runtime; and write tests preventing real secrets from leaking into generated snippets/CI artifacts.

## References

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessing.html): operation preprocessors, editing requests/responses before snippet generation.
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): `modifyHeaders`, `replacePattern`, and preprocessing helpers.
- [Spring REST Docs — OperationPreprocessor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/OperationPreprocessor.html): contract for processing operations before generating documentation.
