# Preventing Snippet Overwrites Between Tests

## 1. Why Can Snippets Be Overwritten?

Spring REST Docs writes the snippets for a documentation call into a directory determined by the **output directory** combined with the **document identifier**. If two tests use the same output root and the same identifier, they write to the exact same location. Files with the same names such as `http-request.adoc`, `http-response.adoc`, or `request-fields.adoc` can be overwritten by the later run.

Example with two tests:

~~~java
@Test
void getOrderAsCustomer() throws Exception {
    mockMvc.perform(get("/orders/42"))
        .andDo(document("orders/get"));
}

@Test
void getOrderAsAdmin() throws Exception {
    mockMvc.perform(get("/admin/orders/42"))
        .andDo(document("orders/get"));
}
~~~

Both write into:

~~~text
build/generated-snippets/orders/get/
~~~

After both tests run, the directory contains only one set of snippets for that identifier. The final contents depend on write order; the documentation might mistakenly describe the customer request as the admin request or vice versa.

In the **SPRING_REST_DOCS** module, HTTP tests using MockMvc, WebTestClient, or REST Assured serve as the source generating snippets for Asciidoctor/Markdown compilation and build/CI pipelines. For documentation to be trustworthy, each documented operation must have a stable identifier that is unique within the scope of the output root it uses.

## 2. Understanding the Uniqueness Scope of a Document Identifier

A snippet path consists of two parts:

~~~text
<output-directory>/<document-identifier>/<snippet-file>
~~~

For example:

~~~text
build/generated-snippets/
└── orders/
    └── get-customer/
        ├── http-request.adoc
        └── http-response.adoc
~~~

To prevent overwrites, ensure the pair **output directory + document identifier** does not collide across tests that produce different content.

| Configuration | Collision Likelihood |
| --- | --- |
| Same output root, same identifier | Yes; two tests write to the same directory |
| Same output root, different identifiers | No direct overwrite |
| Different output roots, same identifier | No overwrite if the roots are genuinely distinct |
| Same identifier, tests run in parallel | High risk; concurrent writes to the same files possible |

Method names alone are not guaranteed to be unique. Another class might have a method with the same name; a parameterized test might run multiple invocations with different data; a workflow test might call `document` multiple times. Choose identifiers based on the unit of documentation that needs to be distinguished.

## 3. Separating Identifiers by Class and Method

Spring REST Docs supports placeholders in document identifiers:

| Placeholder | Meaning |
| --- | --- |
| `{class-name}` | Test class name in kebab-case |
| `{ClassName}` | Class name as-is |
| `{class_name}` | Class name in snake_case |
| `{method-name}` | Test method name in kebab-case |
| `{methodName}` | Method name as-is |
| `{method_name}` | Method name in snake_case |
| `{step}` | Sequence number of the `document` call in the current test |

For example:

~~~java
mockMvc.perform(get("/orders/42"))
    .andDo(document("{class-name}/{method-name}"));
~~~

Two classes with identically named methods still produce distinct directories:

~~~text
build/generated-snippets/
├── customer-order-documentation-test/
│   └── get-order/
└── admin-order-documentation-test/
    └── get-order/
~~~

This is a good choice when test classes represent different permission roles, API groups, or business scenarios. If you only use `{method-name}`, classes sharing the same method name will collide.

### 3.1. Naming Identifiers Explicitly

For tests with few operations, explicit names are also readable:

~~~java
document("orders/customer/get-one");
document("orders/admin/get-one");
~~~

For large test suites, placeholders avoid repeating the class name:

~~~java
document("{class-name}/{method-name}");
~~~

Both approaches can be combined. What matters is that the name accurately reflects the request's intent and does not collide with another test.

## 4. Using {step} When One Test Produces Multiple Snippet Sets

A single test may perform multiple requests and want to save snippets for each one. If all requests use the same identifier, later calls will overwrite earlier results.

For example:

~~~java
@Test
void createThenReadOrder() throws Exception {
    mockMvc.perform(post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"product\":\"book\"}"))
        .andExpect(status().isCreated())
        .andDo(document("orders/create"));

    mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andDo(document("orders/get"));
}
~~~

If a single handler automatically writes snippets for every request, you can use:

~~~java
.alwaysDo(document("{class-name}/{method-name}/{step}"))
~~~

Then each `document` call inside the test is separated by step:

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

Do not add `{step}` mechanically when a test makes only one request. Use class/method to create a namespace; use step when multiple requests within the same test have documentation value.

## 5. Parameterized Tests and Varying Input Data

A JUnit parameterized test can run the same method multiple times with different data:

~~~java
@ParameterizedTest
@ValueSource(strings = {"basic", "pro"})
void getOrdersByPlan(String plan) throws Exception {
    mockMvc.perform(get("/orders").param("plan", plan))
        .andExpect(status().isOk())
        .andDo(document("orders/by-plan"));
}
~~~

All invocations share the same method name and the fixed identifier `orders/by-plan`. They write to the same directory; later invocations replace snippets from earlier invocations. The final output fails to represent both cases completely.

There are three ways to resolve this:

1. **Split into separate test methods** if the cases have distinct documentation meaning and need independent includes.
2. **Separate identifiers by scenario** using meaningful fixed names like `orders/by-plan-basic` and `orders/by-plan-pro`.
3. **Use the test framework's invocation-distinguishing mechanism** to generate unique identifiers, if the framework provides stable, controllable values.

Avoid using random data such as UUIDs or timestamps as identifiers. Directory names would change on every run, making Asciidoctor includes difficult and builds non-reproducible. When input values form a finite set, stable scenario names are easier to manage.

Example of splitting by scenario:

~~~java
@Test
void getBasicPlanOrders() throws Exception {
    documentOrdersForPlan("basic", "orders/by-plan-basic");
}

@Test
void getProPlanOrders() throws Exception {
    documentOrdersForPlan("pro", "orders/by-plan-pro");
}
~~~

## 6. Avoiding Conflicts During Parallel Test Execution

Separating identifiers by class/method is the first step. If two JVMs, two Gradle workers, or two Maven modules write to the **same physical output directory** with the same identifier, they can still collide.

For example:

~~~text
Worker A ── document("orders/get") ──┐
                                    ├── build/generated-snippets/orders/get/
Worker B ── document("orders/get") ──┘
~~~

File write operations can interleave. Even if two tests produce identical content, concurrent writes can yield non-deterministic results depending on how files are created and replaced.

Ways to mitigate the risk:

- Use identifiers containing class and method to isolate independent tests.
- If the same test suite runs in multiple processes or modules with the same identifiers, assign separate output roots per task/module/process and merge outputs after tests finish.
- Alternatively, serialize test groups that write to the same output root if paths cannot be separated.
- Do not let multiple CI jobs share the same workspace/output directory without an isolation mechanism.

Example of two Gradle tasks using separate output roots:

~~~groovy
tasks.register('testAdmin', Test) {
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    systemProperty 'restdocs.outputDir', layout.buildDirectory.dir('snippets/admin').get().asFile
}

tasks.register('testCustomer', Test) {
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    systemProperty 'restdocs.outputDir', layout.buildDirectory.dir('snippets/customer').get().asFile
}
~~~

This example only illustrates the idea of isolating outputs. The test harness must read the `restdocs.outputDir` system property and pass it as REST Docs' output directory; not every Spring Boot annotation setup automatically honors this custom property. If using `@AutoConfigureRestDocs(outputDir = "...")` with a hardcoded path, adjust the test configuration so each task genuinely receives its own root.

With Maven, you can configure Surefire system properties per profile/module and pass the same value to the Asciidoctor plugin. Avoid having modules write into a shared directory if they share overlapping identifiers.

## 7. Using alwaysDo(...) Selectively

`alwaysDo(document(...))` is convenient because it automatically writes snippets for every request going through a MockMvc instance:

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(documentationConfiguration(documentation))
    .alwaysDo(document("{class-name}/{method-name}/{step}"))
    .build();
~~~

However, if a test also sends auxiliary requests such as logging in, seeding data, or calling internal endpoints, all of them can generate snippets. This bloats the output and can cause overwrites if identifiers are not sufficiently distinct.

Choose one of these approaches:

- Use `alwaysDo` when every request in the test is part of the documentation.
- Attach `andDo(document(...))` only to requests meant to be published.
- Separate fixture setup from the request being documented.
- Use a separate test for each API operation if independent snippets and clear names are needed.

Do not generate snippets for requests outside the API contract merely because they pass through the same MockMvc instance.

## 8. Organizing Asciidoctor Includes by Identifier

When the identifier is `{class-name}/{method-name}`, Asciidoctor must include the exact path after REST Docs resolves the placeholders. For example:

~~~text
build/generated-snippets/
└── customer-order-documentation-test/
    └── get-order/
        ├── http-request.adoc
        └── http-response.adoc
~~~

AsciiDoc page:

~~~adoc
== Get Customer Order

=== HTTP request
include::{snippets}/customer-order-documentation-test/get-order/http-request.adoc[]

=== HTTP response
include::{snippets}/customer-order-documentation-test/get-order/http-response.adoc[]
~~~

If you rename a class or method, the generated path changes as well. Update the includes alongside that change. To reduce coupling to Java test names, you can use explicit, stable identifiers for snippets included across multiple pages.

A practical strategy:

| Test type | Identifier | Include approach |
| --- | --- | --- |
| Internal snippets, many test classes | `{class-name}/{method-name}` | Use the class/method path |
| Snippets published in long-lived docs | `orders/get-customer` | Include by stable business name |
| Multi-request workflow | `{class-name}/{method-name}/{step}` or scenario/step name | Include each step in order |

Explicit identifier names reduce documentation churn when refactoring test names; placeholders reduce collisions and enable automation. Choose based on the level of stability your documentation requires.

## 9. Cleaning Up Old Snippets After Changing Identifiers

Parameterized identifiers do not delete old directories automatically. For example, if you change:

~~~java
document("orders/get");
~~~

to:

~~~java
document("{class-name}/{method-name}");
~~~

the `orders/get/` directory from a previous build may remain. If Asciidoctor still includes the old path, the documentation may continue displaying stale snippets.

With Gradle:

~~~bash
./gradlew clean test asciidoctor
~~~

With Maven:

~~~bash
mvn clean verify
~~~

A clean build deletes old outputs before tests generate fresh snippets. In incremental pipelines, ensure the output directory is properly managed as a test task/plugin output and is not shared across jobs.

## 10. Pre-Merge Review Checklist

| Question | Expected Result |
| --- | --- |
| Do two different tests use the same identifier? | No, unless intentionally producing a shared snippet set |
| Does the identifier include class/method when needed? | Yes |
| Does a test with multiple requests separate them? | Yes, using `{step}` or distinct scenario names |
| Do parameterized invocations share the same identifier? | Separated by scenario/invocation or intentionally consolidated |
| Do parallel tests share an output root and identifier? | Output roots isolated or execution serialized |
| Does `alwaysDo` record auxiliary requests? | Restricted strictly to requests needing documentation |
| Do Asciidoctor includes point to the new identifiers? | Yes |
| Does a clean build remove stale snippets? | Yes |

## 11. Practice Exercise

Create two test classes `CustomerOrderDocumentationTest` and `AdminOrderDocumentationTest`. Both have a `getOrder` method, but they call different endpoints and use different permissions.

Steps:

1. Use the fixed identifier `orders/get` in both tests, run the tests, and observe the shared output collision.
2. Change to `{class-name}/{method-name}` and verify that each class gets its own directory.
3. Create a workflow test sending two requests; use `{class-name}/{method-name}/{step}` to separate the two snippet sets.
4. Create a parameterized test for the `basic` and `pro` plans; choose a distinct, stable identifier for each scenario.
5. Enable parallel execution for the test group, identify any tests sharing the same output root/identifier, and isolate outputs or adjust execution scheduling.
6. Configure Asciidoctor to include the right customer and admin request/response snippets.
7. Run `clean test asciidoctor` and verify that no stale snippets are included.

**Completion criteria:** No two independent tests write to the same output root/identifier pair; workflow steps are separated; parallel tests have no file contention; documentation includes the exact snippets for the right scenarios.

## References

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs — Using Parameterized Output Directories](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Gradle User Manual — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Apache Maven Surefire Plugin — Parallel Test Execution](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html)
