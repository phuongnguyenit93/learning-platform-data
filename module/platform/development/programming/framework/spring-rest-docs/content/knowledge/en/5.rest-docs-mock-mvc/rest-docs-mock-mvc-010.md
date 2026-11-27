# Preprocessing MockMvc Requests and Responses

## Lesson Objectives

When using **MockMvc** with **Spring REST Docs**, requests and responses recorded from tests may contain data unsuitable for direct inclusion in documentation: single-line JSON, internal hosts, random ports, test headers, tokens, or values that need masking. **Operation preprocessors** let you normalize requests/responses before REST Docs generates snippets.

In the **SPRING_REST_DOCS** module, we build verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generate snippets for requests, responses, payloads, parameters, and headers; compile Asciidoctor/Markdown; and integrate into the build and CI pipeline.

After this lesson, you will be able to:

- Explain where preprocessing fits in the MockMvc and Spring REST Docs flow.
- Use **preprocessRequest(...)** and **preprocessResponse(...)** to apply processors to documented operations.
- Pretty-print JSON/XML, normalize URIs, and remove headers that should not be published.
- Mask or replace sensitive data before generating snippets.
- Choose between applying preprocessing per **document(...)** call or as shared default configuration.
- Distinguish data preprocessed for documentation from the actual data received/returned by the application.
- Verify snippets after preprocessing and integrate documentation generation into build/CI.

## 1. Where Does Preprocessing Fit in the Documentation Flow?

A typical MockMvc test sends a request to a controller, asserts status and response, and then calls **document(...)** to generate snippets:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get"));
~~~

When adding preprocessing, we instruct REST Docs to transform the recorded operation before creating snippets:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint())
    ));
~~~

Overview flow:

~~~mermaid
flowchart TD
    A["MockMvc request"] --> B["Spring MVC processes request"]
    B --> C["HTTP response"]
    C --> D["Test assertions"]
    D --> E["document(...) receives operation"]
    E --> F["Preprocess request / response"]
    F --> G["Generate request, response, and payload snippets"]
    G --> H["Asciidoctor / API documentation"]
~~~

Preprocessors act on **the operation recorded by REST Docs to generate documentation**. They do not replace controllers, alter service logic, or act as middleware modifying requests before the application processes them. For example, **prettyPrint()** does not alter the JSON returned by the controller; it formats the JSON copy written into snippets.

### 1.1. Two Main Function Groups

| Function | Applies To | Purpose |
| --- | --- | --- |
| **preprocessRequest(...)** | Recorded HTTP request | Normalize URIs, format body, remove headers, or mask request data |
| **preprocessResponse(...)** | Recorded HTTP response | Format body, remove headers, mask response data |

These functions are typically imported from:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
~~~

An operation can use both groups or only one. There is no need to preprocess the request if only the response needs formatting, and vice versa.

## 2. Pretty-Printing Bodies with prettyPrint()

JSON or XML in default snippets can be hard to read if written on a single line. **prettyPrint()** formats the body to make documentation easier to read.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(get("/api/orders/{orderId}", 42L)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint())
    ));
~~~

Example JSON before formatting:

~~~json
{"id":42,"status":"OPEN","customer":{"name":"Lan","active":true}}
~~~

After formatting:

~~~json
{
  "id": 42,
  "status": "OPEN",
  "customer": {
    "name": "Lan",
    "active": true
  }
}
~~~

**prettyPrint()** is useful when the body is JSON/XML recognized and supported by the preprocessor. It does not replace **requestFields(...)** or **responseFields(...)**: body snippets present the payload, while field snippets describe the meaning and structure of each field.

If a test does not send or receive a body, pretty-printing produces no new body content. Keep the proper **Content-Type** and inspect the generated snippets to confirm the final formatting.

## 3. Normalizing URIs in Request Snippets

In CI, MockMvc may record a host, scheme, or port different from the public URL. For example, documentation should show:

~~~http
https://api.example.com/api/orders/42
~~~

but the test records:

~~~http
http://localhost:51827/api/orders/42
~~~

Use **modifyUris()** to normalize URIs in documentation:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

mockMvc.perform(get("/api/orders/{orderId}", 42L))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort()
        )
    ));
~~~

If documentation requires a specific public port, use **port(...)** instead of **removePort()**:

~~~java
modifyUris()
    .scheme("https")
    .host("api.example.com")
    .port(443)
~~~

This normalization only alters the URI recorded in snippets. It does not route real requests to **api.example.com**, change the test execution environment, or check DNS/TLS. Use the public host specified by the API contract, avoiding internal CI hostnames or random ports in published documentation.

## 4. Removing Unwanted Headers from Documentation

A request may carry internal, tracing, or test headers. If a header is not part of the API contract, remove it from the recorded request:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

mockMvc.perform(get("/api/orders/{orderId}", 42L)
        .header("X-Test-Run", "local-123")
        .header("X-Internal-Trace", "trace-456"))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(
            removeHeaders("X-Test-Run", "X-Internal-Trace")
        )
    ));
~~~

For responses, apply **removeHeaders(...)** inside **preprocessResponse(...)**:

~~~java
preprocessResponse(
    removeHeaders("X-Internal-Server", "X-Debug-Id")
)
~~~

Only remove a header from snippets when it is unnecessary for API consumers. Do not arbitrarily strip **Authorization**, **Content-Type**, **Accept**, **ETag**, **Location**, **Cache-Control**, or other headers meaningful to how clients call the API if documentation needs to show clients how to use them.

If a header contains secrets such as a bearer token, cookie, or API key, mask or remove it from the documentation record. Also avoid putting real secrets into fixtures/tests when dummy values can be used.

## 5. Masking or Replacing Sensitive Data

Some requests/responses contain data that must be hidden before generating snippets:

- **Authorization** containing an access token.
- Cookies containing session identifiers.
- JSON bodies containing emails, phone numbers, or personal data used in fixtures.
- Responses containing internal information that should not be published.

Two common approaches are removing the header entirely or **replacing part of the value** with placeholder data.

### 5.1. Removing Sensitive Headers

~~~java
preprocessRequest(
    removeHeaders("Authorization", "Cookie")
)
~~~

Example:

~~~http
GET /api/orders/42
Accept: application/json
~~~

The snippet no longer displays the token. However, if readers need to know the endpoint requires authentication, document the **Authorization header using a safe placeholder** via an intentional replacement rather than erasing all signs of the security mechanism.

### 5.2. Replacing Patterns in the Body

Spring REST Docs provides **replacePattern(...)** to replace a regex pattern in the operation body:

~~~java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

preprocessResponse(
    replacePattern(
        Pattern.compile("lan@example\\.com"),
        "user@example.com"
    )
)
~~~

In Java strings, regular expression backslashes must be escaped. If a pattern could match multiple values, write a sufficiently specific regex and inspect the body after replacement to avoid accidentally altering business content.

It can be applied similarly to request bodies:

~~~java
preprocessRequest(
    replacePattern(
        Pattern.compile("0901234567"),
        "0900000000"
    )
)
~~~

**replacePattern(...)** operates on the preprocessed operation copy; it does not modify objects handled by the controller or data stored in the database. Verify the snippet output to make sure no values needing masking remain.

### 5.3. Masking Links When Responses Contain URLs

If a response contains HAL links or JSON links with test-environment URLs, consider the **maskLinks()** preprocessor to replace link URIs with placeholders in documentation:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.maskLinks;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

preprocessResponse(maskLinks())
~~~

Only use this when the response structure is genuinely link content supported by the preprocessor. If the API aims to publish exact URLs or specific link structures, consider **modifyUris()** or targeted replacements instead of masking everything.

## 6. Combining Multiple Preprocessors in One Operation

Preprocessors can be combined inside the same **preprocessRequest(...)** or **preprocessResponse(...)** call. For example:

~~~java
mockMvc.perform(get("/api/orders/{orderId}", 42L)
        .header("X-Test-Run", "ci-987")
        .header("Authorization", "Bearer test-token")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("order-get",
        preprocessRequest(
            modifyUris()
                .scheme("https")
                .host("api.example.com")
                .removePort(),
            removeHeaders("X-Test-Run", "Authorization")
        ),
        preprocessResponse(
            prettyPrint(),
            replacePattern(
                Pattern.compile("lan@example\\.com"),
                "user@example.com"
            )
        )
    ));
~~~

Preprocessor order in a chain matters: each step receives the output of the previous step. Perform normalization and data removal in a clear order, avoiding a replacement step depending on a value already altered by an earlier step.

Do not mask information in a way that causes documentation to misrepresent the contract. For example, replacing **Authorization** by removing the header might mislead users into thinking an endpoint needs no authentication. If you want to show how to pass a token, it is better to use a clearly formatted dummy value, or document the header via a dedicated snippet.

## 7. Applying Shared Default Preprocessing

If most operations require pretty-printing or host normalization, you can configure shared default preprocessors in MockMvc REST Docs.

Example using **MockMvcRestDocumentationConfigurer**:

~~~java
mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(documentationConfiguration(restDocumentation)
        .operationPreprocessors()
            .withRequestDefaults(
                modifyUris()
                    .scheme("https")
                    .host("api.example.com")
                    .removePort(),
                prettyPrint()
            )
            .withResponseDefaults(prettyPrint()))
    .build();
~~~

This configuration snippet shows how to set default preprocessors at the **documentationConfiguration** level. **WebApplicationContext context** and **RestDocumentationContextProvider restDocumentation** must be set up in the test fixture per the MockMvc REST Docs guide for your version.

When default configuration already includes pretty-printing, you do not need to repeat **preprocessRequest(prettyPrint())** and **preprocessResponse(prettyPrint())** in every operation. For an operation requiring special handling, you can supply additional preprocessors in **document(...)**.

### 7.1. When to Use Defaults vs. Per-Operation Preprocessors?

| Scenario | Where to Configure |
| --- | --- |
| All requests use a public host | Request defaults |
| All JSON responses need formatting | Response defaults |
| Only one endpoint needs email masking | Operation-specific preprocessor in that endpoint's document call |
| One endpoint has its own debug header | Remove header in that operation |
| API has multiple response styles or media types | Choose suitable preprocessors per operation |

Do not set an endpoint-specific data masking rule as a system-wide default if it could distort documentation for other endpoints.

## 8. Preprocessing Does Not Replace Descriptors

Preprocessors modify how the operation's request/response is represented; descriptors explain what the data means. For example:

~~~java
document("order-create",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint()),
    requestFields(
        fieldWithPath("description")
            .description("Order description")
    ),
    responseFields(
        fieldWithPath("id")
            .description("Created order ID"),
        fieldWithPath("status")
            .description("Order status")
    )
)
~~~

Here:

- **prettyPrint()** makes the body readable.
- **requestFields(...)** documents the request payload.
- **responseFields(...)** documents the response payload.
- **preprocessRequest(...)** and **preprocessResponse(...)** do not replace verifying that fields are documented.

If a replacement changes field values while preserving structure, descriptors still need to describe the right fields. If a preprocessor alters the JSON structure itself, be careful because payload descriptors also run on the preprocessed operation and might no longer match.

## 9. Verifying Preprocessing Results

Do not assume snippets are clean just because tests pass. Open the generated snippets and check:

1. Host, scheme, and port in **http-request.adoc** match the public URL.
2. Debug headers/tokens/cookies are not unintentionally exposed.
3. Request/response bodies are properly formatted and contain no real data needing masking.
4. Headers required by clients are still preserved.
5. **request-fields.adoc** and **response-fields.adoc** accurately describe the actual payload.

A test with a preprocessed response:

~~~java
mockMvc.perform(get("/api/customers/{customerId}", 12L)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("customer-get",
        preprocessResponse(
            prettyPrint(),
            replacePattern(
                Pattern.compile("lan@example\\.com"),
                "user@example.com"
            )
        )
    ));
~~~

The application response may contain a test email; the snippet after preprocessing must show the placeholder value. If you need to verify replacement output automatically, inspect the snippet file in a separate documentation QA step or write unit tests for custom preprocessors. Never use assertions on the raw response to conclude that the recorded snippet has been transformed.

## 10. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| JSON in snippet is still on one line | **prettyPrint()** not applied or body not recognized | Add preprocessRequest/preprocessResponse properly and check Content-Type |
| URL shows localhost/random port | Request URI not normalized | Use **modifyUris()** in request preprocessor |
| Token still appears in request snippet | Token removed only from response or preprocessor not applied | Remove/replace header in **preprocessRequest(...)** |
| Real email still appears in response snippet | Replacement pattern mismatches or only applied to request | Check regex pattern and use **preprocessResponse(...)** |
| Essential header disappeared | Overly broad header removal | Only remove internal headers; keep contract headers |
| Documentation describes something different from real API | Preprocessor altered business data | Normalize presentation/mask data only; clearly explain placeholders |
| URI double-encoded or normalized twice | Multiple layers transforming URIs | Pick a single normalization point and inspect output |
| Default processor conflicts with per-operation processor | Same transformation applied multiple times | Clearly define defaults and per-operation overrides |

## 11. Practice Exercise

Customer profile management API:

~~~text
GET /api/customers/{customerId}
~~~

Test response contains:

~~~json
{
  "id": 12,
  "name": "Lan",
  "email": "lan@example.com"
}
~~~

Requirements:

1. Write a MockMvc test with request template **/api/customers/{customerId}** and assert HTTP 200.
2. Use **preprocessRequest(...)** to normalize the URI to **https://api.example.com** and remove the **X-Test-Run** header.
3. Use **preprocessResponse(...)** to format JSON and replace **lan@example.com** with **user@example.com** in snippets.
4. Add a **pathParameters(...)** descriptor for **customerId**.
5. Add **responseFields(...)** for **id**, **name**, and **email**.
6. Inspect **http-request.adoc**, **http-response.adoc**, and **response-fields.adoc** to confirm data was properly normalized/masked.
7. Wire the test into the Gradle task before Asciidoctor and ensure CI never publishes snippets containing real data.

Setup template:

~~~java
document("customer-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.com")
            .removePort(),
        removeHeaders("X-Test-Run")
    ),
    preprocessResponse(
        prettyPrint(),
        replacePattern(
            Pattern.compile("lan@example\\.com"),
            "user@example.com"
        )
    ),
    pathParameters(
        parameterWithName("customerId")
            .description("Customer identifier")
    ),
    responseFields(
        fieldWithPath("id").description("Customer ID"),
        fieldWithPath("name").description("Customer name"),
        fieldWithPath("email").description("Email masked in snippet")
    )
)
~~~

**Completion criteria:** request/response snippets are properly formatted; host is normalized; test header does not appear; real email is gone from documentation; path parameter and response fields remain complete.

## Remember

**preprocessRequest(...)** and **preprocessResponse(...)** normalize the HTTP records that Spring REST Docs uses to generate snippets. Use **prettyPrint()** for bodies, **modifyUris()** for URLs, **removeHeaders(...)** to strip internal headers, and **replacePattern(...)** to replace data that needs masking. Processors can be configured per **document(...)** call or as MockMvc defaults, but you must inspect final snippets to guarantee published information stays accurate and free of secrets. Combining preprocessing with descriptors and HTTP tests produces API documentation that is readable, consistent, and ready for build/CI pipelines.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [OperationPreprocessors API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/Preprocessors.html), and [MockMvcRestDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html).
