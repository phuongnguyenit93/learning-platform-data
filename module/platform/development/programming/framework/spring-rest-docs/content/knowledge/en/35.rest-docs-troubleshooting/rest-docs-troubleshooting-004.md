# Incorrect Operation Names and Directory Overwrites in Spring REST Docs

## 1. Why Operation Names Matter

In Spring REST Docs, the string passed to `document(...)` is the **document identifier** of the operation. The identifier determines the subdirectory under the output directory where snippets are written.

Example:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(document("orders/get-by-id"));
```

With the `build/generated-snippets` output directory, snippets are written to:

```text
build/generated-snippets/
  orders/
    get-by-id/
      http-request.adoc
      http-response.adoc
      curl-request.adoc
```

If two operations use the same identifier, they write to the same directory and the same snippet filenames. The request/response of the later-running operation can replace previously generated content. The documentation may end up showing the request of one endpoint with the response of another, or including a snippet set that no longer matches the operation.

The **SPRING_REST_DOCS** module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests produce request, response, payload, parameter, and header snippets, which are then assembled into Asciidoctor/Markdown in build/CI. This lesson belongs to the **Troubleshooting** chapter and guides you on detecting incorrect operation names, duplicate identifiers, and snippet directory overwrites.

After this lesson, you will be able to:

1. Understand how the document identifier directly affects the output path.
2. Recognize wrong, missing, duplicate, or unstable identifiers.
3. Partition snippets by operation, test class, test method, and step.
4. Check output and Asciidoctor includes when refactoring operation names.
5. Avoid race conditions when multiple tests write to the same identifier.

## 2. The Document Identifier Is Not the Endpoint Path

| Concept | Example | Role |
| --- | --- | --- |
| HTTP endpoint | GET /api/orders/42 | Actual route called by the test |
| Document identifier | orders/get-by-id | Snippet directory name |
| Output directory | build/generated-snippets | Root containing identifier directories |

The identifier is not automatically inferred from the URL, HTTP method, or controller method. The test author passes it into `document(...)`. Therefore, changing the endpoint path does not automatically change the identifier; changing the identifier does not change the URL called by the test either.

Full path:

```text
<output-directory>/<document-identifier>/<snippet-file>
```

For example, `document("orders/get-by-id")` and `document("orders/create")` are two independent operations even though both belong to `OrderController`.

## 3. Signs of an Incorrect Operation Name

Common symptoms:

- A documentation page pulls in the wrong request or response from another operation.
- Snippets are generated, yet Asciidoctor include reports file not found.
- Output still contains old directory names after tests were renamed.
- Two tests share the same identifier despite having different URLs.
- Running a test individually produces the right output, while running the full suite yields different content.
- Snippets vary depending on execution order or when parallel execution is enabled.

Example of two tests accidentally using the same identifier:

```java
@Test
void getOrder() throws Exception {
    mockMvc.perform(get("/api/orders/42"))
            .andDo(document("order"));
}

@Test
void createOrder() throws Exception {
    mockMvc.perform(post("/api/orders"))
            .andDo(document("order"));
}
```

Both write `http-request.adoc` and `http-response.adoc` into `build/generated-snippets/order`. The create-order test can overwrite the get-order test's snippets or vice versa.

## 4. Diagnosing from the Output Directory

When an overwrite is suspected, inspect the output after running tests:

```text
build/generated-snippets/
  order/
    http-request.adoc
    http-response.adoc
```

If there are many tests but only one identifier directory, review the `document(...)` calls:

```java
document("order")
document("orders")
document("order-detail")
```

Search in the test sources:

```bash
rg -n 'document\\(' src/test
```

With PowerShell:

```powershell
Get-ChildItem -Path src/test -Recurse -File |
    Select-String -Pattern 'document\\('
```

Cross-check each identifier with the operation the test actually performs. Do not rely solely on directory names; open `http-request.adoc` and `http-response.adoc` to confirm the method, URL, status, and payload match.

## 5. Naming Operations Consistently

A readable convention is to group by resource and then name by action:

```text
orders/get-by-id
orders/create
orders/cancel
customers/get-by-id
customers/update-address
```

Recommendations:

- Use names that describe the operation rather than generic names like `test1`, `sample`, or `request`.
- Use kebab-case for readability in file paths.
- Keep identifiers stable so Asciidoctor includes do not break constantly.
- Never share the same identifier across two operations with different contracts.
- Avoid embedding random data, timestamps, or test-run IDs in identifiers.
- If multiple tests verify the same operation, decide whether one test owns the canonical snippets or partition by test class/method.

The identifier name does not have to match the endpoint verbatim. It should describe the operation in documentation terms, while the URL and HTTP method are shown inside the snippets.

## 6. Partitioning by Test Class and Method

If a test class contains multiple documentation methods, use placeholders:

```java
document("{class-name}/{method-name}")
```

Example:

```text
build/generated-snippets/
  order-documentation-tests/
    get-order/
    create-order/
    cancel-order/
```

MockMvc can configure a default identifier via `alwaysDo(...)`:

```java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(documentationConfiguration(restDocumentation))
        .alwaysDo(document("{class-name}/{method-name}"))
        .build();
```

This is useful when every request in the test class needs snippets. If a test needs a custom identifier or performs multiple exchanges, configure `andDo(document(...))` explicitly to control the path.

Common placeholders:

| Placeholder | Result |
| --- | --- |
| {class-name} | Class name in kebab-case |
| {method-name} | Method name in kebab-case |
| {ClassName} | Class name preserved as-is |
| {methodName} | Method name preserved as-is |
| {class_name} | Class name in snake_case |
| {method_name} | Method name in snake_case |
| {step} | Sequence number of the operation in the current test |

Renaming a class or method can change the snippet directory. Update Asciidoctor includes in the same change.

## 7. Multiple HTTP Exchanges in One Test Method

A test method might create an order and then read it back. If both exchanges use `{class-name}/{method-name}`, they can write to the same `http-request.adoc` and `http-response.adoc`.

Use `{step}` to distinguish them:

```java
@Test
void createAndReadOrder() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"productId":"P-42","quantity":1}
                            """))
            .andExpect(status().isCreated())
            .andDo(document("{class-name}/{method-name}/{step}"));

    mockMvc.perform(get("/api/orders/ORD-100"))
            .andExpect(status().isOk())
            .andDo(document("{class-name}/{method-name}/{step}"));
}
```

Output:

```text
build/generated-snippets/
  order-documentation-tests/
    create-and-read-order/
      1/
      2/
```

`{step}` distinguishes consecutive calls within the current test. In the documentation, clearly note that step 1 creates the order and step 2 reads the order.

## 8. Checking Asciidoctor Include Paths

If the identifier is `orders/get-by-id`, the include must reference the exact path:

```asciidoc
== Get Order by ID

include::{snippets}/orders/get-by-id/http-request.adoc[]
include::{snippets}/orders/get-by-id/http-response.adoc[]
```

The `{snippets}` attribute must point to the output root, such as `build/generated-snippets`. Do not append `orders/get-by-id` to `{snippets}` again when the include already contains the identifier, as this creates a duplicated path.

When renaming an identifier from `order-detail` to `orders/get-by-id`, update the `document(...)` call, Asciidoctor includes, scripts checking required snippet files, and any artifact/reference names if the pipeline stores snippet paths.

Cleaning the output before building helps uncover stale includes. Without cleaning, old directories may persist and mask broken includes.

## 9. Distinguishing Intentional Overwrites from Collisions

Not every rewrite to the same identifier is a bug. A test may re-run to regenerate fresh snippets for the same operation. What you must avoid is multiple distinct operations sharing a single identifier.

| Case | Assessment |
| --- | --- |
| One test re-runs and generates the same identifier | Normal |
| Two different tests write to the same identifier | Collision, needs partitioning |
| Same operation has multiple exchanges without step | Potential overwrite, needs separate identifiers |
| Test changed identifier, old output not cleaned | Stale directory |
| Multiple CI jobs write to a shared output directory | Race condition and cross-job overwrite |
| Two tests deliberately contribute to one snippet set | Valid only when ordered sequentially and intentional |

If multiple tests need to document the same operation, decide which test serves as the canonical snippet source. Remaining tests can assert behavior without generating snippets, or use separate identifiers per test perspective.

## 10. Parallel Execution and Output Isolation

When tests run in parallel, two operations sharing an identifier can write to the same file concurrently. The outcome becomes nondeterministic, especially when request/response snippets are created at different moments.

Solutions:

- Use unique identifiers per class/method/step.
- Do not share an output root across independent CI jobs.
- If multiple test tasks produce snippets, partition by task or arrange sequential task dependencies.
- Clean the output once before the producer group; do not let individual tasks wipe another task's shared directory.
- Do not use random identifiers to mask collisions, because include paths will become unstable.

With REST Assured, WebTestClient, and MockMvc, the same principle applies: the identifier belongs to the documented operation and must be unique within the active output root.

## 11. Quick Check When Snippets Are Overwritten

1. Run clean to remove stale snippets.
2. Search for all `document(...)` calls in the test source.
3. Build a table mapping test method -> HTTP operation -> identifier.
4. Check for duplicate identifiers.
5. Run each test individually and inspect its request/response snippets.
6. Run the entire test suite, including parallel mode if enabled by the project.
7. Verify Asciidoctor include paths and re-render the documentation.

Example checklist table:

| Test | HTTP operation | Expected identifier |
| --- | --- | --- |
| getOrder | GET /api/orders/42 | orders/get-by-id |
| createOrder | POST /api/orders | orders/create |
| cancelOrder | DELETE /api/orders/42 | orders/cancel |

If two rows share an identifier while their snippet contents differ, that signals a collision to resolve.

## 12. Hands-On Exercise

Create a test class `OrderDocumentationTests` with three methods:

- getOrder
- createOrder
- cancelOrder

Steps:

1. Intentionally make all three tests call `document("order")`.
2. Run each test and observe the shared output being overwritten.
3. Change the identifiers to `orders/get-by-id`, `orders/create`, and `orders/cancel`.
4. Update the corresponding Asciidoctor includes.
5. Add a test method performing two exchanges using `{step}`.
6. Run a clean build and verify each operation has the right request/response snippets.
7. Run tests in parallel and confirm there are no identifier collisions.

**Completion criteria:** Each operation has a clear, unique identifier; snippets accurately reflect HTTP method, URL, status, and payload; Asciidoctor includes point to the right directories; clean build leaves no stale directories; parallel execution does not alter snippet contents.

## 13. Key Takeaways

The document identifier is the snippet directory name specified by the test, not the endpoint path. Two different operations sharing an identifier write to the same snippet files and can overwrite content. Use descriptive names like `orders/get-by-id`, partition via `{class-name}/{method-name}`, and add `{step}` when a method documents multiple exchanges. When changing an identifier, update Asciidoctor includes and clean old output. Inspect request/response snippets after both individual tests and full-suite runs to catch collisions, stale output, and race conditions.

### References

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Spring REST Docs — MockMvc Integration](https://docs.spring.io/spring-restdocs/reference/getting-started/using-mock-mvc.html)
- [Spring REST Docs — REST Assured Integration](https://docs.spring.io/spring-restdocs/reference/getting-started/using-rest-assured.html)
- [Spring REST Docs — WebTestClient Integration](https://docs.spring.io/spring-restdocs/reference/getting-started/using-webtestclient.html)
