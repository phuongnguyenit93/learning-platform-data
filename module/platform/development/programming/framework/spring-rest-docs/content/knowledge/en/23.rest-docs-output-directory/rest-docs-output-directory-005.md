# Identifying Test Class and Test Method in Snippet Paths

## 1. Why Include Class and Method Names in the Path?

A single test class may test multiple operations:

```java
class OrderDocumentationTests {
    @Test void getOrderById() { /* ... */ }
    @Test void createOrder() { /* ... */ }
    @Test void cancelOrder() { /* ... */ }
}
```

Each test can generate identically named snippets such as `http-request.adoc`, `http-response.adoc`, `curl-request.adoc`, and `request-fields.adoc`. If all tests write to the same directory, files with the same name can overwrite one another or cause the documentation to reference the wrong operation.

Spring REST Docs solves this with the **document identifier** — the identifier string passed to `document(...)`. The identifier becomes a subdirectory under the output directory. You can provide a fixed identifier or use placeholders to include the test class name, test method name, and operation sequence number in the path.

The **SPRING_REST_DOCS** module produces verifiable REST API documentation using HTTP tests with MockMvc, WebTestClient, or REST Assured. Tests generate snippets for requests, responses, payloads, parameters, and headers; these are then compiled into Asciidoctor/Markdown and integrated into build/CI. This lesson belongs to the **Output Directory** chapter, focusing on identifying test classes and test methods in snippet paths.

After this lesson, you will be able to:

1. Distinguish the root output directory from the document identifier.
2. Use `{class-name}` and `{method-name}` to partition snippets automatically.
3. Choose placeholders matching an appropriate naming convention.
4. Use `{step}` when a single test method documents multiple HTTP operations.
5. Organize includes in Asciidoctor without mixing up snippets between tests.

## 2. Two Path Levels to Distinguish

Suppose Gradle uses the output directory:

```text
build/generated-snippets
```

When a test calls:

```java
document("order-detail")
```

Spring REST Docs creates snippets under:

```text
build/generated-snippets/
  order-detail/
    curl-request.adoc
    http-request.adoc
    http-response.adoc
    httpie-request.adoc
    request-body.adoc
    response-body.adoc
```

Here:

- **Output directory** is the root directory receiving all snippets, e.g., `build/generated-snippets`.
- **Document identifier** is the subdirectory for a specific operation, e.g., `order-detail`.
- **Snippet file** is the specific file generated inside the identifier directory, e.g., `http-request.adoc`.

Full path:

```text
<output-directory>/<document-identifier>/<snippet-file>
```

Changing the output directory moves the entire snippet tree. Changing the identifier partitions an operation's snippets within the same output directory. These two configurations do not replace each other.

## 3. Fixed Identifiers and Collision Risks

Fixed identifier example:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(document("order-detail"));
```

This approach works well when only one test owns that identifier. If multiple tests use `order-detail`, they write into the same directory and the same files named `http-request.adoc` and `http-response.adoc`. Contents can overwrite each other; parallel execution also risks file-write contention.

Use a fixed identifier only when tests intentionally share the same snippet set or when a single test generates that snippet set. When each test describes a different operation, partition by class and method.

## 4. Placeholders in Document Identifiers

Spring REST Docs supports the following parameters:

| Placeholder | Meaning | Example |
| --- | --- | --- |
| `{methodName}` | Original test method name | `getOrderById` |
| `{method-name}` | Method name in kebab-case | `get-order-by-id` |
| `{method_name}` | Method name in snake_case | `get_order_by_id` |
| `{ClassName}` | Original simple class name | `OrderDocumentationTests` |
| `{class-name}` | Class name in kebab-case | `order-documentation-tests` |
| `{class_name}` | Class name in snake_case | `order_documentation_tests` |
| `{step}` | Service call count in the current test | `1`, `2`, `3` |

Placeholders can be combined with slashes:

```java
document("{class-name}/{method-name}")
```

For example, the `getOrderById` test method in `OrderDocumentationTests` generates snippets into:

```text
build/generated-snippets/
  order-documentation-tests/
    get-order-by-id/
      http-request.adoc
      http-response.adoc
      curl-request.adoc
```

Placeholders are case-sensitive. `{ClassName}` and `{class-name}` have different meanings; choose the exact form from the table.

## 5. Configuring the Identifier Once per Test Class

With MockMvc, you can configure a default document identifier in `@BeforeEach`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTests {

    @Autowired
    private WebApplicationContext context;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
                .apply(documentationConfiguration(restDocumentation))
                .alwaysDo(document("{class-name}/{method-name}"))
                .build();
    }

    @Test
    void getOrderById() throws Exception {
        this.mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk());
    }
}
```

`alwaysDo(document(...))` automatically documents requests executed through MockMvc with a default identifier derived from the test context. This is convenient when every request in the class needs snippets. If a test needs custom configuration, use `andDo(document(...))` and consider omitting `alwaysDo` to avoid unintentionally generating two sets of snippets.

## 6. Identifying Multiple Operations in One Test Method with {step}

A test method sometimes executes multiple HTTP exchanges, such as creating an order, reading the newly created order, and then canceling it. If all three requests use `{class-name}/{method-name}`, they target the same directory and can overwrite identically named snippets.

The `{step}` placeholder provides the sequence number of the service call in the current test:

```java
@Test
void createReadAndCancelOrder() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType("application/json")
                    .content("""
                            {"productId":"P-42","quantity":1}
                            """))
            .andExpect(status().isCreated())
            .andDo(document("{class-name}/{method-name}/{step}"));

    mockMvc.perform(get("/api/orders/ORD-100"))
            .andExpect(status().isOk())
            .andDo(document("{class-name}/{method-name}/{step}"));

    mockMvc.perform(delete("/api/orders/ORD-100"))
            .andExpect(status().isNoContent())
            .andDo(document("{class-name}/{method-name}/{step}"));
}
```

Illustrative directory tree:

```text
build/generated-snippets/
  order-documentation-tests/
    create-read-and-cancel-order/
      1/
      2/
      3/
```

`{step}` is the service call number within the current test, not a global sequence number across the test suite. When documenting multiple operations in one method, explain the meaning of each step in the documentation so readers understand which action corresponds to steps 1, 2, and 3.

## 7. Combining Identifiers with Custom Output Directories

With JUnit 5, `RestDocumentationExtension` accepts the output directory via its constructor:

```java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/api-snippets");
```

When the identifier is `{class-name}/{method-name}`, the structure looks like:

```text
build/api-snippets/
  order-documentation-tests/
    get-order-by-id/
      http-request.adoc
      http-response.adoc
```

The custom output directory is the root; the identifier still creates subdirectories beneath that root.

With JUnit 4, the `JUnitRestDocumentation` rule accepts the output directory in its constructor:

```java
@Rule
public JUnitRestDocumentation restDocumentation =
        new JUnitRestDocumentation("target/api-snippets");
```

If using Spring Boot `@AutoConfigureRestDocs`, you can configure `outputDir` for the snippet root. Identifiers are still passed to `document(...)` as usual. Avoid letting a JUnit extension, rule, or auto-configuration write to different roots while Asciidoctor only reads from one place.

## 8. Usage with WebTestClient and REST Assured

Placeholder identifiers also work with WebTestClient:

```java
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("{class-name}/{method-name}"));
```

With REST Assured, the identifier is passed into the document filter:

```java
given(this.spec)
        .filter(document("{class-name}/{method-name}"))
        .when()
        .get("/api/orders/42")
        .then()
        .statusCode(200);
```

If a test method sends multiple requests, use `{step}` in each operation's identifier. The identifier only determines snippet placement; it does not replace WebTestClient configuration, `RequestSpecification`, or the HTTP target.

## 9. Naming Conventions and Directory Structure

A readable structure:

```text
generated-snippets/
  order-documentation-tests/
    get-order-by-id/
    create-order/
    cancel-order/
  customer-documentation-tests/
    get-customer-by-id/
    update-customer-address/
```

Recommendations:

- Use `{class-name}` to group by test class or API domain.
- Use `{method-name}` to represent operations in kebab-case.
- Choose one consistent language and method naming convention.
- Use `{step}` when a single test method has multiple exchanges needing separate snippets.
- Do not include random IDs or timestamps in the identifier unless truly necessary.
- Keep identifiers stable so Asciidoctor include pages do not have to be updated on every test run.

Test method names indirectly become part of the documentation structure. Renaming a method can rename snippet directories; review documentation includes alongside such changes.

## 10. Including Snippets in Asciidoctor

With the identifier `{class-name}/{method-name}`, Asciidoctor includes the corresponding exact paths:

```asciidoc
= Order API

== Get Order by ID

include::{snippets}/order-documentation-tests/get-order-by-id/http-request.adoc[]
include::{snippets}/order-documentation-tests/get-order-by-id/http-response.adoc[]

== Create Order

include::{snippets}/order-documentation-tests/create-order/http-request.adoc[]
include::{snippets}/order-documentation-tests/create-order/http-response.adoc[]
```

The `{snippets}` variable must point to the root output directory, e.g., `build/generated-snippets`. Do not include the identifier in `{snippets}` again if the include already specifies class/method, as this can produce duplicate path segments.

With `{step}`, include the corresponding step directory:

```asciidoc
== Create, Read, and Cancel Order Workflow

=== Step 1 — Create Order
include::{snippets}/order-documentation-tests/create-read-and-cancel-order/1/http-request.adoc[]

=== Step 2 — Read Order
include::{snippets}/order-documentation-tests/create-read-and-cancel-order/2/http-request.adoc[]

=== Step 3 — Cancel Order
include::{snippets}/order-documentation-tests/create-read-and-cancel-order/3/http-request.adoc[]
```

## 11. Common Mistakes

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Snippets from one test appear in another test's documentation | Multiple tests share a fixed identifier | Use `{class-name}/{method-name}` |
| Only snippets from the last HTTP call are kept | Multiple requests in the same method write to the same directory | Add `{step}` |
| Asciidoctor reports snippet not found | Include path does not match resolved placeholders | Inspect the output directory tree after tests run |
| Include path has the class name duplicated | `{snippets}` already contains the identifier while the include adds it again | Keep `{snippets}` as the output root |
| Renaming a test breaks documentation build | `{method-name}` generates a new directory while includes remain unchanged | Update includes or use an explicit identifier |
| Parallel runs produce unstable outputs | Two tests write to the same identifier | Create distinct identifiers by class/method/step |
| Method folder names are hard to read | Used `{methodName}` preserving camelCase | Use `{method-name}` for kebab-case |
| Identifier changes on every run | Embedded random ID/time in the name | Use stable test names; keep dynamic data inside snippets |

## 12. Build and CI

Basic workflow:

1. Choose a stable output root, e.g., `build/generated-snippets`.
2. Configure `RestDocumentationExtension`, the JUnit 4 rule, or Spring Boot `@AutoConfigureRestDocs`.
3. Choose an identifier convention, typically `{class-name}/{method-name}`.
4. For tests with multiple exchanges, add `{step}`.
5. Run tests to generate snippets.
6. Run Asciidoctor and verify that all includes point to the generated directory tree.

Gradle example when tasks are configured:

```groovy
val snippetsDir by extra { file("build/generated-snippets") }

tasks.test {
    outputs.dir(snippetsDir)
    useJUnitPlatform()
}

tasks.named("asciidoctor") {
    inputs.dir(snippetsDir)
    dependsOn(tasks.test)
}
```

If a test method is renamed, a build may generate a new directory while Asciidoctor still includes the old one. CI should build from a clean output and require all includes to resolve cleanly. Avoid letting stale snippets from a previous run produce a false green build.

## 13. Practice Exercise

Create an `InventoryDocumentationTests` class containing:

- `getStockBySku`
- `reserveStock`
- `releaseReservation`

Steps:

1. Configure the output root as `build/generated-snippets`.
2. Use the `{class-name}/{method-name}` identifier for each test.
3. In `reserveStock`, perform two exchanges: create a reservation, then read the reservation; use `{step}` to partition them.
4. Run the tests and inspect the output directory tree.
5. Write Asciidoctor includes for the request/response snippets of each method and each step.
6. Rename one test method and re-run the build to observe the impact on include paths.
7. Run `test` and `asciidoctor` in CI.

**Completion criteria:** Each test has its own snippet directory; multiple exchanges in one method do not overwrite each other; identifiers are stable and readable; output root and include paths are clearly separated; a clean build still generates and includes all snippets.

## 14. Key Takeaways

The output directory is the root directory, whereas the document identifier determines the subdirectory for each operation. Spring REST Docs lets you use `{class-name}`, `{method-name}`, camelCase/snake_case variants, and `{step}` in identifiers to partition snippets automatically. Use `{class-name}/{method-name}` for most tests; add `{step}` when one method documents multiple requests. Point `{snippets}` to the output root, keep test names and identifiers stable, and verify Asciidoctor includes in build/CI so snippets are neither overwritten nor misreferenced.

### References

- [Spring REST Docs — Generating Documentation Snippets](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Spring REST Docs — RestDocumentationExtension API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/RestDocumentationExtension.html)
- [Spring Boot — Auto-configured Spring REST Docs Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Guides — Creating API Documentation with REST Docs](https://spring.io/guides/gs/testing-restdocs/)
