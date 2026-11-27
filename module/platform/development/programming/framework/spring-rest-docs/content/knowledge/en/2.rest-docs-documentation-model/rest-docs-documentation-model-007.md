# Operation Identifiers and Snippet Directory Organization

In Spring REST Docs, every call to §document(...)§ requires an **operation identifier**. This identifier is used to group the snippets generated from the request/response and descriptors of that test run. When an Asciidoctor page includes §{snippets}/orders-get-success/http-response.adoc[]§, the §orders-get-success§ segment must match the identifier used by the test.

Naming and organizing snippet directories directly affects documentation maintainability. If multiple tests write to the same directory, success and error examples can overwrite or mix with each other. If a test renames its identifier while the documentation still includes the old path, the build may fail or silently use leftover snippets from an earlier run. If operation names are cryptic, developers struggle to trace a documentation page back to the test that produced it.

This lesson belongs to the **Documentation Model** chapter of the §SPRING_REST_DOCS§ module. The module practices generating verifiable REST API documentation with MockMvc, WebTestClient, or REST Assured, producing snippets for requests, responses, payloads, parameters, and headers, and compiling Asciidoctor/Markdown in build and CI. This lesson focuses on choosing identifiers, structuring directories, separating operations on the same route, and managing the snippet lifecycle.

## 1. Learning Objectives

After this lesson, you can:

1. Explain how the §document(...)§ identifier is used to locate snippets.
2. Name operations stably and clearly, distinguishing method, resource, and handling scenario.
3. Organize snippet outputs by resource, operation, and scenario.
4. Distinguish one operation with multiple snippets from multiple operations sharing a route.
5. Prevent duplicate identifiers, overwritten outputs, stale snippets, and broken includes.
6. Connect snippet paths with Gradle/Maven configuration and CI workflows.
7. Manage operation renames without breaking documentation pages.

## 2. Identifiers Link Snippets to Their Source Operation

A MockMvc test typically ends with a call like:

```java
.andDo(document("orders-get-success",
    pathParameters(
        parameterWithName("orderId")
            .description("Order ID")
    ),
    responseFields(
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("status").description("Status")
    )
));
```

Here §orders-get-success§ is an author-chosen identifier. Spring REST Docs uses this identifier to create an operation directory under the test's output directory. Under common configurations, the structure looks like:

```text
build/generated-snippets/
└── orders-get-success/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
```

The actual path depends on the output directory configured for tests. Gradle projects usually use §build/generated-snippets§; Maven projects usually use §target/generated-snippets§. The identifier remains the folder name appended to the output directory.

When writing:

```asciidoc
include::{snippets}/orders-get-success/http-response.adoc[]
```

the parts mean:

| Part | Meaning |
| --- | --- |
| §{snippets}§ | Asciidoctor attribute pointing to the output directory |
| §orders-get-success§ | Identifier passed into §document(...)§ |
| §http-response.adoc§ | Name of the snippet to include |

**The identifier is the linking contract between tests and source documentation.** Renaming an identifier in a test normally requires updating the corresponding include paths.

### 2.1. One Identifier Holds Multiple Snippets

One operation can generate multiple content fragments simultaneously. For instance, an order-reading test can produce:

- §http-request.adoc§ and §http-response.adoc§ for HTTP examples.
- §path-parameters.adoc§ for path variables.
- §query-parameters.adoc§ for query parameters.
- §request-headers.adoc§ or §response-headers.adoc§ for documented headers.
- §request-fields.adoc§ or §response-fields.adoc§ for payloads.

These files reside together inside the directory named after the operation's identifier. There is no need to create a separate identifier for each snippet. The filename distinguishes **the type of information**, while the directory name identifies **the source operation**.

### 2.2. Multiple Operations Can Share the Same Route

For example, §GET /api/orders/{orderId}§ has at least two outcomes:

| Operation | Example request | Response | Identifier |
| --- | --- | --- | --- |
| Read order successfully | §GET /api/orders/42§ | §200 OK§, order JSON | §orders-get-success§ |
| Order not found | §GET /api/orders/999§ | §404 Not Found§, error JSON or empty body per contract | §orders-get-not-found§ |

These are two separate documented operations despite sharing the same method and route template. If they share an identifier, one run's snippets can overwrite the other's. Readers would also lose clarity on which response belongs to which scenario.

## 3. Identifier Naming Guidelines

A good name quickly answers three questions: **which resource, which action, which scenario?**

A readable pattern:

```text
<resource>-<http-method>-<scenario>
```

Examples:

| Identifier | Meaning |
| --- | --- |
| §orders-get-success§ | Read order successfully |
| §orders-get-not-found§ | Order not found |
| §orders-create-success§ | Create order successfully |
| §orders-create-invalid§ | Invalid order creation request |
| §orders-update-conflict§ | Update hit a state conflict |
| §orders-delete-success§ | Delete order successfully |

This is a convention a project can adopt; Spring REST Docs does not mandate this exact pattern. What matters is that identifiers are stable and unique across tests writing to the same output directory.

### 3.1. Concrete Guidelines

**Use consistent resource or endpoint-group names.** If the rest of the documentation calls it §orders§, do not switch between §order§ and §purchase§ for the same concept without reason.

**State the method or action clearly.** §orders-get-success§ is easier to recognize than §orders-success§ when a resource supports GET, POST, and DELETE.

**Include the scenario when multiple responses are possible.** Use §success§, §not-found§, §invalid§, §forbidden§, §conflict§, or a consistent project vocabulary.

**Prefer lowercase and hyphens.** Names like §orders-get-not-found§ are readable in include paths and independent of filesystem case-sensitivity rules.

**Keep identifiers independent of fixture data.** Do not name it §orders-get-42§ merely because the test currently calls ID 42, unless the ID value itself is an essential distinction. Fixtures may change, whereas operation names should stay stable.

**Do not embed arbitrary code versions or run dates.** Identifiers such as §orders-get-v17-20261117§ cause builds to spawn unnecessary directories. API versions should appear in explicitly managed documentation/output structures if the project needs them.

### 3.2. Avoid Ambiguous or Overly Long Names

| Poor name | Problem | Better name |
| --- | --- | --- |
| §test1§ | Does not state the resource or action | §orders-get-success§ |
| §success§ | Can collide across multiple resources | §orders-create-success§ |
| §get-order§ | Does not distinguish success from errors | §orders-get-success§ |
| §orders-42§ | Coupled to fixture data | §orders-get-success§ |
| §orders-get-success-with-user-role-admin-and-v2§ | Too long, mixes too many classification axes | §orders-get-admin-success§ if the role actually produces a distinct response |
| §orders-final-new§ | Does not describe behavior; words like final/new age poorly | §orders-create-success§ |

If role, locale, version, or media type genuinely alters the response contract, you can include that dimension in the operation name, such as §orders-get-owner-success§ and §orders-get-support-success§. Only add it when there is a difference worth documenting; do not put every input value into the identifier.

## 4. Organizing Snippet Directories Across Multiple Resources

For a small service, a single output directory can hold operations at the same level:

```text
build/generated-snippets/
├── products-get-success/
├── products-get-not-found/
├── products-create-success/
├── orders-get-success/
├── orders-create-invalid/
└── orders-cancel-conflict/
```

This flat structure is easy to search and convenient when source docs include snippets. As the number of operations grows, maintain a clear naming convention or split output directories by source set, module, or test suite.

### 4.1. Splitting by Resource in Documentation Pages

You do not need deeply nested output directories to have multi-part documentation. A usually simpler approach is keeping identifiers flat and organizing Asciidoctor pages by resource:

```text
src/docs/asciidoc/
├── index.adoc
├── introduction.adoc
├── products.adoc
├── orders.adoc
└── errors.adoc

build/generated-snippets/
├── products-get-success/
├── products-get-not-found/
├── orders-get-success/
└── orders-create-invalid/
```

The §orders.adoc§ page references §orders-*§ directories, while §products.adoc§ references §products-*§. Editors can quickly locate related operations by filename and identifier.

### 4.2. When Should You Split Output Directories?

In large systems, splitting output directories helps when:

- Multiple independent modules generate snippets.
- Different source sets or test suites have distinct lifecycles and build responsibilities.
- API versions need to be built, reviewed, or released separately.
- Different documentation sets require distinct preprocessing or snippet templates.

In those cases, test groups can be configured to use separate output directories, for example:

```text
build/
├── snippets-public-api/
│   ├── orders-get-success/
│   └── products-get-success/
├── snippets-admin-api/
│   ├── orders-get-admin/
│   └── users-get-admin/
└── docs/
    ├── public-api/
    └── admin-api/
```

These directory names illustrate **build organization strategies**, not structures created automatically by Spring REST Docs by default. Separation must be paired with per-test configuration and the corresponding §snippets§ attribute in documentation. If all tests still write to a single output directory, creating folders manually in the source tree will not automatically split Spring REST Docs' output.

### 4.3. Avoid Over-Splitting

Do not create a separate output directory for every single test method if the tests belong to the same documentation set and can share the build mechanism. Splitting into too many places multiplies configurations, include attributes, and cleanup steps.

A practical choice:

| Scale | Suitable organization |
| --- | --- |
| A few endpoints in one service | Single output directory; identifiers by resource/method/scenario |
| Many resources in one API | Single output directory; pages split by resource |
| Multiple independent APIs/modules | Separate output directories per module or test suite |
| Multiple public API versions | Split docs and outputs by version when independent releases are needed |

## 5. Example of Consistent Identifiers and Includes

Suppose a MockMvc test records an API that reads a product. We use the identifier §products-get-success§.

```java
@Test
void getProduct_success() throws Exception {
    mockMvc.perform(
            get("/api/products/{productId}", 7L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(7))
        .andDo(document("products-get-success",
            pathParameters(
                parameterWithName("productId")
                    .description("ID of the product to look up")
            ),
            responseFields(
                fieldWithPath("id")
                    .description("Product identifier"),
                fieldWithPath("name")
                    .description("Product name")
            )
        ));
}
```

Because the test uses the URI variable §{productId}§, Spring REST Docs' builder is required:

```java
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
```

For §MockMvc§, the test needs REST Docs configuration, such as with §RestDocumentationExtension§ and §documentationConfiguration(...)§. Dependencies and the output directory must be set up according to the build tool in use.

The AsciiDoc page uses this exact identifier:

```asciidoc
=== Look up a product

.Request
include::{snippets}/products-get-success/http-request.adoc[]

.Path parameters
include::{snippets}/products-get-success/path-parameters.adoc[]

.Response
include::{snippets}/products-get-success/http-response.adoc[]

.Response fields
include::{snippets}/products-get-success/response-fields.adoc[]
```

If you rename the identifier in the test to §product-get§, all four includes above must be reviewed. Changing the test while forgetting the docs creates an invalid path; if the build does not clean old outputs, includes might still find stale files and mask the broken link.

## 6. Identifiers Must Be Unique Within a Shared Output Scope

Two independent tests writing to the same identifier write files like §http-request.adoc§ and §http-response.adoc§ into the same folder. If their content differs, the final output depends on execution order or parallel scheduling, leading to non-deterministic documentation.

Bad example:

```java
@Test
void getOrder_success() {
    // ...
    document("orders-get");
}

@Test
void getOrder_notFound() {
    // ...
    document("orders-get");
}
```

Both tests write to §orders-get§. Proper names should reflect each scenario:

```java
document("orders-get-success", ...);
document("orders-get-not-found", ...);
```

Rules to remember:

- Identifiers must be **unique** across independent operations within the same output directory.
- If one test method executes multiple documented requests, each operation must have its own identifier matching its purpose.
- Never allow two concurrent test tasks to write to the same directory/identifier when producing different content.
- If output directories are split, identifiers may be reused across independent outputs, provided documentation pages point to the exact directory containing the intended snippet.

### 6.1. Reusing Identifiers Is Not How You Reuse Snippets

If multiple pages need the same snippet from **the same operation**, include that same output file in multiple places. Do not run a different test with that identifier to “regenerate” the snippet for a new page. If the operation has a different response, create a new identifier and a corresponding test.

### 6.2. When Tests Run in Parallel

Parallel test execution shortens build time, yet requires care with shared outputs. Tests generating distinct identifiers can generally write to separate directories safely. Tests sharing an identifier or custom snippet file can collide. The fix is keeping identifiers unique, avoiding writes to the same output from multiple tasks, and giving each test suite its own output location if run independently.

## 7. Managing Stale Outputs and Obsolete Snippets

Snippets are auto-generated outputs, so they have a **lifecycle**:

```text
Test + document(identifier)
          │
          ▼
  Create snippet directory
          │
          ▼
  Source doc includes file
          │
          ▼
   API/identifier changes
          │
          ▼
      Run new build
          │
     ┌────┴─────┐
     ▼          ▼
  Update     Delete / no longer
  snippet    referenced
```

A dangerous pitfall: snippet files from a previous build still exist. The current test might not run or its identifier might have changed, yet Asciidoctor still reads the old file. The page renders successfully without using fresh evidence.

### 7.1. Cleaning at the Right Time

In CI, build from a clean checkout or clean generated outputs before generating snippets. Locally, use the appropriate clean task and then run tests and the documentation task. Never manually delete source documentation files or directories outside auto-generated outputs.

Distinguish carefully:

- **Documentation sources:** §.adoc§/§.md§ files maintained by the team, which must be preserved.
- **Generated snippets:** test output files, which are reproducible.
- **Rendered documentation:** HTML/PDF/site outputs from compilation.

Cleaning generated outputs does not mean deleting sources. The build should define output directories explicitly so cleaning is safe and repeatable.

### 7.2. Checking Includes After Renaming Identifiers

When renaming §orders-get-success§:

1. Search for includes referencing the old name across managed pages.
2. Update the identifier in tests and include paths in the same change.
3. Regenerate snippets in a clean output directory.
4. Run Asciidoctor and confirm no broken includes remain.
5. Inspect rendered content to ensure it shows the right operation and success/error case.

Do not rely on “the old file is still there so it rendered fine”. A clean build proves the new path actually has a live source.

## 8. Configuring Output Directories in the Build

The identifier is only part of the path. The root path is determined by Spring REST Docs configuration and the build tool.

### 8.1. With Gradle

A common configuration sets snippet output to a build directory and makes the documentation task depend on tests. Illustrative Groovy DSL example:

```groovy
plugins {
    id 'org.asciidoctor.jvm.convert' version '4.0.2'
}

configurations {
    asciidoctorExt
}

dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

def snippetsDir = file("$buildDir/generated-snippets")

test {
    outputs.dir snippetsDir
}

asciidoctor {
    dependsOn test
    configurations 'asciidoctorExt'
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

This is a skeleton configuration; plugin versions, Spring Boot/REST Docs versions, and your project's Gradle DSL may require adjustments. The core idea is that the test task writes snippets to a known output directory and Asciidoctor reads that exact directory via the §snippets§ attribute.

With JUnit 5 tests, you can connect §RestDocumentationExtension§ to MockMvc via §documentationConfiguration(provider)§. Spring Boot projects can also use §@AutoConfigureRestDocs§ with the appropriate test configuration.

### 8.2. With Maven

In Maven, the default output under common setups usually resides at §target/generated-snippets§. The documentation compilation plugin must be bound to the lifecycle after tests generate snippets and receive the §snippets§ attribute pointing to that directory.

Do not copy Gradle configuration syntax into Maven. Explicitly check:

- Which tests generate snippets and in which phase.
- What the actual output directory is.
- Whether the Asciidoctor plugin runs after tests.
- Whether include files use the right attribute and identifiers.
- Whether a clean build reproduces the same output structure.

### 8.3. When One Module Has Multiple Test Suites

If integration tests, contract tests, and smoke tests all generate snippets, decide whether they belong to the same documentation set. If they have independent lifecycles, use separate output directories and compile each documentation set individually. Avoid letting one suite get skipped while the page pulls snippets from another suite that happens to share a name.

Example:

```text
build/
├── generated-snippets/
│   ├── orders-get-success/       (unit/MVC docs)
│   └── products-get-success/
├── integration-snippets/
│   ├── orders-get-database/
│   └── products-get-indexed/
└── docs/
    ├── mvc-api/
    └── integration-api/
```

The names and grouping above are a project organization strategy; corresponding test outputs and attributes must be configured. Spring REST Docs does not automatically distinguish “unit” from “integration” based on folder names.

## 9. Organizing Identifiers When APIs Have Versions, Locales, or Roles

Some systems have multiple variants of the same resource. Not every variant needs its own identifier; split only when the variant produces a different response or contract that needs to be documented.

| Variation axis | When to reflect in the identifier | Example |
| --- | --- | --- |
| API version | When docs and version schemas are independent | §v1-orders-get-success§, §v2-orders-get-success§ |
| Role/permission | When permissions change the response or behavior to document | §orders-get-owner-success§, §orders-get-admin-success§ |
| Locale | When payload or content genuinely differs by language | §products-get-vi§, §products-get-en§ |
| Content type | When the API supports distinct representations to document | §products-get-json§, §products-get-xml§ |
| Scenario | When the same operation has different outcomes | §orders-get-not-found§, §orders-get-forbidden§ |

If locale only changes fixture data without changing schema or contract, use one standard operation and explain locale in the query parameter section. Do not create hundreds of directories just for varying sample data. Conversely, if API v1 and v2 have different fields or statuses, separate them so one version's descriptor table is never embedded into the other by mistake.

## 10. Identifier and Path Checklist

Before completing a documentation change, verify:

- Does the identifier name describe the resource/action/scenario clearly?
- Are any independent tests reusing the same identifier in one output directory?
- Are the required snippets requested by the test?
- Does the path §{snippets}/<identifier>/<file>§ match the name in §document(...)§?
- Does the §snippets§ attribute point to the right test suite's output directory?
- Does the documentation build depend on the snippet-generating tests?
- Could stale outputs hide unrun tests or renames?
- On rename, were all includes in documentation sources updated?
- Are output directories over-split to the point that configuration is hard to track?
- Does the final page display the right scenarios without slipping a success snippet into an error section?

## 11. Common Errors and Troubleshooting

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Include reports file not found | Wrong identifier or attribute; test did not generate snippet | Cross-check §document(...)§ and §snippets§, run tests |
| Page renders, but shows old examples | Leftover generated outputs | Clean outputs, rerun tests, and re-render |
| Two operations have mixed responses | Shared identifier | Split identifiers by scenario |
| Parallel tests overwrite files | Multiple tests share output path | Unique identifiers or separate output directories |
| Snippets appear in an unexpected folder | Test output directory differs from Asciidoctor attribute | Use one shared configuration source or update the attribute |
| Renamed test, yet includes keep old name | Test and docs out of sync | Update both and verify with a clean build |
| Identifier name contains fixture ID | Name coupled to fluctuating test data | Name by resource/method/scenario |
| API versions share snippets | Version schemas got mixed | Split outputs or identifiers clearly by version |
| Only some snippets appear | Test omitted corresponding descriptors | Add descriptors if the element belongs to the contract |
| Documentation build skips running tests | Missing task dependency | Wire test task before compilation task |

## 12. Hands-On Exercise: Managing Names and Snippet Directories

Suppose an order management API has the following scenarios:

- §GET /api/orders/{id}§ returns §200§ when the order exists.
- The same GET returns §404§ when not found.
- §POST /api/orders§ creates an order and returns §201§.
- §POST /api/orders§ returns §400§ if data is invalid.
- §PATCH /api/orders/{id}§ returns §409§ if the current state forbids updates.

**Tasks:**

1. Assign identifiers for all five operations using one consistent convention.
2. Sketch the expected snippet directory tree after tests run.
3. Write a representative §document(...)§ call for the successful §POST§ operation with §requestFields§, §responseHeaders§, and §responseFields§.
4. Create the corresponding include paths for the §orders.adoc§ page.
5. Describe what happens if the GET success and GET 404 tests share the same identifier.
6. Rename the §orders-create-success§ identifier to §orders-post-201§. List the files to update and the verification steps on a clean build.
7. Propose when to split into separate output directories if the project adds integration tests and API v2.

**Passing criteria:** every operation has a unique identifier, directories reflect scenarios accurately, includes trace back to source tests, and a clean build generates all snippets without relying on old outputs.

## 13. Takeaways

- The identifier in §document("...")§ defines the directory grouping an operation's snippets under the configured output directory.
- Good names typically combine **resource + method/action + scenario**, remaining stable and unique within shared outputs.
- One operation has multiple snippets; **multiple operations sharing a route** need separate identifiers when illustrating different responses or scenarios.
- Split output directories by module, suite, or version when independent lifecycles or docs are required; avoid excessive splitting.
- Renaming an identifier requires updating includes and re-verifying from a clean output so leftover snippets are never accidentally embedded.
- Build/CI must run snippet-generating tests before compiling Asciidoctor/Markdown and confirm the exact output directory is used.
