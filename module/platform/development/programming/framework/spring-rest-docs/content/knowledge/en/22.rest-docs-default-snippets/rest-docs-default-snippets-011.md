# Linking Snippets by Operation Directory

## Learning Objectives

In the **SPRING_REST_DOCS** module, each HTTP test can generate multiple snippets such as http-request, http-response, path-parameters, request-fields, response-fields, request-headers, or response-cookies. For Asciidoctor to compile documentation accurately, snippets must be placed in a predictable directory and the AsciiDoc file must include the exact paths.

Spring REST Docs organizes snippets by **operation identifier**. When a test calls document with an operation ID, REST Docs creates a corresponding subdirectory under the generated-snippets directory. Every snippet generated in that operation lives in the same directory. Source documentation then includes each snippet using a path composed of the root directory, operation ID, and snippet name.

After this lesson, you will be able to:

- Explain the relationship between operation ID, operation directory, and snippet file.
- Choose stable, unique, and readable operation IDs.
- Include snippets in AsciiDoc using the snippets attribute.
- Organize multiple operations for the same endpoint or multiple response variants.
- Avoid duplicate operation names causing overwrites or documentation pulling the wrong snippet.
- Synchronize the snippet output directory across tests, Asciidoctor, Gradle/Maven, and CI.
- Diagnose include path errors, missing snippets, and stale snippets.

## 1. What Is an Operation Directory?

When a test documents an HTTP exchange:

```java
mockMvc.perform(get("/api/products/{id}", 501))
    .andDo(document("products-get"));
```

The string products-get is the **operation identifier**. REST Docs uses this identifier to create a subdirectory inside the snippet output directory.

With Gradle, the default structure is typically:

```text
build/
└── generated-snippets/
    └── products-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── httpie-request.adoc
        └── request-parameters.adoc
```

With Maven, the output directory is typically at target/generated-snippets:

```text
target/
└── generated-snippets/
    └── products-get/
        ├── http-request.adoc
        ├── http-response.adoc
        └── request-parameters.adoc
```

The specific files depend on which snippets the test requested. REST Docs does not necessarily generate every type of snippet for every operation.

**Three components to distinguish:**

| Component | Example | Meaning |
| --- | --- | --- |
| Snippet output root | build/generated-snippets | Root directory containing operations |
| Operation ID/directory | products-get | Snippet group for a single HTTP operation |
| Snippet file | http-response.adoc | A documentation fragment generated from the test |

Operation directories keep snippets belonging to the same test operation together, avoiding a flat directory filled with identically named files like http-request.adoc across all endpoints.

## 2. Operation ID Determines the Include Path

Test example:

```java
this.mockMvc.perform(get("/api/products/{id}", 501)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("products-get",
        pathParameters(
            parameterWithName("id")
                .description("Product ID.")
        ),
        responseFields(
            fieldWithPath("id")
                .description("Product ID."),
            fieldWithPath("name")
                .description("Product name.")
        )));
```

The test above uses operation ID products-get and creates the corresponding snippets in:

```text
build/generated-snippets/products-get/
```

The AsciiDoc file includes the right directory:

```asciidoc
== GET /api/products/{id}

=== Path parameters
include::{snippets}/products-get/path-parameters.adoc[]

=== Response fields
include::{snippets}/products-get/response-fields.adoc[]

=== HTTP response
include::{snippets}/products-get/http-response.adoc[]
```

The snippets attribute represents the generated-snippets **root directory**; the products-get segment is the operation directory; the rest is the snippet filename. Do not include directly from the project root if the build task already provides the snippets attribute.

## 3. The snippets Attribute and Root Directory Location

Spring REST Docs' Asciidoctor extension provides the snippets attribute to reference the snippet directory. In a typical Gradle configuration, the Asciidoctor task uses the extension and reads the output directory written by tests.

Gradle configuration example:

```groovy
ext {
    snippetsDir = file('build/generated-snippets')
}

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn test
}
```

When the Spring REST Docs Asciidoctor extension is on the task classpath, documentation can include:

```asciidoc
include::{snippets}/products-get/http-request.adoc[]
```

There are two related configurations with distinct responsibilities here:

- The REST Docs test context determines where snippets are written.
- The Asciidoctor extension/attribute determines where documentation looks for snippets.

Merely declaring a Gradle variable snippetsDir does not automatically change where REST Docs tests write files. You must configure the output directory for the test context and synchronize Asciidoctor's input.

### 3.1. Maven

With Maven, plugins and test configurations typically use target/generated-snippets as the output. The Asciidoctor Maven Plugin must read that same directory and the REST Docs extension must be on the compilation classpath.

Includes in source documentation still use a relative form:

```asciidoc
include::{snippets}/products-get/http-request.adoc[]
```

There is no need to write target/ in every include if the snippets attribute is already configured to point to target/generated-snippets. This keeps source documentation less coupled to the build tool.

### 3.2. Changing the Output Directory

If a project configures snippets to a custom directory, for example:

```text
build/api-doc-snippets/
```

then all components must agree:

1. REST Docs tests write to build/api-doc-snippets.
2. The test task declares the matching output directory.
3. The Asciidoctor task declares build/api-doc-snippets as an input.
4. The snippets attribute points to build/api-doc-snippets.
5. CI saves/passes the exact directory if tests and documentation run in separate jobs.

If one step still points to the old build/generated-snippets, tests may pass while Asciidoctor reports missing files.

## 4. Choosing Stable Operation IDs

An operation ID should reflect the resource and action, independent of test execution order or test class name:

| HTTP operation | Suggested Operation ID |
| --- | --- |
| GET /api/products | products-list |
| GET /api/products/{id} | products-get |
| POST /api/products | products-create |
| PUT /api/products/{id} | products-update |
| DELETE /api/products/{id} | products-delete |
| POST /api/products/{id}/images | products-image-upload |

A helpful naming convention:

- Use lowercase letters and hyphens.
- Use resource names consistent with API documentation.
- Indicate the action or response variant when needed.
- Do not use vague names like test1, sample, or operationA.
- Do not embed dynamic data such as actual IDs, timestamps, or usernames in operation IDs.

IDs should remain stable across runs so include paths in documentation do not need to change with test data.

## 5. One Endpoint Can Have Multiple Operations

The same URL can have multiple scenarios that need documenting:

| Endpoint | Scenario | Operation ID |
| --- | --- | --- |
| GET /api/products/{id} | Product found | products-get |
| GET /api/products/{id} | Not found | products-get-not-found |
| GET /api/products/{id} | Access forbidden | products-get-forbidden |

Test example for the not-found case:

```java
this.mockMvc.perform(get("/api/products/{id}", 9999))
    .andExpect(status().isNotFound())
    .andDo(document("products-get-not-found",
        responseFields(
            fieldWithPath("code")
                .description("Error code."),
            fieldWithPath("message")
                .description("Error message.")
        )));
```

Snippets are separated:

```text
generated-snippets/
├── products-get/
│   ├── http-response.adoc
│   └── response-fields.adoc
└── products-get-not-found/
    ├── http-response.adoc
    └── response-fields.adoc
```

Separating operation IDs gives each scenario its own set of snippets. Source documentation can present both cases on the same page:

```asciidoc
== Get product
include::{snippets}/products-get/http-response.adoc[]
include::{snippets}/products-get/response-fields.adoc[]

== Product not found
include::{snippets}/products-get-not-found/http-response.adoc[]
include::{snippets}/products-get-not-found/response-fields.adoc[]
```

Do not use the same operation ID for two tests with different responses if you want to keep both sets of snippets intact.

## 6. Avoiding Duplicate Operation IDs and Snippet Overwrites

Multiple document calls can write into the same operation directory. If two tests both use products-get yet produce different payloads or descriptors, files with the same name in that directory may be overwritten by whichever test runs later. Documentation output becomes dependent on execution order.

Anti-pattern example:

```java
// Success test
.andDo(document("products-get", responseFields(...)));

// Error test using the same operation ID
.andDo(document("products-get", responseFields(...)));
```

Use distinct IDs instead:

```java
.andDo(document("products-get", responseFields(...)));

.andDo(document("products-get-not-found", responseFields(...)));
```

Rules:

- Each HTTP exchange with different documentation content should have its own operation ID.
- If multiple tests contribute snippets to one operation, only do so intentionally and when descriptors/bodies do not conflict.
- Do not let parallel tests write to the same snippet file.
- For parameterized tests, do not use actual parameter values to build dynamic IDs; pick stable IDs based on the documented scenario.

## 7. Organizing Source Documentation by Operation Groups

In a project with many endpoints, AsciiDoc can be split into pages by resource:

```text
src/docs/asciidoc/
├── index.adoc
├── products.adoc
├── orders.adoc
└── accounts.adoc
```

products.adoc example:

```asciidoc
= Products API

== List products
include::{snippets}/products-list/http-request.adoc[]
include::{snippets}/products-list/http-response.adoc[]

== View product details
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/http-response.adoc[]

== Create product
include::{snippets}/products-create/http-request.adoc[]
include::{snippets}/products-create/http-response.adoc[]
```

index.adoc can include the pages:

```asciidoc
= API Reference

include::products.adoc[]
include::orders.adoc[]
include::accounts.adoc[]
```

Source documentation is organized into reader-friendly groups; generated-snippets remains organized by operation ID. These two structures serve different purposes:

| Structure | Organized By | Goal |
| --- | --- | --- |
| src/docs/asciidoc | Chapters, resources, topics | Navigation and explanation for readers |
| generated-snippets | Operation ID | Grouping output generated from each test exchange |

Do not force the source documentation structure to mirror generated-snippets identically.

## 8. Linking Snippets by Operation in AsciiDoc

A full include path has the structure:

```text
{snippets}/<operation-id>/<snippet-name>.adoc
```

Examples:

| Content to Place on Page | Include |
| --- | --- |
| HTTP request | {snippets}/products-create/http-request.adoc |
| HTTP response | {snippets}/products-create/http-response.adoc |
| Request fields | {snippets}/products-create/request-fields.adoc |
| Response fields | {snippets}/products-create/response-fields.adoc |
| Path parameters | {snippets}/products-get/path-parameters.adoc |
| Request headers | {snippets}/products-create/request-headers.adoc |
| Response cookies | {snippets}/login/response-cookies.adoc |

Only include snippets that the test actually generates. If the operation did not call requestFields, request-fields.adoc will not exist. If the endpoint does not return cookies, response-cookies.adoc will not exist.

### 8.1. Using Attributes to Reduce Repetition

You can declare an attribute for the operation when a section focuses on a single operation:

```asciidoc
:operation: products-create

== Request
include::{snippets}/{operation}/http-request.adoc[]

== Response
include::{snippets}/{operation}/http-response.adoc[]

== Request fields
include::{snippets}/{operation}/request-fields.adoc[]
```

The operation attribute is purely an AsciiDoc variable to reduce path repetition. It does not create an operation directory and does not affect tests; the name must still match document("products-create").

## 9. When Using Custom Snippet Templates

REST Docs allows customizing snippet templates. Even when template content changes, the operation directory organization rule stays the same: the operation's output resides in the corresponding directory and the file bears the configured snippet name.

If creating a custom snippet named, for instance, operation-summary, the include path must use the exact filename produced by the task:

```asciidoc
include::{snippets}/products-create/operation-summary.adoc[]
```

Do not guess filenames from template names. Inspect the output directory after tests run to see the exact generated snippet name and custom snippet output configuration. If a template name or snippet name is overridden, update includes accordingly.

## 10. Multi-Module Projects and CI

### 10.1. Multiple Gradle Modules

In a multi-module project, each module may have its own build/generated-snippets directory. Example:

```text
project/
├── catalog-service/
│   └── build/generated-snippets/
│       ├── products-list/
│       └── products-create/
├── order-service/
│   └── build/generated-snippets/
│       ├── orders-list/
│       └── orders-create/
└── api-docs/
    └── src/docs/asciidoc/
```

If the api-docs module compiles documentation from snippets of other modules, expose those output directories to the task workspace and configure attributes/base paths for each source. Example:

```asciidoc
:catalog-snippets: ../catalog-service/build/generated-snippets
:order-snippets: ../order-service/build/generated-snippets

include::{catalog-snippets}/products-list/http-response.adoc[]
include::{order-snippets}/orders-list/http-response.adoc[]
```

Relative paths must be verified against the actual base directory of the Asciidoctor task. In complex setups, pass attributes using absolute paths resolved by the build script rather than guessing relative paths.

### 10.2. CI Splitting Tests and Documentation into Two Jobs

If tests and Asciidoctor run in two separate jobs:

1. The test job runs HTTP documentation tests.
2. The test job archives the entire generated-snippets directory as an artifact.
3. The documentation job downloads the artifact into the exact snippet output root.
4. Asciidoctor reads the snippets attribute pointing to the downloaded location.
5. The documentation job verifies that required operation directories and included files exist.

Do not transfer only a few scattered files if documentation uses multiple operations; transfer the entire generated-snippets directory to preserve structure.

### 10.3. Avoiding Artifact Collisions

If multiple jobs generate snippets for the same operation ID and save them into a shared directory, files can overwrite each other. Organize each module/job into its own output root or ensure operation IDs are unique and artifact merging has clear rules.

## 11. Inspecting the Operation Directory

After running tests:

PowerShell:

```powershell
Get-ChildItem -Recurse build/generated-snippets
```

Linux/macOS:

```bash
find build/generated-snippets -type f
```

For the products-create operation, verify:

- The products-create directory exists.
- Snippets needed for includes were generated.
- Snippet filenames are spelled properly with the right extension.
- Timestamps/file contents belong to the test run just executed.
- No other test overwrote the same directory.

You can quickly check specific paths:

```powershell
Test-Path build/generated-snippets/products-create/http-request.adoc
Test-Path build/generated-snippets/products-create/response-fields.adoc
```

Verification commands must match the snippets actually generated by the test. For example, an operation without a response body will not have response-fields.adoc.

## 12. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Asciidoctor reports included file does not exist | Wrong operation ID or snippet name | Compare document(...) against the output directory tree |
| Operation directory does not appear | Test did not run, test did not call document, or different output root | Run the right test task and check the output directory |
| Snippets are in target yet include looks in build | Mixed Maven/Gradle paths | Synchronize the snippets attribute with test output |
| Include points to right operation yet wrong file | Test did not generate that snippet type | Check descriptors/actions actually used in the test |
| An operation has an unexpected response | Multiple tests share an ID and overwrite | Separate operation IDs for each scenario |
| Docs work locally yet fail in CI | Artifact does not preserve directory tree or downloaded to wrong location | Upload/download the full directory and fix the attribute |
| Stale snippets still included | Old output remains after test changes | Run clean and verify output from the new build |
| Multi-module include has wrong path | Asciidoctor base directory differs from expectation | Print/verify resolved paths and set attributes explicitly |
| Custom snippet not found | Output filename differs from include name | Check template/snippet configuration and actual output |
| Parallel tests have flaky snippet contents | Two tests write to the same operation directory | Use separate IDs or coordinate output writing |

## 13. Hands-on Exercise

1. Create a GET /api/products/{id} test with operation ID products-get.
2. Verify the generated-snippets/products-get directory is created.
3. Create products.adoc and include http-request.adoc and http-response.adoc for that operation.
4. Create a products-get-not-found test and use a distinct ID.
5. Include response-fields of both cases in two separate sections.
6. Change the output root to a custom directory; synchronize the test context, task output/input, and snippets attribute.
7. Run clean test asciidoctor, inspect the directory tree, and check the HTML documentation.
8. (Advanced) Transfer snippets to a CI job artifact and run Asciidoctor in a separate job.

**Self-assessment questions**

1. Which part of the generated-snippets tree is determined by the operation ID?
2. Which directory does the snippets attribute represent?
3. Why does an AsciiDoc file need both operation ID and snippet name in the include path?
4. When the same endpoint has a success response and an error response, should they share an ID?
5. Why can tests using the same operation ID overwrite snippets?
6. How do the AsciiDoc source directory and generated-snippets differ in purpose?
7. How should multi-module CI transfer artifacts to preserve include paths?
8. How can you determine whether a missing snippet is caused by a wrong include or because the test never generated it?

## Official References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): configuring the output directory, running tests, and using Asciidoctor to include snippets.
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): operations, snippets, and the documentation workflow.
- [Spring REST Docs — Asciidoctor](https://docs.spring.io/spring-restdocs/reference/getting-started/documentation-snippets.html): integrating snippets with Asciidoctor and attributes.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): declaring inputs/outputs and task relationships.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): organizing tasks and dependencies across modules.
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): test lifecycle and build outputs.

**Practical conclusion:** Use stable operation IDs to group all snippets of an HTTP exchange into the same directory. In AsciiDoc, include using the structure of snippets root directory, operation ID, and snippet name. Keep IDs unique for scenarios with different outputs, synchronize the output root between tests and Asciidoctor, and transfer the full directory structure through CI so include paths always point to files generated by tests.
