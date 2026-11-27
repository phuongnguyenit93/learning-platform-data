# Reusing common preprocessors

## Lesson objectives

In projects with many endpoints, REST Docs tests often repeat request/response preparation steps before writing snippets: formatting JSON, removing sensitive headers, replacing mock tokens, or normalizing dynamic data. If every test declares these operations independently, configurations easily drift apart and become hard to maintain.

Spring REST Docs **preprocessors** transform the request or response representation used to generate documentation. You can configure shared steps at the MockMvc/WebTestClient/REST Assured level or package them into helpers so multiple tests follow the same policy.

This lesson belongs to the **Reuse** chapter of the **SPRING_REST_DOCS** module: producing verifiable REST API documentation through HTTP tests with **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; compiling Asciidoctor/Markdown and integrating into builds and CI.

After this lesson, you will be able to:

- Explain the role of operation preprocessors and when they are applied.
- Reuse request/response preprocessing configurations across multiple operations.
- Set default preprocessors at the documentation configurer level.
- Create shared helpers to normalize requests and responses.
- Remove or replace sensitive data before writing snippets.
- Distinguish transformed documentation data from the actual HTTP exchange.
- Test preprocessing policies and apply them consistently in CI.

## 1. What problems do preprocessors solve?

REST Docs records the operation executed during a test. Requests and responses may contain data unsuitable for putting directly into documentation:

- JSON bodies serialized on a single line, making them hard to read.
- Authorization headers, session cookies, or correlation IDs that should not be exposed.
- Randomly generated tokens, emails, phone numbers, or IDs that make snippets unstable.
- Tests for the same API presenting output inconsistently.

Instead of editing snippets after generation, preprocess the operation data before REST Docs generates the snippets.

~~~mermaid
flowchart LR
    A["HTTP test executes"] --> B["Request / response"]
    B --> C["Shared preprocessors"]
    C --> D["REST Docs snippets"]
    D --> E["Asciidoctor / Markdown"]
~~~

A preprocessor acts on the data copy that REST Docs uses to create documentation. It is not middleware altering the request received by the application or the response received by the real client. For instance, removing Authorization from snippets does not mean that header is stripped from the HTTP request sent to the controller.

## 2. Separating request and response preprocessing

Spring REST Docs provides preprocessor factory methods in the org.springframework.restdocs.operation.preprocess.Preprocessors package. Two common groups are:

- **Request preprocessing:** normalizes the request before generating http-request, request body, and related snippets.
- **Response preprocessing:** normalizes the response before generating http-response, response body, and related snippets.

Example formatting JSON for readability:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(get("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint())
    ));
~~~

prettyPrint() makes JSON in snippets easier to read when the body is a supported format. It only changes how content is rendered in documentation; it does not modify the data processed by the application.

If every operation needs formatting, declare defaults once instead of repeating those two lines in every test.

## 3. Declaring shared default preprocessors

With MockMvc, MockMvcRestDocumentationConfigurer can set default request/response preprocessors:

~~~java
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.mockmvc.MockMvcRestDocumentationConfigurer;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;

MockMvcRestDocumentationConfigurer configurer =
    documentationConfiguration(restDocumentation)
        .operationPreprocessors()
        .withRequestDefaults(prettyPrint())
        .withResponseDefaults(prettyPrint());
~~~

This is an illustrative configuration for a project using Spring Test/MockMvc. Pass the configurer into MockMvcBuilders or your test setup according to the existing test structure. You can place the configuration in a base test class or shared factory so all tests use the same configurer.

Once default preprocessors are declared, operations only need to document their specific parts:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        responseFields(
            fieldWithPath("id").description("Order ID"),
            fieldWithPath("status").description("Order status")
        )
    ));
~~~

You do not need to call preprocessRequest(prettyPrint()) and preprocessResponse(prettyPrint()) in each operation if defaults already apply. Avoid double formatting or conflicting configurations at the test level.

## 4. Packaging helpers for reuse

When you do not want to put every policy into the configurer, you can create a helper returning preprocessor configurations for operations that need them.

For example, grouping preprocessors by purpose:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import org.springframework.restdocs.operation.preprocess.OperationPreprocessor;

final class ApiDocumentationPreprocessors {

    private ApiDocumentationPreprocessors() {
    }

    static OperationPreprocessor[] safeRequestDefaults() {
        return new OperationPreprocessor[] {
            prettyPrint(),
            removeHeaders("Authorization")
        };
    }

    static OperationPreprocessor[] readableResponseDefaults() {
        return new OperationPreprocessor[] {
            prettyPrint()
        };
    }
}
~~~

Helpers centralize policies and provide meaningful names. Accepted preprocessor types and overloads may vary by REST Docs version. Check the Javadoc for the dependency in use; if an API requires OperationRequestPreprocessor or OperationResponsePreprocessor, create helpers returning those specific types rather than casting.

For APIs that take individual preprocessors, pass elements individually to preprocessRequest(...) or preprocessResponse(...). For configurers supporting varargs, pass the corresponding list to withRequestDefaults(...) and withResponseDefaults(...). Do not assume every overload has the same signature.

## 5. Choosing the scope: global, API group, or per operation

Not every preprocessor should apply to the entire documentation:

| Scope | When suitable | Example |
| --- | --- | --- |
| Entire MockMvc configurer | Rules always true for every endpoint | Pretty-printing JSON |
| API group | A group of endpoints sharing a policy | Hiding internal headers for admin APIs |
| Single operation | Only that endpoint has data requiring processing | Replacing mock tokens in a callback response |
| Single snippet type | Only one fragment needs custom presentation | Customizing a payload snippet |

General formatting rules should be placed at the configurer level. Rules protecting sensitive data require more care: if a sensitive header can appear in any operation, masking/removal policies should be applied centrally so no endpoint is missed.

Do not add global preprocessing that strips contract information. For example, removing all Content-Type headers would leave snippets unable to show request/response formats.

## 6. Removing sensitive headers

Headers like Authorization should not appear in public documentation. You can use a preprocessor to remove the header from the recorded request:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token"))
    .andExpect(status().isOk())
    .andDo(document("profile-get",
        preprocessRequest(removeHeaders("Authorization"))
    ));
~~~

The header is still sent to the application for authentication during the test; the preprocessor only removes it from the operation recorded by REST Docs.

If you need to keep the header name so readers know the API requires authentication, without exposing the value, use a preprocessor that replaces the value with a placeholder as supported by your version's API, or write a custom operation preprocessor. The snippet can then show:

~~~http
GET /api/profile HTTP/1.1
Authorization: Bearer [redacted]
Accept: application/json
~~~

Keeping the header name and authentication structure is often more helpful than deleting the entire header, provided the placeholder cannot be mistaken for a real token.

## 7. Normalizing dynamic data in requests/responses

Some responses contain dynamic timestamps, UUIDs, or hosts. If those values are not central to the API contract, you can replace them in documentation to keep snippets stable:

~~~java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content(requestJson))
    .andExpect(status().isCreated())
    .andDo(document("orders-create",
        preprocessResponse(
            replacePattern(
                Pattern.compile("\"createdAt\":\"[^\"]+\""),
                "\"createdAt\":\"2026-01-01T00:00:00Z\""
            )
        )
    ));
~~~

This example replaces JSON strings matching a regular expression in the documented response copy. Only use this when the pattern is narrow enough and will not unintentionally alter structure. If you need to replace structured JSON fields, use a custom preprocessor that parses JSON and updates the exact field rather than a broad regex.

Do not replace contract-significant values. For example, orderId, status, monetary amounts, or fields clients must understand should remain intact or use deterministic fixtures straight from the test.

## 8. Reusing across multiple tests and multiple clients

REST Docs supports different test integrations. The reuse idea is the same: normalize operation requests/responses before generating snippets. How configurers/filters are attached depends on the integration:

| Integration | Configuration point | How to reuse |
| --- | --- | --- |
| MockMvc | MockMvcRestDocumentationConfigurer | Share configurer or base test |
| WebTestClient | WebTestClientRestDocumentationConfigurer | Share WebTestClient builder/configuration |
| REST Assured | RestAssuredRestDocumentation filter/configuration | Share RequestSpecification and filter |

With REST Assured, you can create a shared specification containing the REST Docs filter and use it across multiple tests. With WebTestClient, configure documentation on a shared builder. Do not copy MockMvc configuration verbatim into the other two integrations, as each integration has its own configuration API.

Keep preprocessing policies equivalent across test clients: the same sensitive headers must be masked, the same JSON formatted, and the same dynamic data normalized. If three test harnesses produce different documentation, verify whether the difference is intentional or caused by configuration drift.

## 9. Preprocessor ordering and idempotency

When combining multiple steps, ordering can affect the outcome. For example:

1. Replace token values.
2. Remove headers that should not appear.
3. Format JSON.

If you remove the header first, a subsequent header-value replacement step has no effect. If you format JSON first and a regex relies on a single-line string, the pattern may no longer match.

Design helpers so that:

- Order is declared explicitly and commented when necessary.
- Each step modifies only the intended piece of data.
- Repeated execution does not keep distorting the output (idempotent where appropriate).
- Information needed to understand the contract is never stripped.
- Tests verify that snippets are masked/formatted properly.

Ordering example:

~~~java
preprocessResponse(
    replacePattern(Pattern.compile("internal-node-[0-9]+"), "service-node"),
    prettyPrint()
)
~~~

This illustrates transformation order. If JSON whitespace or escaping can vary, patterns should be tested against the exact representation before and after each step.

## 10. Testing preprocessing policies

Do not only assert that the endpoint returns the right status. Verify that generated snippets follow policy:

- JSON is formatted when required.
- Authorization header is not exposed or is replaced with a placeholder.
- Session cookies are not written with real values.
- Dynamic timestamps/UUIDs are normalized if permitted by the contract.
- Important headers like Content-Type and Location remain present.

Example checking a snippet file after a test:

~~~java
String requestSnippet = Files.readString(
    Path.of("build/generated-snippets/profile-get/http-request.adoc"),
    StandardCharsets.UTF_8
);

assertThat(requestSnippet).doesNotContain("test-token");
assertThat(requestSnippet).contains("Accept");
~~~

Paths and extensions depend on the output directory and template format. You can place snippet checks inside a test or in a separate validation step after all tests complete. Ensure tests do not depend on execution order or leftover old snippet files.

### 10.1. Verifying preprocessors do not alter HTTP behavior

Because preprocessors act on the operation data used for documentation, tests must prove the application still receives the proper request:

~~~java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token"))
    .andExpect(status().isOk());
~~~

Then verify the snippet does not contain test-token. These two assertions prove two distinct goals:

- The actual test request still carries the authentication information needed for the endpoint to process it.
- The documentation has removed or masked the sensitive value.

## 11. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Authorization header still appears in snippet | Preprocessor was not attached to the operation/configurer | Check request preprocessing and scope |
| Endpoint no longer receives Authorization | Confused documentation preprocessor with a real HTTP filter or placed logic in the wrong layer | Verify the header is still sent in the test request |
| JSON snippet stays on one line | prettyPrint() not applied or content type unrecognized | Check request/response content type and configurer |
| Some tests are formatted, others are not | Duplicated configuration or test uses a different builder | Move defaults into a factory/base configuration |
| Token replaced in body but still exposed in header | Preprocessed only the body, forgot headers | Add a dedicated header policy |
| Timestamp replacement is too broad | Regex matches other fields as well | Use a narrower pattern or parse structured JSON |
| Content-Type header disappears | Used removeHeaders too broadly | Only remove specific sensitive headers |
| Snippet missing contract information | Preprocessor removed critical data | Review the retained header/field list |
| MockMvc API has config but REST Assured does not | Each integration has its own configurer/filter | Create equivalent configuration for each test harness |
| Helper does not compile | Preprocessor types or overloads differ across REST Docs versions | Check Javadoc and use the exact request/response types |
| CI passes due to stale snippets | Output directory retained artifacts from a prior run | Refresh output cleanly and validate content |

## 12. Practice exercise

Create an endpoint:

~~~text
GET /api/profile
~~~

The test request includes an Authorization header with value Bearer test-token and an Accept: application/json header.

Response JSON:

~~~json
{
  "id": 42,
  "name": "Lan",
  "generatedAt": "2026-11-17T08:30:15Z"
}
~~~

Requirements:

1. Create a shared helper/preprocessor to pretty-print request and response JSON.
2. Remove or replace the Authorization value in the request snippet.
3. Normalize generatedAt to a fixture timestamp if the timestamp is not part of the contract.
4. Reuse the same configuration across at least two operation tests.
5. Assert the endpoint still receives the request with Authorization and returns a success response.
6. Read the generated snippet to confirm test-token does not appear, while required Accept and Content-Type headers are retained.
7. Wire snippet-generating tests and output verification into CI.

**Completion criteria:** helper is reused; request/response snippets have consistent formatting; sensitive data is masked; HTTP behavior remains correct; CI fails if a snippet leaks a token or drops an important header.

## Remember

Preprocessors transform the request/response copy that Spring REST Docs uses to build snippets without altering the application's HTTP exchange. Place global rules such as pretty-printing at the configurer level; package group or operation rules into helpers when needed. Use preprocessing to strip/replace sensitive data and normalize dynamic values, while preserving information required to understand the contract. Verify both actual requests and preprocessed snippets, and apply equivalent policies across MockMvc, WebTestClient, and REST Assured. Centralizing shared configuration keeps documentation consistent and easy to maintain in CI.

**References:** [Spring REST Docs Reference – Preprocessing](https://docs.spring.io/spring-restdocs/reference/documentation-operations/preprocessing.html), [Spring REST Docs Preprocessors API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/Preprocessors.html), [Spring REST Docs MockMvc API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentationConfigurer.html).
