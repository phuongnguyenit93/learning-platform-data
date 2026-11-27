# Distinguishing form parameters from JSON request bodies in Spring REST Docs

## 1. Same business data, two different HTTP contracts

In the **Form parameters** chapter of the **SPRING_REST_DOCS** module, a key question is: how does an API receiving form data via `application/x-www-form-urlencoded` differ from an API receiving a JSON object via `application/json`? The difference determines how clients package data, how Spring reads the request, how HTTP tests are written, and which snippet type **Spring REST Docs** can generate.

This module focuses on generating REST API documentation **verifiable by tests** with MockMvc, WebTestClient, or REST Assured. Snippets are produced from requests, responses, payloads, parameters, and headers in tests, and then included in Asciidoctor/Markdown documentation and the build/CI pipeline. If you document the wrong payload type or pick the wrong snippet, the documentation can mislead API consumers even when field names look identical.

Consider the same account registration operation with an email, plan, and note:

**Request sent as a URL-encoded form:**

```http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept: application/json

email=mai%40example.com&plan=pro&note=Hello
```

**Request sent as JSON:**

```http
POST /registrations HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "email": "mai@example.com",
  "plan": "pro",
  "note": "Hello"
}
```

The two requests share the same business meaning yet are **not arbitrarily interchangeable**: body structure, media type, decoder, data types, and documentation mechanism differ. An endpoint may accept both if declared and tested separately, or support only one format.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish form parameters in an HTTP body, JSON fields, and query parameters in a URL.
2. Explain how Spring MVC binds data via `@RequestParam` and `@RequestBody`.
3. Choose appropriately between `formParameters(parameterWithName(...))` and `requestFields(fieldWithPath(...))`.
4. Write tests verifying valid requests, missing data, invalid data, and incompatible media types.
5. Include both snippet sets in documentation so readers know exactly which request format to send.

## 2. Comparing HTTP structure and data types

| Criterion | URL-encoded form | JSON request body |
| --- | --- | --- |
| Request `Content-Type` | `application/x-www-form-urlencoded` | `application/json` |
| Structure | `name=value&name=value` | Object, array, string, number, boolean, `null` |
| Data location | HTTP body | HTTP body |
| Space encoding in examples | `+` | Literal space character inside JSON string |
| Special character encoding | Percent-encoding by charset bytes | Characters inside JSON string, escaped if needed |
| Multiple values for one name | Can repeat `topic=java&topic=spring` | Typically uses an array `"topic":["java","spring"]` |
| Numeric/boolean values | Strings on the wire, converted by the server | JSON has native number/boolean types |
| Null | No standard `null` type in form encoding | Has the `null` literal |
| Nested objects | No universal standard representation | Supports nested objects |
| Typical Spring MVC usage | `@RequestParam` or form/model binding | `@RequestBody` with HTTP message converter |
| REST Docs body documentation | `formParameters(...)` | `requestFields(...)` |

**Both URL-encoded forms and JSON reside in the HTTP body**, so saying "a form is a parameter while JSON is a request body" is not entirely accurate. The real difference lies in **how data is represented and extracted from the body**.

### 2.1. Form encoding vs. JSON

With a URL-encoded form, name/value pairs are joined by `&` and separated by `=`:

```text
email=mai%40example.com&note=C%2B%2B+%26+Java
```

After decoding, `email` is `mai@example.com` and `note` is `C++ & Java`. In a URL-encoded form, spaces are typically represented as `+`, literal plus signs as `%2B`, and `&` inside values as `%26`.

With JSON, standard JSON literal syntax is used:

```json
{
  "email": "mai@example.com",
  "note": "C++ & Java"
}
```

`+` and `&` inside JSON strings carry no parameter-delimiting meaning. In particular, **never use a form encoder to encode an entire JSON string**, and never send JSON while declaring `Content-Type: application/x-www-form-urlencoded`.

### 2.2. Query parameters are a separate concept

Example URL with a query parameter:

```http
POST /registrations?source=campaign HTTP/1.1
Content-Type: application/json

{"email":"mai@example.com","plan":"pro"}
```

Here `source` belongs to the **URL query string** and requires `queryParameters(...)`; `email` and `plan` belong to the **JSON body** and require `requestFields(...)`. A request can also combine query parameters with a form body; do not choose `formParameters(...)` solely because Spring MVC can bind both query and form data via `@RequestParam`.

### 2.3. `Content-Type` header vs. `Accept`

`Content-Type` describes **the body of the current message itself**. In a request, it tells the server whether the client is sending a form or JSON. `Accept` describes **the response format the client wants to receive**. Therefore, a request can submit a form while expecting a JSON response:

```http
Content-Type: application/x-www-form-urlencoded
Accept: application/json
```

When documenting an API, tests should clearly specify both the request media type and the response format. If the controller uses `consumes`/`produces`, Spring can return `415 Unsupported Media Type` or `406 Not Acceptable` when a request fails to satisfy the corresponding constraint.

## 3. Distinguishing missing, empty, null, and array fields

### 3.1. For an optional field

| Client intent | URL-encoded form example | JSON example |
| --- | --- | --- |
| Omit `note` | `email=mai%40example.com` | `{"email":"mai@example.com"}` |
| Send empty string | `email=mai%40example.com&note=` | `{"email":"mai@example.com","note":""}` |
| Send null | No standard null literal | `{"email":"mai@example.com","note":null}` |
| Send the string `"null"` | `note=null` (four-character string) | `{"note":"null"}` (four-character string) |

In Spring MVC, when `@RequestParam(required = false)` receives an absent field, the value is typically `null` unless a default or custom converter is configured. `@RequestParam(defaultValue = "basic")` can apply the default value when the parameter is absent **or empty**. With JSON, `@RequestBody` usually deserializes objects using Jackson; an absent property and a `null` property may both map to `null` on a reference DTO field, though an application can still distinguish them via appropriate models, validation, or parsers if required.

Consequently, an API accepting both form and JSON inputs must **explicitly specify whether they share one business contract or follow two different rule sets**. Do not infer optionality and default rules solely from the snippet type.

### 3.2. For multi-valued lists

URL-encoded forms typically repeat the parameter name:

```text
topics=java&topics=spring
```

JSON has a native array type:

```json
{
  "topics": ["java", "spring"]
}
```

In REST Docs, the form is documented with **one** `parameterWithName("topics")` whose description explains that the name may repeat. A JSON array is typically documented with `fieldWithPath("topics")`, and inner paths within objects/arrays can be documented further if the schema is complex. The syntax `topics=java,spring` in a form creates a single comma-containing string on the wire; whether the server splits it into a list depends on converters and the specific contract.

### 3.3. Nested objects

JSON represents nested structures naturally:

```json
{
  "email": "mai@example.com",
  "profile": {
    "city": "Hà Nội",
    "notifications": true
  }
}
```

Spring REST Docs can document subfields `profile.city` and `profile.notifications` with `fieldWithPath(...)`. For URL-encoded forms, an application might invent a naming convention such as `profile.city=Ha+Noi`, but that is an **application-specific binding convention**, not a nested JSON object in the HTTP body.

## 4. Spring MVC: handling both media types on the same URL

The following example shows two `POST /registrations` handlers that both return `201 Created` and a JSON response. Spring MVC selects the handler based on the request's `Content-Type` using `consumes`.

### 4.1. DTOs for JSON and response

```java
package example.docs;

public record RegistrationRequest(
        String email,
        String plan,
        String note) {
}
```

```java
package example.docs;

public record RegistrationResponse(
        String id,
        String email,
        String plan) {
}
```

To stay focused on documentation, the example uses Java records (Java 17+) without a database connection. The fixed `id` field `reg-demo` is purely illustrative test data; a real system would generate an ID and persist the registration.

### 4.2. Controller with `@RequestParam` and `@RequestBody`

```java
package example.docs;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    @PostMapping(
        path = "/registrations",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<RegistrationResponse> fromForm(
            @RequestParam("email") String email,
            @RequestParam(name = "plan", defaultValue = "basic") String plan,
            @RequestParam(name = "note", required = false) String note) {

        return register(email, plan, note);
    }

    @PostMapping(
        path = "/registrations",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<RegistrationResponse> fromJson(
            @RequestBody RegistrationRequest request) {

        // With JSON, the plan field may be absent or null.
        String plan = request.plan() == null || request.plan().isBlank()
                ? "basic"
                : request.plan();

        return register(request.email(), plan, request.note());
    }

    private ResponseEntity<RegistrationResponse> register(
            String email, String plan, String note) {

        // Minimal validation to clarify test branches.
        if (email == null || email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (!plan.equals("basic") && !plan.equals("pro")) {
            return ResponseEntity.badRequest().build();
        }

        RegistrationResponse result =
                new RegistrationResponse("reg-demo", email, plan);
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}
```

Contract notes:

- `fromForm(...)` uses `@RequestParam` to extract form parameter pairs. `email` is required at the binding layer; `plan` defaults to `basic`; `note` may be absent.
- `fromJson(...)` uses `@RequestBody` to trigger reading the full JSON body via an appropriate `HttpMessageConverter` (typically Jackson in Spring Boot). An absent `email` property is not automatically enforced as required just because the DTO declares `String email`; `register(...)` rejects `null`.
- Both branches share `register(...)`, keeping email and plan rules consistent. Setting the `basic` default in the JSON branch is **application logic**, not a feature of `requestFields(...).optional()`.
- `email.contains("@")` is an illustrative check only, not production email validation. Real applications need Bean Validation or appropriate validation rules.
- `note` is not persisted; if you need to distinguish `null`, empty strings, and concrete values, implement corresponding handling and tests.
- When an application only intends to support one body format, keep only one `consumes` mapping; do not add a second handler merely for documentation.

## 5. Choosing the right Spring REST Docs API for each body

### 5.1. URL-encoded form: `formParameters`

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

formParameters(
    parameterWithName("email")
        .description("Registration email; required and non-empty"),
    parameterWithName("plan")
        .optional()
        .description("basic or pro; defaults to basic"),
    parameterWithName("note")
        .optional()
        .description("Optional note")
)
```

The `parameterWithName("email")` descriptor documents a **parameter name in the form**. Under strict mode, if the request contains an undocumented form name or lacks a required descriptor, snippet generation fails. `.optional()` allows that parameter to be absent in the documented request; it does not alter `@RequestParam` or validate the email format.

The generated snippet is named **`form-parameters.adoc`**.

### 5.2. JSON: `requestFields`

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

requestFields(
    fieldWithPath("email")
        .description("Registration email; required and non-empty"),
    fieldWithPath("plan")
        .optional()
        .description("basic or pro; defaults to basic"),
    fieldWithPath("note")
        .optional()
        .description("Optional note")
)
```

The `fieldWithPath("email")` descriptor documents a **field path in the JSON payload**. When JSON contains nested objects or arrays, you can declare paths such as `profile.city` or `items[].sku` according to the actual schema. `.optional()` on a payload descriptor permits the field to be absent; it does **not** make the DTO property optional on its own, nor does it apply a default value.

The generated snippet is named **`request-fields.adoc`**.

### 5.3. Comparing contract checks

| Scenario | Form `formParameters` | JSON `requestFields` |
| --- | --- | --- |
| Request adds undocumented `debug` name | Strict mode reports undocumented form parameter | Strict mode reports undocumented JSON field |
| `email` missing from documented request | Default required descriptor causes snippet error | Default required `fieldWithPath("email")` causes snippet error |
| `note` marked `.optional()` and omitted | Snippet check passes | Snippet check passes |
| Malformed `email` content | Requires separate validation/tests | Requires separate validation/tests |
| Multiple values | Documents one repeatable form parameter name | Documents a JSON array and element paths if needed |
| Nested objects | Requires custom application binding convention | Uses nested paths directly understood by the JSON parser |

**Quick rule of thumb:** `parameterWithName(...)` describes *parameter names*; `fieldWithPath(...)` describes *field paths in a payload*. Do not use `formParameters` for JSON bodies or `requestFields` for URL-encoded forms simply because both share the same property names.

## 6. MockMvc: one test suite, two snippet types

Example based on Spring Boot 3.x with Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

This assumes the project already uses dependency management providing a compatible Spring REST Docs version. When Spring Security enables CSRF, POST requests in tests must supply valid CSRF configuration.

### 6.1. Two main tests generating the corresponding snippets

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
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationFormatDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentUrlEncodedForm() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(MediaType.APPLICATION_JSON)
                .characterEncoding("UTF-8")
                .param("email", "mai@example.com")
                .param("plan", "pro")
                .param("note", "Hello"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("reg-demo"))
            .andExpect(jsonPath("$.plan").value("pro"))
            .andDo(document("registrations/form",
                requestHeaders(
                    headerWithName("Content-Type")
                        .description("application/x-www-form-urlencoded")
                ),
                formParameters(
                    parameterWithName("email")
                        .description("Registration email; required"),
                    parameterWithName("plan")
                        .optional().description("basic or pro; defaults to basic"),
                    parameterWithName("note")
                        .optional().description("Note")
                ),
                responseFields(
                    fieldWithPath("id").description("Registration ID"),
                    fieldWithPath("email").description("Registered email"),
                    fieldWithPath("plan").description("Applied plan")
                )
            ));
    }

    @Test
    void documentJsonRequest() throws Exception {
        String json = """
                {
                  "email": "mai@example.com",
                  "plan": "pro",
                  "note": "Hello"
                }
                """;

        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(json))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("reg-demo"))
            .andExpect(jsonPath("$.plan").value("pro"))
            .andDo(document("registrations/json",
                requestHeaders(
                    headerWithName("Content-Type")
                        .description("application/json")
                ),
                requestFields(
                    fieldWithPath("email")
                        .description("Registration email; required"),
                    fieldWithPath("plan")
                        .optional().description("basic or pro; defaults to basic"),
                    fieldWithPath("note")
                        .optional().description("Note")
                ),
                responseFields(
                    fieldWithPath("id").description("Registration ID"),
                    fieldWithPath("email").description("Registered email"),
                    fieldWithPath("plan").description("Applied plan")
                )
            ));
    }

    @Test
    void formWithoutOptionalFieldsUsesDefaultPlan() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.plan").value("basic"));
    }

    @Test
    void jsonWithoutOptionalFieldsUsesDefaultPlan() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"mai@example.com"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.plan").value("basic"));
    }

    @Test
    void formWithoutEmailIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("plan", "pro"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void jsonWithoutEmailIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"plan":"pro"}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedMediaTypeIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.TEXT_PLAIN)
                .content("email=mai@example.com"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void malformedJsonIsRejected() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{email:"))
            .andExpect(status().isBadRequest());
    }
}
```

### 6.2. Analysis of testing techniques

**Form request:** `.contentType(APPLICATION_FORM_URLENCODED)` specifies the media type; `.param(...)` adds parameters to the MockMvc request. For URL-encoded POSTs, MockMvc represents parameters as a form body. Inspect `http-request.adoc` to confirm the documented bytes/request match real clients.

**JSON request:** `.contentType(APPLICATION_JSON)` sets the media type; `.content(json)` sends the **JSON string in the body**. `.param("email", ...)` does not substitute for a JSON body; misusing `.param(...)` can prevent `@RequestBody` from reading the expected object.

**Response:** both handlers return the same JSON structure, so both document `responseFields(...)`. Response data can remain identical even when request formats differ.

**Negative tests:** `formWithoutEmailIsRejected` and `jsonWithoutEmailIsRejected` confirm that the server rejects the same error across both binding mechanisms; `malformedJsonIsRejected` checks JSON syntax errors; `unsupportedMediaTypeIsRejected` sends `text/plain` so neither `consumes` handler matches.

**Limitation of snippet tests:** `formParameters(...)`/`requestFields(...)` verify structural descriptions, not whether an email is valid, `plan` is in the allowed set, or default values work. Those require assertions like `jsonPath("$.plan").value("basic")` and invalid-input tests.

### 6.3. Output structure

After both tests with `document(...)` succeed:

```text
build/generated-snippets/
└── registrations/
    ├── form/
    │   ├── form-parameters.adoc
    │   ├── request-headers.adoc
    │   ├── response-fields.adoc
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── json/
        ├── request-fields.adoc
        ├── request-headers.adoc
        ├── response-fields.adoc
        ├── http-request.adoc
        └── http-response.adoc
```

The two request pages have two **different** table types:

| Request type | Request structure snippet | Example names/fields |
| --- | --- | --- |
| URL-encoded form | `registrations/form/form-parameters.adoc` | `email`, `plan`, `note` |
| JSON | `registrations/json/request-fields.adoc` | `email`, `plan`, `note` |

Because field names match while body types differ, assign distinct snippet identifiers such as `registrations/form` and `registrations/json`. Never reuse the same identifier across two tests generating different documentation, as output files may overwrite each other and break accurate cross-referencing.

## 7. WebTestClient: sending forms and JSON properly

The following examples assume `webTestClient` is configured with `WebTestClientRestDocumentation.documentationConfiguration(...)` and corresponding WebFlux handlers support both form and JSON. Reading form data in WebFlux typically uses `ServerWebExchange.getFormData()` or an appropriate binding; do not assume Spring MVC's `@RequestParam` pattern can simply be copied to WebFlux handlers.

### 7.1. URL-encoded form with `BodyInserters.fromFormData`

```java
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

webTestClient.post()
    .uri("/registrations")
    .body(BodyInserters.fromFormData("email", "mai@example.com")
        .with("plan", "pro")
        .with("note", "Hello"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("registrations/webtestclient-form",
        formParameters(
            parameterWithName("email").description("Required email"),
            parameterWithName("plan").optional()
                .description("basic or pro; defaults to basic"),
            parameterWithName("note").optional()
                .description("Note")
        )
    ));
```

`BodyInserters.fromFormData(...)` creates a URL-encoded form with the appropriate content type. If a name has multiple values, use `MultiValueMap<String, String>`/`LinkedMultiValueMap` and append values with `add(...)`.

### 7.2. JSON with `bodyValue` and `requestFields`

```java
import org.springframework.http.MediaType;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

webTestClient.post()
    .uri("/registrations")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new RegistrationRequest("mai@example.com", "pro", "Hello"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .consumeWith(document("registrations/webtestclient-json",
        requestFields(
            fieldWithPath("email").description("Required email"),
            fieldWithPath("plan").optional()
                .description("basic or pro; defaults to basic"),
            fieldWithPath("note").optional()
                .description("Note")
        )
    ));
```

`bodyValue(...)` requires a JSON encoder configured in WebTestClient. If you want to verify the exact serialized JSON, inspect `http-request.adoc` and add specific assertions. Even when using the same `RegistrationRequest` class, the WebFlux handler must still be written to read a JSON body appropriately.

## 8. REST Assured: `formParam` vs. JSON `body`

REST Assured typically runs against a live HTTP server. Assume `specification` is configured with `RestAssuredRestDocumentation.documentationConfiguration(...)` and the server is listening on the endpoint.

**Form:**

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

given(specification)
    .filter(document("registrations/rest-assured-form",
        formParameters(
            parameterWithName("email").description("Required email"),
            parameterWithName("plan").optional()
                .description("Plan, defaults to basic"),
            parameterWithName("note").optional()
                .description("Note")
        )))
    .contentType(ContentType.URLENC)
    .formParam("email", "mai@example.com")
    .formParam("plan", "pro")
    .formParam("note", "Hello")
    .when().post("/registrations")
    .then().statusCode(201);
```

**JSON:**

```java
import io.restassured.http.ContentType;

import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

String json = """
    {"email":"mai@example.com","plan":"pro","note":"Hello"}
    """;

given(specification)
    .filter(document("registrations/rest-assured-json",
        requestFields(
            fieldWithPath("email").description("Required email"),
            fieldWithPath("plan").optional()
                .description("Plan, defaults to basic"),
            fieldWithPath("note").optional()
                .description("Note")
        )))
    .contentType(ContentType.JSON)
    .body(json)
    .when().post("/registrations")
    .then().statusCode(201);
```

In REST Assured, `formParam(...)` with `ContentType.URLENC` creates form data, while `body(...)` with `ContentType.JSON` sends JSON. Do not use `formParam(...)` to represent JSON fields. If the client uses custom serializer settings, inspect the request snippet to confirm the actual structure.

## 9. Including both request types in Asciidoctor/Markdown

Clear documentation must state whether the API supports both formats or only one, and provide separate examples. Example `src/docs/asciidoc/index.adoc` page:

```adoc
= Registrations API

== Create registration

The POST /registrations endpoint accepts two request body formats:
application/x-www-form-urlencoded and application/json.
A successful response is JSON.

=== Option 1: URL-encoded form

==== HTTP request
include::{snippets}/registrations/form/http-request.adoc[]

==== Request Content-Type
include::{snippets}/registrations/form/request-headers.adoc[]

==== Form parameters
include::{snippets}/registrations/form/form-parameters.adoc[]

=== Option 2: JSON body

==== HTTP request
include::{snippets}/registrations/json/http-request.adoc[]

==== Request Content-Type
include::{snippets}/registrations/json/request-headers.adoc[]

==== JSON fields
include::{snippets}/registrations/json/request-fields.adoc[]

=== JSON response

include::{snippets}/registrations/json/http-response.adoc[]
include::{snippets}/registrations/json/response-fields.adoc[]
```

The `{snippets}` variable must point to the root snippets directory, such as `build/generated-snippets`. Generated files serve as the **documentation source**, so never manually edit `form-parameters.adoc` or `request-fields.adoc` after running tests.

### 9.1. Connecting tests to Asciidoctor in Gradle

Assume the Asciidoctor plugin is already added to the build (Groovy DSL):

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

CI can run:

```bash
./gradlew test asciidoctor
```

When tests fail because a body or descriptor no longer matches, the pipeline should not publish documentation pages built from stale snippets. Verify both the output HTML file and the presence of the included sections, rather than trusting a snippets directory left over from a previous build.

### 9.2. When the main documentation uses Markdown

The `include::{snippets}/...[]` directive is **Asciidoctor syntax**, not an include syntax supported by default in Markdown renderers. You can compile Asciidoctor to HTML and link to it from Markdown pages, or add a conversion step and verify the output. What matters is that table contents still originate from HTTP tests.

## 10. Common errors and fixes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Endpoint returns `415` | Media type does not match `consumes` | Check `Content-Type` and supported handlers |
| Endpoint returns `400` on JSON submission | Malformed JSON syntax, missing data, or binding/validation rejection | Inspect actual JSON, `@RequestBody`, DTO, and parse errors |
| JSON sent with valid field names but server reports missing parameter | Calling a `@RequestParam`/form handler without appropriate binding | Use the matching media type/handler or add a JSON mapping |
| Form sent with `.param(...)` but `@RequestBody` cannot read JSON | Form body differs from JSON body | Use `.content(...)` with `application/json` for JSON APIs |
| `formParameters` cannot document JSON | Chose the API for the wrong payload type | Switch to `requestFields(fieldWithPath(...))` |
| `requestFields` reports inability to parse form | Body is not a JSON object | Choose `formParameters(parameterWithName(...))` |
| Client sends `A+B` but server receives `A B` | `+` in forms is interpreted as a space | Encode literal plus signs as `%2B` |
| JSON has an array but documentation test only describes form fields | Confused JSON list with repeated form names | Document `fieldWithPath("topics")` with schema and test the JSON array |
| `plan` documented as optional but server rejects omission | `.optional()` descriptor does not modify the controller | Align binding, default logic, and behavioral tests |
| Two tests share the same `document(...)` identifier | Risk of overwriting or mixing snippets | Use distinct identifiers per format, such as `registrations/form` and `registrations/json` |
| Asciidoctor cannot find snippet | Tests did not run first or `{snippets}` points to the wrong path | Make `asciidoctor` depend on `test` and verify paths |

**Test data:** `http-request.adoc` and `curl-request.adoc` snippets can display the entire body. Use only dummy emails, tokens, and content; never include real personal data, passwords, or secrets in published fixtures.

## 11. Practice exercise

Build `POST /feedback` accepting **both** body formats:

- For URL-encoded form: `rating` required; `comment` optional; `tags` name may repeat.
- For JSON: object with `rating` (number), `comment` (optional string), `tags` (optional string array).
- The server requires `rating` to be within 1–5; if `tags` is present, each item may only be `bug`, `feature`, or `docs`.

Steps:

1. Create two separate `consumes` handlers on the same path using `@RequestParam` and `@RequestBody` appropriately.
2. Write a MockMvc form test with `tags=bug&tags=docs`; generate `form-parameters.adoc` and `http-request.adoc`.
3. Write a MockMvc JSON test with `"tags":["bug","docs"]`; generate `request-fields.adoc` and `http-request.adoc`.
4. Test missing `rating`, `rating=0`, wrong JSON type for `rating`, malformed JSON, and `Content-Type: text/plain`.
5. Try adding an undocumented form name `debug` and JSON field `debug`; observe strict validation for both snippet types.
6. Embed the snippets into two Asciidoctor documentation sections and configure Gradle/CI to run tests before rendering.

**Pass criteria:** both formats have properly typed sample HTTP requests; the controller enforces the contract; `formParameters` and `requestFields` validate their respective descriptors; tests verify business rules; documentation is generated and compiled directly from the tests.

## References

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — Documenting Request and Response Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-headers.html)
- [Spring Framework — Request Body](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Request Parameters](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
