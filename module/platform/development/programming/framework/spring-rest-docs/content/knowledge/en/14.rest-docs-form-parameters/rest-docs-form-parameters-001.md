# Documenting form parameters with `formParameters`

## 1. When do you need to document form parameters?

In **Spring REST Docs** (`SPRING_REST_DOCS`), REST API documentation is generated from HTTP tests that have run successfully. An endpoint that receives data from an HTML form typically uses `Content-Type: application/x-www-form-urlencoded`; each `name=value` pair resides in the request **body**. Callers of the API need to know which fields are required, which fields can be omitted, and the meaning and format of each value.

For example, a client sends a request to subscribe to a newsletter:

```http
POST /subscriptions HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=lan%40example.com&frequency=weekly&referral=docs
```

After decoding the form, the server receives three parameters: `email`, `frequency`, and `referral`. Unlike JSON, they are not fields of a JSON object. Spring REST Docs provides `RequestDocumentation.formParameters(...)` to describe **form parameters in the body** and generate the `form-parameters.adoc` snippet from the actual request in the test.

**Practice goal:** create an endpoint that accepts a form, write a MockMvc test that generates the snippet, understand how parameters are validated, and then include the snippet in an Asciidoctor page and build/CI pipeline. The same approach can be applied with WebTestClient and REST Assured.

## 2. Distinguishing form parameters from other request parts

| Data | Location / data type | Appropriate documentation method |
| --- | --- | --- |
| `email=lan%40example.com` | `application/x-www-form-urlencoded` body | `formParameters(...)` |
| `?page=2&size=10` | Query string in the URL | `queryParameters(...)` |
| `/subscriptions/42` | Value in the path | `pathParameters(...)` |
| `{"email":"lan@example.com"}` | JSON body | `requestFields(...)` |
| `Authorization: Bearer ...` | HTTP header | `requestHeaders(...)` |
| Files and parts in `multipart/form-data` | Multipart request body | `requestParts(...)`, snippets supporting request parts |

You should not treat `formParameters` and `queryParameters` as equivalent just because Spring MVC can bind both with `@RequestParam`. For example, `POST /subscriptions?source=web` with a body of `email=...` has parameters in two different places: `source` is a query parameter, while `email` is a form parameter. If you need to document both, add both snippets separately to the `document(...)` call.

The `formParameters(...)` API has been available since **Spring REST Docs 3.0.0**. When referring to older code that uses `requestParameters(...)`, check the library version and switch to the dedicated `queryParameters(...)` / `formParameters(...)` API pair when using Spring REST Docs 3.x or later.

## 3. Core API: `formParameters` and `parameterWithName`

Commonly used static imports:

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.relaxedFormParameters;
```

Example of declaring a form's contract:

```java
formParameters(
    parameterWithName("email")
        .description("Subscription email address; required"),
    parameterWithName("frequency")
        .optional()
        .description("Frequency: weekly or monthly; defaults to weekly"),
    parameterWithName("referral")
        .optional()
        .description("Referral code; may be omitted")
)
```

- `parameterWithName("email")` creates a descriptor for the **parameter name**, not a specific value.
- `.description(...)` explains the meaning, valid values, format, units, or default. You should clearly document the rules that the API actually enforces.
- `.optional()` allows the parameter to be absent from the request under test; it **does not automatically turn** an `@RequestParam` in the controller into an optional parameter and does not replace business logic tests.
- `.ignored()` is used when an incoming parameter must be accepted but you do not want it displayed in the snippet table.

By default, Spring REST Docs checks the **set of parameter names**: if the request contains an undeclared form parameter, snippet generation fails; a declared parameter that is missing from the request also causes an error unless it is marked `optional()`. This check does not automatically verify email validity, value ranges, or business conditions; those require separate assertions and tests.

## 4. Complete example with Spring MVC and MockMvc

Suppose the newsletter subscription API has three parameters: `email` is required; `frequency` and `referral` are optional. When `frequency` is omitted, the server defaults to `weekly`.

### 4.1. Controller receiving form data

```java
package example.docs;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/subscriptions")
public class SubscriptionController {

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> create(
            @RequestParam String email,
            @RequestParam(defaultValue = "weekly") String frequency,
            @RequestParam(required = false) String referral) {

        // Simulate business rules; a real system would persist the subscription.
        if (!frequency.equals("weekly") && !frequency.equals("monthly")) {
            return ResponseEntity.badRequest().build();
        }
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

This is a minimal illustrative controller: it checks `frequency`, but does not yet validate email syntax, prevent duplicate subscriptions, or persist data. Documentation for a real system must reflect the rules actually implemented and tested.

### 4.2. Integrating Spring REST Docs in tests

For a Spring Boot project using Gradle, you need Spring Boot Test and the corresponding MockMvc library:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

The following example assumes the Spring REST Docs version is provided by the project's dependency management configuration.

```java
package example.docs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(SubscriptionController.class)
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class SubscriptionDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void createSubscriptionGeneratesFormParameterSnippet() throws Exception {
        mockMvc.perform(post("/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "lan@example.com")
                .param("frequency", "weekly")
                .param("referral", "docs"))
            .andExpect(status().isCreated())
            .andDo(document("subscriptions/create",
                formParameters(
                    parameterWithName("email")
                        .description("Subscription email; required"),
                    parameterWithName("frequency")
                        .optional()
                        .description("weekly or monthly; defaults to weekly"),
                    parameterWithName("referral")
                        .optional()
                        .description("Referral code, if any")
                )
            ));
    }

    @Test
    void missingRequiredEmailIsRejected() throws Exception {
        mockMvc.perform(post("/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("frequency", "weekly"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidFrequencyIsRejected() throws Exception {
        mockMvc.perform(post("/subscriptions")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "lan@example.com")
                .param("frequency", "hourly"))
            .andExpect(status().isBadRequest());
    }
}
```

Workflow of the documentation test:

1. `post(...)` builds the HTTP request; `contentType(APPLICATION_FORM_URLENCODED)` specifies the body format expected by the API; `.param(...)` supplies each form value to MockMvc.
2. `.andExpect(status().isCreated())` verifies the response. If this assertion fails, the execution chain does not reach snippet generation in this example.
3. `.andDo(document("subscriptions/create", ...))` writes the snippets into the directory under the `subscriptions/create` identifier.
4. `formParameters(...)` matches the request's field names against the declared `parameterWithName(...)` descriptors and generates the documentation table.

The two error tests illustrate **endpoint contract verification**, complementing Spring REST Docs' check on the completeness of the parameter list. Depending on your Spring Security configuration, POST requests in projects with CSRF protection may require adding a valid CSRF token in tests.

### 4.3. Generated snippet

After running the tests successfully, the output directory contains the file:

```text
build/generated-snippets/
└── subscriptions/
    └── create/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
```

`form-parameters.adoc` is an AsciiDoc table generated by Spring REST Docs, with content equivalent to the following example (actual formatting depends on the template):

| Parameter | Description |
| --- | --- |
| `email` | Subscription email; required |
| `frequency` | weekly or monthly; defaults to weekly |
| `referral` | Referral code, if any |

**Note:** marking `.optional()` prevents the test from failing if the field is missing; explain optionality and default values in the description so readers understand accurately, rather than relying solely on how the template renders it.

## 5. Important scenarios when documenting forms

### 5.1. Ignoring secondary parameters with `.ignored()`

Suppose the request also includes `trackingCode` used by an integration layer, while the documentation page only wants to publish business fields:

```java
formParameters(
    parameterWithName("email").description("Subscription email"),
    parameterWithName("trackingCode").ignored()
)
```

When the request includes `trackingCode`, validation does not treat it as an undeclared parameter, yet it **does not appear** in the `form-parameters.adoc` table. Only use `ignored()` when you intentionally decide not to publish that field; do not overuse it to hide missing documentation errors.

### 5.2. Relaxed mode `relaxedFormParameters(...)`

```java
relaxedFormParameters(
    parameterWithName("email").description("Subscription email")
)
```

In this mode, the form may contain other parameter names without causing snippet generation to fail. However, `email` is still checked for presence because it has not been marked `.optional()`. Relaxed mode is suitable for documenting **part** of a large form; documentation describing a complete public contract should prefer strict `formParameters(...)`.

### 5.3. Optional field actually absent

A valid request that sends only `email`:

```java
mockMvc.perform(post("/subscriptions")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "lan@example.com"))
    .andExpect(status().isCreated())
    .andDo(document("subscriptions/create-minimal",
        formParameters(
            parameterWithName("email").description("Subscription email"),
            parameterWithName("frequency").optional()
                .description("Frequency; defaults to weekly"),
            parameterWithName("referral").optional()
                .description("Referral code")
        )
    ));
```

This verifies that the documentation accepts a request missing the two optional fields. To verify that the server actually applies the default value, add an assertion at the appropriate layer (for example, verifying the parameter passed to the service) rather than inferring it solely from status `201`.

### 5.4. Single parameter name with multiple values

For an endpoint with form parameters `topics=spring&topics=docs`, in MockMvc you can construct the request with:

```java
.param("topics", "spring", "docs")
```

And declare **one** descriptor by name:

```java
parameterWithName("topics")
    .description("List of topics; the topics name can be repeated")
```

`formParameters` checks the `topics` name, not each element of the list or the number of values. Write separate tests if the endpoint enforces a limit on the number of items, disallows duplicates, or validates values against an allowed set.

### 5.5. Combining query parameters and form parameters

```java
mockMvc.perform(post("/subscriptions?source=landing-page")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "lan@example.com"))
    .andExpect(status().isCreated())
    .andDo(document("subscriptions/create-with-source",
        queryParameters(
            parameterWithName("source").description("Traffic source")
        ),
        formParameters(
            parameterWithName("email").description("Subscription email")
        )
    ));
```

This snippet requires a static import for `queryParameters`. For query parameters, passing the value directly in the URL or using `.queryParam(...)` makes the parameter origin clear. Do not mechanically substitute `.param(...)` for query parameters, as it represents a Servlet-level request parameter and can easily be confused with the form body.

## 6. Same technique with WebTestClient and REST Assured

Spring REST Docs supports multiple HTTP testing tools; `formParameters(...)` and `parameterWithName(...)` remain in the same `org.springframework.restdocs.request` package. The main difference is how the request is sent and how snippet generation is hooked into the result.

### 6.1. WebTestClient

The example below assumes `webTestClient` is already configured with Spring REST Docs and a WebFlux endpoint handles the form body:

```java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("email", "lan@example.com");
form.add("frequency", "weekly");

webTestClient.post()
    .uri("/subscriptions")
    .body(BodyInserters.fromFormData(form))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("subscriptions/webtestclient",
        formParameters(
            parameterWithName("email").description("Subscription email"),
            parameterWithName("frequency").optional()
                .description("Frequency, defaults to weekly")
        )
    ));
```

Relevant imports are `org.springframework.util.MultiValueMap`, `LinkedMultiValueMap`, `org.springframework.web.reactive.function.BodyInserters`, and `WebTestClientRestDocumentation.document`. `BodyInserters.fromFormData(...)` creates a URL-encoded form body. In Spring WebFlux, how a handler reads form data differs from Spring MVC; do not assume the `@RequestParam` controller example above applies directly to WebFlux. Check the handler binding, such as using `ServerWebExchange.getFormData()` or an appropriate model.

### 6.2. REST Assured

The following example assumes `specification` is configured with `RestAssuredRestDocumentation.documentationConfiguration(...)` and an HTTP server is running:

```java
given(specification)
    .filter(document("subscriptions/rest-assured",
        formParameters(
            parameterWithName("email").description("Subscription email"),
            parameterWithName("frequency").optional()
                .description("Frequency, defaults to weekly")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "lan@example.com")
    .formParam("frequency", "weekly")
    .when().post("/subscriptions")
    .then().statusCode(201);
```

Specific components: `io.restassured.RestAssured.given`, `io.restassured.http.ContentType.URLENC`, and `RestAssuredRestDocumentation.document`. REST Assured sends form data using `.formParam(...)` and applies the documentation filter with `.filter(...)`.

## 7. Including snippets in documentation and CI

### 7.1. Authoring an Asciidoctor page

Create an AsciiDoc page (for example, `src/docs/asciidoc/index.adoc`) and use the `include` directive:

```adoc
= Newsletter Subscription API

== Create subscription

=== HTTP request
include::{snippets}/subscriptions/create/http-request.adoc[]

=== Form parameters
include::{snippets}/subscriptions/create/form-parameters.adoc[]

=== HTTP response
include::{snippets}/subscriptions/create/http-response.adoc[]
```

`{snippets}` must be configured to point to the **actual snippets directory** (for example, `build/generated-snippets` with Gradle). Relative paths must resolve correctly relative to the documentation directory; in build tasks, you can use an absolute path to avoid depending on where the command is run.

### 7.2. Connecting the test and documentation build steps

In Gradle with the Asciidoctor plugin, the task relationship can be configured as follows (Groovy DSL, added to a build that already has the appropriate plugins):

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir.absolutePath
}
```

A CI step can then run `./gradlew test asciidoctor`. When tests fail because the parameter contract no longer matches, the pipeline stops and does not publish invalid documentation. When tests pass, Asciidoctor picks up the generated snippets and builds HTML or whatever output format the project configures. You should inspect the Asciidoctor output file itself, not just check that the snippets directory exists.

If the main documentation is written in **Markdown**, you can link to the generated HTML documentation or set up an appropriate conversion/embedding step; `include::{snippets}/...[]` is **AsciiDoc syntax**, not an include syntax supported out of the box by all Markdown renderers.

## 8. Common errors and how to fix them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `form-parameters.adoc` does not appear | `document(...)` not called, REST Docs not configured, or test never reaches the snippet-writing step | Check `@AutoConfigureRestDocs` configuration, assertions, snippet identifier, and output directory |
| Reports undeclared/undocumented parameter | Form body has a new name not yet declared in `formParameters(...)` | Add `parameterWithName(...)`, or use `ignored()` only if intentional |
| Reports missing declared parameter | Test does not send the parameter while the descriptor defaults to required | Add test data if required; mark `.optional()` if the contract genuinely allows omitting it |
| Sent JSON but form table is empty / errors | Body is not URL-encoded form data | Use the proper content type and form body, or switch to `requestFields(...)` for JSON |
| Put `page` in the URL but used `formParameters` | Confused query string with form body | Use `queryParameters(...)` for `page` |
| Using `relaxedFormParameters` lets form changes go undetected | Relaxed mode accepts names outside the list | Switch back to strict mode when full contract protection is needed |
| Asciidoctor reports `include` file not found | Tests have not run, wrong identifier, or `{snippets}` points to the wrong path | Make the documentation task depend on the test task and check the actual output directory |

Do not put real tokens, passwords, addresses, or personal data in fixtures: the HTTP request snippet may expose test request values in published documentation. Use dummy data such as `lan@example.com` and review snippets before release.

## 9. Practice exercises

1. Create a `POST /feedback` API with a required `rating` form parameter (1–5), optional `comment`, and `tags` that can accept multiple values.
2. Write a MockMvc test that submits a valid form and uses `formParameters(...)` to describe the three parameters, marking `comment` and `tags` as `.optional()` if the controller allows omitting them.
3. Write an additional test confirming `rating=6` is rejected; do not treat successful snippet generation as proof that validation is correct.
4. Try adding an undeclared `unexpected=1` parameter to the body; observe the test failing in strict mode. Then try `relaxedFormParameters(...)` and explain the difference.
5. Include `form-parameters.adoc` in an Asciidoctor page and verify the final page renders the table accurately from the test you just ran.

**Pass criteria:** an HTTP test verifies behavior, the `form-parameters.adoc` snippet is generated from that exact request, the documentation accurately explains required/optional fields, and the documentation build does not ignore parameter contract errors.

## References

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — `RequestDocumentation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
