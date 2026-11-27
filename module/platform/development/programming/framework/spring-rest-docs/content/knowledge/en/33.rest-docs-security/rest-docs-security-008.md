# Hiding User Identifiers and Environment Information

## 1. Why Hide Data in Snippets?

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Security** chapter, API documentation is generated from actual requests and responses of HTTP tests. Test data sometimes contains user IDs, emails, phone numbers, IP addresses, internal hostnames, database names, dummy tokens, or development environment URLs. If snippets are published, these values can expose internal structure or create the habit of putting personal data into documentation.

Spring REST Docs provides operation preprocessors to transform requests/responses before writing snippets. You can replace identifiers with stable placeholders, remove internal headers, or normalize URIs to a sample host. As a result, examples remain understandable and verifiable without carrying real environment information.

Crucially, a preprocessor transforms only Spring REST Docs' documentation record. It does not encrypt data, does not alter the request sent to the controller, and does not protect application logs, APM, databases, or runtime traffic. Sensitive data must still be handled safely at other layers.

After this lesson, you will be able to:

- Identify user identifiers and environment traces in requests/responses.
- Use replacePattern to replace sensitive data with placeholders.
- Use removeHeaders/modifyHeaders to remove or normalize headers.
- Use modifyUris to normalize scheme, host, and port.
- Apply operation-specific preprocessors.
- Verify that snippets are masked and contain no original values.

Examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, and MockMvc**.

## 2. Classifying Data to Hide

Before writing preprocessors, identify which data represents personal identifiers, secrets, or environment information.

| Category | Example | Handling in Snippets |
| --- | --- | --- |
| User identifier | userId, customerId, account number | Replace with a placeholder such as USER_ID |
| Contact information | email, phone, address | Use dummy data not belonging to real people or replace with a placeholder |
| Session identifier | session ID, correlation ID | Replace with a stable sample value or remove if unnecessary |
| Credential | Authorization, Cookie, API key | Remove header or replace with an unmistakably dummy token |
| Internal environment | hostname, private IP, port, internal DNS | Normalize URI or replace with a sample host |
| Infrastructure | cluster, pod, database, schema name | Exclude from snippets if not part of the public contract |
| Sensitive business data | balances, transactions, customer records | Use synthetic fixtures, never copy production data |

Not every ID is a secret. However, real IDs can link to personal data or reveal scale, creation order, and system structure. Using stable dummy IDs in fixtures is usually the best choice; preprocessors act as an additional layer of defense for snippets.

## 3. Where Do Preprocessors Operate?

Spring REST Docs allows configuring preprocessors directly on an operation:

```java
document("users-find",
    preprocessRequest(...),
    preprocessResponse(...),
    ...
)
```

The request preprocessor transforms the copy of the request written into snippets; the response preprocessor transforms the copy of the response written into snippets. The controller still receives the actual request and the test client still receives the actual response.

General flow:

```text
MockMvc request
     |
     v
Application / Controller
     |
     v
HTTP response
     |
     +----> Test assertions use actual data
     |
     v
Spring REST Docs operation
     |
     +----> preprocessRequest  -> request snippets
     |
     +----> preprocessResponse -> response snippets
                                  |
                                  v
                           Generated snippets
```

Because assertions typically run against the original response before the document handler writes snippets, tests can verify real behavior while publishing masked copies. However, you should also add direct assertions on generated artifacts/snippets after the build to prove sensitive values were stripped.

## 4. Replacing User IDs with replacePattern

### 4.1. Masking Identifiers in Payloads

Suppose a response contains:

```json
{
  "userId": "usr-849201",
  "email": "alice.private@example.test",
  "displayName": "Alice",
  "status": "ACTIVE"
}
```

Create a response preprocessor:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

preprocessResponse(
    replacePattern(
        Pattern.compile("usr-[0-9]+"),
        "USER_ID"
    ),
    replacePattern(
        Pattern.compile("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{2,}"),
        "user@example.test"
    )
)
```

The response body snippet will contain placeholders instead of the fixture's user ID and email:

```json
{
  "userId": "USER_ID",
  "email": "user@example.test",
  "displayName": "Alice",
  "status": "ACTIVE"
}
```

Regular expressions must match the actual data format. Avoid overly broad regexes that accidentally replace valid content, or overly narrow ones that let identifier variants slip through. For complex data, consider using synthetic fixtures from the start with preprocessors serving only as an additional safeguard.

### 4.2. Masking Identifiers in Both Request and Response

If a user ID appears in both the request URL and the response payload, you can apply masking to both sides:

```java
document("users-find",
    preprocessRequest(
        replacePattern(
            Pattern.compile("usr-[0-9]+"),
            "USER_ID"
        )
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile("usr-[0-9]+"),
            "USER_ID"
        )
    )
)
```

Inspect the request line and response body snippets after the build to confirm the pattern actually covers all occurrences. If the identifier sits in a URI handled separately by a URI modifier, use the appropriate modifier and do not assume a single body regex will normalize all URL components.

## 5. Hiding Sensitive Headers and Environment Information

### 5.1. Removing Headers Outside the Public Contract

Headers such as Authorization, Cookie, Set-Cookie, or internal debug headers generally do not need to appear in public documentation:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

preprocessRequest(
    removeHeaders("Authorization", "Cookie", "X-Internal-Debug")
),
preprocessResponse(
    removeHeaders("Set-Cookie", "X-Internal-Node", "Server")
)
```

Remove headers from snippets only when they are not part of the contract that integrators need to know. If the API requires clients to send Authorization, the documentation should still explain the authentication mechanism in a dedicated security section; there is no need to put a real token in examples.

### 5.2. Replacing Header Values with Placeholders

If a header must be documented while its actual value may contain environment details, use modifyHeaders:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;

preprocessResponse(
    modifyHeaders()
        .set("X-Request-Id", "REQUEST_ID")
        .set("X-Region", "example-region")
)
```

The example above keeps the header name and replaces the value. Use this approach when the header belongs to the public contract but test values should not be published.

### 5.3. Normalizing URI Host and Port

Request/response snippets may contain an environment host:

```text
https://catalog-staging.internal.example:8443/api/products/42
```

Use modifyUris to normalize the scheme, host, and port:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;

preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.test")
        .removePort()
)
```

The URI in the snippet becomes a sample host suitable for public documentation. Replace the host only if it is an illustrative URI; if the API contract requires a tenant- or client-configured host, explain the base URL separately rather than distorting endpoint semantics.

## 6. Organizing a Shared Preprocessor Suite

You can create a helper in test sources:

```java
package com.example.catalog.docs;

import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.*;

public final class DocumentationPreprocessors {

    private DocumentationPreprocessors() {
    }

    public static OperationRequestPreprocessor safeRequest() {
        return preprocessRequest(
            removeHeaders("Authorization", "Cookie", "X-Internal-Debug"),
            replacePattern(
                Pattern.compile("usr-[0-9]+"),
                "USER_ID"
            ),
            modifyUris()
                .scheme("https")
                .host("api.example.test")
                .removePort()
        );
    }

    public static OperationResponsePreprocessor safeResponse() {
        return preprocessResponse(
            removeHeaders("Set-Cookie", "X-Internal-Node", "Server"),
            modifyHeaders()
                .set("X-Request-Id", "REQUEST_ID"),
            replacePattern(
                Pattern.compile("usr-[0-9]+"),
                "USER_ID"
            ),
            replacePattern(
                Pattern.compile("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{2,}"),
                "user@example.test"
            )
        );
    }
}
```

Then use it in an operation:

```java
document("users-find",
    DocumentationPreprocessors.safeRequest(),
    DocumentationPreprocessors.safeResponse(),
    responseFields(
        fieldWithPath("userId").description("User ID"),
        fieldWithPath("email").description("Contact email"),
        fieldWithPath("status").description("Account status")
    )
)
```

This factory suits public documentation sharing the same masking rules. For operations with different contracts, create a dedicated preprocessor or add a clearly named processing step; do not apply one broad masking suite to every API if it alters needed example data.

## 7. Verifying Masked Snippets

Do not check only that tests pass. You must confirm that generated artifacts no longer contain sensitive values.

### 7.1. Assertions on the Original Response

A MockMvc test can assert that the application returns the expected fixture data:

```java
mockMvc.perform(get("/api/users/{id}", "usr-849201")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.userId").value("usr-849201"))
    .andDo(document("users-find",
        DocumentationPreprocessors.safeRequest(),
        DocumentationPreprocessors.safeResponse(),
        responseFields(
            fieldWithPath("userId").description("User ID"),
            fieldWithPath("email").description("Contact email"),
            fieldWithPath("status").description("Account status")
        )
    ));
```

Assertions verify that the original response still matches the fixture. Preprocessors apply when writing snippets.

### 7.2. Inspecting Snippet Files After Tests

After running tests, inspect the files in build/generated-snippets/users-find:

```text
http-request.adoc
http-response.adoc
response-body.adoc
response-fields.adoc
```

Search for original values that should have been masked:

```powershell
$snippetRoot = "build/generated-snippets/users-find"
$generatedText = Get-Content -Raw "$snippetRoot/http-request.adoc"
$generatedText += Get-Content -Raw "$snippetRoot/http-response.adoc"
$generatedText += Get-Content -Raw "$snippetRoot/response-body.adoc"

if ($generatedText.Contains("usr-849201")) {
    throw "User identifier leaked into generated snippets"
}
if ($generatedText.Contains("alice.private@example.test")) {
    throw "Email leaked into generated snippets"
}
```

This check can be turned into a CI task that fails the build if forbidden values appear in artifacts. For multiple operations, build a list of forbidden patterns/values from fixtures and scan the entire generated snippets directory.

## 8. Documenting Without Distorting the Contract

Masking must preserve the meaning of examples:

- Replace user IDs with clearly formatted placeholders, such as USER_ID.
- Preserve JSON data types; if the ID is a string, the placeholder must also be a string.
- Do not change field names, relations, or headers that belong to the public contract.
- Do not remove Content-Type or status headers needed to understand the response.
- Normalize environment hosts without altering meaningful paths or queries.
- Keep examples realistic enough for clients to understand how to call the API.

If you need to document an authentication header, use a dummy value like Bearer <escape>EXAMPLE_TOKEN</escape> and state clearly that it is a placeholder. Never use a token copied from a running environment.

When an ID appears in multiple places, use a consistent placeholder within the same operation so readers recognize they refer to the same resource. If you replace all IDs with one generic value, ensure the example does not imply false relationships or create confusion between distinct resources.

## 9. Protection Boundaries and Other Data Layers

Operation preprocessors only affect the content Spring REST Docs writes into snippets. They do not automatically:

- Mask application logs or test framework logs.
- Modify data in databases or message brokers.
- Hide requests/responses from proxies, tracing agents, or APM.
- Strip data from test reports, dump files, or other artifacts.
- Replace secret management, access control, or test data policies.

Therefore, prefer dummy data directly in fixtures. Do not load production data into tests just because preprocessors exist. Restrict access to CI artifacts, inspect logs, and publish only verified snippets.

## 10. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| User ID still appears in snippet | Regex does not match format or applied to only one side. | Check request and response separately; expand pattern carefully. |
| Email partially replaced | Regex does not cover valid domain or characters. | Use a pattern matching the data and inspect artifacts after tests. |
| Authorization header still recorded | removeHeaders not attached to the right request preprocessor. | Verify the operation invokes safeRequest(). |
| Staging host appears in HTTP snippet | URI not normalized or only response modified. | Apply modifyUris to whichever side contains the URI. |
| Required documented header deleted | removeHeaders is too broad. | Remove only secret/internal headers; use modifyHeaders to replace values to keep. |
| Snippet shows wrong business example | Regex mistakenly replaced meaningful ID or path. | Narrow the pattern and check request/response fixtures. |
| Test passes yet artifact still leaks data | Asserted only original response, did not scan snippets. | Add artifact checks to CI. |
| Assumed preprocessor protects runtime | Confused documentation generation with application data protection. | Mask fixtures, logs, and tracing at their proper layers. |

## 11. Practice Exercise

Create an endpoint GET /api/users/{userId} returning user ID, email, and status. Test fixtures use a dummy user ID matching pattern usr-849201 and email alice.private@example.test. Test requests/responses may include dummy auth headers and internal environment headers.

Steps to perform:

1. Create DocumentationPreprocessors.safeRequest() to remove Authorization/Cookie, replace user IDs, and normalize the host.
2. Create safeResponse() to remove Set-Cookie/internal headers and replace request IDs and emails.
3. Write a MockMvc test asserting the original response matches the fixture, then attach preprocessors to document(...).
4. Run the test and inspect http-request.adoc, http-response.adoc, and response-body.adoc.
5. Add automated checks ensuring the original user ID and email do not appear in snippets.
6. Verify placeholders preserve data types and examples remain easy to understand.
7. Include masked snippets in Asciidoctor and run clean test asciidoctor.

**Completion criteria:** identify personal identifiers and environment data; use replacePattern, removeHeaders, modifyHeaders, and modifyUris for their intended purposes; verify masked artifacts; understand that preprocessors protect snippets only and do not replace runtime security.

## 12. References

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [Spring REST Docs — OperationPreprocessor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/OperationPreprocessor.html)
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [OWASP Cheat Sheet Series — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Cheat Sheet Series — Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
