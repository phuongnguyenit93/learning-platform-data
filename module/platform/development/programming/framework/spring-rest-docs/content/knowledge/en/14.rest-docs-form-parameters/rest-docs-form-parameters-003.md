# Required and optional form fields in Spring REST Docs

## 1. Objectives and context

In a REST API that accepts a form, each field (form field) can be **required** or **optional**. For the API caller, this distinction determines the minimum payload a request must send and what default value applies if a field is omitted. For the test author, it determines the scenarios that need verification. For the documentation author, it determines the corresponding descriptor configuration in Spring REST Docs.

In the **SPRING_REST_DOCS** module, the goal is to generate verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**, and then include the request, response, payload, parameter, and header snippets in Asciidoctor/Markdown documentation and the build/CI workflow. This **Form parameters** chapter specifically focuses on requests with an `application/x-www-form-urlencoded` body, using `formParameters(...)` and `parameterWithName(...)` to describe each field's contract.

After this lesson, you will be able to:

1. Explain the difference between an absent field, a field with an empty value, and a field with a valid value.
2. Distinguish controller binding/validation rules from Spring REST Docs snippet validation rules.
3. Use `.optional()` appropriately so the documentation reflects a form with required and optional fields.
4. Write tests for full requests, minimal requests, and invalid requests.
5. Generate the `form-parameters.adoc` snippet and include it in documentation verified by CI.

## 2. "Required" and "optional" exist at three different layers

Suppose a registration API has three fields:

| Field | Business rule | Example |
| --- | --- | --- |
| `email` | Required, must not be blank | `mai@example.com` |
| `plan` | Optional, defaults to `basic`; accepts `basic` or `plus` | `plus` |
| `displayName` | Optional; may be omitted | `Mai Nguyễn` |

To document this accurately, you must consider three layers:

| Layer | Question to answer | Verification tool |
| --- | --- | --- |
| **Actual request** | Is the parameter name present in the form body? If so, what is its value? | HTTP request and `http-request.adoc` snippet |
| **Server contract** | Is a missing field rejected? Are empty/malformed values accepted? What is the default value? | Controller, validation, and test assertions |
| **Documentation contract** | Is the field name declared in `formParameters(...)`? Can it be absent in the documented test request? | `parameterWithName(...)`, `.optional()`, and Spring REST Docs snippet checks |

**Key takeaway:** `parameterWithName("plan").optional()` only marks the field as *allowed to be absent in the request used to generate documentation*. It **does not change** the controller signature, does not add a default value, and does not automatically validate the `basic`/`plus` value set. Those behaviors must be implemented and tested at the application layer.

### 2.1. A form field is not a JSON field

This is a URL-encoded form body:

```http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

email=mai%40example.com&plan=plus&displayName=Mai+Nguy%E1%BB%85n
```

Whereas the following body is JSON:

```http
POST /registrations HTTP/1.1
Content-Type: application/json

{"email":"mai@example.com","plan":"plus","displayName":"Mai Nguyễn"}
```

The two requests carry similar information but have different structures. For a **form body**, use `formParameters(...)`; for a **JSON body**, use `requestFields(...)`. For parameters placed after `?` in the URL, use `queryParameters(...)`. Do not pick a snippet solely from the controller's `@RequestParam` annotation while ignoring where the data actually lives in the HTTP request.

### 2.2. An absent field differs from an empty field

Consider three form bodies:

```text
# A: Only email
email=mai%40example.com

# B: displayName present with empty value
email=mai%40example.com&displayName=

# C: displayName present as a string containing a space
email=mai%40example.com&displayName=Mai+Nguy%E1%BB%85n
```

- **A:** `displayName` is absent; an `@RequestParam(required = false) String displayName` typically receives `null` if no other value-providing mechanism exists.
- **B:** `displayName` is present and has the empty string `""` as its value; this is not equivalent to being absent.
- **C:** `displayName` is present with the value `"Mai Nguyễn"` after form decoding.

Spring REST Docs can document all three scenarios, but it does not decide whether they are valid according to business rules. `.optional()` allows the parameter name to be missing; if you require a field to be **present and non-empty**, you must enforce that condition on the server and in tests.

In Spring MVC, `@RequestParam(defaultValue = "basic")` can apply when the parameter is missing **or** has an empty value; declaring a default value also makes the parameter non-required during binding. Write tests for both cases if the API needs to distinguish them.

## 3. Spring REST Docs API for form fields

With Spring REST Docs 3.x and later, the commonly used static imports are:

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.relaxedFormParameters;
```

Documenting the three fields in the example:

```java
formParameters(
    parameterWithName("email")
        .description("Registration email, required and must not be blank"),
    parameterWithName("plan")
        .optional()
        .description("Plan basic or plus; defaults to basic"),
    parameterWithName("displayName")
        .optional()
        .description("Display name; may be omitted")
)
```

| API | Meaning | What must not be inferred |
| --- | --- | --- |
| `parameterWithName("email")` | Declares a descriptor for the form parameter name `email`; treated as required by default in snippet validation | Does not verify that the email is valid or non-empty |
| `.description("...")` | Explains the meaning, format, allowed values, and default value | The description text does not automatically become a validation rule |
| `.optional()` | Suppresses snippet errors when the request used to generate documentation omits this parameter name | Does not automatically change `@RequestParam` or business logic |
| `.ignored()` | Accepts the declared parameter in the request but excludes it from the documentation table | Should not be used to hide public fields that ought to be documented |
| `relaxedFormParameters(...)` | Allows the request to include additional form parameters without declared descriptors | Does not mean declared required descriptors are allowed to be absent |

In standard `formParameters(...)` mode, Spring REST Docs compares the **set of parameter names** in the request against the descriptors:

- **Parameter present in request, no descriptor:** fails because the parameter is undocumented.
- **Required descriptor present, parameter missing from request:** fails because the declared parameter was not found.
- **`.optional()` descriptor present, parameter missing from request:** valid during snippet validation.
- **`.ignored()` descriptor present, parameter present:** does not display that descriptor in the output table.

The `formParameters` check is primarily about **names and presence**. It does not guarantee data types, business rules, regular expressions, or the number of elements in a multi-valued field. Those requirements need separate assertions and validation.

## 4. Building an endpoint with required and optional fields

The following example uses Spring MVC. The `POST /registrations` endpoint accepts `application/x-www-form-urlencoded`, always requires `email`, and allows omitting `plan`, `displayName`, and `tag`. `tag` may be repeated multiple times in the form body.

```java
package example.docs;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> create(
            @RequestParam("email") String email,
            @RequestParam(name = "plan", defaultValue = "basic") String plan,
            @RequestParam(name = "displayName", required = false) String displayName,
            @RequestParam(name = "tag", required = false) List<String> tags) {

        // Simplify business logic to focus on form field rules.
        if (email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (!plan.equals("basic") && !plan.equals("plus")) {
            return ResponseEntity.badRequest().build();
        }

        // A real system would persist registration, plan, displayName, and tags.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Key distinctions:

1. `@RequestParam("email")` is required to be present; if missing, Spring MVC typically returns `400 Bad Request` before entering the controller method. If `email=` is sent, the parameter is **present** but rejected by the `isBlank()` check.
2. `@RequestParam(defaultValue = "basic")` lets the server fall back to `basic` when `plan` is missing or empty; therefore, the corresponding REST Docs descriptor must be `.optional()` if a test omits that field.
3. `required = false` on `displayName` and `tag` allows those fields to be absent. With `tag=a&tag=b`, a multi-valued list can be bound into `List<String>`.
4. The example uses `email.contains("@")` to illustrate data rejection; this is **not** a complete email syntax validator. A production API needs standard validation and specific tests aligned with the system contract.
5. Returning `201` for a valid request does not prove data was persisted; persistence is intentionally omitted here.

## 5. MockMvc: testing real cases and generating snippets

### 5.1. Test configuration

For a Spring Boot 3.x application using Gradle Groovy DSL, compatible test dependencies are needed:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

The project's dependency management must provide compatible Spring Boot and Spring REST Docs versions. For projects not using Spring Boot, integrate `RestDocumentationExtension`/`RestDocumentationContextProvider` and the corresponding MockMvc configuration manually.

### 5.2. Full request and minimal request

```java
package example.docs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationFormDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void fullFormRequestIsDocumented() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding("UTF-8")
                .param("email", "mai@example.com")
                .param("plan", "plus")
                .param("displayName", "Mai Nguyễn")
                .param("tag", "java", "spring"))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-full",
                formParameters(
                    parameterWithName("email")
                        .description("Registration email; required, non-empty"),
                    parameterWithName("plan")
                        .optional()
                        .description("Plan basic or plus; defaults to basic"),
                    parameterWithName("displayName")
                        .optional()
                        .description("Display name; may be omitted"),
                    parameterWithName("tag")
                        .optional()
                        .description("Interest tag; may be repeated multiple times")
                )
            ));
    }

    @Test
    void minimalFormRequestIsDocumented() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com"))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-minimal",
                formParameters(
                    parameterWithName("email")
                        .description("Registration email; required, non-empty"),
                    parameterWithName("plan")
                        .optional()
                        .description("Plan basic or plus; defaults to basic"),
                    parameterWithName("displayName")
                        .optional()
                        .description("Display name; may be omitted"),
                    parameterWithName("tag")
                        .optional()
                        .description("Interest tag; may be repeated multiple times")
                )
            ));
    }

    @Test
    void missingRequiredEmailIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("plan", "plus"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void blankEmailIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", ""))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownPlanIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("plan", "enterprise"))
            .andExpect(status().isBadRequest());
    }
}
```

**How to read the results:**

- The `fullFormRequestIsDocumented` test includes all four field names. Even though `plan`, `displayName`, and `tag` are marked `.optional()`, they still appear in this request. "Optional" does not mean "must not be sent".
- The `minimalFormRequestIsDocumented` test sends only `email`. The remaining three fields are absent, yet `formParameters(...)` does not fail because they have `.optional()`.
- The `missingRequiredEmailIsRejected` test proves server behavior when the `email` name is missing. You do not need to force `formParameters(...)` to generate a success snippet from a request that violates the endpoint's contract.
- The `blankEmailIsRejected` test distinguishes a field present with an empty value. Even with a descriptor for `email`, REST Docs does not automatically detect an empty string as invalid data.
- The `unknownPlanIsRejected` test asserts the rule on the allowed values for `plan`. `.description(...)` only documents this rule; the assertion verifies the server behavior.

**Testing note:** MockMvc's `.param(...)` represents a request parameter; when using it for URL-encoded POSTs, inspect the `http-request.adoc` snippet to verify how the framework builds the HTTP body. If Spring Security with CSRF is enabled, POST requests may require valid CSRF token configuration. That is an application security requirement, not a general requirement of `formParameters(...)`.

### 5.3. Documentation generation output

When the two tests with `document(...)` succeed, the snippet output directory has a structure similar to:

```text
build/generated-snippets/
└── registrations/
    ├── create-full/
    │   ├── form-parameters.adoc
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── create-minimal/
        ├── form-parameters.adoc
        ├── http-request.adoc
        └── http-response.adoc
```

The informational content of the `form-parameters.adoc` table includes:

| Parameter | Description |
| --- | --- |
| `email` | Registration email; required, non-empty |
| `plan` | Plan basic or plus; defaults to basic |
| `displayName` | Display name; may be omitted |
| `tag` | Interest tag; may be repeated multiple times |

Spring REST Docs uses templates to render snippets. **Explicitly state requiredness and optionality in the description**, because readers of the published documentation do not necessarily see how the Java descriptors were declared in the test.

## 6. Common pitfalls

### 6.1. Marking `.optional()` when the server still requires the parameter

This is a case where the documentation and server contradict each other:

```java
// Controller: email is required
@RequestParam("email") String email

// Descriptor allows email to be absent
parameterWithName("email").optional()
    .description("Registration email")
```

REST Docs will not treat the absence of `email` as a snippet error, yet the controller may reject the request with `400`. Therefore, the descriptor should reflect the tested API behavior. If `email` is required, **remove `.optional()`** and clearly describe the non-empty requirement.

### 6.2. Forgetting `.optional()` for a field that can genuinely be absent

For example, the endpoint accepts omitting `plan`, yet the snippet declares:

```java
formParameters(
    parameterWithName("email")
        .description("Required email"),
    parameterWithName("plan")
        .description("Plan, defaults to basic")
)
```

When tested with a request containing only `email`, Spring REST Docs treats `plan` as a required descriptor and fails because the request lacks that parameter. Fix this by adding `.optional()` to `plan`; do not "fix" the test by adding `plan=basic` if the test's purpose is to demonstrate that the client is allowed to omit the field.

### 6.3. Using `relaxedFormParameters(...)` to hide omissions

```java
relaxedFormParameters(
    parameterWithName("email")
        .description("Registration email")
)
```

The relaxed variant allows the request to contain extra undocumented parameter names. It **does not resolve** the case where the `email` descriptor is required while `email` is absent from the request. For public API contract documentation, prefer strict `formParameters(...)` and apply `.optional()` individually to fields that may be omitted.

### 6.4. Confusing absent fields, empty fields, and default values

Suppose the controller uses `@RequestParam(defaultValue = "basic") String plan`:

| Form body | Value of `plan` received by server (default Spring MVC binding) | Evaluation |
| --- | --- | --- |
| `email=mai%40example.com` | `basic` | `plan` is absent, default used |
| `email=mai%40example.com&plan=` | `basic` | `plan` is present but empty, default still used |
| `email=mai%40example.com&plan=plus` | `plus` | `plan` supplied by client |
| `email=mai%40example.com&plan=enterprise` | `enterprise` | Controller must reject it as invalid |

If the business requirement is "when the field is sent, it must never be empty", do not rely solely on `defaultValue`: that mechanism can turn an empty value into the default, erasing the distinction between the two cases. When exact differentiation is needed, design binding and validation accordingly and write tests for both **missing** and **empty**.

### 6.5. A single field name appearing multiple times

Form encoding allows:

```text
email=mai%40example.com&tag=java&tag=spring
```

A single `parameterWithName("tag")` descriptor documents the `tag` parameter name, whether it appears once or multiple times. If the server allows omitting all `tag` entries, mark the descriptor `.optional()`. If the server requires at least one tag, add separate validation and tests; `formParameters(...)` does not check value counts automatically.

### 6.6. Intentionally ignored fields

In a system with internal fields, you can use:

```java
formParameters(
    parameterWithName("email")
        .description("Registration email"),
    parameterWithName("trackingId")
        .ignored()
)
```

`trackingId` is still recognized for documentation validation, yet it does not appear in the snippet table. Only use `.ignored()` when there is a clear decision on publication scope; if public clients need to know about the parameter, document it rather than ignoring it.

## 7. What differs in WebTestClient and REST Assured?

With **WebTestClient** and **REST Assured**, the same principles still apply: send the exact form body, declare `formParameters(...)` in the documentation step, and verify the status/response. How the snippet is attached to the test changes by library.

### 7.1. WebTestClient

Assume `webTestClient` is configured with Spring REST Docs and a WebFlux handler is implemented to read form data:

```java
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

webTestClient.post()
    .uri("/registrations")
    .body(BodyInserters.fromFormData("email", "mai@example.com"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("registrations/webtestclient-minimal",
        formParameters(
            parameterWithName("email")
                .description("Required email"),
            parameterWithName("plan")
                .optional().description("Plan, defaults to basic"),
            parameterWithName("displayName")
                .optional().description("Display name"),
            parameterWithName("tag")
                .optional().description("Interest tag")
        )
    ));
```

`BodyInserters.fromFormData(...)` builds a URL-encoded form body. In Spring WebFlux, reading form data can use `ServerWebExchange.getFormData()` or an appropriate binding mechanism; do not assume a WebFlux handler reads a form body through `@RequestParam` identically to the Spring MVC controller in the previous example.

### 7.2. REST Assured

Assume an HTTP server is running and `specification` is configured with `RestAssuredRestDocumentation.documentationConfiguration(...)`:

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

given(specification)
    .filter(document("registrations/rest-assured-minimal",
        formParameters(
            parameterWithName("email")
                .description("Required email"),
            parameterWithName("plan")
                .optional().description("Plan, defaults to basic"),
            parameterWithName("displayName")
                .optional().description("Display name"),
            parameterWithName("tag")
                .optional().description("Interest tag")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "mai@example.com")
    .when().post("/registrations")
    .then().statusCode(201);
```

`formParam(...)` tells REST Assured to send form data, while `ContentType.URLENC` specifies `application/x-www-form-urlencoded`. Do not use `body("{...}")` with JSON and expect a matching form parameters table.

## 8. Including snippets in Asciidoctor/Markdown and CI pipelines

From the `fullFormRequestIsDocumented` test, Spring REST Docs generates `registrations/create-full/form-parameters.adoc` along with request and response snippets. In `src/docs/asciidoc/index.adoc`, you can include them:

```adoc
= Registration API

== Create registration

Send `Content-Type: application/x-www-form-urlencoded`.

=== Minimal request
include::{snippets}/registrations/create-minimal/http-request.adoc[]

=== Form fields
include::{snippets}/registrations/create-full/form-parameters.adoc[]

=== Successful response
include::{snippets}/registrations/create-full/http-response.adoc[]
```

In the code block above, adjust inline formatting markers according to the project's AsciiDoc conventions if needed; the `include::{snippets}/...[]` directives are the meaningful part. The `{snippets}` variable must point to the root directory of generated snippets, such as `build/generated-snippets`.

With Gradle Groovy DSL and a suitable Asciidoctor plugin, connect the steps:

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

Run in CI:

```bash
./gradlew test asciidoctor
```

When the server changes whether a field is required, update **both the behavioral tests and the documentation descriptors**. If tests fail, do not treat documentation from an older build as proof that the contract is still valid. The AsciiDoc `include::[]` directive is not automatically processed by standard Markdown renderers; when publishing Markdown, link to the HTML page generated by Asciidoctor or configure an explicit conversion step.

## 9. Comprehension exercise

Design a `POST /feedback` API that accepts a URL-encoded form with:

- `rating`: required, integer from 1 to 5.
- `comment`: optional, but if sent, must not consist solely of whitespace.
- `nickname`: optional, defaults to `anonymous` when absent.
- `category`: optional, parameter name may repeat to submit multiple items.

Perform the steps in order:

1. Create a controller with binding and validation that accurately implements the rules above.
2. Write tests for a full request and a minimal request; use `formParameters(...)` together with `parameterWithName(...)`/`.optional()` to generate both snippets.
3. Submit a form missing `rating` and verify the error response. Repeat with `rating=0`, `rating=abc`, `comment=+++`, and `comment=`; explain the differences between missing fields, invalid types, and empty values.
4. Try removing `.optional()` from `nickname` while running the minimal test; observe the Spring REST Docs error and restore the descriptor.
5. Add a parameter name not declared in the descriptors, compare `formParameters(...)` with `relaxedFormParameters(...)`, and explain why strict mode is usually preferred for public documentation.
6. Include the `form-parameters.adoc` table in Asciidoctor; configure CI to run tests before the documentation generation task.

**Self-check:** "A form field is optional" means **the server accepts the absence of that field under the API contract**. For reliable documentation, that must be reflected simultaneously in binding/validation configuration, HTTP tests, and Spring REST Docs' `.optional()`.

## References

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
