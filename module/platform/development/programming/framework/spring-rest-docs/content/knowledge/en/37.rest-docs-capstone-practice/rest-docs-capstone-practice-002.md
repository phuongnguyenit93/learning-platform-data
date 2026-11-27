# Documenting CRUD Resources with Request and Response Fields

## 1. Practice Objectives

In this capstone, you will document a REST resource with full CRUD operations using Spring REST Docs and MockMvc. Each HTTP operation is tested with realistic requests and responses; descriptors document payload fields, path parameters, query parameters, and headers. Generated snippets are assembled into Asciidoctor/Markdown documentation and integrated into the build and CI.

The sample resource is Product:

| HTTP method | Endpoint | Purpose | Success status |
| --- | --- | --- | --- |
| GET | /api/products | List products | 200 OK |
| GET | /api/products/{id} | Get a single product | 200 OK |
| POST | /api/products | Create a product | 201 Created |
| PUT | /api/products/{id} | Replace product information | 200 OK |
| PATCH | /api/products/{id} | Partially update | 200 OK |
| DELETE | /api/products/{id} | Delete a product | 204 No Content |

Not every API needs both PUT and PATCH. This exercise includes both to clarify the request contract for full resource replacement versus partial update.

## 2. Designing Payloads and Resource Contracts

A Product has the following JSON structure:

~~~json
{
  "id": "p-42",
  "name": "Mechanical Keyboard",
  "description": "75% layout mechanical keyboard",
  "price": 1299000,
  "currency": "VND",
  "active": true
}
~~~

The create-product request does not contain `id` because the server assigns the identifier:

~~~json
{
  "name": "Mechanical Keyboard",
  "description": "75% layout mechanical keyboard",
  "price": 1299000,
  "currency": "VND",
  "active": true
}
~~~

The PATCH request contains only the fields that need to change:

~~~json
{
  "price": 1199000,
  "active": false
}
~~~

The examples use stable mock data. Choose a dataset that is reproducible in tests so snippets do not change randomly between builds.

## 3. Sample DTOs and Controller

Define separate request/response DTOs to distinguish fields sent by the client from fields returned by the server:

~~~java
record CreateProductRequest(String name, String description,
        BigDecimal price, String currency, boolean active) {}

record ReplaceProductRequest(String name, String description,
        BigDecimal price, String currency, boolean active) {}

record UpdateProductRequest(BigDecimal price, Boolean active) {}

record ProductResponse(String id, String name, String description,
        BigDecimal price, String currency, boolean active) {}
~~~

Controller illustrating the routes and statuses:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping
    List<ProductResponse> list() { /* delegate to service */ }

    @GetMapping("/{id}")
    ProductResponse get(@PathVariable String id) { /* delegate to service */ }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
        /* delegate to service */
    }

    @PutMapping("/{id}")
    ProductResponse replace(@PathVariable String id,
            @Valid @RequestBody ReplaceProductRequest request) {
        /* delegate to service */
    }

    @PatchMapping("/{id}")
    ProductResponse update(@PathVariable String id,
            @RequestBody UpdateProductRequest request) {
        /* apply partial update */
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void delete(@PathVariable String id) { /* delegate to service */ }
}
~~~

The method bodies are integration points with services/repositories, not standalone runnable implementations. When applying this to a real project, ensure the actual DTOs, validation, and statuses match the chosen contract.

## 4. Configuring MockMvc and REST Docs

With Spring Boot tests, you can use auto-configuration:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductCrudDocumentationTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

If using manual configuration, apply `documentationConfiguration(...)` to the MockMvc builder. Choose only one configuration approach per test context to avoid registering REST Docs multiple times.

## 5. GET Collection: Documenting Response Fields and Query Parameters

The `GET /api/products` endpoint returns a list. Suppose the API supports pagination with `page` and `size`:

~~~java
@Test
void listProducts() throws Exception {
    mockMvc.perform(get("/api/products")
                    .queryParam("page", "0")
                    .queryParam("size", "20")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andDo(document("products-list",
                    queryParameters(
                            parameterWithName("page").description("Page number, zero-based"),
                            parameterWithName("size").description("Maximum number of items per page")),
                    responseFields(
                            fieldWithPath("items").description("List of products"),
                            fieldWithPath("items[].id").description("Product ID"),
                            fieldWithPath("items[].name").description("Product name"),
                            fieldWithPath("items[].description").description("Description"),
                            fieldWithPath("items[].price").description("Price"),
                            fieldWithPath("items[].currency").description("Currency code"),
                            fieldWithPath("items[].active").description("Active status"),
                            fieldWithPath("page").description("Current page"),
                            fieldWithPath("size").description("Page size"),
                            fieldWithPath("totalElements").description("Total number of products"))));
}
~~~

This example assumes the response has a pagination envelope containing `items`, `page`, `size`, and `totalElements`. If the API returns a JSON array directly or uses different field names, adjust the descriptors to match the actual payload. With a root JSON array, paths typically start with `[]` instead of `items[]`.

## 6. GET Resource: Path Parameter and Response Fields

~~~java
@Test
void getProduct() throws Exception {
    mockMvc.perform(get("/api/products/{id}", "p-42")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("p-42"))
            .andDo(document("products-get",
                    pathParameters(parameterWithName("id").description("Product ID")),
                    responseFields(
                            fieldWithPath("id").description("Product ID"),
                            fieldWithPath("name").description("Product name"),
                            fieldWithPath("description").description("Product description"),
                            fieldWithPath("price").description("Product price"),
                            fieldWithPath("currency").description("Currency code"),
                            fieldWithPath("active").description("Whether the product is active"))));
}
~~~

In MockMvc, use a URI template with the `id` variable so REST Docs recognizes the path parameter. If your Spring Framework version requires a dedicated builder to retain URI template variables, use `RestDocumentationRequestBuilders` according to that version's documentation.

## 7. POST Resource: Request Fields and Response Fields

Creating a resource with POST typically returns `201 Created` and the new representation:

~~~java
@Test
void createProduct() throws Exception {
    mockMvc.perform(post("/api/products")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Mechanical Keyboard",
                              "description": "75% layout mechanical keyboard",
                              "price": 1299000,
                              "currency": "VND",
                              "active": true
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("p-100"))
            .andDo(document("products-create",
                    requestFields(
                            fieldWithPath("name").description("Product name"),
                            fieldWithPath("description").description("Product description"),
                            fieldWithPath("price").description("Product price"),
                            fieldWithPath("currency").description("Currency code"),
                            fieldWithPath("active").description("Active status")),
                    responseFields(
                            fieldWithPath("id").description("Server-assigned product ID"),
                            fieldWithPath("name").description("Product name"),
                            fieldWithPath("description").description("Product description"),
                            fieldWithPath("price").description("Product price"),
                            fieldWithPath("currency").description("Currency code"),
                            fieldWithPath("active").description("Active status"))));
}
~~~

Do not include `id` in request fields if the client does not send `id`. This is an important distinction between the request contract and the response contract.

## 8. PUT Resource: Documenting a Full Replacement Request

PUT typically requires a full representation according to the API contract. If all fields are required, descriptors should be strict:

~~~java
@Test
void replaceProduct() throws Exception {
    mockMvc.perform(put("/api/products/{id}", "p-42")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Mechanical Keyboard Pro",
                              "description": "Mechanical keyboard with rotary knob",
                              "price": 1499000,
                              "currency": "VND",
                              "active": true
                            }
                            """))
            .andExpect(status().isOk())
            .andDo(document("products-replace",
                    pathParameters(parameterWithName("id").description("Product ID")),
                    requestFields(
                            fieldWithPath("name").description("Replacement name"),
                            fieldWithPath("description").description("Replacement description"),
                            fieldWithPath("price").description("Replacement price"),
                            fieldWithPath("currency").description("Currency code"),
                            fieldWithPath("active").description("Active status")),
                    responseFields(
                            fieldWithPath("id").description("Product ID"),
                            fieldWithPath("name").description("Updated product name"),
                            fieldWithPath("description").description("Updated description"),
                            fieldWithPath("price").description("Updated price"),
                            fieldWithPath("currency").description("Currency code"),
                            fieldWithPath("active").description("Active status"))));
}
~~~

If the API allows partial PUT or has server-managed fields, descriptors must reflect the actual contract rather than inferring solely from the HTTP method.

## 9. PATCH Resource: Optional Fields

PATCH typically accepts a partial payload. Fields that may be omitted must be marked as `optional`:

~~~java
@Test
void patchProduct() throws Exception {
    mockMvc.perform(patch("/api/products/{id}", "p-42")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "price": 1199000,
                              "active": false
                            }
                            """))
            .andExpect(status().isOk())
            .andDo(document("products-patch",
                    pathParameters(parameterWithName("id").description("Product ID")),
                    requestFields(
                            fieldWithPath("price").optional()
                                    .description("New price if a change is needed"),
                            fieldWithPath("active").optional()
                                    .description("New status if a change is needed")),
                    responseFields(
                            fieldWithPath("id").description("Product ID"),
                            fieldWithPath("name").description("Product name"),
                            fieldWithPath("description").description("Product description"),
                            fieldWithPath("price").description("Current price"),
                            fieldWithPath("currency").description("Currency code"),
                            fieldWithPath("active").description("Current status"))));
}
~~~

An `optional` descriptor does not mean `null` values and absent fields are always equivalent. Rules for handling `null`, clearing fields, or ignoring fields must be defined in the API and have dedicated tests if important.

## 10. DELETE Resource: Response Without a Body

DELETE may return `204 No Content`. When a response has no body, do not declare `responseFields` for a non-existent payload:

~~~java
@Test
void deleteProduct() throws Exception {
    mockMvc.perform(delete("/api/products/{id}", "p-42"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""))
            .andDo(document("products-delete",
                    pathParameters(
                            parameterWithName("id").description("ID of the product to delete"))));
}
~~~

If the API returns `200` with a deletion confirmation body or `202 Accepted` for asynchronous processing, document the actual response and explain the corresponding semantics.

## 11. Reusing Descriptors Without Misrepresenting the Contract

You can reuse standard descriptions for fields that are genuinely identical, such as `currency` or `active`. However, do not share descriptors solely because field names match if their required/optional status or meaning differs.

~~~java
static FieldDescriptor currencyField() {
    return fieldWithPath("currency")
            .description("ISO 4217 currency code")
            .attributes(key("example").value("VND"));
}

static FieldDescriptor optionalPatchPriceField() {
    return fieldWithPath("price")
            .optional()
            .description("New price if a change is needed")
            .attributes(key("unit").value("VND"));
}
~~~

Factories create a fresh descriptor for each operation. Keep request descriptors separate from response descriptors; server-assigned `id` fields should not be placed into the request contract if the client does not send them.

## 12. Assembling CRUD Snippets into AsciiDoc

Create `api-guide.adoc` and include the snippets for each operation:

~~~adoc
= Product API
:toc:
:sectnums:

== List Products
include::{snippets}/products-list/http-request.adoc[]
include::{snippets}/products-list/query-parameters.adoc[]
include::{snippets}/products-list/http-response.adoc[]
include::{snippets}/products-list/response-fields.adoc[]

== Get Product
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/path-parameters.adoc[]
include::{snippets}/products-get/http-response.adoc[]
include::{snippets}/products-get/response-fields.adoc[]

== Create Product
include::{snippets}/products-create/http-request.adoc[]
include::{snippets}/products-create/request-fields.adoc[]
include::{snippets}/products-create/http-response.adoc[]
include::{snippets}/products-create/response-fields.adoc[]

== Replace Product
include::{snippets}/products-replace/http-request.adoc[]
include::{snippets}/products-replace/path-parameters.adoc[]
include::{snippets}/products-replace/request-fields.adoc[]
include::{snippets}/products-replace/http-response.adoc[]

== Partially Update Product
include::{snippets}/products-patch/http-request.adoc[]
include::{snippets}/products-patch/path-parameters.adoc[]
include::{snippets}/products-patch/request-fields.adoc[]
include::{snippets}/products-patch/http-response.adoc[]

== Delete Product
include::{snippets}/products-delete/http-request.adoc[]
include::{snippets}/products-delete/path-parameters.adoc[]
include::{snippets}/products-delete/http-response.adoc[]
~~~

Only include snippets that the operation actually generates. If an endpoint has no body or a snippet is not configured, do not add a fake include for a non-existent file.

## 13. Running and Verifying the Entire Workflow

Build order:

~~~text
Clean generated snippets
          |
          v
Run MockMvc documentation tests
          |
          v
Verify status and descriptor coverage
          |
          v
Generate CRUD snippets
          |
          v
Run Asciidoctor
          |
          v
Inspect HTML artifact
~~~

With Gradle:

~~~bash
./gradlew clean test
./gradlew asciidoctor
~~~

Or run in a single command if the `asciidoctor` task already declares `dependsOn test`:

~~~bash
./gradlew clean asciidoctor
~~~

After the build, verify that each operation has its own snippet directory; path/query parameter snippets match the routes and filters; request fields do not contain server-generated-only fields; response fields document the full payload; PATCH marks fields that may be omitted according to the contract; DELETE does not include a response body if status is 204; and the HTML documentation has no missing includes.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| POST request fields contain `id` | Using the response DTO as the request descriptor | Separate request and response contracts |
| PATCH test fails when a field is omitted | Descriptor is not marked `optional` | Use `optional()` for fields allowed to be absent |
| GET list cannot find fields | Response is an array or different envelope than assumed | Inspect actual JSON and fix paths |
| PUT omits a field yet test still passes | Using `relaxed` or overly broad `optional` | Use strict descriptors for the full contract |
| DELETE has no `response-fields` snippet | 204 response has no body | Do not declare `responseFields` for an empty body |
| Path parameter is not generated | Request builder does not retain URI template variables | Use the REST Docs builder appropriate for your version |
| Asciidoctor is missing an include file | Wrong identifier or test has not generated snippets | Align `document` identifier and include path |
| Stale snippets remain | Output directory was not cleaned | Run `clean` before documentation tests |

## 15. Capstone Exercise

Complete the CRUD documentation for Product:

1. Document `GET` collection with `page` and `size` query parameters and response envelope.
2. Document `GET` item with `id` path parameter and response fields.
3. Document `POST` with request fields, response fields, and status 201.
4. Document `PUT` with the full request representation per the contract.
5. Document `PATCH` with optional fields and a dedicated test for updating only a single field.
6. Document `DELETE` with status 204 and no response body.
7. Add 404 error responses for GET/PUT/DELETE and document the error payload.
8. Include all snippets in an AsciiDoc page.
9. Run a clean build and verify the HTML.

**Completion criteria:** all CRUD operations have documentation tests; request/response fields match the DTOs; path/query parameters are documented; optionality is accurate; snippets are generated from current tests and the Asciidoctor documentation builds cleanly.

## 16. Checklist Before Adding to CI

- [ ] Each CRUD operation has a test and a unique operation identifier.
- [ ] HTTP status and media type are asserted.
- [ ] Request fields and response fields are separated by DTO.
- [ ] Path/query parameters are documented according to actual routes.
- [ ] PATCH marks `optional` only on fields that can genuinely be omitted.
- [ ] DELETE 204 declares no response body.
- [ ] Error responses are tested and documented.
- [ ] Old snippet output is cleaned before building.
- [ ] AsciiDoc includes point to the exact identifiers and generated files.
- [ ] CI runs documentation tests before Asciidoctor and archives the HTML artifact.

**Remember:** Good CRUD documentation needs to describe the request and response of each operation separately. GET, POST, PUT, PATCH, and DELETE have different contracts; using MockMvc assertions together with strict field descriptors ensures snippets accurately reflect the API and catch payload changes.
