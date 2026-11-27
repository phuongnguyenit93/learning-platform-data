# Representing multi-part values in forms with Spring REST Docs

## 1. Context and objectives

In the **Form parameters** chapter of `SPRING_REST_DOCS`, an HTTP form does not necessarily consist only of single-valued fields. Users may select multiple tags, multiple permissions, multiple interests, or upload multiple attachments. When designing a REST API, how **multiple values** are represented determines how the server parses the request, how it is tested, and how Spring REST Docs generates documentation.

The phrase "multi-part values in a form" often causes confusion between two concepts:

1. **A form parameter with multiple values (multi-value parameter):** in an `application/x-www-form-urlencoded` body, the same **field name** is sent repeatedly, such as `topics=java&topics=spring`.
2. **A multipart request:** in a `multipart/form-data` body, data is split into multiple independent **parts**, each with its own headers and content; suitable for files and combined payloads. Multiple parts can also share the same name.

Both cases involve "multiple", yet they differ in HTTP structure and documentation approach. With Spring REST Docs, URL-encoded forms use `formParameters(...)`; multipart requests use `requestParts(...)`, combined with `requestPartFields(...)` when a part contains JSON.

The goal of this lesson is to produce REST API documentation **verifiable from HTTP tests** (MockMvc, WebTestClient, or REST Assured): testing requests/responses, payloads, parameters, and headers; generating snippets; embedding them into Asciidoctor/Markdown; and enforcing that documentation generation follows tests in CI.

## 2. A single form field name with multiple values

### 2.1. Wire model

Suppose an API saves user preferences. A user can select three topics simultaneously:

```http
POST /preferences HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

email=mai%40example.com&topics=java&topics=spring&topics=rest-docs
```

Here there are **two parameter names**: `email` and `topics`. However, `topics` appears **three times**, carrying three independent values. Visualized as a multi-value map:

```text
email  -> ["mai@example.com"]
topics -> ["java", "spring", "rest-docs"]
```

The corresponding data type in Spring is `MultiValueMap<String, String>`, rather than `Map<String, String>` which stores only one value per name.

Common cases:

| Requirement | URL-encoded form body | Note |
| --- | --- | --- |
| Select only one topic | `topics=java` | One name, one value |
| Select three topics | `topics=java&topics=spring&topics=rest-docs` | One name, three values |
| Select no topics | `topics` omitted | Field absent |
| Send an empty field | `topics=` | Name present with empty value; not equivalent to absent |
| Repeat the same value | `topics=java&topics=java` | Two duplicate values; the server must decide how to handle them |

Values on the wire are still strings. Java/Spring can convert them to `List<String>`, arrays, or sets, but **there is no default JSON array schema** embedded in a URL-encoded form.

### 2.2. Why not join strings with commas?

Compare:

```text
# Two separate values
topics=java&topics=spring

# A single value containing a comma
topics=java%2Cspring
```

In the second case, the data on the wire is a single value `java,spring`. Some Spring binding mechanisms may split strings on commas when converting to a collection type, depending on converters and configuration. However, that is a **server-side conversion rule**, not something that turns both HTTP forms into a universal contract. When the documentation specifies "repeat the `topics` name", clients should send the `topics=...&topics=...` format.

Similarly, the `topics[]=java&topics[]=spring` syntax produces an actual parameter name of `topics[]`. Square brackets **do not automatically turn** data into an array under a universal standard; only use them if the endpoint explicitly defines and tests that convention.

### 2.3. Values containing special characters

With `application/x-www-form-urlencoded`, every name and value must be properly encoded. Examples:

| Original value | Form-encoded value |
| --- | --- |
| `Spring REST Docs` | `Spring+REST+Docs` |
| `C++` | `C%2B%2B` |
| `A & B` | `A+%26+B` |
| `Đà Nẵng` | `%C4%90%C3%A0+N%E1%BA%B5ng` |

Spaces typically become `+`, while literal plus signs must become `%2B`. If you assemble a body by raw string concatenation without encoding, an `&` inside a value can be misinterpreted as the start of a new parameter. Use the HTTP client's form encoder and standardize on UTF-8 for Unicode data.

### 2.4. How HTML forms produce repeated fields

For example, users can select multiple checkboxes or multiple options in a `select`:

```html
<form action="/preferences" method="post" accept-charset="UTF-8">
  <label>
    Email
    <input name="email" type="email" required>
  </label>

  <label><input type="checkbox" name="topics" value="java"> Java</label>
  <label><input type="checkbox" name="topics" value="spring"> Spring</label>
  <label><input type="checkbox" name="topics" value="rest-docs"> REST Docs</label>

  <button type="submit">Save preferences</button>
</form>
```

Checked checkboxes can submit multiple `topics=...` pairs, each carrying the same name. An **unchecked** checkbox normally does not produce a corresponding parameter pair. When the client is required to submit at least one selection, that requirement must be enforced on the server; HTML validation only assists user experience.

## 3. Binding multiple values in Spring MVC

A simple endpoint allows 1–3 topics, each belonging to `java`, `spring`, `rest-docs`, `testing` with no duplicates:

```java
package example.docs;

import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/preferences")
public class PreferenceController {

    private static final Set<String> ALLOWED_TOPICS =
            Set.of("java", "spring", "rest-docs", "testing");

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> save(
            @RequestParam("email") String email,
            @RequestParam("topics") List<String> topics,
            @RequestParam(name = "note", required = false) String note) {

        if (email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (topics.isEmpty() || topics.size() > 3) {
            return ResponseEntity.badRequest().build();
        }
        if (topics.stream().anyMatch(topic -> !ALLOWED_TOPICS.contains(topic))) {
            return ResponseEntity.badRequest().build();
        }
        if (topics.stream().distinct().count() != topics.size()) {
            return ResponseEntity.badRequest().build();
        }

        // Learning example: a real application should save preferences via a service.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Explaining each choice:

- `@RequestParam("topics") List<String> topics` represents a single **parameter name** bound to multiple values. This is Spring MVC server-side binding; the client still sends name/value pairs in the HTTP body.
- `@RequestParam("topics")` by default requires the parameter to be present; a request without `topics` is normally rejected before reaching the controller.
- `topics.isEmpty()`, `topics.size() > 3`, the allowed-set check, and the uniqueness check enforce **business rules**. REST Docs does not verify them automatically.
- `@RequestParam(name = "note", required = false)` allows omitting the `note` field.
- The email check is kept simple for illustration; `contains("@")` is not a standard email validator for production applications.

To be certain how the server handles `topics=`, `topics=java,docs`, or a field name with square brackets, add tests matching the actual converter configuration. Do not infer behavior solely from the `List<String>` parameter type.

## 4. Documenting multiple values with `formParameters(...)`

### 4.1. One descriptor per parameter name

Spring REST Docs generates one description row for the **name** `topics`, whether the request has one or multiple values:

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

formParameters(
    parameterWithName("email")
        .description("Email address; required"),
    parameterWithName("topics")
                .description("Repeat the topics name to send 1–3 topics; " +
                "accepts only java, spring, rest-docs, testing; no duplicates"),
    parameterWithName("note")
        .optional()
        .description("Optional note")
)
```

**Do not write three separate descriptors with the same name `topics`** to describe `java`, `spring`, and `rest-docs`. A descriptor belongs to the field name, while valid values and repetition rules are explained in `description(...)`. Count, ordering, and value validity must be tested with assertions or business logic.

In strict mode, `formParameters(...)` checks the set of parameter names: a field present in the request without a descriptor causes an error; a required descriptor missing from the request also causes an error. `.optional()` permits missing the field name; `.ignored()` excludes a declared name from the output table; `relaxedFormParameters(...)` accepts undocumented names. None of these modes replace multi-value validation.

### 4.2. MockMvc test generating the snippet

Example using Spring Boot 3.x with Gradle Groovy DSL and the corresponding dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Complete test code for the controller above:

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

@WebMvcTest(PreferenceController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PreferenceDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void multipleValuesGenerateOneParameterDescriptor() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .characterEncoding("UTF-8")
                .param("email", "mai@example.com")
                .param("topics", "java", "spring", "rest-docs")
                .param("note", "Project-based learning"))
            .andExpect(status().isCreated())
            .andDo(document("preferences/multiple-topics",
                formParameters(
                    parameterWithName("email")
                        .description("Required email"),
                    parameterWithName("topics")
                        .description("List of 1–3 topics: " +
                                "java, spring, rest-docs, testing; repeat the topics name"),
                    parameterWithName("note")
                        .optional()
                        .description("Optional note")
                )
            ));
    }

    @Test
    void singleTopicAndOmittedNoteAreValid() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("topics", "java"))
            .andExpect(status().isCreated());
    }

    @Test
    void missingTopicsAreRejected() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void duplicateTopicsAreRejected() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("topics", "java", "java"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownTopicIsRejected() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("topics", "java", "unknown"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void tooManyTopicsAreRejected() throws Exception {
        mockMvc.perform(post("/preferences")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("topics", "java", "spring", "rest-docs", "testing"))
            .andExpect(status().isBadRequest());
    }
}
```

Workflow and results:

1. `.param("topics", "java", "spring", "rest-docs")` adds multiple values for the same `topics` name in the MockMvc request.
2. The `Content-Type: application/x-www-form-urlencoded` header identifies the form content. If real-world requests come from another client, inspect `http-request.adoc` to confirm the actual body is encoded properly.
3. `.andExpect(status().isCreated())` verifies that a valid request is accepted by the server.
4. `.andDo(document(..., formParameters(...)))` generates `form-parameters.adoc` for `email`, `topics`, and `note`.
5. The error tests prove that the server rejects duplicate values, unlisted values, excess count, or missing required fields. **Spring REST Docs cannot infer these rules from descriptors alone.**

If tests use Spring Security with CSRF, POST requests require a CSRF token or appropriate test security configuration. The examples assume the controller has no extra service dependencies; if it does, mock those dependencies or use an appropriate slice test configuration.

### 4.3. Snippet output

When the documentation test succeeds, the corresponding files typically reside at:

```text
build/generated-snippets/
└── preferences/
    └── multiple-topics/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
```

The informational table of `form-parameters.adoc` looks like:

| Parameter | Description |
| --- | --- |
| `email` | Required email |
| `topics` | List of 1–3 topics: java, spring, rest-docs, testing; repeat the topics name |
| `note` | Optional note |

You will see **a single `topics` row** even though the test request sent three values. To show readers the full syntax of a repeated-name request, also include `http-request.adoc` or `curl-request.adoc`. Do not manually edit generated snippets to list individual values; clarify the semantics in `description(...)` and the HTTP fixture instead.

## 5. Representing multiple values with WebTestClient and REST Assured

Spring REST Docs shares the same `formParameters(...)` API across testing approaches, but each HTTP client has its own syntax for sending repeated values.

### 5.1. WebTestClient: `MultiValueMap`

This example assumes `webTestClient` is configured with Spring REST Docs, the WebFlux endpoint handles form bodies, and a successful request returns `201`:

```java
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("email", "mai@example.com");
form.add("topics", "java");
form.add("topics", "spring");
form.add("topics", "rest-docs");

webTestClient.post()
    .uri("/preferences")
    .body(BodyInserters.fromFormData(form))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("preferences/webtestclient",
        formParameters(
            parameterWithName("email").description("Required email"),
            parameterWithName("topics")
                .description("Repeatable topic, 1–3 values")
        )
    ));
```

`MultiValueMap.add(...)` appends a new value **without overwriting** existing values under the same key. `BodyInserters.fromFormData(form)` builds a URL-encoded form. In WebFlux, handlers typically receive form data via `ServerWebExchange.getFormData()` or an appropriate binding; do not assume identical parameter-source rules as Spring MVC's Servlet `@RequestParam`.

### 5.2. REST Assured: multiple arguments to `formParam`

This example assumes a running server and `specification` configured with `RestAssuredRestDocumentation.documentationConfiguration(...)`:

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(specification)
    .filter(document("preferences/rest-assured",
        formParameters(
            parameterWithName("email").description("Required email"),
            parameterWithName("topics")
                .description("Repeatable topic, 1–3 values")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "mai@example.com")
    .formParam("topics", "java", "spring", "rest-docs")
    .when().post("/preferences")
    .then().statusCode(201);
```

`ContentType.URLENC` specifies a URL-encoded form. `formParam("topics", ...)` provides multiple values under the same name; check `http-request.adoc` or log the HTTP request in tests to confirm the client sends repeated-name form data accurately. Avoid `body("[...]")` or JSON when the API contract requires a form body.

## 6. Distinguishing repeated form values from `multipart/form-data`

### 6.1. Multipart consists of parts with their own headers

If an API handles file attachments or complex payloads, use the `multipart/form-data` media type. The body is delimited by a `boundary` string generated by the HTTP client. Simplified illustration:

```http
POST /uploads HTTP/1.1
Content-Type: multipart/form-data; boundary=FormBoundary123

--FormBoundary123
Content-Disposition: form-data; name="title"

Course materials
--FormBoundary123
Content-Disposition: form-data; name="files"; filename="lesson-a.txt"
Content-Type: text/plain

Content A
--FormBoundary123
Content-Disposition: form-data; name="files"; filename="lesson-b.txt"
Content-Type: text/plain

Content B
--FormBoundary123--
```

A multipart request has multiple **parts**; in the example, the name `files` appears in two separate parts. Each part can carry binary, text, or JSON content along with metadata such as `Content-Type`/`filename`. This is not the `files=a&files=b` string of a URL-encoded form. Actual line endings in HTTP multipart follow CRLF; the example simplifies byte details for readability.

| Characteristic | Repeated URL-encoded form values | Multipart form |
| --- | --- | --- |
| Content-Type | `application/x-www-form-urlencoded` | `multipart/form-data; boundary=...` |
| Structure | `name=value` pairs, names may repeat | Multiple parts, each with its own headers |
| Best suited for | Short strings, checkboxes, multi-select inputs | File uploads, mixed files and metadata |
| Documenting with REST Docs | `formParameters(parameterWithName(...))` | `requestParts(partWithName(...))` |
| When a part contains JSON | Not applicable as a JSON part | Can additionally use `requestPartFields(...)` |

### 6.2. Server receiving multiple files under one name

An illustrative Spring MVC controller:

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
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/uploads")
public class UploadController {

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Void> upload(
            @RequestParam("files") List<MultipartFile> files) {

        if (files.isEmpty() || files.size() > 2 ||
                files.stream().anyMatch(MultipartFile::isEmpty)) {
            return ResponseEntity.badRequest().build();
        }
        // Example: file storage or content scanning omitted.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Use `List<MultipartFile>` for the shared `files` name. A real endpoint needs size limits, format checks, filename handling, security checks, and storage logic. Those conditions are not automatically verified by REST Docs.

### 6.3. Documenting multipart with `requestParts(...)`

Assume `mockMvc` is configured with Spring REST Docs for `UploadController`:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.mock.web.MockMultipartFile;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

MockMultipartFile first = new MockMultipartFile(
    "files", "lesson-a.txt", "text/plain",
    "Content A".getBytes(StandardCharsets.UTF_8));

MockMultipartFile second = new MockMultipartFile(
    "files", "lesson-b.txt", "text/plain",
    "Content B".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/uploads").file(first).file(second))
    .andExpect(status().isCreated())
    .andDo(document("uploads/multiple-files",
        requestParts(
            partWithName("files")
                .description("1 to 2 files; send multiple parts with the name files")
        )
    ));
```

This generates `request-parts.adoc`, where `files` has a single contract description. `requestParts` verifies the **documented part names**, not that exactly two files exist, that files are non-empty, or that their `Content-Type` is valid; those belong in separate validation and tests. If a part contains structured JSON, you can add `requestPartFields("metadata", fieldWithPath("version").description(...))` to generate a dedicated snippet for the `metadata` part's contents; the corresponding JSON part must be sent in the test request.

**Note:** do not use `formParameters(...)` in place of `requestParts(...)` to document uploaded files. If a multipart request also contains text fields, choose the documentation approach based on whether the data is sent as a parameter or a request part in the actual request and verify the generated snippet.

## 7. Including snippets in documentation and CI

For the URL-encoded form test in Section 4, an Asciidoctor page can include:

```adoc
= Preferences API

== Submitting multiple topics of interest

=== HTTP request with repeated form name
include::{snippets}/preferences/multiple-topics/http-request.adoc[]

=== Form parameters
include::{snippets}/preferences/multiple-topics/form-parameters.adoc[]

=== HTTP response
include::{snippets}/preferences/multiple-topics/http-response.adoc[]

== Uploading multiple files

=== Multipart request
include::{snippets}/uploads/multiple-files/http-request.adoc[]

=== Parts
include::{snippets}/uploads/multiple-files/request-parts.adoc[]
```

The `{snippets}` variable must point to the root snippets directory, such as `build/generated-snippets`. The `include::{snippets}/...[]` directive belongs to Asciidoctor, not default Markdown features. If the output must be Markdown, link to the compiled HTML or add a controlled conversion step.

In Gradle Groovy DSL with the Asciidoctor plugin installed:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
```

In CI:

```bash
./gradlew test asciidoctor
```

The pipeline should verify that tests pass, snippets are generated at the expected paths, and the final documentation renders. When the server changes from "single value" to "multiple values" or from URL-encoded to multipart, update fixtures, validation, descriptors, and HTTP examples; never edit generated `.adoc` files manually.

## 8. Common errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Server only receives the last item | Client/map overwrites values for the same key | Use a multi-value mechanism (`MultiValueMap.add`, varargs `.param`) and verify the HTTP body |
| API expects repeated name, client sends `topics=java,spring` | Confused comma-separated string with repeated fields | Send `topics=java&topics=spring` per the contract |
| Sees `topics[]` but cannot bind `topics` | Actual field names differ | Align field names across controller and descriptors, or configure binding intentionally |
| REST Docs shows only one `topics` row | Snippet describes the parameter name, not individual values | Explain repetition rules in the description and include sample HTTP requests |
| Snippet test passes but list has duplicate values | REST Docs does not validate count or uniqueness | Add validation and business error tests |
| `+` lost or `&` splits values incorrectly | Manual form encoding | Use an encoder, UTF-8, and inspect the raw request |
| Upload request sent as URL-encoded | Confused repeated text values with file parts | Use `multipart/form-data` and `requestParts(...)` |
| Multipart uses `formParameters` without documenting files | Chose the wrong snippet type | Use `requestParts(partWithName(...))`; add `requestPartFields` for structured JSON payloads |
| Asciidoctor page cannot find snippet | Tests have not run, wrong identifier, or missing `{snippets}` variable | Make documentation build depend on `test` and check actual output paths |

Do not use real passwords, tokens, or personal data in fixtures; `http-request.adoc` snippets can expose request values in published documentation. For uploads, use only dummy files and never emit sensitive content in examples.

## 9. Practice exercise

Design two endpoints to verify the difference:

**Exercise A — URL-encoded multi-value:** `POST /enrollments` accepts a required `studentId` and `courses` repeated 1–4 times; courses must belong to `java`, `sql`, `git`, `testing` with no duplicates.

1. Write a controller accepting `List<String> courses` along with the business rules.
2. Write a MockMvc test sending `courses=java&courses=git`, generating `form-parameters.adoc` with **one** descriptor named `courses`.
3. Write tests for missing `courses`, duplicate `courses`, and more than four values. Observe that behavioral tests, not descriptors, catch these errors.
4. Use WebTestClient `MultiValueMap` or REST Assured `formParam` to send an equivalent request and compare HTTP snippets.

**Exercise B — multipart:** `POST /assignments` accepts one to two files under the shared name `attachments`, enforcing file/size limits you define.

1. Send two `MockMultipartFile` instances named `attachments` via `multipart(...)`.
2. Generate `request-parts.adoc` with `requestParts(partWithName("attachments")...)`.
3. Try adding a JSON metadata part and documenting its fields with `requestPartFields(...)`.
4. Build an Asciidoctor page containing request examples and both appropriate tables; place tests before documentation rendering in CI.

**Pass criteria:** you accurately distinguish when a **parameter has multiple values** versus when a **request has multiple parts**; clients send the proper wire format; the server validates counts/values; Spring REST Docs snippets are generated from HTTP tests and automatically assembled into documentation.

## References

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
- [Spring Framework — Multipart Forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
