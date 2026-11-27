# Naming Stable Operation Directories

## 1. How Does the Identifier Determine Snippet Location?

**Spring REST Docs** generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. From the executed request and response, the tool writes **snippets** describing the HTTP message, payload, parameters, and headers. Snippets are then included into Asciidoctor/Markdown documentation and the build/CI pipeline so documentation can be regenerated alongside source code.

With MockMvc, each documentation call usually looks like:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andDo(document("books-get"));
~~~

The string `"books-get"` is the operation's **identifier**. Spring REST Docs uses this identifier as the base path for the generated snippet group. With Gradle's default output, the path typically looks like:

~~~text
build/generated-snippets/
└── books-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    └── response-body.adoc
~~~

The illustrative file list depends on default snippets, version, and project configuration. The key point is that all snippets from this operation recording are placed under the `books-get` directory. Asciidoctor documentation can reference them via:

~~~adoc
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/http-response.adoc[]
~~~

The identifier is not just a display label in the test. It is **part of the output file structure and the contract between tests and documentation**. If the identifier changes, include paths must also change.

## 2. What Makes a Stable Identifier?

A good identifier should satisfy four criteria:

1. **Business-meaningful:** reading the name reveals which operation or resource is being documented.
2. **Stable:** does not change simply because a test class or method is renamed, tests are reordered, or sample data changes without altering the contract.
3. **Unique:** two different operations never write to the same snippet directory.
4. **Easy to reference:** short, readable, free of characters that make paths awkward on the OS or in Asciidoctor includes.

Practical convention:

~~~text
<resource>-<http-action>-<scenario>
~~~

| Identifier | Operation | Meaning |
| --- | --- | --- |
| `books-list` | `GET /api/books` | List books |
| `books-get` | `GET /api/books/{id}` | Read a single book |
| `books-create` | `POST /api/books` | Create a book |
| `books-update` | `PUT /api/books/{id}` | Update a book |
| `books-delete` | `DELETE /api/books/{id}` | Delete a book |
| `books-get-not-found` | `GET /api/books/{id}` returning `404` | Not found |
| `books-create-invalid` | `POST /api/books` returning error code per contract | Invalid creation data |

You can add an API version or resource group prefix:

~~~text
v1-books-get
v1-books-create
v2-books-get
admin-users-list
public-catalog-search
~~~

Do not embed every request detail into the directory name. ID values, dynamic query strings, timestamps, or random data belong to **operation data**, not the operation type identifier. Do not create `books-get-bk-101` and `books-get-bk-102` just because tests use two different book IDs. Both requests describe the same `GET /api/books/{id}` contract; `books-get` is usually the appropriate identifier.

## 3. Distinguishing Identifiers from Test Method Names and URIs

| Component | Example | Role |
| --- | --- | --- |
| Test method name | `getBookReturnsBookDetails()` | Explains the test goal in Java code. |
| URI template | `/api/books/{id}` | Describes the HTTP path and path parameter. |
| Identifier | `books-get` | Determines the directory containing generated snippets. |

Example:

~~~java
@Test
void getBookReturnsBookDetails() throws Exception {
    mockMvc.perform(get("/api/books/{id}", "bk-101")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("books-get"));
}
~~~

The method name can be changed to `readBook()` without changing the identifier. The URI can move from `/api/books/{id}` to `/api/v1/books/{id}` if the API is versioned. The identifier can remain `books-get` if you want snippet groups keyed by stable operation name; if v1 and v2 are published side by side, add a namespace to avoid collisions.

If using the `{method-name}` placeholder, renaming the test changes the snippet directory and forces include updates. This is convenient when test names directly define the desired documentation structure, but **not optimal if stable documentation paths across test refactors are needed**.

## 4. Designing Naming Conventions by Resource and Action

### 4.1. Using Clear Resource Nouns and Actions

In REST APIs, nouns represent resources; HTTP methods represent action types:

~~~text
orders-list       GET    /api/orders
orders-get        GET    /api/orders/{id}
orders-create     POST   /api/orders
orders-replace    PUT    /api/orders/{id}
orders-update     PATCH  /api/orders/{id}
orders-delete     DELETE /api/orders/{id}
~~~

`orders-get` is clearer than generic names like `get1`, `test2`, or `api-call`. When an endpoint has multiple GET operations, qualify the meaning:

~~~text
orders-list
orders-search
orders-get
orders-get-history
orders-get-summary
~~~

### 4.2. Adding Scenarios When One Endpoint Has Multiple Documented Outcomes

~~~text
orders-get
orders-get-not-found
orders-get-forbidden
orders-get-invalid-id
~~~

Only split a scenario into its own identifier when it deserves to appear as an independent HTTP example in documentation. There is no need to create separate snippets for internal branches that make no meaningful difference to clients.

### 4.3. Using Lowercase and Hyphens

The `kebab-case` convention is usually easy to read:

~~~text
payment-methods-list
payment-methods-create
payment-methods-delete
~~~

Consistently use lowercase and hyphens, avoiding spaces, diacritics, special characters, and redundant separators. Choose consistent verbs for the same concept—such as `get` rather than mixing `read`/`fetch`/`retrieve` without a business reason. Spring REST Docs permits hierarchical directory identifiers, though flat kebab-case names are simpler for newer teams.

## 5. Fixed Naming for Operations in MockMvc

Example of a book controller with three operations. Each test chooses a meaningful identifier independent of the method name:

~~~java
@Test
void getBookReturnsDetails() throws Exception {
    mockMvc.perform(get("/api/books/{id}", "bk-101")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("books-get",
                    pathParameters(
                            parameterWithName("id").description("Book ID")),
                    responseFields(
                            fieldWithPath("id").description("Book ID"),
                            fieldWithPath("title").description("Book title"))));
}

@Test
void createBookReturnsLocation() throws Exception {
    mockMvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"REST Docs Guide\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andDo(document("books-create",
                    requestFields(
                            fieldWithPath("title").description("Book title"))));
}

@Test
void getMissingBookReturnsNotFound() throws Exception {
    mockMvc.perform(get("/api/books/{id}", "missing"))
            .andExpect(status().isNotFound())
            .andDo(document("books-get-not-found"));
}
~~~

These are test snippets illustrating `document(...)` calls; place them inside a test class configured with MockMvc and Spring REST Docs. In practice, add body/header assertions and corresponding descriptors before writing snippets.

After running the tests, the directory tree may look like:

~~~text
build/generated-snippets/
├── books-get/
├── books-create/
└── books-get-not-found/
~~~

When method names are refactored, the directories stay intact because the identifiers are fixed strings. This is a major advantage when documentation references snippets via stable paths.

## 6. Multiple HTTP Operations in One Test Method

A single test may send multiple sequential requests, such as creating and then reading back a resource:

~~~java
@Test
void createThenReadBook() throws Exception {
    mockMvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New book\"}"))
            .andExpect(status().isCreated())
            .andDo(document("books-create"));

    mockMvc.perform(get("/api/books/{id}", "bk-102"))
            .andExpect(status().isOk())
            .andDo(document("books-get-after-create"));
}
~~~

Each `perform(...)` represents a distinct HTTP operation. A test method with two requests needs two identifiers to record two separate snippet groups. Never reuse a single `books-flow` identifier for both responses, as the second operation's files can overwrite files of the same name from the first operation.

If documentation needs to show a multi-step flow, keep snippets separated by operation and describe the sequence on the Asciidoctor page:

~~~adoc
== Create and Read Book

=== Step 1: Create Book
include::{snippets}/books-create/http-request.adoc[]
include::{snippets}/books-create/http-response.adoc[]

=== Step 2: Read Newly Created Book
include::{snippets}/books-get-after-create/http-request.adoc[]
include::{snippets}/books-get-after-create/http-response.adoc[]
~~~

## 7. Dynamic Placeholders: When to Use and Avoid

Spring REST Docs supports placeholders in identifiers to use test context:

~~~java
document("{method-name}");
document("{class-name}/{method-name}");
document("catalog/{method-name}");
~~~

Placeholders are helpful when each test method produces exactly one operation, method names serve as official documentation names, the test suite enforces strict naming conventions, or you want snippets automatically partitioned by test class.

Static identifiers are preferable when include paths must remain stable across class/method renames, a single method executes multiple operations, or test names describe implementation details while documented operation names should stay concise and business-oriented.

| Criterion | Static Identifier | Dynamic Placeholder |
| --- | --- | --- |
| Stability when refactoring test names | High | Paths may change |
| Minimal per-request naming effort | Lower if each operation needs its own name | High |
| Multiple operations per method | Easy to assign distinct names per request | Requires suffixes or explicit names |
| Business-language folder naming | Direct control | Dependent on test names |

A hybrid pattern combines a fixed prefix with a placeholder:

~~~java
document("catalog/{method-name}");
~~~

This groups snippets by resource while still depending on method names. If absolute stability is required, use fixed identifiers like `catalog-search` or `catalog-get`.

## 8. Avoiding Collisions Under Parallel Test Execution

If two requests write to the same identifier, they target the same directory. If two tests run in parallel and write the same snippet files, output can depend on completion order. Therefore:

- Each independent operation needs its own identifier.
- Never share an identifier between success and error scenarios if they produce different snippets.
- Never reuse an identifier across different test classes if descriptors or responses differ.
- Under parallel test execution, partition identifiers by test/operation group and avoid writers competing on the same path.

Partitioning example:

~~~text
v1-books-get
v1-books-create
v2-books-get
v2-books-create
admin-books-get
public-books-search
~~~

Unique identifiers do not replace proper output directory management or cleaning stale snippets in the build. Have the build write outputs into a generated directory and ensure test/documentation tasks execute in a clear sequence.

## 9. Following Team Identifier Conventions

A convention should be documented and applied consistently:

~~~text
<api-version>-<resource>-<action>[-<scenario>]
~~~

If there is only one API version, omit the `api-version` segment:

~~~text
<resource>-<action>[-<scenario>]
~~~

| Poor Name | Recommended Name | Reason |
| --- | --- | --- |
| `test1` | `books-get` | Conveys resource and action |
| `getBookTest` | `books-get` | Decouples test name from identifier |
| `books-bk101` | `books-get` | Avoids tying folder names to sample data |
| `books-get-success-200-json` | `books-get` | Avoids putting details already shown inside snippets into the name |
| `orders` used for GET and POST | `orders-list` and `orders-create` | Each operation has its own directory |
| `bookNotFoundTestV2` | `books-get-not-found` or `v2-books-get-not-found` | Readable name with clear scope |

Rules should be descriptive enough to prevent collisions and identify operations without turning identifiers into long sentences.

Before adding a new identifier, check: what is the resource, which HTTP method/operation is it, is it a special scenario needing its own snippets, does the name already exist, will the folder name stay stable across test refactors, and which path will the documentation page reference?

## 10. Linking Identifiers to Asciidoctor and Markdown

Stable identifiers let documentation reference snippets using fixed paths:

~~~adoc
= Books API

== List Books
include::{snippets}/books-list/http-request.adoc[]
include::{snippets}/books-list/http-response.adoc[]

== View a Book
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/path-parameters.adoc[]
include::{snippets}/books-get/http-response.adoc[]

== Create Book
include::{snippets}/books-create/http-request.adoc[]
include::{snippets}/books-create/request-fields.adoc[]
include::{snippets}/books-create/http-response.adoc[]

== Book Not Found
include::{snippets}/books-get-not-found/http-response.adoc[]
~~~

`{snippets}` must point to Spring REST Docs' output directory. Include files must match the exact identifier and actual snippet filenames. For Markdown, use the conversion/embedding mechanism designed by your project; default snippets are usually AsciiDoc.

When renaming an identifier, simultaneously update the identifier string in the test/handler, all Asciidoctor include paths, any Markdown snippet-conversion scripts/templates, and references in the build pipeline. Do not rename output folders manually after tests run; the identifier in test code is the source of truth for the next build.

## 11. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Asciidoctor reports missing include file | Identifier in test differs from path in include | Open `generated-snippets`, verify folder names, and update the include. |
| Snippets from two operations are mixed | Two requests share the same identifier | Assign distinct identifiers by resource, method, and scenario. |
| Refactoring test names breaks docs build | Identifier uses `{method-name}` or `{class-name}` | Switch to static identifiers for stable paths, or update includes to match new names. |
| Snippet directory has confusing name | Identifier was based on technical test name or sample data | Rename to a short business-operation name. |
| Two parallel tests write to same folder | Identifier is not unique | Partition identifiers, prevent competing writers, and manage parallel execution. |
| No snippets found after tests | Request lacks handler or test stopped before document step | Check `andDo(document(...))`, assertions, and `documentationConfiguration(...)`. |
| Old snippet files remain after rename | Output directory holds artifacts from prior run | Clean output using the project's standard clean/build task and re-run tests. |
| Placeholder creates unexpected folder | Identifier resolution not checked | Inspect actual generated folders before writing includes. |

## 12. Practice Exercises

1. Write three tests for `GET /api/books`, `GET /api/books/{id}`, and `POST /api/books`. Use identifiers `books-list`, `books-get`, and `books-create`.
2. Rename the test methods while keeping fixed identifiers; verify the folders do not change.
3. Add a `GET` test returning `404` using `books-get-not-found`. Put both snippet groups into two separate subsections in Asciidoctor.
4. Create a test method performing POST then GET. Assign different identifiers to the two requests, then build documentation describing both steps sequentially.
5. Try using `{method-name}`, rename the method, and inspect the new snippet path. Compare the cost of updating includes with static identifiers.
6. Check a parallel test suite: find duplicate identifiers and fix the naming convention before integrating into CI.

**Completion criteria:** operation names are meaningful and stable; no two different operations write to the same directory; test refactoring does not accidentally break documentation paths; Asciidoctor/Markdown references exact snippets generated from the current test run.

## 13. Checklist Before Adding a New Identifier

- [ ] Identifier describes the resource and operation, not merely the test name.
- [ ] Follows a consistent convention, preferring lowercase and hyphens.
- [ ] Distinct error/response scenarios have separate identifiers when documented independently.
- [ ] Identifier does not depend on sample data IDs or random values.
- [ ] A test method with multiple requests assigns a unique name to each operation.
- [ ] Dynamic placeholders are used only when dependency on test names is intentional.
- [ ] No parallel tests write to the same identifier.
- [ ] All Asciidoctor/Markdown includes match actual snippet directories.
- [ ] Build/CI regenerates snippets before compiling and publishing documentation.

**Remember:** The identifier passed to `document(...)` determines the snippet directory. Naming it after the resource, HTTP operation, and scenario to be published keeps paths easy to understand, prevents overwrites, and stays stable across internal test changes. It is a small convention with direct impact on maintaining REST API documentation with Spring REST Docs.
