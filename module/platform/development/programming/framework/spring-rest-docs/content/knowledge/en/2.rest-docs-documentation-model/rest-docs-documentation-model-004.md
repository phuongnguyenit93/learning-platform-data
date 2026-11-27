# Snippets as Embeddable Documentation Fragments in Larger Docs

In **Spring REST Docs**, a single HTTP test can generate multiple **snippets**: a request example, a response example, a path parameter table, a query parameter table, request/response header tables, a JSON field table, or a cURL command. Each snippet is a **documentation fragment generated from a tested operation**, ready to be embedded into an endpoint page or a larger API documentation set.

This lesson belongs to the **Documentation Model** chapter of the `SPRING_REST_DOCS` module. The module's goal is to create verifiable REST API documentation from tests with **MockMvc**, **WebTestClient**, or **REST Assured**, documenting requests, responses, payloads, parameters, and headers, and then compiling **Asciidoctor/Markdown** in the build and CI pipeline. This lesson focuses on how a snippet is generated, identified, embedded into a documentation page, reused properly, and kept under control when the API changes.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain why a snippet is a **small unit of content** rather than the entire endpoint documentation.
2. Distinguish between default snippets of observed HTTP data and descriptive table snippets requested by descriptors.
3. Write a Spring REST Docs test that generates the needed snippets for an operation.
4. Embed snippets into an AsciiDoc page using `include`, while adding human-written business context.
5. Design paths, operation names, and build workflows to prevent missing, mismatched, or stale snippets.
6. Recognize differences when publishing Markdown documentation instead of Asciidoctor.

## 2. What Is a Snippet, and What Is It Not?

Suppose an API has the endpoint `GET /api/products/{productId}`. API consumers need to know:

- How to call the endpoint, including method, path, headers, and query parameters if any.
- Whether the request has a body.
- On success, what the status, response headers, and JSON look like.
- What `productId`, `name`, `price`, and other fields mean.
- Which situations return `400`, `404`, or `403` according to the API contract.

An `http-response.adoc` file may contain a response example recorded from a test. A `response-fields.adoc` file contains a table explaining the fields. **Each file only answers part of the questions.** A complete documentation page combines them with headings, endpoint descriptions, invocation conditions, error details, and links to other sections.

You can visualize the relationship as follows:

```text
HTTP test for an operation
              │
              ▼
         Spring REST Docs
              │
              ├── http-request.adoc       (call example)
              ├── http-response.adoc      (result example)
              ├── path-parameters.adoc    (path parameter table)
              ├── query-parameters.adoc   (query parameter table)
              ├── request-headers.adoc    (request header table)
              └── response-fields.adoc    (response field table)
                          │
                          ▼
          "Look up a product" documentation page
          ┌───────────────────────────────┐
          │ Purpose and access permissions│
          │ Request example               │
          │ Parameter tables              │
          │ Response example              │
          │ JSON fields table             │
          │ Error codes & matching examples│
          └───────────────────────────────┘
                          │
                          ▼
            Service API documentation set
```

| Concept | Role | Example |
| --- | --- | --- |
| **Operation** | A single request/response exchange recorded by Spring REST Docs | Test calls `GET /api/products/7` and receives `200` |
| **Snippet** | Documentation fragment generated from an operation and descriptor config | `products-get/http-response.adoc` |
| **Endpoint page** | Presents how to use a specific API behavior | Section “Get product details” |
| **API documentation set** | Collection of multiple pages, introduction, general rules, and references | Documentation for products, orders, and authentication |

**One operation can generate multiple snippets; one documentation page can include snippets from multiple operations.** For instance, the `GET /api/products/{productId}` page can contain snippets for both `200 OK` and `404 Not Found`.

## 3. Two Common Categories of Snippets

Spring REST Docs provides snippets based on observed request/response data and snippets generated when a test requests descriptions for specific components.

### 3.1. Snippets Showing Observed HTTP Data

Common default snippets (unless the default snippet set is reconfigured) are:

| Filename | Content | When to include |
| --- | --- | --- |
| `http-request.adoc` | HTTP request line, headers, and body | When readers need a complete HTTP example |
| `http-response.adoc` | HTTP response status, headers, and body | When displaying a complete result example |
| `curl-request.adoc` | API call example using cURL | When readers want to try the API quickly |
| `httpie-request.adoc` | API call example using HTTPie | When the docs prioritize HTTPie |
| `request-body.adoc` | Only the request body | When the body is long or needs separate explanation |
| `response-body.adoc` | Only the response body | When illustrating JSON/XML without repeating status/headers |

These snippets pull data from **the actual request and response executed by the test**, optionally passing through configured preprocessors to format, normalize, or mask data.

For example, `http-request.adoc` might display:

```http
GET /api/products/7?locale=vi HTTP/1.1
Accept: application/json
```

Whereas `response-body.adoc` displays only the body:

```json
{
  "id": 7,
  "name": "Notebook",
  "price": 45000
}
```

They do not contain the full business explanation of the API. Which currency unit the price uses, whether tax is applied, and which roles may view the product—those details must still be stated by the author according to the system contract.

### 3.2. Descriptor-Based Table Snippets

This group is created when the test declares the corresponding descriptors:

| Descriptor API in test | Typical snippet name | What it documents |
| --- | --- | --- |
| `pathParameters(...)` | `path-parameters.adoc` | Variables in the path template |
| `queryParameters(...)` | `query-parameters.adoc` | Request query parameters |
| `requestHeaders(...)` | `request-headers.adoc` | Request headers |
| `responseHeaders(...)` | `response-headers.adoc` | Response headers |
| `requestFields(...)` | `request-fields.adoc` | Fields in the request payload |
| `responseFields(...)` | `response-fields.adoc` | Fields in the response payload |
| `links(...)` | `links.adoc` | Hypermedia links if the API uses them |

Example:

```java
pathParameters(
    parameterWithName("productId")
        .description("ID of the product to look up")
),
responseFields(
    fieldWithPath("id")
        .type(JsonFieldType.NUMBER)
        .description("Product ID"),
    fieldWithPath("name")
        .type(JsonFieldType.STRING)
        .description("Display name"),
    fieldWithPath("price")
        .type(JsonFieldType.NUMBER)
        .description("Price in the API's currency unit")
)
```

The expected output is a path parameter table and a response field table, stored in `path-parameters.adoc` and `response-fields.adoc` respectively.

**Not every operation has every snippet.** A `GET` without a JSON body does not need `request-fields.adoc`. A `DELETE` returning `204 No Content` typically has no response fields table. If a test does not declare `responseHeaders(...)`, do not assume `response-headers.adoc` was generated.

## 4. Complete Example: Generating Snippets from MockMvc

Let us build a controller solely for this example. The endpoint `GET /api/products/{productId}?locale=vi` returns a sample product with ID `7`; any other product returns `404`. Real implementations may use services, repositories, and security, but here we focus purely on the snippet generation process.

### 4.1. Controller Returning Predictable Data

```java
@RestController
class ProductController {

    record ProductView(
        long id,
        String name,
        BigDecimal price,
        String locale
    ) {}

    @GetMapping(
        value = "/api/products/{productId}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<ProductView> findOne(
            @PathVariable long productId,
            @RequestParam(defaultValue = "vi") String locale) {

        if (productId != 7L) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(
            new ProductView(
                7L,
                "Notebook",
                new BigDecimal("45000"),
                locale
            )
        );
    }
}
```

The example uses Java `record` (Java 17+) and Spring MVC. You need the corresponding imports for `BigDecimal`, `RestController`, `GetMapping`, `PathVariable`, `RequestParam`, `ResponseEntity`, and `MediaType`. In a real project, use dedicated fixtures to accurately reflect business data and configure tests for each scenario.

### 4.2. Test Containing Both Assertions and Snippet Configuration

```java
@ExtendWith(RestDocumentationExtension.class)
class ProductDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new ProductController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    @Test
    void getProduct_generatesSnippets() throws Exception {
        mockMvc.perform(
                get("/api/products/{productId}", 7L)
                    .queryParam("locale", "vi")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("Notebook"))
            .andExpect(jsonPath("$.price").value(45000))
            .andDo(document("products-get-success",
                pathParameters(
                    parameterWithName("productId")
                        .description("Product identifier")
                ),
                queryParameters(
                    parameterWithName("locale")
                        .description("Display language code")
                        .optional()
                ),
                requestHeaders(
                    headerWithName("Accept")
                        .description("Response format desired by the client")
                ),
                responseFields(
                    fieldWithPath("id")
                        .type(JsonFieldType.NUMBER)
                        .description("Product ID"),
                    fieldWithPath("name")
                        .type(JsonFieldType.STRING)
                        .description("Product name"),
                    fieldWithPath("price")
                        .type(JsonFieldType.NUMBER)
                        .description("Product price"),
                    fieldWithPath("locale")
                        .type(JsonFieldType.STRING)
                        .description("Language of the response")
                )
            ));
    }
}
```

To document `{productId}`, the example must import `get` from `org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get`. This request builder stores the URI template so `pathParameters(...)` can identify variable names. `document` and `documentationConfiguration` come from `MockMvcRestDocumentation`, while `fieldWithPath`, `parameterWithName`, and `headerWithName` come from Spring REST Docs' payload/request/header API groups.

A typical set of static imports:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
```

Remaining imports include `MockMvc`, `MockMvcBuilders`, `JsonFieldType`, `RestDocumentationContextProvider`, `RestDocumentationExtension`, and the corresponding JUnit annotations. The project needs the Spring REST Docs dependency and snippet directory configuration matching the build tool in use. The example follows the Spring REST Docs 3.x API style.

### 4.3. Which Files Does the Test Generate?

When running `getProduct_generatesSnippets`, Spring REST Docs typically writes to:

```text
build/generated-snippets/products-get-success/     (Gradle)
target/generated-snippets/products-get-success/    (Maven)
```

Using the Gradle directory name in the example, the output might look like:

```text
generated-snippets/
└── products-get-success/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    ├── path-parameters.adoc
    ├── query-parameters.adoc
    ├── request-headers.adoc
    └── response-fields.adoc
```

The first six example/body files are typically the default snippet group; the last four tables are requested by the descriptors in `document(...)`. For a `GET` without a body, the contents of `request-body.adoc` may be empty. Exact paths and file sets depend on the project's output configuration and default snippet set.

**The name `products-get-success` must match between the test and the documentation.** If you rename it in `document(...)` without updating the include directive, rendering may fail with a missing file or pick up a stale file if prior output was not cleaned.

## 5. Embedding Snippets into an Asciidoctor Page

Suppose a documentation source file `src/docs/asciidoc/products.adoc` (the path varies by project) needs to present the success operation. You can write:

```asciidoc
[[products-get]]
=== Look up a product

Call this endpoint to read information about a product.
productId is the product's identifier.
If it does not exist, the API returns HTTP 404.

==== Sample request

include::{snippets}/products-get-success/http-request.adoc[]

==== Path variables

include::{snippets}/products-get-success/path-parameters.adoc[]

==== Query parameters

include::{snippets}/products-get-success/query-parameters.adoc[]

==== Request headers

include::{snippets}/products-get-success/request-headers.adoc[]

==== Successful response

include::{snippets}/products-get-success/http-response.adoc[]

==== Response JSON fields

include::{snippets}/products-get-success/response-fields.adoc[]
```

With Asciidoctor, `include::...[]` is a directive that inserts a child file's contents into the source file **at render time**. In `include::{snippets}/products-get-success/http-request.adoc[]`:

- `{snippets}` is an attribute pointing to the snippets directory, configured by the build.
- `products-get-success` is the operation identifier from `document(...)`.
- `http-request.adoc` is the fragment to display.

If the file does not exist or the attribute is misconfigured, compilation may report an error or emit a warning depending on configuration. CI should treat invalid includes as failures to resolve, never publishing a page with unresolved directives.

### 5.1. Why Not Copy Snippets into Markdown/AsciiDoc by Hand?

Suppose the JSON response renames the `price` field to `unitPrice`. If you copied that JSON block into the documentation page, the copy does not update automatically with the code. If the page uses an include pointing to `http-response.adoc` regenerated after tests, the example updates with the current response; if `responseFields(...)` still documents `price`, strict documentation testing catches the mismatch.

Thus, includes maintain **a single source for generating examples**, replacing multiple static copies. Still, the author must update business prose explaining field meanings and API usage rules when the contract changes; snippets cannot write that part themselves.

### 5.2. Embed by Reading Purpose, Not Every Available Fragment

A page may choose to include `http-request.adoc` or `curl-request.adoc`, depending on its audience. There is no need to show raw HTTP, cURL, HTTPie, and the identical request body all in one section if they merely repeat the same information.

A clear way to organize:

| Documentation section | Suggested snippet | Explanation to add |
| --- | --- | --- |
| Endpoint overview | Optional | Purpose, access permissions, preconditions |
| Call example | `http-request.adoc` or `curl-request.adoc` | When to pass parameters, default values |
| Input description | `path-parameters.adoc`, `query-parameters.adoc`, `request-fields.adoc` when present | Meaning, constraints, and valid examples |
| Result example | `http-response.adoc` | Conditions for returned status and error handling |
| Output description | `response-fields.adoc`, `response-headers.adoc` when present | Enum values, units, date/time formats |
| Error scenarios | Snippets of the corresponding error operations | Conditions for `400`, `404`, `409` and remediation |

This is a presentation choice, not a fixed requirement of the library. What matters is that readers find the information they need without piecing meaning together from disconnected examples.

## 6. Using Snippets from Multiple Operations on the Same Page

An endpoint can return multiple statuses. Write separate tests for important scenarios, such as:

```java
@Test
void getProduct_notFound() throws Exception {
    mockMvc.perform(
            get("/api/products/{productId}", 999L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isNotFound())
        .andDo(document("products-get-not-found",
            pathParameters(
                parameterWithName("productId")
                    .description("Product identifier")
            )
        ));
}
```

With the sample controller, the `404` response has no body, so this snippet does not declare `responseFields(...)`. The AsciiDoc page can add:

```asciidoc
==== When product is not found (HTTP 404)

The product ID does not exist in the system's data.

include::{snippets}/products-get-not-found/http-request.adoc[]

include::{snippets}/products-get-not-found/http-response.adoc[]
```

If the real system has a JSON error body like `{"code":"PRODUCT_NOT_FOUND","message":"..."}`, the test must actually produce and assert that body and document the corresponding error fields. Never insert a success response snippet into an error section or invent an error response that no test has proven.

### 6.1. Be Careful When “Reusing” Snippets

There are two different kinds of reuse:

1. **Reusing the generated snippet itself:** multiple pages may include `products-get-success/response-fields.adoc` when referring to **the exact same operation and the exact same schema**.
2. **Reusing a descriptor set or presentation pattern:** multiple endpoints sharing standard errors or common headers can use test helpers, documentation templates, or a shared rules page.

Do not take the response field table from `GET /api/products/7` and drop it into `POST /api/orders` just because both have an `id` field: their meanings and schemas differ. A snippet is tied to its **source operation**. When you want a shared description table, identify the contract that is genuinely shared and test it against the appropriate endpoints.

## 7. Key Characteristics of Snippets

### 7.1. Snippets Have Stable Paths and Mutable Content

`products-get-success/response-fields.adoc` is a stable location to reference, while the file's content is rewritten whenever the test runs. This is an advantage: documentation tracks current test behavior.

From this come two requirements:

- Give operations meaningful names that are easy to follow and do not collide across tests.
- Never share the same identifier across multiple tests producing different content; under parallel execution, tests can overwrite each other's output.

If you need to display both `200` and `404`, naming them `products-get-success` and `products-get-not-found` is much clearer than sharing `products-get`.

### 7.2. Snippets Reflect Post-Preprocessed Data

Spring REST Docs can apply preprocessors when generating snippets to pretty-print JSON, normalize URIs, remove noisy headers, or mask sensitive data with placeholder values. For example:

```java
.andDo(document("products-get-success",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint()),
    responseFields(
        fieldWithPath("id").description("Product ID"),
        fieldWithPath("name").description("Product name"),
        fieldWithPath("price").description("Product price"),
        fieldWithPath("locale").description("Language")
    )
));
```

This is **an illustrative snippet showing a different `document(...)` configuration**, not a drop-in replacement for the full test example above since input descriptors were omitted. `preprocessRequest`, `preprocessResponse`, and `prettyPrint` belong to `org.springframework.restdocs.operation.preprocess.Preprocessors`.

When rendering public documentation, safe fixture data must be used. Avoid letting real tokens, cookies, personal data, internal hostnames, or credentials enter snippets. At the same time, preprocessors only alter presentation; tests must keep assertions verifying real behavior so API discrepancies are never masked.

### 7.3. Snippets Are AsciiDoc Files Under Common Configuration

Most Spring REST Docs examples use **Asciidoctor** templates, so outputs have the `.adoc` extension. If your project uses Markdown, do not rename `response-fields.adoc` to `response-fields.md` and embed it directly: table syntax, source blocks, and directives may be incompatible.

Common implementation approaches include:

- Using Asciidoctor as the documentation source and converting it to HTML/PDF or an intermediate format.
- Configuring snippet templates to match the desired output format with an injection step into Markdown suited to your tooling.
- Using a pipeline that generates Markdown from verified data/snippets with an output check step.

**Markdown has no single standardized include syntax.** The `include::{snippets}/...[]` syntax belongs to Asciidoctor; using it in Markdown requires a compiler or plugin that explicitly supports it.

### 7.4. Snippets Cannot Document Every Business Rule

A `response-fields` table can state that `price` is a number and describe it as “Product price”. Yet a sample request cannot prove all rounding rules, currency units, tax-inclusive pricing, permissions to view prices, or time-based price validity. To state those rules, you need accurate business documentation and corresponding tests if they form part of the public contract.

## 8. Organizing Large Documentation with Sections and Links

As the number of endpoints grows, organize documentation by resource or business domain. Example:

```text
src/docs/asciidoc/
├── index.adoc              (entry point)
├── introduction.adoc       (base URL, authentication, conventions)
├── products.adoc           (product resource)
├── orders.adoc             (order resource)
└── errors.adoc             (common error format)

build/generated-snippets/
├── products-get-success/
├── products-get-not-found/
├── products-create-success/
├── orders-get-success/
└── orders-create-invalid/
```

The `index.adoc` file can assemble the sections into a larger document:

```asciidoc
= API Reference
:toc: left
:toclevels: 3

include::introduction.adoc[]

include::products.adoc[]

include::orders.adoc[]

include::errors.adoc[]
```

There are **two distinct levels of include** here:

- `include::products.adoc[]` pulls a **page or content section** into the master document.
- `include::{snippets}/products-get-success/http-response.adoc[]` pulls a **test-generated snippet** inside that page.

Layered organization lets authors control the overarching narrative while request/response samples and field tables are managed from tests. Avoid putting hundreds of ungrouped includes on one page; use sections and headings so readers understand which scenario each fragment describes.

## 9. Build and CI Ensure Snippets Have a Clear Source

Because snippets are test outputs, the documentation compilation step **must run after the snippet-generation step**. For a Gradle project with a properly configured Asciidoctor plugin, wiring might look like this (Groovy DSL, illustrative):

```groovy
def snippetsDir = file("build/generated-snippets")

tasks.named("test") {
    outputs.dir snippetsDir
}

tasks.named("asciidoctor") {
    dependsOn tasks.named("test")
    inputs.dir snippetsDir
    attributes "snippets": snippetsDir
}
```

This configuration assumes the project already has `test` and `asciidoctor` tasks, the Spring REST Docs dependency, and the appropriate plugins. Task configuration syntax may need adjustments depending on Gradle and Asciidoctor plugin versions. For Maven, the idea is similar: tests generate snippets in `target/generated-snippets`, and the documentation plugin is bound to the right phase and receives the snippet path as an attribute.

Desired build flow:

```text
Source code + tests + descriptors + .adoc pages
                  │
                  ▼
              Run HTTP tests
                  │
             ┌────┴────┐
             │         │
           FAIL       PASS
             │         │
        Stop build   Generate snippets
                       │
                       ▼
             Render docs with includes
                       │
                ┌──────┴──────┐
                │             │
           Missing file      PASS
                │             │
           Stop build     HTML/PDF/site
```

In CI, run from a clean output directory or ensure stale outputs are properly purged before verification. If documentation tests are skipped, leftover snippets can let the page still compile, creating the false impression that the documentation is verified against current code.

### 9.1. How Are API Changes Reflected?

Suppose the product response changes from:

```json
{"id":7,"name":"Notebook","price":45000,"locale":"vi"}
```

to:

```json
{"id":7,"name":"Notebook","unitPrice":45000,"locale":"vi"}
```

In a test using `responseFields(...)` with `price` and strict checking, documentation validation detects that the schema no longer matches. The developer must confirm this is an intentional contract change, update the descriptors and relevant assertions, and regenerate snippets. The AsciiDoc page using includes will pick up the updated field table and response example once tests pass.

Conversely, if the page only had hand-copied JSON, changing the API would not trigger this validation link. That is the practical benefit of embedding test-generated snippets.

### 9.2. Checking Output Quality

Once an Asciidoctor or Markdown page finishes rendering, verify:

1. No unresolved include directives remain.
2. All examples show the right operation and right HTTP status.
3. Field tables contain all contract fields with clear meanings.
4. Internal links, table of contents, and headings are not confusing.
5. No secrets or internal environment data appear in public snippets.

These checks complement tests. Tests protect the correctness of tested behavior; output checks protect the **assembly and presentation** of documentation fragments.

## 10. Common Errors When Working with Snippets

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `include` reports missing `response-fields.adoc` | Test did not declare `responseFields(...)` or did not run | Add appropriate descriptors and run the right test task |
| Directory `products-get-success` does not exist | Name in `document(...)` differs from page or test was skipped | Cross-check identifiers and test execution logs |
| Page still shows an old response | Leftover snippets or render task does not depend on tests | Run a clean build and wire tasks in the proper order |
| Path parameter table cannot be generated | Builder does not preserve URI template or descriptor name is wrong | Use `RestDocumentationRequestBuilders` with `{productId}` |
| Duplicate content when embedding | Multiple fragments repeating the same HTTP/body info were included together | Choose snippets tailored to each section's purpose |
| `response-fields.adoc` does not match JSON | Test schema changed without updating descriptors | Confirm contract, then update tests, descriptors, and prose |
| Two tests write to the same snippet directory | Reused identical identifier for different responses | Assign scenario-specific identifiers |
| Markdown renders raw Asciidoctor syntax | Markdown pipeline does not support includes/adoc | Convert or configure appropriate tooling/templates |
| Examples expose sensitive tokens or hostnames | Test operation contains data unfit for publishing | Use dummy fixtures, preprocessors, or safe scrubbing steps |
| Documentation consists only of tables and code blocks | Business descriptions are missing | Add usage conditions, meanings, errors, and general rules |

## 11. Hands-On Exercise: From Small Fragments to a Complete API Page

Document the `GET /api/products/{productId}` endpoint with two scenarios: product exists (`200`) and not found (`404`).

**Implementation requirements:**

1. Write two MockMvc tests using identifiers `products-get-success` and `products-get-not-found`.
2. In the `200` test, document `productId`, `locale`, the `Accept` header, and response fields; assert the status and business values.
3. In the `404` test, assert the status and only document elements that actually appear in the response.
4. Run the tests and inspect `http-request.adoc`, `http-response.adoc`, `path-parameters.adoc`, and `response-fields.adoc` in the corresponding operation directories.
5. Create an AsciiDoc page with an introduction, successful request, parameter tables, successful response, and a `404` error section. Include only files that were actually generated.
6. Compile the page, then temporarily rename `products-get-success` in the test without updating the page. Observe the missing include error; restore the name and rerun.
7. Try adding a new JSON field to the response without documenting it; when using strict response field documentation, the test must catch the change. Update descriptors to match the contract and regenerate the documentation.

**Passing criteria:** every snippet on the page has a concrete test source; explanations help readers understand when to call the endpoint; documentation regenerates on a clean build and catches missing files or schema drift within the tested scope.

## 12. Takeaways

- **Snippets** are documentation content fragments generated from **HTTP operations in tests** and can be embedded into Asciidoctor pages or an appropriate Markdown compilation workflow.
- **One operation produces multiple snippets**; each fragment presents one part of the request/response or a table describing fields, parameters, and headers.
- **Large documentation pages** combine snippets with business explanations, organized by endpoint and success/error scenarios.
- **Stable identifiers, complete descriptors, proper build ordering, and CI from clean outputs** prevent snippet mix-ups and keep documentation aligned with tested API parts.
- **Snippets are verifiable sources of examples, not replacements** for access control rules, business logic, and test scope caveats that documentation authors must clarify.
