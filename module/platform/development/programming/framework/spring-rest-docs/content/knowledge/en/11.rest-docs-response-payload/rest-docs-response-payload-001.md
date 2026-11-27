# Documenting response payloads with `responseFields`

## 1. Purpose and role of `responseFields`

In **Spring REST Docs**, `responseFields(...)` describes the structure of the response data returned by a REST API directly inside an HTTP test. Each field is declared using `fieldWithPath(...)` along with a meaningful description for API consumers. When the test passes, Spring REST Docs generates a `response-fields.adoc` **snippet** to be included in Asciidoctor documentation.

This approach keeps documentation aligned with tested behavior:

- Field descriptions live right next to the endpoint tests, making them easy to update when the API contract changes.
- In strict (default) mode, an actual field appearing in the response that has not been documented—or a required field declared in the test that does not appear—can cause the documentation generation step to fail.
- The same response can be verified for HTTP status, content, and documentation structure in a single test run.
- Snippets can be reused in composite documentation and in build/CI pipelines.

`responseFields` is a tool for **describing and verifying payload fields at test time**. It does not replace assertions for business logic, authorization, special formatting, or full schema constraints. For example, to guarantee that `available` is `true` or that `id` has a specific value, you must add MockMvc assertions.

## 2. Example response to document

Suppose the endpoint `GET /api/books/42` returns HTTP `200 OK` with the following JSON:

```json
{
  "id": 42,
  "title": "Spring REST Docs",
  "available": true,
  "authors": [
    {
      "id": 7,
      "name": "Nguyen An"
    }
  ],
  "tags": ["spring", "documentation"]
}
```

We want to generate documentation for five groups of information: `id`, `title`, `available`, the `authors` list with the fields in each element, and the `tags` array. Paths to nested fields or array elements must reflect the **actual JSON after serialization**, not just the property names in the Java class.

## 3. Writing a MockMvc test to generate `response-fields.adoc`

The following example uses JUnit Jupiter, MockMvc, and Spring REST Docs. The project requires the Spring MVC/JUnit test libraries and the `spring-restdocs-mockmvc` dependency; the sample uses Java 17+ because of `record`. `standaloneSetup` creates a simple controller so the lesson focuses on documenting the response.

```java
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.junit.jupiter.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class BookResponseDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetBookResponse() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.authors[0].id").value(7))
                .andDo(document("books-get",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Unique identifier of the book"),
                                fieldWithPath("title")
                                        .description("Book title"),
                                fieldWithPath("available")
                                        .description("Whether the book is currently available"),
                                fieldWithPath("authors")
                                        .description("List of authors"),
                                fieldWithPath("authors[].id")
                                        .description("Unique identifier of each author"),
                                fieldWithPath("authors[].name")
                                        .description("Name of each author"),
                                fieldWithPath("tags")
                                        .description("Classification tags for the book")
                        )
                ));
    }

    @RestController
    static class BookController {
        @GetMapping(value = "/api/books/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        BookResponse getBook(@PathVariable long id) {
            return new BookResponse(
                    id,
                    "Spring REST Docs",
                    true,
                    List.of(new Author(7L, "Nguyen An")),
                    List.of("spring", "documentation")
            );
        }
    }

    record Author(long id, String name) {}

    record BookResponse(long id, String title, boolean available,
                        List<Author> authors, List<String> tags) {}
}
```

**Explanation of key parts:**

1. `documentationConfiguration(restDocumentation)` attaches the HTTP exchange recording mechanism to MockMvc; `RestDocumentationExtension` manages the documentation context for each test.
2. `document("books-get", ...)` sets the identifier for the HTTP operation's snippet set. This name becomes a subdirectory inside the generated snippets directory.
3. `responseFields(...)` accepts `FieldDescriptor` instances describing the **response** payload; the path `authors[].id` applies to the `id` field inside the objects of the `authors` array.
4. `andExpect(...)` verifies the HTTP result and business data. `andDo(document(...))` generates snippets from the executed exchange.

In real-world projects, you can use `@SpringBootTest`/`@AutoConfigureMockMvc` or `@WebMvcTest` with the corresponding REST Docs configuration instead of declaring the controller directly inside the test class. With WebTestClient and REST Assured, the principle of describing `fieldWithPath` is similar, though how `document(...)` is chained into the test differs per library.

## 4. Reading and designing JSON paths

`fieldWithPath` uses Spring REST Docs' field path syntax. For JSON, you can describe nested objects, arrays of objects, and arrays of primitive values.

| Example payload | Descriptor | Meaning |
| --- | --- | --- |
| `{"id":42}` | `fieldWithPath("id")` | Top-level field |
| `{"publisher":{"name":"A"}}` | `fieldWithPath("publisher.name")` | Property inside an object |
| `{"authors":[{"id":7}]}` | `fieldWithPath("authors[].id")` | Field in each object of an array |
| `{"tags":["spring","java"]}` | `fieldWithPath("tags")` | Describes the entire array of values |
| `{"items":[{"sku":"B-1"}]}` | `fieldWithPath("items[].sku")` | Structure of elements in a list |

Some guidelines when choosing descriptors:

- Use `fieldWithPath("authors")` to describe the meaning of the entire array and `fieldWithPath("authors[].id")`/`fieldWithPath("authors[].name")` to expose the structure of each element when integrators need the details.
- For arrays of simple values like `tags`, describing the whole array is usually sufficient. When you need to clarify the meaning or element type, include that information in `description`.
- In paginated responses, paths typically take forms like `content[].id`, `content[].title`, `page.totalElements`, `page.totalPages`; the actual names must match the returned JSON.
- If the fixture used to generate documentation contains an empty array, paths to elements such as `authors[].id` may not match anything and cause the test to fail. Use a sample response with representative elements or design a separate test for the empty-array case.

For clear documentation, descriptions should convey **meaning and usage contract**: for example, what `available` means, when its value changes, or how `tags` are used for searching/filtering—avoid merely repeating the field name.

## 5. Optional fields, ignored fields, and field types

Real-world payloads often include fields that are absent depending on context or technical metadata that does not belong in the documentation table. Spring REST Docs supports options on descriptors:

```java
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("subtitle")
        .optional()
        .type(JsonFieldType.STRING)
        .description("Subtitle; may be omitted"),

fieldWithPath("internalTraceId")
        .optional()
        .ignored()
```

The descriptors above are **illustrative snippets inside the argument list** of `responseFields(...)`, not a standalone Java program.

| Declaration | Behavior to understand |
| --- | --- |
| `.description("...")` | Explanatory text included in the snippet |
| `.optional()` | Allows the declared field to be absent from the response under test |
| `.ignored()` | Allows the field to be present without displaying it in the documentation table |
| `.type(JsonFieldType.STRING)` | Specifies the documented field type, useful when it is hard to infer from sample data such as `null` values |

**Note:** `optional()` describes the possibility of a **missing field**, which is different from asserting that a returned field has a `null` value. `ignored()` should be used intentionally because an ignored field will no longer be visible to readers in the snippet. Write dedicated assertions for important business conditions or data type rules rather than relying solely on the generated field table.

## 6. Strict mode, `relaxedResponseFields`, and subsections

By default, `responseFields(...)` enforces strict checking: undocumented payload fields can cause the test to fail. This is a useful safeguard for detecting when an API adds new fields that the team has not yet documented.

When you only want to describe part of a response during a transition period, you can use:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedResponseFields;

relaxedResponseFields(
        fieldWithPath("id").description("Unique identifier of the book"),
        fieldWithPath("title").description("Book title")
)
```

`relaxedResponseFields(...)` ignores **fields outside the documented list** during documentation verification, though any required descriptors you declare must still match the payload. Only use it when there is a clear reason: the trade-off for flexibility is the risk of missing newly added API fields.

If a JSON branch is a large structure documented separately, you can document that branch as a subsection:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
        fieldWithPath("id").description("Unique identifier of the book"),
        fieldWithPath("title").description("Book title"),
        fieldWithPath("available").description("Availability status"),
        subsectionWithPath("authors")
                .description("List of authors (see detailed documentation)"),
        fieldWithPath("tags").description("Classification tags")
)
```

`subsectionWithPath("authors")` treats the `authors` branch and all fields beneath it as already documented. Only use this approach when the endpoint's documentation does not need to expose each individual element's fields.

## 7. Generating snippets and including them in Asciidoctor

After the test passes, Spring REST Docs creates files in the generated snippets directory. With a standard Gradle layout, the example output path is:

```text
build/generated-snippets/
└── books-get/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

Other snippets may also be generated depending on default configuration and how `document(...)` is invoked; the list above focuses on the files relevant to the example. With Maven, the standard output directory is `target/generated-snippets`. The exact location can be customized in the test/build configuration.

`response-fields.adoc` contains a table describing paths, data types, and descriptions from the `FieldDescriptor` entries. Asciidoctor documentation can include the snippet using:

```adoc
= Book API
:snippets: build/generated-snippets

== Get book details

=== Example response
include::{snippets}/books-get/http-response.adoc[]

=== Response fields
include::{snippets}/books-get/response-fields.adoc[]
```

The `snippets` attribute value must point to the exact location where the build outputs snippets. In build/CI pipelines, tests that generate snippets must run **before** the Asciidoctor or documentation packaging step. If the HTTP test or snippet generation step fails, the pipeline should fail rather than publishing stale documentation.

Markdown can also be used to author documentation at the publishing layer, though `response-fields.adoc` in this example is the default Asciidoctor snippet. Generating Markdown content directly requires configuring the appropriate templates/output format, not merely changing the file extension.

## 8. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Test reports undocumented fields | The response contains a new property not yet covered by `responseFields` | Add a meaningful descriptor, or intentionally mark it `.ignored()` if appropriate for the contract |
| Test reports a declared field was not found | Incorrect JSON path, different serialization rules, or field missing from fixture | Inspect the actual JSON and fix the path; use `.optional()` if the contract allows omission |
| Object array does not generate a nested field table | The fixture returns an empty array so `items[].id`, `items[].name` are absent | Use a fixture with at least one element when generating structural documentation |
| Table displays an inappropriate or ambiguous type | Missing sample data, only `null` values, or description does not match JSON type | Provide a representative fixture; consider `.type(JsonFieldType...)` and dedicated type assertions |
| `response-fields.adoc` is missing | Tests have not run, `document(...)` was not called, or directory configuration is wrong | Verify tests succeeded and check the generated snippets path |
| Asciidoctor reports an `include` error | The `snippets` attribute points to the wrong path or docs task runs before tests | Fix the path and build task ordering/dependencies |

Some Java classes use `@JsonProperty`, naming strategies, `@JsonInclude`, or business-state-dependent DTOs. These factors can alter the **actual JSON sent to clients**. Always rely on the real response captured by MockMvc/WebTestClient/REST Assured when updating `fieldWithPath`.

## 9. Practice: verifying the response contract

For the `GET /api/books/42` endpoint, try the following changes in order:

1. Add an `isbn` field to the returned JSON without adding a descriptor yet. Observe the error raised by `responseFields(...)` in strict mode.
2. Add `fieldWithPath("isbn").description("ISBN of the book")`; re-run the test and inspect the newly generated field table.
3. Make the `subtitle` field appear in some responses and disappear in others. Declare `.optional()` according to the contract while keeping assertions for required fields.
4. Test a response with `authors: []` to see its impact on the `authors[].id` and `authors[].name` descriptors. Build a representative fixture for the documentation-generating test.
5. Include `response-fields.adoc` in an Asciidoctor page and run the test → documentation pipeline to verify the table updates after modifying the response structure.

**Completion criteria:** tests verify HTTP status and key values; all public fields in the fixture are appropriately documented; optional/ignored fields are used intentionally; snippets are generated in the expected directory; and the composite documentation pulls content from the latest snippets. This forms the foundation for maintaining verifiable REST API documentation alongside Spring source code.
