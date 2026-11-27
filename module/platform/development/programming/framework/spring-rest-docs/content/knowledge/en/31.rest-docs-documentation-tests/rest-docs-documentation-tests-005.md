# Verifying Operation Names and Snippet Directories

## Learning Objectives

In the **SPRING_REST_DOCS** module, each call to `document(...)` binds an HTTP exchange to an operation identifier. Spring REST Docs uses this identifier to group generated snippets into a dedicated directory. AsciiDoc documentation then references that exact directory and snippet filename to assemble the API reference.

If an operation name is unstable, duplicated, or does not match the include path, tests can overwrite snippets, Asciidoctor fails to find files, or documentation pulls content from the wrong operation. Verifying operation names and the snippet directory tree is therefore a crucial part of documentation testing.

After this lesson, you will be able to:

- Explain the role of the operation identifier in `document(...)`.
- Distinguish an operation name from a test method name, endpoint URL, and snippet name.
- Choose stable, unique, and readable operation names.
- Verify that the snippet directory is created accurately from test output.
- Detect duplicate operation IDs and overwrite risks during parallel test execution.
- Synchronize the snippet output root with Asciidoctor and CI.
- Diagnose wrong operation paths, missing snippets, and stale snippets.

## 1. What Is an Operation Name?

When using Spring REST Docs, tests typically call:

```java
this.mockMvc.perform(get("/api/products/{id}", 501))
    .andExpect(status().isOk())
    .andDo(document("products-get"));
```

The string `products-get` is the **operation identifier** (also commonly called the operation name). It identifies the snippet bundle for this HTTP exchange.

With the default output root commonly used in Gradle:

```text
build/generated-snippets/
└── products-get/
    ├── http-request.adoc
    └── http-response.adoc
```

If the test declares additional descriptors, the operation directory gets the corresponding snippets:

```java
.andDo(document("products-get",
    pathParameters(
        parameterWithName("id").description("Product ID.")
    ),
    responseFields(
        fieldWithPath("id").description("Product ID."),
        fieldWithPath("name").description("Product name.")
    )));
```

Then the directory may contain:

```text
build/generated-snippets/
└── products-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
```

Only the snippets the test explicitly requests are created. `document("products-get")` does not automatically generate every snippet type.

## 2. Distinguishing Operation Name from Other Names

| Concept | Example | Role |
| --- | --- | --- |
| Test method name | `getProduct_returnsProduct()` | Java test method identifier |
| Endpoint URL | `GET /api/products/{id}` | HTTP path called by clients |
| Operation identifier | `products-get` | Groups snippets for the exchange |
| Snippet name | `http-response.adoc` | Specific file generated inside the operation directory |
| AsciiDoc include path | `{snippets}/products-get/http-response.adoc` | Documentation path used to include the file |

There is no requirement for the operation name to match the test method or endpoint. Name it after the API operation's semantics so documentation sources can reference it stably.

For example, the test method might be `shouldReturnProductWhenIdExists`, the endpoint `/api/products/{id}`, and the operation ID `products-get`. Three names serve three different purposes.

## 3. Rules for Naming Operations

An operation name should be:

- Stable across test runs.
- Unique for each request/response set that needs separate documentation.
- Readable and reflective of the resource/action or scenario.
- Independent of dynamic data such as random IDs, timestamps, or usernames.
- Consistent between tests and AsciiDoc includes.

A simple convention:

```text
<resource>-<action>[-<scenario>]
```

Examples:

| HTTP operation/scenario | Operation name |
| --- | --- |
| GET /api/products | `products-list` |
| GET /api/products/{id} succeeded | `products-get` |
| POST /api/products | `products-create` |
| PUT /api/products/{id} | `products-update` |
| DELETE /api/products/{id} | `products-delete` |
| GET /api/products/{id} not found | `products-get-not-found` |
| POST /api/products/{id}/images | `products-image-upload` |

Short, lowercase, hyphenated names make include paths easy to read. Dots or nested directory structures can be used if the project follows that convention, provided you check actual output and avoid hard-to-maintain paths.

Avoid using:

- `test1`, `sample`, `operationA`: convey no meaning.
- `products-get-501`: tied to a specific data ID.
- `products-get-2026-11-17`: changes over time.
- Overly long test method names: make documentation paths hard to read and prone to breaking on test refactors.

## 4. One Endpoint, Multiple Operation Names

The same endpoint can have multiple outcomes worth documenting:

| Endpoint | Scenario | Operation name |
| --- | --- | --- |
| GET /api/products/{id} | Found | `products-get` |
| GET /api/products/{id} | Not found | `products-get-not-found` |
| GET /api/products/{id} | Insufficient permissions | `products-get-forbidden` |

Example:

```java
@Test
void getProduct() throws Exception {
    this.mockMvc.perform(get("/api/products/{id}", 501))
        .andExpect(status().isOk())
        .andDo(document("products-get"));
}

@Test
void getProductNotFound() throws Exception {
    this.mockMvc.perform(get("/api/products/{id}", 9999))
        .andExpect(status().isNotFound())
        .andDo(document("products-get-not-found"));
}
```

Two operation directories are separated:

```text
generated-snippets/
├── products-get/
│   ├── http-request.adoc
│   └── http-response.adoc
└── products-get-not-found/
    ├── http-request.adoc
    └── http-response.adoc
```

Do not share an operation name when two tests produce different responses and need independent snippet sets.

## 5. What Can Duplicate Operation Names Cause?

Each operation directory holds snippet files with fixed names like `http-request.adoc`, `http-response.adoc`, `response-fields.adoc`. If multiple tests use the same operation ID yet produce different content, the same file can be overwritten.

Example:

```java
// Success test
.andDo(document("products-get",
    responseFields(
        fieldWithPath("id").description("Product ID.")
    )));

// Not found test - mistakenly reuses the same operation ID
.andDo(document("products-get",
    responseFields(
        fieldWithPath("code").description("Error code.")
    )));
```

Two responses with different schemas write into the same `products-get/response-fields.adoc`. The final result can depend on which test ran last. Under parallel execution, file write conflicts become even less predictable.

The solution is separating operation IDs:

```java
.andDo(document("products-get", successDescriptors));

.andDo(document("products-get-not-found", errorDescriptors));
```

If multiple tests intentionally contribute snippets to the same operation, ensure they do not overwrite identically named files and follow a clear strategy. For distinct HTTP scenarios, separating IDs is usually clearer and safer.

## 6. Operation Names Do Not Determine the Output Root

An operation name only determines the subdirectory. The root directory is configured by the REST Docs test context or build integration settings.

Example:

```text
build/generated-snippets/       # Common in Gradle
target/generated-snippets/       # Common in Maven
```

If the output root is customized to `build/api-snippets`, the operation directory lives underneath that root:

```text
build/api-snippets/
└── products-get/
    ├── http-request.adoc
    └── http-response.adoc
```

Do not confuse the operation ID with the output directory. Changing `document("products-get")` does not automatically move the entire output root elsewhere.

### 6.1. Synchronizing Tests and Asciidoctor

Both sides must use the same output root:

1. REST Docs tests write snippets to the configured directory.
2. The Asciidoctor task reads that exact directory.
3. The `snippets` attribute points to the output root.
4. The include path appends the operation ID and snippet name.

Example include:

```asciidoc
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]
```

If tests write to `target/generated-snippets` while Asciidoctor looks in `build/generated-snippets`, includes will fail even when the operation name is exact.

## 7. Inspecting the Operation Directory After Tests Run

After running documentation tests, inspect the output directory tree.

PowerShell:

```powershell
Get-ChildItem -Recurse build/generated-snippets
```

Linux/macOS:

```bash
find build/generated-snippets -type f
```

For operation ID `products-get`, verify the directory and files:

```powershell
Test-Path build/generated-snippets/products-get
Test-Path build/generated-snippets/products-get/http-request.adoc
Test-Path build/generated-snippets/products-get/http-response.adoc
```

These commands are examples for default Gradle output. If the project uses Maven or a custom output root, substitute the actual path.

When inspecting, confirm:

- The operation directory has the exact name passed to `document(...)`.
- Only the snippets requested by the test are expected to exist.
- Files contain content from the exchange that just ran.
- No stale files from renamed operations remain to cause confusion.
- No other operation unintentionally shares the same ID.

## 8. Including Snippets by Operation Name

An include path follows this structure:

```text
{snippets}/<operation-name>/<snippet-name>.adoc
```

Example `products.adoc` page:

```asciidoc
= Products API

== List Products
include::{snippets}/products-list/http-request.adoc[]
include::{snippets}/products-list/http-response.adoc[]

== Get Product Details
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]

== Product Not Found
include::{snippets}/products-get-not-found/http-response.adoc[]
```

The operation name segment in the include must match the parameter passed to `document(...)` character for character. A single wrong character, hyphen, or case mismatch can prevent Asciidoctor from finding the file.

### 8.1. Using an Operation Attribute to Avoid Repetition

If a section includes multiple snippets from the same operation:

```asciidoc
:operation: products-create

== Request
include::{snippets}/{operation}/http-request.adoc[]

== Response
include::{snippets}/{operation}/http-response.adoc[]

== Request fields
include::{snippets}/{operation}/request-fields.adoc[]
```

The `operation` attribute is simply an AsciiDoc variable to reduce repetition. It does not create directories and has no effect on REST Docs. Its value must match the test's operation ID.

## 9. Operation Names in Parameterized Tests

Parameterized tests can run across many inputs without needing to create an operation directory for each value.

Example avoiding runtime data in the ID:

```java
document("products-get-" + productId)
```

This approach can generate numerous folders and make include paths unstable. Pick one operation ID for a meaningful documentation scenario, use a fixed fixture, or split tests if differing responses require separate documentation.

If parameterized runs only verify the same schema and the same documentation, ensure they do not simultaneously write to the same snippet file. You can designate a single test case as the snippet source or assign distinct IDs per documented scenario group.

## 10. Operation Names in Multi-Module Builds and CI

### 10.1. Multi-Module

Each module may have its own output root:

```text
project/
├── catalog-service/
│   └── build/generated-snippets/
│       ├── products-list/
│       └── products-get/
├── order-service/
│   └── build/generated-snippets/
│       ├── orders-list/
│       └── orders-get/
└── api-docs/
    └── src/docs/asciidoc/
```

Operation IDs could collide between two modules if they used separate output roots, and when merged into a shared root you must avoid path collisions. You can add a module prefix:

- `catalog-products-get`
- `orders-orders-get`

What matters is keeping the naming convention consistent and ensuring include paths point to the right source.

### 10.2. CI Splitting Tests and Asciidoctor Across Jobs

If tests and documentation compilation run in two separate jobs:

1. The test job runs documentation tests and generates `generated-snippets`.
2. Archive the entire output root as an artifact, preserving all operation directories.
3. The docs job downloads the artifact into the exact configured output root.
4. Asciidoctor includes files by operation ID and snippet name.
5. If an include fails, verify whether the artifact preserved the directory structure and filenames.

Do not upload only isolated snippet files if documentation spans multiple operations. Preserving the entire directory tree prevents rewriting include paths between local and CI builds.

## 11. Diagnosing Operation Name and Directory Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| No operation directory exists | Test did not run, did not call document, or output root differs | Run the right test task and check output root |
| Directory has an unexpected name | Operation ID in document differs from include name | Compare document(...) argument and AsciiDoc |
| Asciidoctor reports http-response.adoc not found | Test did not generate that snippet or include filename is wrong | Check descriptors and output tree |
| Snippet contains another test's response | Two tests share the same operation ID and overwrite the file | Separate IDs per scenario |
| Unstable results under parallel runs | Multiple tests write to the same operation directory | Use distinct IDs or coordinate snippet-writing tests |
| Includes work locally but fail in CI | Artifact missing subdirectories or downloaded to wrong root | Archive/restore the entire generated-snippets tree |
| Include points to stale snippet | Old output left behind after renaming test/operation | Clean output and re-run documentation tests |
| Maven produces files but Asciidoctor looks in build | Confusing target with build output | Align the snippets attribute with Maven output |
| Parameterized test spawns too many folders | ID contains runtime values | Use stable scenario-based IDs |
| Two modules write to same operation path | Merged into one root with colliding IDs | Prefix by module or separate output roots |

## 12. Pre-Compilation Verification Workflow

1. Locate all `document(...)` calls in the operation's documentation tests.
2. Confirm the operation ID is stable and unique for that exchange's content.
3. Run the right test task to generate snippets.
4. Inspect the operation directory inside the output root.
5. Check the snippet files that AsciiDoc will include.
6. Cross-check operation IDs in includes against the tests.
7. Run Asciidoctor to confirm includes succeed.
8. If CI uses separate jobs, verify artifacts preserve operation directories.

This workflow isolates failures: test not generating snippets, test writing to the wrong directory, wrong include name, or incomplete artifact transfer.

## 13. Hands-On Exercise

1. Write a `GET /api/products/{id}` test calling `document("products-get")`.
2. Inspect `generated-snippets/products-get` and the generated snippets.
3. Write a not-found test using `document("products-get-not-found")`.
4. Include both operations in `products.adoc` under two different sections.
5. Create two tests with different responses that temporarily share an operation ID; observe the overwrite risk and fix it with separate IDs.
6. Change the output root to a custom directory; synchronize the test context, Asciidoctor input, and `snippets` attribute.
7. Try running tests in parallel to verify no two tests write to the same file.
8. (Advanced) Save `generated-snippets` as a CI artifact and compile the documentation in another job.

**Self-Assessment Questions**

1. Where is the operation identifier passed in Spring REST Docs?
2. How does an operation name differ from a test method name and an endpoint URL?
3. Why should two tests with differing responses not share the same operation ID?
4. Does the operation ID determine the output root?
5. What components make up an include path?
6. How should parameterized tests handle operation IDs to avoid generating too many folders?
7. When merging snippets from multiple modules into one root, what must be controlled?
8. How can you distinguish a test failing to generate snippets from an incorrect AsciiDoc include?

## Official References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): configuring the output directory and generating snippets from tests.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): operations and snippet generation.
- [Spring REST Docs — Asciidoctor Integration](https://docs.spring.io/spring-restdocs/reference/getting-started/documentation-snippets.html): including snippets and Asciidoctor configuration.
- [Spring REST Docs API — MockMvcRestDocumentation](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html): integrating `document` with MockMvc.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): declaring task inputs/outputs.
- [Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): test lifecycle and build outputs.

**Practical Takeaway:** An operation name is the stable key grouping an HTTP exchange's snippets. Choose meaningful, distinct IDs for scenarios with differing outputs; inspect operation directories after tests; include `{snippets}/<operation-name>/<snippet-name>.adoc` accurately; and keep the output root synchronized across tests, Asciidoctor, and CI. When these steps align, documentation always references snippets generated by the current tests.
