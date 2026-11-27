# Parameterized output directories

## 1. Purpose of Parameterized Output Directories

In Spring REST Docs, each `document(...)` call can generate multiple snippets such as HTTP request, HTTP response, headers, parameters, and payload. If multiple tests use the same document identifier, they can write into the same directory and cause conflicts or make results hard to trace.

A **parameterized output directory** allows inserting information about the current test into the document identifier so Spring REST Docs generates distinct paths automatically. Instead of manually concatenating class/test strings in every call, you use placeholders such as `{class-name}`, `{method-name}`, and `{step}`.

For example:

~~~java
mockMvc.perform(get("/orders/42"))
    .andDo(document("{class-name}/{method-name}"));
~~~

With test class `OrderDocumentationTest` and test method `getOrderDetails`, the output will be placed under:

~~~text
order-documentation-test/
└── get-order-details/
    ├── http-request.adoc
    ├── http-response.adoc
    └── ...
~~~

Parameterized paths are especially useful when configuring documentation once in setup and reusing it across multiple test methods. Each test gets its own directory without having to rewrite fixed identifiers in every location.

In the **SPRING_REST_DOCS** module, HTTP tests using MockMvc, WebTestClient, or REST Assured generate snippets to compile into Asciidoctor/Markdown and feed into build/CI. Naming paths systematically helps separate snippets by class, method, and HTTP call; this prevents documentation from accidentally sharing outputs across different tests.

## 2. Supported Placeholders

Spring REST Docs supports the following placeholders in document identifiers:

| Placeholder | Meaning | Example Result |
| --- | --- | --- |
| `{methodName}` | Test method name as-is | `getOrderDetails` |
| `{method-name}` | Method name in kebab-case | `get-order-details` |
| `{method_name}` | Method name in snake_case | `get_order_details` |
| `{ClassName}` | Simple name of the test class, preserved as-is | `OrderDocumentationTest` |
| `{class-name}` | Class name in kebab-case | `order-documentation-test` |
| `{class_name}` | Class name in snake_case | `order_documentation_test` |
| `{step}` | Sequence number of the service call in the current test | `1`, `2`, `3` |

### 2.1. Choosing a Consistent Casing Style

Kebab-case works well for directory names and include paths:

~~~java
document("{class-name}/{method-name}");
~~~

Snake-case is also valid if the team follows that convention:

~~~java
document("{class_name}/{method_name}");
~~~

Verbatim names are useful when you want to mirror Java identifiers closely, but they can contain uppercase letters and feel less uniform when scanning directory trees. Choose one style for the entire module so documentation authors can easily predict paths.

### 2.2. Placeholders Are Not Maven/Gradle Variables

The placeholders above are resolved by Spring REST Docs inside the document identifier when the test executes. They are not Asciidoctor attributes, environment variables, or properties in `pom.xml`/`build.gradle`. For example:

~~~java
document("{class-name}/{method-name}");
~~~

is resolved by REST Docs into a snippet path; whereas:

~~~adoc
include::{snippets}/order-documentation-test/get-order-details/http-request.adoc[]
~~~

is an include processed by Asciidoctor when rendering the documentation. The two stages are related, but use different syntax and execution times.

## 3. Combining Class and Method to Separate Outputs

Suppose you have a test class:

~~~java
class OrderDocumentationTest {

    @Test
    void getOrderDetails() {
        // Send GET /orders/42 request
    }

    @Test
    void createOrder() {
        // Send POST /orders request
    }
}
~~~

If each operation records with:

~~~java
document("{class-name}/{method-name}");
~~~

the two snippet sets are written to separate directories:

~~~text
build/generated-snippets/
└── order-documentation-test/
    ├── get-order-details/
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── create-order/
        ├── http-request.adoc
        └── http-response.adoc
~~~

This structure provides three benefits:

- Looking at the path immediately reveals which test class and API behavior generated the snippets.
- Test methods do not overwrite each other's identically named snippets.
- When modifying or deleting a test, you can pinpoint the exact set of snippets that needs updating.

If multiple test classes test the same endpoint with different fixtures, keep both class and method in the identifier. Only use `{method-name}` alone when you guarantee method names are unique across all tests writing to the same output root.

## 4. Reusing Configuration with MockMvc

### 4.1. Configuring Once in Setup

A common pattern is configuring MockMvc in `@BeforeEach` and using `alwaysDo(...)` to write snippets after every request:

~~~java
@ExtendWith(RestDocumentationExtension.class)
@WebMvcTest(OrderController.class)
class OrderDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(documentation))
            .alwaysDo(document("{class-name}/{method-name}/{step}"))
            .build();
    }

    @Test
    void getOrderDetails() throws Exception {
        this.mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk());
    }

    @Test
    void createOrder() throws Exception {
        this.mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"product\":\"book\"}"))
            .andExpect(status().isCreated());
    }
}
~~~

Assuming the first test sends only one request, the path looks like:

~~~text
order-documentation-test/get-order-details/1/
~~~

The second test gets its own output:

~~~text
order-documentation-test/create-order/1/
~~~

`alwaysDo(...)` attaches a result handler to every request executed through the MockMvc instance. Therefore, you do not need to call `andDo(document(...))` in each test method.

### 4.2. When a Test Sends Multiple Requests

The `{step}` placeholder distinguishes service calls within the current test. For example:

~~~java
@Test
void createThenReadOrder() throws Exception {
    mockMvc.perform(post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"product\":\"book\"}"))
        .andExpect(status().isCreated());

    mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk());
}
~~~

With the identifier `{class-name}/{method-name}/{step}`, snippets are separated in sequence:

~~~text
order-documentation-test/
└── create-then-read-order/
    ├── 1/
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── 2/
        ├── http-request.adoc
        └── http-response.adoc
~~~

This is especially useful when documenting a multi-request workflow such as creating a resource, querying the newly created resource, and updating its status.

### 4.3. Writing Snippets Only for Relevant Requests

Because `alwaysDo(...)` runs for every request passing through the MockMvc instance, consider whether to document all requests in a test or only specific ones. If a test makes auxiliary requests such as logging in, initializing fixtures, or calling endpoints not part of the public documentation, you can configure `document(...)` individually per request rather than applying a global handler.

When each test has only one request to record, using `{class-name}/{method-name}` is sufficient. Add `{step}` when there are multiple calls that need separate snippets.

## 5. Reusing Configuration with REST Assured

REST Assured uses filters to observe requests/responses and generate snippets. You can put a parameterized document identifier into a shared request specification:

~~~java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    this.specification = new RequestSpecBuilder()
        .addFilter(documentationConfiguration(documentation))
        .addFilter(document("{class-name}/{method-name}/{step}"))
        .build();
}
~~~

In each test:

~~~java
given(this.specification)
    .when()
    .get("/orders/42")
    .then()
    .statusCode(200);
~~~

The document filter is registered once in the specification. Placeholders are resolved according to the test class, test method, and sequence number of the current service call. If a test sends multiple requests using the same specification, `{step}` creates a separate directory for each call.

For REST Assured to write snippets under the right output root, the `documentationConfiguration(documentation)` filter must use the REST Docs context provider. Do not omit the context configuration filter and add only the document filter; the document filter needs the context to know the output directory and test metadata.

## 6. WebTestClient and Differences in Application

WebTestClient uses a Spring REST Docs filter to record documentation. Single-request example:

~~~java
webTestClient
    .mutateWith(documentationConfiguration(documentation))
    .get()
    .uri("/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("{class-name}/{method-name}"));
~~~

With WebTestClient, the document operation is typically attached to the response assertion step via `consumeWith(document(...))`. You can therefore use placeholders inside that call's identifier. If a test issues multiple requests, choose an identifier with `{step}` or a clear scenario name so snippet sets do not collide.

Specific builder and filter APIs may differ depending on the Spring Framework / Spring REST Docs version. Check how WebTestClient integrates in your project's dependency version before adopting a shared automatic setup. The principle remains the same: each documentation call needs a resolved identifier, and the context provides the output root.

## 7. Practical Rules for Choosing Identifiers

| Scenario | Suggested Identifier | Reason |
| --- | --- | --- |
| Each test method makes one request | `{class-name}/{method-name}` | Separates by class and method |
| One test has multiple requests to document | `{class-name}/{method-name}/{step}` | Separates each individual call |
| Class name is already reflected in package/module path | `{method-name}/{step}` | Shorter while still separating test methods |
| Test class has method names overlapping another class | `{class-name}/{method-name}` | Prevents collisions across classes |
| Need human-readable paths | Kebab-case | Consistent with URLs/paths |
| Want to closely match Java names | `{ClassName}/{methodName}` | Preserves original casing |

Avoid identifiers with only `{step}` when multiple test classes or methods share an output root. The step counter resets within the scope of the current test; the value `1` will repeat across different tests. Always include method or class to provide a namespace when outputs need separation.

Do not put dynamic test data such as order IDs, UUIDs, timestamps, or emails into the path. Those values produce unpredictable directory trees, make includes difficult, and can expose unnecessary data. Class/method/step placeholders are more stable because they are based on test structure.

## 8. Organizing Includes in Asciidoctor

Suppose the document identifier is `{class-name}/{method-name}/{step}`. After running tests, snippets reside under:

~~~text
build/generated-snippets/
└── order-documentation-test/
    └── create-then-read-order/
        ├── 1/
        │   ├── http-request.adoc
        │   └── http-response.adoc
        └── 2/
            ├── http-request.adoc
            └── http-response.adoc
~~~

An Asciidoctor page can include them:

~~~adoc
== Create Order

=== Order creation request
include::{snippets}/order-documentation-test/create-then-read-order/1/http-request.adoc[]

=== Order creation response
include::{snippets}/order-documentation-test/create-then-read-order/1/http-response.adoc[]

=== Request to read the newly created order
include::{snippets}/order-documentation-test/create-then-read-order/2/http-request.adoc[]

=== Read order response
include::{snippets}/order-documentation-test/create-then-read-order/2/http-response.adoc[]
~~~

Asciidoctor does not natively understand JUnit placeholders like `{class-name}`. Those placeholders were already resolved by REST Docs at test execution time; in source documentation, you must include the actual resulting paths, or use build-process attributes/partials if the team wants to abstract paths.

If you rename a test class or method, the generated directories change accordingly. Update the corresponding includes; in a pull request, you can review the diff between newly generated snippets and the include paths.

## 9. Avoiding Overwrites and Managing Stale Outputs

Parameterized identifiers separate tests, but they do not automatically clean up old snippets. When renaming a test method or deleting a test, output directories created in previous builds may linger until the build directory is cleaned.

Best practices:

1. Include both class and method in the identifier if tests span multiple classes.
2. Use step only when a test has multiple requests that need documenting.
3. Keep method names stable if Asciidoctor includes directly from those directories.
4. Run a clean build when changing naming conventions or refactoring test names.
5. Do not manually edit test-generated snippets.

With Gradle:

~~~bash
./gradlew clean test asciidoctor
~~~

With Maven:

~~~bash
mvn clean verify
~~~

In CI, tests must run before the documentation rendering step. When snippets do not appear, check whether tests reached the document handler/filter, then inspect the output root and resolved identifier.

## 10. Common Errors

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| All tests write to the same directory | Used a fixed identifier | Use `{class-name}/{method-name}` |
| Two classes with the same method name overwrite each other | Used only `{method-name}` | Add `{class-name}` |
| Multiple requests in one test overwrite the same snippet | Missing `{step}` when using a shared handler | Add `{step}` to the identifier |
| Step directories restart at `1` in another test | Step count is scoped to the current test | Combine step with class and method |
| Asciidoctor include not found after renaming a test | Snippet path changed with the placeholder | Update includes to match the new output |
| Old snippets remain in build | Deleted/renamed tests without cleaning | Run a clean build |
| REST Assured filter does not know the output root | Missing documentation configuration filter/context | Add the `documentationConfiguration` filter using the same provider |
| MockMvc writes unwanted snippets for auxiliary requests | `alwaysDo` applies to every request | Attach `document` only to requests needing docs or split tests |

## 11. Practice Exercise

Create a `ProductDocumentationTest` class with three tests:

- `getProductDetails`: sends a GET request once.
- `createProduct`: sends a POST request once.
- `createThenReadProduct`: sends a POST followed by a GET within the same test.

Steps:

1. Configure MockMvc with `alwaysDo(document("{class-name}/{method-name}/{step}"))`.
2. Run the tests and observe the directory structure for each class/method/step.
3. Verify that the two single-request tests both produce step directory `1`, but under different method directories.
4. Verify that the workflow test produces two directories, `1` and `2`.
5. Include the workflow's request/response snippets in Asciidoctor.
6. Rename a test method, run `clean test asciidoctor`, and update includes to the new path.
7. Try an identifier containing only `{step}` in another test class to observe the collision risk, then fix it back to the class/method/step convention.

**Completion criteria:** Document identifiers produce stable, predictable output paths; test methods/classes do not overwrite one another; multiple requests within the same test are separated by step; Asciidoctor includes the latest snippets accurately.

## References

- [Spring REST Docs — Using Parameterized Output Directories](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — RestDocumentationContext API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/RestDocumentationContext.html)
- [Spring REST Docs — MockMvc API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html)
