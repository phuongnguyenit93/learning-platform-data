# Distinguishing Request Parts from Form Parameters in Spring REST Docs

## 1. Two Closely Related Concepts with Different Wire Representations

Both form parameters and request parts can carry name/value data, yet they belong to different HTTP representations.

A **form parameter** is typically a form value sent via `application/x-www-form-urlencoded`. For example:

```http
POST /api/profile HTTP/1.1
Content-Type: application/x-www-form-urlencoded

displayName=Nguyen+An&newsletter=true
```

The body is encoded as name/value pairs. In Spring REST Docs, use `formParameters(...)` together with `parameterWithName(...)` to document form fields.

A **request part** is a distinct section inside a `multipart/form-data` body. Each part has a name, content, and can have its own headers:

```http
POST /api/profile/photo HTTP/1.1
Content-Type: multipart/form-data; boundary=----FormBoundary

------FormBoundary
Content-Disposition: form-data; name="displayName"

Nguyen An
------FormBoundary
Content-Disposition: form-data; name="photo"; filename="avatar.png"
Content-Type: image/png

<image bytes>
------FormBoundary--
```

In multipart, `displayName` is also a part on the wire, even though its content is just text. `photo` is a part containing a file. Spring REST Docs uses `requestParts(...)` and `partWithName(...)` to document the multipart structure.

This lesson belongs to the **Request parts** chapter of **SPRING_REST_DOCS**: producing verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, then integrating snippets into Asciidoctor/Markdown and build/CI.

After this lesson, you will be able to:

- Distinguish `application/x-www-form-urlencoded` from `multipart/form-data`.
- Choose `formParameters(...)` or `requestParts(...)` based on the actual HTTP representation.
- Understand why a multipart text part can be bound using `@RequestParam`.
- Distinguish `@RequestParam` from `@RequestPart` when a controller receives JSON or XML.
- Generate snippets for form parameters, multipart parts, and query parameters without mixing scopes.
- Test names, presence, content types, and validation of submitted values.

## 2. Identifying by Request Content-Type

The reliable way to tell them apart is to inspect the overall request's `Content-Type` and body structure.

| Characteristic | Form parameter | Request part |
| --- | --- | --- |
| Common Content-Type | `application/x-www-form-urlencoded` | `multipart/form-data; boundary=...` |
| Body structure | URL-encoded name/value pairs | Multiple sections separated by boundary |
| Does each value have its own headers? | No per-part headers | Can have `Content-Disposition`, `Content-Type` |
| Typically used for | Text fields, choices, checkboxes | Files, JSON/XML parts, text parts, and other content |
| Spring REST Docs | `formParameters(...)` | `requestParts(...)` |
| Descriptor | `parameterWithName(...)` | `partWithName(...)` |
| Default snippet | `form-parameters.adoc` | `request-parts.adoc` |

For example, two requests may send the same value `displayName=Nguyen An`, yet package it differently:

```text
application/x-www-form-urlencoded
    displayName=Nguyen+An

multipart/form-data
    Part name="displayName"
    Body: Nguyen An
```

Having the same parameter name and value does not make the two HTTP structures identical. When selecting a snippet, base your choice on the actual request sent by the test.

## 3. `formParameters(...)` and `parameterWithName(...)`

Spring REST Docs provides `formParameters(...)` in `RequestDocumentation` to generate snippets for form parameters:

```java
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;

formParameters(
    parameterWithName("displayName")
        .description("User display name"),
    parameterWithName("newsletter")
        .description("Whether the user subscribes to the newsletter")
);
```

The generated snippet is `form-parameters.adoc`. Descriptors use `ParameterDescriptor`; therefore, the API to create descriptors is `parameterWithName(...)`, not `fieldWithPath(...)` or `partWithName(...)`.

A basic MockMvc test:

```java
mockMvc.perform(post("/api/profile")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("displayName", "Nguyen An")
        .param("newsletter", "true"))
    .andExpect(status().isNoContent())
    .andDo(document("profile-update",
        formParameters(
            parameterWithName("displayName")
                .description("Display name"),
            parameterWithName("newsletter")
                .description("Newsletter subscription")
        )
    ));
```

`.param(...)` in MockMvc builds request parameters. Setting Content-Type to `application/x-www-form-urlencoded` clarifies that this is a URL-encoded form body, not a JSON body.

### 3.1. Required, Optional, and Ignored

Like other request descriptors, parameter descriptors are treated as required by default in snippets. If a form parameter may be absent, mark `.optional()`:

```java
formParameters(
    parameterWithName("displayName")
        .description("Display name"),
    parameterWithName("newsletter")
        .description("Newsletter subscription")
        .optional()
);
```

If a parameter is known but does not need to appear in the table:

```java
parameterWithName("trackingSource")
    .description("Internal tracking source")
    .optional()
    .ignored();
```

`.optional()` allows the documented parameter to be absent in the sample request. `.ignored()` excludes the parameter from the snippet table. The two attributes have different purposes.

### 3.2. Strict and Relaxed Form Parameters

`formParameters(...)` validates form parameters against descriptors; undocumented parameters can cause the snippet to fail. When you need to document part of a form and allow additional parameters, use `relaxedFormParameters(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.relaxedFormParameters;

relaxedFormParameters(
    parameterWithName("displayName")
        .description("Display name")
);
```

Relaxed mode is suitable when the form allows extensions by contract. It reduces the ability to catch new undocumented parameters, so avoid using it merely to skip updating descriptors.

## 4. `requestParts(...)` and `partWithName(...)`

With `multipart/form-data`, the body is divided into multiple parts. Use `requestParts(...)`:

```java
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;

requestParts(
    partWithName("displayName")
        .description("Display name in the form"),
    partWithName("photo")
        .description("Avatar image to upload")
);
```

Here both `displayName` and `photo` are parts on the wire. The `displayName` part may contain only text; the `photo` part contains file bytes and usually has its own filename and Content-Type.

Spring REST Docs generates the `request-parts.adoc` snippet. In strict mode, a part present in the request without documentation can fail the test; a required descriptor missing from the request can also fail the test. Use `.optional()` when a part is allowed to be absent, and `.ignored()` when a part is known but should not appear in the table. `relaxedRequestParts(...)` allows undocumented parts to appear.

Multipart upload example:

```java
mockMvc.perform(multipart("/api/profile/photo")
        .file(new MockMultipartFile(
            "photo",
            "avatar.png",
            MediaType.IMAGE_PNG_VALUE,
            validPngBytes
        ))
        .part(new MockPart(
            "displayName",
            "Nguyen An".getBytes(StandardCharsets.UTF_8)
        )))
    .andExpect(status().isNoContent())
    .andDo(document("profile-photo-upload",
        requestParts(
            partWithName("displayName")
                .description("Display name"),
            partWithName("photo")
                .description("PNG avatar image")
        )
    ));
```

The example uses `MockPart` to represent the text part and `MockMultipartFile` to represent the file part. In real tests, `validPngBytes` must be a valid image fixture if the endpoint validates file content.

## 5. The Same Multipart Text Part Can Be Bound with `@RequestParam`

This is an easy point of confusion. How the controller binds data and how data is represented on the wire are two different perspectives.

Spring MVC can expose multipart form fields as request parameters. Therefore, a text part named `displayName` can be bound like this:

```java
@PostMapping(
    path = "/api/profile/photo",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> upload(
        @RequestParam("displayName") String displayName,
        @RequestPart("photo") MultipartFile photo) {
    // Process display name and photo.
    return ResponseEntity.noContent().build();
}
```

At the HTTP layer, `displayName` is still sent inside a multipart part. `@RequestParam` is how Spring MVC extracts that simple value into a method argument; it does not turn the request body into `application/x-www-form-urlencoded`.

Therefore:

- If you need to document the multipart request structure on the wire, use `requestParts(...)` for both the `displayName` and `photo` parts.
- If the operation uses a URL-encoded form, use `formParameters(...)`.
- If you only want to explain a value bound by `@RequestParam` in the controller, check whether the actual request is a URL-encoded form, a query string, or multipart before choosing the snippet.

Do not choose the snippet solely by looking at controller annotations. Look at the HTTP request that the client actually sends.

## 6. How Do `@RequestParam` and `@RequestPart` Differ?

Spring Framework allows both `@RequestParam` and `@RequestPart` to bind a multipart part to a controller parameter in appropriate cases. The notable difference lies in how content is converted:

- `@RequestParam` is typically used for simple name/value form fields. Values are converted via a registered `Converter` or `PropertyEditor`.
- `@RequestPart` fits parts with complex content such as JSON/XML. Spring uses an `HttpMessageConverter` and considers the part's Content-Type, similar to how `@RequestBody` handles regular bodies.

Example multipart request with text and JSON:

```http
Content-Disposition: form-data; name="category"

COVER
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Book Cover","displayOrder":1}
```

Controller:

```java
@PostMapping(
    path = "/api/assets",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> create(
        @RequestParam("category") AssetCategory category,
        @RequestPart("metadata") @Valid AssetMetadata metadata) {
    return ResponseEntity.noContent().build();
}
```

`category` is a simple name/value entry that can be converted to an enum. `metadata` is a JSON object, so it is deserialized through a message converter according to `application/json`.

Multipart documentation:

```java
requestParts(
    partWithName("category")
        .description("Asset category"),
    partWithName("metadata")
        .description("JSON metadata of the asset")
),
requestPartFields("metadata",
    fieldWithPath("title").description("Asset title"),
    fieldWithPath("displayOrder").description("Display order").optional()
)
```

Even though the controller receives `category` via `@RequestParam`, it is still a part of the multipart request and can be documented in the request parts table. `requestPartFields(...)` is strictly for JSON fields inside `metadata`.

## 7. Do Not Confuse Form Parameters with Query Parameters

A parameter can also appear in the URL query string:

```http
GET /api/products?category=BOOK&page=2
```

This is a query parameter, not a form parameter and not a multipart part.

Spring REST Docs has a dedicated API:

```java
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
    parameterWithName("category").description("Product category"),
    parameterWithName("page").description("Page number")
);
```

Each snippet has a distinct scope:

| Data Type | Example | REST Docs API |
| --- | --- | --- |
| Path variable | `/products/{id}` | `pathParameters(...)` |
| Query parameter | `?page=2` | `queryParameters(...)` |
| URL-encoded form parameter | `displayName=Nguyen+An` in body | `formParameters(...)` |
| Multipart part | `name="photo"` in multipart body | `requestParts(...)` |
| JSON request body field | `{"name":"An"}` | `requestFields(...)` |

Using the right API gives snippets accurate titles, placements, and semantics.

## 8. Two Complete Operations in MockMvc

### 8.1. Operation Accepting a URL-Encoded Form

Controller:

```java
@PostMapping(
    path = "/api/preferences",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
ResponseEntity<Void> updatePreferences(
        @RequestParam String displayName,
        @RequestParam(defaultValue = "false") boolean newsletter) {
    return ResponseEntity.noContent().build();
}
```

Test and snippet:

```java
@Test
void documentUrlEncodedForm() throws Exception {
    mockMvc.perform(post("/api/preferences")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("displayName", "Nguyen An")
            .param("newsletter", "true"))
        .andExpect(status().isNoContent())
        .andDo(document("preferences-update",
            formParameters(
                parameterWithName("displayName")
                    .description("Display name"),
                parameterWithName("newsletter")
                    .description("Newsletter subscription")
            )
        ));
}
```

Generated snippet:

```text
build/generated-snippets/preferences-update/form-parameters.adoc
```

### 8.2. Operation Accepting a Multipart File and Text Field

Controller:

```java
@PostMapping(
    path = "/api/profile/photo",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
ResponseEntity<Void> uploadPhoto(
        @RequestParam("displayName") String displayName,
        @RequestPart("photo") MultipartFile photo) {
    return ResponseEntity.noContent().build();
}
```

Test and snippet:

```java
@Test
void documentMultipartForm() throws Exception {
    MockMultipartFile photo = new MockMultipartFile(
            "photo",
            "avatar.png",
            MediaType.IMAGE_PNG_VALUE,
            validPngBytes
    );

    MockPart displayName = new MockPart(
            "displayName",
            "Nguyen An".getBytes(StandardCharsets.UTF_8)
    );

    mockMvc.perform(multipart("/api/profile/photo")
            .file(photo)
            .part(displayName))
        .andExpect(status().isNoContent())
        .andDo(document("profile-photo-upload",
            requestParts(
                partWithName("displayName")
                    .description("Display name"),
                partWithName("photo")
                    .description("Avatar image")
            )
        ));
}
```

Generated snippet:

```text
build/generated-snippets/profile-photo-upload/request-parts.adoc
```

Both operations may use `@RequestParam` in the controller, yet their tests and documentation use different snippets because the requests have different Content-Types and body structures.

## 9. WebTestClient and REST Assured

### 9.1. WebTestClient with a URL-Encoded Form

Use `BodyInserters.fromFormData(...)` to build the form body:

```java
webTestClient.post()
    .uri("/api/preferences")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData("displayName", "Nguyen An")
        .with("newsletter", "true"))
    .exchange()
    .expectStatus().isNoContent()
    .expectBody()
    .consumeWith(document("preferences-update",
        formParameters(
            parameterWithName("displayName").description("Display name"),
            parameterWithName("newsletter").description("Newsletter subscription")
        )
    ));
```

### 9.2. WebTestClient with Multipart

Use `BodyInserters.fromMultipartData(...)`:

```java
MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
parts.add("displayName", "Nguyen An");
parts.add("photo", imageResource);

webTestClient.post()
    .uri("/api/profile/photo")
    .contentType(MediaType.MULTIPART_FORM_DATA)
    .body(BodyInserters.fromMultipartData(parts))
    .exchange()
    .expectStatus().isNoContent()
    .expectBody()
    .consumeWith(document("profile-photo-upload",
        requestParts(
            partWithName("displayName").description("Display name"),
            partWithName("photo").description("Avatar image")
        )
    ));
```

### 9.3. REST Assured

URL-encoded form:

```java
given(this.spec)
    .filter(document("preferences-update",
        formParameters(
            parameterWithName("displayName").description("Display name"),
            parameterWithName("newsletter").description("Newsletter subscription")
        )))
    .formParam("displayName", "Nguyen An")
    .formParam("newsletter", "true")
    .when()
    .post("/api/preferences")
    .then()
    .statusCode(204);
```

Multipart:

```java
given(this.spec)
    .filter(document("profile-photo-upload",
        requestParts(
            partWithName("displayName").description("Display name"),
            partWithName("photo").description("Avatar image")
        )))
    .multiPart("displayName", "Nguyen An")
    .multiPart("photo", imageFile, "image/png")
    .when()
    .post("/api/profile/photo")
    .then()
    .statusCode(204);
```

Exact syntax of the multipart builder depends on the overload and REST Assured version. What matters is that the overall Content-Type and final body structure match the contract.

## 10. Optional, Ignored, and Relaxed

Both `formParameters(...)` and `requestParts(...)` support descriptor controls:

- `.optional()` allows the documented parameter/part to be absent in the sample request.
- `.ignored()` acknowledges the parameter/part without displaying it in the snippet.
- `relaxedFormParameters(...)` allows undocumented form parameters.
- `relaxedRequestParts(...)` allows undocumented multipart parts.

Example:

```java
formParameters(
    parameterWithName("displayName").description("Display name"),
    parameterWithName("referralCode")
        .description("Referral code")
        .optional()
);
```

Multipart equivalent:

```java
requestParts(
    partWithName("photo").description("Avatar image"),
    partWithName("caption")
        .description("Image caption")
        .optional()
);
```

Do not use `.optional()` to make the server accept missing data. That is a contract and endpoint validation decision. REST Docs only checks the sample request used to generate the snippet.

## 11. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Using `requestParts(...)` for URL-encoded body | Confusing form field with multipart part | Use `formParameters(...)` |
| Using `formParameters(...)` for file upload | Files require multipart structure | Use `requestParts(...)` |
| Multipart text field bound via `@RequestParam`, mistaking it for URL-encoded form | Confusing controller binding with wire representation | Check Content-Type; a multipart part is still a part |
| JSON metadata bound to wrong type | Using `@RequestParam` with a complex object or unsuitable part Content-Type | Use `@RequestPart` and `application/json` |
| Using `fieldWithPath(...)` for form parameter | Misusing JSON payload descriptor | Use `parameterWithName(...)` |
| Using `partWithName(...)` for query parameter | Confusing query string with multipart | Use `queryParameters(...)` |
| Snippet reports missing parameter/part | Required descriptor was not sent by sample request | Fix fixture or mark `.optional()` per contract |
| Snippet reports extra parameter/part | Strict mode encountered undeclared value | Add descriptor, intentionally ignore, or relax per contract |
| Choosing snippet solely from controller annotations | Ignoring actual HTTP structure | Choose by Content-Type and data placement on the wire |

## 12. Asciidoctor and Build/CI

You can include both form parameter and multipart part snippets in the same API documentation:

```adoc
= Profile API
:toc: left

== Update Preferences

include::{snippets}/preferences-update/form-parameters.adoc[]

== Upload Avatar

include::{snippets}/profile-photo-upload/request-parts.adoc[]
```

With Gradle and the Asciidoctor plugin configured, the documentation task should depend on the snippet-generating tests:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

CI flow:

```text
HTTP tests
   |
   +--> application/x-www-form-urlencoded
   |       |
   |       +--> formParameters(...)
   |
   +--> multipart/form-data
           |
           +--> requestParts(...)
   |
   v
Generated snippets
   |
   v
Asciidoctor / Markdown export step
   |
   v
Verify and publish documentation
```

If a URL-encoded form is changed to multipart to support file uploads, simultaneously update controller `consumes`, test request construction, snippet descriptors, and Asciidoctor docs. Do not keep an old `form-parameters.adoc` and present it as if it documented the new multipart request.

Spring REST Docs generates AsciiDoc snippets by default. To export Markdown, a custom template or conversion step is needed; `.md` snippets are not generated by default.

## 13. Practice Exercise

Using the two sample endpoints in this lesson:

1. Create `POST /api/preferences` with Content-Type `application/x-www-form-urlencoded`. Use `formParameters(...)` to document `displayName` and `newsletter`.
2. Add an optional `referralCode`; test requests with and without the parameter.
3. Create `POST /api/profile/photo` with `multipart/form-data`, containing a text part `displayName` and a file part `photo`.
4. Use `requestParts(...)` to document both parts. Confirm that even though the controller uses `@RequestParam` for `displayName`, the wire format is still multipart.
5. Add a JSON part `metadata`, bind it with `@RequestPart`, and use `requestPartFields(...)` to document its fields.
6. Try changing the overall Content-Type from multipart to URL-encoded and observe that the endpoint no longer receives the file as before.
7. Include both `form-parameters.adoc` and `request-parts.adoc` in Asciidoctor.
8. Run the documentation tests and verify CI detects when a new parameter/part lacks a descriptor.

### Self-Assessment Questions

- Which request type does `formParameters(...)` document?
- Which component of a multipart body does `requestParts(...)` document?
- Can a text part in a multipart request be bound via `@RequestParam`?
- Why does `@RequestParam` not guarantee the request is a URL-encoded form?
- When is `@RequestPart` more appropriate than `@RequestParam`?
- How do `formParameters`, `queryParameters`, and `requestParts` differ in where data is transmitted?
- If an endpoint changes from a URL-encoded form to multipart, which parts of tests and documentation must be updated?

**Remember:** Choose snippets based on the HTTP structure on the wire. `formParameters(...)` is for form parameters; `requestParts(...)` is for `multipart/form-data` parts. A multipart text part can be bound by Spring using `@RequestParam`, yet it remains a part of the multipart request. For JSON/XML content needing a message converter by Content-Type, `@RequestPart` is generally the right choice.

## References

- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html): `formParameters`, `relaxedFormParameters`, `requestParts`, `partWithName`, and parameter snippets.
- [Spring REST Docs — Multipart](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/multipart.html): documenting multipart requests and request part payloads.
- [Spring Framework — Multipart forms](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): how Spring MVC accesses form fields and multipart files.
- [Spring Framework — `@RequestPart` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html): conversion differences between `@RequestPart` and `@RequestParam`.
