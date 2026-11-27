# Testing templates with realistic payloads

## 1. Purpose of testing templates

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests execute requests, verify responses, and declare descriptors; REST Docs uses operation data to generate snippets for requests, responses, fields, parameters, headers, and hypermedia links. Snippets are compiled into Asciidoctor/Markdown and integrated into the build and CI pipeline.

Once you have customized a Mustache template, simply inspecting the template file is not enough to know whether the final result is accurate. A template can be syntactically valid yet display wrong field names, miss attributes, skip nested fields, mishandle optional/null values, break tables on special characters, or produce invalid AsciiDoc/Markdown syntax.

Therefore, you need to test using payloads representative of the API, flowing through the serializer and HTTP layer that the documentation describes. This lesson explains how to build documentation tests, check descriptor coverage, and verify that snippets actually render properly.

## 2. Three layers to verify

| Layer | Question | Example |
| --- | --- | --- |
| HTTP behavior | Does the API return the expected status, media type, and payload? | status assertion, JSONPath |
| Descriptors | Did the test document the exposed fields/parameters/links properly? | requestFields(...), responseFields(...), links(...) |
| Template output | Does the template render metadata and table structure properly? | Verify the snippet has a Constraints column and Example values |

The three layers complement each other. HTTP assertions do not prove the template displays properly; checking the snippet file alone does not prove the endpoint works. Documentation tests should combine assertions and document(...), while the output verification step reads the generated files after tests finish.

~~~text
Payload fixture
      |
      v
Jackson serialization + HTTP request
      |
      v
Controller / application behavior
      |
      v
HTTP response + assertions
      |
      v
REST Docs descriptors + attributes
      |
      v
Custom Mustache template
      |
      v
Generated snippet
      |
      v
Verify snippet content + build document
~~~

## 3. Preparing representative payloads

Do not use only a minimal payload with a single string field. Choose data representing structures the API actually supports: basic fields, nested objects, collections, enums, numbers, timestamps, and fields that may be null or absent.

Example order creation request:

~~~json
{
  "customerId": "c-1024",
  "note": "Deliver during business hours",
  "items": [
    {"productId": "p-42", "quantity": 2, "unitPrice": 125000},
    {"productId": "p-88", "quantity": 1, "unitPrice": 79000}
  ],
  "shippingAddress": {
    "city": "Ho Chi Minh City",
    "district": "District 1"
  }
}
~~~

The response can include server-generated fields:

~~~json
{
  "id": "o-9001",
  "status": "PENDING",
  "total": 329000,
  "createdAt": "2026-11-17T08:30:00Z",
  "note": "Deliver during business hours",
  "items": [
    {"productId": "p-42", "quantity": 2, "unitPrice": 125000},
    {"productId": "p-88", "quantity": 1, "unitPrice": 79000}
  ]
}
~~~

The payload tests the template across multiple field types and nested structures. This is a synthetic fixture; never put real customer info, tokens, addresses, or identifiers into public snippets.

## 4. Using DTOs and ObjectMapper to send payloads in HTTP tests

With MockMvc, build requests from DTOs and serialize them with ObjectMapper. This tests payloads serialized through the application's Jackson configuration, rather than testing a hand-written JSON string unrelated to the model.

Abbreviated DTO example:

~~~java
record CreateOrderRequest(
        String customerId,
        String note,
        List<OrderItemRequest> items,
        ShippingAddress shippingAddress) {}

record OrderItemRequest(String productId, int quantity, long unitPrice) {}

record ShippingAddress(String city, String district) {}
~~~

Documentation test using ObjectMapper:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class OrderDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void createOrderDocumentsRealRequestAndResponse() throws Exception {
        CreateOrderRequest request = new CreateOrderRequest(
                "c-1024",
                "Deliver during business hours",
                List.of(
                        new OrderItemRequest("p-42", 2, 125000),
                        new OrderItemRequest("p-88", 1, 79000)),
                new ShippingAddress("Ho Chi Minh City", "District 1"));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(request)))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").exists())
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.items.length()").value(2))
                .andDo(document("orders-create",
                        requestFields(
                                fieldWithPath("customerId").description("Customer ID"),
                                fieldWithPath("note").description("Delivery note"),
                                fieldWithPath("items").description("Product list"),
                                fieldWithPath("items[].productId").description("Product ID"),
                                fieldWithPath("items[].quantity").description("Quantity"),
                                fieldWithPath("items[].unitPrice").description("Unit price"),
                                fieldWithPath("shippingAddress").description("Shipping address"),
                                fieldWithPath("shippingAddress.city").description("City"),
                                fieldWithPath("shippingAddress.district").description("District")),
                        responseFields(
                                fieldWithPath("id").description("Order ID"),
                                fieldWithPath("status").description("Order status"),
                                fieldWithPath("total").description("Total amount"),
                                fieldWithPath("createdAt").description("Creation timestamp"),
                                fieldWithPath("note").description("Delivery note"),
                                fieldWithPath("items").description("Product list"),
                                fieldWithPath("items[].productId").description("Product ID"),
                                fieldWithPath("items[].quantity").description("Quantity"),
                                fieldWithPath("items[].unitPrice").description("Unit price"))));
    }
}
~~~

This is an integration pattern that should be adapted to your application's DTOs, endpoints, responses, and imports. If using @WebMvcTest instead of @SpringBootTest, include the appropriate controller, serializer, mocked services, and REST Docs configuration.

## 5. Checking descriptor coverage on payloads

When using requestFields(...) or responseFields(...) in strict mode, Spring REST Docs verifies descriptions against the payload structure. For nested payloads, document subsections/fields matching the structure. An overly broad descriptor can hide fields the documentation ought to present; a missing descriptor fails the test.

Inspect the payload before writing descriptors:

- Actual field names and data types after serialization.
- Nested fields with paths like parent.child.
- Arrays and elements like items[] or items[].productId.
- Optional, nullable fields, or fields that may be omitted from JSON.
- Fields added by the server in responses that do not appear in requests.
- Sensitive fields that must be filtered or excluded from fixtures.

Example documenting a collection and each field:

~~~java
requestFields(
        fieldWithPath("items").description("Product list"),
        fieldWithPath("items[].productId").description("Product ID"),
        fieldWithPath("items[].quantity").description("Quantity"),
        fieldWithPath("items[].unitPrice").description("Unit price"))
~~~

When a payload has optional fields, use optional() according to the contract. Use ignored() only for fields intentionally excluded from documentation; do not use it to mask an important field missing from descriptors.

## 6. Testing template metadata

Suppose request-fields.snippet has been customized with Path, Type, Description, Constraints, and Example columns. The test passes metadata:

~~~java
requestFields(
        attributes(
                key("title").value("Fields for creating an order"),
                key("api-version").value("v1")),
        fieldWithPath("customerId")
                .description("Customer ID")
                .attributes(
                        key("constraints").value("Must not be blank"),
                        key("example").value("c-1024")),
        fieldWithPath("items[].quantity")
                .description("Quantity")
                .attributes(
                        key("constraints").value("1 or greater"),
                        key("example").value("2")))
~~~

To test the template, do not check only that Java called attributes(...). Inspect the snippet output after the documentation test completes:

~~~text
build/generated-snippets/
└── orders-create/
    └── request-fields.adoc
~~~

The contents should show the title "Fields for creating an order", API version v1, constraints for customerId and items[].quantity, and examples attached to the right fields; fields without metadata must not produce bad content or break the table.

This directly verifies the rendered template rather than only confirming descriptor configuration.

## 7. Verifying snippet files after tests run

Snippets are written when an operation executes document(...). Therefore, the file-reading check must run after documentation tests. Do not assume another test in the same test suite will execute after the snippet-generating test; test execution order is typically not a stable contract.

You can add a separate verification step in the build after the test task. Example standalone Java snippet to verify the generated file:

~~~java
Path snippet = Path.of(
        "build/generated-snippets",
        "orders-create",
        "request-fields.adoc");

String rendered = Files.readString(snippet, StandardCharsets.UTF_8);

assertThat(rendered)
        .contains("Fields for creating an order")
        .contains("Must not be blank")
        .contains("1 or greater")
        .contains("c-1024");
~~~

Place this verification in a task/verifier running after documentation tests and adjust the output directory/extension to match your project configuration. Do not put the verifier in a test running concurrently with snippet-generating tests because it may read the file before it is written.

### Output format checks

- Column headers appear exactly once.
- Every row has the expected number of columns per the template.
- Optional metadata sections appear only when values are present.
- Special characters in payloads do not break AsciiDoc/Markdown syntax.
- No unrendered Mustache placeholders such as {{constraints}} remain.
- No stale content from earlier payloads remains if the build reuses the output directory.

Use a clean output directory for CI snippet generation, or ensure the clean task deletes old output before documentation tests run.

## 8. Using multiple payloads to test template resilience

A single successful payload is not enough to prove a template handles all data shapes. Select cases that test optional sections, tables, and escaping:

| Case | Test data | What to observe |
| --- | --- | --- |
| Normal values | Valid strings, numbers, enums | Table renders completely |
| String with special characters | A&B <C> | Content does not break structure |
| Empty string | note: "" | Empty cell renders consistently |
| Null value | note: null if API allows | Field shows null or is omitted by serializer per config |
| Absent optional field | Key omitted | Optional descriptor handles it cleanly |
| Empty collection | items: [] | Collection description does not assume items exist |
| Multi-element collection | Two or more items | Array-style field paths are documented properly |
| Nested object | shippingAddress.city | Paths and subsections are accurate |
| Long values | Long note or description | Table does not break during compilation |

Not every case needs its own public snippet. You can use a few documentation operations for main examples and extra tests solely for verifying behavior/serialization. If generating snippets per case, use distinct identifiers so outputs do not overwrite one another.

## 9. Checking escaping and sensitive data

Real payloads can contain characters special to AsciiDoc, Markdown, or tables. For instance, a pipe | can be treated as a column separator, and newlines can alter layout. Templates must handle escaping according to the output format; never assume all content is safe when inserted directly into a table.

Create a fixture with special characters:

~~~json
{
  "displayName": "Alice & Bob",
  "description": "Plan A | Plan B",
  "note": "Line one\nLine two"
}
~~~

After generating snippets, check that the data does not break tables or create unintended headings. If the template needs a specialized escaping helper, check the capabilities of your active engine/format and implement appropriate rules; do not alter fixtures to hide rendering bugs.

Use only synthetic data in documentation. Never use real tokens, cookies, customer emails, phone numbers, real shipping addresses, or confidential data from staging/production.

## 10. Testing multiple template formats

If the project supports both Asciidoctor and Markdown, verify the output of each format:

~~~text
templates/
├── asciidoctor/
│   └── request-fields.snippet
└── markdown/
    └── request-fields.snippet
~~~

The two templates can display the same metadata while using different table syntax. Run documentation tests with each respective format, then verify:

| Check | Asciidoctor | Markdown |
| --- | --- | --- |
| Output extension | .adoc | .md |
| Table syntax | AsciiDoc table | Markdown table |
| Title/note | Renders cleanly | Renders cleanly |
| Constraints/examples | Right fields | Right fields |
| Special characters | Escaped properly | Escaped properly |
| Include/build | Asciidoctor task | Markdown pipeline |

Do not just check that .snippet files are in the right place. Run tests with the selected format and read the generated snippet files.

## 11. Organizing CI so templates are tested with current payloads

~~~text
Clean generated snippets
          |
          v
Run documentation tests
          |
          v
Assert HTTP behavior and descriptor coverage
          |
          v
Verify generated snippet content
          |
          v
Build Asciidoctor / Markdown
          |
          v
Archive or publish documentation
~~~

CI principles:

1. Clean old output or use a fresh output directory for the current build.
2. Run documentation tests using fixtures representative of API payloads.
3. Verify snippet output after tests finish writing files.
4. Compile documentation after the snippet-generation step.
5. Archive artifacts so reviewers can compare diffs when templates change.
6. When upgrading Spring REST Docs, verify template models and snippet diffs.

If CI only runs Asciidoctor without running documentation tests, a new template may never have been rendered against current payloads. The compilation task must depend on snippet-generating tests.

## 12. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Template renders but lacks metadata column | Test did not pass attribute or template uses wrong key | Check descriptor attributes and Mustache placeholders |
| Nested field does not appear | Descriptor path does not match serialized JSON | Inspect actual payload and adjust field path |
| Tests pass but snippet format is wrong | Only checked HTTP assertions, did not verify template output | Add a post-test snippet reading step |
| Snippet contains stale data | Output directory retains files from previous build | Clean output or use a dedicated directory |
| Template breaks on empty array | Fixture only tested populated collections | Add an empty collection test case |
| Table breaks due to pipes or newlines | Content not escaped for target format | Adjust template and inspect output |
| Optional field reported missing | Descriptor not marked optional per contract | Use optional() when absence is valid |
| Snippet verifier cannot find file | Verifier runs before documentation test or wrong output path | Set task dependency order and check paths |
| Markdown works but AsciiDoc fails | Only tested one template format | Run and verify both formats if supported |
| Test fixture leaks real data | Payload copied from an environment | Replace with stable, synthetic data |

## 13. Hands-on exercises

1. Build a request payload using DTOs and ObjectMapper, including a collection and nested object.
2. Write a MockMvc documentation test with status/content-type assertions and request/response field descriptors.
3. Add constraints, example, and a snippet-level title to the request-fields template.
4. Run the test and verify that the request-fields snippet file contains metadata on the right fields.
5. Add fixtures with an empty collection, optional field, and special-character strings; observe the output.
6. Create a verifier running after documentation tests to check that snippets have no remaining Mustache placeholders and have the right column count.
7. Run the same test suite with Asciidoctor and Markdown, then compile the documentation in CI.

**Completion criteria:** templates are tested with serialized payloads over HTTP; assertions confirm API behavior; descriptors cover published payloads; snippet output is read after tests finish; edge cases and output formats are verified.

## 14. Pre-commit checklist

- [ ] Payload fixtures represent realistic requests/responses and use only synthetic data.
- [ ] Serializer produces JSON matching the published endpoint.
- [ ] Tests assert status, media type, and key content.
- [ ] Descriptors cover nested fields, arrays, and optional fields accurately.
- [ ] Snippet/descriptor-level attributes use matching keys.
- [ ] Templates render metadata cleanly into output snippets.
- [ ] Snippet verifier runs after documentation tests.
- [ ] Old output directories are cleaned or isolated per build.
- [ ] Special characters, empty strings, nulls, and empty collections are accounted for.
- [ ] All supported formats have render tests and documentation builds.
- [ ] CI builds artifacts from fresh snippets of the current run.

**Key takeaway:** Testing templates does not stop at inspecting Mustache files. Run documentation tests with payloads serialized like the real API, verify HTTP behavior and descriptor coverage, and read the rendered snippets to ensure metadata, field paths, escaping, and output syntax are all sound before compiling documentation.
